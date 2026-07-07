"""Minimal MCP streamable-http client for the portal backend.

Alice's portal reads her own vault directly (she owns it) — the gateway and
the grant loop exist for *other people's* agents, not for Alice's first-party
UI. Same MCP server, same fixtures, real protocol path.
"""

import json

import httpx


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
        text = payload["result"]["content"][0]["text"]
        return json.loads(text)
