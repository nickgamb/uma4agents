"""Minimal MCP streamable-http client for the portal backend.

Alice's portal reads her own vault directly (she owns it) — the gateway and
the grant loop exist for *other people's* agents, not for Alice's first-party
UI. Same MCP server, same fixtures, real protocol path.
"""

import json

import httpx


class VaultError(Exception):
    """The vault refused a call or could not answer it. `status` is what the
    portal should report: 400 when the vault refused the input, 502 otherwise."""

    def __init__(self, reason: str, status: int = 502):
        super().__init__(reason)
        self.status = status


class VaultClient:
    def __init__(self, url: str):
        self.url = url
        self._id = 0

    async def _call(self, client: httpx.AsyncClient, session_id: str | None,
                    method: str, params: dict | None = None,
                    notification: bool = False):
        self._id += 1
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        if not notification:
            msg["id"] = self._id
        headers = {"accept": "application/json, text/event-stream",
                   "content-type": "application/json"}
        if session_id:
            headers["mcp-session-id"] = session_id
        r = await client.post(self.url, json=msg, headers=headers)
        sid = r.headers.get("mcp-session-id", session_id)
        payload = None
        if "text/event-stream" in r.headers.get("content-type", ""):
            for line in r.text.splitlines():
                if line.startswith("data:"):
                    payload = json.loads(line[5:].strip())
                    break
        elif r.content:
            payload = r.json()
        return sid, payload

    async def call_tool(self, tool: str, args: dict | None = None) -> dict:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                sid, _ = await self._call(
                    client, None, "initialize",
                    {"protocolVersion": "2025-03-26", "capabilities": {},
                     "clientInfo": {"name": "alice-portal", "version": "1.0"}},
                )
                await self._call(client, sid, "notifications/initialized", {}, notification=True)
                _, payload = await self._call(
                    client, sid, "tools/call", {"name": tool, "arguments": args or {}}
                )
        except httpx.HTTPError as e:
            raise VaultError(f"The vault did not answer: {type(e).__name__}.") from e
        except ValueError as e:
            raise VaultError("The vault's answer was not JSON-RPC.") from e
        if not isinstance(payload, dict):
            raise VaultError("The vault sent back nothing.")
        if "error" in payload:
            raise VaultError(payload["error"].get("message") or "The vault refused the call.")
        result = payload.get("result") or {}
        content = result.get("content") or [{}]
        text = content[0].get("text", "")
        if result.get("isError"):
            # A tool that raised: its message is the reason, e.g. an unknown side.
            raise VaultError(text or f"{tool} failed.", status=400)
        try:
            return json.loads(text)
        except ValueError as e:
            raise VaultError(f"{tool} returned something that is not JSON.") from e
