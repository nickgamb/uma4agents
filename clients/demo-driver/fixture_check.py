"""The whole grant, with nothing standing behind it.

This is the same four beats the rest of the lab runs, against a deployment
that has been stripped of everything that is not the protocol:

    no identity provider   Alice signs her own owner-API requests with a key
                           she holds (RFC 9421), so there is no realm, no
                           login and no token to issue
    no database            the authorization server keeps state in memory
    no gateway             the resource enforces in-process
    no certificate         everything is plain http on localhost, so there is
                           no CA to create and no name to trust
    no registration        the resource publishes its metadata and the
                           authority reads it; neither was told about the
                           other beyond one URL

What is left is the part that matters, and it still refuses the calls Alice
has not agreed to. That is the point being demonstrated: the protection does
not depend on the infrastructure underneath it.

Run with `make fixture`.
"""

import json
import os
import sys
import threading
import time

import httpx

sys.path.insert(0, "/driver/lib")
from uma4a_grant import (  # noqa: E402
    AgentKeys, GrantDenied, mcp_call, mcp_json, mcp_meta, run_grant, signed_headers,
)
from uma4a_http_sig import sign as http_sign  # noqa: E402

VAULT = os.environ.get("VAULT_URL", "http://alice-vault-mcp:9020/mcp")
AS = os.environ.get("AS_URL", "http://uma-as:9000")
AUTHORITY = os.environ.get("UMA_EXPECTED_AUTHORITY", "alice-vault.local")
OWNER_AUTHORITY = os.environ.get("UMA_AS_OWNER_AUTHORITY", "alice-as.local")
OWNER_KEY = os.environ.get("UMA4A_OWNER_KEY", "/keys/owner-ed25519.pem")
PATH = "/mcp"
UMA_CHALLENGE = -32001

META = mcp_meta("u4a-fixture-check")


def say(msg: str) -> None:
    print(f"   {msg}", flush=True)


def rpc(client: httpx.Client, method: str, params: dict, headers: dict | None = None) -> dict:
    return mcp_json(mcp_call(client, VAULT, method, params, META, headers))


def owner_key():
    from cryptography.hazmat.primitives import serialization

    with open(OWNER_KEY, "rb") as fh:
        return serialization.load_pem_private_key(fh.read(), password=None)


def owner_call(client: httpx.Client, method: str, path: str, body: dict | None = None):
    """One owner-API request, signed with her key.

    No Authorization header at all — the signature *is* the credential. It
    still covers `authorization`, as an empty string, because the covered
    components are fixed by the profile rather than by what happens to be
    present.
    """
    raw = json.dumps(body).encode() if body is not None else None
    headers = http_sign(method=method, authority=OWNER_AUTHORITY, path=path,
                        authorization="", key=owner_key(), keyid="owner", body=raw)
    if raw is not None:
        headers["Content-Type"] = "application/json"
    return client.request(method, f"{AS}{path}", headers=headers, content=raw,
                          timeout=10.0)


def approve_in_background(client: httpx.Client) -> None:
    """Stand in for Alice tapping approve on whatever surface she uses."""

    def loop() -> None:
        for _ in range(60):
            try:
                r = owner_call(client, "GET", "/owner/pending")
                pending = r.json() if r.status_code < 400 else []
            except Exception:
                pending = []
            for p in pending:
                say(f"[alice, with her own key] approving {p['kind']} {p['family']}")
                owner_call(client, "POST",
                           f"/owner/pending/{p['family']}/decision",
                           {"decision": "approved"})
            time.sleep(1)

    threading.Thread(target=loop, daemon=True).start()


def main() -> int:
    with httpx.Client() as client:
        print("\n== The owner authenticates to her own authority ==")
        r = owner_call(client, "GET", "/owner/policies")
        if r.status_code >= 400:
            print(f"FAIL: owner API refused her signature: {r.status_code} {r.text[:200]}")
            return 1
        tiers = r.json()
        say(f"signed request accepted — {len(tiers)} tiers, no identity provider involved")

        unsigned = client.get(f"{AS}/owner/policies", timeout=10.0)
        if unsigned.status_code != 401:
            print(f"FAIL: an unsigned owner request was not refused ({unsigned.status_code})")
            return 1
        say("an unsigned request to the same endpoint: 401")

        print("\n== Beat 0: the resource says who speaks for it ==")
        d = rpc(client, "server/discover", {})
        exts = d.get("result", {}).get("capabilities", {}).get("extensions", {}) or {}
        mine = exts.get("dev.uma4agents/uma-enforcement")
        if not mine:
            print("FAIL: the vault does not advertise UMA enforcement")
            return 1
        say(f"names its authority: {mine['authorization_servers']}")

        print("\n== Beat 1: an unauthorized call is refused ==")
        r = rpc(client, "tools/call", {"name": "get_positions", "arguments": {}})
        err = r.get("error") or {}
        if err.get("code") != UMA_CHALLENGE:
            print(f"FAIL: expected {UMA_CHALLENGE}, got {json.dumps(r)[:300]}")
            return 1
        ch = err["data"]
        say(f"ticket {ch['ticket'][:18]}…, authority {ch['as_uri']}")

        print("\n== Beats 2-4: terms, signature, grant ==")
        keys = AgentKeys.load_or_create("/driver/keys/fixture-check.pem")
        approve_in_background(client)

        def approve_terms(template: dict) -> bool:
            say(f"terms proffered: {template['purpose']}")
            return True

        try:
            rpt = run_grant(client, ch["as_uri"], ch["ticket"], keys, approve_terms,
                            on_status=say)
        except GrantDenied as exc:
            print(f"FAIL: grant denied: {exc}")
            return 1
        say("grant issued")

        print("\n== The authorized call ==")
        hdrs = signed_headers("POST", AUTHORITY, PATH, rpt, keys)
        r = rpc(client, "tools/call", {"name": "get_positions", "arguments": {}}, hdrs)
        if "error" in r:
            print(f"FAIL: authorized call rejected: {json.dumps(r['error'])[:300]}")
            return 1
        say("data received: "
            + json.dumps(json.loads(r["result"]["content"][0]["text"]))[:100] + "…")

        print("\n== And the refusals still hold ==")
        forged = dict(hdrs)
        forged["Signature"] = "sig1=:" + "A" * 86 + ":"
        r = rpc(client, "tools/call", {"name": "get_positions", "arguments": {}}, forged)
        if "error" not in r:
            print("FAIL: a forged agent signature was accepted")
            return 1
        say(f"forged agent signature: {r['error']['message'][:60]}")

        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        wrong = http_sign(method="GET", authority=OWNER_AUTHORITY,
                          path="/owner/policies", authorization="",
                          key=Ed25519PrivateKey.generate(), keyid="owner")
        r2 = client.get(f"{AS}/owner/policies", headers=wrong, timeout=10.0)
        if r2.status_code != 401:
            print(f"FAIL: a request signed by the wrong key was accepted ({r2.status_code})")
            return 1
        say("owner request signed by a key she did not enrol: 401")

    print("\nPASS: no IdP, no database, no gateway, no certificate — and the")
    print("      owner's policy was still the thing that decided.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
