"""Verify the four-beat grant against a resource that protects *itself*.

Same authorization server, same ticket, same MyTerms contract, same
proof-of-possession RPT as the gateway path — but the request goes straight to
alice-vault-mcp, with no gateway and no ext_authz service anywhere in it. Run
with ENFORCEMENT_MODE=embedded.

The one difference is beat 1's envelope. A gateway answers `401 +
WWW-Authenticate: UMA`; a resource enforcing in-process has no status line, so
it raises a JSON-RPC error carrying the same as_uri, ticket and
resource_metadata. This script parses that instead, and everything downstream
is unchanged — which is the point being demonstrated.
"""

import json
import os
import sys
import threading
import time

import httpx

sys.path.insert(0, "/driver/lib")
from uma4a_grant import AgentKeys, GrantDenied, run_grant, signed_headers  # noqa: E402

VAULT = os.environ.get("VAULT_URL", "http://alice-vault-mcp:9020/mcp")
AS_INTERNAL = os.environ.get("AS_INTERNAL", "https://alice-as.uma.lab")
KEYCLOAK = os.environ.get("KEYCLOAK", "https://keycloak.uma.lab")
# The signature covers the resource's canonical public authority, not the
# transport hop this script happens to dial.
AUTHORITY = os.environ.get("UMA_EXPECTED_AUTHORITY", "gateway.uma.lab")
PATH = "/mcp"
UMA_CHALLENGE = -32001

META = {
    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
    "io.modelcontextprotocol/clientCapabilities": {},
    "io.modelcontextprotocol/clientInfo": {"name": "u4a-embedded-check", "version": "0.1"},
}


def say(msg: str) -> None:
    print(f"   {msg}", flush=True)


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
    r = client.post(VAULT, json={"jsonrpc": "2.0", "method": method, "id": 1, "params": p},
                    headers=h, timeout=30.0)
    body = r.text
    for line in body.splitlines():
        if line.startswith("data:"):
            body = line[5:].strip()
    return json.loads(body)


def owner_token(client: httpx.Client) -> str:
    r = client.post(f"{KEYCLOAK}/realms/alice/protocol/openid-connect/token",
                    data={"grant_type": "password", "client_id": "meridian-portal",
                          "username": "alice", "password": os.environ.get("ALICE_PASSWORD", "alice-demo")},
                    timeout=10.0)
    r.raise_for_status()
    return r.json()["access_token"]


def approve_in_background(client: httpx.Client) -> None:
    """Stand in for Alice's portal tap."""
    def run():
        hdrs = {"Authorization": f"Bearer {owner_token(client)}"}
        for _ in range(40):
            time.sleep(1.5)
            try:
                pending = client.get(f"{AS_INTERNAL}/owner/pending", headers=hdrs, timeout=10.0).json()
            except httpx.HTTPError:
                continue
            if pending:
                p = pending[0]
                say(f"[simulated-alice] approving {p['kind']} {p['family']}")
                client.post(f"{AS_INTERNAL}/owner/pending/{p['family']}/decision",
                            json={"decision": "approved"}, headers=hdrs, timeout=10.0)
                return
    threading.Thread(target=run, daemon=True).start()


def main() -> int:
    ca = "/driver/rootCA.pem"
    with httpx.Client(verify=ca) as client:
        print("\n== Beat 0: the resource advertises that it enforces a grant ==")
        d = rpc(client, "server/discover", {})
        exts = d.get("result", {}).get("capabilities", {}).get("extensions", {}) or {}
        mine = exts.get("dev.uma4agents/uma-enforcement")
        if not mine:
            print("FAIL: the vault does not advertise UMA enforcement")
            return 1
        say(f"capabilities.extensions names the AS: {mine['authorization_servers']}")
        say(f"protocol negotiated: {d['result']['supportedVersions']}")

        print("\n== Beat 1: unauthorized tools/call, straight to the resource ==")
        r = rpc(client, "tools/call", {"name": "get_positions", "arguments": {}})
        err = r.get("error") or {}
        if err.get("code") != UMA_CHALLENGE:
            print(f"FAIL: expected {UMA_CHALLENGE}, got {json.dumps(r)[:300]}")
            return 1
        ch = err["data"]
        say(f"challenged in-band: ticket {ch['ticket'][:18]}…, AS {ch['as_uri']}")
        say("no gateway and no ext_authz service in this path")

        print("\n== Beats 2-4: the same negotiation at Alice's AS ==")
        keys = AgentKeys.load_or_create("/driver/keys/embedded-check.pem")
        approve_in_background(client)

        def approve_terms(template: dict) -> bool:
            say(f"terms proffered: {template['purpose']} "
                f"(expires {template['expires_in']}s)")
            return True

        try:
            rpt = run_grant(client, ch["as_uri"], ch["ticket"], keys, approve_terms,
                            on_status=say)
        except GrantDenied as exc:
            print(f"FAIL: grant denied: {exc}")
            return 1
        say("grant issued — proof-of-possession RPT in hand")

        print("\n== The authorized call, enforced in-process ==")
        hdrs = signed_headers("POST", AUTHORITY, PATH, rpt, keys)
        r = rpc(client, "tools/call", {"name": "get_positions", "arguments": {}}, hdrs)
        if "error" in r:
            print(f"FAIL: authorized call rejected: {json.dumps(r['error'])[:300]}")
            return 1
        text = r["result"]["content"][0]["text"]
        say("data received: " + json.dumps(json.loads(text))[:110] + "…")

        print("\n== And a forged signature still fails, in-process ==")
        forged = dict(hdrs)
        forged["Signature"] = "sig1=:" + "A" * 86 + ":"
        r = rpc(client, "tools/call", {"name": "get_positions", "arguments": {}}, forged)
        if "error" not in r:
            print("FAIL: a forged signature was accepted")
            return 1
        say(f"rejected: {r['error']['message'][:70]}")

    print("\nPASS: a resource enforced its owner's UMA policy with no gateway")
    return 0


if __name__ == "__main__":
    sys.exit(main())
