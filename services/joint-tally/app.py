"""The tally: it counts verdicts and holds no policy.

When a resource has one owner, her authorization server decides. When it has
several of equal standing, something has to put one question to all of them
and combine the answers — and whatever does that is, structurally, in a
privileged position. The reflex is to make the privileged thing trustworthy:
replicate it, distribute it, put it on a ledger. This service takes the other
route, which is to make it *unable to lie*, and then stop caring who runs it.

Three properties do that, and none of them is consensus in the
distributed-systems sense — there is no ordered history here to agree on and
no long-lived state to protect:

**It cannot manufacture a yes.** Every holder's answer is a JWS signed by her
own authorization server. This service collects them and does arithmetic. It
holds no key any relying party accepts as a verdict, so the worst it can do
is withhold or misreport — and misreporting is caught, because the grant it
issues carries the verdicts inside it and the enforcement point re-checks
them against each holder's published keys and re-runs the count.

**It cannot weaken anybody's terms.** It folds every holder's terms into the
one document an agent signs, because an agent cannot usefully sign four
documents and an intersection computed by the requesting side is one computed
by the party that benefits from getting it wrong. But each holder's authority
independently compares what was signed against what she published, and
refuses on any difference in the direction of more.

**It decides nothing about identity.** It verifies that the agreement was
signed by the key it names, because that key gets bound into the grant. Who
the agent is, who operates it and whether anyone is accountable for it are
questions for the holders' authorities, which is where the evidence and the
policy both live.

What it speaks is an ordinary UMA authorization-server surface — ticket,
`need_info`, grant — so an enforcement point in front of a jointly held
resource is the same enforcement point pointed somewhere else, and an agent
never learns that the party it negotiated with was not an owner.

State is in memory and this runs as one replica. That is a lab limitation
rather than a property of the design: the authorization servers here persist
their negotiations and a real deployment of this would too.
"""

import base64
import json
import os
import secrets
import sys
import time
import uuid
from hashlib import sha256

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from jwt.algorithms import OKPAlgorithm

import uma4a_joint as J

ISSUER = os.environ.get("TALLY_ISSUER", "https://joint-tally.uma.lab")
AUDIENCE = os.environ.get("TALLY_AUDIENCE", "https://gateway.uma.lab")
RS_SECRET = os.environ.get("TALLY_RS_SECRET", "tally-rs-dev-secret")
CA_BUNDLE = os.environ.get("UMA4A_CA_BUNDLE")
POLL_INTERVAL = int(os.environ.get("TALLY_POLL_INTERVAL", "2"))
TICKET_TTL_S = float(os.environ.get("TALLY_TICKET_TTL_S", "300"))
# How long a question this service signs to a holder stays answerable.
REQUEST_TTL_S = int(os.environ.get("TALLY_REQUEST_TTL_S", "120"))
# A minimum the holders may not vote themselves below. Configuration here
# stands in for whatever supplies it in the world — an account agreement, or
# a regulator — and its presence is the point: a quorum a group sets for
# itself cannot answer what quorum sets the quorum.
FLOOR = int(os.environ.get("TALLY_THRESHOLD_FLOOR", "0"))

# The same two constants every other authority in this lab uses. A tally
# that invented its own would be a party an unmodified agent could not
# negotiate with, which is the one thing this is not allowed to be.
AGREEMENT_FORMAT = "urn:uma4agents:format:myterms-agreement-v1+jws"
AGREEMENT_CLAIM = "urn:uma4agents:claim:myterms-agreement"

KEY_PATH = os.environ.get("TALLY_SIGNING_KEY", "/keys/tally-ed25519.pem")
KID = os.environ.get("TALLY_KID", "tally-1")


def load_or_create_key() -> Ed25519PrivateKey:
    """Persisted, not generated per process.

    Two parties verify what this service signs against the keys it publishes,
    and both of them cache. A tally that minted a new key on every restart
    would have every holder's authority reject its requests until their
    caches expired — which reads as a broken mandate rather than as a
    restart, and is the sort of thing that is only ever debugged once.
    """
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
PUBLIC_KEY = SIGNING_KEY.public_key()

MANDATES: dict[str, dict] = {}
NEGOTIATIONS: dict[str, dict] = {}
TICKETS: dict[str, tuple[str, float]] = {}
RPTS: dict[str, dict] = {}
TERMS: dict[str, dict] = {}

app = FastAPI(title="joint-tally")


def now() -> float:
    return time.time()


def event(kind: str, **fields) -> None:
    print(json.dumps({"svc": "joint-tally", "kind": kind, **fields}), flush=True)


def s256(data: bytes) -> str:
    # The same prefixed form every other party here uses. A digest that
    # agreed on the bytes and disagreed on the spelling would make each
    # holder's authority refuse an agreement that was, in fact, the one it
    # was sent.
    return "s256:" + base64.urlsafe_b64encode(sha256(data).digest()).rstrip(b"=").decode()


def jwks() -> dict:
    raw = PUBLIC_KEY.public_bytes(serialization.Encoding.Raw,
                                  serialization.PublicFormat.Raw)
    return {"keys": [{"kty": "OKP", "crv": "Ed25519", "kid": KID,
                      "x": base64.urlsafe_b64encode(raw).rstrip(b"=").decode(),
                      "use": "sig", "alg": "EdDSA"}]}


def load_mandates() -> None:
    """The mandates this tally counts for.

    Read from configuration because a mandate is not this service's to write.
    It names who is entitled to be counted and at what weight, the holders
    agreed to it, and a coordinator that could edit it would be deciding who
    gets a say — the one thing this design is arranged to stop it doing.
    """
    raw = os.environ.get("TALLY_MANDATES") or ""
    path = os.environ.get("TALLY_MANDATES_FILE") or ""
    if path and os.path.exists(path):
        raw = open(path).read()
    if not raw.strip():
        return
    for account, doc in json.loads(raw).items():
        try:
            MANDATES[account] = J.validate_mandate({**doc}, floor=FLOOR)
        except J.MandateError as exc:
            print(f"mandate {account!r} refused: {exc}", file=sys.stderr, flush=True)
            raise SystemExit(2)
    event("mandates.loaded", accounts=sorted(MANDATES), floor=FLOOR)


@app.on_event("startup")
async def startup() -> None:
    load_mandates()


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "accounts": sorted(MANDATES)}


@app.get("/jwks")
async def jwks_endpoint() -> dict:
    return jwks()


@app.get("/.well-known/uma4agents-configuration")
async def configuration() -> dict:
    return {
        "issuer": ISSUER,
        "jwks_uri": f"{ISSUER}/jwks",
        "token_endpoint": f"{ISSUER}/token",
        "permission_endpoint": f"{ISSUER}/perm",
        "introspection_endpoint": f"{ISSUER}/introspect",
        # What makes this not an ordinary authorization server, said out
        # loud. A relying party finding this field is being told the thing it
        # most needs to know: the party at this endpoint decides nothing, and
        # the grants it signs are worth exactly what the verdicts inside them
        # are worth.
        "u4a_tally": True,
        "u4a_mandate_endpoint": f"{ISSUER}/mandate/{{account}}",
    }


@app.get("/mandate/{account}")
async def mandate(account: str) -> dict:
    """Who is entitled to be counted here, and how many it takes.

    Public. A holder reads it before she agrees, an agent may read it to see
    why it is being asked to wait on several people, and anybody verifying a
    grant this service issued needs it to re-run the count.
    """
    doc = MANDATES.get(account)
    if doc is None:
        raise HTTPException(status_code=404, detail="no such mandate")
    return {**doc, "account": account, "tally": ISSUER, "summary": J.describe(doc)}


# --- The holders' authorities ------------------------------------------------


def signed_request(claims: dict) -> str:
    """One question to one holder's authority, signed and short-lived.

    The expiry is the point of the second claim. Without it a captured
    request is good forever: replayed weeks later it would put a decided
    question back in front of an owner, under a policy she has since edited.
    Nothing here is a privilege to steal, and a question that can be re-asked
    indefinitely is still a way to bother somebody.
    """
    return jwt.encode({**claims, "iss": ISSUER, "iat": int(now()),
                       "exp": int(now()) + REQUEST_TTL_S},
                      SIGNING_KEY, algorithm="EdDSA",
                      headers={"typ": "u4a-tally-req+jwt", "kid": KID})


async def ask_holder(holder: dict, path: str, claims: dict) -> dict:
    async with httpx.AsyncClient(verify=CA_BUNDLE or True, timeout=10.0) as c:
        r = await c.post(f"{holder['issuer']}{path}",
                         json={"request": signed_request(claims)})
        r.raise_for_status()
        return r.json()


async def quotes_for(account: str, doc: dict,
                     resource_id: str) -> list[tuple[str, dict]]:
    """Every holder's terms over this resource.

    A holder who quotes nothing has written no terms over it and is left out
    of the fold rather than defaulted into something. Under unanimity that
    stops the request, which is the right answer: silence is not consent, and
    an owner who has not said what she permits has not permitted anything.
    """
    out = []
    for h in doc.get("holders") or []:
        try:
            answer = await ask_holder(h, "/joint/quote", {
                "owner": h["owner"], "account": account,
                "resource_id": resource_id})
        except httpx.HTTPError as exc:
            event("quote.unreachable", account=account, holder=h["owner"],
                  error=str(exc)[:160])
            continue
        if answer.get("tier"):
            out.append((h["owner"], answer["tier"]))
        else:
            event("quote.none", account=account, holder=h["owner"],
                  because=answer.get("because"))
    return out


_HOLDER_JWKS: dict[str, tuple[float, list]] = {}


def holder_keys(issuer: str) -> list:
    cached = _HOLDER_JWKS.get(issuer)
    if cached and cached[0] > now():
        return cached[1]
    with httpx.Client(verify=CA_BUNDLE or True, timeout=5.0) as c:
        r = c.get(f"{issuer.rstrip('/')}/jwks")
        r.raise_for_status()
    keys = r.json()["keys"]
    _HOLDER_JWKS[issuer] = (now() + 300, keys)
    return keys


def verify_verdict(jws: str, holder: dict, rec: dict) -> dict | None:
    """A holder's answer, checked before it is counted.

    This service verifies what it collects even though the enforcement point
    verifies it again — not belt and braces. Without this check a tally would
    count a forgery, issue a grant, and have it rejected downstream: the agent
    would be told yes and then refused, and the holder who actually refused
    would appear nowhere. Catching it here makes the failure legible where it
    happens.
    """
    for jwk_dict in holder_keys(holder["issuer"]):
        try:
            claims = jwt.decode(jws, OKPAlgorithm.from_jwk(json.dumps(jwk_dict)),
                                algorithms=["EdDSA"], issuer=holder["issuer"],
                                options={"verify_aud": False})
        except jwt.InvalidTokenError:
            continue
        # Bound to this negotiation and this exact agreement. Without both, a
        # verdict is a reusable yes: the same signed answer would carry a
        # later request, over different terms, that she never saw.
        if claims.get("holder") != holder["owner"] \
                or claims.get("negotiation") != rec["family"] \
                or claims.get("contract") != rec["contract_hash"] \
                or claims.get("effect") not in ("allow", "refuse"):
            return None
        return claims
    event("verdict.unverified", corr=rec["family"], holder=holder["owner"])
    return None


async def collect(rec: dict, doc: dict) -> dict:
    """Ask every holder who has not answered, and report where it stands."""
    for h in doc.get("holders") or []:
        owner = h["owner"]
        if owner in rec["verdicts"]:
            continue
        try:
            answer = await ask_holder(h, "/joint/verdict", {
                "owner": owner, "account": rec["account"],
                "negotiation": rec["family"], "resource_id": rec["resource_id"],
                "contract": rec["contract_hash"], "agreement": rec["agreement"]})
        except httpx.HTTPError as exc:
            # Unreachable is not a no. It is also not a yes, and under any
            # rule that needs this holder the request does not proceed — the
            # fail-closed direction, and the only safe one when the missing
            # party may have been about to refuse.
            event("verdict.unreachable", corr=rec["family"], holder=owner,
                  error=str(exc)[:160])
            continue
        if answer.get("pending"):
            event("verdict.pending", corr=rec["family"], holder=owner)
            continue
        jws = answer.get("verdict")
        if not jws:
            continue
        claims = verify_verdict(jws, h, rec)
        if claims is None:
            continue
        rec["verdicts"][owner] = claims["effect"]
        rec.setdefault("signed", {})[owner] = jws
        if claims.get("because"):
            rec["because"][owner] = claims["because"]
        event("verdict.recorded", corr=rec["family"], holder=owner,
              effect=claims["effect"])
    return J.tally(doc, rec["verdicts"])


# --- The grant loop ----------------------------------------------------------


def mint_ticket(family: str) -> str:
    ticket = secrets.token_urlsafe(24)
    TICKETS[ticket] = (family, now() + TICKET_TTL_S)
    return ticket


def take_ticket(ticket: str) -> dict | None:
    entry = TICKETS.pop(ticket or "", None)
    if entry is None or entry[1] < now():
        return None
    return NEGOTIATIONS.get(entry[0])


def account_for(resource_id: str) -> tuple[str | None, dict]:
    for account, doc in MANDATES.items():
        if J.governs(doc, resource_id):
            return account, doc
    return None, {}


def rs_auth(request: Request) -> None:
    auth = request.headers.get("authorization") or ""
    if not auth.startswith("Bearer ") or not secrets.compare_digest(
            auth[7:], RS_SECRET):
        raise HTTPException(status_code=401, detail="invalid_client")


@app.post("/perm")
async def perm(request: Request) -> dict:
    """Beat 1. The enforcement point registers the attempted permission."""
    rs_auth(request)
    body = await request.json()
    resource_id = body.get("resource_id") or ""
    account, _ = account_for(resource_id)
    if account is None:
        raise HTTPException(status_code=400, detail="no mandate covers that resource")
    family = f"jnt_{uuid.uuid4().hex[:12]}"
    NEGOTIATIONS[family] = {
        "family": family, "account": account, "state": "new",
        "resource_id": resource_id,
        "resource_scopes": body.get("resource_scopes") or [],
        "verdicts": {}, "because": {}, "signed": {},
    }
    event("ticket.minted", corr=family, account=account, resource_id=resource_id)
    return {"ticket": mint_ticket(family)}


def fold_terms(rec: dict, quotes: list[tuple[str, dict]], doc: dict) -> dict:
    """The one document the agent is asked to sign."""
    folded, changes = J.fold(quotes, doc.get("resources") or [])
    terms = folded.get("terms") or {}
    template_id = f"{rec['account']}/joint/v{len(TERMS) + 1}"
    asked_for = rec.get("resource_scopes") or terms.get("scope") or []
    template = {
        "template_id": template_id,
        "terms_uri": f"{ISSUER}/terms/{template_id}",
        "proffered_by": ISSUER,
        "purpose": f"Access to {rec['account']}, held jointly",
        "scope": [s for s in terms.get("scope") or [] if s in asked_for],
        "expires_in": terms.get("expires_in"),
        "prohibited": sorted(terms.get("prohibited") or []),
        "nonce": rec["nonce"],
        "family": rec["family"],
        "audience": ISSUER,
        # Who is behind these terms and what it takes to get past them. The
        # agent is told before it signs that the party proffering this is not
        # an owner and that several people have to agree — the same job the
        # `organization` block does one layer up.
        "joint": {
            "account": rec["account"],
            "tally": ISSUER,
            "holders": [h["owner"] for h in doc.get("holders") or []],
            "quoted": [owner for owner, _ in quotes],
            "rule": (doc.get("rule") or {}).get("kind"),
            "threshold": (doc.get("rule") or {}).get("threshold"),
            "requires": J.describe(doc),
        },
        "enforced": {"ask_me": bool(folded.get("ask_me"))},
    }
    TERMS[template_id] = {**template, "changes": changes}
    return template


@app.get("/terms/{template_id:path}")
async def terms(template_id: str) -> dict:
    doc = TERMS.get(template_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="no such terms document")
    return doc


def bind_key(agreement_b64: str) -> tuple[dict, dict]:
    """Verify the agreement over the key it names, and return that key.

    Deliberately less than an authorization server does. This checks the
    document was signed by the key in its header, because that key is what
    gets bound into the grant, and it stops there. Whether the agent is
    identified, who operates it and whether that operator published this key
    are judgements each holder's own authority makes with its own evidence
    and its own policy. A coordinator that graded identity would be a
    coordinator holding policy.
    """
    raw = base64.urlsafe_b64decode(agreement_b64 + "=" * (-len(agreement_b64) % 4))
    token = raw.decode()
    header = jwt.get_unverified_header(token)
    if "jwk" in header:
        signer = header["jwk"]
    elif "agent_token" in header:
        signer = jwt.decode(header["agent_token"],
                            options={"verify_signature": False})["cnf"]["jwk"]
    else:
        raise ValueError("agreement must carry jwk or agent_token in its header")
    claims = jwt.decode(token, OKPAlgorithm.from_jwk(json.dumps(signer)),
                        algorithms=["EdDSA"], audience=ISSUER)
    return claims, signer


@app.post("/token")
async def token(request: Request) -> JSONResponse:
    form = await request.form()
    grant_type = form.get("grant_type") or ""
    if grant_type == "client_credentials":
        if not secrets.compare_digest(form.get("client_secret") or "", RS_SECRET):
            return JSONResponse({"error": "invalid_client"}, status_code=401)
        return JSONResponse({"access_token": RS_SECRET, "token_type": "Bearer",
                             "expires_in": 3600, "scope": "uma_protection"})
    if grant_type != "urn:ietf:params:oauth:grant-type:uma-ticket":
        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)

    rec = take_ticket(form.get("ticket") or "")
    if rec is None:
        return JSONResponse({"error": "invalid_grant"}, status_code=400)
    doc = MANDATES.get(rec["account"]) or {}

    if form.get("decline") == "true":
        event("terms.declined", corr=rec["family"], account=rec["account"])
        NEGOTIATIONS.pop(rec["family"], None)
        return JSONResponse({"error": "request_denied"}, status_code=403)

    if rec["state"] == "awaiting-holders":       # beat 3, taking longer
        return await poll(rec, doc)

    claim_token = form.get("claim_token")
    if not claim_token:
        # Beat 2: fold every holder's terms and dictate the result.
        quotes = await quotes_for(rec["account"], doc, rec["resource_id"])
        if not quotes:
            event("policy.evaluated", corr=rec["family"], result="no-terms")
            NEGOTIATIONS.pop(rec["family"], None)
            return JSONResponse(
                {"error": "request_denied",
                 "error_description": "no holder of this account has written "
                                      "terms over that resource"},
                status_code=403)
        rec["nonce"] = secrets.token_urlsafe(12)
        rec["state"] = "need_info"
        rec["template"] = fold_terms(rec, quotes, doc)
        event("need_info.terms_dictated", corr=rec["family"],
              template_id=rec["template"]["template_id"],
              quoted=[o for o, _ in quotes])
        return JSONResponse(
            {"error": "need_info", "ticket": mint_ticket(rec["family"]),
             "required_claims": [{
                 "claim_type": AGREEMENT_CLAIM,
                 "claim_token_format": [AGREEMENT_FORMAT],
                 "friendly_name": f"Terms for {rec['account']}, held jointly",
                 "terms_template": rec["template"]}]},
            status_code=403)

    if form.get("claim_token_format") != AGREEMENT_FORMAT:
        return JSONResponse({"error": "invalid_claim_token_format"}, status_code=400)
    if rec["state"] != "need_info":
        return JSONResponse({"error": "invalid_grant"}, status_code=400)

    try:
        contract, signer = bind_key(claim_token)
    except Exception as exc:                                    # noqa: BLE001
        event("contract.rejected", corr=rec["family"], reason=str(exc)[:200])
        NEGOTIATIONS.pop(rec["family"], None)
        return JSONResponse({"error": "request_denied",
                             "error_description": str(exc)}, status_code=403)
    template = rec["template"]
    if contract.get("nonce") != template["nonce"] \
            or contract.get("family") != rec["family"] \
            or contract.get("template_id") != template["template_id"]:
        return JSONResponse(
            {"error": "request_denied",
             "error_description": "that agreement is not the one proffered"},
            status_code=403)
    raw = base64.urlsafe_b64decode(claim_token + "=" * (-len(claim_token) % 4))
    rec["agreement"] = claim_token
    rec["contract_hash"] = s256(raw)
    rec["contract"] = contract
    rec["signer"] = signer
    rec["state"] = "awaiting-holders"
    event("contract.committed", corr=rec["family"], contract=rec["contract_hash"])
    return await poll(rec, doc)


async def poll(rec: dict, doc: dict) -> JSONResponse:
    result = await collect(rec, doc)
    if result["effect"] == "allow":
        return JSONResponse(issue(rec, doc, result))
    if result["effect"] == "refuse":
        because = [line for lines in rec["because"].values() for line in lines]
        event("policy.evaluated", corr=rec["family"], result="refused", tally=result)
        NEGOTIATIONS.pop(rec["family"], None)
        return JSONResponse(
            {"error": "request_denied",
             "error_description": "; ".join(because)
                                  or "the holders of this account did not agree"},
            status_code=403)
    event("ticket.awaiting_holders", corr=rec["family"],
          outstanding=result["outstanding"])
    return JSONResponse({"error": "request_submitted",
                         "ticket": mint_ticket(rec["family"]),
                         "interval": POLL_INTERVAL}, status_code=403)


def issue(rec: dict, doc: dict, result: dict) -> dict:
    """The grant, carrying the evidence it rests on.

    The verdicts travel inside the token. That is what makes this service
    something other than a party everyone has to trust: an enforcement point
    verifies each one against the holder's own published keys and re-runs the
    count itself, so a grant signed here without the answers to back it is
    refused at the door. It costs a larger token and buys the only property
    that matters.
    """
    jti = f"rpt_{uuid.uuid4().hex[:12]}"
    exp = int(now()) + min(3600, int(rec["template"]["expires_in"] or 900))
    claims = {
        "iss": ISSUER,
        "sub": rec["contract"].get("sub") or "aauth:pseudonymous-agent",
        "owner": rec["account"],
        "aud": AUDIENCE,
        "jti": jti,
        "exp": exp,
        "cnf": {"jwk": rec["signer"]},
        "permissions": [{"resource_id": rec["resource_id"],
                         "resource_scopes": rec["template"]["scope"],
                         "exp": exp}],
        "contract": rec["contract_hash"],
        "joint": {
            "account": rec["account"],
            "mandate": {"holders": doc.get("holders"), "rule": doc.get("rule"),
                        "resources": doc.get("resources")},
            "verdicts": [rec["signed"][o] for o in sorted(rec.get("signed") or {})
                         if rec["verdicts"].get(o) == "allow"],
            "tally": result,
        },
    }
    if rec["contract"].get("operation"):
        claims["single_use"] = True
        claims["operation"] = {
            "tool": rec["contract"]["operation"]["tool"],
            "params_s256": s256(json.dumps(
                rec["contract"]["operation"].get("params", {}),
                sort_keys=True).encode())}
    token = jwt.encode(claims, SIGNING_KEY, algorithm="EdDSA",
                       headers={"typ": "aa-auth+jwt", "kid": KID})
    RPTS[jti] = {"claims": claims, "spent": False, "family": rec["family"]}
    event("rpt.issued", corr=rec["family"], jti=jti, account=rec["account"],
          holders=sorted(rec.get("signed") or {}))
    NEGOTIATIONS.pop(rec["family"], None)
    return {"access_token": token, "token_type": "PoP",
            "expires_in": exp - int(now())}


# --- What the enforcement point asks -----------------------------------------


def read_own(token: str) -> dict | None:
    try:
        return jwt.decode(token, OKPAlgorithm.from_jwk(json.dumps(jwks()["keys"][0])),
                          algorithms=["EdDSA"], options={"verify_aud": False})
    except jwt.InvalidTokenError:
        return None


@app.post("/introspect")
async def introspect(request: Request, token: str = Form(...),
                     consume: str = Form("false")) -> dict:
    rs_auth(request)
    claims = read_own(token)
    if claims is None:
        return {"active": False}
    entry = RPTS.get(claims.get("jti") or "")
    if entry is None or entry["spent"] or claims.get("exp", 0) < now():
        return {"active": False}
    if consume == "true" and claims.get("single_use"):
        entry["spent"] = True
    return {"active": True, **claims}


@app.post("/consume")
async def consume(request: Request, token: str = Form(...)) -> dict:
    rs_auth(request)
    claims = read_own(token)
    if claims is None:
        return {"consumed": False}
    entry = RPTS.get(claims.get("jti") or "")
    if entry is None or entry["spent"]:
        return {"consumed": False}
    entry["spent"] = True
    event("rpt.consumed", jti=claims.get("jti"))
    return {"consumed": True}


@app.post("/audit/access")
async def audit_access(request: Request) -> dict:
    rs_auth(request)
    body = await request.json()
    event("access.reported", corr=body.get("family"), tool=body.get("tool"))
    return {"recorded": True}


@app.post("/rs/register")
async def rs_register(request: Request) -> dict:
    """Declarative registration, accepted and ignored.

    The resources this tally answers about are the ones its mandates name,
    and a mandate is not something a resource server may add to. Kept so an
    enforcement point can introduce itself with the same code it uses against
    an owner's authority rather than needing a branch.
    """
    rs_auth(request)
    return {"status": "active"}
