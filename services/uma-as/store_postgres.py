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


class PostgresStore:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None
        self._listener: asyncpg.Connection | None = None
        self._subscribers: list[asyncio.Queue] = []

    # --- lifecycle ---------------------------------------------------------

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
                await self._seed()
                await self._start_listener()
                return
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

    async def _seed(self) -> None:
        """Insert the defaults if nobody has yet. ON CONFLICT DO NOTHING is
        the whole concurrency story: three replicas racing to seed leaves one
        copy, and a later owner edit is never overwritten by a restart."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for tier_id, tier in policy.defaults().items():
                    await conn.execute(
                        "INSERT INTO tiers (tier_id, tier) VALUES ($1, $2) "
                        "ON CONFLICT (tier_id) DO NOTHING",
                        tier_id, json.dumps(tier))
                for cid, rs in store.default_resource_servers().items():
                    await conn.execute(
                        "INSERT INTO resource_servers (client_id, rs) VALUES ($1, $2) "
                        "ON CONFLICT (client_id) DO NOTHING",
                        cid, json.dumps(rs))

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
            "SELECT payload FROM owner_events WHERE id = $1", event_id)
        if row is None:
            return
        item = json.loads(row["payload"])
        for q in list(self._subscribers):
            await q.put(item)

    async def close(self) -> None:
        if self._listener is not None:
            await self._listener.close()
        if self._pool is not None:
            await self._pool.close()

    # --- negotiations and tickets ------------------------------------------

    async def mint_ticket(self, rec: dict, ttl: float) -> str:
        import secrets

        ticket = f"tkt_{secrets.token_urlsafe(24)}"
        rec["expires"] = time.time() + ttl
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO negotiations (family, expires, state, decision, rec) "
                    "VALUES ($1, $2, $3, $4, $5) "
                    "ON CONFLICT (family) DO UPDATE SET "
                    "  expires = EXCLUDED.expires, state = EXCLUDED.state, "
                    "  decision = EXCLUDED.decision, rec = EXCLUDED.rec",
                    rec["family"], rec["expires"], rec["state"],
                    rec.get("decision"), json.dumps(rec))
                await conn.execute(
                    "INSERT INTO tickets (ticket, family) VALUES ($1, $2)",
                    ticket, rec["family"])
        return ticket

    async def consume_ticket(self, ticket: str) -> dict | None:
        # One statement: the ticket is spent by the act of asking about it.
        # Only the index row is deleted -- the negotiation stays addressable
        # by family, so the owner's portal can still see and decide a pending
        # request in the window before the rotation is issued.
        row = await self._pool.fetchrow(
            """
            WITH popped AS (
                DELETE FROM tickets WHERE ticket = $1 RETURNING family
            )
            SELECT n.rec FROM negotiations n
              JOIN popped p ON n.family = p.family
             WHERE n.expires >= $2
            """,
            ticket or "", time.time())
        return json.loads(row["rec"]) if row else None

    async def negotiation(self, family: str) -> dict | None:
        row = await self._pool.fetchrow(
            "SELECT rec FROM negotiations WHERE family = $1", family)
        return json.loads(row["rec"]) if row else None

    async def save_negotiation(self, rec: dict) -> None:
        await self._pool.execute(
            "UPDATE negotiations SET state = $2, decision = $3, rec = $4 "
            "WHERE family = $1",
            rec["family"], rec["state"], rec.get("decision"), json.dumps(rec))

    async def close_negotiation(self, family: str | None) -> None:
        if not family:
            return
        # Tickets cascade.
        await self._pool.execute("DELETE FROM negotiations WHERE family = $1",
                                 family)

    async def reap_expired(self) -> int:
        result = await self._pool.execute(
            "DELETE FROM negotiations WHERE expires < $1", time.time())
        # Opportunistic: the event feed is bounded by the same sweep rather
        # than by a second timer nobody would remember to run.
        await self._pool.execute(
            "DELETE FROM owner_events WHERE ts < now() - ($1 || ' seconds')::interval",
            str(EVENT_RETENTION_SECONDS))
        return int(result.rsplit(" ", 1)[-1] or 0)

    async def pending_negotiations(self) -> list[dict]:
        rows = await self._pool.fetch(
            "SELECT rec FROM negotiations "
            "WHERE state = 'awaiting-owner' AND decision IS NULL")
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
               AND state = 'awaiting-owner'
               AND decision IS NULL
            RETURNING family
            """,
            family, decision)
        return row is not None

    # --- RPTs ---------------------------------------------------------------

    async def record_rpt(self, jti: str, family: str, handle: str,
                         operation: dict | None) -> None:
        await self._pool.execute(
            "INSERT INTO rpts (jti, family, handle, operation, consumed) "
            "VALUES ($1, $2, $3, $4, false)",
            jti, family, handle,
            json.dumps(operation) if operation is not None else None)

    async def rpt(self, jti: str) -> dict | None:
        row = await self._pool.fetchrow(
            "SELECT jti, family, handle, operation, consumed FROM rpts "
            "WHERE jti = $1", jti)
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
            "WHERE jti = $1 AND consumed = false RETURNING family", jti)
        return row["family"] if row else None

    # --- standing relationships ---------------------------------------------

    async def connection(self, handle: str) -> dict | None:
        row = await self._pool.fetchrow(
            "SELECT conn FROM connections WHERE handle = $1", handle)
        return json.loads(row["conn"]) if row else None

    async def put_connection(self, conn: dict) -> None:
        await self._pool.execute(
            "INSERT INTO connections (handle, first_seen, conn) "
            "VALUES ($1, $2, $3) "
            "ON CONFLICT (handle) DO UPDATE SET conn = EXCLUDED.conn",
            conn["handle"], conn["first_seen"], json.dumps(conn))

    async def connections(self) -> list[dict]:
        rows = await self._pool.fetch(
            "SELECT conn FROM connections ORDER BY first_seen DESC")
        return [json.loads(r["conn"]) for r in rows]

    async def touch_connection(self, handle: str, when: str) -> None:
        await self._pool.execute(
            "UPDATE connections "
            "SET conn = jsonb_set(conn, '{last_access}', to_jsonb($2::text)) "
            "WHERE handle = $1", handle, when)

    async def note_tier_grant(self, handle: str, tier_id: str) -> None:
        # Append-if-absent in one statement, so two replicas granting at the
        # same tier concurrently cannot lose each other's write.
        await self._pool.execute(
            "UPDATE connections SET conn = jsonb_set("
            "  conn, '{tiers_granted}',"
            "  COALESCE(conn->'tiers_granted', '[]'::jsonb) || to_jsonb($2::text))"
            "WHERE handle = $1 AND NOT COALESCE(conn->'tiers_granted', '[]'::jsonb)"
            "                        @> to_jsonb($2::text)", handle, tier_id)

    async def note_tier_approval(self, handle: str, tier_id: str) -> None:
        await self._pool.execute(
            "UPDATE connections SET conn = jsonb_set("
            "  conn, '{tiers_approved}',"
            "  COALESCE(conn->'tiers_approved', '[]'::jsonb) || to_jsonb($2::text))"
            "WHERE handle = $1 AND NOT COALESCE(conn->'tiers_approved', '[]'::jsonb)"
            "                        @> to_jsonb($2::text)", handle, tier_id)

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
                    "WHERE handle = $1 RETURNING handle", handle)
                if row is None:
                    return None
                killed = await conn.fetch(
                    "UPDATE rpts SET consumed = true "
                    "WHERE handle = $1 AND consumed = false RETURNING jti",
                    handle)
                return len(killed)

    # --- operators she has shut out -------------------------------------------

    async def blocked_operators(self) -> dict[str, dict]:
        rows = await self._pool.fetch("SELECT origin, blocked FROM blocked_operators")
        return {r["origin"]: json.loads(r["blocked"]) for r in rows}

    async def block_operator(self, origin: str, when: str) -> None:
        await self._pool.execute(
            "INSERT INTO blocked_operators (origin, blocked) VALUES ($1, $2) "
            "ON CONFLICT (origin) DO NOTHING",
            origin, json.dumps({"origin": origin, "blocked_at": when}))

    async def unblock_operator(self, origin: str) -> bool:
        row = await self._pool.fetchrow(
            "DELETE FROM blocked_operators WHERE origin = $1 RETURNING origin", origin)
        return row is not None

    # --- resource servers ----------------------------------------------------

    async def resource_servers(self) -> dict[str, dict]:
        rows = await self._pool.fetch("SELECT client_id, rs FROM resource_servers")
        return {r["client_id"]: json.loads(r["rs"]) for r in rows}

    async def resource_server(self, client_id: str) -> dict | None:
        row = await self._pool.fetchrow(
            "SELECT rs FROM resource_servers WHERE client_id = $1", client_id)
        return json.loads(row["rs"]) if row else None

    async def touch_pat(self, client_id: str, when: str) -> None:
        await self._pool.execute(
            "UPDATE resource_servers "
            "SET rs = jsonb_set(rs, '{last_pat_issued}', to_jsonb($2::text)) "
            "WHERE client_id = $1", client_id, when)

    async def revoke_resource_server(self, client_id: str) -> bool:
        row = await self._pool.fetchrow(
            "UPDATE resource_servers "
            "SET rs = jsonb_set(rs, '{status}', '\"revoked\"') "
            "WHERE client_id = $1 RETURNING client_id", client_id)
        return row is not None

    # --- owner-visible documents ---------------------------------------------

    async def ledger_add(self, kind: str, family: str, ts: str,
                         entry: dict, handle: str | None = None) -> None:
        await self._pool.execute(
            "INSERT INTO ledger (kind, family, ts, entry, handle) "
            "VALUES ($1, $2, $3, $4, $5)",
            kind, family, ts, json.dumps(entry), handle)

    async def ledger(self, handle: str | None = None) -> list[dict]:
        if handle is None:
            rows = await self._pool.fetch(
                "SELECT kind, family, ts, entry, handle FROM ledger ORDER BY seq")
        else:
            rows = await self._pool.fetch(
                "SELECT kind, family, ts, entry, handle FROM ledger "
                "WHERE handle = $1 ORDER BY seq", handle)
        # Columns last, so an `entry` key can never shadow one of them.
        return [{**json.loads(r["entry"]), "kind": r["kind"],
                 "family": r["family"], "ts": r["ts"], "handle": r["handle"]}
                for r in rows]

    async def handle_for_family(self, family: str) -> str | None:
        return await self._pool.fetchval(
            "SELECT handle FROM rpts WHERE family = $1 AND handle IS NOT NULL "
            "ORDER BY jti LIMIT 1", family)

    async def trajectory(self, handle: str, since: str) -> dict:
        # One pass over the (handle, kind, ts) index. `ts` is fixed-width
        # UTC, so the lexicographic comparison is a time comparison.
        row = await self._pool.fetchrow(
            "SELECT count(*) FILTER (WHERE kind = 'denied') AS denials, "
            "       coalesce(array_agg(DISTINCT entry->>'tier') "
            "                FILTER (WHERE entry ? 'tier'), '{}') AS tiers "
            "  FROM ledger WHERE handle = $1 AND ts >= $2", handle, since)
        return {"denials": int(row["denials"] or 0),
                "tiers": list(row["tiers"] or [])}

    async def publish_terms(self, doc: dict) -> None:
        # DO NOTHING, not DO UPDATE: a published version's content never
        # changes. An owner edit produces a new template_id, and both remain
        # dereferenceable.
        await self._pool.execute(
            "INSERT INTO terms_docs (template_id, doc) VALUES ($1, $2) "
            "ON CONFLICT (template_id) DO NOTHING",
            doc["template_id"], json.dumps(doc))

    async def terms_doc(self, template_id: str) -> dict | None:
        row = await self._pool.fetchrow(
            "SELECT doc FROM terms_docs WHERE template_id = $1", template_id)
        return json.loads(row["doc"]) if row else None

    async def terms_docs(self) -> list[dict]:
        rows = await self._pool.fetch(
            "SELECT doc FROM terms_docs ORDER BY template_id")
        return [json.loads(r["doc"]) for r in rows]

    # --- Alice's policy -------------------------------------------------------

    async def tiers(self) -> dict[str, dict]:
        rows = await self._pool.fetch("SELECT tier_id, tier FROM tiers")
        return {r["tier_id"]: json.loads(r["tier"]) for r in rows}

    async def create_tier(self, tier_id: str, tier: dict) -> dict:
        # ON CONFLICT DO NOTHING, then check what came back: the uniqueness
        # test and the write are one statement, so two replicas cannot both
        # believe they created it.
        row = await self._pool.fetchrow(
            "INSERT INTO tiers (tier_id, tier) VALUES ($1, $2) "
            "ON CONFLICT (tier_id) DO NOTHING RETURNING tier_id",
            tier_id, json.dumps(tier))
        if row is None:
            raise KeyError(tier_id)
        return tier

    async def delete_tier(self, tier_id: str) -> bool:
        row = await self._pool.fetchrow(
            "DELETE FROM tiers WHERE tier_id = $1 RETURNING tier_id", tier_id)
        return row is not None

    async def update_tier(self, tier_id: str, patch: dict) -> dict:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # FOR UPDATE so two portals editing at once produce two
                # version bumps in order, not one lost edit. The version is
                # what ties a signed agreement to the terms in force when it
                # was signed, so losing a bump is losing an audit trail.
                row = await conn.fetchrow(
                    "SELECT tier FROM tiers WHERE tier_id = $1 FOR UPDATE",
                    tier_id)
                if row is None:
                    raise KeyError(tier_id)
                updated = policy.apply_patch(json.loads(row["tier"]), patch)
                await conn.execute(
                    "UPDATE tiers SET tier = $2 WHERE tier_id = $1",
                    tier_id, json.dumps(updated))
                return updated

    # --- fan-out ---------------------------------------------------------------

    async def notify(self, payload: dict) -> None:
        row = await self._pool.fetchrow(
            "INSERT INTO owner_events (payload) VALUES ($1) RETURNING id",
            json.dumps(payload))
        # Every replica's listener receives this, so it does not matter which
        # one holds Alice's stream.
        await self._pool.execute("SELECT pg_notify('owner_events', $1)",
                                 str(row["id"]))

    async def subscribe(self) -> AsyncIterator[dict]:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            if queue in self._subscribers:
                self._subscribers.remove(queue)
