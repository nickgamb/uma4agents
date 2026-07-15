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

import policy

ISSUER = os.environ.get("UMA_AS_ISSUER", "https://alice-as.uma.lab")
KEY_PATH = os.environ.get("UMA_AS_SIGNING_KEY", "/keys/uma-as-ed25519.pem")
# The owner authenticates with her OIDC token (Keycloak); the AS validates
# it against the realm's published keys. No static owner credential exists.
OWNER_ISSUER = os.environ.get(
    "UMA_AS_OWNER_ISSUER", "https://keycloak.uma.lab/realms/alice")
OWNER_USERNAME = os.environ.get("UMA_AS_OWNER", "alice")
OWNER_AUDIENCES = set(
    os.environ.get("UMA_AS_OWNER_CLIENTS", "alice-portal").split(","))
# Resource servers Alice has authorized to use her Protection API. The PAT
# is an OAuth token this AS issues to these clients (client_credentials,
# scope uma_protection); the day-0 consent for her brokerage's gateway is
# seeded — the RS-side onboarding handshake is a finding, not a feature here.
RS_CLIENTS: dict[str, dict] = {
    os.environ.get("UMA_AS_RS_CLIENT_ID", "meridian-gateway"): {
        "secret": os.environ.get("UMA_AS_RS_CLIENT_SECRET", "gateway-dev-secret"),
        "name": "Meridian Wealth API gateway",
        "status": "active",
        "consented": "seeded at provisioning (Alice linked her brokerage)",
        "last_pat_issued": None,
        # Where the RS publishes itself — the root of declarative
        # registration (RFC 9728 metadata is derived from this identifier).
        "resource_uri": os.environ.get(
            "UMA_AS_RS_RESOURCE_URI", "https://gateway.uma.lab/mcp"),
    }
}
PAT_TTL = 3600
# push: the RS registers its resources here (classic FedAuthz /rreg).
# pull: this AS *reads* the RS's published metadata — public structure from
# the RFC 9728 document, owner-bound instances from the protected
# owner-resources endpoint — and materializes its registry from it.
REGISTRATION_MODE = os.environ.get("REGISTRATION_MODE", "push")
# The owner-proffered terms + signed agreement follow the MyTerms pattern
# (IEEE 7012): the individual proffers machine-readable terms from her own
# roster; the counterparty agrees; both sides keep a record. The URN is ours —
# a MyTerms-shaped profile for agentic access terms, not a claim of
# conformance to the IEEE document's schema.
AGREEMENT_FORMAT = "urn:uma4agents:format:myterms-agreement-v1+jws"
AGREEMENT_CLAIM = "urn:uma4agents:claim:myterms-agreement"
TICKET_TTL = 300
PENDING_TTL = 600
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
# In-memory state. TICKETS is keyed by the *current* ticket string; each
# presentation consumes it (UMA 2.0 single-use rule) and, if the negotiation
# continues, a rotated ticket inherits the same negotiation record.
# ---------------------------------------------------------------------------
RESOURCES: dict[str, dict] = {}
TICKETS: dict[str, dict] = {}
RPTS: dict[str, dict] = {}          # jti -> {consumed, operation, family, handle}
LEDGER: list[dict] = []             # promised / touched / approved entries
OWNER_QUEUE: list[asyncio.Queue] = []  # SSE subscribers (portal)
# Standing relationships: the day-1 handshake's output. Keyed by the agent's
# connection handle — the RFC 7638 JWK thumbprint for a pseudonymous agent
# (the key is the identity), issuer-qualified subject for an identified one
# (its session keys rotate; see connection_handle). An unknown agent's first
# contract commit pends as a connection request — UMA's request_submitted
# doing double duty as owner-mediated agent registration. Revocation
# deactivates live RPTs too.
CONNECTIONS: dict[str, dict] = {}


def jwk_thumbprint(jwk: dict) -> str:
    """RFC 7638 thumbprint (OKP profile)."""
    canonical = json.dumps(
        {"crv": jwk["crv"], "kty": jwk["kty"], "x": jwk["x"]},
        separators=(",", ":"), sort_keys=True,
    )
    return "jkt:" + base64.urlsafe_b64encode(
        hashlib.sha256(canonical.encode()).digest()
    ).rstrip(b"=").decode()


def ledger_add(kind: str, family: str, entry: dict) -> None:
    LEDGER.append({"kind": kind, "family": family, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **entry})


async def owner_notify(payload: dict) -> None:
    for q in list(OWNER_QUEUE):
        await q.put(payload)


def new_ticket(record: dict) -> str:
    ticket = f"tkt_{secrets.token_urlsafe(24)}"
    record["expires"] = now() + (PENDING_TTL if record.get("state") == "awaiting-owner" else TICKET_TTL)
    TICKETS[ticket] = record
    return ticket


def consume_ticket(ticket: str) -> dict | None:
    rec = TICKETS.pop(ticket or "", None)
    if not rec or rec["expires"] < now():
        return None
    return rec


# --- Basics -----------------------------------------------------------------


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "issuer": ISSUER}


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
        "resource_registration_endpoint": f"{ISSUER}/rreg",
        "jwks_uri": f"{ISSUER}/jwks",
        "terms_endpoint": f"{ISSUER}/terms",
        "grant_types_supported": ["urn:ietf:params:oauth:grant-type:uma-ticket"],
        "claim_token_formats_supported": [AGREEMENT_FORMAT],
    }


# --- Terms roster (MyTerms pattern: proffered terms are persistent documents) -

# Every version of every proffered terms document, kept dereferenceable at a
# stable URI for the life of the AS — the "persistent record of the policies
# the requesting party promises to adhere to" (2010), in MyTerms shape.
TERMS_DOCS: dict[str, dict] = {}


def terms_uri(template_id: str) -> str:
    return f"{ISSUER}/terms/{template_id}"


def publish_terms(tier_id: str, tier: dict) -> str:
    """Archive the current version of a tier's terms as a served document.
    Idempotent per template_id (a version's content never changes)."""
    template_id = tier["terms"]["template_id"]
    if template_id not in TERMS_DOCS:
        TERMS_DOCS[template_id] = {
            "template_id": template_id,
            "terms_uri": terms_uri(template_id),
            "proffered_by": ISSUER,
            "name": tier["name"],
            "tier": tier_id,
            **{k: v for k, v in tier["terms"].items() if k != "template_id"},
            "published_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        event("terms.published", template_id=template_id, tier=tier_id)
    return terms_uri(template_id)


@app.on_event("startup")
async def publish_initial_terms() -> None:
    for tier_id, tier in policy.tiers().items():
        publish_terms(tier_id, tier)


@app.get("/terms")
async def terms_index() -> dict:
    return {
        "proffered_by": ISSUER,
        "terms": sorted(TERMS_DOCS.values(), key=lambda d: d["template_id"]),
    }


def terms_as_html(doc: dict) -> str:
    """The plain-language representation IEEE 7012 (4.4.1) requires the terms
    themselves to carry — same URI as the machine-readable form."""
    prohibited = "".join(f"<li>{p}</li>" for p in doc.get("prohibited", []))
    scopes = ", ".join(doc.get("scope", []))
    hours = round(doc.get("expires_in", 0) / 3600, 1)
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>{doc['name']} — {doc['template_id']}</title>
<style>body{{background:#0b0e14;color:#e6e9f0;font-family:system-ui;max-width:640px;
margin:3rem auto;padding:0 1rem;line-height:1.6}}h1{{font-size:1.3rem}}
code{{background:#161b26;padding:2px 7px;border-radius:5px}}
.k{{color:#8a93a8}}li{{margin:.2rem 0}}</style></head><body>
<h1>{doc['name']}</h1>
<p class="k">Terms <code>{doc['template_id']}</code>, proffered by
<code>{doc['proffered_by']}</code>, published {doc['published_at']}.</p>
<p>The owner of these accounts offers access on the following terms. By
signing an agreement that names this document, you accept all of them.</p>
<ul>
<li><b>Purpose</b> — access is granted only for: {doc['purpose']}.</li>
<li><b>What you may access</b> — {scopes}.</li>
<li><b>How long</b> — access expires {doc['expires_in']} seconds
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
    doc = TERMS_DOCS.get(template_id)
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


def issue_pat(client_id: str) -> dict:
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
    RS_CLIENTS[client_id]["last_pat_issued"] = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    event("pat.issued", client_id=client_id, expires_in=PAT_TTL)
    return {"access_token": token, "token_type": "Bearer",
            "expires_in": PAT_TTL, "scope": "uma_protection"}


def require_pat(request: Request) -> None:
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
    rs = RS_CLIENTS.get(claims.get("azp", ""))
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
        meta = client.get(f"{OWNER_ISSUER}/.well-known/openid-configuration")
        meta.raise_for_status()
        jwks = client.get(meta.json()["jwks_uri"])
        jwks.raise_for_status()
    keys = jwks.json()["keys"]
    _OWNER_KEYS_CACHE[OWNER_ISSUER] = (now() + JWKS_CACHE_TTL, keys)
    return keys


def require_owner(request: Request) -> None:
    """The owner API takes Alice's own OIDC access token, validated against
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


# --- Declarative registration (pull mode) -------------------------------------


def well_known_prm_url(resource_uri: str) -> str:
    from urllib.parse import urlparse

    u = urlparse(resource_uri)
    return (f"{u.scheme}://{u.netloc}"
            f"/.well-known/oauth-protected-resource{u.path.rstrip('/')}")


def pull_registrations(client_id: str) -> int:
    """Read the RS's published metadata and materialize the registry.

    1. Fetch the public RFC 9728 document (TLS-anchored) and verify its
       signed_metadata against the resource's jwks_uri — the pulled copy is
       attributable, not just transport-secure.
    2. Query the protected owner-resources endpoint it advertises, signing
       the request with this AS's key (RFC 9421) — "protected webfinger":
       the RS serves the owner-bound instances only to her AS.
    """
    import httpx

    from uma4a_http_sig import sign as http_sign

    rs = RS_CLIENTS[client_id]
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
    if REGISTRATION_MODE != "pull":
        return
    import asyncio

    async def attempt_loop():
        for _ in range(60):
            for client_id in RS_CLIENTS:
                try:
                    # Off the event loop: the RS authenticates this AS's
                    # signed query by fetching *our* JWKS, so the pull and
                    # the verification form a call cycle — a blocking pull
                    # deadlocks a single-threaded AS. (Finding: pull-model
                    # verification must tolerate a live back-call, or keys
                    # must be cached ahead of need.)
                    await asyncio.to_thread(pull_registrations, client_id)
                    return
                except Exception as exc:
                    event("resources.pull_retry", client_id=client_id,
                          error=str(exc)[:200])
            await asyncio.sleep(2)
        event("resources.pull_failed", note="lazy pull on first /perm remains")

    asyncio.create_task(attempt_loop())


# --- Protection API (gateway-side, FedAuthz shape) ---------------------------


def resource_description(body: dict) -> dict:
    """Validate and normalize a FedAuthz §3 resource description."""
    scopes = body.get("resource_scopes")
    if not isinstance(scopes, list) or not scopes or not all(
        isinstance(s, str) and s for s in scopes
    ):
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_request",
                    "error_description": "resource_scopes (non-empty list) is required"},
        )
    return {
        "resource_scopes": scopes,
        "name": body.get("name"),
        "type": body.get("type"),
        "icon_uri": body.get("icon_uri"),
        "description": body.get("description"),
    }


def reject_push() -> None:
    """In pull mode the registry is materialized from what the RS publishes;
    accepting pushes too would leave two writers and no single truth."""
    if REGISTRATION_MODE == "pull":
        raise HTTPException(
            status_code=405,
            detail={"error": "registration_is_declarative",
                    "error_description": "this AS pulls the RS's published "
                    "metadata; update the published documents instead"})


@app.post("/rreg")
async def register_resource(request: Request) -> JSONResponse:
    require_pat(request)
    reject_push()
    body = await request.json()
    desc = resource_description(body)
    rid = body.get("_id") or f"res_{uuid.uuid4().hex[:8]}"
    created = rid not in RESOURCES
    RESOURCES[rid] = desc
    event("resource.registered", resource_id=rid, scopes=desc["resource_scopes"],
          created=created)
    return JSONResponse(
        {"_id": rid, "user_access_policy_uri": f"{ISSUER}/owner/policies"},
        status_code=201 if created else 200,
        headers={"Location": f"{ISSUER}/rreg/{rid}"} if created else {},
    )


@app.get("/rreg")
async def list_resources(request: Request) -> list:
    """FedAuthz §3.4 List: bare ids, as the spec shapes it."""
    require_pat(request)
    return list(RESOURCES.keys())


@app.get("/rreg/{rid:path}")
async def read_resource(rid: str, request: Request) -> dict:
    require_pat(request)
    if rid not in RESOURCES:
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    return {"_id": rid, **{k: v for k, v in RESOURCES[rid].items() if v is not None}}


@app.put("/rreg/{rid:path}")
async def update_resource(rid: str, request: Request) -> dict:
    require_pat(request)
    reject_push()
    if rid not in RESOURCES:
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    RESOURCES[rid] = resource_description(await request.json())
    event("resource.updated", resource_id=rid,
          scopes=RESOURCES[rid]["resource_scopes"])
    return {"_id": rid}


@app.delete("/rreg/{rid:path}")
async def delete_resource(rid: str, request: Request) -> JSONResponse:
    require_pat(request)
    reject_push()
    if rid not in RESOURCES:
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    del RESOURCES[rid]
    event("resource.deleted", resource_id=rid)
    return JSONResponse(None, status_code=204)


@app.post("/perm")
async def register_permission(request: Request) -> JSONResponse:
    require_pat(request)
    body = await request.json()
    rid = body.get("resource_id")
    # FedAuthz §4.1: the AS only issues tickets against its own registry.
    registered = RESOURCES.get(rid)
    if registered is None and REGISTRATION_MODE == "pull":
        # The mirror of push mode's RS-side repair: an unknown id means our
        # pulled copy may be stale, so re-read what the RS publishes.
        # (to_thread: see pull_at_startup — the pull triggers a JWKS
        # back-call from the RS and must not block this event loop.)
        import asyncio

        for client_id in RS_CLIENTS:
            try:
                await asyncio.to_thread(pull_registrations, client_id)
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
    ticket = new_ticket(
        {
            "family": family,
            "state": "issued",
            "resource_id": rid,
            "resource_scopes": scopes,
        }
    )
    event("permission.registered", corr=family, resource_id=rid, scopes=scopes)
    return JSONResponse({"ticket": ticket}, status_code=201)


@app.post("/introspect")
async def introspect(request: Request, token: str = Form(...), consume: str = Form(None)) -> dict:
    require_pat(request)
    try:
        claims = jwt.decode(
            token,
            SIGNING_KEY.public_key(),
            algorithms=["EdDSA"],
            issuer=ISSUER,
            options={"verify_aud": False},
        )
    except jwt.InvalidTokenError as exc:
        event("rpt.introspected", details_result=f"invalid: {exc}")
        return {"active": False}

    jti = claims.get("jti", "")
    rec = RPTS.get(jti)
    if rec is None:
        return {"active": False}
    conn = CONNECTIONS.get(rec.get("handle", ""))
    if conn is not None and conn["status"] != "active":
        event("rpt.introspected", corr=rec["family"], result="connection-revoked")
        return {"active": False}
    if conn is not None:
        conn["last_access"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if claims.get("single_use"):
        if rec["consumed"]:
            event("rpt.introspected", corr=rec["family"], result="already-consumed")
            return {"active": False}
        if consume == "true":
            rec["consumed"] = True
            event("rpt.consumed", corr=rec["family"], jti=jti)

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


@app.post("/audit/access")
async def audit_access(request: Request) -> dict:
    """The PEP reports allowed calls so the ledger's 'touched' column is
    grounded in enforcement, not client claims."""
    require_pat(request)
    body = await request.json()
    ledger_add("touched", body.get("family", "?"), {
        "tool": body.get("tool"),
        "summary": body.get("summary"),
    })
    event("access.allowed", corr=body.get("family"), tool=body.get("tool"))
    return {"recorded": True}


# --- Grant API (agent-facing, UMA 2.0 Grant shape) ---------------------------


def terms_template_for(rec: dict, tier_id: str, tier: dict, family: str) -> dict:
    template = dict(tier["terms"])
    template.update(
        {
            "proffered_by": ISSUER,
            "terms_uri": publish_terms(tier_id, tier),
            "nonce": rec["nonce"],
            "family": family,
            "resource_id": rec["resource_id"],
        }
    )
    return template


def need_info_response(rec: dict, tier_id: str, tier: dict) -> JSONResponse:
    family = rec["family"]
    rec["state"] = "need_info"
    rec["nonce"] = secrets.token_urlsafe(12)
    rec["tier"] = tier_id
    template = terms_template_for(rec, tier_id, tier, family)
    rec["template"] = template
    rotated = new_ticket(rec)
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

    key = OKPAlgorithm.from_jwk(json.dumps(signer_jwk))
    contract = jwt.decode(token, key, algorithms=["EdDSA"], audience=ISSUER)

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

    contract["_identity"] = identity
    return contract, signer_jwk


def issue_rpt(rec: dict, contract_hash: str, signer_jwk: dict,
              operation: dict | None) -> dict:
    family = rec["family"]
    tier = policy.tiers()[rec["tier"]]
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
    RPTS[jti] = {"consumed": False, "family": family,
                 "operation": claims.get("operation"),
                 "handle": handle}
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
        rs = RS_CLIENTS.get(client_id or "")
        if rs is None or not secrets.compare_digest(client_secret or "", rs["secret"]):
            return JSONResponse({"error": "invalid_client"}, status_code=401)
        if rs["status"] != "active":
            return JSONResponse(
                {"error": "access_denied",
                 "error_description": "the owner has revoked this resource server"},
                status_code=403)
        if scope != "uma_protection":
            return JSONResponse({"error": "invalid_scope"}, status_code=400)
        return JSONResponse(issue_pat(client_id))

    if grant_type != "urn:ietf:params:oauth:grant-type:uma-ticket":
        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)

    rec = consume_ticket(ticket)
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
        ledger_add("refused", family, {
            "tier": rec.get("tier"),
            "terms_uri": rec.get("template", {}).get("terms_uri"),
        })
        return JSONResponse({"error": "request_denied"}, status_code=403)

    # Pending ask-me ticket being re-presented (beat 3, taking longer).
    if rec["state"] == "awaiting-owner":
        return await pending_poll(rec)

    tier_id, tier = policy.tier_for_resource(rec["resource_id"])
    if tier_id is None:
        event("policy.evaluated", corr=family, result="no-tier")
        return JSONResponse({"error": "request_denied"}, status_code=403)

    # Beat 2: no contract yet -> dictate Alice's terms.
    if not claim_token:
        return need_info_response(rec, tier_id, tier)

    # Beat 3: contract committed.
    if claim_token_format != AGREEMENT_FORMAT:
        return JSONResponse({"error": "invalid_claim_token_format"}, status_code=400)
    if rec["state"] != "need_info":
        return JSONResponse({"error": "invalid_grant"}, status_code=400)
    try:
        contract, signer_jwk = verify_contract(claim_token, rec)
    except Exception as exc:
        event("contract.rejected", corr=family, reason=str(exc))
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
    ledger_add("promised", family, {
        "tier": rec["tier"],
        "purpose": contract["purpose"],
        "prohibited": contract["prohibited"],
        "expires_in": contract["expires_in"],
        "contract": contract_hash,
        "terms_uri": contract["terms_uri"],
        "operation": contract.get("operation"),
    })

    # Day-1 handshake: an agent without a standing connection pends — the same
    # request_submitted machinery, asking a different question ("do you want a
    # relationship with this agent?"). Alice's approval creates the connection
    # AND releases this negotiation in one tap.
    handle = connection_handle(contract["_identity"], signer_jwk)
    conn = CONNECTIONS.get(handle)
    needs_connection = conn is None or conn["status"] != "active"
    needs_operation_approval = tier["ask_me"]

    if needs_connection or needs_operation_approval:
        kind = "connection" if needs_connection else "operation"
        rec["state"] = "awaiting-owner"
        rec["decision"] = None
        rec["pending_kind"] = kind
        rec["handle"] = handle
        rotated = new_ticket(rec)
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
                "prohibited": contract["prohibited"],
                "identity": contract["_identity"],
                "handle": handle,
            }
        )
        event("owner.notified", corr=family, kind=kind)
        return JSONResponse(
            {"error": "request_submitted", "ticket": rotated, "interval": POLL_INTERVAL},
            status_code=403,
        )

    conn["last_access"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    event("policy.evaluated", corr=family, result="auto-grant", tier=rec["tier"],
          connection=handle)
    return JSONResponse(issue_rpt(rec, contract_hash, signer_jwk, None))


async def pending_poll(rec: dict) -> JSONResponse:
    family = rec["family"]
    if rec.get("decision") == "approved":
        if rec.get("pending_kind") == "connection":
            handle = rec["handle"]
            identity = rec["contract"]["_identity"]
            CONNECTIONS[handle] = {
                "handle": handle,
                "identity": identity,
                "label": identity.get("sub") or f"Agent {handle[4:12]}",
                "status": "active",
                "first_seen": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "last_access": None,
                "tiers": ["tier1", "tier2", "tier3"],
            }
            event("connection.approved", corr=family, handle=handle)
            ledger_add("connected", family, {"handle": handle,
                                             "identity": identity})
        event("policy.evaluated", corr=family, result="owner-approved", tier=rec["tier"])
        # Tier policy still applies after connection: an ask-me tier needs its
        # per-operation approval, which Alice's single tap covered only if this
        # negotiation carried the operation (it did — the contract binds it).
        return JSONResponse(
            issue_rpt(rec, rec["contract_hash"], rec["signer_jwk"],
                      rec["contract"].get("operation"))
        )
    if rec.get("decision") == "denied":
        event("policy.evaluated", corr=family, result="owner-denied", tier=rec["tier"])
        return JSONResponse({"error": "request_denied"}, status_code=403)
    rotated = new_ticket(rec)  # still pending: rotate and keep waiting
    return JSONResponse(
        {"error": "request_submitted", "ticket": rotated, "interval": POLL_INTERVAL},
        status_code=403,
    )


# --- Owner API (the portal's backend) ----------------------------------------


@app.get("/owner/pending")
async def owner_pending(request: Request) -> list:
    require_owner(request)
    out = []
    for rec in {id(r): r for r in TICKETS.values()}.values():
        if rec["state"] == "awaiting-owner" and rec.get("decision") is None:
            out.append(
                {
                    "family": rec["family"],
                    "kind": rec.get("pending_kind", "operation"),
                    "tier": rec["tier"],
                    "purpose": rec["contract"]["purpose"],
                    "operation": rec["contract"].get("operation"),
                    "prohibited": rec["contract"]["prohibited"],
                    "identity": rec["contract"]["_identity"],
                    "handle": rec.get("handle"),
                }
            )
    return out


@app.post("/owner/pending/{family}/decision")
async def owner_decision(family: str, request: Request) -> dict:
    require_owner(request)
    body = await request.json()
    decision = body.get("decision")
    if decision not in ("approved", "denied"):
        raise HTTPException(status_code=400, detail="decision must be approved|denied")
    found = False
    for rec in TICKETS.values():
        if rec["family"] == family and rec["state"] == "awaiting-owner":
            rec["decision"] = decision
            found = True
    if not found:
        raise HTTPException(status_code=404, detail="no pending negotiation for that family")
    event("owner.decision", corr=family, decision=decision)
    # Record both outcomes: "what did I decide" is an audit question, and a
    # denial is as much a decision as an approval.
    ledger_add("approved" if decision == "approved" else "denied", family,
               {"decision": decision})
    await owner_notify({"type": "decided", "family": family, "decision": decision})
    return {"family": family, "decision": decision}


@app.get("/owner/resource-servers")
async def owner_resource_servers(request: Request) -> list:
    """The resource servers Alice has authorized to use her Protection API —
    the other standing relationship her AS holds, beside agent connections."""
    require_owner(request)
    return [
        {"client_id": cid, **{k: v for k, v in rs.items() if k != "secret"}}
        for cid, rs in RS_CLIENTS.items()
    ]


@app.post("/owner/resource-servers/{client_id}/revoke")
async def owner_revoke_resource_server(client_id: str, request: Request) -> dict:
    require_owner(request)
    rs = RS_CLIENTS.get(client_id)
    if rs is None:
        raise HTTPException(status_code=404, detail="unknown resource server")
    rs["status"] = "revoked"
    event("resource_server.revoked", client_id=client_id)
    ledger_add("revoked", "-", {"resource_server": client_id})
    return {"client_id": client_id, "status": "revoked"}


@app.get("/owner/resources")
async def owner_resources(request: Request) -> list:
    """The owner's view of what her AS is protecting: every registered
    resource, joined with the tier whose policy governs it. This is the
    surface Alice attaches policy to before any agent has ever called."""
    require_owner(request)
    out = []
    for rid, desc in RESOURCES.items():
        tier_id, tier = policy.tier_for_resource(rid)
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
    require_owner(request)
    return policy.tiers()


@app.put("/owner/policies/{tier_id}")
async def owner_update_policy(tier_id: str, request: Request) -> dict:
    require_owner(request)
    patch = await request.json()
    try:
        updated = policy.update_tier(tier_id, patch)
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown tier")
    event("policy.updated", tier=tier_id, template_id=updated["terms"]["template_id"])
    # Publish the new version immediately so its terms URI dereferences from
    # the moment it exists; earlier versions remain served (persistent record).
    publish_terms(tier_id, updated)
    return updated


@app.get("/owner/connections")
async def owner_connections(request: Request) -> list:
    require_owner(request)
    return sorted(CONNECTIONS.values(), key=lambda c: c["first_seen"], reverse=True)


@app.post("/owner/connections/{handle}/revoke")
async def owner_revoke_connection(handle: str, request: Request) -> dict:
    require_owner(request)
    conn = CONNECTIONS.get(handle)
    if conn is None:
        raise HTTPException(status_code=404, detail="unknown connection")
    conn["status"] = "revoked"
    killed = 0
    for rec in RPTS.values():
        if rec.get("handle") == handle and not rec["consumed"]:
            rec["consumed"] = True
            killed += 1
    event("connection.revoked", handle=handle, rpts_deactivated=killed)
    ledger_add("revoked", "-", {"handle": handle, "rpts_deactivated": killed})
    await owner_notify({"type": "decided", "family": "-", "decision": "revoked"})
    return {"handle": handle, "status": "revoked", "rpts_deactivated": killed}


@app.get("/owner/ledger")
async def owner_ledger(request: Request) -> list:
    require_owner(request)
    return LEDGER


@app.get("/owner/events")
async def owner_events(request: Request):
    """SSE stream for the portal: pending approvals arriving, decisions landing."""
    require_owner(request)
    from sse_starlette.sse import EventSourceResponse

    queue: asyncio.Queue = asyncio.Queue()
    OWNER_QUEUE.append(queue)

    async def stream():
        try:
            while True:
                item = await queue.get()
                yield {"event": item["type"], "data": json.dumps(item)}
        finally:
            OWNER_QUEUE.remove(queue)

    return EventSourceResponse(stream())
