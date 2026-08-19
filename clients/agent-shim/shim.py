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
  UMA4A_SHIM_TRANSPORT  stdio (default) or streamable-http
  UMA4A_SHIM_HOST/PORT  where to listen, for streamable-http

Run it as a service instead of a subprocess
-------------------------------------------
`UMA4A_SHIM_TRANSPORT=streamable-http` makes the same shim a remote MCP
server, which is what an agent that is not a local process needs — an agent
framework running in a cluster cannot spawn a stdio subprocess on your laptop.

Nothing else changes, and that is the point worth noticing: the four-beat
grant, the signing key, the terms decision and the receipts are all in here,
so the *agent* on the other side needs to know none of it. It sees ordinary
MCP tools. See `k8s/base/sterling-vance/agent-shim.yaml` for the deployed
shape, and `docs/KAGENT.md` for an agent framework using it unmodified.
"""

import json
import os
import sys

import httpx
from mcp.server.mcpserver import Context, MCPServer
from mcp.shared.exceptions import MCPError
from pydantic import BaseModel

from uma4a_grant import (
    AgentKeys,
    DiscoveryMismatch,
    GrantDenied,
    TermsRejected,
    parse_challenge,
    run_grant_async,
    signed_headers,
    validate_resource_metadata,
    well_known_prm_url,
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
TRANSPORT = os.environ.get("UMA4A_SHIM_TRANSPORT", "stdio")
SHIM_HOST = os.environ.get("UMA4A_SHIM_HOST", "127.0.0.1")
SHIM_PORT = int(os.environ.get("UMA4A_SHIM_PORT", "9030"))
AGENT_ISSUER = os.environ.get("UMA4A_AGENT_ISSUER")
PERSON_TOKEN = os.environ.get("UMA4A_PERSON_TOKEN")
AUTHORITY = httpx.URL(GATEWAY).host
MCP_PATH = httpx.URL(GATEWAY).path

# 2026-07-28 is only reachable through the server/discover handshake: the SDK
# splits HANDSHAKE_PROTOCOL_VERSIONS (which tops out at 2025-11-25) from
# MODERN_PROTOCOL_VERSIONS, so asking `initialize` for the new version is
# silently answered with the old one.
PROTOCOL_VERSION = "2026-07-28"
# Client identity travels in params._meta on every request now, rather than
# being exchanged once at initialize — that is what makes the transport
# stateless (SEP-2567/2575).
CLIENT_META = {
    "io.modelcontextprotocol/protocolVersion": PROTOCOL_VERSION,
    "io.modelcontextprotocol/clientCapabilities": {},
    "io.modelcontextprotocol/clientInfo": {
        "name": "uma4agents-agent-shim", "version": "0.1",
    },
}

mcp = MCPServer("alice-vault-via-uma")


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


class KeepWaiting(BaseModel):
    keep_waiting: bool


# How long the shim polls Alice's AS before handing the wait back to Bob.
# Short on purpose: the point is that a pend is a protocol state to be
# *rendered*, not a call to be held open.
PEND_HANDBACK_S = int(os.environ.get("UMA4A_PEND_HANDBACK", 15))


class Upstream:
    """Minimal MCP streamable-http client with the grant dance built in."""

    def __init__(self) -> None:
        self.client = httpx.AsyncClient(verify=CACERT, timeout=30.0)
        self._id = 0
        self._discovered = False
        self._prm: dict | None = None

    async def resource_metadata(self) -> dict | None:
        """Beat 0 — the resource's RFC 9728 metadata, fetched once. Names
        the owner's AS and the protected tool surfaces before any call."""
        if self._prm is None:
            try:
                url = well_known_prm_url(GATEWAY)
                doc = (await self.client.get(url)).json()
                self._prm = validate_resource_metadata(doc, GATEWAY)
                log(f"beat 0: resource metadata at {url} — AS "
                    f"{', '.join(doc.get('authorization_servers', []))}, "
                    f"{len(doc.get('tool_surfaces', []))} tool surfaces")
            except DiscoveryMismatch:
                raise
            except Exception as exc:
                # Discovery is declarative; the challenge remains authoritative.
                log(f"beat 0: resource metadata unavailable ({exc}); "
                    "continuing challenge-driven")
        return self._prm

    async def _post(self, msg: dict, headers: dict | None = None) -> httpx.Response:
        # No session id: 2026-07-28 removed sessions, and all the state a
        # server needs rides in the message.
        h = {"accept": "application/json, text/event-stream",
             "content-type": "application/json",
             "MCP-Protocol-Version": PROTOCOL_VERSION}
        # SEP-2243: mirror the method and target into headers so a gateway can
        # route and enforce without parsing the body. The receiver is expected
        # to reconcile them against the body — they are a routing convenience,
        # not a second source of truth.
        if method := msg.get("method"):
            h["Mcp-Method"] = method
        if name := (msg.get("params") or {}).get("name"):
            h["Mcp-Name"] = name
        if headers:
            h.update(headers)
        return await self.client.post(GATEWAY, json=msg, headers=h)

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
        p = dict(params or {})
        p["_meta"] = {**CLIENT_META, **(p.get("_meta") or {})}
        msg: dict = {"jsonrpc": "2.0", "method": method, "params": p}
        if not notification:
            self._id += 1
            msg["id"] = self._id
        r = await self._post(msg, headers)
        return r, self._payload(r)

    async def ensure_discovered(self) -> None:
        """The 2026-07-28 handshake. Stateless, and the only door to the
        modern protocol — `initialize` cannot negotiate past 2025-11-25."""
        if self._discovered:
            return
        r, payload = await self.request("server/discover", {})
        if r.status_code != 200 or not payload or "result" in payload is None:
            raise RuntimeError(f"server/discover failed: {r.status_code} {r.text[:200]}")
        result = payload.get("result") or {}
        versions = result.get("supportedVersions", [])
        if PROTOCOL_VERSION not in versions:
            raise RuntimeError(
                f"resource does not speak {PROTOCOL_VERSION} (offers {versions})")
        # A resource enforcing UMA in-process advertises it here, so the shim
        # can know a grant is required before it makes a single call.
        exts = (result.get("capabilities") or {}).get("extensions") or {}
        if uma := exts.get("dev.uma4agents/uma-enforcement"):
            log("resource enforces UMA in-process; AS "
                f"{', '.join(uma.get('authorization_servers', []))}")
        self._discovered = True

    @staticmethod
    def _jsonrpc_challenge(payload: dict | None) -> tuple[str, str] | None:
        """Beat 1 from a resource that enforces in-process.

        With no gateway in the path there is no status line to carry
        `WWW-Authenticate`, so the same challenge arrives as a JSON-RPC error
        with the ticket and the AS in its data. The envelope follows the
        deployment; the ticket does not.
        """
        err = (payload or {}).get("error") or {}
        data = err.get("data") or {}
        if data.get("error") == "uma_challenge" and data.get("ticket"):
            return data["as_uri"], data["ticket"]
        return None

    async def call_tool(self, ctx: Context, tool: str, args: dict,
                        operation: dict | None = None,
                        reason: str | None = None) -> str:
        mission = MISSION
        await self.ensure_discovered()
        params = {"name": tool, "arguments": args}
        r, payload = await self.request("tools/call", params)

        challenge = None
        if r.status_code == 401:
            challenge = parse_challenge(r.headers.get("www-authenticate", ""))
            if challenge is None:
                raise RuntimeError(f"401 without a UMA challenge: {r.text[:200]}")
        else:
            challenge = self._jsonrpc_challenge(payload)

        if challenge is not None:
            as_uri, ticket = challenge
            log(f"challenged by {as_uri}; negotiating")
            prm = await self.resource_metadata()
            if prm is not None:
                try:
                    validate_resource_metadata(prm, GATEWAY, as_uri)
                    log("challenge corroborated against the resource's "
                        "published metadata")
                except DiscoveryMismatch as exc:
                    raise RuntimeError(f"refusing to negotiate: {exc}")
            # 2026-07-28 deprecated the logging capability (SEP-2577), which
            # was the only way to narrate progress to the requesting human
            # mid-call. Nothing replaces it for narration — the structural
            # answer is to stop narrating and make the wait a *result* the
            # client can render (MRTR's input_required). Until the shim
            # forwards the pend that way, this stays on stderr.
            log(f"Alice's AS requires terms before {tool} — negotiating")

            async def approve(template: dict) -> bool:
                return await approve_terms(ctx, tool, template)

            async def still_waiting(pend: dict) -> bool:
                return await keep_waiting(ctx, tool, pend)

            rpt = await run_grant_async(
                self.client, as_uri, ticket, keys, approve,
                operation=operation, reason=reason, mission=mission,
                on_status=log,
                on_receipt=store_receipt,
                max_wait_s=PEND_HANDBACK_S,
                on_pending=still_waiting,
            )
            headers = signed_headers("POST", AUTHORITY, MCP_PATH, rpt, keys)
            r, payload = await self.request("tools/call", params, headers=headers)

        if r.status_code != 200:
            raise RuntimeError(f"call failed: {r.status_code} {r.text[:300]}")
        if err := (payload or {}).get("error"):
            raise RuntimeError(f"call refused: {err.get('message')}")
        try:
            return payload["result"]["content"][0]["text"]
        except (KeyError, IndexError, TypeError):
            return json.dumps(payload)


async def keep_waiting(ctx: Context, tool: str, pend: dict) -> bool:
    """Hand a third party's pending decision back to the requesting human.

    This is the U4A case MCP has no type for. On 2026-07-28 the SDK turns this
    elicitation into an `InputRequiredResult` with a `request_state` handle, so
    the call stops being held open and Bob's client can render the wait and
    come back — exactly the machinery a pend needs.

    What it cannot express is *who* is being waited on. MRTR's `input_requests`
    is a closed union of CreateMessageRequest | ListRootsRequest |
    ElicitRequest — three requests that all address the client's own user.
    There is no slot for "blocked on a different principal, who is not on this
    connection and cannot be reached through it." So the only question that can
    be asked here is the one Bob can actually answer — keep waiting, or stop —
    and the real subject is described in prose:

        subject:  party=resource_owner
                  is_requesting_party=false
                  reachable_by_client=false

    That block is what the ext-auth proposal adds to an input request.
    Without it a conforming client will try to satisfy the wait from its own
    user, who has nothing to do with the decision.
    """
    message = (
        f"`{tool}` is waiting on the resource owner's decision.\n\n"
        f"• who must decide: the resource owner — not you, and not reachable "
        f"from this connection\n"
        f"• where: {pend['as_uri']}\n"
        f"• they have been notified and the request is holding\n\n"
        f"Keep waiting?"
    )
    try:
        result = await ctx.elicit(message=message, schema=KeepWaiting)
    except MCPError:
        log("client cannot render the pend; continuing to hold the call open")
        return True
    if result.action == "accept" and result.data:
        return result.data.keep_waiting
    log("requesting side stopped waiting")
    return False


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
    except MCPError as exc:
        # Only "this client cannot elicit" falls back to standing config.
        # Catching everything here would turn a real failure into a silent
        # auto-accept, which is the wrong way for this to break.
        ok = template["expires_in"] <= STANDING_MAX_EXPIRES
        log(f"elicitation unavailable ({type(exc).__name__}); standing config "
            f"{'accepts' if ok else 'refuses'} (max_expires={STANDING_MAX_EXPIRES})")
        log(f"{'Accepted' if ok else 'Refused'} Alice's terms under Bob's "
            f"standing config: {template['purpose']}")
        return ok
    if result.action == "accept" and result.data:
        log(f"terms {'approved' if result.data.approve else 'refused'} via elicitation")
        return result.data.approve
    log("elicitation declined/cancelled — refusing terms")
    return False


upstream = Upstream()


# The mandate this agent is running under, if its operator gave it one. An
# AAuth mission lives at the requesting party's own person server and is named
# by content hash, so what travels is the citation rather than the text — set
# both halves or neither.
#
# Alice's authority records it and shows it to her. It cannot check it: AAuth
# serves missions to administrators, so a relying party in another trust
# domain has nothing to dereference. Citing one buys less friction, never more
# access, which is the same bargain every other claim here makes.
MISSION = (
    {"approver": os.environ["UMA4A_MISSION_APPROVER"],
     "s256": os.environ["UMA4A_MISSION_S256"]}
    if os.environ.get("UMA4A_MISSION_APPROVER")
    and os.environ.get("UMA4A_MISSION_S256")
    else None
)


# `reason` is the agent's own account of the errand, in its own words. It is
# optional, it is never checked against Alice's terms, and her policy can do
# exactly one thing with it: require her to look when it is missing. So the
# model above this shim can fill it from whatever it actually knows, and
# leaving it blank costs friction rather than access.
@mcp.tool()
async def get_positions(ctx: Context) -> str:
    """Alice's current holdings summary (tier 1: auto-grant under her standard terms)."""
    return await upstream.call_tool(ctx, "get_positions", {})


@mcp.tool()
async def get_transactions(ctx: Context, account: str = "brokerage-main",
                           reason: str = "") -> str:
    """Alice's transaction history (tier 2: stricter dictated terms).

    `reason`: why you are asking, in one sentence, for Alice to read."""
    return await upstream.call_tool(ctx, "get_transactions", {"account": account},
                                    reason=reason)


@mcp.tool()
async def execute_trade(ctx: Context, symbol: str, side: str, quantity: int,
                        reason: str = "") -> str:
    """Propose a trade in Alice's account (tier 3: pends until Alice approves;
    the grant is single-use and bound to exactly this order).

    `reason`: why this order, in one sentence. Alice reads it beside the order
    itself when she is asked to approve, so it is the most useful here."""
    order = {"symbol": symbol, "side": side, "quantity": quantity}
    try:
        return await upstream.call_tool(
            ctx, "execute_trade", order,
            operation={"tool": "execute_trade", "params": order},
            reason=reason,
        )
    except GrantDenied as exc:
        return f"Alice did not authorize this trade: {exc}"
    except TermsRejected:
        return "You declined Alice's terms; the trade was not submitted."


if __name__ == "__main__":
    log(f"proxying {GATEWAY} (authority {AUTHORITY}); keystore {KEYSTORE}")
    if TRANSPORT == "stdio":
        mcp.run(transport="stdio")
    else:
        # Stateless, because there is no session state worth keeping: the
        # negotiation's continuity lives in the permission ticket at Alice's
        # authorization server, not in this process. That is what lets the
        # shim be replicated, restarted, or scaled to zero between calls
        # without an agent noticing.
        log(f"listening on {SHIM_HOST}:{SHIM_PORT} ({TRANSPORT})")
        mcp.run(transport=TRANSPORT, host=SHIM_HOST, port=SHIM_PORT,
                stateless_http=True)
