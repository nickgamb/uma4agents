-- uma-as state, for the replicated deployment. See store.py for why.
--
-- Applied idempotently by every replica at startup; whichever gets there
-- first wins and the rest are no-ops.
--
-- The shape follows the interface, not the other way round: one table per
-- kind of fact the authorization server remembers, and the two single-use
-- guarantees (a ticket is spent once, a per-operation RPT is burned once)
-- each expressed as a single statement rather than a read followed by a
-- write. Those two statements are the reason this file exists.

CREATE TABLE IF NOT EXISTS negotiations (
    family   text PRIMARY KEY,
    expires  double precision NOT NULL,
    state    text NOT NULL,
    decision text,
    rec      jsonb NOT NULL
);

-- The portal's "what is waiting for me" query, and the reaper's sweep.
CREATE INDEX IF NOT EXISTS negotiations_awaiting
    ON negotiations (state) WHERE decision IS NULL;
CREATE INDEX IF NOT EXISTS negotiations_expires ON negotiations (expires);

-- Tickets are an *index into* negotiations, not the negotiations themselves.
-- ON DELETE CASCADE is what makes closing a negotiation one statement, and
-- what guarantees no ticket can outlive the thing it names.
CREATE TABLE IF NOT EXISTS tickets (
    ticket text PRIMARY KEY,
    family text NOT NULL REFERENCES negotiations(family) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS tickets_family ON tickets (family);

CREATE TABLE IF NOT EXISTS rpts (
    jti       text PRIMARY KEY,
    family    text NOT NULL,
    handle    text,
    operation jsonb,
    consumed  boolean NOT NULL DEFAULT false
);

-- Revoking a connection burns every token issued under it; this is the index
-- that makes that one statement rather than a scan.
CREATE INDEX IF NOT EXISTS rpts_live_by_handle
    ON rpts (handle) WHERE NOT consumed;

CREATE TABLE IF NOT EXISTS connections (
    handle     text PRIMARY KEY,
    first_seen text NOT NULL,
    conn       jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS resource_servers (
    client_id text PRIMARY KEY,
    rs        jsonb NOT NULL
);

-- Operators Alice has shut out. Keyed by origin rather than by the full
-- client_id URL, because an operator that publishes two metadata documents is
-- still one party -- and because the origin is what the key-directory check is
-- already required to match.
CREATE TABLE IF NOT EXISTS blocked_operators (
    origin  text PRIMARY KEY,
    blocked jsonb NOT NULL
);

-- Append-only. This is the audit trail, so nothing here is ever updated or
-- deleted -- including refusals and denials, which are decisions too.
CREATE TABLE IF NOT EXISTS ledger (
    seq    bigserial PRIMARY KEY,
    kind   text NOT NULL,
    family text NOT NULL,
    ts     text NOT NULL,
    entry  jsonb NOT NULL
);

-- Added after the ledger already existed, so it has to be an ALTER rather
-- than a column in the CREATE above -- and idempotent, because every replica
-- applies this file at startup and they race. The index is composite because
-- the only two queries are "one agent's rows" and "one agent's rows since a
-- timestamp"; `ts` is fixed-width UTC, so comparing it as text is comparing
-- it as time.
ALTER TABLE ledger ADD COLUMN IF NOT EXISTS handle text;
ALTER TABLE rpts ADD COLUMN IF NOT EXISTS tier text;
CREATE INDEX IF NOT EXISTS ledger_by_handle
    ON ledger (handle, kind, ts) WHERE handle IS NOT NULL;

-- An allowed call is reported by the enforcement point after the negotiation
-- has been closed, so the grant it was issued under is the only surviving
-- link back to the agent. The enforcement point is never told the handle.
CREATE INDEX IF NOT EXISTS rpts_by_family ON rpts (family);

-- Every version of every proffered terms document, dereferenceable for the
-- life of the AS. A published version's content never changes: that is what
-- lets an agreement signed last year still be checked against the terms that
-- were in force when it was signed.
CREATE TABLE IF NOT EXISTS terms_docs (
    template_id text PRIMARY KEY,
    doc         jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS tiers (
    tier_id text PRIMARY KEY,
    tier    jsonb NOT NULL
);

-- The owner's event feed. Rows exist so NOTIFY can carry an id instead of a
-- payload: Postgres caps NOTIFY payloads at 8000 bytes and a pending event
-- carries the purpose, the prohibitions and the agent's identity. Every
-- replica re-reads the row, which is also what makes a replica that
-- reconnects after a blip correct rather than merely lucky.
CREATE TABLE IF NOT EXISTS owner_events (
    id      bigserial PRIMARY KEY,
    ts      timestamptz NOT NULL DEFAULT now(),
    payload jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS owner_events_ts ON owner_events (ts);
