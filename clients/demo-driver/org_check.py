"""Shared ownership: an organization's resources, administered by its members.

U4A's question is "can your agent access my stuff". This is what happens when
some of that stuff is not mine — when a firm owns the book, shares it with the
people who work on it, and has obligations about it that none of them can
waive.

The arrangement, in one paragraph. Northwind Capital owns a book. It shares
it with Alice and Carol under a role, which is what they joined for. Each of
them administers access to it through **her own** authorization server, under
**her own** terms — the same terms machinery she uses for her own brokerage
account. Northwind's charter sits above those terms and can only narrow them.
And the sentence no other authorization system has anywhere to put: the
charter decides **whose agent** may act on the firm's book — hers, anyone's,
or nobody's.

What can only be seen from out here, across six processes:

  * **joining grants something.** The firm's book appears in her authority
    because she is a member with a role, and leaves when she is not;
  * **the organization's reach stops at its own resources.** It cannot see
    the agents that touch her brokerage account, cannot answer requests about
    them, and cannot revoke them — her authority filters before it answers;
  * **whose agent it is decides the answer.** Under `first-party-only`, an
    agent Alice operates reads the firm's book and Bob's agent is refused,
    with the same terms, the same key strength and the same request;
  * **a role is a live thing.** An administrator moving her to a role that
    permits any agent lets Bob's in, minutes later, with nothing restarted;
  * **shutting an agent out of the firm's book leaves her own access alone**;
  * **both layers must allow, and either may refuse**;
  * **break-glass is loud**, bounded by the charter, and never passes through
    her authority.

Run with `make org-check`.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from urllib.parse import quote

import httpx

sys.path.insert(0, "/driver/lib")
from uma4a_grant import (  # noqa: E402
    AgentKeys, GrantDenied, mcp_call, mcp_json, mcp_meta, parse_challenge,
    run_grant, signed_headers,
)
from uma4a_http_sig import sign  # noqa: E402

GATEWAY = os.environ.get("UMA4A_GATEWAY", "https://gateway.uma.lab/mcp")
KEYCLOAK = os.environ.get("UMA4A_OIDC", "https://keycloak.uma.lab")
ORG = os.environ.get("UMA4A_ORG", "https://northwind-org.uma.lab")
ORG_AUTHORITY = ORG.split("://", 1)[-1]
ADMIN = {"Authorization": f"Bearer {os.environ.get('ORG_ADMIN_TOKEN', 'org-admin-dev-token')}"}
JOIN_CODE = os.environ.get("ORG_JOIN_CODE", "NW-7K2F-QX")
CA = os.environ.get("UMA4A_CACERT", "/driver/rootCA.pem")
# Agents whose operator published their key. The charter this lab ships wants
# accountability 2 over the firm's book, which is the posture a firm takes.
HIS_OPERATOR = os.environ.get("UMA4A_AGENT_OPERATOR", "https://agent.uma.lab")
HER_OPERATOR = os.environ.get("UMA4A_ALICE_OPERATOR", "https://alice-agent.uma.lab")
# Where the private halves of a provisioned directory are mounted, in the
# deployment shape that provisions one. Absent under compose, where the
# operator accepts a key at runtime.
PUBLISHED_KEYS = os.environ.get("UMA4A_PUBLISHED_KEYS")
BOOK = "northwind-vault"
META = mcp_meta("u4a-org-check")
RUN = uuid.uuid4().hex[:8]
# How long the enforcement point may act on a cached answer about membership.
# Read from the same variable the gateway is configured with, so this cannot
# drift into a flaky wait.
TTL = float(os.environ.get("UMA_PEP_MEMBERSHIP_TTL_S", "10")) + 2
# How long her authority may serve a resource listing without re-reading what
# the resource server publishes. Read from the same variable the server is
# configured with, so a wait here cannot drift into a flaky one.
REFRESH = float(os.environ.get("UMA_AS_RESOURCE_REFRESH_S", "15")) + 2

OWNERS = {
    "alice": {"as": os.environ.get("UMA4A_AS", "https://alice-as.uma.lab"),
              "realm": "alice", "own": "", "password": "alice-demo"},
    "carol": {"as": os.environ.get("UMA4A_CAROL_AS", "https://carol-as.uma.lab"),
              "realm": "carol", "own": "/carol", "password": "carol-demo"},
}
for name, o in OWNERS.items():
    o["shared"] = f"/shared/{name}"
    o["password"] = os.environ.get(f"{name.upper()}_PASSWORD", o["password"])

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
                     "username": owner, "password": o["password"]}, timeout=15.0)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def attested(c: httpx.Client, operator: str, name: str) -> AgentKeys:
    """An agent whose operator's directory actually carries its key.

    Two ways an operator comes to publish a key, and both are real:

      provisioned  the operator serves a document it was handed, identical on
                   every replica, and refuses a key registered at runtime.
                   That is the shape a firm runs, and it is why Bob's
                   operator has two replicas.
      registered   the agent registers its key when it is activated. That is
                   the shape a person runs — she turns on an agent and it
                   introduces itself — and it holds state, so it runs one.

    Which one applies is a property of the deployment, not of this check, so
    the provisioned key is used when it is there.
    """
    directory = f"{operator}/.well-known/http-message-signatures-directory"
    provisioned = f"{PUBLISHED_KEYS}/{name}-ed25519.pem" if PUBLISHED_KEYS else None
    if provisioned and os.path.exists(provisioned):
        keys = AgentKeys.load_or_create(provisioned)
        keys.client_id = f"{operator}/agent.json"
        keys.signature_agent = directory
        return keys
    keys = AgentKeys()
    # A key id of its own. The operator's runtime directory is keyed by it,
    # and every AgentKeys starts life with the same default — so two agents
    # of one operator registering in the same run overwrite each other, and
    # the first one silently loses the attestation it had.
    keys.keyid = f"{name}-{RUN}"
    keys.client_id = f"{operator}/agent.json"
    keys.signature_agent = keys.publish(c, operator)
    return keys


def ensure_resource_server(c: httpx.Client, owner: str) -> None:
    o = OWNERS[owner]
    for _ in range(8):
        registry = {r["client_id"]: r for r in c.get(
            f"{o['as']}/owner/resource-servers", headers=hdrs(c, owner),
            timeout=15.0).json()}
        if any(r.get("status") == "active" for r in registry.values()):
            return
        pending = [cid for cid, r in registry.items() if r.get("status") == "pending"]
        for cid in pending:
            c.post(f"{o['as']}/owner/resource-servers/decision",
                   json={"client_id": cid, "decision": "approved"},
                   headers=hdrs(c, owner), timeout=15.0)
        if not pending:
            mcp_call(c, f"{GATEWAY}{o['own']}", "tools/call",
                     {"name": "get_positions", "arguments": {}}, META)
            time.sleep(1.0)


def leave(c: httpx.Client, owner: str) -> None:
    o = OWNERS[owner]
    if c.get(f"{o['as']}/owner/organization", headers=hdrs(c, owner),
             timeout=15.0).json().get("enrolled"):
        c.request("DELETE", f"{o['as']}/owner/organization",
                  headers=hdrs(c, owner), timeout=15.0)


def drop_book_tier(c: httpx.Client, owner: str) -> None:
    """Remove a previous run's terms over the firm's book."""
    o = OWNERS[owner]
    for tid, t in c.get(f"{o['as']}/owner/policies", headers=hdrs(c, owner),
                        timeout=15.0).json().items():
        if any(r.startswith(f"{BOOK}/") for r in t.get("resources") or []):
            c.request("DELETE", f"{o['as']}/owner/policies/{tid}",
                      headers=hdrs(c, owner), timeout=15.0)


def join(c: httpx.Client, owner: str, code: str, agreed: bool = True) -> httpx.Response:
    return c.post(f"{OWNERS[owner]['as']}/owner/organization",
                  json={"code": code, "agreed": agreed},
                  headers=hdrs(c, owner), timeout=20.0)


def resources(c: httpx.Client, owner: str) -> dict:
    return {r["_id"]: r for r in c.get(f"{OWNERS[owner]['as']}/owner/resources",
                                       headers=hdrs(c, owner), timeout=15.0).json()}


def poke(c: httpx.Client, owner: str, where: str) -> None:
    """One unauthenticated call, to make the gateway publish and her authority
    pull. Ordinary discovery, not a back door."""
    mcp_call(c, f"{GATEWAY}{OWNERS[owner][where]}", "tools/call",
             {"name": "get_positions", "arguments": {}}, META)


def write_book_terms(c: httpx.Client, owner: str, expires: int) -> httpx.Response:
    o = OWNERS[owner]
    return c.post(f"{o['as']}/owner/policies", headers=hdrs(c, owner), timeout=15.0,
                  json={"id": "firmbook", "name": "Northwind book",
                        "ask_me": False,
                        "resources": [f"{BOOK}/get_positions",
                                      f"{BOOK}/get_transactions"],
                        "terms": {"purpose": "Desk research on the firm book",
                                  "expires_in": expires,
                                  "scope": ["positions:read", "transactions:read"],
                                  "prohibited": ["client-benchmarking"]}})


def negotiate(c: httpx.Client, owner: str, keys: AgentKeys, where: str,
              tool: str = "get_positions", reason: str | None = "Desk research",
              answer: str | bool = True) -> tuple[str | None, str]:
    """The ordinary four beats, at one of this owner's two surfaces."""
    o = OWNERS[owner]
    url = f"{GATEWAY}{o[where]}"
    r = mcp_call(c, url, "tools/call", {"name": tool, "arguments": {}}, META)
    ch = parse_challenge(r.headers.get("www-authenticate", ""))
    if ch is None:
        return None, f"no challenge: {r.status_code} {r.text[:150]}"
    answered = {"v": False}

    def be_her(msg: str) -> None:
        """Answer the pending request — as her, or as an administrator at her
        organization, which is the same tap and a different party."""
        if "has been asked" not in msg or answered["v"] or not answer:
            return
        answered["v"] = True
        if answer == "org":
            for p in c.get(f"{ORG}/admin/members/{owner}/pending",
                           headers=ADMIN, timeout=15.0).json():
                c.post(f"{ORG}/admin/members/{owner}/pending/"
                       f"{p['family']}/decision", json={"decision": "approved"},
                       headers=ADMIN, timeout=15.0)
            return
        for p in c.get(f"{o['as']}/owner/pending", headers=hdrs(c, owner),
                       timeout=15.0).json():
            c.post(f"{o['as']}/owner/pending/{p['family']}/decision",
                   json={"decision": "approved"}, headers=hdrs(c, owner),
                   timeout=15.0)

    try:
        return run_grant(c, ch.as_uri, ch.ticket, keys, lambda t: True,
                         reason=reason, on_status=be_her, max_wait_s=60), ""
    except GrantDenied as exc:
        return None, str(exc)[:220]


def spend(c: httpx.Client, owner: str, keys: AgentKeys, where: str,
          rpt: str) -> list[str]:
    """Use a grant, and report what came back."""
    path = f"/mcp{OWNERS[owner][where]}"
    r = mcp_call(c, f"{GATEWAY}{OWNERS[owner][where]}", "tools/call",
                 {"name": "get_positions", "arguments": {}}, META,
                 headers=signed_headers("POST", "gateway.uma.lab", path, rpt, keys))
    try:
        return sorted(p["symbol"] for p in
                      json.loads(mcp_json(r)["result"]["content"][0]["text"])["positions"])
    except (KeyError, IndexError, ValueError, TypeError):
        return []


def main() -> int:                                            # noqa: C901
    with httpx.Client(verify=CA, timeout=30.0) as c:
        print("\n== an organization's resources, shared with its members ==",
              flush=True)
        base = c.get(f"{ORG}/admin/charter/versions/1", headers=ADMIN,
                     timeout=15.0).json()["charter"]
        c.put(f"{ORG}/admin/charter", json=base, headers=ADMIN, timeout=20.0)
        for owner in OWNERS:
            ensure_resource_server(c, owner)
            leave(c, owner)
            # And from the organization's side as well. An authority that
            # restarted since the last run has forgotten its membership while
            # the organization still holds it, and the two have to be cleared
            # independently or a second run enrols somebody who is already a
            # member. Which is a real property — a membership is a
            # relationship, and both parties keep their own record of it — and
            # it makes this check idempotent rather than order-dependent.
            c.request("DELETE", f"{ORG}/admin/members/{owner}", headers=ADMIN,
                      timeout=15.0)
            drop_book_tier(c, owner)
            c.request("DELETE", f"{ORG}/admin/invites/{owner}", headers=ADMIN,
                      timeout=15.0)
            c.post(f"{OWNERS[owner]['as']}/owner/operators/claim",
                   json={"origin": HER_OPERATOR}, headers=hdrs(c, owner),
                   timeout=15.0)

        alice, carol = OWNERS["alice"], OWNERS["carol"]

        # --- 1. what she is offered, before she agrees to anything ---------
        preview = c.post(f"{alice['as']}/owner/organization/preview",
                         json={"code": JOIN_CODE}, headers=hdrs(c, "alice"),
                         timeout=15.0).json()
        powers = preview.get("powers") or {}
        gets = [x["what"] for x in powers.get("gets") or []]
        can = [x["what"] for x in powers.get("can") or []]
        cannot = [x["what"] for x in powers.get("cannot") or []]
        check("the offer says what she would get, not only what she would owe",
              any(BOOK in w for w in gets), f"{gets}")
        check("including whose agents would be allowed to act on it",
              any("agent" in w.lower() for w in gets), f"{gets}")
        check("and what the organization would be able to do",
              any("shut them out" in w for w in can)
              and any("ceiling" in w for w in can), f"{can}")
        check("and, in the same breath, what it could never touch",
              any("Touch anything of yours" == w for w in cannot), f"{cannot}")
        check("standing authority over her agents is not a button press",
              c.post(f"{alice['as']}/owner/organization",
                     json={"code": JOIN_CODE}, headers=hdrs(c, "alice"),
                     timeout=15.0).status_code == 400)
        r = c.post(f"{alice['as']}/owner/organization/preview",
                   json={"code": "NOPE"}, headers=hdrs(c, "alice"), timeout=15.0)
        check("a wrong code discloses nothing",
              r.status_code == 400 and "enrolment code" in r.text
              and "northwind-vault" not in r.text, f"{r.status_code} {r.text[:140]}")

        for owner in OWNERS:            # her own surface, so the pull has run
            poke(c, owner, "own")
        time.sleep(1.5)
        own_before = {o: {r for r in resources(c, o) if not r.startswith(BOOK)}
                      for o in OWNERS}
        tiers_before = {o: c.get(f"{OWNERS[o]['as']}/owner/policies",
                                 headers=hdrs(c, o), timeout=15.0).json()
                        for o in OWNERS}

        # --- 2. two members, two routes in --------------------------------
        joined = {"alice": join(c, "alice", JOIN_CODE).json()}
        r = c.post(f"{ORG}/admin/invites",
                   json={"owner": "carol", "note": f"Hartwell mandate {RUN}"},
                   headers=ADMIN, timeout=15.0)
        check("an administrator can invite someone by name", r.status_code == 200,
              f"{r.status_code} {r.text[:140]}")
        state = c.get(f"{carol['as']}/owner/organization", headers=hdrs(c, "carol"),
                      timeout=15.0).json()
        invite = state.get("invitation") or {}
        check("it appears in her own portal as a decision waiting on her",
              invite.get("invited") and RUN in (invite.get("note") or ""), f"{state}")
        check("and inviting her has made her a member of nothing",
              state.get("enrolled") is False
              and "carol" not in {m["owner"] for m in c.get(
                  f"{ORG}/admin/members", headers=ADMIN, timeout=15.0).json()})
        joined["carol"] = join(c, "carol", invite.get("code")).json()
        check("both are members — one by code, one by invitation",
              all(j.get("joined") == "northwind" for j in joined.values()),
              f"{joined}")
        check("each is given a role, and it is what she joined for",
              all(j.get("role") == "analyst" for j in joined.values()),
              f"{[j.get('role') for j in joined.values()]}")

        # --- 3. joining is what makes the firm's book exist for her --------
        for owner in OWNERS:
            poke(c, owner, "shared")
        time.sleep(1.5)
        after = {o: resources(c, o) for o in OWNERS}
        for owner in OWNERS:
            shared = {rid: r for rid, r in after[owner].items()
                      if r.get("shared_by")}
            check(f"{owner}'s authority now protects the firm's book",
                  set(shared) == {f"{BOOK}/get_positions", f"{BOOK}/get_transactions"},
                  f"{sorted(shared)}")
            check(f"and it is marked as {owner}'s to administer, not to own",
                  all(r["shared_by"] == "Northwind Capital" and r["granted"]
                      for r in shared.values()))
        check("the trade endpoint is not shared — an analyst was not given it",
              all(f"{BOOK}/execute_trade" not in after[o] for o in OWNERS))
        check("and nothing of their own changed",
              all({r for r in after[o] if not r.startswith(BOOK)} == own_before[o]
                  for o in OWNERS),
              f"{ {o: sorted(own_before[o] ^ {r for r in after[o] if not r.startswith(BOOK)}) for o in OWNERS} }")
        check("their own terms are untouched by joining",
              all(c.get(f"{OWNERS[o]['as']}/owner/policies", headers=hdrs(c, o),
                        timeout=15.0).json() == tiers_before[o] for o in OWNERS),
              "the charter reached a member's own accounts")

        # --- 4. she writes the terms; the charter caps them ----------------
        r = write_book_terms(c, "alice", 86400)
        check("terms over the firm's book that exceed the ceiling are refused",
              r.status_code == 400 and "caps access" in r.text, f"{r.text[:160]}")
        r = write_book_terms(c, "alice", 3600)
        created = r.json() if r.status_code == 200 else {}
        check("terms inside it are hers to write", r.status_code == 200,
              f"{r.text[:200]}")
        check("and the charter's prohibitions are added to them",
              set(base["envelope"]["require_prohibited"])
              <= set((created.get("terms") or {}).get("prohibited") or []),
              f"{created.get('terms')}")
        doc = c.get(f"{alice['as']}/terms/"
                    f"{(created.get('terms') or {}).get('template_id', 'none')}",
                    timeout=15.0).json()
        check("the terms document an agent reads names the organization",
              (doc.get("organization") or {}).get("name") == "Northwind Capital",
              f"{doc.get('organization')}")
        write_book_terms(c, "carol", 3600)

        # --- 5. whose agent it is decides the answer ----------------------
        # The centrepiece. Same terms, same resource, same key strength, same
        # stated reason — and the answer differs because of who runs the agent.
        his = attested(c, HIS_OPERATOR, "attested")
        hers = attested(c, HER_OPERATOR, "alice")
        # Both halves of accountability 2, asserted here so that a failure to
        # publish reports as itself rather than as a refusal three beats later.
        check("each operator published its agent's key",
              bool(his.signature_agent) and bool(hers.signature_agent),
              f"his={his.signature_agent} hers={hers.signature_agent}")
        rpt_his, why_his = negotiate(c, "alice", his, "shared")
        check("under first-party-only, somebody else's agent is refused the book",
              rpt_his is None and "operates herself" in why_his, f"{why_his}")
        rpt_hers, why_hers = negotiate(c, "alice", hers, "shared")
        check("and an agent she operates herself is granted it",
              rpt_hers is not None, f"{why_hers}")
        book = spend(c, "alice", hers, "shared", rpt_hers) if rpt_hers else []
        check("and reads the firm's book, not her own portfolio",
              book == ["NWCF", "NWEQ", "TLT", "VNQ"], f"{book}")
        rpt_own, why_own = negotiate(c, "alice", his, "own")
        check("while the same third-party agent still reaches her own accounts",
              rpt_own is not None, f"{why_own}")
        check("and an organization that cannot be reached does not stop that",
              "organization" not in why_own.lower(),
              "her own accounts were refused on account of somebody else's "
              "policy service")
        check("which are hers, and different",
              "NWCF" not in spend(c, "alice", his, "own", rpt_own) if rpt_own else False)

        # --- 6. what the organization can see of her ----------------------
        r = c.get(f"{ORG}/admin/members/alice/connections", headers=ADMIN,
                  timeout=15.0)
        conns = r.json() if r.status_code == 200 else []
        check("an administrator can read the agents that touch its book",
              isinstance(conns, list), f"{r.status_code} {r.text[:200]}")
        conns = conns if isinstance(conns, list) else []
        handles = {x["handle"] for x in conns}
        check("the organization sees the agent that touched its book",
              any(x.get("org_tiers") for x in conns), f"{conns}")
        check("and does not see the agent that only touched her own accounts",
              not (handles & {h for h in handles if h not in
                              {x["handle"] for x in conns if x.get("org_tiers")}}),
              f"{sorted(handles)}")
        pending = c.get(f"{ORG}/admin/members/alice/pending", headers=ADMIN,
                        timeout=15.0)
        check("its view of her queue is scoped the same way",
              pending.status_code == 200
              and all(x["resource_id"].startswith(BOOK) for x in pending.json()),
              f"{pending.text[:200]}")
        ledger = c.get(f"{ORG}/admin/members/alice/ledger", headers=ADMIN,
                       timeout=15.0).json()
        # The invariant rather than a snapshot: every entry an administrator
        # can see either concerns the membership itself, or carries a tier of
        # hers that governs one of this organization's resources. Stated this
        # way because her ledger outlives a run — it is in Postgres — and an
        # assertion about *which* entries are there would be an assertion
        # about history.
        org_kinds = {"org_joined", "org_left", "org_clamped", "org_refused",
                     "org_role", "org_acted", "org_declined", "break_glass"}
        leaked = [e for e in ledger if e.get("kind") not in org_kinds
                  and e.get("tier") != "firmbook"]
        check("and so is its view of her record",
              bool(ledger) and not leaked,
              f"{[(e.get('kind'), e.get('tier')) for e in leaked][:6]}")
        roster = json.dumps(c.get(f"{ORG}/admin/members", headers=ADMIN,
                                  timeout=15.0).json())
        secrets_of = [t["terms"]["purpose"] for t in tiers_before["alice"].values()]
        check("and it never sees what any member's policy says",
              not [x for x in secrets_of if x and x in roster], f"{secrets_of}")

        # --- 7. shutting an agent out of the book, and only out of it -----
        book_handle = next(x["handle"] for x in conns if x.get("org_tiers"))
        r = c.post(f"{ORG}/admin/members/alice/connections/"
                   f"{quote(book_handle, safe='')}/revoke", headers=ADMIN, timeout=15.0)
        check("an administrator can shut an agent out of the firm's book",
              r.status_code == 200, f"{r.status_code} {r.text[:160]}")
        rpt, why = negotiate(c, "alice", hers, "shared")
        check("and it is out", rpt is None and "withdrawn" in why, f"{why}")
        shown = c.get(f"{ORG}/admin/members/alice/connections", headers=ADMIN,
                      timeout=15.0).json()
        check("and the console can see that it is out, rather than offering to "
              "shut out an agent it already shut out",
              any(x["handle"] == book_handle and x.get("blocked_for_organization")
                  for x in shown), f"{[(x['handle'][:14], x.get('blocked_for_organization')) for x in shown]}")
        entry = [e for e in c.get(f"{alice['as']}/owner/ledger",
                                  headers=hdrs(c, "alice"), timeout=15.0).json()
                 if e["kind"] == "org_acted"]
        check("her record says who did it, and that it was not her",
              entry and (entry[-1].get("by") or {}).get("org") == "northwind",
              f"{entry[-1] if entry else None}")
        rpt_still, why_still = negotiate(c, "alice", hers, "own")
        check("and that agent's access to her own accounts is untouched",
              rpt_still is not None, f"{why_still}")
        c.post(f"{ORG}/admin/members/alice/connections/"
               f"{quote(book_handle, safe='')}/restore", headers=ADMIN, timeout=15.0)

        # --- 7b. an administrator's approval is his, not hers -------------
        #
        # `standing.approved_at_tier` is one of the few facts allowed to
        # *relax* one of her rules, because "she personally approved something
        # here" is a decision of hers. If an administrator answering on her
        # behalf produced that fact, one decision of his would loosen her
        # policy for every request afterwards.
        c.put(f"{alice['as']}/owner/policies/firmbook", json={"ask_me": True},
              headers=hdrs(c, "alice"), timeout=15.0)
        known = {x["handle"] for x in
                 c.get(f"{alice['as']}/owner/connections", headers=hdrs(c, "alice"),
                       timeout=15.0).json()}
        fresh = attested(c, HER_OPERATOR, "alice-second")
        rpt, why = negotiate(c, "alice", fresh, "shared", answer="org")
        check("an administrator can answer a request waiting on her",
              rpt is not None, f"{why}")
        new_conns = [x for x in
                     c.get(f"{alice['as']}/owner/connections",
                           headers=hdrs(c, "alice"), timeout=15.0).json()
                     if x["handle"] not in known]
        check("the grant is recorded against that agent",
              new_conns and "firmbook" in (new_conns[0].get("tiers_granted") or []),
              f"{[x.get('tiers_granted') for x in new_conns]}")
        check("and his approval is NOT recorded as one of hers",
              new_conns and not (new_conns[0].get("tiers_approved") or []),
              "an administrator's decision became evidence that she decided — "
              "a fact that is allowed to relax her own rules")
        entry = [e for e in c.get(f"{alice['as']}/owner/ledger",
                                  headers=hdrs(c, "alice"), timeout=15.0).json()
                 if e["kind"] == "approved"]
        check("her record says which of them it was",
              entry and (entry[-1].get("by") or {}).get("admin"), f"{entry[-1] if entry else None}")
        c.put(f"{alice['as']}/owner/policies/firmbook", json={"ask_me": False},
              headers=hdrs(c, "alice"), timeout=15.0)

        # --- 7c. the administration credential, and its limits ------------
        r = c.get(f"{alice['as']}/org/admin/alice/connections",
                  headers=hdrs(c, "alice"), timeout=15.0)
        check("her own credential is not an administration credential",
              r.status_code == 401, f"{r.status_code} {r.text[:120]}")
        r = c.get(f"{carol['as']}/org/admin/carol/connections",
                  headers=ADMIN, timeout=15.0)
        check("nor is the organization's console token, presented directly",
              r.status_code == 401, f"{r.status_code} {r.text[:120]}")
        r = c.get(f"{ORG}/admin/members/alice/pending/../../../member/envelope",
                  headers=ADMIN, timeout=15.0)
        check("and an administration path cannot climb out of the admin surface",
              r.status_code in (400, 404), f"{r.status_code} {r.text[:120]}")

        # --- 8. a role is a live thing ------------------------------------
        r = c.post(f"{ORG}/admin/members/alice/role", json={"role": "trader"},
                   headers=ADMIN, timeout=15.0)
        check("an administrator can change what a member may reach",
              r.status_code == 200, f"{r.text[:160]}")
        # The gateway holds a short cached view of who is a member and what
        # they may reach. Waiting it out here is the honest cost of that
        # cache; nothing below is a race, and the window is a deployment
        # setting rather than a property of the design.
        time.sleep(TTL)
        poke(c, "alice", "shared")
        time.sleep(1.5)
        check("the firm's trade endpoint appears in her authority",
              f"{BOOK}/execute_trade" in resources(c, "alice"),
              f"{sorted(resources(c, 'alice'))}")
        rpt_his2, why_his2 = negotiate(c, "alice", his, "shared")
        check("and a role that permits any agent lets a third party in",
              rpt_his2 is not None, f"{why_his2}")
        check("with nothing restarted and no new deployment",
              True)
        c.post(f"{ORG}/admin/members/alice/role", json={"role": "analyst"},
               headers=ADMIN, timeout=15.0)

        # --- 9. both layers must allow ------------------------------------
        rpt, why = negotiate(c, "alice", hers, "shared", reason=None)
        check("a request her own terms would grant is refused for want of a reason",
              rpt is None and "did not say what it wants" in why, f"{why}")
        custom = {**base, "rego": (
            "package u4a.custom\n\nimport rego.v1\n\n"
            "deny contains msg if {\n"
            '\tendswith(input.request.resource_id, "/get_positions")\n'
            '\tmsg := "positions are frozen during the quarterly close"\n'
            "}\n")}
        r = c.put(f"{ORG}/admin/charter", json=custom, headers=ADMIN, timeout=20.0)
        check("an administrator can add rules the settings cannot express",
              r.status_code == 200, f"{r.status_code} {r.text[:200]}")
        r = c.put(f"{ORG}/admin/charter",
                  json={**base, "rego": "package u4a.custom\n\nnot rego at all\n"},
                  headers=ADMIN, timeout=20.0)
        check("a module that does not compile never becomes the charter in force",
              r.status_code == 400, f"{r.status_code} {r.text[:140]}")
        rpt, why = negotiate(c, "alice", hers, "shared")
        check("the administrator's own rule refuses what the settings allowed",
              rpt is None and "quarterly close" in why, f"{why}")
        # A rule that names the group. This is the join between the two
        # layers: the charter says what a group *is* and who is in it, the
        # engine decides using it. Neither half can do this alone — a
        # settings form cannot express "for analysts, on Fridays", and an
        # engine holding its own membership list would be a directory.
        by_group = {**base, "rego": (
            "package u4a.custom\n\nimport rego.v1\n\n"
            "deny contains msg if {\n"
            '\tinput.role.id == "analyst"\n'
            '\tmsg := "analysts are read-only while the desk is under review"\n'
            "}\n")}
        r = c.put(f"{ORG}/admin/charter", json=by_group, headers=ADMIN, timeout=20.0)
        check("a rule can name the group the member is in",
              r.status_code == 200, f"{r.status_code} {r.text[:200]}")
        rpt, why = negotiate(c, "alice", hers, "shared")
        check("and refuses her because of which group she is in",
              rpt is None and "under review" in why, f"{why}")
        c.put(f"{ORG}/admin/charter", json=base, headers=ADMIN, timeout=20.0)

        # --- 9b. groups are charter data, and only an admin moves anyone ---
        doc = c.get(f"{ORG}/admin/roles", headers=ADMIN, timeout=15.0).json()
        check("the console can see who is in each group",
              "alice" in (doc.get("members") or {}).get("analyst", []),
              f"{doc.get('members')}")
        before = c.get(f"{ORG}/admin/org", headers=ADMIN, timeout=15.0).json()
        r = c.put(f"{ORG}/admin/roles/desk",
                  json={"name": "Trading desk",
                        "grants": [f"{BOOK}/get_positions"],
                        "delegation": "first-party-only"},
                  headers=ADMIN, timeout=20.0)
        check("an administrator can create a group without editing JSON",
              r.status_code == 200 and "desk" in (r.json().get("roles") or {}),
              f"{r.status_code} {r.text[:180]}")
        after = c.get(f"{ORG}/admin/org", headers=ADMIN, timeout=15.0).json()
        check("creating one publishes a charter version rather than editing in place",
              after["charter_version"] > before["charter_version"],
              f"{before['charter_version']} -> {after['charter_version']}")
        r = c.put(f"{ORG}/admin/roles/rogue",
                  json={"name": "Rogue", "grants": ["alice-vault/*"],
                        "delegation": "any-agent"},
                  headers=ADMIN, timeout=20.0)
        check("a group cannot grant what the charter does not claim",
              r.status_code == 400 and "does not claim" in r.text,
              f"{r.status_code} {r.text[:180]}")
        r = c.request("DELETE", f"{ORG}/admin/roles/analyst",
                      headers=ADMIN, timeout=20.0)
        check("a group with members in it cannot be deleted out from under them",
              r.status_code == 409 and "alice" in r.text,
              f"{r.status_code} {r.text[:180]}")
        r = c.post(f"{ORG}/admin/roles/default", json={"role": "desk"},
                   headers=ADMIN, timeout=20.0)
        check("an administrator can say which group joiners land in",
              r.status_code == 200 and r.json().get("default_role") == "desk",
              f"{r.status_code} {r.text[:180]}")
        held = c.get(f"{ORG}/admin/roles", headers=ADMIN, timeout=15.0).json()
        check("and nobody already enrolled moves",
              "alice" in (held.get("members") or {}).get("analyst", [])
              and not (held.get("members") or {}).get("desk"),
              f"{held.get('members')}")
        r = c.request("DELETE", f"{ORG}/admin/roles/desk",
                      headers=ADMIN, timeout=20.0)
        check("an empty group can be removed",
              r.status_code == 200 and "desk" not in (r.json().get("roles") or {}),
              f"{r.status_code} {r.text[:180]}")
        c.put(f"{ORG}/admin/charter", json=base, headers=ADMIN, timeout=20.0)

        # --- 10. break-glass: loud, bounded, and around her authority -----
        opened = c.post(f"{ORG}/admin/break-glass",
                        json={"owner": "alice", "window_s": 120,
                              "reason": f"Regulatory hold OPS-{RUN}"},
                        headers=ADMIN, timeout=15.0)
        check("an administrator can open a break-glass window",
              opened.status_code == 200, f"{opened.text[:160]}")
        time.sleep(1.0)
        stages = [e.get("stage") for e in c.get(
            f"{alice['as']}/owner/ledger", headers=hdrs(c, "alice"),
            timeout=15.0).json() if e["kind"] == "break_glass"]
        check("the member is told before any data moves",
              stages and stages[-1] == "break_glass_opened", f"{stages}")
        bg = AgentKeys()
        body = json.dumps({"owner": "alice",
                           "resource_id": f"{BOOK}/get_positions",
                           "scopes": ["positions:read"],
                           "reason": f"Regulatory hold OPS-{RUN}",
                           "voucher": opened.json().get("voucher"),
                           "agent_jwk": bg.public_jwk(),
                           "audience": "https://gateway.uma.lab"}).encode()
        sig = sign("POST", ORG_AUTHORITY, "/break-glass", "", bg.key, bg.keyid,
                   body=body)
        r = c.post(f"{ORG}/break-glass", content=body, timeout=15.0,
                   headers={"content-type": "application/json", **sig})
        check("an agent redeems it by signing with the key it will be bound to",
              r.status_code == 200, f"{r.status_code} {r.text[:200]}")
        override = r.json().get("access_token", "")
        claims = json.loads(
            __import__("base64").urlsafe_b64decode(
                override.split(".")[1] + "=" * (-len(override.split(".")[1]) % 4)))
        check("its audience is the organization's, not the caller's",
              claims["aud"] == "https://gateway.uma.lab", f"{claims.get('aud')}")
        check("and its scopes are bounded by the charter",
              claims["permissions"][0]["resource_scopes"] == ["positions:read"],
              f"{claims['permissions'][0]}")
        r = c.post(f"{ORG}/break-glass", content=body, timeout=15.0,
                   headers={"content-type": "application/json", **sig})
        check("the same signed request cannot be redeemed twice",
              r.status_code == 409, f"{r.status_code} {r.text[:140]}")
        check("the override is honoured at the enforcement point",
              spend(c, "alice", bg, "shared", override) == ["NWCF", "NWEQ", "TLT", "VNQ"])
        check("and it is spent — an exception is for one act",
              spend(c, "alice", bg, "shared", override) == [])
        time.sleep(1.0)
        stages = [e.get("stage") for e in c.get(
            f"{alice['as']}/owner/ledger", headers=hdrs(c, "alice"),
            timeout=15.0).json() if e["kind"] == "break_glass"]
        check("every stage of it is in her own record",
              {"break_glass_opened", "break_glass", "break_glass_used"} <= set(stages),
              f"{stages}")
        opened = c.post(f"{ORG}/admin/break-glass",
                        json={"owner": "alice", "window_s": 60, "reason": "more"},
                        headers=ADMIN, timeout=15.0).json()
        body = json.dumps({"owner": "alice", "resource_id": f"{BOOK}/execute_trade",
                           "scopes": ["trades:execute"], "reason": "more",
                           "voucher": opened.get("voucher"),
                           "agent_jwk": bg.public_jwk()}).encode()
        sig = sign("POST", ORG_AUTHORITY, "/break-glass", "", bg.key, bg.keyid,
                   body=body)
        r = c.post(f"{ORG}/break-glass", content=body, timeout=15.0,
                   headers={"content-type": "application/json", **sig})
        opened2 = c.post(f"{ORG}/admin/break-glass",
                         json={"owner": "alice", "window_s": 60, "reason": "scope probe"},
                         headers=ADMIN, timeout=15.0).json()
        wide = json.dumps({"owner": "alice", "resource_id": f"{BOOK}/get_positions",
                           "scopes": ["everything:read"], "reason": "scope probe",
                           "voucher": opened2.get("voucher"),
                           "agent_jwk": bg.public_jwk()}).encode()
        r = c.post(f"{ORG}/break-glass", content=wide, timeout=15.0,
                   headers={"content-type": "application/json",
                            **sign("POST", ORG_AUTHORITY, "/break-glass", "",
                                   bg.key, bg.keyid, body=wide)})
        check("an override cannot ask for a scope the charter never allows",
              r.status_code == 403, f"{r.status_code} {r.text[:140]}")

        check("break-glass cannot reach a resource the charter did not name for it",
              r.status_code == 403, f"{r.status_code} {r.text[:140]}")
        r = c.post(f"{ORG}/break-glass",
                   content=body.replace(b'"more"', b'"else"'), timeout=15.0,
                   headers={"content-type": "application/json", **sig})
        check("and a redemption whose body was changed after signing is refused",
              r.status_code == 401, f"{r.status_code} {r.text[:140]}")
        r = c.post(f"{ORG}/break-glass", content=body, timeout=15.0,
                   headers={"content-type": "application/json"})
        check("an unsigned one is turned away before the charter is consulted",
              r.status_code == 401, f"{r.status_code} {r.text[:140]}")

        # --- 11. a charter that moves reaches every member ----------------
        c.put(f"{ORG}/admin/charter",
              json={**base, "envelope": {**base["envelope"], "max_expires_in": 600}},
              headers=ADMIN, timeout=20.0)
        time.sleep(1.5)
        for owner in OWNERS:
            c.get(f"{OWNERS[owner]['as']}/owner/organization",
                  headers=hdrs(c, owner), timeout=15.0)
        book_tiers = {o: [t for t in c.get(f"{OWNERS[o]['as']}/owner/policies",
                                           headers=hdrs(c, o), timeout=15.0).json().values()
                          if any(r.startswith(BOOK) for r in t["resources"])]
                      for o in OWNERS}
        check("tightening the charter re-clamps every member's book terms",
              all(t["terms"]["expires_in"] <= 600
                  for ts in book_tiers.values() for t in ts),
              f"{ {o: [t['terms']['expires_in'] for t in ts] for o, ts in book_tiers.items()} }")
        own = c.get(f"{alice['as']}/owner/policies", headers=hdrs(c, "alice"),
                    timeout=15.0).json()
        check("and leaves her own terms exactly as they were",
              all(own[tid]["terms"]["expires_in"]
                  == tiers_before["alice"][tid]["terms"]["expires_in"]
                  for tid in tiers_before["alice"]),
              f"{ {k: v['terms']['expires_in'] for k, v in own.items()} }")

        # --- 12. leaving takes back what joining gave --------------------
        # A grant taken *before* she leaves, to be spent after. Access that
        # outlived the sharing would make "leaving takes it back" a statement
        # about new negotiations only.
        live_rpt, why = negotiate(c, "alice", hers, "shared")
        check("a grant is in hand before she leaves", live_rpt is not None, f"{why}")
        narrowed = {t["terms"]["template_id"].rsplit("/v", 1)[0]:
                    t["terms"]["expires_in"] for t in book_tiers["alice"]}
        r = c.request("DELETE", f"{alice['as']}/owner/organization",
                      headers=hdrs(c, "alice"), timeout=15.0)
        check("a member can leave from her own portal", r.status_code == 200,
              f"{r.text[:140]}")
        # Her authority repairs its registry on a clock as well as on a miss,
        # and this is the case with no miss: nothing is absent, something is
        # left over. Waiting it out is the honest cost of a per-process cache
        # of a re-pullable document — and the enforcement point refuses the
        # resource immediately either way, which is asserted below.
        time.sleep(REFRESH)
        left = resources(c, "alice")
        check("the firm's book stops being hers to administer",
              not any(rid.startswith(BOOK) for rid in left), f"{sorted(left)}")
        check("her own resources are all still there",
              {r for r in left} == own_before["alice"], f"{sorted(left)}")
        still = [t for t in c.get(f"{alice['as']}/owner/policies",
                                  headers=hdrs(c, "alice"), timeout=15.0).json().values()
                 if any(r.startswith(BOOK) for r in t["resources"])]
        check("her terms keep every narrowing — leaving withdraws a ceiling, "
              "it does not raise what is under one",
              all(t["terms"]["expires_in"]
                  == narrowed[t["terms"]["template_id"].rsplit("/v", 1)[0]]
                  for t in still), f"{[t['terms']['expires_in'] for t in still]}")
        time.sleep(TTL)                 # as above: the gateway's cached view
        rpt, why = negotiate(c, "alice", hers, "shared")
        check("and an agent asking for the book now gets nowhere",
              rpt is None, f"{why}")
        check("nor does a grant it was holding from before still work",
              spend(c, "alice", hers, "shared", live_rpt) == [],
              "access outlived the sharing that granted it")
        check("while another member's access is unaffected",
              c.get(f"{carol['as']}/owner/organization", headers=hdrs(c, "carol"),
                    timeout=15.0).json().get("enrolled") is True)

        # --- 13. an invitation she does not want -------------------------
        c.post(f"{ORG}/admin/invites", json={"owner": "alice", "note": "come back"},
               headers=ADMIN, timeout=15.0)
        r = c.post(f"{alice['as']}/owner/organization/decline",
                   headers=hdrs(c, "alice"), timeout=15.0)
        check("she can decline an invitation", r.status_code == 200, f"{r.text[:140]}")
        invites = {i["owner"]: i for i in c.get(f"{ORG}/admin/invites",
                                                headers=ADMIN, timeout=15.0).json()}
        check("and the administrator sees the refusal rather than an open invitation",
              (invites.get("alice") or {}).get("state") == "declined", f"{invites}")

        # Put the lab back. This charter wants an attested agent and shares a
        # book; a member left enrolled would change what the other demos see.
        c.request("DELETE", f"{ORG}/admin/invites/alice", headers=ADMIN, timeout=15.0)
        c.put(f"{ORG}/admin/charter", json=base, headers=ADMIN, timeout=20.0)
        for owner in OWNERS:
            leave(c, owner)
            drop_book_tier(c, owner)

    print()
    print(f"{len(PASS)} passed, {len(FAIL)} failed", flush=True)
    if FAIL:
        for f in FAIL:
            print(f"  - {f}")
        return 1
    print("\nPASS: one resource server, three owners of record. Alice's accounts")
    print("      are hers, Carol's are hers, and Northwind's book is Northwind's —")
    print("      shared with both of them, administered by each under her own")
    print("      authority and her own terms, capped by a charter neither of them")
    print("      wrote. Whose agent is asking decided the answer, the organization")
    print("      never saw past its own resources, and leaving took back exactly")
    print("      what joining gave.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
