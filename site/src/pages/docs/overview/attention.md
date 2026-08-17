---
templateKey: doc
title: The owner's attention
description: The scarcest resource in an owner-decides design, why an unbounded pending queue is a denial-of-service surface, and how to cap it without shutting out the agent you wanted.
next:
  - title: Agent assurance
    to: /docs/overview/assurance/
    blurb: What her authority can verify, which is what the cap is keyed on.
  - title: Revocation and the ledger
    to: /docs/overview/revocation/
    blurb: What she does about a flood that has a name on it.
---

Every design on this site rests on one thing: **the owner decides**. Requests
she has not stood behind wait for her, holding a ticket, for as long as it
takes.

Which makes her attention the scarcest resource in the system, and the only one
that started out with no limit on it at all. Keys are free. Anyone can mint ten
thousand and put ten thousand first-contact requests in front of her, and every
one of them is individually well-formed — nothing in the protocol notices.

So the property that justifies the whole profile is also its
denial-of-service surface.

## Depth, not rate

Rate limiting is the wrong instrument. Per key it is theatre, because keys cost
nothing. Per source address it is the wrong layer. Neither expresses the thing
that actually matters, which is not how fast strangers arrive but **how much of
her queue they can occupy at once**.

So the control is a depth limit. At most *n* requests from agents she has no
standing with may be waiting at any moment; past that they are refused, with a
reason, rather than queued.

It has three properties a rate limit does not:

- **It is self-healing.** Every request she answers frees a slot, so the cap is
  on the backlog and never on the relationship.
- **It needs no new state.** The count is a read of the pending queue her
  surface already lists.
- **It fails honestly.** The agent is told the owner is not accepting new
  requests right now, which is true, and that it may come back. Silence would be
  indistinguishable from a broken server and would provoke exactly the retry
  storm the cap exists to prevent.

## One queue is not enough

A single cap protects the agents she already knows — they have standing, so they
are never counted against it.

It leaves the case that decides whether any of this is adoptable: **the agent
you want to let in is a stranger too, the first time.** With one queue, a flood
of anonymous bots fills it, and a legitimate newcomer is refused alongside them.
The cap defends continuity and leaves onboarding undefended.

So strangers queue in separate lanes, split on the one thing an agent cannot
establish by its own say-so — whether the operator it names has published *this
agent's key*, which the owner's authority
[checked for itself](/docs/overview/assurance/).

| Lane | Who is in it |
|---|---|
| unattributable | Nobody checkable behind it. Cheap to mint by the thousand, so it gets a deliberately small lane. |
| attributable | A named operator published this agent's key. Entering means standing up a domain, serving a metadata document that claims its own URL, and publishing a key per agent. |

A lane is not permission. Everything in it faces her policy unchanged — this is
the same asymmetry as everywhere else, where better evidence buys less friction
and never more access.

## Attributable is the point, not expensive

The second lane is not meaningfully costly to enter, and it does not need to be.
What it is is **attributable**: every agent minted that way is tied to one
operator, so a flood in that lane arrives with somebody's name on it — and a
named flood is one she can [answer in a single
action](/docs/overview/revocation/) rather than one connection at a time.

A flood in the other lane cannot reach it at all.

## What this does not claim

If she accepts anonymous strangers at all, they can fill the anonymous lane.
Nothing here prevents that, and no scheme does without charging the requester
something. What the split guarantees is that the damage stays in that lane:
neither an agent she already knows, nor a newcomer she could put a name to, is
crowded out by it.

Setting the anonymous lane to zero makes her authority
introduce-yourself-first — a coherent posture, and one setting. It is the wrong
default for a profile whose whole argument is that a stranger can negotiate.
