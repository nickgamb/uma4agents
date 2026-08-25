"""In-process store — the default, and what the compose stack runs.

This is the behaviour the service has always had, moved behind the interface
without changing it. It is correct for exactly one replica and makes no
attempt to be correct for more; the atomicity the interface promises is
provided here by the single event loop, which is why every method that
guards a single-use resource does its check and its write without an
``await`` in between.

That constraint is not optional. Adding an ``await`` inside
``consume_ticket`` or ``consume_rpt`` would reintroduce exactly the race the
interface exists to remove — under one loop it would be a real bug, not a
theoretical one.
"""

from __future__ import annotations

import asyncio
import copy
import time
from typing import AsyncIterator

import policy
import store


class MemoryOwnerStore:
    """One owner's state, in one process.

    This is the class the service always had. It did not need changing to
    become per-owner, because it always was per-owner — the deployment simply
    only ever ran one. That is the clearest evidence for the claim in
    store.py: a personal authorization server is not a different design, it
    is this object with nobody else in the process.
    """

    def __init__(self) -> None:
        self._negotiations: dict[str, dict] = {}   # family -> record
        self._tickets: dict[str, str] = {}         # rotating ticket -> family
        self._rpts: dict[str, dict] = {}           # jti -> {consumed, ...}
        self._ledger: list[dict] = []
        self._connections: dict[str, dict] = {}
        self._blocked_operators: dict[str, dict] = {}
        self._owned_operators: dict[str, dict] = {}
        self._terms: dict[str, dict] = {}
        self._tiers: dict[str, dict] = {}
        self._rs: dict[str, dict] = {}
        self._organization: dict | None = None
        self._mandates: dict[str, dict] = {}
        self._subscribers: list[asyncio.Queue] = []

    # --- lifecycle ---------------------------------------------------------

    def __set_owner(self, owner: str) -> None:
        self._owner = owner

    async def seed(self) -> None:
        """Starting policy for an owner who has none. Idempotent."""
        if not self._tiers:
            self._tiers = policy.defaults(getattr(self, "_owner", "alice"))
        if not self._rs:
            self._rs = store.default_resource_servers(
                getattr(self, "_owner", "alice"))

    # --- negotiations and tickets ------------------------------------------

    async def mint_ticket(self, rec: dict, ttl: float) -> str:
        import secrets

        ticket = f"tkt_{secrets.token_urlsafe(24)}"
        rec["expires"] = time.time() + ttl
        self._negotiations[rec["family"]] = rec
        self._tickets[ticket] = rec["family"]
        return ticket

    async def consume_ticket(self, ticket: str) -> dict | None:
        # Only the index entry is removed — the negotiation remains
        # addressable by family so the owner's portal can see and decide a
        # pending request even in the window between one ticket being
        # consumed and its rotation being issued.
        family = self._tickets.pop(ticket or "", None)
        if family is None:
            return None
        rec = self._negotiations.get(family)
        if not rec or rec["expires"] < time.time():
            return None
        return rec

    async def negotiation(self, family: str) -> dict | None:
        return self._negotiations.get(family)

    async def save_negotiation(self, rec: dict) -> None:
        # The caller mutated the very object this dict holds; nothing to do.
        self._negotiations[rec["family"]] = rec

    async def close_negotiation(self, family: str | None) -> None:
        if not family:
            return
        self._negotiations.pop(family, None)
        for t in [t for t, f in self._tickets.items() if f == family]:
            self._tickets.pop(t, None)

    async def reap_expired(self) -> int:
        cutoff = time.time()
        stale = [f for f, r in self._negotiations.items() if r["expires"] < cutoff]
        for family in stale:
            await self.close_negotiation(family)
        return len(stale)

    async def pending_negotiations(self) -> list[dict]:
        return [copy.deepcopy(r) for r in self._negotiations.values()
                if r["state"] == "awaiting-owner" and r.get("decision") is None]

    async def decide(self, family: str, decision: str) -> bool:
        rec = self._negotiations.get(family)
        if rec is None or rec["state"] != "awaiting-owner":
            return False
        if rec.get("decision") is not None:
            return False
        rec["decision"] = decision
        return True

    # --- RPTs ---------------------------------------------------------------

    async def record_rpt(self, jti: str, family: str, handle: str,
                         operation: dict | None, tier: str | None = None) -> None:
        self._rpts[jti] = {"jti": jti, "consumed": False, "family": family,
                           "operation": operation, "handle": handle,
                           "tier": tier}

    async def rpt(self, jti: str) -> dict | None:
        rec = self._rpts.get(jti)
        return dict(rec) if rec is not None else None

    async def consume_rpt(self, jti: str) -> str | None:
        # Check and write with no await between them: under one event loop
        # that is the atomic step the interface promises.
        rec = self._rpts.get(jti)
        if rec is None or rec["consumed"]:
            return None
        rec["consumed"] = True
        return rec["family"]

    # --- standing relationships ---------------------------------------------

    async def connection(self, handle: str) -> dict | None:
        conn = self._connections.get(handle)
        return dict(conn) if conn is not None else None

    async def put_connection(self, conn: dict) -> None:
        self._connections[conn["handle"]] = dict(conn)

    async def connections(self) -> list[dict]:
        return sorted((dict(c) for c in self._connections.values()),
                      key=lambda c: c["first_seen"], reverse=True)

    async def touch_connection(self, handle: str, when: str) -> None:
        if (conn := self._connections.get(handle)) is not None:
            conn["last_access"] = when

    async def note_tier_grant(self, handle: str, tier_id: str) -> None:
        if (conn := self._connections.get(handle)) is not None:
            if tier_id not in conn.setdefault("tiers_granted", []):
                conn["tiers_granted"].append(tier_id)

    async def note_tier_approval(self, handle: str, tier_id: str) -> None:
        if (conn := self._connections.get(handle)) is not None:
            if tier_id not in conn.setdefault("tiers_approved", []):
                conn["tiers_approved"].append(tier_id)

    async def revoke_connection(self, handle: str) -> int | None:
        conn = self._connections.get(handle)
        if conn is None:
            return None
        conn["status"] = "revoked"
        conn["revocations"] = int(conn.get("revocations", 0)) + 1
        killed = 0
        for rec in self._rpts.values():
            if rec.get("handle") == handle and not rec["consumed"]:
                rec["consumed"] = True
                killed += 1
        return killed

    async def blocked_operators(self) -> dict[str, dict]:
        return {k: dict(v) for k, v in self._blocked_operators.items()}

    async def block_operator(self, origin: str, when: str) -> None:
        self._blocked_operators.setdefault(origin, {"origin": origin,
                                                    "blocked_at": when})

    async def unblock_operator(self, origin: str) -> bool:
        return self._blocked_operators.pop(origin, None) is not None

    # --- operators she says are her own --------------------------------------

    async def owned_operators(self) -> dict[str, dict]:
        return {k: dict(v) for k, v in self._owned_operators.items()}

    async def claim_operator(self, origin: str, when: str) -> None:
        self._owned_operators.setdefault(origin, {"origin": origin,
                                                  "claimed_at": when})

    async def disclaim_operator(self, origin: str) -> bool:
        return self._owned_operators.pop(origin, None) is not None

    # --- resource servers ----------------------------------------------------

    async def resource_servers(self) -> dict[str, dict]:
        return {cid: dict(rs) for cid, rs in self._rs.items()}

    async def resource_server(self, client_id: str) -> dict | None:
        rs = self._rs.get(client_id)
        return dict(rs) if rs is not None else None

    async def put_resource_server(self, client_id: str, rs: dict) -> None:
        self._rs[client_id] = copy.deepcopy(rs)

    async def approve_resource_server(self, client_id: str, when: str) -> bool:
        rs = self._rs.get(client_id)
        if rs is None or rs.get("status") != "pending":
            return False
        rs["status"] = "active"
        rs["consented"] = when
        return True

    async def touch_pat(self, client_id: str, when: str) -> None:
        if (rs := self._rs.get(client_id)) is not None:
            rs["last_pat_issued"] = when

    async def revoke_resource_server(self, client_id: str) -> bool:
        rs = self._rs.get(client_id)
        if rs is None:
            return False
        rs["status"] = "revoked"
        return True

    # --- owner-visible documents ---------------------------------------------

    async def ledger_add(self, kind: str, family: str, ts: str,
                         entry: dict, handle: str | None = None) -> None:
        # Columns last, so an `entry` key can never shadow one of them.
        self._ledger.append({**entry, "kind": kind, "family": family,
                             "ts": ts, "handle": handle})

    async def ledger(self, handle: str | None = None) -> list[dict]:
        rows = self._ledger if handle is None else [
            r for r in self._ledger if r.get("handle") == handle]
        return [dict(r) for r in rows]

    async def grant_for_family(self, family: str) -> dict | None:
        for rec in self._rpts.values():
            if rec["family"] == family and rec.get("handle"):
                return {"handle": rec["handle"], "tier": rec.get("tier")}
        return None

    async def trajectory(self, handle: str, since: str) -> dict:
        denials, calls, tiers = 0, 0, []
        for row in self._ledger:
            if row.get("handle") != handle or row["ts"] < since:
                continue
            if row["kind"] == "denied":
                denials += 1
            if row["kind"] == "touched":
                calls += 1
            if (tier := row.get("tier")) and tier not in tiers:
                tiers.append(tier)
        return {"denials": denials, "tiers": sorted(tiers), "calls": calls}

    async def publish_terms(self, doc: dict) -> None:
        self._terms.setdefault(doc["template_id"], dict(doc))

    async def terms_doc(self, template_id: str) -> dict | None:
        doc = self._terms.get(template_id)
        return dict(doc) if doc is not None else None

    async def terms_docs(self) -> list[dict]:
        return sorted((dict(d) for d in self._terms.values()),
                      key=lambda d: d["template_id"])

    # --- Alice's policy -------------------------------------------------------

    async def tiers(self) -> dict[str, dict]:
        return copy.deepcopy(self._tiers)

    async def create_tier(self, tier_id: str, tier: dict) -> dict:
        if tier_id in self._tiers:
            raise KeyError(tier_id)
        self._tiers[tier_id] = copy.deepcopy(tier)
        return copy.deepcopy(tier)

    async def delete_tier(self, tier_id: str) -> bool:
        return self._tiers.pop(tier_id, None) is not None

    async def update_tier(self, tier_id: str, patch: dict) -> dict:
        if tier_id not in self._tiers:
            raise KeyError(tier_id)
        updated = policy.apply_patch(self._tiers[tier_id], patch)
        self._tiers[tier_id] = updated
        return copy.deepcopy(updated)

    # --- resources held jointly -----------------------------------------------

    async def mandates(self) -> dict[str, dict]:
        return copy.deepcopy(self._mandates)

    async def mandate(self, account: str) -> dict | None:
        rec = self._mandates.get(account)
        return copy.deepcopy(rec) if rec else None

    async def set_mandate(self, account: str, record: dict) -> None:
        self._mandates[account] = copy.deepcopy(record)

    async def clear_mandate(self, account: str) -> bool:
        return self._mandates.pop(account, None) is not None

    # --- the organization above her -------------------------------------------

    async def organization(self) -> dict | None:
        return copy.deepcopy(self._organization) if self._organization else None

    async def set_organization(self, record: dict) -> None:
        self._organization = copy.deepcopy(record)

    async def clear_organization(self) -> bool:
        had = self._organization is not None
        self._organization = None
        return had

    # --- fan-out ---------------------------------------------------------------
    #
    # Per owner, which is not a detail: a subscriber list shared across owners
    # would put Carol's pending requests on Alice's event stream.

    async def notify(self, payload: dict) -> None:
        for q in list(self._subscribers):
            await q.put(payload)

    async def subscribe(self) -> AsyncIterator[dict]:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            if queue in self._subscribers:
                self._subscribers.remove(queue)


class MemoryStore:
    """Many owners, one process. A dict of the class above and nothing else —
    there is deliberately no shared state for a query to leak across."""

    def __init__(self) -> None:
        self._owners: dict[str, MemoryOwnerStore] = {}

    async def start(self) -> None:
        return None

    async def close(self) -> None:
        return None

    def owner(self, owner: str) -> MemoryOwnerStore:
        st = self._owners.get(owner)
        if st is None:
            st = self._owners[owner] = MemoryOwnerStore()
            st._owner = owner
        return st

    async def owners(self) -> list[str]:
        return sorted(self._owners)
