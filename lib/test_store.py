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
                           {"tool": "execute_trade"})
    check("audit: the grant names the agent",
          await store.handle_for_family("fam_trace") == "jkt:traced")
    await store.consume_rpt("rpt_trace")
    check("audit: and still does once it is spent",
          await store.handle_for_family("fam_trace") == "jkt:traced")
    check("audit: an unknown negotiation resolves to nothing",
          await store.handle_for_family("fam_missing") is None)


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

    t = await store.trajectory("jkt:t", since)
    check("trajectory: denials inside the window are counted",
          t["denials"] == 2, f"got {t['denials']}")
    check("trajectory: distinct tiers, not repeats",
          sorted(t["tiers"]) == ["tier1", "tier3"], f"got {sorted(t['tiers'])}")
    check("trajectory: another agent's rows are not counted",
          (await store.trajectory("jkt:other", since))["denials"] == 1)
    check("trajectory: an agent with no history counts as nothing",
          await store.trajectory("jkt:none", since) == {"denials": 0, "tiers": []})


TESTS = [
    test_ticket_is_spent_once,
    test_negotiation_survives_its_ticket,
    test_rpt_is_burned_once,
    test_unknown_rpt_cannot_be_burned,
    test_owner_decides_once,
    test_revoke_burns_live_grants,
    test_resource_server_revocation_is_visible,
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
]


async def run_against(label: str, store) -> None:
    print(f"\n{label}")
    await store.start()
    try:
        for test in TESTS:
            await test(store)
    finally:
        await store.close()


async def main() -> int:
    from store_memory import MemoryStore

    await run_against("memory store", MemoryStore())

    dsn = os.environ.get("UMA_AS_TEST_DSN")
    if dsn:
        from store_postgres import PostgresStore

        pg = PostgresStore(dsn)
        await _truncate(dsn)
        await run_against(f"postgres store ({dsn.rsplit('@', 1)[-1]})", pg)
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


async def _truncate(dsn: str) -> None:
    """Start each Postgres run from an empty database; the suite asserts on
    seeded defaults it would otherwise inherit from the previous run."""
    import asyncpg

    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(
            "DROP TABLE IF EXISTS tickets, negotiations, rpts, connections, "
            "resource_servers, ledger, terms_docs, tiers, owner_events, "
            "blocked_operators CASCADE")
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
