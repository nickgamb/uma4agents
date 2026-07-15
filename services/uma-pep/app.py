"""uma-pep — the UMA policy-enforcement point for agentgateway.

HTTP-protocol ext_authz (Spike D). Full enforcement:

- At startup, registers Alice's vault tool surfaces as resources at her AS
  (the FedAuthz obligation the gateway absorbs on behalf of naive MCPs).
- MCP session bootstrap (initialize, notifications, tools/list) passes
  unauthenticated: discovery is open, invocation is protected.
- tools/call without authorization -> beat 1: real ticket from /perm, 401 +
  WWW-Authenticate: UMA challenge.
- tools/call with an RPT -> introspection at the AS, proof-of-possession
  verification against the RPT's cnf key, tool/scope check, and for
  single-use RPTs an exact operation-params match with atomic consumption.
- Allowed calls are reported to the AS so the ledger's "touched" column is
  grounded in enforcement.
"""

import base64
import hashlib
import json
import logging
import os
import sys
import time

import httpx
from fastapi import FastAPI, Request, Response
from jwt.algorithms import OKPAlgorithm

from uma4a_http_sig import VerifyError, verify

AS_PUBLIC = os.environ.get("UMA_AS_PUBLIC", "https://alice-as.uma.lab")
AS_INTERNAL = os.environ.get("UMA_AS_INTERNAL", "http://uma-as:9000")
# The gateway's standing as a resource server: client credentials it
# exchanges at the AS for a PAT (scope uma_protection) — the FedAuthz
# obligation, done as OAuth rather than a shared string.
RS_CLIENT_ID = os.environ.get("UMA_AS_RS_CLIENT_ID", "meridian-gateway")
RS_CLIENT_SECRET = os.environ.get("UMA_AS_RS_CLIENT_SECRET", "gateway-dev-secret")
REALM = os.environ.get("UMA_REALM", "alice-vault")
# The authority Alice's vault is served under. Signature verification
# reconstructs the signed components from configuration rather than trusting
# forwarded headers (the ext_authz hop rewrites Host).
EXPECTED_AUTHORITY = os.environ.get("UMA_EXPECTED_AUTHORITY", "gateway.uma.lab")

# Alice's vault tool surface: tool -> (resource_id, scopes). This is what the
# gateway registers at her AS on startup.
TOOLS = {
    "get_positions": ("alice-vault/get_positions", ["positions:read"]),
    "get_transactions": ("alice-vault/get_transactions", ["transactions:read"]),
    "execute_trade": ("alice-vault/execute_trade", ["trades:execute"]),
}
SINGLE_USE_TOOLS = {"execute_trade"}
OPEN_METHODS = {"initialize", "notifications/initialized", "tools/list", "ping"}

log = logging.getLogger("uma-pep")
logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")

app = FastAPI(title="uma-pep")


def event(name: str, corr: str | None = None, **details) -> None:
    log.info(
        json.dumps(
            {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "event": name,
                "corr": corr,
                "actor": "uma-pep",
                "details": details,
            }
        )
    )


def s256(data: bytes) -> str:
    return "s256:" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()


def deny(status: int, body: dict, headers: dict | None = None) -> Response:
    return Response(
        status_code=status,
        content=json.dumps(body),
        media_type="application/json",
        headers=headers or {},
    )


_PAT: dict = {"token": None, "expires": 0.0}


async def get_pat(client: httpx.AsyncClient, force: bool = False) -> str:
    """The current PAT, refreshed via client_credentials before it expires."""
    if force or _PAT["token"] is None or _PAT["expires"] < time.time() + 60:
        r = await client.post(
            f"{AS_INTERNAL}/token",
            data={"grant_type": "client_credentials",
                  "client_id": RS_CLIENT_ID,
                  "client_secret": RS_CLIENT_SECRET,
                  "scope": "uma_protection"},
            timeout=5.0,
        )
        r.raise_for_status()
        body = r.json()
        _PAT["token"] = body["access_token"]
        _PAT["expires"] = time.time() + body.get("expires_in", 300)
        event("pat.obtained", client_id=RS_CLIENT_ID,
              expires_in=body.get("expires_in"))
    return _PAT["token"]


async def pat_headers(client: httpx.AsyncClient) -> dict:
    return {"Authorization": f"Bearer {await get_pat(client)}"}


async def register_tool_surfaces(client: httpx.AsyncClient) -> None:
    headers = await pat_headers(client)
    for tool, (rid, scopes) in TOOLS.items():
        r = await client.post(
            f"{AS_INTERNAL}/rreg",
            json={"_id": rid, "name": f"Alice's vault: {tool}",
                  "type": "mcp-tool", "resource_scopes": scopes},
            headers=headers,
            timeout=5.0,
        )
        r.raise_for_status()


@app.on_event("startup")
async def register_resources() -> None:
    async with httpx.AsyncClient() as client:
        for attempt in range(30):
            try:
                await register_tool_surfaces(client)
                break
            except httpx.HTTPError:
                time.sleep(1)
    event("resources.registered_at_startup", tools=list(TOOLS))


async def mint_ticket(resource_id: str, scopes: list[str]) -> str | None:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{AS_INTERNAL}/perm",
                json={"resource_id": resource_id, "resource_scopes": scopes},
                headers=await pat_headers(client),
                timeout=5.0,
            )
            if r.status_code == 401:
                # PAT expired mid-flight or the AS restarted with new keys.
                r = await client.post(
                    f"{AS_INTERNAL}/perm",
                    json={"resource_id": resource_id, "resource_scopes": scopes},
                    headers={"Authorization": f"Bearer {await get_pat(client, force=True)}"},
                    timeout=5.0,
                )
            if r.status_code == 400 and r.json().get("error") == "invalid_resource_id":
                # The AS restarted and lost the push-registered state; the RS is
                # the party that has to notice and repair it. (FedAuthz makes
                # the RS responsible for keeping registrations current — this
                # re-push is that obligation, and its awkwardness is a finding.)
                event("resources.reregistered", reason="as_lost_registry")
                await register_tool_surfaces(client)
                r = await client.post(
                    f"{AS_INTERNAL}/perm",
                    json={"resource_id": resource_id, "resource_scopes": scopes},
                    headers=await pat_headers(client),
                    timeout=5.0,
                )
            r.raise_for_status()
            return r.json()["ticket"]
    except httpx.HTTPError as exc:
        event("permission.register_failed", error=str(exc))
        return None


async def introspect(token: str, consume: bool) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{AS_INTERNAL}/introspect",
            data={"token": token, "consume": "true" if consume else "false"},
            headers=await pat_headers(client),
            timeout=5.0,
        )
        r.raise_for_status()
        return r.json()


async def report_access(family: str, tool: str, summary: str) -> None:
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{AS_INTERNAL}/audit/access",
                json={"family": family, "tool": tool, "summary": summary},
                headers=await pat_headers(client),
                timeout=5.0,
            )
    except httpx.HTTPError:
        pass


def parse_mcp(body: bytes) -> tuple[str | None, str | None, dict | None]:
    """Returns (jsonrpc_method, tool_name, tool_args) from an MCP POST body."""
    try:
        msg = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return None, None, None
    method = msg.get("method")
    if method == "tools/call":
        params = msg.get("params", {})
        return method, params.get("name"), params.get("arguments", {})
    return method, None, None


async def challenge(tool: str, original_path: str) -> Response:
    rid, scopes = TOOLS[tool]
    ticket = await mint_ticket(rid, scopes)
    if ticket is None:
        return deny(503, {"error": "as_unreachable"})
    event("challenge.issued", corr=None, tool=tool, resource_id=rid, path=original_path)
    # RFC 9728 §5.1: the challenge names the resource's metadata document, so
    # the client can corroborate as_uri against what the resource publishes
    # instead of taking the header's word for it.
    prm_url = (f"https://{EXPECTED_AUTHORITY}"
               f"/.well-known/oauth-protected-resource/mcp")
    return deny(
        401,
        {"error": "uma_challenge"},
        {
            "WWW-Authenticate": (
                f'UMA realm="{REALM}", as_uri="{AS_PUBLIC}", ticket="{ticket}", '
                f'resource_metadata="{prm_url}"'
            )
        },
    )


@app.api_route("/check{rest:path}", methods=["GET", "POST", "HEAD", "DELETE"])
async def check(request: Request, rest: str = "") -> Response:
    original_path = rest or "/"
    body = await request.body()
    method, tool, args = parse_mcp(body) if body else (None, None, None)

    # Session bootstrap and discovery are open; invocation is protected.
    if request.method != "POST" or method in OPEN_METHODS or method is None and tool is None and not body:
        return Response(status_code=200)
    if method != "tools/call":
        return Response(status_code=200)
    if tool not in TOOLS:
        event("access.denied", reason="unknown-tool", tool=tool)
        return deny(403, {"error": "unknown_tool"})

    authz = request.headers.get("authorization")
    if not authz:
        return await challenge(tool, original_path)

    if not authz.startswith("PoP "):
        return deny(401, {"error": "invalid_token",
                          "error_description": "RPTs are PoP tokens here, not Bearer"})
    rpt = authz[4:]

    info = await introspect(rpt, consume=(tool in SINGLE_USE_TOOLS))
    if not info.get("active"):
        event("access.denied", reason="inactive-rpt", tool=tool)
        return await challenge(tool, original_path)

    rid, _ = TOOLS[tool]
    perms = {p["resource_id"] for p in info.get("permissions", [])}
    if rid not in perms:
        event("access.denied", reason="permission-scope", tool=tool, granted=sorted(perms))
        return await challenge(tool, original_path)

    # Proof of possession: the request signature must verify against the
    # RPT's cnf key, over components that include the Authorization header.
    try:
        jwk = info["cnf"]["jwk"]
        pub = OKPAlgorithm.from_jwk(json.dumps(jwk))
        verify(
            method=request.method,
            authority=EXPECTED_AUTHORITY,
            path=original_path,
            authorization=authz,
            signature_input=request.headers.get("signature-input", ""),
            signature=request.headers.get("signature", ""),
            public_key=pub,
        )
    except (KeyError, VerifyError) as exc:
        event("access.denied", reason=f"pop: {exc}", tool=tool,
              method=request.method, authority=request.headers.get("host", ""),
              path=original_path,
              signature_input=request.headers.get("signature-input", ""))
        return deny(401, {"error": "invalid_token",
                          "error_description": f"proof-of-possession failed: {exc}"})

    # Single-use operation binding: this trade, not trading authority.
    if tool in SINGLE_USE_TOOLS:
        op = info.get("operation") or {}
        expected = op.get("params_s256")
        actual = s256(json.dumps(args or {}, sort_keys=True).encode())
        if op.get("tool") != tool or expected != actual:
            event("access.denied", reason="operation-binding", tool=tool,
                  expected=expected, actual=actual)
            return deny(403, {"error": "operation_mismatch",
                              "error_description": "RPT authorizes a different operation"})

    family = info.get("family", "?")
    contract = info.get("contract")
    event("access.allowed", corr=family, tool=tool, contract=contract,
          single_use=info.get("single_use", False))
    await report_access(family, tool, summary=json.dumps(args or {}, sort_keys=True))
    return Response(status_code=200, headers={"x-uma-contract": contract or ""})


@app.get("/.well-known/oauth-protected-resource")
@app.get("/.well-known/oauth-protected-resource/mcp")
async def protected_resource_metadata() -> dict:
    """RFC 9728 Protected Resource Metadata — the declare-and-pick-up
    complement to gateway-side registration. An agent can discover the
    owner's authorization server (and the protected tool surface) before it
    is ever challenged. `tool_surfaces` is an extension member carrying the
    per-tool resource ids the gateway registers at the AS."""
    scopes = sorted({s for _, (rid, ss) in TOOLS.items() for s in ss})
    return {
        "resource": f"https://{EXPECTED_AUTHORITY}/mcp",
        "authorization_servers": [AS_PUBLIC],
        "scopes_supported": scopes,
        "bearer_methods_supported": ["header"],
        "resource_signing_alg_values_supported": ["EdDSA"],
        "tool_surfaces": [
            {"tool": tool, "resource_id": rid, "resource_scopes": ss}
            for tool, (rid, ss) in TOOLS.items()
        ],
    }


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
