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
OWNER_USERNAME = os.environ.get("UMA_AS_OWNER", "alice")
OWNER_AUDIENCES = set(
    os.environ.get("UMA_AS_OWNER_CLIENTS", "alice-portal").split(","))

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


async def ledger_add(kind: str, family: str, entry: dict,
                     handle: str | None = None) -> None:
    """One decision record. `handle` names the agent it was about, where
    there is one — see Store.ledger_add for why it is not part of `entry`."""
    await STORE.ledger_add(kind, family, utcstamp(), entry, handle)


async def owner_notify(payload: dict) -> None:
    await STORE.notify(payload)


async def new_ticket(record: dict) -> str:
    """Mint a ticket and index it to the record's family. The record itself
    stays addressable by family throughout."""
    ttl = PENDING_TTL if record.get("state") == "awaiting-owner" else TICKET_TTL
    return await STORE.mint_ticket(record, ttl)


async def close_negotiation(rec: dict | None) -> None:
    if rec:
        await STORE.close_negotiation(rec.get("family"))


# --- Basics -----------------------------------------------------------------


@app.on_event("startup")
async def open_store() -> None:
    await STORE.start()


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


async def publish_terms(tier_id: str, tier: dict) -> str:
    """Archive the current version of a tier's terms as a served document.
    Idempotent per template_id (a version's content never changes)."""
    template_id = tier["terms"]["template_id"]
    if await STORE.terms_doc(template_id) is None:
        await STORE.publish_terms({
            "template_id": template_id,
            "terms_uri": terms_uri(template_id),
            "proffered_by": ISSUER,
            "name": tier["name"],
            "tier": tier_id,
            **{k: v for k, v in tier["terms"].items() if k != "template_id"},
            "enforced": policy.enforced_prohibitions(tier),
            "published_at": utcstamp(),
        })
        event("terms.published", template_id=template_id, tier=tier_id)
    return terms_uri(template_id)


@app.on_event("startup")
async def publish_initial_terms() -> None:
    for tier_id, tier in (await STORE.tiers()).items():
        await publish_terms(tier_id, tier)


@app.get("/terms")
async def terms_index() -> dict:
    return {
        "proffered_by": ISSUER,
        "terms": await STORE.terms_docs(),
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


@app.get("/terms/{template_id:path}")
async def terms_document(template_id: str, request: Request, format: str = None):
    doc = await STORE.terms_doc(template_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="unknown terms document")
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


async def issue_pat(client_id: str) -> dict:
    """Mint a PAT: an OAuth access token for the Protection API, carrying
    the owner it acts about (FedAuthz's RO context) and the RS it was
    issued to."""
    exp = int(now()) + PAT_TTL
    token = jwt.encode(
        {
            "iss": ISSUER,
            "sub": OWNER_USERNAME,
            "azp": client_id,
            "scope": "uma_protection",
            "jti": f"pat_{uuid.uuid4().hex[:12]}",
            "exp": exp,
        },
        SIGNING_KEY,
        algorithm="EdDSA",
        headers={"typ": "pat+jwt", "kid": KID},
    )
    await STORE.touch_pat(client_id, utcstamp())
    event("pat.issued", client_id=client_id, expires_in=PAT_TTL)
    return {"access_token": token, "token_type": "Bearer",
            "expires_in": PAT_TTL, "scope": "uma_protection"}


async def require_pat(request: Request) -> None:
    """The Protection API takes the PAT this AS issued — verified, scoped,
    and revocable via the owner's resource-server registry."""
    try:
        claims = jwt.decode(_bearer(request), SIGNING_KEY.public_key(),
                            algorithms=["EdDSA"], issuer=ISSUER,
                            options={"verify_aud": False})
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401,
                            detail=f"protection API requires a valid PAT: {exc}")
    if "uma_protection" not in claims.get("scope", "").split():
        raise HTTPException(status_code=403, detail="PAT lacks uma_protection scope")
    rs = await STORE.resource_server(claims.get("azp", ""))
    if rs is None or rs["status"] != "active":
        raise HTTPException(status_code=401,
                            detail="the owner has revoked this resource server")


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


async def require_owner_signature(request: Request) -> None:
    """The owner signs her own request, with her own key.

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


async def require_owner(request: Request) -> None:
    """Whoever is calling the owner API has to be the owner.

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

    last: HTTPException | None = None
    for mode in OWNER_AUTH:
        try:
            result = VERIFY_OWNER[mode](request)
            if hasattr(result, "__await__"):
                await result
            return
        except HTTPException as exc:
            last = exc
    raise last or HTTPException(status_code=401, detail="owner authentication failed")


def require_owner_oidc(request: Request) -> None:
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
    if claims.get("preferred_username") != OWNER_USERNAME:
        raise HTTPException(status_code=403,
                            detail="this authorization server serves a different owner")



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
            for client_id, rs in (await STORE.resource_servers()).items():
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
    await require_pat(request)
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
        for client_id, rs in (await STORE.resource_servers()).items():
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
    rec = await STORE.rpt(claims.get("jti", ""))
    if rec is None:
        return claims, None, "unknown_token"
    if (conn := await STORE.connection(rec.get("handle") or "")) is not None:
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

    if rec.get("handle"):
        await STORE.touch_connection(rec["handle"], utcstamp())
    # Consumption is no longer done here by default: the PEP has not yet
    # verified proof-of-possession at this point, so burning the token now
    # lets an unsigned replay destroy a grant the owner just approved. The
    # PEP calls /consume once every check has passed. The parameter is kept
    # for the single-shot case where a caller has already verified.
    if claims.get("single_use") and consume == "true":
        if await STORE.consume_rpt(claims.get("jti", "")) is None:
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
    await require_pat(request)
    claims, rec, err = await _decode_rpt(token)
    if err:
        return {"consumed": False, "error": err}
    if not claims.get("single_use"):
        return {"consumed": False, "error": "not_single_use"}
    family = await STORE.consume_rpt(claims.get("jti", ""))
    if family is None:
        return {"consumed": False, "error": "already_consumed"}
    event("rpt.consumed", corr=family, jti=claims.get("jti", ""))
    return {"consumed": True, "family": family}


@app.post("/audit/access")
async def audit_access(request: Request) -> dict:
    """The PEP reports allowed calls so the ledger's 'touched' column is
    grounded in enforcement, not client claims."""
    await require_pat(request)
    body = await request.json()
    family = body.get("family", "?")
    # The enforcement point reports what it allowed; the authority decides
    # whose it was, and against which of her tiers. It is never told the handle — it enforces for a policy it
    # cannot read, and the connection is the owner's record, not its.
    grant = await STORE.grant_for_family(family)
    await ledger_add("touched", family, {
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
            "terms_uri": await publish_terms(tier_id, tier),
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


def standing_facts(conn: dict | None, tier_id: str,
                   trajectory: dict | None = None) -> dict:
    """What Alice's own authority has seen of this agent.

    Kept apart from assurance because only these may relax a requirement —
    they are the one kind of evidence here that the requesting side had no
    hand in producing. `age_seconds` is None when she has never met it, which
    the conditions read as "younger than everything, older than nothing".

    `trajectory` is read from her ledger by the caller and passed in, so
    `policy.evaluate` stays a pure function of a dict and can be tested with
    no store at all.
    """
    trajectory = trajectory or {"denials": 0, "tiers": []}
    if conn is None or conn.get("status") != "active":
        return {"active": False, "age_seconds": None, "first_at_tier": True,
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
        "first_at_tier": tier_id not in (conn.get("tiers_granted") or []),
        # What Alice decided. Only these may lower a requirement, so they are
        # kept apart from the line above even though both are her side's.
        "approved_tiers": list(conn.get("tiers_approved") or []),
        "revocations": int(conn.get("revocations", 0)),
        # What it has been doing lately. Restrictions only — see policy.py.
        "trajectory": trajectory,
    }


async def trajectory_facts(handle: str) -> dict:
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
    return await STORE.trajectory(handle, since)


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
    tier = (await STORE.tiers())[rec["tier"]]
    exp = int(now()) + min(3600, tier["terms"]["expires_in"])
    jti = f"rpt_{uuid.uuid4().hex[:12]}"
    claims = {
        "iss": ISSUER,
        "sub": rec.get("agent_sub", "aauth:pseudonymous-agent"),
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
    await STORE.record_rpt(jti, family, handle, claims.get("operation"),
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
async def token(
    grant_type: str = Form(...),
    ticket: str = Form(None),
    claim_token: str = Form(None),
    claim_token_format: str = Form(None),
    decline: str = Form(None),
    client_id: str = Form(None),
    client_secret: str = Form(None),
    scope: str = Form(None),
) -> JSONResponse:
    # PAT issuance: a resource server the owner has authorized exchanges its
    # client credentials for a uma_protection-scoped token (FedAuthz's PAT).
    if grant_type == "client_credentials":
        rs = await STORE.resource_server(client_id or "")
        if rs is None or not secrets.compare_digest(client_secret or "", rs["secret"]):
            return JSONResponse({"error": "invalid_client"}, status_code=401)
        if rs["status"] != "active":
            return JSONResponse(
                {"error": "access_denied",
                 "error_description": "the owner has revoked this resource server"},
                status_code=403)
        if scope != "uma_protection":
            return JSONResponse({"error": "invalid_scope"}, status_code=400)
        return JSONResponse(await issue_pat(client_id))

    if grant_type != "urn:ietf:params:oauth:grant-type:uma-ticket":
        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)

    await STORE.reap_expired()
    rec = await STORE.consume_ticket(ticket)
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
        await ledger_add("refused", family, {
            "tier": rec.get("tier"),
            "terms_uri": rec.get("template", {}).get("terms_uri"),
        })
        await close_negotiation(rec)
        return JSONResponse({"error": "request_denied"}, status_code=403)

    # Pending ask-me ticket being re-presented (beat 3, taking longer).
    if rec["state"] == "awaiting-owner":
        return await pending_poll(rec)

    tier_id, tier = policy.tier_for_resource(await STORE.tiers(),
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

    await ledger_add("promised", family, {
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
    conn = await STORE.connection(handle)
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
    if origin and origin in await STORE.blocked_operators():
        event("policy.evaluated", corr=family, result="operator-blocked",
              operator=origin)
        await ledger_add("refused", family, {"tier": rec["tier"],
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
        "standing": standing_facts(conn, rec["tier"],
                                   await trajectory_facts(handle)),
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
        await ledger_add("refused", family, {"tier": rec["tier"],
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
            1 for p in await STORE.pending_negotiations()
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

    await STORE.touch_connection(handle, utcstamp())
    await STORE.note_tier_grant(handle, rec["tier"])
    event("policy.evaluated", corr=family, result="auto-grant", tier=rec["tier"],
          connection=handle, because=reasons or None)
    if reasons and requirement == policy.AUTO and tier.get("ask_me"):
        # A rule she wrote lowered an ask-me tier to automatic. That is the
        # one direction worth being able to audit after the fact, so it is a
        # ledger entry and not only a log line.
        await ledger_add("relaxed", family, {"tier": rec["tier"],
                                             "because": reasons},
                         handle=handle)
    granted = await issue_rpt(rec, contract_hash, signer_jwk, None)
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
            prior = await STORE.connection(handle) or {}
            await STORE.put_connection({
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
            await ledger_add("connected", family, {"identity": identity},
                             handle=handle)
        event("policy.evaluated", corr=family, result="owner-approved", tier=rec["tier"])
        # Tier policy still applies after connection: an ask-me tier needs its
        # per-operation approval, which Alice's single tap covered only if this
        # negotiation carried the operation (it did — the contract binds it).
        if handle := rec.get("handle"):
            await STORE.note_tier_grant(handle, rec["tier"])
            # She answered this one herself. That is the only kind of fact a
            # relaxation is allowed to rest on.
            await STORE.note_tier_approval(handle, rec["tier"])
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
    await require_owner(request)
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
        for rec in await STORE.pending_negotiations()
    ]


@app.post("/owner/pending/{family}/decision")
async def owner_decision(family: str, request: Request) -> dict:
    await require_owner(request)
    body = await request.json()
    decision = body.get("decision")
    if decision not in ("approved", "denied"):
        raise HTTPException(status_code=400, detail="decision must be approved|denied")
    # The store's guard, not a read-then-write here: a double tap, or two
    # portals open on the same request, must produce one decision.
    if not await STORE.decide(family, decision):
        raise HTTPException(status_code=404, detail="no pending negotiation for that family")
    event("owner.decision", corr=family, decision=decision)
    # Read after the decision, not before: `decide` is the guard, and doing the
    # lookup first would invite someone to move the guard behind it. The
    # negotiation survives its own decision — `close_negotiation` runs when the
    # grant is issued — so the handle it was pending under is still there.
    pended = await STORE.negotiation(family)
    # Record both outcomes: "what did I decide" is an audit question, and a
    # denial is as much a decision as an approval.
    await ledger_add("approved" if decision == "approved" else "denied", family,
                     {"decision": decision, "tier": (pended or {}).get("tier")},
                     handle=(pended or {}).get("handle"))
    await owner_notify({"type": "decided", "family": family, "decision": decision})
    return {"family": family, "decision": decision}


@app.get("/owner/resource-servers")
async def owner_resource_servers(request: Request) -> list:
    """The resource servers Alice has authorized to use her Protection API —
    the other standing relationship her AS holds, beside agent connections."""
    await require_owner(request)
    return [
        {"client_id": cid, **{k: v for k, v in rs.items() if k != "secret"}}
        for cid, rs in (await STORE.resource_servers()).items()
    ]


@app.post("/owner/resource-servers/{client_id}/revoke")
async def owner_revoke_resource_server(client_id: str, request: Request) -> dict:
    await require_owner(request)
    if not await STORE.revoke_resource_server(client_id):
        raise HTTPException(status_code=404, detail="unknown resource server")
    event("resource_server.revoked", client_id=client_id)
    await ledger_add("revoked", "-", {"resource_server": client_id})
    return {"client_id": client_id, "status": "revoked"}


@app.get("/owner/operators")
async def owner_operators(request: Request) -> list:
    """Operators she has met, and whether she has shut any of them out.

    Assembled from her connections rather than kept as its own registry: an
    operator is not a thing she onboards, it is a name that turned up attached
    to agents she has already decided about.
    """
    await require_owner(request)
    blocked = await STORE.blocked_operators()
    seen: dict[str, dict] = {}
    for conn in await STORE.connections():
        origin = operator_origin(conn.get("identity") or {})
        if origin is None:
            continue
        meta = (conn["identity"].get("client_metadata") or {})
        row = seen.setdefault(origin, {
            "origin": origin, "name": meta.get("client_name") or origin,
            "agents": 0, "active": 0, "blocked": origin in blocked,
            "blocked_at": (blocked.get(origin) or {}).get("blocked_at"),
        })
        row["agents"] += 1
        row["active"] += 1 if conn.get("status") == "active" else 0
    for origin, rec in blocked.items():          # blocked before ever connecting
        seen.setdefault(origin, {"origin": origin, "name": origin, "agents": 0,
                                 "active": 0, "blocked": True,
                                 "blocked_at": rec.get("blocked_at")})
    return sorted(seen.values(), key=lambda r: r["origin"])


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
    await require_owner(request)
    origin = ((await request.json()).get("origin") or "").strip().rstrip("/")
    if not origin.startswith("https://"):
        raise HTTPException(status_code=400,
                            detail="an operator is named by its https origin")
    await STORE.block_operator(origin, utcstamp())
    revoked, tokens = 0, 0
    for conn in await STORE.connections():
        if conn.get("status") != "active":
            continue
        if operator_origin(conn.get("identity") or {}) != origin:
            continue
        killed = await STORE.revoke_connection(conn["handle"])
        if killed is not None:
            revoked, tokens = revoked + 1, tokens + killed
    event("operator.blocked", operator=origin, connections_revoked=revoked,
          rpts_deactivated=tokens)
    await ledger_add("revoked", "-", {"operator": origin,
                                      "connections_revoked": revoked,
                                      "rpts_deactivated": tokens})
    await owner_notify({"type": "decided", "family": "-", "decision": "revoked"})
    return {"origin": origin, "connections_revoked": revoked,
            "rpts_deactivated": tokens}


@app.post("/owner/operators/unblock")
async def owner_unblock_operator(request: Request) -> dict:
    """Let them ask again. Deliberately not the reverse of blocking: the
    connections it revoked stay revoked, so unblocking restores the right to
    negotiate rather than the access that was withdrawn."""
    await require_owner(request)
    origin = ((await request.json()).get("origin") or "").strip().rstrip("/")
    if not await STORE.unblock_operator(origin):
        raise HTTPException(status_code=404, detail="that operator is not blocked")
    event("operator.unblocked", operator=origin)
    return {"origin": origin, "blocked": False}


@app.get("/owner/resources")
async def owner_resources(request: Request) -> list:
    """The owner's view of what her AS is protecting: every registered
    resource, joined with the tier whose policy governs it. This is the
    surface Alice attaches policy to before any agent has ever called."""
    await require_owner(request)
    tiers = await STORE.tiers()
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
    await require_owner(request)
    return await STORE.tiers()


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
    await require_owner(request)
    spec = await request.json()
    tier_id = (spec.get("id") or "").strip()
    try:
        tier = policy.new_tier(tier_id, spec, await STORE.tiers(), set(RESOURCES))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        created = await STORE.create_tier(tier_id, tier)
    except KeyError:
        raise HTTPException(status_code=409,
                            detail=f"there is already a tier called {tier_id!r}")
    event("policy.created", tier=tier_id, template_id=created["terms"]["template_id"],
          resources=created["resources"])
    await publish_terms(tier_id, created)
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
    await require_owner(request)
    tiers = await STORE.tiers()
    orphaned = list(tiers.get(tier_id, {}).get("resources") or [])
    if not await STORE.delete_tier(tier_id):
        raise HTTPException(status_code=404, detail="unknown tier")
    event("policy.deleted", tier=tier_id, ungoverned=orphaned)
    return {"deleted": tier_id, "ungoverned": orphaned}


@app.put("/owner/policies/{tier_id}")
async def owner_update_policy(tier_id: str, request: Request) -> dict:
    await require_owner(request)
    patch = await request.json()
    try:
        updated = await STORE.update_tier(tier_id, patch)
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
    await publish_terms(tier_id, updated)
    return updated


@app.get("/owner/connections")
async def owner_connections(request: Request) -> list:
    await require_owner(request)
    return await STORE.connections()


@app.post("/owner/connections/{handle}/revoke")
async def owner_revoke_connection(handle: str, request: Request) -> dict:
    await require_owner(request)
    # Deactivating the connection and burning the tokens issued under it is
    # one step, not two: a revocation that flipped the connection and then
    # failed would leave the agent holding exactly the authority Alice had
    # just withdrawn.
    killed = await STORE.revoke_connection(handle)
    if killed is None:
        raise HTTPException(status_code=404, detail="unknown connection")
    event("connection.revoked", handle=handle, rpts_deactivated=killed)
    await ledger_add("revoked", "-", {"rpts_deactivated": killed}, handle=handle)
    await owner_notify({"type": "decided", "family": "-", "decision": "revoked"})
    return {"handle": handle, "status": "revoked", "rpts_deactivated": killed}


@app.get("/owner/ledger")
async def owner_ledger(request: Request) -> list:
    """The record, or one agent's part of it.

    `?handle=` is what turns a list of negotiations into a trajectory: every
    promise that agent made, every decision she took about it, and everything
    it actually touched, in order."""
    await require_owner(request)
    return await STORE.ledger(request.query_params.get("handle") or None)


@app.get("/owner/events")
async def owner_events(request: Request):
    """SSE stream for the portal: pending approvals arriving, decisions landing.

    The subscription is the store's, not this process's. Alice's browser
    holds one stream against whichever replica answered her request, while
    the approval she is waiting for may be produced by any of them — so the
    fan-out has to be a property of the state, not of the process that
    happens to be serving her.
    """
    await require_owner(request)
    from sse_starlette.sse import EventSourceResponse

    async def stream():
        async for item in STORE.subscribe():
            yield {"event": item["type"], "data": json.dumps(item)}

    return EventSourceResponse(stream())
