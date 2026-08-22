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

-- Upgrading a database that predates multi-owner: the column is additive and
-- backfills to the owner the single-owner deployment served. The composite
-- primary keys above are not retrofitted, because changing a primary key is
-- not an idempotent statement and every replica applies this file at startup.
-- A database that needs the new keys is recreated, which is what `make
-- k8s-down && make k8s-up` does and what the lab assumes.
ALTER TABLE negotiations     ADD COLUMN IF NOT EXISTS owner text NOT NULL DEFAULT 'alice';
ALTER TABLE tickets          ADD COLUMN IF NOT EXISTS owner text NOT NULL DEFAULT 'alice';
ALTER TABLE rpts             ADD COLUMN IF NOT EXISTS owner text NOT NULL DEFAULT 'alice';
ALTER TABLE connections      ADD COLUMN IF NOT EXISTS owner text NOT NULL DEFAULT 'alice';
ALTER TABLE resource_servers ADD COLUMN IF NOT EXISTS owner text NOT NULL DEFAULT 'alice';
ALTER TABLE blocked_operators ADD COLUMN IF NOT EXISTS owner text NOT NULL DEFAULT 'alice';
ALTER TABLE owned_operators  ADD COLUMN IF NOT EXISTS owner text NOT NULL DEFAULT 'alice';
ALTER TABLE ledger           ADD COLUMN IF NOT EXISTS owner text NOT NULL DEFAULT 'alice';
ALTER TABLE terms_docs       ADD COLUMN IF NOT EXISTS owner text NOT NULL DEFAULT 'alice';
ALTER TABLE tiers            ADD COLUMN IF NOT EXISTS owner text NOT NULL DEFAULT 'alice';
ALTER TABLE owner_events     ADD COLUMN IF NOT EXISTS owner text NOT NULL DEFAULT 'alice';
