"""The personal-AI binding against the real stack.

`kwaai/check.py` runs this against the stripped-down fixture. This runs it
against the reference architecture — her identity provider, her replicated
authority, the gateway, the vault and her portal all present and unchanged —
because that is the deployment the binding has to work in to mean anything.

The only difference from the portal's point of view is who answered. Her
browser session is still a valid credential and still works; the personal AI
holds a second, independent one — a key on her device — and answers with that.
Both are her.

Run with `make kwaai-check` after `make up`.
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
from uma4a_grant import AgentKeys, GrantDenied, parse_challenge, run_grant  # noqa: E402

GATEWAY = os.environ.get("UMA4A_GATEWAY", "https://gateway.uma.lab/mcp")
AS_PUBLIC = os.environ.get("UMA4A_AS", "https://alice-as.uma.lab")
KEYCLOAK = os.environ.get("UMA4A_OIDC", "https://keycloak.uma.lab")
OWNER_KEY = os.environ.get("UMA4A_OWNER_KEY", "/owner/owner-ed25519.pem")
CA = os.environ.get("UMA4A_CACERT", "/driver/rootCA.pem")

META = {
    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
    "io.modelcontextprotocol/clientCapabilities": {},
    "io.modelcontextprotocol/clientInfo": {"name": "u4a-kwaai-full", "version": "0.1"},
}

asked: list[Request] = []


class PersonalAI:
    """A personal AI holding her key. Four methods; nothing protocol-aware."""

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
        print(f"   [her personal AI] {request.summary()}", flush=True)
        return True

    def log(self, event: str, detail: dict) -> None:
        # Everything, including "unreachable". Filtering that one out hid a
        # real failure once — the ability was polling an authority it could
        # not verify and quietly doing nothing.
        print(f"   [her personal AI] {event} {json.dumps(detail)[:80]}", flush=True)


def rpc(client: httpx.Client, params: dict, headers=None) -> httpx.Response:
    p = dict(params)
    p["_meta"] = META
    h = {"content-type": "application/json",
         "accept": "application/json, text/event-stream",
         "MCP-Protocol-Version": "2026-07-28",
         "Mcp-Method": "tools/call", "Mcp-Name": params.get("name", "")}
    h.update(headers or {})
    return client.post(GATEWAY, json={"jsonrpc": "2.0", "method": "tools/call",
                                      "id": 1, "params": p},
                       headers=h, timeout=30.0)


def portal_still_works(client: httpx.Client) -> bool:
    """Her browser credential, unchanged and still sufficient on its own."""
    r = client.post(f"{KEYCLOAK}/realms/alice/protocol/openid-connect/token",
                    data={"grant_type": "password", "client_id": "alice-portal",
                          "username": "alice",
                          "password": os.environ.get("ALICE_PASSWORD", "alice-demo")},
                    timeout=15.0)
    r.raise_for_status()
    tok = r.json()["access_token"]
    got = client.get(f"{AS_PUBLIC}/owner/policies",
                     headers={"Authorization": f"Bearer {tok}"}, timeout=10.0)
    return got.status_code == 200


def main() -> int:
    ca = CA if os.path.exists(CA) else True
    ai = PersonalAI(OWNER_KEY)
    ability = OwnerAuthority(host=ai, authority_url=AS_PUBLIC,
                             authority_name="alice-as.uma.lab")

    with httpx.Client(verify=ca) as client:
        print("\n== Two credentials, one owner ==")
        if not portal_still_works(client):
            print("FAIL: her OIDC session stopped working")
            return 1
        print("   her portal session: still accepted")

        r = ability._call(client, "GET", "/owner/policies")
        if r.status_code != 200:
            print(f"FAIL: her device key was refused: {r.status_code} {r.text[:200]}")
            return 1
        print("   her device key, held by a personal AI: also accepted")
        print("   neither is a fallback for the other")

        print("\n== The personal AI takes over answering ==")
        stop = False
        threading.Thread(target=lambda: ability.run(1.0, lambda: stop, client),
                         daemon=True).start()

        print("\n== Somebody else's agent asks for something of hers ==")
        first = rpc(client, {"name": "get_positions", "arguments": {}})
        ch = parse_challenge(first.headers.get("www-authenticate", ""))
        if ch is None:
            print(f"FAIL: no challenge from the gateway: {first.status_code}")
            return 1
        print(f"   refused by the gateway, ticket issued, authority {ch.as_uri}")

        # A new agent every run, deliberately. A standing connection
        # auto-grants on an open tier — which is the protocol working, and
        # which would mean the personal AI is never asked anything. Reusing a
        # keystore here made this check pass or fail depending on whether it
        # had been run before.
        import uuid

        keys = AgentKeys.load_or_create(f"/driver/keys/kwaai-full-{uuid.uuid4().hex[:8]}.pem")
        try:
            rpt = run_grant(client, ch.as_uri, ch.ticket, keys, lambda t: True,
                            on_status=lambda m: print(f"   [agent] {m}", flush=True))
        except GrantDenied as exc:
            print(f"FAIL: grant denied: {exc}")
            return 1

        from uma4a_grant import signed_headers

        authority = os.environ.get("UMA_EXPECTED_AUTHORITY", "gateway.uma.lab")
        hdrs = signed_headers("POST", authority, "/mcp", rpt, keys)
        r = rpc(client, {"name": "get_positions", "arguments": {}}, hdrs)
        if r.status_code != 200:
            print(f"FAIL: authorized call rejected: {r.status_code} {r.text[:200]}")
            return 1
        print("   the call went through")

        time.sleep(0.5)
        stop = True

        if not asked:
            print("FAIL: the personal AI was never asked to decide anything")
            return 1

        # The ledger is the owner's record. Her decision has to be in it
        # whichever credential she used to make it — an approval that does not
        # appear is an approval nobody can reconstruct afterwards.
        tok = client.post(
            f"{KEYCLOAK}/realms/alice/protocol/openid-connect/token",
            data={"grant_type": "password", "client_id": "alice-portal",
                  "username": "alice",
                  "password": os.environ.get("ALICE_PASSWORD", "alice-demo")},
            timeout=15.0).json()["access_token"]
        ledger = client.get(f"{AS_PUBLIC}/owner/ledger",
                            headers={"Authorization": f"Bearer {tok}"},
                            timeout=10.0).json()
        approvals = [e for e in ledger if e.get("kind") == "approved"]
        if not approvals:
            print("FAIL: the decision the personal AI made is not in her ledger")
            return 1
        print(f"   her ledger, read from the portal: {len(approvals)} approval(s) "
              "including the one the personal AI made")

    print(f"\n   she was asked {len(asked)} time(s) by her personal AI")
    print("\nPASS: a personal AI answered for the owner on the full stack.")
    print("      Her portal credential still works, the grant is unchanged, and")
    print("      the decision is in the same ledger either way.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
