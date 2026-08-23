"""uma-as — the UMA-for-agents authorization service (reference implementation).

Implements the four-beat grant loop from docs/PROTOCOL.md:

  challenge (ticket via /perm) -> attempt (/token: need_info + dictated terms)
  -> commit (signed intent contract) -> grant (PoP-bound RPT)

with UMA 2.0's request_submitted pending state for Alice's ask-me tier, an
owner API for the portal (pending approvals, tier policy, ledger), and one
structured log line per protocol event (ticket family = correlation id).

State is in-memory by design: `make reset` rewinds the story.
"""

import asyncio
import base64
import hashlib
import calendar
import html
import json
import logging
import os
import secrets
import sys
import time
import uuid

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from jwt.algorithms import OKPAlgorithm

import assurance
import policy
import store

ISSUER = os.environ.get("UMA_AS_ISSUER", "https://alice-as.uma.lab")
# The host a signature over a request to this server has to cover. Taken
# from the issuer so the two cannot drift apart.
AS_AUTHORITY = ISSUER.split("://", 1)[-1].rstrip("/")
KEY_PATH = os.environ.get("UMA_AS_SIGNING_KEY", "/keys/uma-as-ed25519.pem")
# The owner authenticates with her OIDC token (Keycloak); the AS validates
# it against the realm's published keys. No static owner credential exists.
OWNER_ISSUER = os.environ.get(
    "UMA_AS_OWNER_ISSUER", "https://keycloak.uma.lab/realms/alice")
# Where to read her identity provider's metadata, as distinct from the issuer
# her tokens must claim. Normally the same origin answers both. They come
# apart when her browser reaches it somewhere this process cannot follow — a
# tunnelled deployment gives the browser a public address while this pod has
# only the cluster network — and the issuer in the token is then the address
# the *browser* used, not the one the keys were fetched from.
OWNER_METADATA_URL = os.environ.get(
    "UMA_AS_OWNER_METADATA_URL",
    f"{OWNER_ISSUER}/.well-known/openid-configuration")
# Whose authority this is.
#
# An authorization server belongs to one owner. `UMA_AS_OWNER` names her, and
# every other owner is refused at the door rather than filtered out later —
# on her laptop, in a container, at the edge, the answer to "may I read
# somebody else's policy" is no before the question reaches the store.
#
# Unset, the server falls back to a default owner. That is a convenience for
# tests and for a single-owner lab, not a deployment shape: the many-owner
# case is one *resource server* holding many people's accounts, each governed
# by an authority of her own, which is what k8s/base and docker-compose run.
#
# The store is partitioned by owner regardless, and that is what makes an
# owner's state a clean cut — the reason her authority can move somewhere she
# controls without the grant loop noticing.
SERVED_OWNER = os.environ.get("UMA_AS_OWNER") or None
# Retained for the paths that need *an* owner before a request has named one:
# startup seeding, the resource pull, and the compose stack's fixtures.
DEFAULT_OWNER = SERVED_OWNER or os.environ.get("UMA_AS_DEFAULT_OWNER", "alice")
# Which owner the configured device key belongs to. See
# require_owner_signature: the signature proves a holder, this says whose.
OWNER_KEY_OWNER = os.environ.get("UMA_AS_OWNER_KEY_OWNER", DEFAULT_OWNER)


def st(owner: str):
    """This owner's state. The only way to reach the store."""
    return STORE.owner(owner)


def serves(owner: str) -> bool:
    return SERVED_OWNER is None or owner == SERVED_OWNER


# Tickets are minted by this server, so they can carry the owner they belong
# to. A multi-tenant deployment needs that: a ticket arrives with no session
# and no token, and there is nothing else on the request that says whose
# negotiation it indexes. A single-owner deployment does not need it and pays
# nothing for it.
def _enc_owner(owner: str) -> str:
    return base64.urlsafe_b64encode(owner.encode()).decode().rstrip("=")


def split_ticket(ticket: str | None) -> tuple[str | None, str]:
    """(owner, the store's ticket). Owner is None if the ticket is unmarked,
    which is what a ticket minted before this looked like."""
    head, sep, rest = (ticket or "").partition("~")
    if not sep:
        return None, ticket or ""
    try:
        return base64.urlsafe_b64decode(head + "=" * (-len(head) % 4)).decode(), rest
    except Exception:                                          # noqa: BLE001
        return None, ticket or ""
OWNER_AUDIENCES = set(
    os.environ.get("UMA_AS_OWNER_CLIENTS", "meridian-portal").split(","))

# How the owner proves she is the owner, to her own authorization server.
#
#   oidc       she signs in to an identity provider and the AS validates the
#              token against its published keys. Right for a deployment that
#              already has one, and the default.
#   local-key  she holds an Ed25519 key and signs her owner-API requests with
#              it (RFC 9421 — the same profile agents use for proof-of-
#              possession, pointed at the owner). No identity provider, no
#              static credential, nothing to stand up.
#
# Both, comma-separated, is the interesting configuration and the one the
# reference stack runs: `oidc,local-key`. A person has more than one way to
# reach her own things — a browser on her laptop, an app on her phone, a
# personal AI holding a key — and the profile should not force her to pick
# one. Each credential is independently sufficient and independently
# revocable; the second is not a fallback for the first.
#
# The key mode exists because OIDC is the one piece of this profile that
# cannot go anywhere small. An authority meant to be personal should not
# require her to operate an identity provider before she can answer a single
# request. The verifying code is the same either way; only the credential is
# different.
OWNER_AUTH = tuple(
    m.strip().lower()
    for m in os.environ.get("UMA_AS_OWNER_AUTH", "oidc").split(",")
    if m.strip()
)
# Her public key, in local-key mode: a path to an Ed25519 public key PEM.
OWNER_KEY_PATH = os.environ.get("UMA_AS_OWNER_KEY", "/keys/owner-ed25519.pub")
# The authority this AS reconstructs an owner signature base against. Taken
# from configuration, never from the request — an authority the caller can set
# is not an authority. Defaults to the host part of this AS's own issuer.
OWNER_EXPECTED_AUTHORITY = os.environ.get(
    "UMA_AS_OWNER_AUTHORITY", ISSUER.split("://", 1)[-1].split("/", 1)[0])
PAT_TTL = 3600
# Registration is declarative: this AS *reads* the RS's published metadata —
# public structure from the RFC 9728 document, owner-bound instances from the
# protected owner-resources endpoint — and materializes its registry from it.
# Classic FedAuthz push registration (/rreg) is gone from this line; the
# measured comparison lives on the `legacy/rreg-baseline` branch, and rec 5 in
# FINDINGS.md is what it produced. One registry, one writer.
# The owner-proffered terms + signed agreement follow the MyTerms pattern
# (IEEE 7012): the individual proffers machine-readable terms from her own
# roster; the counterparty agrees; both sides keep a record. The URN is ours —
# a MyTerms-shaped profile for agentic access terms, not a claim of
# conformance to the IEEE document's schema.
AGREEMENT_FORMAT = "urn:uma4agents:format:myterms-agreement-v1+jws"
AGREEMENT_CLAIM = "urn:uma4agents:claim:myterms-agreement"
TICKET_TTL = 300
# How long a held "ask-me" ticket stays valid. The demo's own premise is that
# Alice may be asleep, so ten minutes was never right — and it is only safe to
# lengthen because the requesting side no longer holds a call open across it
# (the shim hands the wait up as an MCP input_required and resumes).
PENDING_TTL = int(os.environ.get("UMA_AS_PENDING_TTL", 3600))
POLL_INTERVAL = 3

log = logging.getLogger("uma-as")
logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")


def now() -> float:
    return time.time()


def s256(data: bytes) -> str:
    return "s256:" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()


def event(name: str, corr: str | None = None, **details) -> None:
    log.info(
        json.dumps(
            {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "event": name,
                "corr": corr,
                "actor": "uma-as",
                "details": details,
            }
        )
    )


def load_or_create_key() -> Ed25519PrivateKey:
    if os.path.exists(KEY_PATH):
        with open(KEY_PATH, "rb") as f:
            return serialization.load_pem_private_key(f.read(), password=None)
    key = Ed25519PrivateKey.generate()
    os.makedirs(os.path.dirname(KEY_PATH), exist_ok=True)
    with open(KEY_PATH, "wb") as f:
        f.write(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
    return key


SIGNING_KEY = load_or_create_key()
KID = "uma-as-1"

app = FastAPI(title="uma-as")

# ---------------------------------------------------------------------------
# State.
#
# Everything the grant loop remembers lives behind STORE (see store.py):
# negotiations and the tickets that index them, issued RPTs, standing
# connections, the ledger, Alice's tiers, the resource servers she has
# authorized. Two backends — in-process for the compose stack, Postgres when
# this service runs replicated — because at more than one replica a
# module-level dict is not merely slower, it is wrong: a ticket minted here
# is unknown there, and a single-use burn stops being single-use.
#
# The negotiation record is keyed by its *family* and lives for the whole
# negotiation; the ticket table is only a rotating index into it. Each
# presentation consumes the current ticket (UMA 2.0 single-use rule) and, if
# the negotiation continues, a fresh ticket is indexed to the same family.
#
# Keying the record by the ticket instead — the obvious first design — makes
# the record invisible between the pop and the re-insert, so a concurrent
# /owner/pending misses it and /owner/pending/{family}/decision 404s on a
# negotiation that plainly exists. The family is the stable identity here;
# the ticket is a credential for it.
#
# RESOURCES stays here, per process, and deliberately: it is a *derived*
# cache of what the resource server publishes, re-pullable at any time from
# the authoritative copy, so replicas converging separately is correct rather
# than merely tolerable. Standing relationships are the opposite — one wrong
# answer there is an access-control failure — which is the line between the
# two.
# ---------------------------------------------------------------------------
# How much the requesting side may write about itself. Small on purpose: this
# is a sentence for a person to read in an approval dialog, not a document.
MAX_REASON = int(os.environ.get("UMA_AS_MAX_REASON", "512"))

# How far back a rule about an agent's recent behaviour looks. One window for
# all of them, so a rule reads "recently" and the deployment says how long that
# is, rather than every rule carrying its own duration.
TRAJECTORY_WINDOW = os.environ.get("UMA_AS_TRAJECTORY_WINDOW", "7d")

STORE: store.Store = store.make_store()
RESOURCES: dict[str, dict] = {}


def jwk_thumbprint(jwk: dict) -> str:
    """RFC 7638 thumbprint (OKP profile)."""
    canonical = json.dumps(
        {"crv": jwk["crv"], "kty": jwk["kty"], "x": jwk["x"]},
        separators=(",", ":"), sort_keys=True,
    )
    return "jkt:" + base64.urlsafe_b64encode(
        hashlib.sha256(canonical.encode()).digest()
    ).rstrip(b"=").decode()


def utcstamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


async def ledger_add(owner: str, kind: str, family: str, entry: dict,
                     handle: str | None = None) -> None:
    """One decision record. `handle` names the agent it was about, where
    there is one — see Store.ledger_add for why it is not part of `entry`."""
    await st(owner).ledger_add(kind, family, utcstamp(), entry, handle)


async def owner_notify(owner: str, payload: dict) -> None:
    await st(owner).notify(payload)


async def new_ticket(record: dict) -> str:
    """Mint a ticket and index it to the record's family, marked with the
    owner so it can be resolved on the way back in."""
    owner = record["owner"]
    ttl = PENDING_TTL if record.get("state") == "awaiting-owner" else TICKET_TTL
    raw = await st(owner).mint_ticket(record, ttl)
    return f"{_enc_owner(owner)}~{raw}"


async def close_negotiation(rec: dict | None) -> None:
    if rec:
        await st(rec["owner"]).close_negotiation(rec.get("family"))


# --- Basics -----------------------------------------------------------------


@app.on_event("startup")
async def open_store() -> None:
    await STORE.start()
    # An owner who has never been seen has no policy, and policy is what the
    # grant loop reads first. Seeding the ones this instance knows about at
    # startup keeps a cold database serviceable; an owner who appears later is
    # seeded when she first authenticates.
    await st(DEFAULT_OWNER).seed()


@app.on_event("shutdown")
async def close_store() -> None:
    await STORE.close()


@app.get("/health")
async def health() -> dict:
    """Liveness and readiness both.

    Deliberately independent of whether the registry pull has completed. The
    pull calls this AS's *public* hostname, which routes back here for a JWKS
    check — so gating readiness on it would leave this service with no ready
    endpoints, which fails the back-call, which fails the pull, which never
    lets readiness go green. See /health/registry for the honest answer to
    "has the pull finished", which is a question worth asking and a terrible
    readiness probe.
    """
    return {"status": "ok", "issuer": ISSUER}


@app.get("/health/registry")
async def health_registry() -> JSONResponse:
    """Has this replica's declarative pull landed yet?

    For `kubectl wait`, the smoke tests and a dashboard panel — never for a
    readiness probe (see /health).
    """
    ready = bool(RESOURCES)
    return JSONResponse(
        {"status": "ok" if ready else "pending", "resources": len(RESOURCES)},
        status_code=200 if ready else 503,
    )


@app.get("/jwks")
async def jwks() -> dict:
    jwk = json.loads(OKPAlgorithm.to_jwk(SIGNING_KEY.public_key()))
    jwk.update({"kid": KID, "use": "sig"})
    return {"keys": [jwk]}


@app.get("/.well-known/uma4agents-configuration")
async def discovery() -> dict:
    return {
        "issuer": ISSUER,
        "token_endpoint": f"{ISSUER}/token",
        "permission_endpoint": f"{ISSUER}/perm",
        "introspection_endpoint": f"{ISSUER}/introspect",
        "jwks_uri": f"{ISSUER}/jwks",
        "terms_endpoint": f"{ISSUER}/terms",
        "grant_types_supported": ["urn:ietf:params:oauth:grant-type:uma-ticket"],
        "claim_token_formats_supported": [AGREEMENT_FORMAT],
    }


# --- Terms roster (MyTerms pattern: proffered terms are persistent documents) -

# Every version of every proffered terms document is kept dereferenceable at
# a stable URI for the life of the AS — the "persistent record of the
# policies the requesting party promises to adhere to" (2010), in MyTerms
# shape. They live in the store: a terms URI that resolved on one replica and
# 404'd on another would break exactly the property that makes a signed
# agreement checkable later.


def terms_uri(template_id: str) -> str:
    return f"{ISSUER}/terms/{template_id}"


def owner_of_template(template_id: str) -> str:
    """Template ids are namespaced by owner — `alice/advisor-tier1/v2` — so a
    terms document dereferenced by an agent who has no token still resolves to
    whose terms it is. That namespacing predates multi-owner; it just turned
    out to be the lookup."""
    head = (template_id or "").split("/", 1)[0]
    return head or DEFAULT_OWNER


async def publish_terms(owner: str, tier_id: str, tier: dict) -> str:
    """Archive the current version of a tier's terms as a served document.
    Idempotent per template_id (a version's content never changes)."""
    template_id = tier["terms"]["template_id"]
    if await st(owner).terms_doc(template_id) is None:
        await st(owner).publish_terms({
            "template_id": template_id,
            "terms_uri": terms_uri(template_id),
            "proffered_by": ISSUER,
            "name": tier["name"],
            "tier": tier_id,
            **{k: v for k, v in tier["terms"].items() if k != "template_id"},
            "published_at": utcstamp(),
        })
        event("terms.published", template_id=template_id, tier=tier_id)
    return terms_uri(template_id)


async def ensure_owner(owner: str) -> None:
    """Seed an owner, and publish the terms documents her tiers name.

    Both halves, and the second is easy to miss: seeding creates the policy
    but a terms document is a *served* artifact, and the challenge tells an
    agent to go and fetch one. An owner who first appears after startup would
    otherwise have tiers whose `terms_uri` 404s — which fails at beat 2, in
    the agent, a long way from the cause.
    """
    await st(owner).seed()
    for tier_id, tier in (await st(owner).tiers()).items():
        await publish_terms(owner, tier_id, tier)


@app.on_event("startup")
async def publish_initial_terms() -> None:
    for owner in await STORE.owners() or [DEFAULT_OWNER]:
        await ensure_owner(owner)


@app.get("/terms")
async def terms_index(owner: str = None) -> dict:
    """One owner's proffered terms. `?owner=` on a multi-tenant instance;
    the served owner otherwise."""
    who = owner or DEFAULT_OWNER
    return {
        "owner": who,
        "proffered_by": ISSUER,
        "terms": await st(who).terms_docs(),
    }


def terms_as_html(doc: dict) -> str:
    """The plain-language representation IEEE 7012 (4.4.1) requires the terms
    themselves to carry — same URI as the machine-readable form.

    Every interpolation is escaped. Alice writes most of this herself through
    the owner API, so it is not obviously attacker-controlled — but a terms
    document is a public URL that agents dereference and quote, and a rendering
    that trusts its own stored values is one owner-API bug away from serving
    markup. Escaping here costs nothing and does not depend on that argument
    staying true."""
    e = html.escape
    enforced = doc.get("enforced") or {}
    prohibited = "".join(
        f"<li>{e(str(p))}"
        + (f" — <b>refused at the door</b> ({e(str(enforced[p]))})"
           if p in enforced else " — undertaken, not enforced")
        + "</li>"
        for p in doc.get("prohibited", []))
    scopes = e(", ".join(doc.get("scope", [])))
    hours = round(doc.get("expires_in", 0) / 3600, 1)
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>{e(str(doc['name']))} — {e(str(doc['template_id']))}</title>
<style>body{{background:#0b0e14;color:#e6e9f0;font-family:system-ui;max-width:640px;
margin:3rem auto;padding:0 1rem;line-height:1.6}}h1{{font-size:1.3rem}}
code{{background:#161b26;padding:2px 7px;border-radius:5px}}
.k{{color:#8a93a8}}li{{margin:.2rem 0}}</style></head><body>
<h1>{e(str(doc['name']))}</h1>
<p class="k">Terms <code>{e(str(doc['template_id']))}</code>, proffered by
<code>{e(str(doc['proffered_by']))}</code>, published {e(str(doc['published_at']))}.</p>
<p>The owner of these accounts offers access on the following terms. By
signing an agreement that names this document, you accept all of them.</p>
<ul>
<li><b>Purpose</b> — access is granted only for: {e(str(doc['purpose']))}.</li>
<li><b>What you may access</b> — {scopes}.</li>
<li><b>How long</b> — access expires {int(doc['expires_in'])} seconds
    (~{hours} hours) after grant.</li>
<li><b>Prohibited</b> — you agree you will not engage in:<ul>{prohibited}</ul></li>
<li><b>Anything not expressly permitted here is not permitted.</b></li>
</ul>
<p class="k">Machine-readable: this same URI as <code>application/json</code>,
or <code>?format=jsonld</code> for a JSON-LD/ODRL representation.</p>
</body></html>"""


def terms_as_jsonld(doc: dict) -> dict:
    """JSON-LD/ODRL representation (IEEE 7012 4.4.2 and Annex A principle (j):
    structured, IRI-linked terms; ODRL for permissions/prohibitions).
    Prohibition actions are fragment IRIs on the terms document itself, which
    dereferences to their definition."""
    uri = doc["terms_uri"]
    return {
        "@context": {
            "odrl": "http://www.w3.org/ns/odrl/2/",
            "dcterms": "http://purl.org/dc/terms/",
        },
        "@id": uri,
        "@type": "odrl:Offer",
        "odrl:uid": uri,
        "dcterms:title": doc["name"],
        "dcterms:identifier": doc["template_id"],
        "dcterms:publisher": doc["proffered_by"],
        "dcterms:issued": doc["published_at"],
        "dcterms:description": doc["purpose"],
        "odrl:permission": [
            {"odrl:action": f"{uri}#scope/{s}", "odrl:constraint": [
                {"odrl:leftOperand": "odrl:elapsedTime",
                 "odrl:operator": "odrl:lteq",
                 "odrl:rightOperand": {"@value": f"PT{doc['expires_in']}S",
                                        "@type": "xsd:duration"}}]}
            for s in doc.get("scope", [])
        ],
        "odrl:prohibition": [
            {"odrl:action": f"{uri}#prohibited/{p}"} for p in doc.get("prohibited", [])
        ],
    }


async def annotate_enforced(owner: str, doc: dict) -> dict:
    """Mark which prohibitions the enforcement point currently refuses.

    Computed on read and deliberately not stored. `publish_terms` is
    idempotent because an agreement names a version and must stay checkable
    against exactly the bytes that were proffered — so a document cannot gain
    a field later, and anything that can change without the terms changing has
    no business inside one. Whether reuse is refused depends on the tier's
    `per_operation` switch, which she can flip without rewriting a word.

    Only annotated while this version is the one in force. A superseded
    version would otherwise be labelled with today's posture, which is a
    different kind of wrong from saying nothing.
    """
    tiers = await st(owner).tiers()
    tier = tiers.get(doc.get("tier") or "")
    if not tier or tier["terms"]["template_id"] != doc["template_id"]:
        return doc
    return {**doc, "enforced": policy.enforced_prohibitions(tier)}


@app.get("/terms/{template_id:path}")
async def terms_document(template_id: str, request: Request, format: str = None):
    owner = owner_of_template(template_id)
    doc = await st(owner).terms_doc(template_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="unknown terms document")
    # The stored bytes are what was proffered and signed against. The
    # enforcement posture is annotated on top, never folded in.
    doc = await annotate_enforced(owner, doc)
    if format == "jsonld":
        return JSONResponse(terms_as_jsonld(doc), media_type="application/ld+json")
    accept = request.headers.get("accept", "")
    if "text/html" in accept and "application/json" not in accept.split(",")[0]:
        from fastapi.responses import HTMLResponse
        return HTMLResponse(terms_as_html(doc))
    return doc


def _bearer(request: Request) -> str:
    authz = request.headers.get("authorization", "")
    if not authz.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="bearer token required")
    return authz[7:]


async def issue_pat(owner: str, client_id: str) -> dict:
    """Mint a PAT: an OAuth access token for the Protection API, carrying
    the owner it acts about (FedAuthz's RO context) and the RS it was
    issued to."""
    exp = int(now()) + PAT_TTL
    token = jwt.encode(
        {
            "iss": ISSUER,
            "sub": owner,
            "azp": client_id,
            "scope": "uma_protection",
            "jti": f"pat_{uuid.uuid4().hex[:12]}",
            "exp": exp,
        },
        SIGNING_KEY,
        algorithm="EdDSA",
        headers={"typ": "pat+jwt", "kid": KID},
    )
    await st(owner).touch_pat(client_id, utcstamp())
    event("pat.issued", client_id=client_id, expires_in=PAT_TTL)
    return {"access_token": token, "token_type": "Bearer",
            "expires_in": PAT_TTL, "scope": "uma_protection"}


async def require_pat(request: Request) -> str:
    """The Protection API takes the PAT this AS issued — verified, scoped,
    and revocable via the owner's resource-server registry.

    Returns the owner it was issued for. One resource server holds one PAT per
    owner it serves, so the token is what says whose resources this call is
    about; there is no other signal on a Protection API request."""
    try:
        claims = jwt.decode(_bearer(request), SIGNING_KEY.public_key(),
                            algorithms=["EdDSA"], issuer=ISSUER,
                            options={"verify_aud": False})
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401,
                            detail=f"protection API requires a valid PAT: {exc}")
    if "uma_protection" not in claims.get("scope", "").split():
        raise HTTPException(status_code=403, detail="PAT lacks uma_protection scope")
    owner = claims.get("sub") or DEFAULT_OWNER
    if not serves(owner):
        raise HTTPException(status_code=403,
                            detail="this authorization server serves a different owner")
    rs = await st(owner).resource_server(claims.get("azp", ""))
    if rs is None or rs["status"] != "active":
        raise HTTPException(status_code=401,
                            detail="the owner has revoked this resource server")
    return owner


_OWNER_KEYS_CACHE: dict[str, tuple[float, list]] = {}


def owner_issuer_keys() -> list:
    cached = _OWNER_KEYS_CACHE.get(OWNER_ISSUER)
    if cached and cached[0] > now():
        return cached[1]
    import httpx

    with httpx.Client(verify=AGENT_ISSUER_CA or True, timeout=5.0) as client:
        meta = client.get(OWNER_METADATA_URL)
        meta.raise_for_status()
        jwks = client.get(meta.json()["jwks_uri"])
        jwks.raise_for_status()
    keys = jwks.json()["keys"]
    _OWNER_KEYS_CACHE[OWNER_ISSUER] = (now() + JWKS_CACHE_TTL, keys)
    return keys


_OWNER_KEY_CACHE: dict[str, object] = {}


def owner_device_key():
    """Her registered device key, in local-key mode.

    Read once and cached. A real deployment enrols this key — she proves
    possession of it on a device she already trusts — rather than finding it
    on disk; the lab writes it at first run so the stack has nothing to set up.
    """
    from cryptography.hazmat.primitives.serialization import load_pem_public_key

    cached = _OWNER_KEY_CACHE.get(OWNER_KEY_PATH)
    if cached is not None:
        return cached
    try:
        with open(OWNER_KEY_PATH, "rb") as fh:
            key = load_pem_public_key(fh.read())
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=(f"UMA_AS_OWNER_AUTH=local-key but no owner key at "
                    f"{OWNER_KEY_PATH}: {exc}")) from exc
    _OWNER_KEY_CACHE[OWNER_KEY_PATH] = key
    return key


async def require_owner_signature(request: Request) -> str:
    """The owner signs her own request, with her own key.

    **A key names a holder, not an owner**, so the binding is configuration:
    `UMA_AS_OWNER_KEY` is registered *for* `UMA_AS_OWNER_KEY_OWNER`. Verifying
    the signature proves the holder; the registration says whose key it is.

    One key per instance is the lab's simplification, and the honest limit: a
    multi-tenant deployment serving a million people would hold these as
    per-owner records rather than one environment variable, keyed the same way
    everything else here is. The verification is unchanged either way — what
    changes is where the binding is read from.

    RFC 9421 over method, authority, path and authorization, verified with
    `lib/uma4a_http_sig.py` — the same module the enforcement point uses.
    There is no bearer token to steal, nothing to introspect, and no third
    party that has to be available: the authority holds one public key.

    **A request with a body must also cover an RFC 9530 Content-Digest.** The
    four base components say who is asking and what they are asking of; they
    say nothing about the bytes. That is adequate for a GET and unsafe for
    `POST /owner/pending/{family}/decision`, whose whole meaning is a word in
    its body: without the digest an intermediary can leave her signature
    untouched and turn an approval into a refusal. The family is in the path
    and so cannot be retargeted — but the answer could be inverted, which is
    worse, because it is silent and it is hers.

    `authorization` is part of the signature base whether or not it carries a
    value, so an owner request that has no bearer token signs the empty
    string.
    """
    from uma4a_http_sig import VerifyError
    from uma4a_http_sig import verify as verify_sig

    sig_input = request.headers.get("signature-input")
    sig = request.headers.get("signature")
    if not sig_input or not sig:
        raise HTTPException(
            status_code=401,
            detail="owner API requires an RFC 9421 signature from the owner's key")

    path = request.url.path
    if request.url.query:
        path = f"{path}?{request.url.query}"
    # Read once and cache on the request: FastAPI's body() is memoised, so the
    # route handler still gets it after this.
    body = await request.body()
    try:
        verify_sig(
            method=request.method,
            authority=OWNER_EXPECTED_AUTHORITY,
            path=path,
            authorization=request.headers.get("authorization", ""),
            signature_input=sig_input,
            signature=sig,
            public_key=owner_device_key(),
            body=body if body else None,
            require_digest=bool(body),
            digest_header=request.headers.get("content-digest"),
        )
    except VerifyError as exc:
        raise HTTPException(
            status_code=401, detail=f"owner signature did not verify: {exc}") from exc

    # Named, never inferred. Treating a valid signature as "whoever the
    # request seems to be about" would let one key holder act as somebody
    # else's authority, which is the thing this service exists to prevent.
    return OWNER_KEY_OWNER


async def require_owner(request: Request) -> str:
    """Whoever is calling the owner API has to be an owner, and gets their own.

    Returns the owner the credential proved, which is the only thing every
    handler below then uses to reach the store. There is no ambient owner: a
    handler that forgets to ask cannot read anything.

    Any configured credential that verifies is enough — she is one person
    however she reached this. Every owner endpoint calls this, so none of them
    needs to know which credentials the deployment accepts.

    A 401 is returned only when *no* configured mode verifies, and it carries
    the last reason rather than a list, so a caller presenting one credential
    is told why that one failed instead of why the others did.
    """
    unknown = [m for m in OWNER_AUTH if m not in VERIFY_OWNER]
    if unknown or not OWNER_AUTH:
        raise HTTPException(
            status_code=500,
            detail=(f"UMA_AS_OWNER_AUTH must be a comma-separated list of "
                    f"{'|'.join(sorted(VERIFY_OWNER))}; got {unknown or 'nothing'}"))

    # Which failure to report when several modes are configured and all of
    # them fail. "The last one" is the obvious choice and the wrong one: a 403
    # from a credential that *did* authenticate ("this server serves a
    # different owner") is the useful answer, and it was being overwritten by
    # a later mode's 401 for a credential that was never presented. Prefer the
    # most advanced failure.
    last: HTTPException | None = None
    best: HTTPException | None = None
    for mode in OWNER_AUTH:
        try:
            result = VERIFY_OWNER[mode](request)
            if hasattr(result, "__await__"):
                owner = await result
            else:
                owner = result
            owner = owner or DEFAULT_OWNER
            if not serves(owner):
                raise HTTPException(
                    status_code=403,
                    detail="this authorization server serves a different owner")
            # An owner seen for the first time gets her starting policy here,
            # which is also the moment a multi-tenant deployment learns she
            # exists.
            await ensure_owner(owner)
            return owner
        except HTTPException as exc:
            last = exc
            if best is None or exc.status_code > best.status_code:
                best = exc
    raise best or last or HTTPException(status_code=401,
                                        detail="owner authentication failed")


def require_owner_oidc(request: Request) -> str:
    """One of the credentials: Alice's own OIDC access token, validated against
    her realm's published keys. The portal proxies it; the simulated Alice
    obtains one by actually logging in (direct-access grant)."""
    from jwt.algorithms import RSAAlgorithm

    token = _bearer(request)
    try:
        header = jwt.get_unverified_header(token)
        claims = None
        last_error: Exception | None = None
        for jwk_dict in owner_issuer_keys():
            if jwk_dict.get("use") == "enc":
                continue
            if header.get("kid") and jwk_dict.get("kid") != header["kid"]:
                continue
            try:
                claims = jwt.decode(
                    token, RSAAlgorithm.from_jwk(json.dumps(jwk_dict)),
                    algorithms=["RS256"], issuer=OWNER_ISSUER,
                    options={"verify_aud": False})
                break
            except jwt.InvalidTokenError as exc:
                last_error = exc
        if claims is None:
            raise last_error or ValueError("no matching realm key")
    except Exception as exc:
        raise HTTPException(status_code=401,
                            detail=f"owner API requires the owner's OIDC token: {exc}")
    if claims.get("azp") not in OWNER_AUDIENCES:
        raise HTTPException(status_code=403,
                            detail="token was not issued to an owner-surface client")
    # The authenticated username *is* the owner. Whether this instance serves
    # her is decided once, in require_owner, rather than here.
    owner = claims.get("preferred_username")
    if not owner:
        raise HTTPException(status_code=403,
                            detail="owner token carries no preferred_username")
    return owner



# Filled after both verifiers exist. A deployment names the credentials it
# accepts; this maps each name to the code that checks it.
VERIFY_OWNER = {
    "oidc": require_owner_oidc,
    "local-key": require_owner_signature,
}


# --- Declarative registration (pull mode) -------------------------------------


def well_known_prm_url(resource_uri: str) -> str:
    from urllib.parse import urlparse

    u = urlparse(resource_uri)
    return (f"{u.scheme}://{u.netloc}"
            f"/.well-known/oauth-protected-resource{u.path.rstrip('/')}")


def pull_registrations(client_id: str, rs: dict) -> int:
    """Read the RS's published metadata and materialize the registry.

    Takes the resource-server record rather than looking it up: this runs on
    a worker thread (see pull_at_startup) and so cannot reach the store.

    1. Fetch the public RFC 9728 document (TLS-anchored) and verify its
       signed_metadata against the resource's jwks_uri — the pulled copy is
       attributable, not just transport-secure.
    2. Query the protected owner-resources endpoint it advertises, signing
       the request with this AS's key (RFC 9421) — "protected webfinger":
       the RS serves the owner-bound instances only to her AS.
    """
    import httpx

    from uma4a_http_sig import sign as http_sign

    resource_uri = rs["resource_uri"]
    with httpx.Client(verify=AGENT_ISSUER_CA or True, timeout=10.0) as client:
        prm = client.get(well_known_prm_url(resource_uri))
        prm.raise_for_status()
        doc = prm.json()
        if doc.get("resource") != resource_uri:
            raise ValueError(f"metadata is for {doc.get('resource')!r}")
        if ISSUER not in doc.get("authorization_servers", []):
            raise ValueError("the RS's metadata does not name this AS")

        jwks = client.get(doc["jwks_uri"])
        jwks.raise_for_status()
        signed = doc.get("signed_metadata")
        if not signed:
            raise ValueError("published metadata is not signed")
        verified = None
        for jwk_dict in jwks.json()["keys"]:
            try:
                verified = jwt.decode(signed, OKPAlgorithm.from_jwk(json.dumps(jwk_dict)),
                                      algorithms=["EdDSA"],
                                      options={"verify_aud": False})
                break
            except jwt.InvalidTokenError:
                continue
        if verified is None or verified.get("iss") != resource_uri:
            raise ValueError("signed_metadata did not verify against the "
                             "resource's published keys")

        endpoint = verified.get("owner_resources_endpoint")
        if not endpoint:
            raise ValueError("no owner_resources_endpoint in signed metadata")
        from urllib.parse import urlparse

        u = urlparse(endpoint)
        headers = http_sign(method="GET", authority=u.netloc, path=u.path,
                            authorization="", key=SIGNING_KEY, keyid=KID)
        listing = client.get(endpoint, headers=headers)
        listing.raise_for_status()
        body = listing.json()

    count = 0
    for res in body.get("resources", []):
        RESOURCES[res["_id"]] = {
            "resource_scopes": res["resource_scopes"],
            "name": res.get("name"),
            "type": res.get("type"),
            "icon_uri": None,
            "description": None,
            "registered_via": "pull",
            "owner": body.get("owner"),
        }
        count += 1
    event("resources.pulled", client_id=client_id, owner=body.get("owner"),
          count=count, endpoint=endpoint)
    return count


@app.on_event("startup")
async def pull_at_startup() -> None:
    async def attempt_loop():
        for _ in range(60):
            owners = await STORE.owners() or [DEFAULT_OWNER]
            pairs = [(o, cid, rs) for o in owners
                     for cid, rs in (await st(o).resource_servers()).items()]
            for owner, client_id, rs in pairs:
                try:
                    # Off the event loop: the RS authenticates this AS's
                    # signed query by fetching *our* JWKS, so the pull and
                    # the verification form a call cycle — a blocking pull
                    # deadlocks a single-threaded AS. (Finding: pull-model
                    # verification must tolerate a live back-call, or keys
                    # must be cached ahead of need.)
                    #
                    # The same cycle is why /health must not report this
                    # loop's progress: under an orchestrator that gates
                    # traffic on readiness, the back-call would have nowhere
                    # to land and the loop could never finish.
                    await asyncio.to_thread(pull_registrations, client_id, rs)
                    return
                except Exception as exc:
                    event("resources.pull_retry", client_id=client_id,
                          error=str(exc)[:200])
            await asyncio.sleep(2)
        event("resources.pull_failed", note="lazy pull on first /perm remains")

    asyncio.create_task(attempt_loop())


# --- Protection API (gateway-side, FedAuthz shape) ---------------------------


@app.post("/perm")
async def register_permission(request: Request) -> JSONResponse:
    owner = await require_pat(request)
    body = await request.json()
    rid = body.get("resource_id")
    # FedAuthz §4.1: the AS only issues tickets against its own registry.
    registered = RESOURCES.get(rid)
    if registered is None:
        # An unknown id means our pulled copy may be stale, so re-read what
        # the RS publishes. Staleness is the price of declarative
        # registration, and repairing it is this side's job — the mirror of
        # the RS-side re-push that classic RReg required.
        # (to_thread: see pull_at_startup — the pull triggers a JWKS
        # back-call from the RS and must not block this event loop.)
        for client_id, rs in (await st(owner).resource_servers()).items():
            try:
                await asyncio.to_thread(pull_registrations, client_id, rs)
            except Exception as exc:
                event("resources.pull_retry", client_id=client_id,
                      error=str(exc)[:200])
        registered = RESOURCES.get(rid)
    if registered is None:
        event("permission.rejected", resource_id=rid, reason="invalid_resource_id")
        return JSONResponse(
            {"error": "invalid_resource_id",
             "error_description": "resource is not registered at this AS"},
            status_code=400,
        )
    scopes = body.get("resource_scopes") or []
    if not scopes or not set(scopes).issubset(set(registered["resource_scopes"])):
        event("permission.rejected", resource_id=rid, reason="invalid_scope",
              requested=scopes)
        return JSONResponse(
            {"error": "invalid_scope",
             "error_description": "requested scopes exceed the registered resource"},
            status_code=400,
        )
    family = f"fam_{secrets.token_urlsafe(8)}"
    ticket = await new_ticket(
        {
            "owner": owner,
            "family": family,
            "state": "issued",
            "resource_id": rid,
            "resource_scopes": scopes,
        }
    )
    event("permission.registered", corr=family, resource_id=rid, scopes=scopes)
    return JSONResponse({"ticket": ticket}, status_code=201)


async def _decode_rpt(token: str) -> tuple[dict | None, dict | None, str]:
    """Decode and look up an RPT. Returns (claims, record, error_code)."""
    try:
        claims = jwt.decode(
            token,
            SIGNING_KEY.public_key(),
            algorithms=["EdDSA"],
            issuer=ISSUER,
            options={"verify_aud": False},
        )
    except jwt.ExpiredSignatureError:
        return None, None, "expired"
    except jwt.InvalidTokenError:
        return None, None, "invalid_signature"
    owner = claims.get("owner") or DEFAULT_OWNER
    rec = await st(owner).rpt(claims.get("jti", ""))
    if rec is None:
        return claims, None, "unknown_token"
    if (conn := await st(owner).connection(rec.get("handle") or "")) is not None:
        if conn["status"] != "active":
            return claims, rec, "connection_revoked"
    if claims.get("single_use") and rec["consumed"]:
        return claims, rec, "already_consumed"
    return claims, rec, ""


@app.post("/introspect")
async def introspect(request: Request, token: str = Form(...), consume: str = Form(None)) -> dict:
    await require_pat(request)
    claims, rec, err = await _decode_rpt(token)
    if err:
        # RFC 7662 permits additional members. Without a reason the PEP cannot
        # tell "come back after re-negotiating" from "the owner revoked you and
        # re-negotiating is pointless" — and sends revoked agents round a loop.
        event("rpt.introspected", corr=(rec or {}).get("family"), result=err)
        return {"active": False, "error": err}

    owner = claims.get("owner") or DEFAULT_OWNER
    if rec.get("handle"):
        await st(owner).touch_connection(rec["handle"], utcstamp())
    # Consumption is no longer done here by default: the PEP has not yet
    # verified proof-of-possession at this point, so burning the token now
    # lets an unsigned replay destroy a grant the owner just approved. The
    # PEP calls /consume once every check has passed. The parameter is kept
    # for the single-shot case where a caller has already verified.
    if claims.get("single_use") and consume == "true":
        if await st(owner).consume_rpt(claims.get("jti", "")) is None:
            event("rpt.introspected", corr=rec["family"], result="already_consumed")
            return {"active": False, "error": "already_consumed"}
        event("rpt.consumed", corr=rec["family"], jti=claims.get("jti", ""))

    event("rpt.introspected", corr=rec["family"], result="active")
    return {
        "active": True,
        "family": rec["family"],
        "iss": claims["iss"],
        "sub": claims.get("sub"),
        "exp": claims["exp"],
        "permissions": claims["permissions"],
        "cnf": claims.get("cnf"),
        "contract": claims.get("contract"),
        "single_use": claims.get("single_use", False),
        "operation": claims.get("operation"),
    }


@app.post("/consume")
async def consume_rpt(request: Request, token: str = Form(...)) -> dict:
    """Burn a single-use RPT — the last step of enforcement, not the first.

    Split out of introspection so the PEP can verify proof-of-possession and
    the operation binding *before* anything is spent. The burn is the atomic
    step: whoever loses the race is told so, and must deny.

    That word "atomic" used to be aspirational. The decode above is a read
    and the burn below is a write, and this was safe only because one event
    loop never yielded between them — a property of the deployment, not of
    the design. It is now a property of the store: a single statement that
    both decides and writes, and reports which caller won. UMA 2.0 says an
    RPT may be single-use; it never says the burn must be indivisible,
    because in 2018 an authorization server was one process.
    """
    pat_owner = await require_pat(request)
    claims, rec, err = await _decode_rpt(token)
    if err:
        return {"consumed": False, "error": err}
    if not claims.get("single_use"):
        return {"consumed": False, "error": "not_single_use"}
    owner = claims.get("owner") or DEFAULT_OWNER
    if owner != pat_owner:
        # The enforcement point holds one PAT per owner it serves. Presenting
        # a grant of Alice's under Carol's PAT is not a mix-up to tolerate.
        event("rpt.consume_refused", corr=None, reason="owner_mismatch")
        return {"consumed": False, "error": "owner_mismatch"}
    family = await st(owner).consume_rpt(claims.get("jti", ""))
    if family is None:
        return {"consumed": False, "error": "already_consumed"}
    event("rpt.consumed", corr=family, jti=claims.get("jti", ""))
    return {"consumed": True, "family": family}


@app.post("/audit/access")
async def audit_access(request: Request) -> dict:
    """The PEP reports allowed calls so the ledger's 'touched' column is
    grounded in enforcement, not client claims."""
    owner = await require_pat(request)
    body = await request.json()
    family = body.get("family", "?")
    # The enforcement point reports what it allowed; the authority decides
    # whose it was, and against which of her tiers. It is never told the handle — it enforces for a policy it
    # cannot read, and the connection is the owner's record, not its.
    grant = await st(owner).grant_for_family(family)
    await ledger_add(owner, "touched", family, {
        "tool": body.get("tool"),
        "summary": body.get("summary"),
        "tier": (grant or {}).get("tier"),
    }, handle=(grant or {}).get("handle"))
    event("access.allowed", corr=body.get("family"), tool=body.get("tool"))
    return {"recorded": True}


# --- Grant API (agent-facing, UMA 2.0 Grant shape) ---------------------------


async def terms_template_for(rec: dict, tier_id: str, tier: dict, family: str) -> dict:
    template = dict(tier["terms"])
    template.update(
        {
            "proffered_by": ISSUER,
            "terms_uri": await publish_terms(rec["owner"], tier_id, tier),
            "nonce": rec["nonce"],
            "family": family,
            "resource_id": rec["resource_id"],
        }
    )
    return template


async def need_info_response(rec: dict, tier_id: str, tier: dict) -> JSONResponse:
    family = rec["family"]
    rec["state"] = "need_info"
    rec["nonce"] = secrets.token_urlsafe(12)
    rec["tier"] = tier_id
    template = await terms_template_for(rec, tier_id, tier, family)
    rec["template"] = template
    rotated = await new_ticket(rec)
    event("need_info.terms_dictated", corr=family, tier=tier_id,
          template_id=template["template_id"], resource_id=rec["resource_id"])
    return JSONResponse(
        {
            "error": "need_info",
            "ticket": rotated,
            "required_claims": [
                {
                    "claim_type": AGREEMENT_CLAIM,
                    "claim_token_format": [AGREEMENT_FORMAT],
                    "friendly_name": f"Alice's terms: {tier['name']}",
                    "terms_template": template,
                }
            ],
        },
        status_code=403,
    )


AGENT_ISSUER_CA = os.environ.get("UMA4A_CA_BUNDLE")  # trust bundle for issuer TLS
_ISSUER_JWKS_CACHE: dict[str, tuple[float, list]] = {}
JWKS_CACHE_TTL = 300


def agent_issuer_keys(iss: str) -> list:
    """Resolve an agent-token issuer's signing keys via AAuth discovery
    (GET {iss}/.well-known/aauth-agent.json -> jwks_uri). TLS on the issuer
    origin is the trust root — AAuth's own precondition — so non-https
    issuers are rejected outright."""
    if not iss.startswith("https://"):
        raise ValueError("agent token issuer must be an https origin")
    cached = _ISSUER_JWKS_CACHE.get(iss)
    if cached and cached[0] > now():
        return cached[1]
    import httpx

    with httpx.Client(verify=AGENT_ISSUER_CA or True, timeout=5.0) as client:
        meta = client.get(f"{iss}/.well-known/aauth-agent.json")
        meta.raise_for_status()
        jwks = client.get(meta.json()["jwks_uri"])
        jwks.raise_for_status()
    keys = jwks.json()["keys"]
    _ISSUER_JWKS_CACHE[iss] = (now() + JWKS_CACHE_TTL, keys)
    return keys


def verify_agent_token(agent_token: str) -> dict:
    """Validate an aa-agent+jwt against its issuer's published keys.
    Returns the verified claims; raises on any break in the chain."""
    header = jwt.get_unverified_header(agent_token)
    if header.get("typ") != "aa-agent+jwt":
        raise ValueError(f"agent token typ must be aa-agent+jwt, got {header.get('typ')!r}")
    unverified = jwt.decode(agent_token, options={"verify_signature": False})
    iss = unverified.get("iss")
    if not iss:
        raise ValueError("agent token has no issuer")
    try:
        candidates = agent_issuer_keys(iss)
    except Exception as exc:
        raise ValueError(f"agent token issuer discovery failed for {iss}: {exc}")
    kid = header.get("kid")
    last_error: Exception | None = None
    for jwk_dict in candidates:
        if kid and jwk_dict.get("kid") and jwk_dict["kid"] != kid:
            continue
        try:
            key = OKPAlgorithm.from_jwk(json.dumps(jwk_dict))
            claims = jwt.decode(agent_token, key, algorithms=["EdDSA"],
                                options={"verify_aud": False})
            if "cnf" not in claims or "jwk" not in claims["cnf"]:
                raise ValueError("agent token carries no cnf.jwk key binding")
            return claims
        except jwt.InvalidTokenError as exc:
            last_error = exc
    raise ValueError(f"agent token signature did not verify against {iss}'s "
                     f"published keys: {last_error}")


def connection_handle(identity: dict, signer_jwk: dict) -> str:
    """The stable name for a standing relationship. A pseudonymous agent *is*
    its key, so the RFC 7638 thumbprint is the handle. An identified agent's
    continuity lives in its issuer+subject — its session keys rotate, and a
    thumbprint-keyed connection would forget the agent every session."""
    if identity.get("level") == "identified":
        from urllib.parse import urlparse

        sub, host = identity["sub"], urlparse(identity["iss"]).netloc
        # Qualify by issuer so two issuers' subjects can never collide —
        # unless the issuer already writes its host into the subject.
        return sub if sub.endswith(f"@{host}") else f"{sub}@{host}"
    return jwk_thumbprint(signer_jwk)


async def first_party_fact(owner: str, identity: dict, axes: dict) -> bool:
    """Did Alice activate this agent herself?

    Two halves, and both are required. The operator the agent names has to be
    an origin she claimed, and her authority has to have found this agent's
    signing key in that operator's own key directory.

    Dropping the second half would be fatal rather than merely weaker. A
    Client ID Metadata Document proves only that it claims the URL it was
    fetched from, so any agent may point at one she publishes and reach
    accountability level 1. Only she can put a key in her directory, which is
    what makes level 2 a fact about *this agent* rather than about her.

    That is also why this may relax a requirement at all: the claim is her
    decision, the attestation is her authority's own check, and the requesting
    side has no hand in either.
    """
    if axes.get("accountability") != assurance.ACCOUNTABILITY_ATTESTED:
        return False
    origin = operator_origin(identity)
    return origin is not None and origin in await st(owner).owned_operators()


def standing_facts(conn: dict | None, tier_id: str,
                   trajectory: dict | None = None,
                   first_party: bool = False) -> dict:
    """What Alice's own authority has seen of this agent.

    Kept apart from assurance because only these may relax a requirement —
    they are the one kind of evidence here that the requesting side had no
    hand in producing. `age_seconds` is None when she has never met it, which
    the conditions read as "younger than everything, older than nothing".

    `trajectory` and `first_party` are read by the caller and passed in, so
    `policy.evaluate` stays a pure function of a dict and can be tested with
    no store at all.
    """
    trajectory = trajectory or {"denials": 0, "tiers": []}
    if conn is None or conn.get("status") != "active":
        return {"active": False, "age_seconds": None, "first_at_tier": True,
                "first_party": first_party,
                "approved_tiers": [], "trajectory": trajectory,
                "revocations": int((conn or {}).get("revocations", 0))}
    age = None
    if first_seen := conn.get("first_seen"):
        try:
            age = max(0, int(now() - calendar.timegm(
                time.strptime(first_seen, "%Y-%m-%dT%H:%M:%SZ"))))
        except ValueError:
            age = None
    return {
        "active": True,
        "age_seconds": age,
        # What this server did.
        "first_party": first_party,
        "first_at_tier": tier_id not in (conn.get("tiers_granted") or []),
        # What Alice decided. Only these may lower a requirement, so they are
        # kept apart from the line above even though both are her side's.
        "approved_tiers": list(conn.get("tiers_approved") or []),
        "revocations": int(conn.get("revocations", 0)),
        # What it has been doing lately. Restrictions only — see policy.py.
        "trajectory": trajectory,
    }


async def trajectory_facts(owner: str, handle: str) -> dict:
    """This agent's recent history, from the ledger her decisions already
    wrote. No counters, no second source of truth.

    Not one of the store's indivisible operations, and it does not need to be:
    the count only ever tightens a requirement, so a replica reading one write
    stale behaves as if the request had arrived a moment earlier — an ordering
    the system already permits. The rule of thumb worth keeping: can a stale
    read widen access beyond what a differently-timed arrival would have? If it
    can, it belongs with the single-use operations instead.
    """
    since = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                          time.gmtime(now() - policy.parse_duration(TRAJECTORY_WINDOW)))
    return await st(owner).trajectory(handle, since)


# Cached, but not forever. An operator removing a key from its directory is
# how it stops vouching for an agent, and a cache with no expiry would keep
# attesting one it had disowned. Bounded as well as timed: the URL is named by
# the requesting side, so an unbounded map is something an agent can grow.
_DIRECTORY_TTL = float(os.environ.get("UMA_AS_DIRECTORY_TTL", "300"))
_DIRECTORY_MAX = 256
_DIRECTORY_CACHE: dict[str, tuple[float, list]] = {}


def operator_origin(identity: dict) -> str | None:
    """The origin of the operator an agent names, or None if it names none.

    Origin rather than the full client_id URL, because an operator publishing
    two metadata documents is still one party — and because the origin is what
    the key-directory check already has to match.
    """
    from urllib.parse import urlparse

    meta = identity.get("client_metadata") or {}
    client_id = meta.get("client_id")
    if not client_id:
        return None
    p = urlparse(client_id)
    return f"{p.scheme}://{p.netloc}" if p.scheme and p.netloc else None


def same_origin(a: str, b: str) -> bool:
    from urllib.parse import urlparse

    pa, pb = urlparse(a), urlparse(b)
    return (pa.scheme, pa.netloc) == (pb.scheme, pb.netloc) and pa.scheme == "https"


def operator_published_key(client_id: str, directory: str,
                           signer_jwk: dict) -> bool:
    """Did the operator named by `client_id` publish this signing key?

    A Web Bot Auth key directory (draft-meunier-http-message-signatures-
    directory) is a JWKS of the keys an operator's agents sign with. Fetching
    it and looking for this key's RFC 7638 thumbprint is a check this server
    performs itself, against a document the *operator* controls and the agent
    does not.

    Two things keep it honest:

    * **Same origin as the client_id.** Otherwise an agent points at a
      directory it runs and attests to itself, which is not an attestation.
    * **Failure is not an accusation.** An unreachable directory leaves the
      claim exactly where it was — self-asserted — rather than counting
      against the agent. Availability of a third party is not evidence about
      the agent, and treating it as such makes any operator's outage look
      like an attack.
    """
    import httpx

    if not same_origin(client_id, directory):
        event("operator_directory.rejected", client_id=client_id,
              directory=directory, reason="not same origin as client_id")
        return False
    def fetch() -> list:
        r = httpx.get(directory, timeout=5.0, follow_redirects=False,
                      verify=AGENT_ISSUER_CA or True)
        r.raise_for_status()
        keys = r.json().get("keys") or []
        if len(_DIRECTORY_CACHE) >= _DIRECTORY_MAX:
            _DIRECTORY_CACHE.pop(next(iter(_DIRECTORY_CACHE)), None)
        _DIRECTORY_CACHE[directory] = (now(), keys)
        return keys

    try:
        wanted = jwk_thumbprint(signer_jwk)

        def holds(keys: list) -> bool:
            for k in keys:
                try:                   # a directory may hold key types we do
                    if jwk_thumbprint(k) == wanted:   # not profile; skip them
                        return True
                except (KeyError, TypeError):
                    continue
            return False

        # Only a *hit* may be served from cache. A miss is re-fetched, because
        # the two errors are not the same size: a stale hit keeps attesting a
        # key the operator has disowned, while a stale miss merely fails to
        # recognise one it has just published — which is the common case, since
        # an agent enrols and then immediately negotiates. So the TTL bounds
        # how long a withdrawal takes to land, and a newly published key is
        # picked up on the next request rather than in five minutes.
        cached = _DIRECTORY_CACHE.get(directory)
        fresh = cached is not None and now() - cached[0] < _DIRECTORY_TTL
        found = fresh and holds(cached[1])
        if not found:
            found = holds(fetch())
        event("operator_directory.checked", directory=directory,
              published=found, from_cache=bool(fresh and found))
        return found
    except Exception as exc:                                       # noqa: BLE001
        event("operator_directory.unresolved", directory=directory,
              reason=str(exc)[:120])
        return False



# --- resource server establishment ---------------------------------------
#
# FedAuthz starts from a resource server that already holds a PAT and says
# nothing about how it came to. Where one operator runs both sides that gap is
# closed by configuration, and a seeded client secret is a fair model of it.
# It stops being closable that way as soon as the authority is the owner's:
# she is not going to paste a secret into her brokerage's console, and the
# brokerage is not going to hold one secret per customer.
#
# So the resource server authenticates as its origin. It signs with a key it
# publishes at that origin, in the RFC 9728 document it already has to serve,
# and this server fetches that document itself. Nothing is provisioned ahead
# of time and no secret is ever transmitted. What is being trusted is control
# of the origin — which is what the address in her challenge pointed at
# anyway, so the check adds no new party to trust.

_RS_META_TTL = float(os.environ.get("UMA_AS_RS_META_TTL", "300"))
_RS_META_CACHE: dict[str, tuple[float, dict]] = {}
# How long a resource that did not check out stays refused without being
# re-fetched, and how big a document may be.
#
# This endpoint takes no credential — that is the point of it — so anyone can
# make this server fetch a URL they chose. Two bounds on what that is worth:
# a failure is remembered briefly, so a flood of bad registrations does not
# become a flood of outbound requests, and a response is read up to a cap
# rather than into memory.
#
# Deliberately the opposite of the operator key directory, which caches only
# hits. There, a stale miss would fail to recognise a key an operator just
# published, in the common case where an agent enrols and immediately
# negotiates — a real cost for no gain, since that check is an attestation.
# Here the fetch *is* the authentication and a registration is retried by a
# resource server rather than awaited by a person, so a few seconds of
# remembered "no" costs nothing and is the only thing bounding the amplifier.
_RS_MISS_TTL = float(os.environ.get("UMA_AS_RS_MISS_TTL", "30"))
_RS_MAX_BYTES = int(os.environ.get("UMA_AS_RS_MAX_BYTES", "65536"))
_RS_MISS_CACHE: dict[str, float] = {}


def _fetch_json(url: str, what: str) -> dict | None:
    """GET a document this server was told to fetch, bounded. None on any
    failure, which every caller reads as "not authenticated"."""
    import httpx

    try:
        with httpx.Client(timeout=5.0, follow_redirects=False,
                          verify=AGENT_ISSUER_CA or True) as c:
            with c.stream("GET", url) as r:
                r.raise_for_status()
                size = 0
                chunks = []
                for chunk in r.iter_bytes():
                    size += len(chunk)
                    if size > _RS_MAX_BYTES:
                        raise ValueError(f"over {_RS_MAX_BYTES} bytes")
                    chunks.append(chunk)
        return json.loads(b"".join(chunks))
    except Exception as exc:                                       # noqa: BLE001
        event(f"resource_server.{what}", url=url, reason=str(exc)[:120])
        return None


def resource_server_metadata(resource_uri: str) -> dict:
    """The RFC 9728 document the named resource publishes about itself.

    Three things have to hold, and each closes a way of registering as
    somebody else:

    * the document claims *this* `resource` — so a host cannot publish
      metadata about a resource it does not serve;
    * its `jwks_uri` is same-origin — so the keys come from the party being
      identified rather than one it points at;
    * it names *this* authorization server — so a resource server cannot
      register with an authority it does not send its own callers to.

    Unlike the operator key directory, an unreachable document here is a
    refusal rather than a shrug. That check attests a claim already made by
    other means; this one *is* the authentication, and a credential that
    cannot be fetched has not been presented.
    """
    from urllib.parse import urlparse

    cached = _RS_META_CACHE.get(resource_uri)
    if cached and now() - cached[0] < _RS_META_TTL:
        return cached[1]
    missed = _RS_MISS_CACHE.get(resource_uri)
    if missed is not None and now() - missed < _RS_MISS_TTL:
        return {}

    def refuse() -> dict:
        if len(_RS_MISS_CACHE) >= 1024:
            _RS_MISS_CACHE.pop(next(iter(_RS_MISS_CACHE)), None)
        _RS_MISS_CACHE[resource_uri] = now()
        return {}

    p = urlparse(resource_uri)
    if p.scheme != "https" or not p.netloc:
        return refuse()
    origin = f"{p.scheme}://{p.netloc}"
    url = (f"{origin}/.well-known/oauth-protected-resource"
           f"{p.path.rstrip('/')}")
    doc = _fetch_json(url, "metadata_unreachable")
    if not isinstance(doc, dict):
        return refuse()

    reasons = []
    if doc.get("resource") != resource_uri:
        reasons.append(f"claims resource {doc.get('resource')!r}")
    jwks_uri = doc.get("jwks_uri") or ""
    if not jwks_uri or not same_origin(jwks_uri, resource_uri):
        reasons.append(f"jwks_uri {jwks_uri!r} is not same-origin")
    if ISSUER not in (doc.get("authorization_servers") or []):
        reasons.append("does not name this authorization server")
    if reasons:
        event("resource_server.metadata_rejected", resource_uri=resource_uri,
              reasons=reasons)
        return refuse()

    if len(_RS_META_CACHE) >= 256:
        _RS_META_CACHE.pop(next(iter(_RS_META_CACHE)), None)
    _RS_META_CACHE[resource_uri] = (now(), doc)
    return doc


def resource_server_keys(resource_uri: str) -> list:
    """The public keys the named resource publishes, as JWKs. Empty on any
    failure, which the callers all read as "not authenticated"."""
    doc = resource_server_metadata(resource_uri)
    if not doc:
        return []
    keys = _fetch_json(doc["jwks_uri"], "jwks_unreachable")
    if not isinstance(keys, dict):
        return []
    found = keys.get("keys")
    return found if isinstance(found, list) else []


async def verify_resource_server_signature(request: Request, body: bytes,
                                           resource_uri: str) -> bool:
    """Did the origin behind `resource_uri` sign this request?

    Off the event loop, because deciding it means dereferencing a host named
    by the caller. This runs on the PAT path, which every resource server
    takes on every refresh; a five-second timeout awaited inline would let one
    slow origin stall every other request this worker is serving.

    Every key that origin publishes is tried, because key rotation overlaps:
    a resource server that has just published a new one may still be signing
    with the old for the length of a deploy. Trying all of them accepts any
    key the origin currently vouches for and no others, which is the same
    answer a kid lookup gives without failing on a stale cache.
    """
    from uma4a_http_sig import VerifyError
    from uma4a_http_sig import verify as verify_sig

    sig_input = request.headers.get("signature-input")
    sig = request.headers.get("signature")
    if not sig_input or not sig:
        return False
    path = request.url.path
    if request.url.query:
        path = f"{path}?{request.url.query}"
    keys = await asyncio.to_thread(resource_server_keys, resource_uri)
    for jwk in keys:
        try:
            key = OKPAlgorithm.from_jwk(json.dumps(jwk))
        except Exception:                                          # noqa: BLE001
            continue                       # a JWKS may hold types we do not
        try:                               # profile; those are simply not it
            verify_sig(
                method=request.method,
                authority=AS_AUTHORITY,
                path=path,
                authorization=request.headers.get("authorization", ""),
                signature_input=sig_input,
                signature=sig,
                public_key=key,
                body=body if body else None,
                require_digest=bool(body),
                digest_header=request.headers.get("content-digest"),
            )
            return True
        except VerifyError:
            continue
    return False


_CIMD_CACHE: dict[str, dict] = {}


def resolve_client_id(client_id: str) -> dict:
    """Fetch and validate a Client ID Metadata Document.

    Per draft-ietf-oauth-client-id-metadata-document the client_id is an https
    URL and the document it resolves to MUST claim that same URL as its own
    `client_id` — otherwise any site could publish metadata about someone
    else's agent. Everything here is display-only, so a failure downgrades to
    "unresolved" rather than rejecting the contract; what it must never do is
    silently present unverified claims as though they were checked.
    """
    import httpx

    if client_id in _CIMD_CACHE:
        return _CIMD_CACHE[client_id]
    out: dict = {"client_id": client_id, "verified": False}
    try:
        if not client_id.startswith("https://"):
            raise ValueError("client_id must be an https URL")
        r = httpx.get(client_id, timeout=5.0, follow_redirects=False,
                      verify=AGENT_ISSUER_CA or True)
        r.raise_for_status()
        doc = r.json()
        if doc.get("client_id") != client_id:
            raise ValueError("document does not claim the URL it was fetched from")
        out = {
            "client_id": client_id,
            "verified": True,
            "client_name": doc.get("client_name"),
            "client_uri": doc.get("client_uri"),
            "logo_uri": doc.get("logo_uri"),
            "policy_uri": doc.get("policy_uri"),
            "tos_uri": doc.get("tos_uri"),
            "contacts": doc.get("contacts"),
        }
        event("client_metadata.resolved", client_id=client_id,
              client_name=out.get("client_name"))
        # Only successes are cached: caching a transient failure would keep an
        # agent nameless in Alice's dialog long after its operator recovered.
        _CIMD_CACHE[client_id] = out
    except Exception as exc:
        out["error"] = str(exc)[:120]
        event("client_metadata.unresolved", client_id=client_id, reason=str(exc)[:120])
    return out


def verify_contract(claim_token_b64: str, rec: dict) -> tuple[dict, dict]:
    """Verify the intent contract JWS and its echo of the dictated template.

    Returns (contract_claims, signer_jwk). The signer key comes from the JWS
    protected header: `jwk` (pseudonymous bare key, an AAuth identity level)
    or the `cnf.jwk` of an embedded `agent_token` (an aa-agent+jwt whose
    signature is verified against its issuer's published keys).
    """
    raw = base64.urlsafe_b64decode(claim_token_b64 + "=" * (-len(claim_token_b64) % 4))
    token = raw.decode()
    header = jwt.get_unverified_header(token)

    if "jwk" in header:
        signer_jwk = header["jwk"]
        identity = {"level": "pseudonymous"}
    elif "agent_token" in header:
        agent_claims = verify_agent_token(header["agent_token"])
        signer_jwk = agent_claims["cnf"]["jwk"]
        identity = {"level": "identified", "iss": agent_claims["iss"],
                    "sub": agent_claims.get("sub")}
    else:
        raise ValueError("contract JWS must carry jwk or agent_token in its header")

    # A CIMD URL, if offered, tells Alice *who operates* this agent. It is
    # resolved and shown, never trusted: the connection handle below is still
    # the key or the verified issuer subject, so a self-asserted name can
    # never widen access. A resolution failure is not a contract failure.
    if client_id := header.get("client_id"):
        identity["client_metadata"] = resolve_client_id(client_id)
        # And, if the agent names the operator's key directory, check whether
        # that operator has published *this* key. That is the difference
        # between "a firm says it operates this agent" and "that firm
        # published this agent's key", and it is the only thing here that
        # makes accountability more than self-assertion.
        #
        # The same-origin requirement is what makes it an attestation *by the
        # named operator*: without it an agent could point at any directory it
        # controls and attest to itself.
        if directory := header.get("signature_agent"):
            identity["operator_attested"] = operator_published_key(
                client_id, directory, signer_jwk)

    key = OKPAlgorithm.from_jwk(json.dumps(signer_jwk))
    contract = jwt.decode(token, key, algorithms=["EdDSA"], audience=ISSUER)
    # The signature verified against a key this server can name and will
    # recognise again. Recorded rather than assumed: `assurance.assess` reads
    # this, so the binding level is an observation and not a comment about the
    # call path. See assurance.py.
    identity["key_bound"] = True

    template = rec["template"]
    if contract.get("nonce") != template["nonce"]:
        raise ValueError("nonce mismatch")
    if contract.get("family") != rec["family"]:
        raise ValueError("negotiation family mismatch")
    if contract.get("template_id") != template["template_id"]:
        raise ValueError("template version mismatch")
    if contract.get("terms_uri") != template["terms_uri"]:
        raise ValueError("agreement must name the proffered terms document")
    if contract.get("purpose") != template["purpose"]:
        raise ValueError("purpose was altered")
    if not set(template["prohibited"]).issubset(set(contract.get("prohibited", []))):
        raise ValueError("prohibited-actions list was weakened")
    if contract.get("expires_in", 0) > template["expires_in"]:
        raise ValueError("expiry was extended beyond dictated terms")
    if template.get("per_operation") and not contract.get("operation"):
        raise ValueError("per-operation tier requires a proposed operation in the contract")

    # The one claim the requesting side authors. It is bounded and nothing
    # else: not compared to her purpose, not parsed, not scored. Reading it
    # would put a judgement about natural language inside the grant, which
    # would make the same request answerable two ways and end the property
    # `make flow-check` asserts. It is checked for size because it is stored
    # and shown to her, and because a field with no ceiling is a place to put
    # a megabyte.
    if (reason := contract.get("reason")) is not None:
        if not isinstance(reason, str):
            raise ValueError("reason must be a string")
        if len(reason.encode()) > MAX_REASON:
            raise ValueError(
                f"reason exceeds the permitted length ({MAX_REASON} bytes)")

    # A citation, checked for shape and nothing else. Whether this request is
    # inside the mission it names is the approver's question, not hers — she
    # has no standing to read Bob's mandate and rule on it, and her authority
    # could not resolve it if it wanted to (AAuth serves missions to admins
    # only). What it establishes is narrower and still worth having: somebody
    # on the other side is running a mandate at all.
    if (mission := contract.get("mission")) is not None:
        if not isinstance(mission, dict):
            raise ValueError("mission must be an object")
        approver, digest = mission.get("approver"), mission.get("s256")
        if not isinstance(approver, str) or not approver.startswith("https://"):
            raise ValueError("mission.approver must be an https URL")
        if not isinstance(digest, str) or not (16 <= len(digest) <= 128):
            raise ValueError("mission.s256 must be a content hash")
        # Normalised down to the two fields AAuth's own header carries, so a
        # citation with extra baggage cannot use her ledger as storage.
        contract["mission"] = {"approver": approver, "s256": digest}

    contract["_identity"] = identity
    return contract, signer_jwk


async def issue_rpt(rec: dict, contract_hash: str, signer_jwk: dict,
                    operation: dict | None) -> dict:
    family = rec["family"]
    owner = rec["owner"]
    tier = (await st(owner).tiers())[rec["tier"]]
    exp = int(now()) + min(3600, tier["terms"]["expires_in"])
    jti = f"rpt_{uuid.uuid4().hex[:12]}"
    claims = {
        "iss": ISSUER,
        "sub": rec.get("agent_sub", "aauth:pseudonymous-agent"),
        # Whose resources this grant is against. `sub` is the agent, so
        # without this a multi-tenant server has nothing on an introspection
        # request that says which owner's registry to consult.
        "owner": owner,
        "aud": "https://gateway.uma.lab",
        "jti": jti,
        "exp": exp,
        "cnf": {"jwk": signer_jwk},
        "permissions": [
            {
                "resource_id": rec["resource_id"],
                "resource_scopes": rec["resource_scopes"],
                "exp": int(now()) + tier["terms"]["expires_in"],
            }
        ],
        "contract": contract_hash,
    }
    if operation is not None:
        claims["single_use"] = True
        claims["operation"] = {
            "tool": operation["tool"],
            "params_s256": s256(json.dumps(operation.get("params", {}), sort_keys=True).encode()),
        }
    token = jwt.encode(claims, SIGNING_KEY, algorithm="EdDSA",
                       headers={"typ": "aa-auth+jwt", "kid": KID})
    handle = connection_handle(rec["contract"]["_identity"], signer_jwk)
    await st(owner).record_rpt(jti, family, handle, claims.get("operation"),
                               rec["tier"])
    event("rpt.issued", corr=family, jti=jti, single_use=claims.get("single_use", False),
          tier=rec["tier"])

    # MyTerms pattern (IEEE 7012 5.2.2/5.4.4): identical, dually-signed
    # copies on both sides. The receipt embeds the complete agent-signed
    # agreement JWS and is counter-signed by the AS, so the artifact the
    # agent stores and the one Alice's side stores are the same record.
    receipt = jwt.encode(
        {
            "iss": ISSUER,
            "sub": handle,
            "iat": int(now()),
            "family": family,
            "terms_uri": rec["template"]["terms_uri"],
            "template_id": rec["template"]["template_id"],
            "agreement": contract_hash,
            "agreement_jws": rec.get("agreement_jws"),
        },
        SIGNING_KEY,
        algorithm="EdDSA",
        headers={"typ": "myterms-receipt+jws", "kid": KID},
    )
    rec["receipt"] = receipt
    event("receipt.issued", corr=family, agreement=contract_hash)
    return {"access_token": token, "token_type": "PoP",
            "expires_in": exp - int(now()), "receipt": receipt}


@app.post("/token")
async def token(request: Request) -> JSONResponse:
    # Read before parsing. A resource server with no shared secret
    # authenticates by signing this request, and the signature covers a
    # digest of the body — so the exact bytes have to be kept. Declaring the
    # fields as FastAPI form parameters would drain the stream before the
    # handler ran, which is why they are pulled out by hand here.
    body = await request.body()
    form = await request.form()
    grant_type = form.get("grant_type") or ""
    ticket = form.get("ticket")
    claim_token = form.get("claim_token")
    claim_token_format = form.get("claim_token_format")
    decline = form.get("decline")
    client_id = form.get("client_id")
    client_secret = form.get("client_secret")
    scope = form.get("scope")
    owner = form.get("owner")
    # PAT issuance: a resource server the owner has authorized exchanges its
    # client credentials for a uma_protection-scoped token (FedAuthz's PAT).
    if grant_type == "client_credentials":
        # A resource server holds one PAT per owner it serves, so the request
        # has to say which. Defaulted rather than required, because a
        # single-owner deployment has nothing to disambiguate.
        pat_owner = owner or DEFAULT_OWNER
        if not serves(pat_owner):
            return JSONResponse({"error": "invalid_client"}, status_code=401)
        await st(pat_owner).seed()
        rs = await st(pat_owner).resource_server(client_id or "")
        if rs is None:
            return JSONResponse({"error": "invalid_client"}, status_code=401)
        # Two ways to be this resource server, and which one applies is a
        # property of the record rather than of the request — so a client
        # that registered by signature cannot fall back to guessing a secret,
        # and one holding a secret cannot be impersonated by anyone who can
        # publish a key. The empty-secret case is branched on explicitly:
        # compare_digest("", "") is true, and a record with no secret must
        # never be openable by sending none.
        if rs.get("secret"):
            if not secrets.compare_digest(client_secret or "", rs["secret"]):
                return JSONResponse({"error": "invalid_client"}, status_code=401)
        elif not await verify_resource_server_signature(
                request, body, rs.get("resource_uri") or ""):
            return JSONResponse({"error": "invalid_client"}, status_code=401)
        if rs["status"] == "pending":
            # Registered, not yet hers. The distinct code is what tells the
            # resource server to wait rather than to register again.
            return JSONResponse(
                {"error": "authorization_pending",
                 "error_description": "the owner has not yet authorized this "
                                      "resource server"},
                status_code=403)
        if rs["status"] != "active":
            return JSONResponse(
                {"error": "access_denied",
                 "error_description": "the owner has revoked this resource server"},
                status_code=403)
        if scope != "uma_protection":
            return JSONResponse({"error": "invalid_scope"}, status_code=400)
        return JSONResponse(await issue_pat(pat_owner, client_id))

    if grant_type != "urn:ietf:params:oauth:grant-type:uma-ticket":
        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)

    ticket_owner, raw_ticket = split_ticket(ticket)
    ticket_owner = ticket_owner or DEFAULT_OWNER
    await st(ticket_owner).reap_expired()
    rec = await st(ticket_owner).consume_ticket(raw_ticket)
    if rec is None:
        event("ticket.presented", corr=None, result="invalid_grant")
        return JSONResponse({"error": "invalid_grant"}, status_code=400)
    family = rec["family"]
    event("ticket.presented", corr=family, state=rec["state"])

    # The requesting side declines the proffered terms. Refusals are records
    # too (IEEE 7012 5.2.4): the owner's ledger notes who walked away from
    # which terms, and the negotiation ends.
    if decline == "true" and rec["state"] == "need_info":
        event("terms.declined", corr=family, tier=rec.get("tier"),
              template_id=rec.get("template", {}).get("template_id"))
        # The one entry with no agent to name, and it is a property of the
        # protocol rather than a gap here: a decline arrives at beat 2, before
        # the requesting side has signed anything, so there is no key, no
        # identity and nothing to file it under. Her record says her terms were
        # refused, which is true and is all that is knowable.
        await ledger_add(rec["owner"], "refused", family, {
            "tier": rec.get("tier"),
            "terms_uri": rec.get("template", {}).get("terms_uri"),
        })
        await close_negotiation(rec)
        return JSONResponse({"error": "request_denied"}, status_code=403)

    # Pending ask-me ticket being re-presented (beat 3, taking longer).
    if rec["state"] == "awaiting-owner":
        return await pending_poll(rec)

    tier_id, tier = policy.tier_for_resource(await st(rec["owner"]).tiers(),
                                             rec["resource_id"])
    if tier_id is None:
        event("policy.evaluated", corr=family, result="no-tier")
        await close_negotiation(rec)
        return JSONResponse({"error": "request_denied"}, status_code=403)

    # Beat 2: no contract yet -> dictate Alice's terms.
    if not claim_token:
        return await need_info_response(rec, tier_id, tier)

    # Beat 3: contract committed.
    if claim_token_format != AGREEMENT_FORMAT:
        return JSONResponse({"error": "invalid_claim_token_format"}, status_code=400)
    if rec["state"] != "need_info":
        return JSONResponse({"error": "invalid_grant"}, status_code=400)
    try:
        contract, signer_jwk = verify_contract(claim_token, rec)
    except Exception as exc:
        event("contract.rejected", corr=family, reason=str(exc))
        await close_negotiation(rec)
        return JSONResponse(
            {"error": "request_denied", "error_description": str(exc)}, status_code=403
        )

    raw = base64.urlsafe_b64decode(claim_token + "=" * (-len(claim_token) % 4))
    contract_hash = s256(raw)
    rec["contract"] = contract
    rec["contract_hash"] = contract_hash
    rec["agreement_jws"] = raw.decode()
    rec["signer_jwk"] = signer_jwk
    if contract["_identity"].get("sub"):
        rec["agent_sub"] = contract["_identity"]["sub"]
    event("contract.committed", corr=family, tier=rec["tier"],
          contract=contract_hash, identity=contract["_identity"]["level"])

    # Named before the first ledger write rather than after it. The promise is
    # the first entry that has an agent to attribute, and both inputs have been
    # in hand since verify_contract returned.
    handle = connection_handle(contract["_identity"], signer_jwk)

    await ledger_add(rec["owner"], "promised", family, {
        "tier": rec["tier"],
        "purpose": contract["purpose"],
        "prohibited": contract["prohibited"],
        "expires_in": contract["expires_in"],
        "contract": contract_hash,
        "terms_uri": contract["terms_uri"],
        "operation": contract.get("operation"),
        "reason": contract.get("reason"),
        "mission": contract.get("mission"),
    }, handle=handle)

    # Day-1 handshake: an agent without a standing connection pends — the same
    # request_submitted machinery, asking a different question ("do you want a
    # relationship with this agent?"). Alice's approval creates the connection
    # AND releases this negotiation in one tap.
    conn = await st(rec["owner"]).connection(handle)
    needs_connection = conn is None or conn["status"] != "active"

    # What her authority can establish about this agent, and what she has
    # herself seen of it. Kept apart on purpose — see `assurance.py`.
    # An operator she has shut out. Blocking is a *restriction*, so it can rest
    # on what the agent claims about itself without any of the usual worry: an
    # agent that lies about its operator only ever lies itself into a refusal.
    #
    # What blocking does not do is remove them from the internet. Drop the
    # client_id and the same party is back as an anonymous stranger — with no
    # accountability, in the small lane, pending in front of her like any
    # other. That is the honest limit, and it is why the lane split matters
    # more than the block does.
    origin = operator_origin(contract["_identity"])
    if origin and origin in await st(rec["owner"]).blocked_operators():
        event("policy.evaluated", corr=family, result="operator-blocked",
              operator=origin)
        await ledger_add(rec["owner"], "refused", family, {"tier": rec["tier"],
                                             "operator": origin,
                                             "because": ["operator is blocked"]},
                         handle=handle)
        await close_negotiation(rec)
        return JSONResponse(
            {"error": "request_denied",
             "error_description": f"the owner does not accept agents from {origin}"},
            status_code=403)

    axes = assurance.assess(contract["_identity"])
    facts = {
        "assurance": axes,
        "standing": standing_facts(
            conn, rec["tier"], await trajectory_facts(rec["owner"], handle),
            await first_party_fact(rec["owner"], contract["_identity"], axes)),
        "request": {"expires_in": contract.get("expires_in", 0),
                    "max_expires_in": tier["terms"]["expires_in"],
                    "reason": contract.get("reason"),
                    "mission": contract.get("mission")},
        "tier": rec["tier"],
    }
    requirement, reasons = policy.evaluate(tier, facts)
    event("assurance.assessed", corr=family, **axes)

    if requirement == policy.REFUSE:
        event("policy.evaluated", corr=family, result="refused", tier=rec["tier"],
              because=reasons)
        await ledger_add(rec["owner"], "refused", family, {"tier": rec["tier"],
                                             "because": reasons},
                         handle=handle)
        await close_negotiation(rec)
        return JSONResponse({"error": "request_denied",
                             "error_description": "; ".join(reasons)},
                            status_code=403)

    needs_operation_approval = requirement == policy.ASK

    # Her attention has a depth limit, and only strangers spend it. An agent she
    # already has standing with is never counted at all.
    #
    # Strangers are counted per *lane*, and that split is the whole point: Bob's
    # agent is a stranger too on first contact, so a single queue let a flood of
    # anonymous bots keep him out of the relationship he needed to form. An
    # agent whose named operator published its key queues against other
    # attributable agents only, where a flood has somebody's name on it. See
    # policy.py.
    if needs_connection:
        lane = policy.pend_lane(axes)
        budget = policy.pend_budget(lane)
        waiting = sum(
            1 for p in await st(rec["owner"]).pending_negotiations()
            if p.get("pending_kind") == "connection" and p["family"] != family
            and policy.pend_lane(p.get("assurance") or {}) == lane)
        if waiting >= budget:
            event("policy.evaluated", corr=family, result="attention-budget",
                  lane=lane, waiting=waiting, budget=budget)
            await close_negotiation(rec)
            return JSONResponse(
                {"error": "request_denied",
                 "error_description": "the owner is not accepting new agent "
                                      "requests at the moment; try later"},
                status_code=429)

    if needs_connection or needs_operation_approval:
        kind = "connection" if needs_connection else "operation"
        rec["state"] = "awaiting-owner"
        rec["decision"] = None
        rec["pending_kind"] = kind
        rec["handle"] = handle
        # Persisted on the negotiation, not only pushed over SSE: her portal
        # lists pending requests with a plain GET after a reload, and a dialog
        # that shows what was checked only to whoever was watching live is not
        # much of a dialog.
        rec["assurance"] = axes
        rec["assurance_notes"] = assurance.describe(axes, contract["_identity"])
        rec["because"] = reasons
        rotated = await new_ticket(rec)
        event("ticket.awaiting_owner", corr=family, tier=rec["tier"], kind=kind)
        await owner_notify(
            rec["owner"],
            {
                "type": "pending",
                "kind": kind,
                "family": family,
                "tier": rec["tier"],
                "tier_name": tier["name"],
                "purpose": contract["purpose"],
                "operation": contract.get("operation"),
                "reason": contract.get("reason"),
                "mission": contract.get("mission"),
                "prohibited": contract["prohibited"],
                "enforced": rec["template"].get("enforced") or {},
                "identity": contract["_identity"],
                "handle": handle,
                # What her authority could and could not establish, in
                # sentences rather than integers. A dialog that shows a level
                # without saying what was checked teaches nothing.
                "assurance": axes,
                "assurance_notes": assurance.describe(axes, contract["_identity"]),
                "because": reasons,
            }
        )
        event("owner.notified", corr=family, kind=kind)
        return JSONResponse(
            {"error": "request_submitted", "ticket": rotated, "interval": POLL_INTERVAL},
            status_code=403,
        )

    await st(rec["owner"]).touch_connection(handle, utcstamp())
    await st(rec["owner"]).note_tier_grant(handle, rec["tier"])
    event("policy.evaluated", corr=family, result="auto-grant", tier=rec["tier"],
          connection=handle, because=reasons or None)
    if reasons and requirement == policy.AUTO and tier.get("ask_me"):
        # A rule she wrote lowered an ask-me tier to automatic. That is the
        # one direction worth being able to audit after the fact, so it is a
        # ledger entry and not only a log line.
        await ledger_add(rec["owner"], "relaxed", family, {"tier": rec["tier"],
                                             "because": reasons},
                         handle=handle)
    # The operation, when the contract carries one — not None.
    #
    # This path used to hardcode None, and it was unreachable while every
    # per-operation tier was ask-me with no rule that could lower it. A
    # relaxation reaches it: the tier still requires a named act at commit,
    # `verify_contract` still refuses a contract without one, and the
    # enforcement point still checks the digest on the call. Issuing an
    # unbound token here would have made the grant useless rather than
    # dangerous — the PEP refuses it with `operation_mismatch` — but a tier
    # that silently stops working when she relaxes it is its own kind of
    # broken.
    granted = await issue_rpt(rec, contract_hash, signer_jwk,
                              contract.get("operation"))
    await close_negotiation(rec)
    return JSONResponse(granted)


async def pending_poll(rec: dict) -> JSONResponse:
    family = rec["family"]
    if rec.get("decision") == "approved":
        if rec.get("pending_kind") == "connection":
            handle = rec["handle"]
            identity = rec["contract"]["_identity"]
            # A previously revoked agent that she admits again starts a new
            # relationship, but not a clean record: `standing.never_revoked`
            # would be worthless if a revocation could be cleared by asking a
            # second time.
            prior = await st(rec["owner"]).connection(handle) or {}
            await st(rec["owner"]).put_connection({
                "handle": handle,
                "identity": identity,
                "label": identity.get("sub") or f"Agent {handle[4:12]}",
                "status": "active",
                "first_seen": utcstamp(),
                "last_access": None,
                # Which tiers this connection has actually been granted at.
                # Being admitted is not the same as being admitted everywhere:
                # `standing.first_at_tier` reads this, so the first request at
                # each new tier comes back to her.
                "tiers_granted": [],
                # Tiers she personally said yes at. Kept separate from the
                # line above because only this one may ever relax a rule.
                "tiers_approved": [],
                "revocations": int(prior.get("revocations", 0)),
            })
            event("connection.approved", corr=family, handle=handle)
            await ledger_add(rec["owner"], "connected", family, {"identity": identity},
                             handle=handle)
        event("policy.evaluated", corr=family, result="owner-approved", tier=rec["tier"])
        # Tier policy still applies after connection: an ask-me tier needs its
        # per-operation approval, which Alice's single tap covered only if this
        # negotiation carried the operation (it did — the contract binds it).
        if handle := rec.get("handle"):
            await st(rec["owner"]).note_tier_grant(handle, rec["tier"])
            # She answered this one herself. That is the only kind of fact a
            # relaxation is allowed to rest on.
            await st(rec["owner"]).note_tier_approval(handle, rec["tier"])
        granted = await issue_rpt(rec, rec["contract_hash"], rec["signer_jwk"],
                                  rec["contract"].get("operation"))
        await close_negotiation(rec)
        return JSONResponse(granted)
    if rec.get("decision") == "denied":
        event("policy.evaluated", corr=family, result="owner-denied", tier=rec["tier"])
        await close_negotiation(rec)
        return JSONResponse({"error": "request_denied"}, status_code=403)
    rotated = await new_ticket(rec)  # still pending: rotate and keep waiting
    return JSONResponse(
        {"error": "request_submitted", "ticket": rotated, "interval": POLL_INTERVAL},
        status_code=403,
    )


# --- Owner API (the portal's backend) ----------------------------------------


@app.get("/owner/pending")
async def owner_pending(request: Request) -> list:
    owner = await require_owner(request)
    return [
        {
            "family": rec["family"],
            "kind": rec.get("pending_kind", "operation"),
            "tier": rec["tier"],
            "purpose": rec["contract"]["purpose"],
            "operation": rec["contract"].get("operation"),
            "reason": rec["contract"].get("reason"),
            "mission": rec["contract"].get("mission"),
            "prohibited": rec["contract"]["prohibited"],
            "enforced": rec.get("template", {}).get("enforced") or {},
            "identity": rec["contract"]["_identity"],
            "handle": rec.get("handle"),
            "assurance": rec.get("assurance", {}),
            "assurance_notes": rec.get("assurance_notes", []),
            "because": rec.get("because", []),
        }
        for rec in await st(owner).pending_negotiations()
    ]


@app.post("/owner/pending/{family}/decision")
async def owner_decision(family: str, request: Request) -> dict:
    owner = await require_owner(request)
    body = await request.json()
    decision = body.get("decision")
    if decision not in ("approved", "denied"):
        raise HTTPException(status_code=400, detail="decision must be approved|denied")
    # The store's guard, not a read-then-write here: a double tap, or two
    # portals open on the same request, must produce one decision.
    if not await st(owner).decide(family, decision):
        raise HTTPException(status_code=404, detail="no pending negotiation for that family")
    event("owner.decision", corr=family, decision=decision)
    # Read after the decision, not before: `decide` is the guard, and doing the
    # lookup first would invite someone to move the guard behind it. The
    # negotiation survives its own decision — `close_negotiation` runs when the
    # grant is issued — so the handle it was pending under is still there.
    pended = await st(owner).negotiation(family)
    # Record both outcomes: "what did I decide" is an audit question, and a
    # denial is as much a decision as an approval.
    await ledger_add(owner, "approved" if decision == "approved" else "denied", family,
                     {"decision": decision, "tier": (pended or {}).get("tier")},
                     handle=(pended or {}).get("handle"))
    await owner_notify(owner, {"type": "decided", "family": family, "decision": decision})
    return {"family": family, "decision": decision}


@app.get("/owner/resource-servers")
async def owner_resource_servers(request: Request) -> list:
    """The resource servers Alice has authorized to use her Protection API —
    the other standing relationship her AS holds, beside agent connections."""
    owner = await require_owner(request)
    return [
        {"client_id": cid, **{k: v for k, v in rs.items() if k != "secret"}}
        for cid, rs in (await st(owner).resource_servers()).items()
    ]


@app.post("/rs/register")
async def rs_register(request: Request) -> JSONResponse:
    """A resource server introduces itself to an owner's authority.

    It arrives holding nothing this server issued. What it presents is a
    signature over the request, made with a key published at the origin of
    the resource it claims to serve — so the credential is the origin, and
    verifying it is a fetch this server performs rather than a claim it is
    handed.

    Success is 202, not 200. A verified signature establishes *who is asking*
    and nothing else; the answer is hers, and until she gives it the record
    sits in her resource-server registry marked pending and opens no door. A
    resource server she has revoked may ask again — and lands in the same
    pending state, because a second request is not a reversal of her first
    decision.
    """
    body = await request.body()
    try:
        req = json.loads(body or b"{}")
    except ValueError:
        return JSONResponse({"error": "invalid_request"}, status_code=400)

    owner = (req.get("owner") or DEFAULT_OWNER).strip()
    if not serves(owner):
        return JSONResponse(
            {"error": "invalid_request",
             "error_description": "this authorization server serves a different owner"},
            status_code=403)
    # An owner exists because a person set one up. A resource server naming a
    # string must not be able to bring one into being, complete with default
    # policy and terms — on a single-owner server `serves` already settles it,
    # but on one holding many this is the check that does. Before the fetch
    # below, so an unknown owner costs no outbound request either.
    if SERVED_OWNER is None and owner not in await STORE.owners():
        return JSONResponse(
            {"error": "invalid_request",
             "error_description": "no such owner at this authorization server"},
            status_code=403)

    resource_uri = (req.get("resource_uri") or "").strip()
    if not await verify_resource_server_signature(request, body, resource_uri):
        event("resource_server.registration_refused", owner=owner,
              resource_uri=resource_uri,
              reason="no signature from a key published at that origin")
        return JSONResponse(
            {"error": "invalid_client",
             "error_description":
                 "register by signing with a key published at the origin of "
                 "the resource you claim to serve"},
            status_code=401)

    client_id = _origin_of(resource_uri)
    await ensure_owner(owner)
    existing = await st(owner).resource_server(client_id)
    if existing and existing.get("status") == "active":
        # Already hers. Saying so beats re-pending a working relationship
        # every time the resource server restarts.
        return JSONResponse({"client_id": client_id, "status": "active"})

    await st(owner).put_resource_server(client_id, {
        "secret": "",
        # Stored raw and capped. This is the one field on the record the
        # registering side authors, so it is the one a surface rendering it
        # has to escape — see the portal's `esc`. Escaping it here would put
        # markup in the store, double-escape wherever that is done properly,
        # and let the cap cut an entity in half.
        "name": str(req.get("name") or client_id)[:120],
        "status": "pending",
        "consented": None,
        "last_pat_issued": (existing or {}).get("last_pat_issued"),
        "resource_uri": resource_uri,
        "registered": utcstamp(),
        # How it will authenticate from here on. Recorded because the two are
        # not interchangeable: a seeded relationship holds a shared secret,
        # and this one holds nothing at all.
        "auth": "origin_signature",
    })
    event("resource_server.registered", owner=owner, client_id=client_id,
          resource_uri=resource_uri, status="pending",
          previously=(existing or {}).get("status"))
    # Only on a change of state. A resource server she has withdrawn will keep
    # asking for as long as traffic keeps arriving for her, and each of those
    # is the same question she has already been asked.
    if (existing or {}).get("status") != "pending":
        await owner_notify(owner, {"type": "resource_server_pending",
                                   "client_id": client_id,
                                   "resource_uri": resource_uri})
    return JSONResponse(
        {"client_id": client_id, "status": "pending",
         "error": "authorization_pending",
         "error_description": "the owner has been asked"},
        status_code=202)


def _origin_of(url: str) -> str:
    from urllib.parse import urlparse

    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


@app.post("/owner/resource-servers/decision")
async def owner_resource_server_decision(request: Request) -> dict:
    """Her answer about a resource server, in the same shape as her answer
    about an agent's first contact — because it is the same kind of question.

    The client_id is in the body rather than the path. It is an https URL for
    anything that registered itself, and a URL inside a path survives neither
    percent-decoding nor a proxy that normalises `//`.
    """
    owner = await require_owner(request)
    body = await request.json()
    client_id = (body.get("client_id") or "").strip()
    decision = body.get("decision")
    if decision == "approved":
        if not await st(owner).approve_resource_server(client_id, utcstamp()):
            raise HTTPException(
                status_code=404,
                detail="no pending registration for that resource server")
        status = "active"
    elif decision == "revoked":
        if not await st(owner).revoke_resource_server(client_id):
            raise HTTPException(status_code=404, detail="unknown resource server")
        status = "revoked"
    else:
        raise HTTPException(status_code=400,
                            detail="decision must be approved or revoked")
    event(f"resource_server.{decision}", client_id=client_id)
    await ledger_add(owner, "approved" if status == "active" else "revoked",
                     "-", {"resource_server": client_id})
    await owner_notify(owner, {"type": "resource_server_decided",
                               "client_id": client_id, "status": status})
    return {"client_id": client_id, "status": status}


@app.post("/owner/resource-servers/{client_id}/revoke")
async def owner_revoke_resource_server(client_id: str, request: Request) -> dict:
    owner = await require_owner(request)
    if not await st(owner).revoke_resource_server(client_id):
        raise HTTPException(status_code=404, detail="unknown resource server")
    event("resource_server.revoked", client_id=client_id)
    await ledger_add(owner, "revoked", "-", {"resource_server": client_id})
    return {"client_id": client_id, "status": "revoked"}


@app.get("/owner/operators")
async def owner_operators(request: Request) -> list:
    """Operators she has met, and whether she has shut any of them out.

    Assembled from her connections rather than kept as its own registry: an
    operator is not a thing she onboards, it is a name that turned up attached
    to agents she has already decided about.
    """
    owner = await require_owner(request)
    blocked = await st(owner).blocked_operators()
    owned = await st(owner).owned_operators()
    seen: dict[str, dict] = {}
    for conn in await st(owner).connections():
        origin = operator_origin(conn.get("identity") or {})
        if origin is None:
            continue
        meta = (conn["identity"].get("client_metadata") or {})
        row = seen.setdefault(origin, {
            "origin": origin, "name": meta.get("client_name") or origin,
            "agents": 0, "active": 0, "blocked": origin in blocked,
            "blocked_at": (blocked.get(origin) or {}).get("blocked_at"),
            # Annotated on read rather than stored on the connection: she can
            # disclaim an origin at any moment, and a copy written when the
            # agent connected would go on saying it was hers.
            "mine": origin in owned,
            "claimed_at": (owned.get(origin) or {}).get("claimed_at"),
        })
        row["agents"] += 1
        row["active"] += 1 if conn.get("status") == "active" else 0
    for origin, rec in blocked.items():          # blocked before ever connecting
        seen.setdefault(origin, {"origin": origin, "name": origin, "agents": 0,
                                 "active": 0, "blocked": True,
                                 "blocked_at": rec.get("blocked_at"),
                                 "mine": origin in owned, "claimed_at": None})
    for origin, rec in owned.items():            # claimed before ever connecting
        row = seen.setdefault(origin, {"origin": origin, "name": origin,
                                       "agents": 0, "active": 0,
                                       "blocked": False, "blocked_at": None,
                                       "mine": True, "claimed_at": None})
        row["mine"] = True
        row["claimed_at"] = rec.get("claimed_at")
    return sorted(seen.values(), key=lambda r: r["origin"])


@app.post("/owner/operators/claim")
async def owner_claim_operator(request: Request) -> dict:
    """Say an origin is hers, so agents it vouches for are her own.

    The mirror of blocking, and deliberately not its equal. A block may rest on
    what an agent says about itself, because the worst a liar achieves is a
    refusal. This may not: it is the only thing in the profile that lets an
    agent meet *less* friction, so the claim alone is never enough. An agent is
    first-party only when this origin is claimed here **and** her authority
    found that agent's signing key in the operator's own key directory.

    Claiming an origin she does not control therefore buys nothing at all —
    she cannot publish keys there, so no agent of theirs can reach the second
    half. That is worth knowing before treating this as dangerous.
    """
    owner = await require_owner(request)
    origin = ((await request.json()).get("origin") or "").strip().rstrip("/")
    if not origin.startswith("https://"):
        raise HTTPException(status_code=400,
                            detail="an operator is named by its https origin")
    await st(owner).claim_operator(origin, utcstamp())
    event("operator.claimed", operator=origin)
    await ledger_add(owner, "claimed", "-", {"operator": origin})
    await owner_notify(owner, {"type": "decided", "family": "-", "decision": "claimed"})
    return {"origin": origin, "status": "mine"}


@app.post("/owner/operators/disclaim")
async def owner_disclaim_operator(request: Request) -> dict:
    """Stop treating an origin as hers.

    Takes effect on the next request rather than retroactively, and does not
    revoke anything. What the relaxation bought was fewer interruptions, not
    access she had not already granted, so there is nothing here to claw back —
    connections stay, grants stay, and the next negotiation simply faces the
    policy it would have faced anyway.
    """
    owner = await require_owner(request)
    origin = ((await request.json()).get("origin") or "").strip().rstrip("/")
    dropped = await st(owner).disclaim_operator(origin)
    event("operator.disclaimed", operator=origin, was_claimed=dropped)
    if dropped:
        await ledger_add(owner, "disclaimed", "-", {"operator": origin})
    return {"origin": origin, "status": "not-mine", "was_claimed": dropped}


@app.post("/owner/operators/block")
async def owner_block_operator(request: Request) -> dict:
    """Shut out every agent of one operator, in one action.

    This is the reason the pend queue's second lane is keyed on an operator
    having *published this agent's key*: it makes a flood attributable, and an
    attributable flood is one she can answer here rather than one connection at
    a time.

    Blocking revokes what is already connected, in the same step. A block that
    stopped new requests and left live grants alone would leave her believing
    she had shut a door that was still open.
    """
    owner = await require_owner(request)
    origin = ((await request.json()).get("origin") or "").strip().rstrip("/")
    if not origin.startswith("https://"):
        raise HTTPException(status_code=400,
                            detail="an operator is named by its https origin")
    await st(owner).block_operator(origin, utcstamp())
    revoked, tokens = 0, 0
    for conn in await st(owner).connections():
        if conn.get("status") != "active":
            continue
        if operator_origin(conn.get("identity") or {}) != origin:
            continue
        killed = await st(owner).revoke_connection(conn["handle"])
        if killed is not None:
            revoked, tokens = revoked + 1, tokens + killed
    event("operator.blocked", operator=origin, connections_revoked=revoked,
          rpts_deactivated=tokens)
    await ledger_add(owner, "revoked", "-", {"operator": origin,
                                      "connections_revoked": revoked,
                                      "rpts_deactivated": tokens})
    await owner_notify(owner, {"type": "decided", "family": "-", "decision": "revoked"})
    return {"origin": origin, "connections_revoked": revoked,
            "rpts_deactivated": tokens}


@app.post("/owner/operators/unblock")
async def owner_unblock_operator(request: Request) -> dict:
    """Let them ask again. Deliberately not the reverse of blocking: the
    connections it revoked stay revoked, so unblocking restores the right to
    negotiate rather than the access that was withdrawn."""
    owner = await require_owner(request)
    origin = ((await request.json()).get("origin") or "").strip().rstrip("/")
    if not await st(owner).unblock_operator(origin):
        raise HTTPException(status_code=404, detail="that operator is not blocked")
    event("operator.unblocked", operator=origin)
    return {"origin": origin, "blocked": False}


@app.get("/owner/resources")
async def owner_resources(request: Request) -> list:
    """The owner's view of what her AS is protecting: every registered
    resource, joined with the tier whose policy governs it. This is the
    surface Alice attaches policy to before any agent has ever called."""
    owner = await require_owner(request)
    tiers = await st(owner).tiers()
    out = []
    for rid, desc in RESOURCES.items():
        tier_id, tier = policy.tier_for_resource(tiers, rid)
        out.append({
            "_id": rid,
            "name": desc.get("name") or rid,
            "type": desc.get("type"),
            "resource_scopes": desc["resource_scopes"],
            "tier": tier_id,
            "tier_name": tier["name"] if tier else None,
            "ask_me": tier["ask_me"] if tier else None,
            "registered_via": desc.get("registered_via", "push"),
        })
    return sorted(out, key=lambda r: r["_id"])


@app.get("/owner/policies")
async def owner_policies(request: Request) -> dict:
    owner = await require_owner(request)
    return await st(owner).tiers()


@app.get("/owner/policy-vocabulary")
async def owner_policy_vocabulary(request: Request) -> list:
    """The conditions her rules may use, and which of them may relax.

    Served so her portal can offer them as choices. One source of truth: a
    surface that hard-coded this list would eventually offer her something
    this server rejects.
    """
    await require_owner(request)
    return policy.vocabulary()


@app.post("/owner/policies")
async def owner_create_policy(request: Request) -> dict:
    """Alice writing a new tier: her terms, and which of her resources they
    govern.

    The resources have to be ones her authority already protects. That is not
    a limitation so much as the direction of the whole design — a resource
    server registers what it holds, and she attaches policy to it. She cannot
    write terms over something nobody is protecting.
    """
    owner = await require_owner(request)
    spec = await request.json()
    tier_id = (spec.get("id") or "").strip()
    try:
        tier = policy.new_tier(tier_id, spec, await st(owner).tiers(), set(RESOURCES))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        created = await st(owner).create_tier(tier_id, tier)
    except KeyError:
        raise HTTPException(status_code=409,
                            detail=f"there is already a tier called {tier_id!r}")
    event("policy.created", tier=tier_id, template_id=created["terms"]["template_id"],
          resources=created["resources"])
    await publish_terms(owner, tier_id, created)
    return created


@app.delete("/owner/policies/{tier_id}")
async def owner_delete_policy(tier_id: str, request: Request) -> dict:
    """Remove a tier. Its resources become ungoverned, and an ungoverned
    resource is *denied* — so this withdraws access rather than widening it,
    which is the only safe direction for a destructive edit to fail in.

    Published terms are not deleted with it. An agreement signed against them
    stays checkable, which is the whole reason those documents are versioned
    and persistent.
    """
    owner = await require_owner(request)
    tiers = await st(owner).tiers()
    orphaned = list(tiers.get(tier_id, {}).get("resources") or [])
    if not await st(owner).delete_tier(tier_id):
        raise HTTPException(status_code=404, detail="unknown tier")
    event("policy.deleted", tier=tier_id, ungoverned=orphaned)
    return {"deleted": tier_id, "ungoverned": orphaned}


@app.put("/owner/policies/{tier_id}")
async def owner_update_policy(tier_id: str, request: Request) -> dict:
    owner = await require_owner(request)
    patch = await request.json()
    try:
        updated = await st(owner).update_tier(tier_id, patch)
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown tier")
    except ValueError as exc:
        # A rule that could widen access on evidence the agent controls, or
        # one whose argument will not parse. Her editor shows this text, so it
        # has to say what is wrong rather than that something is.
        raise HTTPException(status_code=400, detail=str(exc))
    event("policy.updated", tier=tier_id, template_id=updated["terms"]["template_id"])
    # Publish the new version immediately so its terms URI dereferences from
    # the moment it exists; earlier versions remain served (persistent record).
    await publish_terms(owner, tier_id, updated)
    return updated


@app.get("/owner/connections")
async def owner_connections(request: Request) -> list:
    owner = await require_owner(request)
    return await st(owner).connections()


@app.post("/owner/connections/{handle}/revoke")
async def owner_revoke_connection(handle: str, request: Request) -> dict:
    owner = await require_owner(request)
    # Deactivating the connection and burning the tokens issued under it is
    # one step, not two: a revocation that flipped the connection and then
    # failed would leave the agent holding exactly the authority Alice had
    # just withdrawn.
    killed = await st(owner).revoke_connection(handle)
    if killed is None:
        raise HTTPException(status_code=404, detail="unknown connection")
    event("connection.revoked", handle=handle, rpts_deactivated=killed)
    await ledger_add(owner, "revoked", "-", {"rpts_deactivated": killed}, handle=handle)
    await owner_notify(owner, {"type": "decided", "family": "-", "decision": "revoked"})
    return {"handle": handle, "status": "revoked", "rpts_deactivated": killed}


@app.get("/owner/ledger")
async def owner_ledger(request: Request) -> list:
    """The record, or one agent's part of it.

    `?handle=` is what turns a list of negotiations into a trajectory: every
    promise that agent made, every decision she took about it, and everything
    it actually touched, in order."""
    owner = await require_owner(request)
    return await st(owner).ledger(request.query_params.get("handle") or None)


@app.get("/owner/events")
async def owner_events(request: Request):
    """SSE stream for the portal: pending approvals arriving, decisions landing.

    The subscription is the store's, not this process's. Alice's browser
    holds one stream against whichever replica answered her request, while
    the approval she is waiting for may be produced by any of them — so the
    fan-out has to be a property of the state, not of the process that
    happens to be serving her.
    """
    owner = await require_owner(request)
    from sse_starlette.sse import EventSourceResponse

    async def stream():
        async for item in st(owner).subscribe():
            yield {"event": item["type"], "data": json.dumps(item)}

    return EventSourceResponse(stream())
