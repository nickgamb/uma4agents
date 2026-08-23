"""Sterling & Vance — the public web presence of the firm that operates Bob's agent.

Both of the identity conventions this lab adopts assume the requesting side has
somewhere on the web that speaks for it, and neither works without one:

  /agent.json
      A Client ID Metadata Document (draft-ietf-oauth-client-id-metadata-document),
      the mechanism MCP now prefers over Dynamic Client Registration. Alice's
      approval dialog resolves this to show an operator and a policy URI
      instead of a bare key thumbprint. Display metadata only — her AS still
      keys the connection by the agent's key or its verified issuer, so
      nothing here can widen access.

  /.well-known/http-message-signatures-directory
      A Web Bot Auth key directory (draft-meunier-http-message-signatures-directory):
      a JWKS of the keys this operator's agents sign with. A resource that has
      never met this agent can fetch it and learn the key belongs to a
      published operator — which is the RqP != RO cold-start problem, since by
      definition there is no prior relationship to lean on.

A real operator publishes keys it already holds, and that is the shape here:
AGENT_OPERATOR_KEYS_FILE names a JWKS this process reads at startup and only
serves. POST /register remains as a lab path for the single-process stack,
whose agent keys are generated per run — and is refused outright once a
published file is configured, so the two modes cannot be mixed.

The distinction matters more than it looks. A directory held only in memory
and filled in by whoever happened to call is a directory that empties on
restart and disagrees with itself the moment there are two of these
processes — an agent registers with one, a resource asks the other, and the
key it needs is missing. Seeding from a file makes this service hold no
authoritative state at all, which is what makes running several of them
correct. The way to make a service horizontally scalable is usually to stop
it holding state, not to replicate the state.
"""

import json
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

ORIGIN = os.environ.get("AGENT_OPERATOR_ORIGIN", "https://agent.uma.lab")
NAME = os.environ.get("AGENT_OPERATOR_NAME", "Sterling & Vance — Advisory Agent")
KEYS_FILE = os.environ.get("AGENT_OPERATOR_KEYS_FILE")

app = FastAPI(title="agent-operator")

# keyid -> JWK. Seeded from the published file; added to by /register.
KEYS: dict[str, dict] = {}


def load_published_keys() -> int:
    """Read the operator's published JWKS, if it has one.

    A missing or malformed file is not fatal: the directory is a discovery
    aid, never an authorization input, so serving an empty one is a
    degradation rather than a failure. Saying so out loud is the point —
    a service that refused to start over this would be treating discovery as
    though it were trust.
    """
    if not KEYS_FILE:
        return 0
    try:
        with open(KEYS_FILE) as f:
            published = json.load(f)
    except (OSError, ValueError) as exc:
        print(json.dumps({"event": "agent_keys.unreadable", "path": KEYS_FILE,
                          "error": str(exc)[:120]}), flush=True)
        return 0
    for jwk in published.get("keys", []):
        if kid := jwk.get("kid"):
            KEYS[kid] = jwk
    print(json.dumps({"event": "agent_keys.published_loaded",
                      "path": KEYS_FILE, "keys": len(KEYS)}), flush=True)
    return len(KEYS)


@app.on_event("startup")
async def seed_directory() -> None:
    load_published_keys()


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "keys": len(KEYS)}


@app.get("/agent.json")
async def client_id_metadata() -> JSONResponse:
    """The CIMD document. `client_id` MUST equal the URL this is served from —
    that self-reference is what stops one site publishing metadata about
    another's client, and Alice's AS rejects the document if it disagrees."""
    return JSONResponse({
        "client_id": f"{ORIGIN}/agent.json",
        "client_name": NAME,
        "client_uri": ORIGIN,
        "policy_uri": f"{ORIGIN}/privacy",
        "tos_uri": f"{ORIGIN}/terms",
        "contacts": ["advisory-ops@sterling-vance.example"],
        "software_id": "uma4agents-agent-shim",
    })


@app.get("/.well-known/http-message-signatures-directory")
async def signatures_directory() -> JSONResponse:
    """Web Bot Auth key directory: a JWKS under a dedicated media type."""
    return JSONResponse(
        {"keys": list(KEYS.values())},
        media_type="application/http-message-signatures-directory+json",
    )


@app.post("/register")
async def register(request: Request) -> JSONResponse:
    """Lab-only: an agent publishes the key it is about to sign with.

    Real operators publish keys they already hold, which is what
    AGENT_OPERATOR_KEYS_FILE is. This exists because the toy stack generates
    its agent keys per run and something has to publish them. It is
    deliberately unauthenticated and local-only — nothing downstream trusts
    this directory for authorization, only for discovery.

    **Refused once the operator is seeded from a file**, and that is the
    interesting line rather than a safety rail. This endpoint writes to one
    process's memory. With a single process that is merely untidy; with more
    than one it is wrong in a way nothing reports — the registration lands on
    one replica, a resource server asks another, the key is missing, and an
    agent that did everything right drops an assurance level about half the
    time. Refusing here is what makes `replicas: 2` a true statement instead
    of an aspiration: a seeded directory is read-only, identical everywhere,
    and cannot drift.
    """
    if KEYS_FILE:
        return JSONResponse(
            {"registered": False,
             "error": "this operator publishes keys it already holds",
             "detail": ("AGENT_OPERATOR_KEYS_FILE is set, so the directory is "
                        "read-only and identical across replicas. Provision "
                        "the key into that document instead.")},
            status_code=409)
    body = await request.json()
    jwk = body.get("jwk") or {}
    keyid = body.get("keyid") or jwk.get("kid")
    if not keyid or not jwk:
        return JSONResponse({"registered": False,
                             "error": "keyid and jwk required"}, status_code=400)
    KEYS[keyid] = {**jwk, "kid": keyid}
    print(json.dumps({"event": "agent_key.published", "keyid": keyid}), flush=True)
    return JSONResponse({"registered": True, "keyid": keyid, "keys": len(KEYS)})
