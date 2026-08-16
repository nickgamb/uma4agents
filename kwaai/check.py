"""Headless check of the personal-AI binding.

Same thing `make kwaai-host` does interactively, with a host that answers from
a script instead of asking a person — so the binding is something CI can fail
on rather than something you have to watch.

The agent side is `float_check`'s: an unauthorized call, a challenge, terms, a
signed agreement, and a grant. The difference is who answers the pend. Here it
is the ability, holding her key inside a stand-in personal AI.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "ability"))
sys.path.insert(0, "/driver/lib")

import httpx  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402

from u4a_authority import OwnerAuthority, Request  # noqa: E402
from uma4a_grant import AgentKeys, GrantDenied, run_grant, signed_headers  # noqa: E402

VAULT = os.environ.get("VAULT_URL", "http://alice-vault.local:9020/mcp")
AUTHORITY_URL = os.environ.get("AS_URL", "http://uma-as:9000")
AUTHORITY_NAME = os.environ.get("UMA_AS_OWNER_AUTHORITY", "alice-as.local")
RESOURCE_AUTHORITY = os.environ.get("UMA_EXPECTED_AUTHORITY", "alice-vault.local:9020")
KEY_PATH = os.environ.get("UMA4A_OWNER_KEY", "/keys/owner-ed25519.pem")
UMA_CHALLENGE = -32001

META = {
    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
    "io.modelcontextprotocol/clientCapabilities": {},
    "io.modelcontextprotocol/clientInfo": {"name": "u4a-kwaai-check", "version": "0.1"},
}

asked: list[Request] = []


class ScriptedHost:
    """A personal AI with a script where its person would be."""

    def __init__(self, key_path: str) -> None:
        with open(key_path, "rb") as fh:
            self._key = serialization.load_pem_private_key(fh.read(), password=None)

    def sign(self, payload: bytes) -> bytes:
        return self._key.sign(payload)

    def public_key_pem(self) -> bytes:
        return self._key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo)

    def ask(self, request: Request) -> bool:
        asked.append(request)
        print(f"   [personal AI] asking her: {request.summary()}", flush=True)
        return True

    def log(self, event: str, detail: dict) -> None:
        if event == "authority.unreachable":
            return
        print(f"   [personal AI] {event} {json.dumps(detail)[:90]}", flush=True)


def rpc(client: httpx.Client, method: str, params: dict, headers=None) -> dict:
    p = dict(params)
    p["_meta"] = META
    h = {"content-type": "application/json",
         "accept": "application/json, text/event-stream",
         "MCP-Protocol-Version": "2026-07-28",
         "Mcp-Method": method}
    if method == "tools/call":
        h["Mcp-Name"] = params.get("name", "")
    h.update(headers or {})
    r = client.post(VAULT, json={"jsonrpc": "2.0", "method": method, "id": 1,
                                 "params": p}, headers=h, timeout=30.0)
    body = r.text
    for line in body.splitlines():
        if line.startswith("data:"):
            body = line[5:].strip()
    return json.loads(body)


def main() -> int:
    host = ScriptedHost(KEY_PATH)
    ability = OwnerAuthority(host=host, authority_url=AUTHORITY_URL,
                             authority_name=AUTHORITY_NAME)

    print("\n== Her personal AI comes up and takes hold of her authority ==")
    stop = False
    threading.Thread(target=lambda: ability.run(1.0, lambda: stop),
                     daemon=True).start()
    print("   holding her key; nothing else was configured")

    with httpx.Client() as client:
        print("\n== Somebody else's agent asks for something of hers ==")
        r = rpc(client, "tools/call", {"name": "get_positions", "arguments": {}})
        err = r.get("error") or {}
        if err.get("code") != UMA_CHALLENGE:
            print(f"FAIL: expected a challenge, got {json.dumps(r)[:200]}")
            return 1
        ch = err["data"]
        print(f"   refused, with a ticket and an address: {ch['as_uri']}")

        keys = AgentKeys.load_or_create("/driver/keys/kwaai-check.pem")
        try:
            rpt = run_grant(client, ch["as_uri"], ch["ticket"], keys,
                            lambda t: True,
                            on_status=lambda m: print(f"   [agent] {m}", flush=True))
        except GrantDenied as exc:
            print(f"FAIL: grant denied: {exc}")
            return 1

        print("\n== And the call goes through ==")
        hdrs = signed_headers("POST", RESOURCE_AUTHORITY, "/mcp", rpt, keys)
        r = rpc(client, "tools/call", {"name": "get_positions", "arguments": {}}, hdrs)
        if "error" in r:
            print(f"FAIL: authorized call rejected: {json.dumps(r['error'])[:200]}")
            return 1
        print("   data received")

    time.sleep(0.5)
    stop = True

    if not asked:
        print("FAIL: the personal AI was never asked to decide anything")
        return 1
    print(f"\n   she was asked {len(asked)} time(s): "
          f"{', '.join(a.kind for a in asked)}")
    print("\nPASS: a personal AI held the owner's key and answered for her.")
    print("      Nothing about the grant, the terms or the token changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
