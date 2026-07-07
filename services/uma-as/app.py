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
PAT = os.environ.get("UMA_AS_PAT", "pat-dev-gateway")
OWNER_TOKEN = os.environ.get("UMA_AS_OWNER_TOKEN", "owner-dev-portal")
CONTRACT_FORMAT = "urn:uma4agents:format:intent-contract-v1+jws"
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
RPTS: dict[str, dict] = {}          # jti -> {consumed, operation, family, jkt}
LEDGER: list[dict] = []             # promised / touched / approved entries
OWNER_QUEUE: list[asyncio.Queue] = []  # SSE subscribers (portal)
# Standing relationships: the day-1 handshake's output. Keyed by the agent's
# RFC 7638 JWK thumbprint. An unknown agent's first contract commit pends as a
# connection request — UMA's request_submitted doing double duty as
# owner-mediated agent registration. Revocation deactivates live RPTs too.
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
        "grant_types_supported": ["urn:ietf:params:oauth:grant-type:uma-ticket"],
        "claim_token_formats_supported": [CONTRACT_FORMAT],
    }


def require_pat(request: Request) -> None:
    if request.headers.get("authorization") != f"Bearer {PAT}":
        raise HTTPException(status_code=401, detail="protection API requires the PAT")


def require_owner(request: Request) -> None:
    if request.headers.get("authorization") != f"Bearer {OWNER_TOKEN}":
        raise HTTPException(status_code=401, detail="owner API requires the owner token")


# --- Protection API (gateway-side, FedAuthz shape) ---------------------------


@app.post("/rreg")
async def register_resource(request: Request) -> JSONResponse:
    require_pat(request)
    body = await request.json()
    rid = body.get("_id") or f"res_{uuid.uuid4().hex[:8]}"
    RESOURCES[rid] = {
        "resource_scopes": body["resource_scopes"],
        "name": body.get("name", rid),
        "type": body.get("type"),
    }
    event("resource.registered", resource_id=rid, scopes=body["resource_scopes"])
    return JSONResponse({"_id": rid}, status_code=201)


@app.get("/rreg")
async def list_resources(request: Request) -> list:
    require_pat(request)
    return [{"_id": k, **v} for k, v in RESOURCES.items()]


@app.post("/perm")
async def register_permission(request: Request) -> JSONResponse:
    require_pat(request)
    body = await request.json()
    family = f"fam_{secrets.token_urlsafe(8)}"
    ticket = new_ticket(
        {
            "family": family,
            "state": "issued",
            "resource_id": body["resource_id"],
            "resource_scopes": body["resource_scopes"],
        }
    )
    event("permission.registered", corr=family, resource_id=body["resource_id"],
          scopes=body["resource_scopes"])
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
    conn = CONNECTIONS.get(rec.get("jkt", ""))
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
            "dictated_by": ISSUER,
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
                    "claim_type": "urn:uma4agents:claim:intent-contract",
                    "claim_token_format": [CONTRACT_FORMAT],
                    "friendly_name": f"Alice's terms: {tier['name']}",
                    "terms_template": template,
                }
            ],
        },
        status_code=403,
    )


def verify_contract(claim_token_b64: str, rec: dict) -> tuple[dict, dict]:
    """Verify the intent contract JWS and its echo of the dictated template.

    Returns (contract_claims, signer_jwk). The signer key comes from the JWS
    protected header: `jwk` (pseudonymous bare key, an AAuth identity level)
    or the `cnf.jwk` of an embedded `agent_token` (PS-issued aa-agent+jwt).
    """
    raw = base64.urlsafe_b64decode(claim_token_b64 + "=" * (-len(claim_token_b64) % 4))
    token = raw.decode()
    header = jwt.get_unverified_header(token)

    if "jwk" in header:
        signer_jwk = header["jwk"]
        identity = {"level": "pseudonymous"}
    elif "agent_token" in header:
        agent_claims = jwt.decode(header["agent_token"], options={"verify_signature": False})
        # Full agent-token chain validation (issuer JWKS fetch per AAuth dwk
        # discovery) is wired in the shim's bootstrap; here we bind to its cnf.
        signer_jwk = agent_claims["cnf"]["jwk"]
        identity = {"level": "identified", "iss": agent_claims.get("iss"),
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
    RPTS[jti] = {"consumed": False, "family": family,
                 "operation": claims.get("operation"),
                 "jkt": jwk_thumbprint(signer_jwk)}
    event("rpt.issued", corr=family, jti=jti, single_use=claims.get("single_use", False),
          tier=rec["tier"])
    return {"access_token": token, "token_type": "PoP", "expires_in": exp - int(now())}


@app.post("/token")
async def token(
    grant_type: str = Form(...),
    ticket: str = Form(None),
    claim_token: str = Form(None),
    claim_token_format: str = Form(None),
) -> JSONResponse:
    if grant_type != "urn:ietf:params:oauth:grant-type:uma-ticket":
        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)

    rec = consume_ticket(ticket)
    if rec is None:
        event("ticket.presented", corr=None, result="invalid_grant")
        return JSONResponse({"error": "invalid_grant"}, status_code=400)
    family = rec["family"]
    event("ticket.presented", corr=family, state=rec["state"])

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
    if claim_token_format != CONTRACT_FORMAT:
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
        "operation": contract.get("operation"),
    })

    # Day-1 handshake: an agent without a standing connection pends — the same
    # request_submitted machinery, asking a different question ("do you want a
    # relationship with this agent?"). Alice's approval creates the connection
    # AND releases this negotiation in one tap.
    jkt = jwk_thumbprint(signer_jwk)
    conn = CONNECTIONS.get(jkt)
    needs_connection = conn is None or conn["status"] != "active"
    needs_operation_approval = tier["ask_me"]

    if needs_connection or needs_operation_approval:
        kind = "connection" if needs_connection else "operation"
        rec["state"] = "awaiting-owner"
        rec["decision"] = None
        rec["pending_kind"] = kind
        rec["jkt"] = jkt
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
                "jkt": jkt,
            }
        )
        event("owner.notified", corr=family, kind=kind)
        return JSONResponse(
            {"error": "request_submitted", "ticket": rotated, "interval": POLL_INTERVAL},
            status_code=403,
        )

    conn["last_access"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    event("policy.evaluated", corr=family, result="auto-grant", tier=rec["tier"],
          connection=jkt)
    return JSONResponse(issue_rpt(rec, contract_hash, signer_jwk, None))


async def pending_poll(rec: dict) -> JSONResponse:
    family = rec["family"]
    if rec.get("decision") == "approved":
        if rec.get("pending_kind") == "connection":
            jkt = rec["jkt"]
            CONNECTIONS[jkt] = {
                "jkt": jkt,
                "identity": rec["contract"]["_identity"],
                "label": rec["contract"]["_identity"].get("sub")
                or f"Agent {jkt[4:12]}",
                "status": "active",
                "first_seen": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "last_access": None,
                "tiers": ["tier1", "tier2", "tier3"],
            }
            event("connection.approved", corr=family, jkt=jkt)
            ledger_add("connected", family, {"jkt": jkt,
                                             "identity": rec["contract"]["_identity"]})
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
                    "jkt": rec.get("jkt"),
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
    if decision == "approved":
        ledger_add("approved", family, {"decision": decision})
    await owner_notify({"type": "decided", "family": family, "decision": decision})
    return {"family": family, "decision": decision}


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
    return updated


@app.get("/owner/connections")
async def owner_connections(request: Request) -> list:
    require_owner(request)
    return sorted(CONNECTIONS.values(), key=lambda c: c["first_seen"], reverse=True)


@app.post("/owner/connections/{jkt}/revoke")
async def owner_revoke_connection(jkt: str, request: Request) -> dict:
    require_owner(request)
    conn = CONNECTIONS.get(jkt)
    if conn is None:
        raise HTTPException(status_code=404, detail="unknown connection")
    conn["status"] = "revoked"
    killed = 0
    for rec in RPTS.values():
        if rec.get("jkt") == jkt and not rec["consumed"]:
            rec["consumed"] = True
            killed += 1
    event("connection.revoked", jkt=jkt, rpts_deactivated=killed)
    ledger_add("revoked", "-", {"jkt": jkt, "rpts_deactivated": killed})
    await owner_notify({"type": "decided", "family": "-", "decision": "revoked"})
    return {"jkt": jkt, "status": "revoked", "rpts_deactivated": killed}


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
