"""The authority rotates its signing key under live grants.

Two phases around a recreate of uma-as that `make rotation-check` performs:

  --phase before   negotiate a grant and keep it
  --phase after    the kept grant still spends; a fresh one carries the new
                   kid and spends too; both kids are published; and the
                   resource server accepted a pull signed with the new key
                   without waiting out its key cache

Everything a rotation has to keep true, asserted from where an agent stands.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import threading
import time

import httpx

sys.path.insert(0, "/driver/lib")
from uma4a_grant import (  # noqa: E402
    AgentKeys, GrantDenied, mcp_call, mcp_meta, parse_challenge, run_grant,
    signed_headers,
)

AS_PUBLIC = os.environ.get("UMA4A_AS", "https://alice-as.uma.lab")
GATEWAY = os.environ.get("UMA4A_GATEWAY", "https://gateway.uma.lab/mcp")
GATEWAY_AUTHORITY = os.environ.get("UMA4A_GATEWAY_AUTHORITY", "gateway.uma.lab")
KEYCLOAK = os.environ.get("KEYCLOAK", "https://keycloak.uma.lab")
MCP_PATH = "/mcp"
KEYS = "/driver/keys"
HELD = f"{KEYS}/rotation-held.json"
META = mcp_meta("u4a-rotation-check")
PASSED, FAILED = [], []


def say(msg: str) -> None:
    print(f"   {msg}", flush=True)


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASSED if ok else FAILED).append(name)
    print(("   ok   " if ok else "   FAIL ") + name + (f" — {detail}" if detail and not ok else ""),
          flush=True)


def owner_hdrs(client: httpx.Client) -> dict:
    r = client.post(f"{KEYCLOAK}/realms/alice/protocol/openid-connect/token",
                    data={"grant_type": "password", "client_id": "meridian-portal",
                          "username": "alice",
                          "password": os.environ.get("ALICE_PASSWORD", "alice-demo")},
                    timeout=15.0)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def approve_in_background(client: httpx.Client) -> None:
    def loop() -> None:
        hdrs = owner_hdrs(client)
        for _ in range(40):
            items = client.get(f"{AS_PUBLIC}/owner/pending", headers=hdrs, timeout=15.0).json()
            for p in items:
                client.post(f"{AS_PUBLIC}/owner/pending/{p['family']}/decision",
                            json={"decision": "approved"}, headers=hdrs, timeout=15.0)
            if items:
                return
            time.sleep(0.5)
    threading.Thread(target=loop, daemon=True).start()


def kid_of(token: str) -> str | None:
    head = token.split(".")[0]
    return json.loads(base64.urlsafe_b64decode(head + "=" * (-len(head) % 4))).get("kid")


def grant(client: httpx.Client, keys: AgentKeys) -> str:
    r = mcp_call(client, GATEWAY, "tools/call", {"name": "get_positions", "arguments": {}}, META)
    ch = parse_challenge(r.headers.get("www-authenticate", ""))
    if ch is None:
        raise SystemExit(f"no challenge: {r.status_code} {r.text[:200]}")
    approve_in_background(client)
    return run_grant(client, ch.as_uri, ch.ticket, keys, lambda t: True,
                     on_status=say, max_wait_s=40)


def spend(client: httpx.Client, keys: AgentKeys, rpt: str) -> httpx.Response:
    return mcp_call(client, GATEWAY, "tools/call", {"name": "get_positions", "arguments": {}},
                    META, headers=signed_headers("POST", GATEWAY_AUTHORITY, MCP_PATH, rpt, keys))


def before(client: httpx.Client) -> int:
    print("\n== Before the rotation: a grant, kept ==")
    keys = AgentKeys.load_or_create(f"{KEYS}/rotation-agent.pem")
    try:
        rpt = grant(client, keys)
    except GrantDenied as exc:
        print(f"FAIL: grant denied: {exc}")
        return 1
    r = spend(client, keys, rpt)
    check("a grant is issued and spends", r.status_code == 200, f"{r.status_code} {r.text[:120]}")
    check("it carries the current kid", kid_of(rpt) == "uma-as-1", str(kid_of(rpt)))
    with open(HELD, "w") as fh:
        json.dump({"rpt": rpt}, fh)
    say("kept for after the rotation")
    return 0


def after(client: httpx.Client) -> int:
    print("\n== After the rotation ==")
    keys = AgentKeys.load_or_create(f"{KEYS}/rotation-agent.pem")
    with open(HELD) as fh:
        held = json.load(fh)["rpt"]

    kids = {k.get("kid") for k in client.get(f"{AS_PUBLIC}/jwks", timeout=15.0).json()["keys"]}
    check("the authority publishes the new key and the retired one",
          kids == {"uma-as-1", "uma-as-2"}, str(sorted(kids)))

    r = spend(client, keys, held)
    check("a grant signed before the rotation still spends",
          r.status_code == 200, f"{r.status_code} {r.text[:120]}")

    try:
        fresh = grant(client, keys)
    except GrantDenied as exc:
        print(f"FAIL: grant after rotation denied: {exc}")
        return 1
    check("a grant issued after it carries the new kid", kid_of(fresh) == "uma-as-2",
          str(kid_of(fresh)))
    r = spend(client, keys, fresh)
    check("and spends too", r.status_code == 200, f"{r.status_code} {r.text[:120]}")

    # The authority signs its pull of the owner's resources with the new key.
    # Listing her resources forces that pull; a resource server that only
    # knew the old key set would refuse it, and her listing would be empty.
    hdrs = owner_hdrs(client)
    listing = client.get(f"{AS_PUBLIC}/owner/resources", headers=hdrs, timeout=30.0).json()
    pulled = [r for r in listing if r.get("registered_via") == "pull"]
    check("the resource server accepted a pull signed with the new key",
          len(pulled) >= 1, f"{len(listing)} resources, {len(pulled)} pulled")
    return 0


def main() -> int:
    phase = sys.argv[sys.argv.index("--phase") + 1] if "--phase" in sys.argv else "before"
    with httpx.Client(verify="/driver/rootCA.pem") as client:
        status = before(client) if phase == "before" else after(client)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if phase == "after" and not FAILED and not status:
        print("\nPASS: the authority rotated its key and nothing it had issued stopped working.")
    return 1 if FAILED else status


if __name__ == "__main__":
    sys.exit(main())
