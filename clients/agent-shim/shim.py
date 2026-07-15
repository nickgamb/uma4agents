"""agent-shim — lets an unmodified agent (Claude Code, Claude Desktop, any MCP
client) act as Bob's requesting agent.

The shim is to UMA-for-agents what mcp-remote is to MCP OAuth: a local stdio
MCP server that proxies Alice's vault tools through the gateway, holds Bob's
agent signing key, and runs the four-beat grant dance whenever the gateway
challenges. Alice's dictated terms are surfaced to Bob **inside his agent**
via MCP elicitation when the client supports it (Claude Code ≥ 2.1.76);
otherwise Bob's standing config decides (Claude Code renders elicitation;
some clients don't yet, hence the fallback).

Connect from Claude Code:

  claude mcp add alice-vault -- \
      uv run --project /path/to/uma4agents/clients/agent-shim shim

Environment:
  UMA4A_GATEWAY     https://gateway.uma.lab/mcp
  UMA4A_CACERT      path to certs/rootCA.pem
  UMA4A_KEYSTORE    where Bob's agent key persists
  UMA4A_STANDING_MAX_EXPIRES  fallback auto-accept bound (seconds)
  UMA4A_AGENT_ISSUER  Bob's agent server (e.g. https://ps.uma.lab); when set,
                      the shim enrolls and runs identified (aa-agent+jwt) —
                      first enrollment pends until Bob approves in the person
                      server UI. Unset: pseudonymous (bare key).
  UMA4A_PERSON_TOKEN  optional person-API bearer to auto-approve enrollment
                      (headless runs only — normally Bob taps in the PS UI)
"""

import json
import os
import sys

import httpx
from mcp.server.fastmcp import Context, FastMCP
from pydantic import BaseModel

from uma4a_grant import (
    AgentKeys,
    GrantDenied,
    TermsRejected,
    parse_challenge,
    run_grant_async,
    signed_headers,
)

GATEWAY = os.environ.get("UMA4A_GATEWAY", "https://gateway.uma.lab/mcp")
CACERT = os.environ.get("UMA4A_CACERT", "certs/rootCA.pem")
KEYSTORE = os.environ.get("UMA4A_KEYSTORE", os.path.expanduser("~/.uma4agents/agent-key.pem"))
# The agent's half of the dual-held MyTerms record: counter-signed receipts
# from the owner's AS, one file per negotiation.
RECEIPTS_DIR = os.environ.get(
    "UMA4A_RECEIPTS", os.path.join(os.path.dirname(KEYSTORE) or ".", "receipts")
)
STANDING_MAX_EXPIRES = int(os.environ.get("UMA4A_STANDING_MAX_EXPIRES", 7 * 24 * 3600))
AGENT_ISSUER = os.environ.get("UMA4A_AGENT_ISSUER")
PERSON_TOKEN = os.environ.get("UMA4A_PERSON_TOKEN")
AUTHORITY = httpx.URL(GATEWAY).host
MCP_PATH = httpx.URL(GATEWAY).path

mcp = FastMCP("alice-vault-via-uma")


def log(msg: str) -> None:
    print(f"[agent-shim] {msg}", file=sys.stderr, flush=True)


def bootstrap_identity() -> AgentKeys:
    """Pseudonymous by default; identified when an agent issuer is set.
    Identified: the persisted key becomes the stable key, a fresh session
    key signs everything, and the issuer's aa-agent+jwt binds them."""
    if not AGENT_ISSUER:
        return AgentKeys.load_or_create(KEYSTORE)
    from uma4a_enroll import enroll

    k = AgentKeys.load_or_create_identified(KEYSTORE)
    with httpx.Client(verify=CACERT, timeout=30.0) as client:
        k.agent_token = enroll(
            client, AGENT_ISSUER, k.stable, k.key,
            agent_name="Bob's agent via uma4agents shim",
            person_token=PERSON_TOKEN, on_status=log,
        )
    log(f"enrolled with {AGENT_ISSUER}; running identified")
    return k


keys = bootstrap_identity()


def store_receipt(receipt_jws: str) -> None:
    """Persist the counter-signed receipt from the owner's AS — this agent's
    half of the dual-held MyTerms record."""
    import json as _json

    try:
        payload = _json.loads(
            __import__("base64").urlsafe_b64decode(
                receipt_jws.split(".")[1] + "=="
            )
        )
        family = payload.get("family", "unknown")
    except Exception:
        family = "unknown"
    os.makedirs(RECEIPTS_DIR, exist_ok=True)
    path = os.path.join(RECEIPTS_DIR, f"{family}.receipt.jws")
    with open(path, "w") as f:
        f.write(receipt_jws)
    log(f"receipt held: {path}")


class TermsDecision(BaseModel):
    approve: bool


class Upstream:
    """Minimal MCP streamable-http client with the grant dance built in."""

    def __init__(self) -> None:
        self.client = httpx.AsyncClient(verify=CACERT, timeout=30.0)
        self.session_id: str | None = None
        self._id = 0
        self._initialized = False

    async def _post(self, msg: dict, headers: dict | None = None) -> httpx.Response:
        h = {"accept": "application/json, text/event-stream",
             "content-type": "application/json"}
        if self.session_id:
            h["mcp-session-id"] = self.session_id
        if headers:
            h.update(headers)
        r = await self.client.post(GATEWAY, json=msg, headers=h)
        if sid := r.headers.get("mcp-session-id"):
            self.session_id = sid
        return r

    @staticmethod
    def _payload(r: httpx.Response) -> dict | None:
        if "text/event-stream" in r.headers.get("content-type", ""):
            for line in r.text.splitlines():
                if line.startswith("data:"):
                    return json.loads(line[5:].strip())
            return None
        if not r.content:
            return None
        try:
            return r.json()
        except ValueError:
            raise RuntimeError(
                f"non-JSON response ({r.status_code}) from the gateway: {r.text[:200]}"
            ) from None

    async def request(self, method: str, params: dict | None = None,
                      headers: dict | None = None, notification: bool = False):
        msg: dict = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        if not notification:
            self._id += 1
            msg["id"] = self._id
        r = await self._post(msg, headers)
        return r, self._payload(r)

    async def ensure_initialized(self) -> None:
        if self._initialized:
            return
        r, _ = await self.request(
            "initialize",
            {"protocolVersion": "2025-03-26", "capabilities": {},
             "clientInfo": {"name": "uma4agents-agent-shim", "version": "0.1"}},
        )
        if r.status_code != 200:
            raise RuntimeError(f"gateway initialize failed: {r.status_code}")
        await self.request("notifications/initialized", {}, notification=True)
        self._initialized = True

    async def call_tool(self, ctx: Context, tool: str, args: dict,
                        operation: dict | None = None) -> str:
        await self.ensure_initialized()
        params = {"name": tool, "arguments": args}
        r, payload = await self.request("tools/call", params)

        if r.status_code == 401:
            challenge = parse_challenge(r.headers.get("www-authenticate", ""))
            if challenge is None:
                raise RuntimeError(f"401 without a UMA challenge: {r.text[:200]}")
            as_uri, ticket = challenge
            log(f"challenged by {as_uri}; negotiating")
            await ctx.info(f"Alice's AS requires terms before {tool} — negotiating")

            async def approve(template: dict) -> bool:
                return await approve_terms(ctx, tool, template)

            rpt = await run_grant_async(
                self.client, as_uri, ticket, keys, approve,
                operation=operation, on_status=log,
                on_receipt=store_receipt,
            )
            headers = signed_headers("POST", AUTHORITY, MCP_PATH, rpt, keys)
            r, payload = await self.request("tools/call", params, headers=headers)

        if r.status_code != 200:
            raise RuntimeError(f"call failed: {r.status_code} {r.text[:300]}")
        try:
            return payload["result"]["content"][0]["text"]
        except (KeyError, IndexError, TypeError):
            return json.dumps(payload)


async def approve_terms(ctx: Context, tool: str, template: dict) -> bool:
    """Elicit Bob inside his agent; fall back to his standing config."""
    message = (
        f"Alice's authorization server dictates these terms for `{tool}`:\n"
        f"• purpose: {template['purpose']}\n"
        f"• access expires in: {template['expires_in']}s\n"
        f"• prohibited: {', '.join(template['prohibited'])}\n\n"
        f"Sign this intent contract on your behalf?"
    )
    try:
        result = await ctx.elicit(message=message, schema=TermsDecision)
        if result.action == "accept" and result.data:
            log(f"terms {'approved' if result.data.approve else 'refused'} via elicitation")
            return result.data.approve
        log("elicitation declined/cancelled — refusing terms")
        return False
    except Exception as exc:  # client without elicitation support
        ok = template["expires_in"] <= STANDING_MAX_EXPIRES
        log(f"elicitation unavailable ({type(exc).__name__}); standing config "
            f"{'accepts' if ok else 'refuses'} (max_expires={STANDING_MAX_EXPIRES})")
        await ctx.info(
            f"Accepted Alice's terms under Bob's standing config: {template['purpose']}"
        )
        return ok


upstream = Upstream()


@mcp.tool()
async def get_positions(ctx: Context) -> str:
    """Alice's current holdings summary (tier 1: auto-grant under her standard terms)."""
    return await upstream.call_tool(ctx, "get_positions", {})


@mcp.tool()
async def get_transactions(ctx: Context, account: str = "brokerage-main") -> str:
    """Alice's transaction history (tier 2: stricter dictated terms)."""
    return await upstream.call_tool(ctx, "get_transactions", {"account": account})


@mcp.tool()
async def execute_trade(ctx: Context, symbol: str, side: str, quantity: int) -> str:
    """Propose a trade in Alice's account (tier 3: pends until Alice approves;
    the grant is single-use and bound to exactly this order)."""
    order = {"symbol": symbol, "side": side, "quantity": quantity}
    try:
        return await upstream.call_tool(
            ctx, "execute_trade", order,
            operation={"tool": "execute_trade", "params": order},
        )
    except GrantDenied as exc:
        return f"Alice did not authorize this trade: {exc}"
    except TermsRejected:
        return "You declined Alice's terms; the trade was not submitted."


if __name__ == "__main__":
    log(f"proxying {GATEWAY} (authority {AUTHORITY}); keystore {KEYSTORE}")
    mcp.run(transport="stdio")
