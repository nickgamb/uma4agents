"""org-authority — the policy layer above a member.

The question this answers is the one that comes up every time someone is
shown the person-scale demo: *what if Alice does not own the data?* A firm
holds the account, Alice administers its sharing, and the firm has
obligations she cannot waive. UMA has always had a name for her role —
resource rights administrator — and no answer for the layer above it.

This service is that layer, and it is deliberately **its own party** rather
than a table inside anyone's authorization server:

    organization ──charter──▶ its own decision point (this + OPA)
         │                                  ▲
         │ envelope (a ceiling, not a policy)│ one question per request
         ▼                                  │
      member's authorization server ────────┘
         │
         ▼ terms, clamped to the envelope before an agent ever sees them
       agent

Four things cross that boundary and nothing else does:

* the **envelope** goes out — a ceiling a member's authority clamps her terms
  to, so what the organization requires is visible in the document the agent
  signs rather than applied invisibly at the door. It carries what her role
  shares with her, which is the half she joined for;
* a **decision** comes back, per request, from the organization's own engine.
  The charter's conditions and the admin's Rego stay on this side, in the
  same way Alice's tiers stay on hers;
* a **compliance report** goes the other way — that her terms are inside the
  envelope, and which of its fields bit. Never what her terms say;
* an **administration token**, short-lived and signed here, naming one member
  and one administrator. It is what lets him act on the agents that touch
  *this organization's* resources — and her authority is what scopes that to
  the charter's claims and writes his name into her record, because a limit
  this service enforced would be a limit this service could route around.

And one thing goes around the member entirely: **break-glass**. The
organization can reach resources it claims without her authority's
cooperation, because it signs those grants itself and the enforcement point
recognises the issuer. It cannot do so quietly: every one lands in her ledger
and on her screen before the data moves.

State is in memory. One replica, like Carol's authority in the same lab — an
organization is a single small thing here, and `make reset` rewinds it.
"""

import asyncio
import copy
import json
import os
import secrets
import time
import uuid

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from jwt.algorithms import OKPAlgorithm

import charter as charter_mod
from uma4a_http_sig import VerifyError, verify

ISSUER = os.environ.get("ORG_ISSUER", "https://northwind-org.uma.lab")
ORG_AUTHORITY = ISSUER.split("://", 1)[-1].rstrip("/")
ORG_ID = os.environ.get("ORG_ID", "northwind")
ORG_NAME = os.environ.get("ORG_NAME", "Northwind Capital")
KEY_PATH = os.environ.get("ORG_SIGNING_KEY", "/keys/org-ed25519.pem")
KID = os.environ.get("ORG_KID", "org-1")
OPA_URL = os.environ.get("OPA_URL", "http://opa:8181").rstrip("/")
CA_BUNDLE = os.environ.get("UMA4A_CA_BUNDLE")

# How an admin proves they administer this organization. OIDC against a realm
# of the organization's own — not a member's realm, which is the point: the
# admin is a different party from every member, and a deployment where one
# identity provider mints both has collapsed the two layers this service
# exists to keep apart.
ADMIN_ISSUER = os.environ.get(
    "ORG_ADMIN_ISSUER", "https://keycloak.uma.lab/realms/northwind")
ADMIN_METADATA_URL = os.environ.get(
    "ORG_ADMIN_METADATA_URL", f"{ADMIN_ISSUER}/.well-known/openid-configuration")
ADMIN_AUDIENCES = {a for a in os.environ.get(
    "ORG_ADMIN_CLIENTS", "meridian-org-console").split(",") if a}
# A static token for the acceptance containers, which have no browser to log
# in with. Absent in any deployment that has an identity provider.
ADMIN_TOKEN = os.environ.get("ORG_ADMIN_TOKEN") or None

# What an enforcement point presents to read membership and check the grants
# this service signs. The gateway is the firm's own, so a provisioned secret
# is the honest shape here — unlike a member's authority, which nobody was
# there to configure both ends of.
RS_TOKEN = os.environ.get("ORG_RS_TOKEN", "org-rs-dev-token")

JOIN_CODE = os.environ.get("ORG_JOIN_CODE", "NW-7K2F-QX")
# Who a break-glass grant is *for*. Configuration rather than a field on the
# request, and the difference is not cosmetic: an audience the caller chooses
# is an audience the caller can point at some other resource server that also
# trusts this organization. The enforcement point fronting the resources this
# charter claims is the only correct answer, and this service knows it without
# being told.
GLASS_AUDIENCE = os.environ.get("ORG_BREAK_GLASS_AUDIENCE",
                                "https://gateway.uma.lab")

# How long a decision may be answered from cache when OPA cannot be reached.
# Zero would make the organization's engine a single point of failure for
# every member's grant loop; unbounded would make a withdrawn rule take
# effect never. See `org_decision`.
OPA_GRACE_S = float(os.environ.get("ORG_OPA_GRACE_S", "60"))


def load_or_create_key() -> Ed25519PrivateKey:
    if os.path.exists(KEY_PATH):
        with open(KEY_PATH, "rb") as f:
            return serialization.load_pem_private_key(f.read(), password=None)
    key = Ed25519PrivateKey.generate()
    os.makedirs(os.path.dirname(KEY_PATH), exist_ok=True)
    with open(KEY_PATH, "wb") as f:
        f.write(key.private_bytes(serialization.Encoding.PEM,
                                  serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption()))
    return key


SIGNING_KEY = load_or_create_key()

app = FastAPI(title="org-authority")


def now() -> float:
    return time.time()


def utcstamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def event(name: str, **fields) -> None:
    # `name` rather than `kind`: a caller wanting to log *which kind of
    # notice* it sent would otherwise collide with the positional argument
    # and raise from inside the logging call — which is a spectacularly bad
    # place for an exception to come from, since it takes the operation
    # down with it and blames a line that was only trying to say what
    # happened.
    print(json.dumps({"ts": utcstamp(), "svc": "org-authority",
                      "event": name, **fields}), flush=True)


# --- State -------------------------------------------------------------------
#
# Versions rather than a document. A member's terms were clamped to a
# particular charter and an agreement was signed under it; "what did this
# organization require in March" has to stay answerable, for the same reason
# a terms document is never edited in place on the member's side.

CHARTERS: list[dict] = []
MEMBERS: dict[str, dict] = {}
# Outstanding invitations, one per person invited.
#
# An invitation is the direction this relationship usually runs in: an
# organization knows who works for it and says so, rather than handing out a
# code and hoping the right people type it. Both exist here because they fail
# differently — a code is right for onboarding a group at once, an invitation
# is right when the organization already knows the name.
#
# What it is *not* is a way to enrol somebody. It creates something she can
# accept or decline from her own portal, and until she does, nothing about
# her authority, her policy or her resources has changed. An organization
# that could add a member unilaterally would be an organization that could
# clamp a stranger's terms.
INVITES: dict[str, dict] = {}
ACTIVITY: list[dict] = []
GLASS: dict[str, dict] = {}          # jti -> the grant this service signed
_OPA_CACHE: dict[str, tuple[float, dict]] = {}


def current() -> dict:
    return CHARTERS[-1]


def note(name: str, **fields) -> None:
    """The organization's own record. Distinct from a member's ledger and
    kept separately on purpose — the admin console shows this one, and
    nothing in it is a read of anybody's policy."""
    ACTIVITY.append({**fields, "ts": utcstamp(), "kind": name})
    del ACTIVITY[:-500]
    event(name, **fields)


async def publish_charter(doc: dict, by: str) -> dict:
    """Validate, load the admin's rules into the engine, then version it.

    The order is the whole of it. A charter whose Rego does not compile must
    never become the charter in force: members would clamp to an envelope
    whose decision half cannot be evaluated, and every one of their grants
    would fail closed at once.
    """
    validated = charter_mod.validate(doc)
    await load_custom_rego(validated.get("rego") or "")
    entry = {
        "version": len(CHARTERS) + 1,
        "charter": validated,
        "published_at": utcstamp(),
        "by": by,
    }
    CHARTERS.append(entry)
    note("charter.published", version=entry["version"], by=by,
         rego=bool(validated.get("rego")))
    return entry


async def announce_charter(entry: dict) -> None:
    """Tell every member a new version is in force.

    Their authorities would find out anyway on the next envelope read, but
    "anyway" is up to a poll interval of requests decided under the old
    ceiling. Clearing `compliance` matters as much as the notification: it is
    this service's cached answer to "is this member's policy inside the
    envelope", and after a republish that answer is about a document that is
    no longer the charter.
    """
    for owner in list(MEMBERS):
        MEMBERS[owner]["compliance"] = None
        await notify_member(owner, {"kind": "charter_changed",
                                    "charter_version": entry["version"]})


# --- The engine --------------------------------------------------------------


async def opa(method: str, path: str, **kw) -> httpx.Response:
    async with httpx.AsyncClient(timeout=5.0) as c:
        return await c.request(method, f"{OPA_URL}{path}", **kw)


async def load_shipped_rego() -> None:
    with open(os.path.join(os.path.dirname(__file__), "org.rego")) as f:
        text = f.read()
    r = await opa("PUT", "/v1/policies/u4a-org", content=text.encode(),
                  headers={"content-type": "text/plain"})
    if r.status_code != 200:
        raise RuntimeError(f"the shipped policy module did not load: {r.text}")
    event("engine.loaded", module="u4a-org")


async def load_custom_rego(text: str) -> None:
    """The admin's own rules, or their removal.

    A compile error is returned to the console as the message OPA produced,
    unedited. An admin writing Rego wants the compiler's words and the line
    number, not this service's paraphrase of them.
    """
    if not text.strip():
        await opa("DELETE", "/v1/policies/u4a-custom")
        event("engine.loaded", module="u4a-custom", present=False)
        return
    r = await opa("PUT", "/v1/policies/u4a-custom", content=text.encode(),
                  headers={"content-type": "text/plain"})
    if r.status_code != 200:
        detail = r.json() if r.headers.get("content-type", "").startswith(
            "application/json") else {"message": r.text}
        raise ValueError(_compile_error(detail))
    event("engine.loaded", module="u4a-custom", present=True)


def _compile_error(detail: dict) -> str:
    errs = detail.get("errors") or []
    if not errs:
        return detail.get("message") or json.dumps(detail)
    lines = []
    for e in errs:
        loc = e.get("location") or {}
        where = f"line {loc['row']}" if loc.get("row") else ""
        lines.append(" ".join(x for x in (where, e.get("message", "")) if x))
    return "; ".join(lines)


async def org_decision(member: str, request_facts: dict,
                       role: dict | None = None) -> dict:
    """One request, judged by the organization's engine.

    Failure is not an allow. If the engine cannot be reached, a decision it
    made recently for the same shape of request stands for a short grace
    window and then the answer becomes a refusal with a reason — because the
    charter is the organization's protection of its own data, and a request
    that slipped through while the engine was down would be exactly the
    access the charter was written to prevent.
    """
    # `role` sits beside `request` rather than inside it, because it is not
    # something about the request — it is what the organization has given
    # this member. The engine reads `input.role.delegation`, and burying it
    # under `input.request` was how the delegation rule silently evaluated
    # against a missing field and defaulted to "none" for everyone.
    payload = {"input": {"member": member, "charter": current()["charter"],
                         "role": role or {}, "request": request_facts}}
    key = json.dumps(payload, sort_keys=True)
    try:
        r = await opa("POST", "/v1/data/u4a/org/decision", json=payload)
        r.raise_for_status()
        decision = r.json().get("result") or {"effect": "allow", "because": []}
        _OPA_CACHE[key] = (now(), decision)
        del_stale = [k for k, (t, _) in _OPA_CACHE.items()
                     if t < now() - OPA_GRACE_S]
        for k in del_stale:
            _OPA_CACHE.pop(k, None)
        return decision
    except Exception as exc:                                    # noqa: BLE001
        cached = _OPA_CACHE.get(key)
        if cached and cached[0] > now() - OPA_GRACE_S:
            event("engine.unreachable", result="cached", error=str(exc))
            return cached[1]
        event("engine.unreachable", result="refused", error=str(exc))
        return {"effect": "refuse",
                "because": ["the organization's policy engine could not be "
                            "reached, and its policy is not something this "
                            "request may proceed without"]}


# --- Identity ----------------------------------------------------------------


def _bearer(request: Request) -> str:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="bearer token required")
    return header[7:]


_ADMIN_JWKS: tuple[float, list] = (0.0, [])


def admin_issuer_keys() -> list:
    global _ADMIN_JWKS
    if _ADMIN_JWKS[0] > now():
        return _ADMIN_JWKS[1]
    with httpx.Client(verify=CA_BUNDLE or True, timeout=5.0) as c:
        meta = c.get(ADMIN_METADATA_URL)
        meta.raise_for_status()
        jwks = c.get(meta.json()["jwks_uri"])
        jwks.raise_for_status()
    _ADMIN_JWKS = (now() + 300, jwks.json()["keys"])
    return _ADMIN_JWKS[1]


def require_admin(request: Request) -> str:
    """Whoever is administering this organization. Never a member.

    A member's credential is worth nothing here and an admin's is worth
    nothing at a member's authority, which is what makes "the layer above
    her" a party rather than a privilege level.
    """
    token = _bearer(request)
    if ADMIN_TOKEN and secrets.compare_digest(token, ADMIN_TOKEN):
        return "console"
    from jwt.algorithms import RSAAlgorithm

    try:
        header = jwt.get_unverified_header(token)
        for jwk_dict in admin_issuer_keys():
            if jwk_dict.get("use") == "enc":
                continue
            if header.get("kid") and jwk_dict.get("kid") != header["kid"]:
                continue
            try:
                claims = jwt.decode(
                    token, RSAAlgorithm.from_jwk(json.dumps(jwk_dict)),
                    algorithms=["RS256"], issuer=ADMIN_ISSUER,
                    options={"verify_aud": False})
            except jwt.InvalidTokenError:
                continue
            audiences = set(claims.get("aud") or []) | {claims.get("azp")}
            if ADMIN_AUDIENCES and not (audiences & ADMIN_AUDIENCES):
                raise HTTPException(status_code=403,
                                    detail="that token was issued for a "
                                           "different client")
            return claims.get("preferred_username") or claims.get("sub")
    except HTTPException:
        raise
    except Exception as exc:                                    # noqa: BLE001
        raise HTTPException(status_code=401,
                            detail=f"admin token did not verify: {exc}") from exc
    raise HTTPException(status_code=401, detail="admin token did not verify")


def require_rs(request: Request) -> None:
    if not secrets.compare_digest(_bearer(request), RS_TOKEN):
        raise HTTPException(status_code=401, detail="unknown enforcement point")


def membership_token(owner: str) -> str:
    return jwt.encode(
        {"iss": ISSUER, "sub": owner, "org": ORG_ID, "iat": int(now()),
         "jti": uuid.uuid4().hex},
        SIGNING_KEY, algorithm="EdDSA",
        headers={"typ": "u4a-membership+jwt", "kid": KID})


def require_member(request: Request) -> str:
    """The authorization server of a member, acting for that member.

    The token was handed out at enrolment and is presented by her authority,
    never by her browser: the organization and the member's browser have no
    relationship, and one is not being invented here.
    """
    token = _bearer(request)
    try:
        claims = jwt.decode(token, SIGNING_KEY.public_key(),
                            algorithms=["EdDSA"], issuer=ISSUER,
                            options={"verify_aud": False})
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401,
                            detail=f"membership token did not verify: {exc}")
    owner = claims.get("sub") or ""
    member = MEMBERS.get(owner)
    if member is None or member.get("token_jti") != claims.get("jti"):
        # A token from before the member left, or from before she rejoined.
        # Both are "you are not a member", and saying so is what tells her
        # authority to stop clamping and to drop the enrolment.
        raise HTTPException(status_code=403,
                            detail="that membership is no longer current")
    return owner


# --- Discovery ---------------------------------------------------------------


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "org": ORG_ID, "charter_version": current()["version"]}


@app.get("/jwks")
async def jwks() -> dict:
    jwk = json.loads(OKPAlgorithm.to_jwk(SIGNING_KEY.public_key()))
    jwk.update({"kid": KID, "use": "sig", "alg": "EdDSA"})
    return {"keys": [jwk]}


@app.get("/.well-known/u4a-organization")
async def discovery() -> dict:
    """What a member's authority needs to find in order to enrol, and what an
    enforcement point needs in order to check a grant this service signed."""
    glass = current()["charter"].get("break_glass") or {}
    return {
        "issuer": ISSUER,
        "organization": {"id": ORG_ID, "name": ORG_NAME},
        "jwks_uri": f"{ISSUER}/jwks",
        "envelope_endpoint": f"{ISSUER}/member/envelope",
        "decision_endpoint": f"{ISSUER}/decision",
        "enrolment_endpoint": f"{ISSUER}/member/join",
        "introspection_endpoint": f"{ISSUER}/introspect",
        "charter_version": current()["version"],
        "break_glass": bool(glass.get("enabled")),
    }


@app.on_event("startup")
async def boot() -> None:
    if ADMIN_TOKEN and ADMIN_ISSUER:
        # Both configured. Correct for this lab — the acceptance job has no
        # browser to log in with — and wrong anywhere else, because the static
        # credential is a second way to be an administrator that no identity
        # provider can see, revoke or attribute. Said out loud at startup
        # rather than left in a comment somebody has to go looking for.
        event("admin.static_credential_enabled", issuer=ADMIN_ISSUER,
              note="a static admin token is accepted alongside the identity "
                   "provider; do not do this outside a lab")
    # The engine first, and with patience: this service and OPA come up
    # together, and a charter published against an engine that is not yet
    # listening would be a charter in force with nothing evaluating it.
    for attempt in range(30):
        try:
            await load_shipped_rego()
            break
        except Exception as exc:                                # noqa: BLE001
            if attempt == 29:
                raise
            event("engine.waiting", error=str(exc))
            await asyncio.sleep(1.0)
    if not CHARTERS:
        # Published rather than assigned, so version 1 goes through the same
        # validation and the same engine load as every later edit.
        await publish_charter(charter_mod.DEFAULT_CHARTER, by="default")


# --- Enrolment ---------------------------------------------------------------
#
# A member joins by presenting a code the organization gave her, and the
# first thing that happens is not the join: it is being shown, in sentences,
# what she is about to be governed by and what it will do to the terms she
# has already written. Consent to a policy nobody read is the failure mode
# this whole system is arguing against, so the preview is a first-class
# endpoint rather than a courtesy in the portal.
#
# In a real deployment membership would be bound to the organization's
# identity provider and leaving would be an act of the organization, not a
# button in the member's own portal. The lab does it the other way round
# because the interesting property survives either: leaving cannot widen
# anything. Her terms were narrowed on the way in and they stay narrowed on
# the way out — an envelope is a ceiling, and removing a ceiling does not
# raise a floor.


def _authorize_enrolment(owner: str, code: str) -> str:
    """How this person is entitled to join, or a refusal.

    Two ways, and they are different in kind. The shared code admits anybody
    who has it, which is what makes it right for onboarding a group and wrong
    as the only mechanism. An invitation names one person and is good once —
    the organization already knew who she was.
    """
    given = (code or "").strip()
    invite = INVITES.get(owner)
    if invite and invite["state"] == "open" and secrets.compare_digest(
            given, invite["code"]):
        return "invitation"
    if secrets.compare_digest(given.upper(), JOIN_CODE.upper()):
        return "code"
    raise HTTPException(status_code=403,
                        detail="that is not this organization's enrolment code, "
                               "and it is not an invitation addressed to you")


def _check_code(code: str) -> None:
    """The preview path, which is not addressed to anyone yet.

    An invitation code works here too — she is about to be shown what it
    means, which is the whole point of previewing — and so does the shared
    code. Neither reveals anything an enrolled member could not already read.
    """
    given = (code or "").strip()
    if secrets.compare_digest(given.upper(), JOIN_CODE.upper()):
        return
    if any(i["state"] == "open" and secrets.compare_digest(given, i["code"])
           for i in INVITES.values()):
        return
    raise HTTPException(status_code=403,
                        detail="that is not this organization's enrolment code")


def role_of(owner: str) -> tuple[str | None, dict]:
    """Which role this member holds, and what it grants.

    A member with no role is still a member — she is governed by the charter
    and has access to nothing — which is a legitimate state and not an error.
    It is what an administrator leaves someone in while deciding.
    """
    member = MEMBERS.get(owner) or {}
    roles = current()["charter"].get("roles") or {}
    role_id = member.get("role")
    role = dict(roles.get(role_id) or {})
    if role:
        # Carried so that a rule in the engine can name the group — `input.role.id
        # == "analyst"` is the shape most of an organization's operating rules
        # want, and without it the id is only a key in a map the rule cannot see.
        role["id"] = role_id
    return role_id, role


def _envelope_doc(owner: str | None = None) -> dict:
    """The ceiling, and — for a member — what her role gives her.

    Two halves that travel together because they are two halves of one
    bargain. The organization gets policy over its own resources; the member
    gets access to them. A document that carried only the first would
    describe an arrangement nobody would join.
    """
    entry = current()
    role_for_doc = (
        role_of(owner)[1] if owner is not None and owner in MEMBERS
        else (entry["charter"].get("roles") or {}).get(
            entry["charter"].get("default_role")) or {})
    doc = {
        "org": ORG_ID,
        "name": ORG_NAME,
        "issuer": ISSUER,
        "charter_version": entry["version"],
        "published_at": entry["published_at"],
        **charter_mod.envelope_of(entry["charter"], role_for_doc),
    }
    if owner is None:
        # A preview, before anyone is a member. Show what the default role
        # would give her, since that is what she would actually receive.
        default = entry["charter"].get("default_role")
        role = (entry["charter"].get("roles") or {}).get(default) or {}
        doc.update(role=default, role_name=role.get("name"),
                   grants=list(role.get("grants") or []),
                   delegation=role.get("delegation", "none"))
        return doc
    role_id, role = role_of(owner)
    doc.update(role=role_id, role_name=role.get("name"),
               grants=list(role.get("grants") or []),
               delegation=role.get("delegation", "none"))
    return doc


@app.post("/member/preview")
async def member_preview(request: Request) -> dict:
    body = await request.json()
    _check_code(body.get("code") or "")
    return _envelope_doc()


@app.post("/member/join")
async def member_join(request: Request) -> dict:
    body = await request.json()
    owner = (body.get("owner") or "").strip()
    as_uri = (body.get("as_uri") or "").strip()
    if not owner:
        raise HTTPException(status_code=400, detail="which member is joining?")
    how = _authorize_enrolment(owner, body.get("code") or "")
    if how == "invitation":
        # Spent. An invitation names one person and admits her once; leaving
        # and rejoining is a new decision by the organization, not a code she
        # kept.
        INVITES.pop(owner, None)
    token = membership_token(owner)
    MEMBERS[owner] = {
        "owner": owner,
        "as_uri": as_uri,
        "joined": utcstamp(),
        # What she can reach on day one. An administrator can change it; the
        # charter says what "day one" means, so enrolment is never a state
        # where somebody is governed and has nothing.
        "role": current()["charter"].get("default_role"),
        "token_jti": jwt.decode(token, options={"verify_signature": False})["jti"],
        "charter_version": current()["version"],
        # Filled in by her authority once it has clamped. Until then the
        # console shows the honest answer, which is that it does not know.
        "compliance": None,
    }
    note("member.joined", member=owner, as_uri=as_uri, via=how,
         role=MEMBERS[owner]["role"], charter_version=current()["version"])
    return {"membership_token": token, **_envelope_doc(owner)}


@app.get("/member/invitation")
async def member_invitation(owner: str = "") -> dict:
    """Whether this organization has asked for this person, and what it would
    mean if she said yes.

    Read by her authorization server, which was configured with this
    organization's address and is asking on her behalf. It carries the
    invitation's code, which is what makes the invitation self-contained: the
    organization has already decided she may join, so nothing else has to
    reach her out of band.

    The honest limit, since this is unauthenticated and the alternative does
    not exist: anyone who can reach this endpoint can learn whether a
    *name* has been invited. Before enrolment there is no relationship to
    authenticate — her authority has never spoken to this service and this
    service has never heard of her. A deployment where that matters
    federates the identity provider and issues invitations against it
    instead of a name; the layer being demonstrated here is the same either
    way.
    """
    invite = INVITES.get((owner or "").strip())
    if invite is None or invite["state"] != "open":
        return {"invited": False}
    return {"invited": True, "org": ORG_ID, "name": ORG_NAME, "issuer": ISSUER,
            "code": invite["code"], "by": invite["by"], "note": invite["note"],
            "created": invite["created"],
            "charter_version": current()["version"],
            "summary": charter_mod.summarize(current()["charter"])}


@app.post("/member/invitation/decline")
async def member_decline(request: Request) -> dict:
    """No, thank you.

    Recorded rather than silently deleted, and it goes in the organization's
    activity where an administrator will see it. A declined invitation is a
    fact about a relationship, and a console that showed only acceptances
    would let an administrator believe an invitation was still travelling.
    """
    body = await request.json()
    owner = (body.get("owner") or "").strip()
    invite = INVITES.get(owner)
    if invite is None or invite["state"] != "open":
        raise HTTPException(status_code=404, detail="no open invitation")
    if not secrets.compare_digest(body.get("code") or "", invite["code"]):
        raise HTTPException(status_code=403, detail="that is not her invitation")
    invite["state"] = "declined"
    invite["decided"] = utcstamp()
    note("invitation.declined", member=owner)
    return {"declined": True}


@app.post("/member/leave")
async def member_leave(request: Request) -> dict:
    owner = require_member(request)
    MEMBERS.pop(owner, None)
    note("member.left", member=owner)
    return {"left": ORG_ID, "member": owner}


@app.get("/member/envelope")
async def member_envelope(request: Request) -> dict:
    """The ceiling, re-read. Her authority polls this rather than being
    pushed to, because a push that failed would leave her clamping to a
    charter that is no longer the charter — and the failure would be silent
    on both sides."""
    owner = require_member(request)
    MEMBERS[owner]["last_seen"] = utcstamp()
    return _envelope_doc(owner)


@app.post("/member/compliance")
async def member_compliance(request: Request) -> dict:
    """Her authority reporting that her terms are inside the envelope.

    What crosses is a count and the names of the envelope fields that bit —
    never a value from her policy. The organization is entitled to know its
    ceiling is being applied. It is not entitled to read what she wrote
    underneath it, and the difference between those two sentences is the
    reason this endpoint takes a summary instead of her tiers.
    """
    owner = require_member(request)
    body = await request.json()
    MEMBERS[owner]["compliance"] = {
        "charter_version": int(body.get("charter_version") or 0),
        "resources_governed": int(body.get("resources_governed") or 0),
        "tiers_governed": int(body.get("tiers_governed") or 0),
        "clamped_fields": sorted(set(body.get("clamped_fields") or [])),
        "within": bool(body.get("within", True)),
        "reported": utcstamp(),
    }
    MEMBERS[owner]["charter_version"] = int(
        body.get("charter_version") or MEMBERS[owner]["charter_version"])
    note("member.compliance", member=owner,
         charter_version=MEMBERS[owner]["compliance"]["charter_version"],
         clamped=MEMBERS[owner]["compliance"]["clamped_fields"])
    return {"recorded": True}


@app.post("/decision")
async def decision(request: Request) -> dict:
    """The organization's answer about one request, for a member's authority
    to fold into its own.

    It can only ever be `allow`, `ask` or `refuse`, and `allow` means "the
    organization has no objection" rather than "grant this" — the member's
    policy is what permits. That is the whole composition rule and it is one
    sentence long: **both layers must allow, and either may refuse.**
    """
    owner = require_member(request)
    facts = await request.json()
    resource_id = facts.get("resource_id") or ""
    if not charter_mod.claims_match(resource_id, current()["charter"]["claims"]):
        # Not the organization's business. Saying so explicitly, rather than
        # returning a permissive answer, is what keeps a member's own
        # resources out of this: her authority can see that the organization
        # did not judge them at all.
        return {"effect": "allow", "because": [], "governed": False,
                "charter_version": current()["version"]}
    role_id, role = role_of(owner)
    # Whether this member may reach the resource at all, before anything is
    # asked about the agent. A role is the ordinary way an organization says
    # who may see what, and it is checked here rather than folded into the
    # engine because "you were never given this" is a different answer from
    # "your request was judged and refused".
    if not charter_mod.claims_match(resource_id, role.get("grants") or []):
        return {"effect": "refuse", "governed": True,
                "charter_version": current()["version"],
                "because": [
                    f"{ORG_NAME} has not shared {resource_id} with this member"
                    + (f" — their role is {role.get('name') or role_id}"
                       if role_id else ", who holds no role here")]}
    verdict = await org_decision(
        owner, facts,
        role={"id": role_id, "name": role.get("name"),
              "delegation": role.get("delegation", "none"),
              "grants": list(role.get("grants") or [])})
    note("decision", member=owner, resource=resource_id,
         effect=verdict["effect"], because=verdict.get("because"))
    return {**verdict, "governed": True, "charter_version": current()["version"]}


# --- Break-glass -------------------------------------------------------------
#
# The one direction that is genuinely an override, and the reason this is a
# separate code path rather than a flag on a decision: it does not go through
# the member's authority at all. The organization signs the grant itself with
# a key the enforcement point already knows, so it works whether or not a
# member's authorization server chose to cooperate — which is the only shape
# in which "the organization owns the data" is a technical fact rather than a
# hope.
#
# Three things bound it, and all three are in the charter the member read
# before she joined:
#
#   * it reaches only resources the charter both claims and names for
#     break-glass. An override outside what was disclosed is not an override,
#     it is a second front door;
#   * it is short, single-use and bound to the key that asked for it;
#   * it is loud. The member is told before the data moves, in her own
#     ledger and on her own screen, and the notice is signed by this service
#     so she can tell it came from her organization and not from an agent
#     claiming to be one.
#
# Who may invoke: an admin opens a voucher (a person at the organization
# decided), or the agent's signing key is published by an operator origin the
# charter lists. Nothing else.

VOUCHERS: dict[str, dict] = {}
_DIRECTORY_CACHE: dict[str, tuple[float, list]] = {}
# Signatures already spent, for as long as one could still be replayed.
#
# An RFC 9421 signature is valid for a window — sixty seconds here — and a
# captured request presented twice inside it would otherwise mint a second
# override. The voucher path is already protected, because redeeming one
# consumes it; the operator path is not, and an override is the last place to
# leave a replay open. Keyed on the signature and swept on use, so the table
# is bounded by the window rather than by traffic.
_SPENT_SIGNATURES: dict[str, float] = {}
SIGNATURE_WINDOW_S = 60.0


def _same_origin(a: str, b: str) -> bool:
    from urllib.parse import urlparse

    pa, pb = urlparse(a), urlparse(b)
    return (pa.scheme, pa.netloc) == (pb.scheme, pb.netloc)


def invoker_published_key(origin: str, jwk_thumb: str) -> bool:
    """Whether a listed operator publishes this key.

    The same check a member's authority makes before believing an agent's
    operator claim, and it is here for the same reason: pointing at an origin
    proves nothing, and only the operator can put a key in the directory it
    serves.
    """
    directory = f"{origin.rstrip('/')}/.well-known/http-message-signatures-directory"
    cached = _DIRECTORY_CACHE.get(directory)
    if cached and cached[0] > now():
        keys = cached[1]
    else:
        try:
            r = httpx.get(directory, timeout=5.0, follow_redirects=False,
                          verify=CA_BUNDLE or True)
            r.raise_for_status()
            keys = r.json().get("keys") or []
            _DIRECTORY_CACHE[directory] = (now() + 300, keys)
        except Exception as exc:                                # noqa: BLE001
            event("invoker_directory.unresolved", origin=origin, error=str(exc))
            return False
    for key in keys:
        if key.get("kty") != "OKP":
            continue
        if _thumbprint(key) == jwk_thumb:
            return True
    return False


def _thumbprint(jwk: dict) -> str:
    import base64
    import hashlib

    canonical = json.dumps({"crv": jwk["crv"], "kty": jwk["kty"], "x": jwk["x"]},
                           separators=(",", ":"), sort_keys=True)
    return "jkt:" + base64.urlsafe_b64encode(
        hashlib.sha256(canonical.encode()).digest()).rstrip(b"=").decode()


async def notify_member(owner: str, payload: dict) -> None:
    """Tell a member's authority something, signed.

    Signed rather than merely posted, because the receiving side has to be
    able to tell the organization's notice from an agent's forgery of one —
    and it can: it holds this service's JWKS from the moment its owner
    enrolled.
    """
    member = MEMBERS.get(owner) or {}
    as_uri = member.get("as_uri")
    if not as_uri:
        return
    notice = jwt.encode({"iss": ISSUER, "sub": owner, "org": ORG_ID,
                         "iat": int(now()), **payload},
                        SIGNING_KEY, algorithm="EdDSA",
                        headers={"typ": "u4a-org-notice+jwt", "kid": KID})
    try:
        async with httpx.AsyncClient(verify=CA_BUNDLE or True, timeout=5.0) as c:
            r = await c.post(f"{as_uri.rstrip('/')}/org/notice",
                             json={"notice": notice})
        event("member.notified", member=owner, notice=payload.get("kind"),
              status=r.status_code)
    except Exception as exc:                                    # noqa: BLE001
        # Worth being precise about what this failure means. The notice is
        # how a member learns; it is not what authorises the grant, and
        # holding the grant back until she can be reached would make an
        # unreachable member into an outage. So the grant stands, the failure
        # is recorded here, and her authority reconciles when it next reads
        # this organization's record.
        note("notice.failed", member=owner, notice=payload.get("kind"),
             error=str(exc))


@app.post("/break-glass")
async def break_glass(request: Request) -> JSONResponse:
    body = await request.body()
    req = json.loads(body or b"{}")
    owner = (req.get("owner") or "").strip()
    resource_id = (req.get("resource_id") or "").strip()
    reason = (req.get("reason") or "").strip()
    glass = current()["charter"].get("break_glass") or {}

    if not glass.get("enabled"):
        raise HTTPException(status_code=403,
                            detail="this organization's charter does not "
                                   "permit break-glass access")
    # Proof of possession of the key the grant will be bound to, and the
    # first thing checked rather than the last.
    #
    # Ordering matters here in two directions. An unsigned caller must not be
    # able to walk this endpoint for a map of the charter — which resources
    # are break-glass eligible, which members exist — by reading the
    # refusals it gets back. And a request whose bytes were altered after
    # signing must be refused as a forgery rather than evaluated on its
    # altered contents, which is only guaranteed if nothing has read those
    # contents yet.
    #
    # Nothing here takes a key as a field on its own account: a key presented
    # as data is a key anyone can present. It is checked against the
    # signature over this exact request.
    signer = req.get("agent_jwk") or {}
    try:
        pub = OKPAlgorithm.from_jwk(json.dumps(signer))
        verify(method="POST", authority=ORG_AUTHORITY, path="/break-glass",
               authorization="",
               signature_input=request.headers.get("signature-input", ""),
               signature=request.headers.get("signature", ""),
               public_key=pub, body=body, require_digest=True,
               digest_header=request.headers.get("content-digest"))
    except (KeyError, ValueError, VerifyError) as exc:
        raise HTTPException(
            status_code=401,
            detail=f"break-glass must be signed by the key it will bind to: {exc}")

    if owner not in MEMBERS:
        raise HTTPException(status_code=404,
                            detail=f"{owner!r} is not a member of this organization")
    if not charter_mod.claims_match(resource_id, glass.get("resources") or []):
        raise HTTPException(
            status_code=403,
            detail=f"the charter does not name {resource_id!r} for break-glass")
    if glass.get("require_reason") and not reason:
        raise HTTPException(status_code=400,
                            detail="the charter requires a stated reason")

    signature = request.headers.get("signature", "")
    for spent, when in list(_SPENT_SIGNATURES.items()):
        if when < now() - SIGNATURE_WINDOW_S:
            _SPENT_SIGNATURES.pop(spent, None)
    if signature in _SPENT_SIGNATURES:
        event("break_glass.replay_refused")
        raise HTTPException(
            status_code=409,
            detail="that request has already been redeemed. Sign a new one: "
                   "an override is issued once per request, not once per "
                   "signature that is still inside its window.")
    _SPENT_SIGNATURES[signature] = now()

    thumb = _thumbprint(signer)
    authorised_by = None
    voucher = VOUCHERS.pop(req.get("voucher") or "", None)
    if voucher and voucher["expires"] > now() and voucher["owner"] == owner:
        authorised_by = f"voucher from {voucher['admin']}"
    else:
        for origin in glass.get("invokers") or []:
            if invoker_published_key(origin, thumb):
                authorised_by = f"operator {origin}"
                break
    if authorised_by is None:
        raise HTTPException(
            status_code=403,
            detail="break-glass needs either a voucher opened by an "
                   "administrator or a key published by an operator this "
                   "charter lists")

    ttl = min(int(req.get("expires_in") or glass.get("max_expires_in") or 900),
              int(glass.get("max_expires_in") or 900))
    # An override is an exception to a member's policy. It is not an exception
    # to the charter she was shown: whatever the caller asked for, what comes
    # back is bounded by what this organization says may ever be granted over
    # its resources.
    allowed = (current()["charter"].get("envelope") or {}).get("allowed_scopes")
    asked = list(req.get("scopes") or [])
    scopes = [x for x in asked if x in allowed] if allowed is not None else asked
    if asked and not scopes:
        raise HTTPException(
            status_code=403,
            detail=f"this charter does not allow {', '.join(asked)} over its "
                   f"resources, under break-glass or otherwise")
    jti = f"bg_{uuid.uuid4().hex[:12]}"
    exp = int(now()) + ttl
    claims = {
        "iss": ISSUER,
        "sub": req.get("agent_sub") or "aauth:pseudonymous-agent",
        "owner": owner,
        "aud": GLASS_AUDIENCE,
        "jti": jti,
        "exp": exp,
        "cnf": {"jwk": signer},
        "permissions": [{"resource_id": resource_id, "resource_scopes": scopes,
                         "exp": exp}],
        # What makes it recognisable as an override rather than a grant. The
        # enforcement point reads this, the member's ledger keeps it, and
        # nothing about it is inferable — an override that looked like an
        # ordinary grant would be the worst possible version of this feature.
        "break_glass": {
            "org": ORG_ID,
            "reason": reason,
            "authorised_by": authorised_by,
            "charter_version": current()["version"],
        },
        "single_use": True,
    }
    if req.get("operation"):
        claims["operation"] = req["operation"]
    token = jwt.encode(claims, SIGNING_KEY, algorithm="EdDSA",
                       headers={"typ": "aa-auth+jwt", "kid": KID})
    GLASS[jti] = {"claims": claims, "spent": False, "issued": utcstamp(),
                  "member": owner, "resource_id": resource_id,
                  "reason": reason, "authorised_by": authorised_by}
    note("break_glass.granted", member=owner, resource=resource_id, jti=jti,
         authorised_by=authorised_by, expires_in=ttl)
    await notify_member(owner, {
        "kind": "break_glass",
        "resource_id": resource_id,
        "scopes": scopes,
        "reason": reason,
        "authorised_by": authorised_by,
        "expires_in": ttl,
        "jti": jti,
        "charter_version": current()["version"],
    })
    return JSONResponse({"access_token": token, "token_type": "PoP",
                         "expires_in": ttl, "break_glass": claims["break_glass"]})


# --- What an enforcement point asks -----------------------------------------


@app.get("/membership/{owner}")
async def membership(owner: str, request: Request) -> dict:
    """Whether this owner is governed here, and by what.

    Read by the enforcement point in front of the resource, which is the
    third place the envelope is checked and the only one neither the member
    nor her authority controls. A member's authority applying the ceiling is
    what makes it *visible*; this is what makes it *hold*.
    """
    require_rs(request)
    member = MEMBERS.get(owner)
    if member is None:
        return {"member": False}
    return {"member": True, "since": member["joined"], **_envelope_doc(owner)}


@app.post("/introspect")
async def introspect(request: Request, token: str = Form(...)) -> dict:
    """RFC 7662 over a grant this service signed. Shaped exactly like the
    member authority's answer, so the enforcement point's code path is the
    same one — only the issuer it asked differs."""
    require_rs(request)
    try:
        claims = jwt.decode(token, SIGNING_KEY.public_key(),
                            algorithms=["EdDSA"], issuer=ISSUER,
                            options={"verify_aud": False})
    except jwt.InvalidTokenError as exc:
        return {"active": False, "error": str(exc)}
    rec = GLASS.get(claims.get("jti") or "")
    if rec is None:
        return {"active": False, "error": "unknown_grant"}
    if rec["spent"]:
        return {"active": False, "error": "already_consumed"}
    if claims["owner"] not in MEMBERS:
        # She left. An override rests entirely on membership, so it stops the
        # moment membership does — including for a token already issued.
        return {"active": False, "error": "not_a_member"}
    return {
        "active": True,
        "family": claims["jti"],
        "iss": claims["iss"],
        "sub": claims.get("sub"),
        "exp": claims["exp"],
        "permissions": claims["permissions"],
        "cnf": claims.get("cnf"),
        "contract": None,
        "single_use": True,
        "operation": claims.get("operation"),
        "break_glass": claims["break_glass"],
    }


@app.post("/consume")
async def consume(request: Request, token: str = Form(...)) -> dict:
    require_rs(request)
    try:
        claims = jwt.decode(token, SIGNING_KEY.public_key(),
                            algorithms=["EdDSA"], issuer=ISSUER,
                            options={"verify_aud": False})
    except jwt.InvalidTokenError as exc:
        return {"consumed": False, "error": str(exc)}
    rec = GLASS.get(claims.get("jti") or "")
    if rec is None or rec["spent"]:
        return {"consumed": False, "error": "already_consumed"}
    rec["spent"] = True
    note("break_glass.spent", member=rec["member"], jti=claims["jti"],
         resource=rec["resource_id"])
    return {"consumed": True, "family": claims["jti"]}


@app.post("/audit/access")
async def audit_access(request: Request) -> dict:
    """The enforcement point reporting a call it allowed under an override.

    Forwarded to the member's authority rather than only kept here. Her
    ledger is where she looks, and an override that showed up only in the
    organization's records would be an override she has to be told about by
    the party that performed it.
    """
    require_rs(request)
    body = await request.json()
    rec = GLASS.get(body.get("family") or "") or {}
    owner = rec.get("member") or body.get("owner") or ""
    note("break_glass.used", member=owner, tool=body.get("tool"),
         jti=body.get("family"))
    await notify_member(owner, {
        "kind": "break_glass_used",
        "jti": body.get("family"),
        "tool": body.get("tool"),
        "summary": body.get("summary"),
        "resource_id": rec.get("resource_id"),
        "reason": rec.get("reason"),
    })
    return {"recorded": True}


# --- Admin API (the console's backend) --------------------------------------


@app.get("/admin/org")
async def admin_org(request: Request) -> dict:
    admin = require_admin(request)
    entry = current()
    return {
        "id": ORG_ID,
        "name": ORG_NAME,
        "issuer": ISSUER,
        "admin": admin,
        "join_code": JOIN_CODE,
        "charter_version": entry["version"],
        "published_at": entry["published_at"],
        "published_by": entry["by"],
        "versions": len(CHARTERS),
        "members": len(MEMBERS),
        "break_glass": bool((entry["charter"].get("break_glass") or {}).get("enabled")),
        "claims": entry["charter"].get("claims") or [],
        "summary": charter_mod.summarize(entry["charter"]),
    }


@app.get("/admin/charter")
async def admin_charter(request: Request) -> dict:
    require_admin(request)
    entry = current()
    return {"version": entry["version"], "published_at": entry["published_at"],
            "published_by": entry["by"], "charter": entry["charter"],
            "summary": charter_mod.summarize(entry["charter"])}


@app.put("/admin/charter")
async def admin_put_charter(request: Request) -> dict:
    """A new version of the policy. Never an edit of the one in force.

    Members clamped their terms to a particular version and agreements were
    signed under it, so "what did this organization require when that was
    agreed" has to stay answerable. Same reason a member's terms document is
    versioned rather than edited: a policy that can change retroactively is
    not a policy anyone can rely on having read.
    """
    admin = require_admin(request)
    doc = await request.json()
    try:
        entry = await publish_charter(doc, by=admin)
    except ValueError as exc:
        # The console shows this text. It is either the charter validator
        # saying which field is wrong, or OPA's own compiler saying which
        # line is — and in both cases the words that help are the specific
        # ones, not a paraphrase.
        raise HTTPException(status_code=400, detail=str(exc))
    await announce_charter(entry)
    return {"version": entry["version"], "charter": entry["charter"],
            "summary": charter_mod.summarize(entry["charter"])}


@app.get("/admin/charter/versions")
async def admin_versions(request: Request) -> list:
    require_admin(request)
    return [{"version": e["version"], "published_at": e["published_at"],
             "by": e["by"], "name": e["charter"]["name"]}
            for e in reversed(CHARTERS)]


@app.get("/admin/charter/versions/{version}")
async def admin_version(version: int, request: Request) -> dict:
    require_admin(request)
    for e in CHARTERS:
        if e["version"] == version:
            return e
    raise HTTPException(status_code=404, detail="no such charter version")


@app.get("/admin/members")
async def admin_members(request: Request) -> list:
    """Who is in the organization, and whether the ceiling is being applied.

    Note what is not here: what any of them permits. The console can tell an
    administrator that Alice's terms are inside the envelope and which of its
    fields narrowed them. It cannot show him her policy, and that is not an
    omission — an organization that could read every member's private
    arrangements would have replaced the member layer rather than sat above
    it.
    """
    require_admin(request)
    out = []
    for owner, m in sorted(MEMBERS.items()):
        compliance = m.get("compliance")
        role_id, role = role_of(owner)
        out.append({
            "owner": owner,
            "as_uri": m.get("as_uri"),
            "joined": m["joined"],
            "role": role_id,
            "role_name": role.get("name"),
            "grants": list(role.get("grants") or []),
            "delegation": role.get("delegation", "none"),
            "last_seen": m.get("last_seen"),
            "charter_version": m.get("charter_version"),
            "current_version": current()["version"],
            "compliance": compliance,
            "state": ("unreported" if not compliance
                      else "stale" if compliance["charter_version"] != current()["version"]
                      else "within" if compliance["within"] else "outside"),
        })
    return out


@app.post("/admin/members/{owner}/role")
async def admin_set_role(owner: str, request: Request) -> dict:
    """What this member may reach, and what she may let an agent do with it.

    The only endpoint here that *widens* anything, which is why it is the one
    an administrator has to reach for deliberately. Everything else in this
    console narrows.
    """
    admin = require_admin(request)
    member = MEMBERS.get(owner)
    if member is None:
        raise HTTPException(status_code=404, detail="not a member")
    body = await request.json()
    role_id = (body.get("role") or "").strip() or None
    roles = current()["charter"].get("roles") or {}
    if role_id is not None and role_id not in roles:
        raise HTTPException(
            status_code=400,
            detail=f"{role_id!r} is not a role in this charter — "
                   f"{', '.join(sorted(roles)) or 'it defines none'}")
    member["role"] = role_id
    note("member.role_set", member=owner, by=admin, role=role_id)
    # Her authority re-reads the envelope and finds a different set of grants,
    # which is what makes the change take effect on her side rather than
    # only in this service's memory.
    await notify_member(owner, {"kind": "role_changed", "role": role_id,
                                "by": admin})
    return {"owner": owner, "role": role_id}


@app.get("/admin/roles")
async def admin_roles(request: Request) -> dict:
    """The groups this charter defines, and who is in each.

    The count comes from `MEMBERS` rather than from the charter because
    membership is *state*, not policy: the charter says what a group may
    reach, and this service remembers who is in it. Keeping those apart is
    what lets a group be renamed without anybody re-joining, and what stops
    the decision engine from being asked a question it has no business
    answering.
    """
    require_admin(request)
    roles = current()["charter"].get("roles") or {}
    held: dict[str, list[str]] = {role_id: [] for role_id in roles}
    unassigned = []
    for owner, member in MEMBERS.items():
        held.setdefault(member.get("role") or "", []).append(owner)
    unassigned = held.pop("", [])
    return {"roles": roles,
            "default_role": current()["charter"].get("default_role"),
            "members": held,
            "unassigned": unassigned}


@app.put("/admin/roles/{role_id}")
async def admin_put_role(role_id: str, request: Request) -> dict:
    """Create a group, or change what it may reach.

    This publishes a new charter version rather than editing the roles map in
    place, and it is worth being clear about why, because a group looks like
    the kind of administrative detail that ought to be cheap to change. It is
    not: a group is a set of grants over the organization's resources, every
    member was shown the group she was joining, and her authority holds an
    envelope derived from it. Widening a group is handing out access; the
    record of when it happened and who did it belongs in the same versioned
    document as the rest of the bargain.

    The validator does the load-bearing check — a group may only grant what
    the charter claims — so an administrator cannot invent a group that
    reaches somebody's personal accounts.
    """
    admin = require_admin(request)
    role_id = role_id.strip()
    if not role_id:
        raise HTTPException(status_code=400, detail="a group needs an id")
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="expected an object")
    doc = copy.deepcopy(current()["charter"])
    roles = doc.setdefault("roles", {})
    existed = role_id in roles
    roles[role_id] = {
        "name": (body.get("name") or "").strip() or role_id,
        "grants": body.get("grants") or [],
        "delegation": body.get("delegation") or "none",
    }
    if body.get("default"):
        doc["default_role"] = role_id
    try:
        entry = await publish_charter(doc, by=admin)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    note("role.saved", role=role_id, by=admin,
         version=entry["version"], created=not existed)
    await announce_charter(entry)
    return {"version": entry["version"], "role": role_id,
            "roles": entry["charter"].get("roles") or {},
            "default_role": entry["charter"].get("default_role")}


@app.delete("/admin/roles/{role_id}")
async def admin_delete_role(role_id: str, request: Request) -> dict:
    """Remove a group, once nobody is in it.

    Refusing while it is held is the whole of the design here. Deleting a
    group out from under its members would leave them enrolled with a role id
    that resolves to nothing — which fails *closed*, so their access would
    quietly stop working with no event anyone would think to look at. Making
    the administrator move them first means the access change is a thing he
    did on purpose, to named people.
    """
    admin = require_admin(request)
    doc = copy.deepcopy(current()["charter"])
    roles = doc.get("roles") or {}
    if role_id not in roles:
        raise HTTPException(status_code=404, detail="no such group")
    holders = sorted(o for o, m in MEMBERS.items() if m.get("role") == role_id)
    if holders:
        raise HTTPException(
            status_code=409,
            detail=f"{len(holders)} member(s) are in this group — "
                   f"{', '.join(holders)}. Move them to another group first, "
                   f"so the access they lose is something you did to them "
                   f"rather than something that stopped working.")
    del roles[role_id]
    if doc.get("default_role") == role_id:
        doc["default_role"] = None
    try:
        entry = await publish_charter(doc, by=admin)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    note("role.removed", role=role_id, by=admin, version=entry["version"])
    await announce_charter(entry)
    return {"version": entry["version"], "removed": role_id,
            "roles": entry["charter"].get("roles") or {},
            "default_role": entry["charter"].get("default_role")}


@app.post("/admin/roles/default")
async def admin_default_role(request: Request) -> dict:
    """Which group somebody lands in when they join.

    A charter with no default is a legitimate configuration and not an
    oversight: it means joining grants nothing until an administrator says
    what this person is, which is what an organization handling anything
    sensitive would actually want. So `null` is accepted.
    """
    admin = require_admin(request)
    body = await request.json()
    role_id = (body.get("role") or "").strip() or None
    doc = copy.deepcopy(current()["charter"])
    doc["default_role"] = role_id
    try:
        entry = await publish_charter(doc, by=admin)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    note("role.default_set", role=role_id, by=admin, version=entry["version"])
    await announce_charter(entry)
    return {"version": entry["version"],
            "default_role": entry["charter"].get("default_role")}


@app.delete("/admin/members/{owner}")
async def admin_remove_member(owner: str, request: Request) -> dict:
    admin = require_admin(request)
    if MEMBERS.pop(owner, None) is None:
        raise HTTPException(status_code=404, detail="not a member")
    note("member.removed", member=owner, by=admin)
    # Her authority stops clamping when it learns this, and what was clamped
    # stays clamped. Removal withdraws a ceiling; it never re-opens access.
    await notify_member(owner, {"kind": "membership_ended", "by": admin})
    return {"removed": owner}


# --- Co-administration -------------------------------------------------------
#
# The organization holds the accounts, so it can answer for what is connected
# to them: an administrator sees the same pending queue, the same agents and
# the same operators the member sees, and can act on them.
#
# Two rules make that co-administration rather than a takeover, and both are
# enforced on the member's side rather than here — which is the important
# part, because a limit an administrator's own console enforces is a limit an
# administrator can route around:
#
#   * restrictions are unrestricted; approvals only reach resources this
#     charter claims;
#   * everything he does is written into *her* record with his name on it.
#
# What crosses is a short-lived token this service signs, naming the member
# and the administrator. Her authority verifies it against the keys this
# organization publishes — the same keys it has held since she enrolled — so
# it is checkable by her side rather than asserted by ours.


def admin_action_token(owner: str, admin: str) -> str:
    return jwt.encode(
        {"iss": ISSUER, "sub": owner, "org": ORG_ID, "org_name": ORG_NAME,
         "admin": admin, "iat": int(now()), "exp": int(now()) + 120},
        SIGNING_KEY, algorithm="EdDSA",
        headers={"typ": "u4a-org-admin+jwt", "kid": KID})


ADMIN_MEMBER_PATHS = ("pending", "connections", "operators", "ledger")


# Declared *after* every specific `/admin/members/...` route above, because
# FastAPI matches in declaration order and this one would otherwise swallow
# them — `/admin/members/alice/role` would arrive here as an unknown
# administration action and 404, with nothing to say why. Moving this block
# up is the way to break role assignment silently.
@app.api_route("/admin/members/{owner}/{path:path}", methods=["GET", "POST"])
async def admin_member_proxy(owner: str, path: str, request: Request):
    """An administrator acting on one member's agent access.

    A passthrough rather than a handler per action, and deliberately: her
    authority is what decides whether an act is permitted, what it does, and
    what is written down. This service's job is to say who is asking and to
    prove the organization stands behind it. A proxy that re-implemented her
    API here would be a second opinion about her own state.
    """
    admin = require_admin(request)
    member = MEMBERS.get(owner)
    if member is None:
        raise HTTPException(status_code=404, detail="not a member")
    if not member.get("as_uri"):
        raise HTTPException(
            status_code=409,
            detail="this member's authorization server has not told us where "
                   "it is, so there is nowhere to send this")
    # The first segment names the action, and the rest must not be able to
    # climb out of it. Without this, `pending/../../../token` leaves
    # `/org/admin/...` entirely once a URL library normalises it — and a
    # console holding an administration token would be able to reach every
    # endpoint on a member's authorization server, not the four this proxy
    # is for. Her authority would refuse most of them; that is not a reason
    # to send them.
    segments = [x for x in path.split("/") if x not in ("", ".")]
    if not segments or segments[0] not in ADMIN_MEMBER_PATHS or ".." in segments:
        raise HTTPException(status_code=404, detail="unknown administration action")
    path = "/".join(segments)
    body = await request.body()
    url = f"{member['as_uri'].rstrip('/')}/org/admin/{owner}/{path}"
    try:
        async with httpx.AsyncClient(verify=CA_BUNDLE or True, timeout=15.0) as c:
            r = await c.request(
                request.method, url, content=body or None,
                headers={"Authorization": f"Bearer {admin_action_token(owner, admin)}",
                         **({"content-type": "application/json"} if body else {})})
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"her authorization server could not be reached: {exc}")
    if request.method == "POST":
        # The organization's own note. Her ledger is the record of what
        # happened to her agents; this is the record of what this
        # organization's people did, which is the question an administrator's
        # own auditor asks.
        note("member.administered", member=owner, by=admin, action=path,
             result=r.status_code)
    try:
        return JSONResponse(r.json(), status_code=r.status_code)
    except ValueError:
        return JSONResponse({"error": r.text}, status_code=r.status_code)


@app.get("/admin/invites")
async def admin_invites(request: Request) -> list:
    require_admin(request)
    return [{"owner": o, **{k: v for k, v in i.items() if k != "code"}}
            for o, i in sorted(INVITES.items())]


@app.post("/admin/invites")
async def admin_invite(request: Request) -> dict:
    """Ask someone to join.

    Creates something she can accept or decline and nothing else. Note what
    this endpoint does not do: it does not add a member, it does not touch
    her policy, and it does not tell this service where her authorization
    server is — it has no idea, and will not until she says yes. An
    organization that could enrol a person by naming her could clamp a
    stranger's terms.
    """
    admin = require_admin(request)
    body = await request.json()
    owner = (body.get("owner") or "").strip()
    if not owner:
        raise HTTPException(status_code=400,
                            detail="who is being invited? Use the identifier "
                                   "they sign in to their own portal with")
    if owner in MEMBERS:
        raise HTTPException(status_code=409,
                            detail=f"{owner} is already a member")
    existing = INVITES.get(owner)
    if existing and existing["state"] == "open":
        raise HTTPException(status_code=409,
                            detail=f"{owner} already has an open invitation")
    INVITES[owner] = {
        "code": f"inv_{secrets.token_urlsafe(12)}",
        "by": admin,
        "note": (body.get("note") or "").strip(),
        "created": utcstamp(),
        "state": "open",
    }
    note("invitation.sent", member=owner, by=admin)
    return {"invited": owner, "state": "open"}


@app.delete("/admin/invites/{owner}")
async def admin_withdraw_invite(owner: str, request: Request) -> dict:
    admin = require_admin(request)
    if INVITES.pop(owner, None) is None:
        raise HTTPException(status_code=404, detail="no such invitation")
    note("invitation.withdrawn", member=owner, by=admin)
    return {"withdrawn": owner}


@app.get("/admin/activity")
async def admin_activity(request: Request) -> list:
    require_admin(request)
    return list(reversed(ACTIVITY))


@app.get("/admin/break-glass")
async def admin_glass_log(request: Request) -> dict:
    require_admin(request)
    glass = current()["charter"].get("break_glass") or {}
    return {
        "clause": glass,
        "open_vouchers": [
            {"code": code, **{k: v for k, v in v0.items() if k != "code"},
             "expires_in": max(0, int(v0["expires"] - now()))}
            for code, v0 in VOUCHERS.items() if v0["expires"] > now()],
        "grants": [
            {"jti": jti, "member": g["member"], "resource_id": g["resource_id"],
             "reason": g["reason"], "authorised_by": g["authorised_by"],
             "issued": g["issued"], "spent": g["spent"]}
            for jti, g in reversed(list(GLASS.items()))],
    }


@app.post("/admin/break-glass")
async def admin_open_voucher(request: Request) -> dict:
    """A person at the organization opening a window.

    Deliberately two steps rather than one. The organization decides that an
    override is warranted; an agent then redeems it, signing with the key the
    grant will bind to. Splitting them means the member is told at the moment
    a human decided — before any data moves — rather than at the moment
    something took it.
    """
    admin = require_admin(request)
    body = await request.json()
    owner = (body.get("owner") or "").strip()
    reason = (body.get("reason") or "").strip()
    glass = current()["charter"].get("break_glass") or {}
    if not glass.get("enabled"):
        raise HTTPException(status_code=403,
                            detail="the charter does not permit break-glass")
    if owner not in MEMBERS:
        raise HTTPException(status_code=404, detail="not a member")
    if glass.get("require_reason") and not reason:
        raise HTTPException(status_code=400,
                            detail="the charter requires a stated reason")
    ttl = min(int(body.get("window_s") or 300), 3600)
    code = f"bgv_{secrets.token_urlsafe(9)}"
    VOUCHERS[code] = {"owner": owner, "admin": admin, "reason": reason,
                      "opened": utcstamp(), "expires": now() + ttl}
    note("break_glass.opened", member=owner, by=admin, window_s=ttl)
    await notify_member(owner, {"kind": "break_glass_opened", "by": admin,
                                "reason": reason, "window_s": ttl,
                                "resources": glass.get("resources") or []})
    return {"voucher": code, "expires_in": ttl, "owner": owner,
            "resources": glass.get("resources") or [],
            "max_expires_in": glass.get("max_expires_in")}


@app.post("/admin/join-code/rotate")
async def admin_rotate_code(request: Request) -> dict:
    global JOIN_CODE
    admin = require_admin(request)
    JOIN_CODE = "NW-" + secrets.token_hex(2).upper() + "-" + secrets.token_hex(1).upper()
    note("join_code.rotated", by=admin)
    # Existing members are unaffected: the code admits, it does not sustain.
    return {"join_code": JOIN_CODE}
