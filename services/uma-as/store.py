"""The authorization server's state, behind an interface.

Why this exists
---------------
Everything the grant loop remembers — negotiations, the tickets that index
them, issued RPTs, standing connections, the ledger, Alice's tiers — used to
be module-level dicts. That is correct for exactly one process, and this
service ran as exactly one process.

At more than one replica it stops being correct, and not gently:

* a ticket minted on replica A is unknown to replica B;
* `/consume` (the single-use burn) was check-then-act, safe only because a
  single asyncio loop never yields between the read and the write — two
  replicas make the trade replayable;
* revoking a resource server on one replica leaves the others honouring its
  PAT, which is a security regression rather than a demo glitch;
* Alice's SSE stream is attached to whichever replica answered, and would
  never see an approval that landed on another.

So the state moves behind this interface, with two implementations:

* ``store_memory`` — the default, and what ``docker compose`` gets. It
  reproduces the previous semantics exactly, including the deliberate ones
  described below. No database, no new container.
* ``store_postgres`` — one row per fact, used when the AS runs replicated.

The discipline: methods are *intents*, not accessors
----------------------------------------------------
The obvious interface is ``get(key)`` / ``put(key, value)``. It is the wrong
one: it preserves the check-then-act shape that made the single-use burn
racy, and simply moves the race across the network. Every method here that
guards a single-use resource performs its decision and its write as one
step, and reports whether the caller won:

    consume_ticket(ticket) -> record | None    # the ticket is spent by asking
    consume_rpt(jti)       -> family  | None    # None means you lost the race

A caller that gets ``None`` denies. That is the whole contract.

Two behaviours are required and easy to "fix" by accident
---------------------------------------------------------
1. ``consume_ticket`` removes only the *index* entry. The negotiation stays
   addressable by family, so the owner's portal can still see and decide a
   pending request in the window between one ticket being consumed and its
   rotation being issued. Keying negotiations by ticket instead makes the
   record invisible in that window and `/owner/pending/{family}/decision`
   404s on a negotiation that plainly exists.
2. The family is the stable identity; the ticket is a credential for it.
"""

from __future__ import annotations

import os
from typing import AsyncIterator, Protocol


class Store(Protocol):
    """The authorization server's state. See the module docstring for why the
    methods are intents rather than accessors."""

    # --- lifecycle ---------------------------------------------------------

    async def start(self) -> None:
        """Connect, create the schema if absent, and seed defaults. Idempotent:
        every replica calls it at startup and exactly one of them wins each
        seed."""

    async def close(self) -> None: ...

    # --- negotiations and tickets ------------------------------------------

    async def mint_ticket(self, rec: dict, ttl: float) -> str:
        """Persist the negotiation and index a fresh ticket to it.

        The record's ``expires`` is set from ``ttl`` here rather than by the
        caller, so the one place that decides a ticket's lifetime is the one
        place that writes it.
        """

    async def consume_ticket(self, ticket: str) -> dict | None:
        """Burn the presented ticket and return its negotiation, atomically.

        ``None`` means the ticket was unknown, already spent, or its
        negotiation has expired — all of which the caller answers the same
        way (``invalid_grant``).
        """

    async def negotiation(self, family: str) -> dict | None: ...

    async def save_negotiation(self, rec: dict) -> None:
        """Write back a record mutated in place, without minting a ticket."""

    async def close_negotiation(self, family: str | None) -> None:
        """Drop a finished negotiation and any ticket still indexed to it.

        Every path out of the grant loop is terminal except need_info and
        awaiting-owner, so without this the record set grows for the life of
        the deployment. The ledger, not this table, is the audit trail.
        """

    async def reap_expired(self) -> int:
        """Sweep negotiations whose ticket window closed with nobody
        returning."""

    async def pending_negotiations(self) -> list[dict]:
        """Every negotiation awaiting Alice, undecided — what her portal
        lists."""

    async def decide(self, family: str, decision: str) -> bool:
        """Record the owner's decision. False if there is no such negotiation
        awaiting her, so a double-tap or a stale portal cannot decide twice."""

    # --- RPTs: the atomicity everything else rests on ----------------------

    async def record_rpt(self, jti: str, family: str, handle: str,
                         operation: dict | None) -> None: ...

    async def rpt(self, jti: str) -> dict | None: ...

    async def consume_rpt(self, jti: str) -> str | None:
        """Burn a single-use RPT. Returns its family, or ``None`` if it was
        already spent — which is the caller's signal to deny.

        This is the method the whole interface exists for. UMA 2.0 says an
        RPT may be single-use; it does not say the burn must be atomic,
        because in 2018 the authorization server was assumed to be one
        process.
        """

    # --- standing relationships --------------------------------------------

    async def connection(self, handle: str) -> dict | None: ...

    async def put_connection(self, conn: dict) -> None: ...

    async def connections(self) -> list[dict]: ...

    async def touch_connection(self, handle: str, when: str) -> None:
        """Record last access. Best-effort telemetry: never fails a call."""

    async def note_tier_grant(self, handle: str, tier_id: str) -> None:
        """Remember that this connection has now been granted at this tier.

        Not telemetry: `standing.first_at_tier` is a policy input, so this is
        the write that stops the second request at a tier from asking her
        again. It appends rather than replacing, and a lost update under
        concurrency costs an extra ask rather than skipping one — the only
        direction a race here is allowed to fail in.
        """

    async def note_tier_approval(self, handle: str, tier_id: str) -> None:
        """Remember that the owner *personally approved* something at this
        tier — as distinct from this server having granted there.

        The two are separate because only this one may relax a rule. Relaxing
        on what the server granted would be circular: that grant may itself
        have been automatic, so one automatic grant would justify the next.
        """

    async def revoke_connection(self, handle: str) -> int | None:
        """Deactivate the connection and every live RPT issued under it, in
        one step. Returns how many tokens were killed, or ``None`` if the
        connection is unknown. Also bumps the revocation count, which survives
        a later re-connection: `standing.never_revoked` is worth nothing if
        an agent can clear its record by asking again.

        One step because the two halves are the same decision: a revocation
        that flipped the connection and then failed to burn the tokens would
        leave the agent holding exactly the authority Alice just withdrew.
        """

    # --- operators she has shut out -----------------------------------------

    async def blocked_operators(self) -> dict[str, dict]:
        """Origins whose agents she will not deal with, and when she said so."""

    async def block_operator(self, origin: str, when: str) -> None:
        """Shut out an operator. Idempotent — blocking twice is not an error,
        because her portal and her personal AI may both be looking at a stale
        list."""

    async def unblock_operator(self, origin: str) -> bool: ...

    # --- resource servers (the other standing relationship) -----------------

    async def resource_servers(self) -> dict[str, dict]: ...

    async def resource_server(self, client_id: str) -> dict | None: ...

    async def touch_pat(self, client_id: str, when: str) -> None: ...

    async def revoke_resource_server(self, client_id: str) -> bool: ...

    # --- owner-visible documents -------------------------------------------

    async def ledger_add(self, kind: str, family: str, ts: str,
                         entry: dict, handle: str | None = None) -> None:
        """Append one decision record.

        ``handle`` is a column rather than a key in ``entry`` because both
        implementations flatten ``entry`` into the returned row: a key of the
        same name would silently shadow the column, and the caller would never
        find out. One writer, one place.

        It is ``None`` for the entries that genuinely have no counterparty —
        a resource-server revocation, and a decline at beat 2, which happens
        before the requesting side has signed anything and so has no key to
        attribute."""

    async def ledger(self, handle: str | None = None) -> list[dict]:
        """The whole record, or one agent's part of it, oldest first."""

    async def handle_for_family(self, family: str) -> str | None:
        """Which agent a negotiation belonged to, after the negotiation
        itself is gone.

        ``close_negotiation`` drops the record as soon as the grant is issued,
        so by the time the enforcement point reports an allowed call the only
        surviving link is the grant it was issued under. Reading it here keeps
        attribution on the owner's side: the enforcement point never needs to
        be told the handle, and it enforces for an authority it cannot read."""

    async def trajectory(self, handle: str, since: str) -> dict:
        """What this agent has been doing lately: ``{"denials": int,
        "tiers": [str]}`` over the entries at or after ``since``.

        Deliberately *not* one of the indivisible operations above. Those are
        indivisible because a wrong answer is an access-control failure; this
        one only ever tightens a requirement, so a replica reading one write
        stale behaves exactly as if the request had arrived a moment earlier —
        an ordering the system already permits. The question that separates
        the two classes: can a stale read widen access beyond what a
        differently-timed arrival would have? Here it cannot."""

    async def publish_terms(self, doc: dict) -> None:
        """Archive a terms version. Idempotent per template_id — a published
        version's content never changes, which is what makes a signed
        agreement verifiable against it years later."""

    async def terms_doc(self, template_id: str) -> dict | None: ...

    async def terms_docs(self) -> list[dict]: ...

    # --- Alice's policy -----------------------------------------------------

    async def tiers(self) -> dict[str, dict]: ...

    async def update_tier(self, tier_id: str, patch: dict) -> dict:
        """Apply an owner edit and bump the template version atomically.
        Raises ``KeyError`` for an unknown tier."""

    async def create_tier(self, tier_id: str, tier: dict) -> dict:
        """Add a tier Alice wrote. Raises ``KeyError`` if the id is taken —
        checked in the same step as the write, so two replicas cannot both
        believe they created it."""

    async def delete_tier(self, tier_id: str) -> bool:
        """Remove a tier. False if it was not there.

        Its resources become ungoverned, and an ungoverned resource is denied
        rather than defaulted — deleting a tier withdraws access rather than
        widening it, which is the only safe direction for a destructive edit.
        """

    # --- fan-out to the owner's surface -------------------------------------

    async def notify(self, payload: dict) -> None:
        """Publish an event to every replica's subscribers."""

    def subscribe(self) -> AsyncIterator[dict]:
        """One owner's SSE stream. Yields every event published by any
        replica, so it does not matter which one the portal reached."""


def default_resource_servers() -> dict[str, dict]:
    """Resource servers Alice has authorized to use her Protection API.

    The PAT is an OAuth token this AS issues to these clients
    (client_credentials, scope uma_protection); the day-0 consent for her
    brokerage's gateway is seeded — the RS-side onboarding handshake is a
    finding, not a feature here.

    Seeded into the store rather than held in a module dict because
    ``status`` is a live security control: ``require_pat`` reads it on every
    Protection API call, and the owner flips it from her portal. A revocation
    that only reached the replica that served the request would leave the
    others honouring a PAT Alice had just withdrawn.
    """
    return {
        os.environ.get("UMA_AS_RS_CLIENT_ID", "meridian-gateway"): {
            "secret": os.environ.get("UMA_AS_RS_CLIENT_SECRET",
                                     "gateway-dev-secret"),
            "name": "Meridian Wealth API gateway",
            "status": "active",
            "consented": "seeded at provisioning (Alice linked her brokerage)",
            "last_pat_issued": None,
            # Where the RS publishes itself — the root of declarative
            # registration (RFC 9728 metadata is derived from this identifier).
            "resource_uri": os.environ.get(
                "UMA_AS_RS_RESOURCE_URI", "https://gateway.uma.lab/mcp"),
        }
    }


def make_store() -> Store:
    """Pick the backend. ``memory`` is the default: the compose stack gains no
    database, and the two shapes run the same image."""
    kind = os.environ.get("UMA_AS_STORE", "memory").lower()
    if kind == "memory":
        from store_memory import MemoryStore

        return MemoryStore()
    if kind == "postgres":
        # Imported lazily so the memory path never needs the driver present.
        from store_postgres import PostgresStore

        return PostgresStore(os.environ["UMA_AS_DATABASE_URL"])
    raise ValueError(f"UMA_AS_STORE must be memory|postgres, got {kind!r}")
