---
templateKey: doc
title: Wire the owner's approval path
description: Holding a negotiation while a human decides, showing her something she can act on, and authorizing her without inventing a credential for her.
diagram: pend-sandbox
diagramCaption: The rule as the lab implements it. An open tier still pends for an agent she has never met — that is the day-one handshake, and it is the part readers most often leave out.
next:
  - title: Deploy it at scale
    to: /docs/guides/at-scale/
    blurb: What the approval path has to survive once it is real.
  - title: Revocation and the ledger
    to: /docs/overview/revocation/
    blurb: What she can undo afterwards, and what she can see.
---

An owner-authoritative design is only as good as the moment the owner is asked.
If that path is slow, confusing, or absent, every deployment quietly moves to a
policy that never pends — and you have rebuilt the system you were replacing.

This guide covers the pend, the interface, and the credential that authorizes
her.

## Prerequisites

- An authority that can hold a negotiation across restarts
- A way to reach the owner — a portal, an app, a notification channel
- An identity provider the owner already authenticates against

## 1. Decide what pends

Two rules earn their place.

**First contact pends, whatever the tier.** An agent with no standing
relationship gets a decision from the owner even for something her policy would
otherwise permit. This is the day-one handshake, and it is what stops a
permissive tier from being a permissive tier *for everyone*.

**Ask-me tiers pend per operation.** Once a connection stands, ordinary tiers
grant automatically for that agent. Tiers the owner marked ask-me pend every
time, with the specific operation attached.

Everything else grants without bothering her. An approval path that asks about
everything trains the owner to approve without reading, which is worse than not
asking.

## 2. Hold the negotiation, do not hold the call

When a request pends, the authority holds the rotated ticket and refuses with a
"submitted" status. The agent re-presents after an interval, and each poll
rotates the ticket again.

On the agent's side, the pend is **a state to render, not a call to hold open**.
An agent that can express waiting to its own user should hand the wait up rather
than block on a socket for however long the owner takes to wake up.

If your agent speaks MCP, the 2026-07-28 revision turns this into a suspended,
resumable call with a request-state handle instead of a held one. The owner's
decision is still the owner's; the agent's client just stops hanging on it.

There is a gap here worth knowing about. The typed shapes available for
"something is needed" all address the *client's own user*, so there is no field
that says the wait is on a different person entirely. Today the subject travels
as prose in the message. Until that changes, expect a conforming client to try
satisfying the wait from its own user unless you say plainly that it cannot.

## 3. Show her something she can decide

The pending item has to carry enough for a decision and little enough to read on
a phone:

- **Which agent**, by the label she gave it — not a key thumbprint
- **What is being asked**, in the resource's own vocabulary
- **The exact operation**, for an ask-me tier, with the parameters spelled out
- **The terms** the agent signed, dereferenceable rather than summarized
- **Whether this is first contact** or an established connection

![An ask-me approval in the lab's portal: the tier, the purpose, the exact
execute_trade call with its parameters, the agent's verified identity, the terms
it is prohibited from breaking, and Approve or Deny.](/img/docs/owner-approval.png)

For an operation approval, the parameters she sees are the ones hashed into the
grant. If the display and the hash can disagree, the display is decoration. In
the shot above, the `execute_trade` arguments she is reading are the same bytes
the grant will bind to.

A live feed beats polling. In the lab it is a server-sent event stream, backed
by the database's own notification mechanism, so a pod that restarts does not
lose a request she has not answered.

## 4. Authorize her without inventing a credential

The owner API takes **a credential that is hers** — and there is more than one
kind. An access token from the identity provider she already uses, validated
against her realm's published keys, is the obvious one. A key her device holds,
signing each request under RFC 9421, is the other; it is what lets her
authority run somewhere that has no identity provider at all. See
[put the authority on her device](/docs/guides/personal-authority/).

Accept both where both make sense. A person reaches her own things from a
browser, a phone and possibly a personal AI, and each credential should be
independently sufficient and independently revocable.

No static owner credential exists anywhere in the system. This matters more than
it sounds: a shared secret for the owner API is a permanent skeleton key for
every decision the design exists to protect, and it will end up in an
environment variable in a repository.

Validate the token properly. Signature against published keys, issuer, audience,
expiry, and that the subject is the owner whose resources are being decided on.

## 5. Handle the decisions

Approve, on a connection request, records the standing relationship and issues
the grant. Approve on an operation request issues an operation-bound grant for
that operation only.

Deny ends the negotiation with a refusal the agent can distinguish from an error.

Expiry ends it too. If she does not answer within the negotiation's lifetime, the
agent gets an invalid-grant response and can start again later. This is correct
behaviour rather than a failure — the lab's ask-me demo ends with `grant denied:
timed out waiting for the owner` when nobody taps, and that is the system
working.

## 6. Give her the undo

Approval without revocation is a one-way door. She needs, at minimum:

- **Connections** — the standing relationships, with revoke. Revoking marks
  every live grant behind that connection consumed, so introspection fails
  immediately rather than at the next expiry.
- **Resource servers** — which servers hold protection access, with revoke.
  Cutting one off kills its ability to register permissions and to verify tokens
  at the same time.
- **Policy** — her tiers, and which ones are ask-me, editable by her.
- **The ledger** — what was promised, what she personally approved, and what was
  actually touched, correlated.

Those three columns are the ones that answer the question she will actually ask:
did what happened match what I agreed to.

## Verify it

- A pending item survives the authority instance that created it being deleted
- A pending item survives a database failover, and she can still answer it
- A request expires cleanly and the agent is told why
- Revoking a connection kills its live grants immediately, not at expiry
- The owner API refuses a token from a different subject
- The parameters she approved hash to the value the grant carries

## Troubleshooting

**Pending items vanish on deploy.** They are in memory. Move them to the store.

**She approves and nothing happens.** The held ticket is on a different instance
than the one that took her decision. The hold has to be in shared state, not in a
process.

**The event stream reconnects constantly.** A proxy is timing out idle
connections. Send periodic keepalives, or accept the reconnects and make them
cheap.

**Nobody uses the ask-me tier in real deployments.** The path is too slow or the
items are unreadable. That is a product problem and it will decide whether any of
this gets adopted.
