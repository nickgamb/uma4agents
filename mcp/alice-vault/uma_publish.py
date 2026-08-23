"""The vault's own discovery surface, for when nothing is in front of it.

`ENFORCEMENT_MODE=embedded` moves the enforcement obligations into this
process. Publication has to move with them: RFC 9728 says the metadata lives
at the resource's origin, so with no gateway in the path there is nowhere else
for it to be served from.

The documents themselves are built by `lib/uma4a_publish.py`, which the
ext_authz host uses too — the point of both modes is that they are the same
implementation with a different host, and a second copy of the metadata
builder would be exactly the drift `uma4a_pep.py` exists to avoid.
"""

from __future__ import annotations

import json
import logging
import os
import sys

import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse

from uma4a_publish import (
    aauth_document,
    owner_resources_document,
    prm_document,
    sign_metadata,
    verify_owner_as_query,
)

log = logging.getLogger("alice-vault.publish")

AS_PUBLIC = os.environ.get("UMA_AS_PUBLIC", "https://alice-as.uma.lab")
AS_INTERNAL = os.environ.get("UMA_AS_INTERNAL", "http://uma-as:9000")
# Whose vault this is. UMA_VAULT_OWNER is what the server itself is told —
# it namespaces the tool ids and picks the fixtures — so it wins here too;
# a document published under one owner's path while the tools underneath it
# belong to another would be a resource claiming to be somebody else's.
OWNER = (os.environ.get("UMA_VAULT_OWNER")
         or os.environ.get("UMA_OWNER", "alice"))
AUTHORITY = os.environ.get("UMA_EXPECTED_AUTHORITY", "gateway.uma.lab")
# Configuration, not a constant: a resource reachable over plain http — a
# personal deployment with no certificate authority anywhere near it —
# publishes http URLs, and the authority pulling from it has to be able to
# fetch what it reads.
SCHEME = os.environ.get("UMA_PEP_SCHEME", "https")
PUBLIC_BASE = f"{SCHEME}://{AUTHORITY}"
KEY_PATH = os.environ.get("UMA_PEP_SIGNING_KEY", "/keys/vault-ed25519.pem")
KID = "alice-vault-1"


def _load_key():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    if os.path.exists(KEY_PATH):
        with open(KEY_PATH, "rb") as fh:
            return serialization.load_pem_private_key(fh.read(), password=None)
    key = Ed25519PrivateKey.generate()
    os.makedirs(os.path.dirname(KEY_PATH) or ".", exist_ok=True)
    with open(KEY_PATH, "wb") as fh:
        fh.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()))
    return key


_KEY = None


def key():
    global _KEY
    if _KEY is None:
        _KEY = _load_key()
    return _KEY


_AS_KEYS: dict = {"expires": 0.0, "keys": []}


async def as_keys() -> list:
    import time

    if _AS_KEYS["expires"] < time.time():
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{AS_INTERNAL}/jwks", timeout=5.0)
            r.raise_for_status()
        _AS_KEYS.update(expires=time.time() + 300, keys=r.json()["keys"])
    return _AS_KEYS["keys"]


def attach(mcp, tools: dict[str, tuple[str, list[str]]]) -> None:
    """Register the three discovery routes on the MCP server's HTTP app."""

    @mcp.custom_route("/.well-known/oauth-protected-resource", methods=["GET"])
    @mcp.custom_route("/.well-known/oauth-protected-resource/mcp", methods=["GET"])
    async def prm(request: Request) -> JSONResponse:
        doc = prm_document(PUBLIC_BASE, AS_PUBLIC, tools)
        return JSONResponse(sign_metadata(doc, key(), KID))

    @mcp.custom_route("/.well-known/oauth-protected-resource/mcp/{owner}",
                      methods=["GET"])
    async def prm_for_owner(request: Request) -> JSONResponse:
        """The same resource under the owner's own path.

        A resource server fronted by an enforcement point publishes one
        document per owner; this one holds a single owner and is reachable
        both ways. The authorization server dereferences whichever identifier
        it was configured with, so both have to answer — and each has to name
        itself, or the client is required to reject it.
        """
        who = request.path_params["owner"]
        if who != OWNER:
            return JSONResponse({"error": "no such resource"}, status_code=404)
        doc = prm_document(PUBLIC_BASE, AS_PUBLIC, tools, leaf=f"mcp/{who}")
        return JSONResponse(sign_metadata(doc, key(), KID))

    @mcp.custom_route("/.well-known/aauth-resource.json", methods=["GET"])
    async def aauth(request: Request) -> JSONResponse:
        return JSONResponse(aauth_document(PUBLIC_BASE, AS_PUBLIC, tools))

    @mcp.custom_route("/jwks", methods=["GET"])
    async def jwks(request: Request) -> JSONResponse:
        from jwt.algorithms import OKPAlgorithm

        jwk = json.loads(OKPAlgorithm.to_jwk(key().public_key()))
        jwk.update({"kid": KID, "use": "sig"})
        return JSONResponse({"keys": [jwk]})

    @mcp.custom_route("/owner-resources", methods=["GET"])
    async def owner_resources(request: Request) -> JSONResponse:
        """Served only to the owner's authorization server.

        The querier proves possession of her AS's signing key over RFC 9421 —
        the same mechanics the agent uses to prove possession of a grant,
        pointed the other way. Everything above this line is public; this is
        the line.
        """
        reason = verify_owner_as_query(
            method=request.method,
            authority=AUTHORITY,
            path="/owner-resources",
            signature_input=request.headers.get("signature-input", ""),
            signature=request.headers.get("signature", ""),
            as_jwks=await as_keys(),
        )
        if reason is not None:
            log.info(json.dumps({"event": "owner_resources.denied", "reason": reason}))
            return JSONResponse(
                {"error": "invalid_signature",
                 "error_description": "this listing is served only to the owner's "
                                      f"authorization server: {reason}"},
                status_code=401)
        log.info(json.dumps({"event": "owner_resources.served", "owner": OWNER}))
        return JSONResponse(owner_resources_document(PUBLIC_BASE, OWNER, tools))

    print(json.dumps({
        "event": "publishing.self",
        "detail": {"base": PUBLIC_BASE, "as": AS_PUBLIC},
    }), file=sys.stdout, flush=True)
