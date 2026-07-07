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
PAT = os.environ.get("UMA_AS_PAT", "pat-dev-gateway")
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


@app.on_event("startup")
async def register_resources() -> None:
    async with httpx.AsyncClient() as client:
        for tool, (rid, scopes) in TOOLS.items():
            for attempt in range(30):
                try:
                    r = await client.post(
                        f"{AS_INTERNAL}/rreg",
                        json={"_id": rid, "name": f"Alice's vault: {tool}",
                              "type": "mcp-tool", "resource_scopes": scopes},
                        headers={"Authorization": f"Bearer {PAT}"},
                        timeout=5.0,
                    )
                    r.raise_for_status()
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
                headers={"Authorization": f"Bearer {PAT}"},
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
            headers={"Authorization": f"Bearer {PAT}"},
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
                headers={"Authorization": f"Bearer {PAT}"},
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
    return deny(
        401,
        {"error": "uma_challenge"},
        {
            "WWW-Authenticate": (
                f'UMA realm="{REALM}", as_uri="{AS_PUBLIC}", ticket="{ticket}"'
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


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
