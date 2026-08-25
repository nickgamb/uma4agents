"""Postgres store — the replicated deployment.

Postgres rather than a cache: every guarantee the grant loop needs is one
statement here, and a reader can say each of them aloud.

  the single-use burn      UPDATE ... WHERE NOT consumed RETURNING family
  the single-use ticket    DELETE ... RETURNING family, joined to its record
  "what is Alice waiting on"  a WHERE clause
  the owner's live feed    LISTEN / NOTIFY
  the audit trail          an append-only table that survives a restart

A key/value cache gives the first two only through Lua or WATCH gymnastics,
gives the last one no durability at all, and adds a second stateful
component to explain. Nothing in this workload is hot enough to want a cache
tier in front of the database — which is worth saying out loud rather than
adding one out of habit.

This module is imported only when ``UMA_AS_STORE=postgres``; the compose
stack never loads it and never needs the driver.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import AsyncIterator

import asyncpg

import policy
import store

# Retention for the owner's event feed. The rows exist to be read once by
# each live subscriber; anything older than this is history the ledger
# already holds properly.
EVENT_RETENTION_SECONDS = 3600


class SchemaTooOld(Exception):
    """A database whose keys predate multi-owner. Never retried: waiting
    changes nothing, and the retry loop exists for a database that is coming
    back, not for one that is the wrong shape."""


class PostgresStore:
    """The pool, the schema, and the one LISTEN connection. Holds no owner's
    state — ``owner()`` gives you that."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None
        self._listener: asyncpg.Connection | None = None
        # Per owner. A single shared list would put Carol's pending requests
        # on Alice's event stream, which is a disclosure rather than a bug in
        # the fan-out.
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    def owner(self, owner: str) -> "PostgresOwnerStore":
        return PostgresOwnerStore(self, owner)

    async def owners(self) -> list[str]:
        rows = await self._pool.fetch("SELECT DISTINCT owner FROM tiers ORDER BY owner")
        return [r["owner"] for r in rows]

    # --- lifecycle ---------------------------------------------------------

    # The tables an owner-scoped upsert names. Kept beside the check rather
    # than derived, so adding a table to schema.sql without deciding whether
    # it is owner-scoped shows up here as a question rather than as silence.
    _OWNER_KEYED = ("negotiations", "tickets", "rpts", "connections",
                    "resource_servers", "blocked_operators", "owned_operators",
                    "terms_docs", "tiers")

    async def _assert_owner_keys(self, conn) -> None:
        """Refuse to run against a database whose keys predate multi-owner.

        schema.sql deliberately does not retrofit the composite primary keys —
        that is a decision recorded there, and a database needing them is
        recreated. What it cannot do is leave the discovery of that to chance:
        the additive column migration succeeds, so such a database *looks*
        upgraded and then fails on the first upsert with `42P10`, an error
        that names an ON CONFLICT clause and nothing an operator can act on.

        Better here, at startup, once, saying what to do about it.
        """
        stale = [t for t in self._OWNER_KEYED if not await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM pg_index i"
            "  JOIN pg_class c ON c.oid = i.indrelid"
            "  JOIN pg_attribute a ON a.attrelid = c.oid"
            "                     AND a.attnum = ANY (i.indkey)"
            " WHERE i.indisprimary AND c.relname = $1 AND a.attname = 'owner')",
            t)]
        if stale:
            raise SchemaTooOld(
                "this database predates multi-owner: "
                f"{', '.join(stale)} still key on a single owner's rows. "
                "The owner column backfills but the primary keys are not "
                "retrofitted (see the note at the end of schema.sql), so "
                "every upsert would fail. Recreate the database — under "
                "compose `make down && make up`, in the cluster by deleting "
                "the CloudNativePG Cluster and re-applying.")

    async def start(self) -> None:
        """Connect, create the schema if absent, seed, and start listening.

        Retried rather than fatal. A replicated database is unreachable for a
        few seconds every time it fails over or is upgraded, and a process
        that exits on that turns a routine event into a crash loop — which is
        worse than the outage, because the pod then backs off for minutes
        after the database is fine again.

        This is the failure the chaos target found: kill the primary while an
        authorization server happens to be starting, and the server exits
        instead of waiting the two seconds the promotion takes.
        """
        import pathlib

        schema = (pathlib.Path(__file__).parent / "schema.sql").read_text()
        last: Exception | None = None
        for attempt in range(30):
            try:
                self._pool = await asyncpg.create_pool(
                    self._dsn, min_size=1, max_size=8,
                    # Do not wait forever on a primary that is being replaced.
                    command_timeout=10, timeout=10)
                async with self._pool.acquire() as conn:
                    # Every replica runs this; CREATE ... IF NOT EXISTS makes
                    # the losers no-ops rather than errors.
                    await conn.execute(schema)
                    await self._assert_owner_keys(conn)
                await self._start_listener()
                return
            except SchemaTooOld:
                # Not a transient failure. Retrying it thirty times would bury
                # the one message that says what to do under a minute of
                # connect-retry noise and then report the wrong cause.
                if self._pool is not None:
                    await self._pool.close()
                    self._pool = None
                raise
            except Exception as exc:            # noqa: BLE001 — any of them
                last = exc
                if self._pool is not None:
                    await self._pool.close()
                    self._pool = None
                print(json.dumps({
                    "event": "store.connect_retry", "attempt": attempt + 1,
                    "error": str(exc)[:160],
                }), flush=True)
                await asyncio.sleep(2)
        raise RuntimeError(
            f"could not reach the grant database after 30 attempts: {last}")


    async def _start_listener(self) -> None:
        """One dedicated connection per replica, listening for owner events.

        It is deliberately not from the pool: a LISTENing connection is
        occupied for the life of the process, and taking it from the pool
        would quietly shrink the pool by one on every replica.
        """
        self._listener = await asyncpg.connect(self._dsn)
        await self._listener.add_listener("owner_events", self._on_event)

    def _on_event(self, _conn, _pid, _channel, payload: str) -> None:
        # asyncpg calls this from the event loop but not as a coroutine, so
        # the row read is scheduled rather than awaited here.
        asyncio.create_task(self._fanout(int(payload)))

    async def _fanout(self, event_id: int) -> None:
        if not self._subscribers:
            return
        row = await self._pool.fetchrow(
            "SELECT owner, payload FROM owner_events WHERE id = $1", event_id)
        if row is None:
            return
        item = json.loads(row["payload"])
        # Routed, not broadcast. Every replica's listener sees every event,
        # which is what makes a replica holding one owner's stream correct;
        # delivering it to the wrong owner would not be.
        for q in list(self._subscribers.get(row["owner"], ())):
            await q.put(item)

    async def close(self) -> None:
        if self._listener is not None:
            await self._listener.close()
        if self._pool is not None:
            await self._pool.close()


class PostgresOwnerStore:
    """One owner's state, over the shared pool.

    Every statement in this class filters on ``owner``, and none of them can
    see another owner's rows. That is the property that makes the multi-tenant
    deployment and a single person's authorization server the same code: this
    object does not know, and does not need to know, how many others exist.
    """

    def __init__(self, parent: PostgresStore, owner: str) -> None:
        self._parent = parent
        self._o = owner

    @property
    def _pool(self) -> asyncpg.Pool:
        return self._parent._pool

    async def seed(self) -> None:
        """Starting policy for an owner who has none. ON CONFLICT DO NOTHING is
        the whole concurrency story: three replicas racing leaves one copy, and
        a later owner edit is never overwritten by a restart."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for tier_id, tier in policy.defaults(self._o).items():
                    await conn.execute(
                        "INSERT INTO tiers (owner, tier_id, tier) VALUES ($1, $2, $3) "
                        "ON CONFLICT (owner, tier_id) DO NOTHING",
                        self._o, tier_id, json.dumps(tier))
                for cid, rs in store.default_resource_servers(self._o).items():
                    await conn.execute(
                        "INSERT INTO resource_servers (owner, client_id, rs) "
                        "VALUES ($1, $2, $3) "
                        "ON CONFLICT (owner, client_id) DO NOTHING",
                        self._o, cid, json.dumps(rs))

    # --- negotiations and tickets ------------------------------------------

    async def mint_ticket(self, rec: dict, ttl: float) -> str:
        import secrets

        ticket = f"tkt_{secrets.token_urlsafe(24)}"
        rec["expires"] = time.time() + ttl
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO negotiations (owner, family, expires, state, decision, rec) "
                    "VALUES ($6, $1, $2, $3, $4, $5) "
                    "ON CONFLICT (owner, family) DO UPDATE SET "
                    "  expires = EXCLUDED.expires, state = EXCLUDED.state, "
                    "  decision = EXCLUDED.decision, rec = EXCLUDED.rec",
                    rec["family"], rec["expires"], rec["state"],
                    rec.get("decision"), json.dumps(rec), self._o)
                await conn.execute(
                    "INSERT INTO tickets (owner, ticket, family) VALUES ($3, $1, $2)",
                    ticket, rec["family"], self._o)
        return ticket

    async def consume_ticket(self, ticket: str) -> dict | None:
        # One statement: the ticket is spent by the act of asking about it.
        # Only the index row is deleted -- the negotiation stays addressable
        # by family, so the owner's portal can still see and decide a pending
        # request in the window before the rotation is issued.
        row = await self._pool.fetchrow(
            """
            WITH popped AS (
                DELETE FROM tickets WHERE ticket = $1 AND owner = $3
                RETURNING family
            )
            SELECT n.rec FROM negotiations n
              JOIN popped p ON n.family = p.family
             WHERE n.expires >= $2 AND n.owner = $3
            """,
            ticket or "", time.time(), self._o)
        return json.loads(row["rec"]) if row else None

    async def negotiation(self, family: str) -> dict | None:
        row = await self._pool.fetchrow(
            "SELECT rec FROM negotiations WHERE family = $1 AND owner = $2",
            family, self._o)
        return json.loads(row["rec"]) if row else None

    async def save_negotiation(self, rec: dict) -> None:
        await self._pool.execute(
            "UPDATE negotiations SET state = $2, decision = $3, rec = $4 "
            "WHERE family = $1 AND owner = $5",
            rec["family"], rec["state"], rec.get("decision"), json.dumps(rec),
            self._o)

    async def close_negotiation(self, family: str | None) -> None:
        if not family:
            return
        # Tickets cascade.
        await self._pool.execute(
            "DELETE FROM negotiations WHERE family = $1 AND owner = $2",
            family, self._o)

    async def reap_expired(self) -> int:
        result = await self._pool.execute(
            "DELETE FROM negotiations WHERE expires < $1 AND owner = $2",
            time.time(), self._o)
        # Opportunistic: the event feed is bounded by the same sweep rather
        # than by a second timer nobody would remember to run.
        await self._pool.execute(
            "DELETE FROM owner_events "
            "WHERE ts < now() - ($1 || ' seconds')::interval AND owner = $2",
            str(EVENT_RETENTION_SECONDS), self._o)
        return int(result.rsplit(" ", 1)[-1] or 0)

    async def pending_negotiations(self) -> list[dict]:
        rows = await self._pool.fetch(
            "SELECT rec FROM negotiations "
            "WHERE state = 'awaiting-owner' AND decision IS NULL AND owner = $1",
            self._o)
        return [json.loads(r["rec"]) for r in rows]

    async def decide(self, family: str, decision: str) -> bool:
        # The WHERE clause is the guard: a second tap, or a stale portal,
        # updates nothing and is told so.
        row = await self._pool.fetchrow(
            """
            UPDATE negotiations
               SET decision = $2,
                   rec = jsonb_set(rec, '{decision}', to_jsonb($2::text))
             WHERE family = $1
               AND owner = $3
               AND state = 'awaiting-owner'
               AND decision IS NULL
            RETURNING family
            """,
            family, decision, self._o)
        return row is not None

    # --- RPTs ---------------------------------------------------------------

    async def record_rpt(self, jti: str, family: str, handle: str,
                         operation: dict | None, tier: str | None = None) -> None:
        await self._pool.execute(
            "INSERT INTO rpts (owner, jti, family, handle, operation, consumed, tier) "
            "VALUES ($6, $1, $2, $3, $4, false, $5)",
            jti, family, handle,
            json.dumps(operation) if operation is not None else None, tier,
            self._o)

    async def rpt(self, jti: str) -> dict | None:
        row = await self._pool.fetchrow(
            "SELECT jti, family, handle, operation, consumed FROM rpts "
            "WHERE jti = $1 AND owner = $2", jti, self._o)
        if row is None:
            return None
        return {"jti": row["jti"], "family": row["family"],
                "handle": row["handle"], "consumed": row["consumed"],
                "operation": json.loads(row["operation"])
                if row["operation"] else None}

    async def consume_rpt(self, jti: str) -> str | None:
        # The statement this whole module exists for. Zero rows means another
        # replica burned it first, which the caller answers by denying.
        row = await self._pool.fetchrow(
            "UPDATE rpts SET consumed = true "
            "WHERE jti = $1 AND owner = $2 AND consumed = false "
            "RETURNING family", jti, self._o)
        return row["family"] if row else None

    # --- standing relationships ---------------------------------------------

    async def connection(self, handle: str) -> dict | None:
        row = await self._pool.fetchrow(
            "SELECT conn FROM connections WHERE handle = $1 AND owner = $2",
            handle, self._o)
        return json.loads(row["conn"]) if row else None

    async def put_connection(self, conn: dict) -> None:
        await self._pool.execute(
            "INSERT INTO connections (owner, handle, first_seen, conn) "
            "VALUES ($4, $1, $2, $3) "
            "ON CONFLICT (owner, handle) DO UPDATE SET conn = EXCLUDED.conn",
            conn["handle"], conn["first_seen"], json.dumps(conn), self._o)

    async def connections(self) -> list[dict]:
        rows = await self._pool.fetch(
            "SELECT conn FROM connections WHERE owner = $1 "
            "ORDER BY first_seen DESC", self._o)
        return [json.loads(r["conn"]) for r in rows]

    async def touch_connection(self, handle: str, when: str) -> None:
        await self._pool.execute(
            "UPDATE connections "
            "SET conn = jsonb_set(conn, '{last_access}', to_jsonb($2::text)) "
            "WHERE handle = $1 AND owner = $3", handle, when, self._o)

    async def note_tier_grant(self, handle: str, tier_id: str) -> None:
        # Append-if-absent in one statement, so two replicas granting at the
        # same tier concurrently cannot lose each other's write.
        await self._pool.execute(
            "UPDATE connections SET conn = jsonb_set("
            "  conn, '{tiers_granted}',"
            "  COALESCE(conn->'tiers_granted', '[]'::jsonb) || to_jsonb($2::text))"
            "WHERE handle = $1 AND owner = $3 "
            "  AND NOT COALESCE(conn->'tiers_granted', '[]'::jsonb)"
            "          @> to_jsonb($2::text)", handle, tier_id, self._o)

    async def note_tier_approval(self, handle: str, tier_id: str) -> None:
        await self._pool.execute(
            "UPDATE connections SET conn = jsonb_set("
            "  conn, '{tiers_approved}',"
            "  COALESCE(conn->'tiers_approved', '[]'::jsonb) || to_jsonb($2::text))"
            "WHERE handle = $1 AND owner = $3 "
            "  AND NOT COALESCE(conn->'tiers_approved', '[]'::jsonb)"
            "          @> to_jsonb($2::text)", handle, tier_id, self._o)

    async def revoke_connection(self, handle: str) -> int | None:
        async with self._pool.acquire() as conn:
            # One transaction: a revocation that flipped the connection and
            # then failed to burn the tokens would leave the agent holding
            # exactly the authority Alice had just withdrawn.
            async with conn.transaction():
                row = await conn.fetchrow(
                    "UPDATE connections "
                    "SET conn = jsonb_set("
                    "  jsonb_set(conn, '{status}', '\"revoked\"'),"
                    "  '{revocations}',"
                    "  to_jsonb(COALESCE((conn->>'revocations')::int, 0) + 1)) "
                    "WHERE handle = $1 AND owner = $2 RETURNING handle",
                    handle, self._o)
                if row is None:
                    return None
                killed = await conn.fetch(
                    "UPDATE rpts SET consumed = true "
                    "WHERE handle = $1 AND owner = $2 AND consumed = false "
                    "RETURNING jti", handle, self._o)
                return len(killed)

    # --- operators she has shut out -------------------------------------------

    async def blocked_operators(self) -> dict[str, dict]:
        rows = await self._pool.fetch(
            "SELECT origin, blocked FROM blocked_operators WHERE owner = $1",
            self._o)
        return {r["origin"]: json.loads(r["blocked"]) for r in rows}

    async def block_operator(self, origin: str, when: str) -> None:
        await self._pool.execute(
            "INSERT INTO blocked_operators (owner, origin, blocked) "
            "VALUES ($3, $1, $2) "
            "ON CONFLICT (owner, origin) DO NOTHING",
            origin, json.dumps({"origin": origin, "blocked_at": when}), self._o)

    async def unblock_operator(self, origin: str) -> bool:
        row = await self._pool.fetchrow(
            "DELETE FROM blocked_operators WHERE origin = $1 AND owner = $2 "
            "RETURNING origin", origin, self._o)
        return row is not None

    # --- operators she says are her own --------------------------------------

    async def owned_operators(self) -> dict[str, dict]:
        rows = await self._pool.fetch(
            "SELECT origin, owned FROM owned_operators WHERE owner = $1", self._o)
        return {r["origin"]: json.loads(r["owned"]) for r in rows}

    async def claim_operator(self, origin: str, when: str) -> None:
        await self._pool.execute(
            "INSERT INTO owned_operators (owner, origin, owned) VALUES ($3, $1, $2) "
            "ON CONFLICT (owner, origin) DO NOTHING",
            origin, json.dumps({"origin": origin, "claimed_at": when}), self._o)

    async def disclaim_operator(self, origin: str) -> bool:
        row = await self._pool.fetchrow(
            "DELETE FROM owned_operators WHERE origin = $1 AND owner = $2 "
            "RETURNING origin", origin, self._o)
        return row is not None

    # --- resource servers ----------------------------------------------------

    async def resource_servers(self) -> dict[str, dict]:
        rows = await self._pool.fetch(
            "SELECT client_id, rs FROM resource_servers WHERE owner = $1", self._o)
        return {r["client_id"]: json.loads(r["rs"]) for r in rows}

    async def resource_server(self, client_id: str) -> dict | None:
        row = await self._pool.fetchrow(
            "SELECT rs FROM resource_servers WHERE client_id = $1 AND owner = $2",
            client_id, self._o)
        return json.loads(row["rs"]) if row else None

    async def put_resource_server(self, client_id: str, rs: dict) -> None:
        await self._pool.execute(
            "INSERT INTO resource_servers (owner, client_id, rs) "
            "VALUES ($3, $1, $2) "
            "ON CONFLICT (owner, client_id) DO UPDATE SET rs = EXCLUDED.rs",
            client_id, json.dumps(rs), self._o)

    async def approve_resource_server(self, client_id: str, when: str) -> bool:
        # The status test is inside the statement, so two portals approving at
        # once produce one approval and one honest "nothing to do".
        row = await self._pool.fetchrow(
            "UPDATE resource_servers SET rs = jsonb_set("
            "  jsonb_set(rs, '{status}', '\"active\"'),"
            "  '{consented}', to_jsonb($3::text)) "
            "WHERE client_id = $1 AND owner = $2 "
            "  AND rs->>'status' = 'pending' RETURNING client_id",
            client_id, self._o, when)
        return row is not None

    async def touch_pat(self, client_id: str, when: str) -> None:
        await self._pool.execute(
            "UPDATE resource_servers "
            "SET rs = jsonb_set(rs, '{last_pat_issued}', to_jsonb($2::text)) "
            "WHERE client_id = $1 AND owner = $3", client_id, when, self._o)

    async def revoke_resource_server(self, client_id: str) -> bool:
        row = await self._pool.fetchrow(
            "UPDATE resource_servers "
            "SET rs = jsonb_set(rs, '{status}', '\"revoked\"') "
            "WHERE client_id = $1 AND owner = $2 RETURNING client_id",
            client_id, self._o)
        return row is not None

    # --- owner-visible documents ---------------------------------------------

    async def ledger_add(self, kind: str, family: str, ts: str,
                         entry: dict, handle: str | None = None) -> None:
        await self._pool.execute(
            "INSERT INTO ledger (owner, kind, family, ts, entry, handle) "
            "VALUES ($6, $1, $2, $3, $4, $5)",
            kind, family, ts, json.dumps(entry), handle, self._o)

    async def ledger(self, handle: str | None = None) -> list[dict]:
        if handle is None:
            rows = await self._pool.fetch(
                "SELECT kind, family, ts, entry, handle FROM ledger "
                "WHERE owner = $1 ORDER BY seq", self._o)
        else:
            rows = await self._pool.fetch(
                "SELECT kind, family, ts, entry, handle FROM ledger "
                "WHERE handle = $1 AND owner = $2 ORDER BY seq",
                handle, self._o)
        # Columns last, so an `entry` key can never shadow one of them.
        return [{**json.loads(r["entry"]), "kind": r["kind"],
                 "family": r["family"], "ts": r["ts"], "handle": r["handle"]}
                for r in rows]

    async def grant_for_family(self, family: str) -> dict | None:
        row = await self._pool.fetchrow(
            "SELECT handle, tier FROM rpts WHERE family = $1 AND owner = $2 "
            "AND handle IS NOT NULL ORDER BY jti LIMIT 1", family, self._o)
        return {"handle": row["handle"], "tier": row["tier"]} if row else None

    async def trajectory(self, handle: str, since: str) -> dict:
        # One pass over the (handle, kind, ts) index. `ts` is fixed-width
        # UTC, so the lexicographic comparison is a time comparison.
        row = await self._pool.fetchrow(
            "SELECT count(*) FILTER (WHERE kind = 'denied') AS denials, "
            "       count(*) FILTER (WHERE kind = 'touched') AS calls, "
            "       coalesce(array_agg(DISTINCT entry->>'tier') "
            "                FILTER (WHERE entry ? 'tier'), '{}') AS tiers "
            "  FROM ledger WHERE handle = $1 AND ts >= $2 AND owner = $3",
            handle, since, self._o)
        return {"denials": int(row["denials"] or 0),
                "tiers": sorted(row["tiers"] or []),
                "calls": int(row["calls"] or 0)}

    async def publish_terms(self, doc: dict) -> None:
        # DO NOTHING, not DO UPDATE: a published version's content never
        # changes. An owner edit produces a new template_id, and both remain
        # dereferenceable.
        await self._pool.execute(
            "INSERT INTO terms_docs (owner, template_id, doc) VALUES ($3, $1, $2) "
            "ON CONFLICT (owner, template_id) DO NOTHING",
            doc["template_id"], json.dumps(doc), self._o)

    async def terms_doc(self, template_id: str) -> dict | None:
        row = await self._pool.fetchrow(
            "SELECT doc FROM terms_docs WHERE template_id = $1 AND owner = $2",
            template_id, self._o)
        return json.loads(row["doc"]) if row else None

    async def terms_docs(self) -> list[dict]:
        rows = await self._pool.fetch(
            "SELECT doc FROM terms_docs WHERE owner = $1 ORDER BY template_id",
            self._o)
        return [json.loads(r["doc"]) for r in rows]

    # --- Alice's policy -------------------------------------------------------

    async def tiers(self) -> dict[str, dict]:
        rows = await self._pool.fetch(
            "SELECT tier_id, tier FROM tiers WHERE owner = $1", self._o)
        return {r["tier_id"]: json.loads(r["tier"]) for r in rows}

    async def create_tier(self, tier_id: str, tier: dict) -> dict:
        # ON CONFLICT DO NOTHING, then check what came back: the uniqueness
        # test and the write are one statement, so two replicas cannot both
        # believe they created it.
        row = await self._pool.fetchrow(
            "INSERT INTO tiers (owner, tier_id, tier) VALUES ($3, $1, $2) "
            "ON CONFLICT (owner, tier_id) DO NOTHING RETURNING tier_id",
            tier_id, json.dumps(tier), self._o)
        if row is None:
            raise KeyError(tier_id)
        return tier

    async def delete_tier(self, tier_id: str) -> bool:
        row = await self._pool.fetchrow(
            "DELETE FROM tiers WHERE tier_id = $1 AND owner = $2 "
            "RETURNING tier_id", tier_id, self._o)
        return row is not None

    async def update_tier(self, tier_id: str, patch: dict) -> dict:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # FOR UPDATE so two portals editing at once produce two
                # version bumps in order, not one lost edit. The version is
                # what ties a signed agreement to the terms in force when it
                # was signed, so losing a bump is losing an audit trail.
                row = await conn.fetchrow(
                    "SELECT tier FROM tiers WHERE tier_id = $1 AND owner = $2 "
                    "FOR UPDATE", tier_id, self._o)
                if row is None:
                    raise KeyError(tier_id)
                updated = policy.apply_patch(json.loads(row["tier"]), patch)
                await conn.execute(
                    "UPDATE tiers SET tier = $2 WHERE tier_id = $1 AND owner = $3",
                    tier_id, json.dumps(updated), self._o)
                return updated

    # --- the organization above her -------------------------------------------

    async def organization(self) -> dict | None:
        row = await self._pool.fetchrow(
            "SELECT record FROM organizations WHERE owner = $1", self._o)
        return json.loads(row["record"]) if row else None

    async def set_organization(self, record: dict) -> None:
        await self._pool.execute(
            "INSERT INTO organizations (owner, record) VALUES ($1, $2) "
            "ON CONFLICT (owner) DO UPDATE SET record = EXCLUDED.record",
            self._o, json.dumps(record))

    async def clear_organization(self) -> bool:
        row = await self._pool.fetchrow(
            "DELETE FROM organizations WHERE owner = $1 RETURNING owner", self._o)
        return row is not None

    # --- fan-out ---------------------------------------------------------------

    async def notify(self, payload: dict) -> None:
        row = await self._pool.fetchrow(
            "INSERT INTO owner_events (owner, payload) VALUES ($2, $1) "
            "RETURNING id", json.dumps(payload), self._o)
        # Every replica's listener receives this, so it does not matter which
        # one holds Alice's stream.
        await self._pool.execute("SELECT pg_notify('owner_events', $1)",
                                 str(row["id"]))

    async def subscribe(self) -> AsyncIterator[dict]:
        queue: asyncio.Queue = asyncio.Queue()
        subs = self._parent._subscribers.setdefault(self._o, [])
        subs.append(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            if queue in subs:
                subs.remove(queue)
