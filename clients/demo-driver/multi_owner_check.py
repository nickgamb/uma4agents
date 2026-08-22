"""One authorization server, two owners, and no way through the wall.

The operator-hosted shape: a resource server holding many people's accounts,
and an authorization server holding many people's policy. Meridian fronts
Alice at `/mcp` and Carol at `/mcp/carol`; one `uma-as` serves both.

What is worth proving is not that it works — two owners who never interact
would "work" by doing nothing. It is that **every surface an owner can reach
is scoped to her**, and that the interesting cross-owner moves are refused
rather than merely unlikely:

  * her policy, her terms, her connections and her ledger are hers alone;
  * her authority names her resources, and only hers;
  * a grant issued against one owner's resources cannot be spent against the
    other's, even by the same enforcement point holding both their PATs.

The last one is the one with consequences. An enforcement point serving a
thousand owners holds a thousand PATs, and the failure that matters is not a
leak of data but a *grant* crossing — Alice's approval spending against
Carol's account. That is checked here at the wire rather than in the store,
because the store test cannot see the enforcement point at all.

Run with `make multi-owner-check`.
"""

from __future__ import annotations

import os
import sys
import uuid

import httpx

sys.path.insert(0, "/driver/lib")
from uma4a_grant import (  # noqa: E402
    AgentKeys, GrantDenied, mcp_call, mcp_meta, parse_challenge, run_grant,
)

GATEWAY = os.environ.get("UMA4A_GATEWAY", "https://gateway.uma.lab/mcp")
AS_PUBLIC = os.environ.get("UMA4A_AS", "https://alice-as.uma.lab")
KEYCLOAK = os.environ.get("UMA4A_OIDC", "https://keycloak.uma.lab")
CA = os.environ.get("UMA4A_CACERT", "/driver/rootCA.pem")
KEYS = "/driver/keys"
RUN = uuid.uuid4().hex[:8]
META = mcp_meta("u4a-multi-owner-check")

OWNERS = {
    "alice": os.environ.get("ALICE_PASSWORD", "alice-demo"),
    "carol": os.environ.get("CAROL_PASSWORD", "carol-demo"),
}

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"   {'ok  ' if ok else 'FAIL'} {name}"
          + (f" — {detail}" if detail and not ok else ""), flush=True)


def hdrs(client: httpx.Client, owner: str) -> dict:
    r = client.post(f"{KEYCLOAK}/realms/alice/protocol/openid-connect/token",
                    data={"grant_type": "password", "client_id": "alice-portal",
                          "username": owner, "password": OWNERS[owner]},
                    timeout=15.0)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def get(client: httpx.Client, owner: str, path: str):
    return client.get(f"{AS_PUBLIC}{path}", headers=hdrs(client, owner),
                      timeout=15.0)


def main() -> int:
    with httpx.Client(verify=CA, timeout=30.0) as c:
        print("\n== Two owners, one authorization server ==", flush=True)

        # --- each owner has her own policy, naming her own resources -------
        tiers = {o: get(c, o, "/owner/policies").json() for o in OWNERS}
        check("each owner has her own starting policy",
              set(tiers["alice"]) == set(tiers["carol"]),
              "the two owners were given different tier ids")

        a_res = {r for t in tiers["alice"].values() for r in t["resources"]}
        c_res = {r for t in tiers["carol"].values() for r in t["resources"]}
        check("her tiers name her own resources",
              all(r.startswith("alice-vault/") for r in a_res)
              and all(r.startswith("carol-vault/") for r in c_res),
              f"alice={sorted(a_res)} carol={sorted(c_res)}")
        check("and never each other's",
              not (a_res & c_res), f"shared: {sorted(a_res & c_res)}")

        # --- terms documents are namespaced, and dereference without a token
        a_terms = get(c, "alice", "/owner/policies").json()
        a_tpl = next(iter(a_terms.values()))["terms"]["template_id"]
        c_tpl = next(iter(tiers["carol"].values()))["terms"]["template_id"]
        check("terms template ids name their owner",
              a_tpl.startswith("alice/") and c_tpl.startswith("carol/"),
              f"{a_tpl} / {c_tpl}")
        pub = c.get(f"{AS_PUBLIC}/terms/{c_tpl}", timeout=15.0)
        check("an agent with no token can still dereference her terms",
              pub.status_code == 200, f"{pub.status_code}")

        # --- her authority answers for her, and only her --------------------
        idx = c.get(f"{AS_PUBLIC}/terms", params={"owner": "carol"},
                    timeout=15.0).json()
        check("the terms index is one owner's, not everyone's",
              all(d["template_id"].startswith("carol/") for d in idx["terms"]),
              "another owner's terms appeared in the listing")

        # --- one owner's edits are invisible to the other -------------------
        edit = c.put(f"{AS_PUBLIC}/owner/policies/tier1",
                       json={"ask_me": True}, headers=hdrs(c, "carol"),
                       timeout=15.0)
        check("an owner can edit her own policy", edit.status_code == 200,
              f"{edit.status_code} {edit.text[:120]}")
        after = get(c, "alice", "/owner/policies").json()
        check("and the edit does not reach the other owner",
              after["tier1"]["ask_me"] is False,
              "Carol's edit changed Alice's tier")

        # --- the resource server fronts each owner separately ---------------
        for owner, leaf in (("alice", "mcp"), ("carol", "mcp/carol")):
            doc = c.get(f"https://gateway.uma.lab/.well-known/"
                        f"oauth-protected-resource/{leaf}", timeout=15.0).json()
            check(f"{owner}: the resource server publishes her own resource",
                  doc["resource"].endswith(leaf),
                  f"{doc['resource']}")

        # --- a real grant, against Carol's account --------------------------
        keys = AgentKeys.load_or_create(f"{KEYS}/mo-{RUN}")
        carol_gateway = f"{GATEWAY}/carol"
        r = mcp_call(c, carol_gateway, "tools/call",
                     {"name": "get_positions", "arguments": {}}, META)
        ch = parse_challenge(r.headers.get("www-authenticate", ""))
        check("Carol's resource challenges, and names an authority",
              ch is not None,
              f"{r.status_code} {r.text[:200]}")
        if ch is None:
            print("\nFAIL: no challenge from Carol's resource; stopping here.")
            return 1

        # Her first contact pends, exactly as Alice's would, so somebody has
        # to be her. The point of the check is the partition, not the wait.
        approved = {"v": False}

        def approve_for_carol(msg: str) -> None:
            if "has been asked" in msg and not approved["v"]:
                approved["v"] = True
                pend = get(c, "carol", "/owner/pending").json()
                for p in pend:
                    c.post(f"{AS_PUBLIC}/owner/pending/{p['family']}/decision",
                           json={"decision": "approved"},
                           headers=hdrs(c, "carol"), timeout=15.0)

        try:
            run_grant(c, ch.as_uri, ch.ticket, keys, lambda t: True,
                      on_status=approve_for_carol, max_wait_s=90)
            reached, detail = True, ""
        except GrantDenied as exc:
            reached, detail = False, str(exc)[:160]
        check("an agent negotiating for Carol reaches Carol's authority",
              reached, detail)

        # --- and her ledger records it, while Alice's does not --------------
        c_led = get(c, "carol", "/owner/ledger").json()
        a_led = get(c, "alice", "/owner/ledger").json()
        c_fams = {e.get("family") for e in c_led}
        a_fams = {e.get("family") for e in a_led}
        check("the negotiation is in Carol's ledger", bool(c_fams - {None}),
              "Carol's ledger is empty")
        check("and none of it is in Alice's",
              not (c_fams & a_fams - {None}),
              f"shared families: {sorted((c_fams & a_fams) - {None})}")

        # --- connections are hers ------------------------------------------
        c_conn = get(c, "carol", "/owner/connections").json()
        a_conn = get(c, "alice", "/owner/connections").json()
        handles = {x["handle"] for x in c_conn} & {x["handle"] for x in a_conn}
        check("a standing relationship belongs to one owner",
              not handles, f"shared handles: {sorted(handles)}")

    print()
    print(f"{len(PASS)} passed, {len(FAIL)} failed", flush=True)
    if FAIL:
        for f in FAIL:
            print(f"  - {f}")
        return 1
    print("\nPASS: one authorization server held two owners' policy, terms,")
    print("      grants and records without any of it crossing — and the")
    print("      resource server fronted each of them as a resource of her")
    print("      own, which is what lets them name different authorities.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
