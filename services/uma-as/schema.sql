-- uma-as state, for the replicated deployment. See store.py for why.
--
-- Every table is partitioned by `owner`, and no query in store_postgres.py
-- spans owners. That is a deliberate constraint rather than a convenience:
-- if one person's rows are always a clean cut, moving her authority onto
-- something she runs — an isolate at the edge, a box under her desk — is a
-- data move rather than a rewrite. The composite primary keys are what make
-- that true; a bare `handle` or `tier_id` would collide the moment a second
-- owner existed.
--
-- Applied idempotently by every replica at startup; whichever gets there
-- first wins and the rest are no-ops.
--
-- The shape follows the interface, not the other way round: one table per
-- kind of fact the authorization server remembers, and the two single-use
-- guarantees (a ticket is spent once, a per-operation RPT is burned once)
-- each expressed as a single statement rather than a read followed by a
-- write. Those two statements are the reason this file exists.

-- Upgrading a database that predates multi-owner. This runs first, and has to.
--
-- The owner column is additive and backfills to the owner a single-owner
-- deployment served. It is at the top of the file because everything below
-- names the column: an index over `(owner, ...)`, and a foreign key from
-- tickets into `negotiations(owner, family)`. Any of those reached before the
-- column exists fails on that statement, and the connect-retry loop in
-- store_postgres.py then reports a perfectly reachable database as
-- unreachable, thirty times, naming the wrong cause.
--
-- `IF EXISTS` is what lets it run first: on a fresh database none of these
-- tables exist yet and every statement is a no-op, and the CREATE TABLEs
-- below then build the current shape directly.
--
-- What this does *not* do is rebuild the composite primary keys. Rebuilding a
-- primary key is not something to do from a file every replica executes at
-- startup, so a database that needs the new keys is recreated instead. That
-- is a real limitation rather than a hidden one:
-- PostgresStore._assert_owner_keys checks for it at startup and refuses with
-- an error that says so, because the alternative is an upsert failing later
-- with a 42P10 that names an ON CONFLICT clause and no cause.
ALTER TABLE IF EXISTS negotiations     ADD COLUMN IF NOT EXISTS owner text NOT NULL DEFAULT 'alice';
ALTER TABLE IF EXISTS tickets          ADD COLUMN IF NOT EXISTS owner text NOT NULL DEFAULT 'alice';
ALTER TABLE IF EXISTS rpts             ADD COLUMN IF NOT EXISTS owner text NOT NULL DEFAULT 'alice';
ALTER TABLE IF EXISTS connections      ADD COLUMN IF NOT EXISTS owner text NOT NULL DEFAULT 'alice';
ALTER TABLE IF EXISTS resource_servers ADD COLUMN IF NOT EXISTS owner text NOT NULL DEFAULT 'alice';
ALTER TABLE IF EXISTS blocked_operators ADD COLUMN IF NOT EXISTS owner text NOT NULL DEFAULT 'alice';
ALTER TABLE IF EXISTS owned_operators  ADD COLUMN IF NOT EXISTS owner text NOT NULL DEFAULT 'alice';
ALTER TABLE IF EXISTS ledger           ADD COLUMN IF NOT EXISTS owner text NOT NULL DEFAULT 'alice';
ALTER TABLE IF EXISTS terms_docs       ADD COLUMN IF NOT EXISTS owner text NOT NULL DEFAULT 'alice';
ALTER TABLE IF EXISTS tiers            ADD COLUMN IF NOT EXISTS owner text NOT NULL DEFAULT 'alice';
ALTER TABLE IF EXISTS owner_events     ADD COLUMN IF NOT EXISTS owner text NOT NULL DEFAULT 'alice';

CREATE TABLE IF NOT EXISTS negotiations (
    owner    text NOT NULL,
    family   text NOT NULL,
    expires  double precision NOT NULL,
    state    text NOT NULL,
    decision text,
    rec      jsonb NOT NULL,
    PRIMARY KEY (owner, family)
);

-- The portal's "what is waiting for me" query, and the reaper's sweep.
CREATE INDEX IF NOT EXISTS negotiations_awaiting
    ON negotiations (owner, state) WHERE decision IS NULL;
CREATE INDEX IF NOT EXISTS negotiations_expires ON negotiations (owner, expires);

-- Tickets are an *index into* negotiations, not the negotiations themselves.
-- ON DELETE CASCADE is what makes closing a negotiation one statement, and
-- what guarantees no ticket can outlive the thing it names.
CREATE TABLE IF NOT EXISTS tickets (
    owner  text NOT NULL,
    ticket text NOT NULL,
    family text NOT NULL,
    PRIMARY KEY (owner, ticket),
    FOREIGN KEY (owner, family)
        REFERENCES negotiations(owner, family) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS tickets_family ON tickets (owner, family);

CREATE TABLE IF NOT EXISTS rpts (
    owner     text NOT NULL,
    jti       text NOT NULL,
    family    text NOT NULL,
    handle    text,
    operation jsonb,
    consumed  boolean NOT NULL DEFAULT false,
    PRIMARY KEY (owner, jti)
);

-- Revoking a connection burns every token issued under it; this is the index
-- that makes that one statement rather than a scan.
CREATE INDEX IF NOT EXISTS rpts_live_by_handle
    ON rpts (owner, handle) WHERE NOT consumed;

CREATE TABLE IF NOT EXISTS connections (
    owner      text NOT NULL,
    handle     text NOT NULL,
    first_seen text NOT NULL,
    conn       jsonb NOT NULL,
    PRIMARY KEY (owner, handle)
);

CREATE TABLE IF NOT EXISTS resource_servers (
    owner     text NOT NULL,
    client_id text NOT NULL,
    rs        jsonb NOT NULL,
    PRIMARY KEY (owner, client_id)
);

-- Operators Alice has shut out. Keyed by origin rather than by the full
-- client_id URL, because an operator that publishes two metadata documents is
-- still one party -- and because the origin is what the key-directory check is
-- already required to match.
CREATE TABLE IF NOT EXISTS blocked_operators (
    owner   text NOT NULL,
    origin  text NOT NULL,
    blocked jsonb NOT NULL,
    PRIMARY KEY (owner, origin)
);

-- Origins Alice says are hers. The mirror of blocked_operators, and the
-- asymmetry between the two is the whole reason they are separate tables:
-- blocking is a restriction and may rest on what an agent claims about
-- itself, so a liar only lies into a refusal. Claiming is a relaxation, so it
-- may not -- an agent is first-party only when this origin is here AND the
-- operator published that agent's key where her authority could check.
CREATE TABLE IF NOT EXISTS owned_operators (
    owner  text NOT NULL,
    origin text NOT NULL,
    owned  jsonb NOT NULL,
    PRIMARY KEY (owner, origin)
);

-- Append-only. This is the audit trail, so nothing here is ever updated or
-- deleted -- including refusals and denials, which are decisions too.
CREATE TABLE IF NOT EXISTS ledger (
    seq    bigserial PRIMARY KEY,
    owner  text NOT NULL,
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
    ON ledger (owner, handle, kind, ts) WHERE handle IS NOT NULL;

-- An allowed call is reported by the enforcement point after the negotiation
-- has been closed, so the grant it was issued under is the only surviving
-- link back to the agent. The enforcement point is never told the handle.
CREATE INDEX IF NOT EXISTS rpts_by_family ON rpts (owner, family);

-- Every version of every proffered terms document, dereferenceable for the
-- life of the AS. A published version's content never changes: that is what
-- lets an agreement signed last year still be checked against the terms that
-- were in force when it was signed.
CREATE TABLE IF NOT EXISTS terms_docs (
    owner       text NOT NULL,
    template_id text NOT NULL,
    doc         jsonb NOT NULL,
    PRIMARY KEY (owner, template_id)
);

CREATE TABLE IF NOT EXISTS tiers (
    owner   text NOT NULL,
    tier_id text NOT NULL,
    tier    jsonb NOT NULL,
    PRIMARY KEY (owner, tier_id)
);

-- The organization she administers resources for, if any. One row per owner
-- rather than a join table: see the note on OwnerStore.organization for why
-- two at once is a different feature and not a wider column.
CREATE TABLE IF NOT EXISTS organizations (
    owner  text PRIMARY KEY,
    record jsonb NOT NULL
);

-- Resources she holds jointly with other people. Keyed by account, unlike
-- `organizations` above: two mandates are two resources with two different
-- sets of co-owners and they never meet, which is exactly what is not true
-- of two organizations over one terms document.
CREATE TABLE IF NOT EXISTS mandates (
    owner   text NOT NULL,
    account text NOT NULL,
    record  jsonb NOT NULL,
    PRIMARY KEY (owner, account)
);

-- The owner's event feed. Rows exist so NOTIFY can carry an id instead of a
-- payload: Postgres caps NOTIFY payloads at 8000 bytes and a pending event
-- carries the purpose, the prohibitions and the agent's identity. Every
-- replica re-reads the row, which is also what makes a replica that
-- reconnects after a blip correct rather than merely lucky.
CREATE TABLE IF NOT EXISTS owner_events (
    id      bigserial PRIMARY KEY,
    owner   text NOT NULL,
    ts      timestamptz NOT NULL DEFAULT now(),
    payload jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS owner_events_ts ON owner_events (owner, ts);
