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
UMA_DENIED = -32002

META = {
    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
    "io.modelcontextprotocol/clientCapabilities": {},
    "io.modelcontextprotocol/clientInfo": {"name": "u4a-embedded-check", "version": "0.1"},
}


def say(msg: str) -> None:
    print(f"   {msg}", flush=True)


def rpc(client: httpx.Client, method: str, params: dict, headers=None,
        routing: bool = True) -> dict:
    p = dict(params)
    p["_meta"] = META
    h = {"content-type": "application/json",
         "accept": "application/json, text/event-stream",
         "MCP-Protocol-Version": "2026-07-28"}
    if routing:
        h["Mcp-Method"] = method
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
            except (httpx.HTTPError, ValueError):
                # A reply that is not JSON is as transient as one that never
                # arrived: an edge still routing, a proxy's error page. Caught
                # only as the former, one such reply ended the thread and left
                # the agent waiting for an answer nobody was going to give.
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
        rem = ch.get("authorization_remediation") or {}
        if (rem.get("authorization_server") != ch["as_uri"]
                or rem.get("ticket") != ch["ticket"]
                or not rem.get("authorization_details")):
            print(f"FAIL: the remediation object does not name the authorization "
                  f"server and the ticket: {json.dumps(rem)[:200]}")
            return 1
        say("the remediation object names the authorization server and the ticket")

        print("\n== What the in-process host refuses, and how ==")
        # Every refusal that is not a challenge arrives as -32002. A bearer
        # token is the wrong scheme; a header naming an open method over a
        # body naming a protected one is two parsers disagreeing; and on
        # 2026-07-28 the routing headers are required, not merely checked.
        r = rpc(client, "tools/call", {"name": "get_positions", "arguments": {}},
                {"Authorization": "Bearer not-a-pop-token"})
        if (r.get("error") or {}).get("code") != UMA_DENIED:
            print(f"FAIL: a bearer token was not refused as -32002: {json.dumps(r)[:200]}")
            return 1
        say("a refusal that is not a challenge arrives as -32002")
        # The next three are refused by whichever layer sees them first. In
        # this host the MCP SDK reconciles the routing headers against the
        # body and validates Origin before the extension runs, and refuses
        # with its own codes; the enforcement core makes the same refusals
        # for a host that does not (make pep-test). What is asserted here is
        # that none of them reaches a challenge, which is what an attacker
        # steering the headers would be after.
        def refused(r: dict) -> str | None:
            code = (r.get("error") or {}).get("code")
            if code is None or code == UMA_CHALLENGE:
                return None
            return "the enforcement core" if code == UMA_DENIED else f"the MCP host ({code})"

        r = rpc(client, "tools/call", {"name": "get_positions", "arguments": {}},
                {"Mcp-Method": "tools/list"})
        if not (by := refused(r)):
            print(f"FAIL: a steered Mcp-Method was not refused: {json.dumps(r)[:200]}")
            return 1
        say(f"a header naming an open method over a body naming a protected one is refused, by {by}")
        r = rpc(client, "tools/call", {"name": "get_positions", "arguments": {}},
                routing=False)
        if not (by := refused(r)):
            print(f"FAIL: a tools/call without routing headers was not refused: "
                  f"{json.dumps(r)[:200]}")
            return 1
        say(f"a tools/call with no routing headers on 2026-07-28 is refused, by {by}")
        r = rpc(client, "tools/call", {"name": "get_positions", "arguments": {}},
                {"Origin": "https://evil.example"})
        if not (by := refused(r)):
            print(f"FAIL: a foreign Origin was not refused: {json.dumps(r)[:200]}")
            return 1
        say(f"a request from an origin the resource does not serve is refused, by {by}")

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

        print("\n== A single-use grant: the forged replay comes first ==")
        # The order the profile makes normative. A replay with a garbage
        # signature is refused, and because the grant is spent last rather
        # than at introspection, the one legitimate call still goes through.
        # Then it is spent, and a second legitimate call does not.
        order = {"symbol": "VTI", "side": "buy", "quantity": 1}
        r = rpc(client, "tools/call", {"name": "execute_trade", "arguments": order})
        err = r.get("error") or {}
        if err.get("code") != UMA_CHALLENGE:
            print(f"FAIL: expected a challenge for the trade, got {json.dumps(r)[:200]}")
            return 1
        approve_in_background(client)
        try:
            trade = run_grant(client, err["data"]["as_uri"], err["data"]["ticket"], keys,
                              approve_terms, operation={"tool": "execute_trade",
                                                        "params": order},
                              on_status=say)
        except GrantDenied as exc:
            print(f"FAIL: trade grant denied: {exc}")
            return 1
        thdrs = signed_headers("POST", AUTHORITY, PATH, trade, keys)
        replay = dict(thdrs)
        replay["Signature"] = "sig1=:" + "A" * 86 + ":"
        r = rpc(client, "tools/call", {"name": "execute_trade", "arguments": order}, replay)
        if "error" not in r:
            print("FAIL: a forged replay of a single-use grant was accepted")
            return 1
        say("a forged replay of a single-use grant is refused")
        r = rpc(client, "tools/call", {"name": "execute_trade", "arguments": order}, thdrs)
        if "error" in r:
            print(f"FAIL: the grant was spent by the forged replay: "
                  f"{json.dumps(r['error'])[:200]}")
            return 1
        say("and the grant is still spendable afterwards")
        r = rpc(client, "tools/call", {"name": "execute_trade", "arguments": order}, thdrs)
        if "error" not in r:
            print("FAIL: a single-use grant was spent twice")
            return 1
        say("and spent, it cannot be spent again")

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
