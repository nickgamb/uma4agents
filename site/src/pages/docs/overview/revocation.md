---
templateKey: doc
title: Revocation and the ledger
description: What was promised, what was approved, what was touched — and what happens the moment the owner changes her mind.
diagram: revoke-cascade
diagramCaption: Ending the relationship and burning the grants behind it are one operation, not two.
next:
  - title: How it compares to UMA 2.0
    to: /docs/overview/compare-uma/
    blurb: What this profile keeps and what it changes.
  - title: Events
    to: /docs/reference/events/
    blurb: The event stream the ledger projects over.
---

Consent that cannot be withdrawn is not consent, and an approval nobody can
reconstruct afterwards is not much of a record. Those two requirements produce
the same machinery.

## One event stream

Every step of a negotiation emits a structured event: the challenge, the terms
dictated, the contract committed, the owner notified, her decision, the grant
issued, the call allowed or denied, the connection revoked.

Every event carries the same **correlation id** — the negotiation family,
assigned when the ticket is created and stable across every rotation of it. One
negotiation, one thread, however many messages it took.

## The ledger is a projection

The ledger is not a separate store. It is a view over that stream:

- **promised** — the contracts committed, with the hash of the terms signed
- **approved / denied** — the owner's own decisions
- **touched** — the calls actually allowed
- **revoked** — connections ended

Keeping it a projection rather than a table means the audit trail cannot
disagree with what happened. There is no second write to forget.

Refusals are recorded too. A denial is a decision, and a log that only contains
successes cannot answer the question anyone actually asks after an incident.

## Revocation has to be atomic

Revoking a connection does two things: it ends the relationship, and it burns
every live grant issued under it.

Doing those as two steps is a bug, and it was one here. The connection flipped,
and the grants were burned in a second operation that could fail independently —
leaving the agent holding exactly the authority the owner had just withdrawn,
with the interface telling her it was gone.

The fix is the same lesson as
[single-use](/docs/overview/single-use/): one operation that decides and records
together. Revocation ends the connection and burns its grants indivisibly, or it
does neither.

![Two connected agents in the lab's portal, listed by key thumbprint with when
they first connected and when they were last active. One is active with a Revoke
button; the other is already revoked.](/img/docs/owner-connections.png)

What she is revoking is the **relationship**, not a token. The agent above is
named by the thumbprint of its key, because a pseudonymous agent *is* its key —
and the row stays after revocation, because the fact that she once connected to
it is part of the record.

## Revoking an operator, not an agent

Revoking is per agent, and one at a time is not an answer to a flood.

So the same action exists a level up: block the **operator** an agent names, and
every agent it runs is shut out at once, with whatever is already connected
revoked in the same step. A block that stopped new requests and left live grants
alone would leave her believing she had closed a door that was still open — the
same indivisibility the section above is about.

This is what makes the [attention lanes](/docs/overview/attention/) worth having.
Their job is to ensure a flood large enough to matter arrives attributable, and
an attributable flood is one she can end here in a single action.

Blocking is a restriction, so it can rest on what the agent *claims* about
itself with none of the usual care: an agent that lies about its operator only
ever lies itself into a refusal.

Two limits, stated rather than glossed:

- **It does not remove anyone from the internet.** Drop the client identifier
  and the same party returns as an anonymous stranger — no accountability, the
  small lane, pending in front of her like anyone else.
- **Unblocking is not the reverse of blocking.** It restores the right to
  negotiate, not the access that was withdrawn. Connections the block revoked
  stay revoked and have to be established again.

## What the agent sees

An agent presenting a revoked grant is told so explicitly, and the answer is
**terminal**. It is not `need_info`, and it is not an invitation to renegotiate.

That distinction matters more than it looks. A bare "inactive" sends a
well-behaved agent back around a negotiation whose outcome is already settled,
which wastes everyone's time and looks, from the owner's side, like an agent
that will not take no for an answer.

## Why this survives the deployment

In the replicated shape, revocation is correct because every replica reads the
same store, so a revoked connection is revoked everywhere the instant it
commits.

That is worth stating plainly as a boundary rather than a feature. Stretch this
across regions, or across more than one authorization server, and it becomes a
distributed-systems problem this profile does not itself solve. What it gives
you is a revocation that is atomic within one authority, which is the part the
protocol can be responsible for.
