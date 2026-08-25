"""Property suite for the authorization server's store.

Both backends must pass this identically. That is the point: the interface
promises that a single-use thing is spent exactly once no matter how many
callers ask at the same moment, and the only way that promise is worth
anything is if the same tests hold against the in-process store the compose
stack runs and the Postgres store the replicated deployment runs.

Run it against memory (no dependencies):

    python3 lib/test_store.py

Against Postgres as well, once a database is reachable:

    UMA_AS_TEST_DSN=postgres://u4a:u4a@localhost:5432/u4a python3 lib/test_store.py

The Postgres pass is what makes the claim real; the memory pass is what
keeps the two shapes honest about being the same service.
"""

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "services", "uma-as"))

RACERS = 32

_failures: list[str] = []
_passes = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global _passes
    if ok:
        _passes += 1
        print(f"  ok   {name}")
    else:
        _failures.append(f"{name}: {detail}")
        print(f"  FAIL {name} — {detail}")


def negotiation(family: str) -> dict:
    return {"family": family, "state": "issued",
            "resource_id": "alice-vault/get_positions",
            "resource_scopes": ["positions:read"]}


async def test_ticket_is_spent_once(store) -> None:
    """A ticket is single-use. Under N simultaneous presentations exactly one
    caller may be handed the negotiation."""
    ticket = await store.mint_ticket(negotiation("fam_ticket_race"), 300)
    results = await asyncio.gather(
        *(store.consume_ticket(ticket) for _ in range(RACERS)))
    winners = [r for r in results if r is not None]
    check("ticket: exactly one of %d presentations wins" % RACERS,
          len(winners) == 1, f"{len(winners)} callers were given the record")
    check("ticket: the winner gets the right negotiation",
          bool(winners) and winners[0]["family"] == "fam_ticket_race",
          "winner carried the wrong family")
    await store.close_negotiation("fam_ticket_race")


async def test_save_creates_an_unseen_negotiation(store) -> None:
    """`save_negotiation` stores a negotiation that never had a ticket.

    Every negotiation used to begin at `/perm`, which minted a ticket and
    created the row, so the Postgres store implemented this as an UPDATE
    while the in-memory one wrote the key either way. A request over a
    jointly held resource arrives from another owner's tally with no ticket
    at this authority, and on Postgres it silently stored nothing: the
    pending request never reached her portal and the negotiation waited out
    its timeout. Two backends disagreeing about what a method does is the
    bug, so it is asserted rather than remembered.
    """
    rec = {**negotiation("fam_no_ticket"), "state": "awaiting-owner",
           "decision": None, "expires": time.time() + 300}
    await store.save_negotiation(rec)
    got = await store.negotiation("fam_no_ticket")
    check("save: a negotiation with no ticket is stored",
          got is not None and got["family"] == "fam_no_ticket",
          "it was not written")
    pending = [p["family"] for p in await store.pending_negotiations()]
    check("save: and it reaches the owner's pending list",
          "fam_no_ticket" in pending, f"{pending}")
    check("save: and it can be decided",
          await store.decide("fam_no_ticket", "approved"), "decide said no")
    await store.close_negotiation("fam_no_ticket")


async def test_negotiation_survives_its_ticket(store) -> None:
    """Consuming a ticket removes the index entry, not the negotiation.

    This is the property that lets Alice's portal see and decide a pending
    request in the window between one ticket being spent and its rotation
    being issued. Keying negotiations by ticket makes the record invisible
    there, and the owner's decision 404s on a negotiation that plainly
    exists.
    """
    rec = negotiation("fam_survives")
    rec["state"] = "awaiting-owner"
    ticket = await store.mint_ticket(rec, 300)
    await store.consume_ticket(ticket)
    still_there = await store.negotiation("fam_survives")
    check("negotiation outlives the ticket that indexed it",
          still_there is not None, "the record vanished with its ticket")
    await store.close_negotiation("fam_survives")


async def test_rpt_is_burned_once(store) -> None:
    """The single-use grant. N racers, one winner — this is the whole reason
    the store exists, and the reason /consume is a separate call."""
    await store.record_rpt("rpt_race", "fam_rpt", "jkt:agent",
                           {"tool": "execute_trade"})
    results = await asyncio.gather(
        *(store.consume_rpt("rpt_race") for _ in range(RACERS)))
    winners = [r for r in results if r is not None]
    check("rpt: exactly one of %d burns wins" % RACERS,
          len(winners) == 1,
          f"{len(winners)} callers were told they could spend the grant")
    check("rpt: the winner is told which negotiation it belonged to",
          winners == ["fam_rpt"], f"got {winners!r}")
    check("rpt: a later burn still loses",
          await store.consume_rpt("rpt_race") is None,
          "a spent grant was spendable again")


async def test_unknown_rpt_cannot_be_burned(store) -> None:
    check("rpt: an unknown jti cannot be burned",
          await store.consume_rpt("rpt_never_issued") is None,
          "burning an unissued grant reported success")


async def test_owner_decides_once(store) -> None:
    """A double tap, or two portals open on the same request, is one
    decision."""
    rec = negotiation("fam_decide")
    rec["state"] = "awaiting-owner"
    rec["decision"] = None
    await store.mint_ticket(rec, 300)
    results = await asyncio.gather(
        *(store.decide("fam_decide", "approved") for _ in range(RACERS)))
    check("decision: exactly one of %d taps is recorded" % RACERS,
          sum(1 for r in results if r) == 1,
          f"{sum(1 for r in results if r)} taps were accepted")
    check("decision: a denial after an approval is refused",
          await store.decide("fam_decide", "denied") is False,
          "the decision was reversible")
    await store.close_negotiation("fam_decide")


async def test_revoke_burns_live_grants(store) -> None:
    """Revocation deactivates the connection and every live token under it in
    one step. If the two halves could come apart, a revoked agent would keep
    exactly the authority Alice just withdrew."""
    await store.put_connection({"handle": "jkt:revoke-me", "status": "active",
                                "first_seen": "2026-08-11T00:00:00Z",
                                "identity": {"level": "pseudonymous"},
                                "label": "test", "last_access": None,
                                "tiers": ["tier1"]})
    for i in range(3):
        await store.record_rpt(f"rpt_rev{i}", "fam_rev", "jkt:revoke-me", None)
    await store.consume_rpt("rpt_rev0")          # one already spent

    killed = await store.revoke_connection("jkt:revoke-me")
    check("revoke: only the live grants are counted", killed == 2,
          f"reported {killed} deactivated, expected 2")
    conn = await store.connection("jkt:revoke-me")
    check("revoke: the connection is deactivated",
          conn is not None and conn["status"] == "revoked",
          "connection still active")
    check("revoke: a grant issued under it can no longer be spent",
          await store.consume_rpt("rpt_rev1") is None,
          "a revoked agent's grant was still spendable")
    check("revoke: an unknown handle reports not-found, not success",
          await store.revoke_connection("jkt:never-seen") is None,
          "revoking an unknown connection reported success")


async def test_resource_server_revocation_is_visible(store) -> None:
    """The status require_pat reads on every Protection API call. A
    revocation that only reached one replica would leave the others
    honouring a PAT the owner had withdrawn."""
    servers = await store.resource_servers()
    cid = next(iter(servers))
    check("resource server: seeded active",
          servers[cid]["status"] == "active", "seed was not active")
    check("resource server: revoke reports success",
          await store.revoke_resource_server(cid) is True, "revoke failed")
    rs = await store.resource_server(cid)
    check("resource server: revocation is readable afterwards",
          rs is not None and rs["status"] == "revoked",
          "status did not stick")
    check("resource server: revoking an unknown client is not-found",
          await store.revoke_resource_server("nobody") is False,
          "revoking an unknown client reported success")


async def test_a_resource_server_registers_and_waits(store) -> None:
    """The other way a resource server comes to hold protection access: it
    registers itself, and the record it creates opens nothing until the owner
    changes it.

    Worth a storage test rather than only an end-to-end one, because
    ``pending -> active`` is the gate, and where that transition is a
    read-then-write it is a race two portals can both win.
    """
    cid = "https://gateway.example/registered"
    await store.put_resource_server(cid, {
        "secret": "", "name": "a resource server that introduced itself",
        "status": "pending", "consented": None, "last_pat_issued": None,
        "resource_uri": f"{cid}/mcp/alice", "auth": "origin_signature",
    })
    rs = await store.resource_server(cid)
    check("registration: the record is readable and pending",
          rs is not None and rs["status"] == "pending", f"{rs}")
    check("registration: it carries no secret to fall back on",
          rs is not None and not rs.get("secret"), f"{rs}")
    check("registration: it appears in the owner's registry",
          cid in await store.resource_servers())

    check("registration: approving a pending server reports success",
          await store.approve_resource_server(cid, "2026-01-01T00:00:00Z") is True)
    rs = await store.resource_server(cid)
    check("registration: and the approval is readable afterwards",
          rs is not None and rs["status"] == "active" and rs["consented"],
          f"{rs}")
    check("registration: the rest of the record survived the approval",
          rs is not None and rs["resource_uri"] == f"{cid}/mcp/alice"
          and rs["auth"] == "origin_signature", f"{rs}")

    # The race. Only one of these may be an approval; a read-then-write
    # implementation reports success twice and the second one is a lie.
    check("registration: approving twice does not approve twice",
          await store.approve_resource_server(cid, "2026-01-02T00:00:00Z") is False,
          "a second approval reported success")
    check("registration: approving something unregistered is not-found",
          await store.approve_resource_server("nobody", "2026-01-01T00:00:00Z") is False)

    # Withdrawal, and asking again. Re-registering must return it to pending
    # and never restore it, or asking again is a way to undo her answer.
    check("registration: she can withdraw it",
          await store.revoke_resource_server(cid) is True)
    check("registration: approving a revoked server is not-found",
          await store.approve_resource_server(cid, "2026-01-03T00:00:00Z") is False,
          "a revoked server was approved without registering again")
    await store.put_resource_server(cid, {
        "secret": "", "name": "asking again", "status": "pending",
        "consented": None, "last_pat_issued": None,
        "resource_uri": f"{cid}/mcp/alice", "auth": "origin_signature",
    })
    rs = await store.resource_server(cid)
    check("registration: re-registering lands in pending, not active",
          rs is not None and rs["status"] == "pending", f"{rs}")


async def test_terms_versions_are_immutable(store) -> None:
    """A published terms version's content never changes — that is what lets
    an agreement signed against it be checked later."""
    await store.publish_terms({"template_id": "t/v1", "purpose": "original"})
    await store.publish_terms({"template_id": "t/v1", "purpose": "rewritten"})
    doc = await store.terms_doc("t/v1")
    check("terms: a published version cannot be rewritten",
          doc is not None and doc["purpose"] == "original",
          f"content changed to {doc and doc.get('purpose')!r}")


async def test_tier_edits_bump_the_version(store) -> None:
    before = (await store.tiers())["tier1"]["terms"]["template_id"]
    updated = await store.update_tier("tier1", {"terms": {"purpose": "edited"}})
    after = updated["terms"]["template_id"]
    check("policy: an owner edit produces a new template version",
          after != before, f"{before} -> {after}")
    check("policy: the edit is readable back",
          (await store.tiers())["tier1"]["terms"]["purpose"] == "edited",
          "the edit did not stick")
    try:
        await store.update_tier("tier-nope", {})
        check("policy: an unknown tier raises", False, "no KeyError")
    except KeyError:
        check("policy: an unknown tier raises", True)


async def test_expired_negotiations_are_reaped(store) -> None:
    await store.mint_ticket(negotiation("fam_stale"), -1)   # already expired
    await store.mint_ticket(negotiation("fam_fresh"), 300)
    await store.reap_expired()
    check("reap: the expired negotiation is gone",
          await store.negotiation("fam_stale") is None, "stale record survived")
    check("reap: the live one is untouched",
          await store.negotiation("fam_fresh") is not None, "live record swept")
    await store.close_negotiation("fam_fresh")


async def test_events_reach_a_subscriber(store) -> None:
    """The owner's feed. Under Postgres this crosses a LISTEN/NOTIFY round
    trip, which is what makes an approval on one replica visible to a stream
    held by another."""
    stream = store.subscribe()
    received: list[dict] = []

    async def reader():
        async for item in stream:
            received.append(item)
            return

    task = asyncio.create_task(reader())
    await asyncio.sleep(0.1)          # let the subscription register
    await store.notify({"type": "pending", "family": "fam_evt"})
    try:
        await asyncio.wait_for(task, timeout=5)
    except asyncio.TimeoutError:
        task.cancel()
    check("events: a published event reaches a subscriber",
          received and received[0]["family"] == "fam_evt",
          f"received {received!r}")


async def test_tier_grants_and_approvals_are_kept_apart(store) -> None:
    """`standing.first_at_tier` and `standing.approved_at_tier` read two
    different lists, and only the second may relax a rule. If a backend wrote
    them to one field, an automatic grant would start justifying the next."""
    await store.put_connection({"handle": "jkt:tiers", "status": "active",
                                "first_seen": "2026-08-11T00:00:00Z",
                                "identity": {"level": "pseudonymous"},
                                "label": "test", "last_access": None,
                                "tiers_granted": [], "tiers_approved": [],
                                "revocations": 0})
    await store.note_tier_grant("jkt:tiers", "tier1")
    await store.note_tier_grant("jkt:tiers", "tier1")      # idempotent
    await store.note_tier_grant("jkt:tiers", "tier2")
    await store.note_tier_approval("jkt:tiers", "tier2")
    conn = await store.connection("jkt:tiers")
    check("standing: a tier grant is recorded once",
          conn["tiers_granted"] == ["tier1", "tier2"],
          f"got {conn.get('tiers_granted')!r}")
    check("standing: what she approved is a separate list",
          conn["tiers_approved"] == ["tier2"],
          f"got {conn.get('tiers_approved')!r}")
    await store.note_tier_grant("jkt:never-seen", "tier1")   # must not raise


async def test_revocations_survive_reconnection(store) -> None:
    """`standing.never_revoked` is worth nothing if an agent can clear its
    record by asking a second time, so the count is kept by the store."""
    await store.put_connection({"handle": "jkt:again", "status": "active",
                                "first_seen": "2026-08-11T00:00:00Z",
                                "identity": {"level": "pseudonymous"},
                                "label": "test", "last_access": None,
                                "tiers_granted": [], "tiers_approved": [],
                                "revocations": 0})
    await store.revoke_connection("jkt:again")
    conn = await store.connection("jkt:again")
    check("standing: revoking increments the count the policy reads",
          int(conn.get("revocations", 0)) == 1,
          f"got {conn.get('revocations')!r}")


async def test_tiers_can_be_added_and_removed(store) -> None:
    """Terms she writes herself. Creating is the uniqueness check and the write
    in one step, so two replicas cannot both believe they created it."""
    tier = {"name": "Statements", "resources": [], "ask_me": True, "rules": [],
            "terms": {"template_id": "alice/statements/v1", "purpose": "p",
                      "scope": [], "expires_in": 60, "prohibited": []}}
    await store.create_tier("statements", tier)
    check("policy: a tier she wrote is readable back",
          (await store.tiers())["statements"]["name"] == "Statements",
          "the new tier did not stick")
    try:
        await store.create_tier("statements", tier)
        check("policy: a duplicate tier id raises", False, "no KeyError")
    except KeyError:
        check("policy: a duplicate tier id raises", True)
    check("policy: deleting reports success",
          await store.delete_tier("statements") is True, "delete failed")
    check("policy: it is gone", "statements" not in await store.tiers(),
          "the tier survived deletion")
    check("policy: deleting an unknown tier is not-found",
          await store.delete_tier("statements") is False,
          "deleting nothing reported success")


async def test_blocked_operators_round_trip(store) -> None:
    """Blocking is idempotent because her portal and her personal AI may both
    be looking at a stale list."""
    check("operators: none are blocked to begin with",
          await store.blocked_operators() == {}, "something was already blocked")
    await store.block_operator("https://agent.example", "2026-08-11T00:00:00Z")
    await store.block_operator("https://agent.example", "2026-08-12T00:00:00Z")
    blocked = await store.blocked_operators()
    check("operators: a block is readable back once",
          list(blocked) == ["https://agent.example"], f"got {list(blocked)!r}")
    check("operators: blocking twice keeps the first answer",
          blocked["https://agent.example"]["blocked_at"] == "2026-08-11T00:00:00Z",
          "the second block overwrote the first")
    check("operators: unblocking reports success",
          await store.unblock_operator("https://agent.example") is True,
          "unblock failed")
    check("operators: and it is gone",
          await store.blocked_operators() == {}, "the block survived")
    check("operators: unblocking one that is not blocked is not-found",
          await store.unblock_operator("https://agent.example") is False,
          "unblocking nothing reported success")



async def test_the_ledger_names_the_agent(store) -> None:
    """A decision record that cannot say who it was about answers no question
    anybody asks afterwards.

    `handle` is a column rather than a key in `entry` for a reason worth
    testing: both backends flatten `entry` into the row they return, so an
    entry key of the same name would quietly win and the caller would never
    know. The last check here is that it cannot.
    """
    await store.ledger_add("promised", "fam_a", "2026-08-01T10:00:00Z",
                           {"tier": "tier1", "purpose": "review"},
                           handle="jkt:one")
    await store.ledger_add("touched", "fam_a", "2026-08-01T10:00:01Z",
                           {"tool": "get_positions"}, handle="jkt:one")
    await store.ledger_add("promised", "fam_b", "2026-08-01T11:00:00Z",
                           {"tier": "tier1"}, handle="jkt:two")
    # A decline arrives before the requesting side has signed anything, so
    # there is no key to file it under. That is a property, not a gap.
    await store.ledger_add("refused", "fam_c", "2026-08-01T12:00:00Z",
                           {"tier": "tier1"})

    everything = await store.ledger()
    check("ledger: every entry is returned",
          len(everything) == 4, f"got {len(everything)}")
    check("ledger: an unattributed entry has no handle",
          [e for e in everything if e["family"] == "fam_c"][0]["handle"] is None)

    mine = await store.ledger(handle="jkt:one")
    check("ledger: one agent's rows, and only that agent's",
          [e["family"] for e in mine] == ["fam_a", "fam_a"],
          f"got {[e.get('family') for e in mine]}")
    check("ledger: they come back oldest first",
          [e["kind"] for e in mine] == ["promised", "touched"],
          f"got {[e.get('kind') for e in mine]}")
    check("ledger: an unknown agent has no rows",
          await store.ledger(handle="jkt:nobody") == [])

    await store.ledger_add("promised", "fam_d", "2026-08-01T13:00:00Z",
                           {"kind": "spoofed", "family": "spoofed",
                            "ts": "spoofed", "handle": "jkt:spoofed"},
                           handle="jkt:three")
    row = (await store.ledger(handle="jkt:three"))[0]
    check("ledger: an entry key cannot shadow a column",
          (row["kind"], row["family"], row["handle"]) ==
          ("promised", "fam_d", "jkt:three"),
          f"got {row['kind']!r}/{row['family']!r}/{row['handle']!r}")


async def test_an_allowed_call_can_be_traced_to_its_agent(store) -> None:
    """The enforcement point reports an allowed call after the negotiation has
    been closed, and it is never told the handle — it enforces for an authority
    it cannot read. So the authority has to find the agent itself, from the
    grant the call was made under, and that has to keep working after the grant
    is spent."""
    await store.record_rpt("rpt_trace", "fam_trace", "jkt:traced",
                           {"tool": "execute_trade"}, "tier3")
    check("audit: the grant names the agent",
          (await store.grant_for_family("fam_trace") or {}).get("handle") == "jkt:traced")
    await store.consume_rpt("rpt_trace")
    check("audit: and still does once it is spent",
          (await store.grant_for_family("fam_trace") or {}).get("handle") == "jkt:traced")
    check("audit: an unknown negotiation resolves to nothing",
          await store.grant_for_family("fam_missing") is None)
    check("audit: and it carries the tier the call was made against",
          (await store.grant_for_family("fam_trace") or {}).get("tier") == "tier3")


async def test_trajectory_reads_the_window(store) -> None:
    """Policy about an agent's recent behaviour reads the record her decisions
    already wrote — no counters, nothing to keep in sync. What it must get
    right is the edge of the window and whose rows it is counting."""
    old, recent = "2026-07-01T00:00:00Z", "2026-08-01T00:00:00Z"
    since = "2026-07-15T00:00:00Z"
    await store.ledger_add("denied", "f1", old, {"tier": "tier3"}, handle="jkt:t")
    await store.ledger_add("denied", "f2", recent, {"tier": "tier3"}, handle="jkt:t")
    await store.ledger_add("denied", "f3", recent, {"tier": "tier3"}, handle="jkt:t")
    await store.ledger_add("promised", "f4", recent, {"tier": "tier1"}, handle="jkt:t")
    await store.ledger_add("denied", "f5", recent, {"tier": "tier3"}, handle="jkt:other")
    await store.ledger_add("touched", "f4", recent, {"tool": "get_positions",
                                                     "tier": "tier1"}, handle="jkt:t")
    await store.ledger_add("touched", "f4", recent, {"tool": "get_positions",
                                                     "tier": "tier1"}, handle="jkt:t")
    await store.ledger_add("touched", "f4", old, {"tool": "get_positions",
                                                  "tier": "tier1"}, handle="jkt:t")

    t = await store.trajectory("jkt:t", since)
    check("trajectory: denials inside the window are counted",
          t["denials"] == 2, f"got {t['denials']}")
    check("trajectory: distinct tiers, not repeats",
          sorted(t["tiers"]) == ["tier1", "tier3"], f"got {sorted(t['tiers'])}")
    check("trajectory: what it actually did is counted, inside the window",
          t["calls"] == 2, f"got {t['calls']}")
    check("trajectory: another agent's rows are not counted",
          (await store.trajectory("jkt:other", since))["denials"] == 1)
    check("trajectory: an agent with no history counts as nothing",
          await store.trajectory("jkt:none", since)
          == {"denials": 0, "tiers": [], "calls": 0})


async def test_claimed_origins_round_trip(store) -> None:
    """Origins she says are hers, kept apart from the ones she has shut out.

    Two tables rather than one with a flag, because the directions are not
    equivalent: a block may act on an agent's own claim, a claim may not. This
    asserts they stay separate — a bug that merged them would be invisible
    until an origin she blocked started relaxing requirements.
    """
    await store.claim_operator("https://alice.example", "2026-08-01T00:00:00Z")
    await store.claim_operator("https://alice.example", "2026-08-02T00:00:00Z")
    owned = await store.owned_operators()
    check("claim: an origin she claimed is hers", "https://alice.example" in owned)
    check("claim: claiming twice keeps the first answer",
          owned["https://alice.example"]["claimed_at"] == "2026-08-01T00:00:00Z")

    await store.block_operator("https://spam.example", "2026-08-01T00:00:00Z")
    check("claim: blocking does not claim",
          "https://spam.example" not in await store.owned_operators())
    check("claim: claiming does not block",
          "https://alice.example" not in await store.blocked_operators())

    check("claim: disclaiming reports that it did something",
          await store.disclaim_operator("https://alice.example") is True)
    check("claim: and is honest when there was nothing to drop",
          await store.disclaim_operator("https://alice.example") is False)
    check("claim: the origin is no longer hers",
          "https://alice.example" not in await store.owned_operators())


TESTS = [
    test_ticket_is_spent_once,
    test_save_creates_an_unseen_negotiation,
    test_negotiation_survives_its_ticket,
    test_rpt_is_burned_once,
    test_unknown_rpt_cannot_be_burned,
    test_owner_decides_once,
    test_revoke_burns_live_grants,
    test_resource_server_revocation_is_visible,
    test_a_resource_server_registers_and_waits,
    test_terms_versions_are_immutable,
    test_tier_edits_bump_the_version,
    test_tier_grants_and_approvals_are_kept_apart,
    test_revocations_survive_reconnection,
    test_tiers_can_be_added_and_removed,
    test_blocked_operators_round_trip,
    test_expired_negotiations_are_reaped,
    test_events_reach_a_subscriber,
    test_the_ledger_names_the_agent,
    test_an_allowed_call_can_be_traced_to_its_agent,
    test_trajectory_reads_the_window,
    test_claimed_origins_round_trip,
]


async def test_owners_cannot_see_each_other(backing) -> None:
    """The property the whole partition exists for.

    Every accessor is checked, not a representative sample, because the
    failure mode of a missed one is Carol reading Alice's ledger — and a
    partition that holds for nineteen of twenty tables is not a partition.
    """
    a = backing.owner("alice")
    c = backing.owner("carol")
    await a.seed()
    await c.seed()

    # policy
    await a.create_tier("secret-tier", {"name": "Alice only", "resources": [],
                                        "ask_me": True, "rules": [],
                                        "terms": {"template_id": "alice/x/v1"}})
    check("isolation: a tier of Alice's is invisible to Carol",
          "secret-tier" not in (await c.tiers()),
          "Carol can see Alice's tiers")

    # standing relationships
    await a.put_connection({"handle": "jkt:alice-agent", "first_seen": "t0",
                            "status": "active"})
    check("isolation: a connection of Alice's is invisible to Carol",
          await c.connection("jkt:alice-agent") is None,
          "Carol can read Alice's connection")
    check("isolation: Carol's connection list excludes Alice's",
          all(x["handle"] != "jkt:alice-agent" for x in await c.connections()),
          "Alice's connection is in Carol's list")

    # the audit trail
    await a.ledger_add("promised", "fam_a", "2026-01-01T00:00:00Z",
                       {"note": "alice"}, handle="jkt:alice-agent")
    check("isolation: Alice's ledger rows are invisible to Carol",
          len(await c.ledger()) == 0, "Carol sees Alice's ledger")
    check("isolation: trajectory does not count another owner's rows",
          (await c.trajectory("jkt:alice-agent", "2020-01-01T00:00:00Z"))["calls"] == 0,
          "Carol's trajectory counted Alice's rows")

    # operators
    await a.block_operator("https://bad.example", "t0")
    await a.claim_operator("https://mine.example", "t0")
    check("isolation: a block of Alice's does not block for Carol",
          "https://bad.example" not in (await c.blocked_operators()),
          "Carol inherited Alice's block")
    check("isolation: an origin Alice claims is not Carol's",
          "https://mine.example" not in (await c.owned_operators()),
          "Carol inherited Alice's claim")

    # terms
    await a.publish_terms({"template_id": "alice/advisor-tier1/v9",
                           "terms_uri": "https://alice-as/terms/x"})
    check("isolation: Alice's terms documents are invisible to Carol",
          await c.terms_doc("alice/advisor-tier1/v9") is None,
          "Carol can dereference Alice's terms")

    # single-use, across owners
    ticket = await a.mint_ticket(negotiation("fam_cross"), 300)
    check("isolation: Carol cannot spend a ticket minted for Alice",
          await c.consume_ticket(ticket) is None,
          "Carol consumed Alice's ticket")
    check("isolation: and the ticket still works for Alice afterwards",
          (await a.consume_ticket(ticket)) is not None,
          "Carol's attempt burned Alice's ticket")

    await a.record_rpt("rpt_cross", "fam_cross", "jkt:alice-agent", None)
    check("isolation: Carol cannot burn an RPT issued by Alice",
          await c.consume_rpt("rpt_cross") is None,
          "Carol burned Alice's grant")
    check("isolation: and Alice can still burn it",
          await a.consume_rpt("rpt_cross") == "fam_cross",
          "Carol's attempt burned it")

    # decisions
    rec = negotiation("fam_decide_cross")
    rec["state"] = "awaiting-owner"
    await a.mint_ticket(rec, 300)
    check("isolation: Carol cannot decide a negotiation of Alice's",
          await c.decide("fam_decide_cross", "approved") is False,
          "Carol decided Alice's request")

    # Resource servers. Compared before and after rather than against
    # "active": an earlier test in this suite revokes Alice's copy, and
    # asserting on an absolute value would be asserting on test order.
    before = (await a.resource_server("meridian-gateway"))["status"]
    revoked = await c.revoke_resource_server("meridian-gateway")
    after = (await a.resource_server("meridian-gateway"))["status"]
    check("isolation: Carol has her own registration of the same RS",
          revoked is True, "Carol had no registration to revoke")
    check("isolation: revoking it for Carol does not touch Alice's",
          before == after,
          f"Alice's registration went {before} -> {after}")
    check("isolation: and Carol's is the one that changed",
          (await c.resource_server("meridian-gateway"))["status"] == "revoked",
          "Carol's registration was not revoked")

    # A resource server that registers itself. One gateway serves both owners
    # from one origin, so the client_id is deliberately the same string: the
    # two relationships still have to be separate, or one owner's yes is
    # everybody's.
    shared = "https://gateway.example/shared"
    await a.put_resource_server(shared, {
        "secret": "", "name": "one origin, two owners", "status": "pending",
        "consented": None, "last_pat_issued": None,
        "resource_uri": f"{shared}/mcp/alice", "auth": "origin_signature"})
    check("isolation: a registration with Alice is not one with Carol",
          await c.resource_server(shared) is None,
          "Carol's registry holds a resource server that registered with Alice")
    check("isolation: Carol cannot approve what registered with Alice",
          await c.approve_resource_server(shared, "t0") is False,
          "Carol approved Alice's resource server")
    check("isolation: and it is still pending for Alice",
          (await a.resource_server(shared))["status"] == "pending",
          "Carol's attempt changed Alice's record")

    # the event feed
    seen: list[dict] = []

    async def listen():
        async for item in a.subscribe():
            seen.append(item)
            return

    task = asyncio.ensure_future(listen())
    await asyncio.sleep(0.05)
    await c.notify({"kind": "carol-only"})
    await asyncio.sleep(0.25)
    check("isolation: Carol's events do not reach Alice's stream",
          seen == [], f"Alice received {seen}")
    task.cancel()


async def run_against(label: str, backing) -> None:
    print(f"\n{label}")
    await backing.start()
    try:
        owner = backing.owner("alice")
        await owner.seed()
        for test in TESTS:
            await test(owner)
        await test_owners_cannot_see_each_other(backing)
    finally:
        await backing.close()


async def main() -> int:
    from store_memory import MemoryStore

    await run_against("memory store", MemoryStore())

    dsn = os.environ.get("UMA_AS_TEST_DSN")
    if dsn:
        from store_postgres import PostgresStore

        pg = PostgresStore(dsn)
        await _truncate(dsn)
        await run_against(f"postgres store ({dsn.rsplit('@', 1)[-1]})", pg)
        await test_an_older_database_is_refused(dsn)
    else:
        print("\npostgres store — skipped (set UMA_AS_TEST_DSN to include it)")

    print()
    if _failures:
        print(f"{len(_failures)} failed, {_passes} passed")
        for f in _failures:
            print(f"  - {f}")
        return 1
    print(f"{_passes} passed")
    return 0


async def test_an_older_database_is_refused(dsn: str) -> None:
    """A database from before multi-owner is refused at startup, by name.

    schema.sql adds the owner column to an existing database but deliberately
    does not rebuild its primary keys, so such a database comes up looking
    fine and fails on the first upsert with a 42P10 naming an ON CONFLICT
    clause. The guard turns that into one startup error that says to recreate
    the database.

    Both halves are asserted, and the second is the one that regressed once
    already: the file has to *apply* to an old database at all. An index
    naming the owner column above the ALTER that adds it fails on the first
    statement, and the connect-retry loop then reports a perfectly reachable
    database as unreachable thirty times over.
    """
    import asyncpg
    from store_postgres import PostgresStore, SchemaTooOld

    base, _, _ = dsn.rpartition("/")
    scratch = f"{base}/u4a_upgrade_probe"
    admin = await asyncpg.connect(dsn)
    try:
        await admin.execute("DROP DATABASE IF EXISTS u4a_upgrade_probe")
        await admin.execute("CREATE DATABASE u4a_upgrade_probe")
    finally:
        await admin.close()

    # The shape this schema had before owners: single-column primary keys,
    # and tickets keyed into negotiations by family alone. Three tables rather
    # than all eleven, but the three that matter — one plain, one that another
    # table has a foreign key into, and one the seeder writes to on every
    # start. schema.sql creates the rest correctly, so the guard below should
    # name exactly these.
    conn = await asyncpg.connect(scratch)
    try:
        await conn.execute("""
            CREATE TABLE negotiations (family text PRIMARY KEY, state text,
                                       decision text, expires double precision,
                                       rec jsonb NOT NULL);
            CREATE TABLE tickets (ticket text PRIMARY KEY, family text NOT NULL,
                                  FOREIGN KEY (family)
                                      REFERENCES negotiations(family)
                                      ON DELETE CASCADE);
            CREATE TABLE tiers (tier_id text PRIMARY KEY, tier jsonb NOT NULL);
        """)
    finally:
        await conn.close()

    try:
        await PostgresStore(scratch).start()
        check("upgrade: an older database is refused", False,
              "it started, and would have failed on the first upsert")
    except SchemaTooOld as exc:
        named = {t for t in ("negotiations", "tickets", "tiers") if t in str(exc)}
        check("upgrade: an older database is refused at startup, by name",
              named == {"negotiations", "tickets", "tiers"}, str(exc)[:160])
        check("upgrade: and only the tables that actually predate it",
              "connections" not in str(exc) and "rpts" not in str(exc),
              "a table schema.sql just created correctly was reported stale")
    except Exception as exc:                                       # noqa: BLE001
        # Anything else means the file did not even apply — which is the
        # regression this test exists for, and it does not look like one
        # unless it is named.
        check("upgrade: schema.sql applies to a database that predates it",
              False, f"{type(exc).__name__}: {str(exc)[:160]}")

    admin = await asyncpg.connect(dsn)
    try:
        await admin.execute("DROP DATABASE IF EXISTS u4a_upgrade_probe")
    finally:
        await admin.close()


async def _truncate(dsn: str) -> None:
    """Start each Postgres run from an empty database; the suite asserts on
    seeded defaults it would otherwise inherit from the previous run."""
    import asyncpg

    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(
            "DROP TABLE IF EXISTS tickets, negotiations, rpts, connections, "
            "resource_servers, ledger, terms_docs, tiers, owner_events, "
            "blocked_operators, owned_operators CASCADE")
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
