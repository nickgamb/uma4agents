---
templateKey: doc
title: Clearance, which is nobody's here to give
seoTitle: "Clearance: licence and jurisdiction checks in an agent authorization grant"
description: Some authorizations are facts about the world, not decisions the owner can make — so they travel authority to authority, never through the agent.
next:
  - title: Joint ownership
    to: /docs/overview/joint-ownership/
    blurb: Where the same rule about adverse facts was first arrived at.
  - title: Shared ownership
    to: /docs/overview/shared-ownership/
    blurb: The layer above the owner that can require a clearance.
---

Alice's terms decide whether an agent may touch her things. They cannot decide
whether the act is *permitted at all*.

Whether the desk behind a trade holds a current licence, whether it is
registered where the order would be placed, whether a buyer is old enough —
these are facts about the world, established by somebody else. A grant that
asked the requesting party for them would be a compliance check performed by
the party it is about.

## The rule

> A claim works when the requesting party is the only one who holds the fact,
> and fails when the fact may be adverse to it.

That sentence came out of [joint ownership](/docs/overview/joint-ownership/),
where a counting party's verdict could not travel as a claim from the agent
being counted. A licence is the same shape: its holder has every reason to say
it is current, and no counterparty can tell the difference from the assertion
alone.

So a clearance never rides on the agent. The organization attests it, her
authorization server fetches it over its own membership credential, and
verifies it against the keys the organization publishes.

## What travels

| | |
|---|---|
| Who requires it | her policy, her organization's charter, or both |
| Who attests it | the organization, about its member |
| Who verifies it | her authorization server, against the organization's published keys |
| How | a signed, short-lived attestation naming her as subject and her authority as audience |
| Who never carries it | the agent |

Short-lived on purpose: a licence is exactly the kind of fact that lapses, and
a statement about one should not outlive it. Withdrawing it is an administrator
setting it to nothing — access stops within the attestation's lifetime, and
nobody edits a policy to make that happen.

## The requirement, and the stack of policies

A requirement is a set of claims, each naming the values that satisfy it:

```json
{"licence_active": [true], "jurisdiction": ["US-NY", "US-NJ"]}
```

This is where the two layers of policy meet. The business's compliance rule and
the individual's sharing rule are different documents written by different
people, and both apply: the organization requires the clearance in its charter,
her own terms still decide what an agent may do with what it reaches, and
**both must be satisfied**.

Where both name a claim, they combine by **intersection** — a claim either
requires is required, and a claim both require is satisfied only by values both
accept. The layer above may add a claim and narrow an accepted value. It cannot
remove a requirement she wrote, and she cannot edit out one it added.

## When it is unmet

The negotiation is refused **before her terms are dictated**, and the refusal
names the claim rather than saying "denied". An agent that signed an agreement
it was never going to be allowed to act under would hold a record of a bargain
that never existed.

Her ledger keeps the reason in the words she would be shown. An organization
that cannot be reached has not attested to anything, so that is a refusal too.

## What the grant carries

A digest, and not the facts.

That a clearance was checked is the enforcement point's business; what it said
is the subject's. The facts are about her — her licence, where she is
registered — and the party that would read them out of the grant is the agent
that asked. So the token carries a hash, her ledger keeps the facts on her
side, and the check asserts both.

## Why not a claim token

Because there is deliberately no wire path for one. Her authority accepts two
claim token formats — her signed terms agreement, and an enterprise identity
assertion — and a clearance offered by a client is refused as a format this
authority does not take.

The enterprise assertion is the neighbouring case, and the contrast is exact:
[Cross App Access](/docs/overview/cross-app-access/) says *who the agent acts
for*, which is a fact the requesting side legitimately holds about itself. A
clearance says *whether that party is permitted*, which is not.

Run it: `make clearance-check`, or `make k8s-clearance-check` in the cluster.
