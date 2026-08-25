"""Two owners. Nothing about them differs but which one it is.

Meridian holds Alice's account and Carol's. Each owner has her own
authorization server, her own signing key, her own identity provider and her
own record, and each is reached at her own resource. Bob's agent negotiates
with both, running the same four beats against different authorities and
getting a separate answer from each.

There is no privileged owner and no special case. Add a third and a
thousandth the same way. What varies between deployments is how many owners
live in one process — one each here, many in one elsewhere — and that is a
packaging choice the grant loop cannot observe. The partition that makes it
safe either way is proven in `lib/test_store.py`, across every accessor on
both backends.

What can only be seen from out here is what crosses processes:

  * the challenge for each owner names her own authority, which is the only
    reason an owner can choose one at all;
  * an authorization server holding one owner refuses everyone else at the
    door rather than serving them and filtering;
  * each authority trusts its own owner's identity provider — one that
    accepts somebody else's tokens for its owner is only partly hers;
  * the same agent, with the same key, negotiates with both and neither
    authority learns anything about the other's decision.

How each of them came to protect anything differs, and deliberately: Alice's
authority holds a secret it was provisioned with, and Carol's holds nothing
and was introduced at runtime. Neither is visible from here, which is the
claim — see `establishment_check.py`, where it is the subject.

Run with `make multi-owner-check`.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid

import httpx

sys.path.insert(0, "/driver/lib")
from uma4a_grant import (  # noqa: E402
    AgentKeys, GrantDenied, mcp_call, mcp_json, mcp_meta, parse_challenge,
    run_grant, signed_headers,
)

GATEWAY = os.environ.get("UMA4A_GATEWAY", "https://gateway.uma.lab/mcp")
KEYCLOAK = os.environ.get("UMA4A_OIDC", "https://keycloak.uma.lab")
CA = os.environ.get("UMA4A_CACERT", "/driver/rootCA.pem")
KEYS = "/driver/keys"
RUN = uuid.uuid4().hex[:8]
META = mcp_meta("u4a-multi-owner-check")

# Two owners, described identically. Adding a third is another row.
OWNERS = {
    "alice": {
        "as": os.environ.get("UMA4A_AS", "https://alice-as.uma.lab"),
        "realm": "alice",
        "password": os.environ.get("ALICE_PASSWORD", "alice-demo"),
    },
    "carol": {
        "as": os.environ.get("UMA4A_CAROL_AS", "https://carol-as.uma.lab"),
        "realm": "carol",
        "password": os.environ.get("CAROL_PASSWORD", "carol-demo"),
    },
}

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"   {'ok  ' if ok else 'FAIL'} {name}"
          + (f" — {detail}" if detail and not ok else ""), flush=True)


def hdrs(c: httpx.Client, owner: str) -> dict:
    o = OWNERS[owner]
    r = c.post(f"{KEYCLOAK}/realms/{o['realm']}/protocol/openid-connect/token",
               data={"grant_type": "password", "client_id": "meridian-portal",
                     "username": owner, "password": o["password"]},
               timeout=15.0)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def ensure_resource_server(c: httpx.Client, owner: str) -> None:
    """Whatever this owner's authority needs before it will protect anything.

    An authority provisioned alongside the resource server already knows it.
    One that is the owner's own has to be introduced, and she has to say yes
    — so a call is made to provoke the introduction and she answers it from
    her portal, exactly as she would the first time she linked the account.

    Which of those applies is not something this check decides or asserts on;
    it is a property of how the deployment was put together, and the point of
    everything below is that from here the two are indistinguishable.
    `establishment_check.py` is where the difference is the subject.
    """
    o = OWNERS[owner]
    for _ in range(8):
        registry = {r["client_id"]: r for r in
                    c.get(f"{o['as']}/owner/resource-servers",
                          headers=hdrs(c, owner), timeout=15.0).json()}
        if any(r.get("status") == "active" for r in registry.values()):
            return
        pending = [cid for cid, r in registry.items()
                   if r.get("status") == "pending"]
        if pending:
            for cid in pending:
                c.post(f"{o['as']}/owner/resource-servers/decision",
                       json={"client_id": cid, "decision": "approved"},
                       headers=hdrs(c, owner), timeout=15.0)
            continue
        mcp_call(c, f"{GATEWAY}/{owner}", "tools/call",
                 {"name": "get_positions", "arguments": {}}, META)
        time.sleep(1.0)


def negotiate(c: httpx.Client, owner: str,
              agent: AgentKeys) -> tuple[bool, str, dict | None]:
    """Bob's agent, against one owner. Identical for every owner."""
    o = OWNERS[owner]
    r = mcp_call(c, f"{GATEWAY}/{owner}", "tools/call",
                 {"name": "get_positions", "arguments": {}}, META)
    ch = parse_challenge(r.headers.get("www-authenticate", ""))
    if ch is None:
        return False, f"no challenge: {r.status_code} {r.text[:160]}", None

    answered = {"v": False}

    def be_her(msg: str) -> None:
        if "has been asked" in msg and not answered["v"]:
            answered["v"] = True
            for p in c.get(f"{o['as']}/owner/pending", headers=hdrs(c, owner),
                           timeout=15.0).json():
                c.post(f"{o['as']}/owner/pending/{p['family']}/decision",
                       json={"decision": "approved"},
                       headers=hdrs(c, owner), timeout=15.0)

    try:
        rpt = run_grant(c, ch.as_uri, ch.ticket, agent, lambda t: True,
                        on_status=be_her, max_wait_s=90)
    except GrantDenied as exc:
        return False, str(exc)[:160], None

    # Spend it, and keep what came back. A check that stops at "granted"
    # cannot tell one owner's vault from another's, which is the whole
    # question when a resource server holds more than one.
    hdr = signed_headers("POST", "gateway.uma.lab", f"/mcp/{owner}", rpt, agent)
    r = mcp_call(c, f"{GATEWAY}/{owner}", "tools/call",
                 {"name": "get_positions", "arguments": {}}, META, headers=hdr)
    # MCP wraps a tool result as text content inside the JSON-RPC result.
    try:
        payload = mcp_json(r)
        data = json.loads(payload["result"]["content"][0]["text"])
    except (KeyError, IndexError, ValueError, TypeError):
        return True, ch.as_uri, None
    return True, ch.as_uri, data


def main() -> int:
    names = list(OWNERS)
    with httpx.Client(verify=CA, timeout=30.0) as c:
        print(f"\n== {len(names)} owners, one resource server ==", flush=True)
        for owner in names:
            ensure_resource_server(c, owner)

        # --- each owner is reached the same way, at her own address --------
        named = {}
        for owner in names:
            r = mcp_call(c, f"{GATEWAY}/{owner}", "tools/call",
                         {"name": "get_positions", "arguments": {}}, META)
            ch = parse_challenge(r.headers.get("www-authenticate", ""))
            named[owner] = ch.as_uri if ch else None
            check(f"{owner}: her resource challenges, and names her authority",
                  ch is not None and ch.as_uri == OWNERS[owner]["as"],
                  f"{r.status_code} named {named[owner]}")
        check("no two owners are sent to the same authority",
              len(set(named.values())) == len(names),
              f"{named}")

        # --- an authority holds exactly one owner ---------------------------
        for owner in names:
            others = [x for x in names if x != owner]
            worst = max(
                c.get(f"{OWNERS[owner]['as']}/owner/policies",
                      headers=hdrs(c, x), timeout=15.0).status_code
                for x in others)
            check(f"{owner}'s authority will not answer {', '.join(others)}",
                  worst in (401, 403), f"got {worst}")
            check(f"and does answer {owner}",
                  c.get(f"{OWNERS[owner]['as']}/owner/policies",
                        headers=hdrs(c, owner),
                        timeout=15.0).status_code == 200)

        # --- and trusts only her identity provider --------------------------
        for owner in names:
            others = [x for x in names if x != owner]
            worst = max(
                c.post(f"{KEYCLOAK}/realms/{OWNERS[owner]['realm']}"
                       "/protocol/openid-connect/token",
                       data={"grant_type": "password",
                             "client_id": "meridian-portal", "username": x,
                             "password": OWNERS[x]["password"]},
                       timeout=15.0).status_code
                for x in others)
            check(f"{owner}'s identity provider cannot mint anybody else",
                  worst >= 400, f"got {worst}")

        # --- her policy and her terms name her, and nobody else -------------
        tiers = {o: c.get(f"{OWNERS[o]['as']}/owner/policies",
                          headers=hdrs(c, o), timeout=15.0).json()
                 for o in names}
        res = {o: {r for t in tiers[o].values() for r in t["resources"]}
               for o in names}
        check("every owner's tiers name her own resources",
              all(all(r.startswith(f"{o}-vault/") for r in res[o])
                  for o in names),
              f"{ {o: sorted(res[o]) for o in names} }")
        check("and no resource is claimed by two owners",
              len(set().union(*res.values())) == sum(len(res[o]) for o in names))

        tpl = {o: next(iter(tiers[o].values()))["terms"]["template_id"]
               for o in names}
        check("terms template ids name their owner",
              all(tpl[o].startswith(f"{o}/") for o in names), f"{tpl}")
        check("and an agent holding no token can dereference them",
              all(c.get(f"{OWNERS[o]['as']}/terms/{tpl[o]}",
                        timeout=15.0).status_code == 200 for o in names))

        keys = {o: {k.get("x") for k in
                    c.get(f"{OWNERS[o]['as']}/jwks",
                          timeout=15.0).json()["keys"]} for o in names}
        check("every authority signs with its own key",
              len({frozenset(k) for k in keys.values()}) == len(names),
              "two authorities published the same key")

        # --- the same agent negotiates with each ----------------------------
        before = {o: len(c.get(f"{OWNERS[o]['as']}/owner/ledger",
                               headers=hdrs(c, o), timeout=15.0).json())
                  for o in names}
        agent = AgentKeys.load_or_create(f"{KEYS}/mo-{RUN}")
        got = {}
        for owner in names:
            ok, detail, body = negotiate(c, owner, agent)
            check(f"Bob's agent negotiates with {owner} and is granted",
                  ok, detail)
            got[owner] = body

        # The holdings themselves, not just the verdict.
        symbols = {o: sorted(
            p.get("symbol") for p in ((got[o] or {}).get("positions") or []))
            for o in names}
        check("each owner's agent is served her own holdings",
              all(symbols[o] for o in names)
              and len({tuple(symbols[o]) for o in names}) == len(names),
              f"{symbols}")

        after = {o: c.get(f"{OWNERS[o]['as']}/owner/ledger",
                          headers=hdrs(c, o), timeout=15.0).json()
                 for o in names}
        for owner in names:
            check(f"{owner}'s record grew by her own negotiation",
                  len(after[owner]) > before[owner],
                  "nothing was written")
        fams = {o: {e.get("family") for e in after[o]} for o in names}
        overlap = set()
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                overlap |= (fams[a] & fams[b]) - {None, "-"}
        # A negotiation over a resource one of them owns must never appear in
        # another's record. A negotiation over a resource they hold *jointly*
        # must appear in both, and that is not a leak but the point of it —
        # each holder keeps her own record of what she was asked and what she
        # answered. So the property is not "no overlap" but "nothing overlaps
        # except the negotiations that belong to all of them". See
        # docs/JOINT.md; `jnt_` is a tally's family prefix.
        leaked = {f for f in overlap if not str(f).startswith("jnt_")}
        check("and no negotiation over one owner's resources reaches another's record",
              not leaked, f"shared: {sorted(leaked)}")

    print()
    print(f"{len(PASS)} passed, {len(FAIL)} failed", flush=True)
    if FAIL:
        for f in FAIL:
            print(f"  - {f}")
        return 1
    print(f"\nPASS: {len(names)} owners of one resource server, each with her own")
    print("      authority, key, identity provider and record. The same agent")
    print("      ran the same four beats against each of them, and neither")
    print("      authority learned anything about the other's decision.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
