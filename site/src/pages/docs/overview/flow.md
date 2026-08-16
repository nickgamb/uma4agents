---
templateKey: doc
title: Identity stays where it is
description: The owner never has to know how the asking agent is identified — checked against four identity regimes that produce one unchanged decision.
next:
  - title: Identity is not authorization
    to: /docs/overview/identity/
    blurb: The distinction this rests on.
  - title: Agent identity
    to: /docs/overview/compare-agent-identity/
    blurb: What each identity scheme answers, and what is left over.
---

The load-bearing idea in this profile is not the ticket or the token. It is
that **Alice never has to know how Bob's agent is identified.**

She writes her terms and sets her tiers. Whether the agent asking is a bare key
with no issuer anywhere, an identified agent whose session keys rotate every
run, one described by a metadata document, or one whose keys are published in a
directory — none of that reaches her. Governance of the agent stays with the
party who runs it. Governance of the resource stays with the party who owns it.
Neither has to adopt the other's identity system for the grant to work.

## Checked, not asserted

Four negotiations against the same authorization server, with the requesting
side arranged four ways:

| Regime | What the agent brings |
|---|---|
| Pseudonymous | a bare Ed25519 key — the key *is* the identity |
| Identified | an AAuth agent token, with a fresh session key each run |
| Described | a CIMD document saying who operates it |
| Published | a Web Bot Auth directory its keys can be looked up in |

Across all four, the terms proffered, the grant issued and her policy are
identical. `make flow-check` in the lab runs it.

## Two levels, not four

Four regimes do not produce four handles:

```
pseudonymous   aauth:pseudonymous-agent
identified     aauth:6db1c44a-…@ps.uma.lab
described      aauth:pseudonymous-agent
published      aauth:pseudonymous-agent
```

There are **two identity levels**. Either the key is the identity, or a
verified issuer stands behind it. CIMD and Web Bot Auth are additive
*description* — they let a party who has never met this agent say something
true about who operates it, and they change nothing about how it is filed or
judged.

Description is not identity, and neither is authorization.

## The negative that makes it falsifiable

Asserting that everything is identical proves little on its own: a system that
ignored all four inputs would also pass. So the check also asserts that her
policy document contains **no identity vocabulary at all** — no issuer, no
thumbprint, no scheme name.

If any identity signal ever became an authorization input, one of the two
halves breaks. Either her policy has to name it, or the four runs stop
agreeing.

## Why it comes out this way

Three decisions already in the profile add up to it.

**The verifying key is always the grant's confirmation claim.** Not the
metadata document, not the directory, not the issuer. Those are consulted for
display and discovery; the key named in the grant is what decides whether a
request is authentic.

**The connection handle follows the identity level and nothing else.** A
pseudonymous agent is filed under its key thumbprint, because the key must
persist for the relationship to persist. An identified agent is filed under its
issuer-qualified subject, because its session keys rotate and a thumbprint
would forget it every run. Both are handles; neither is a permission.

**Her terms are about the access, not the asker.** Purpose, scope, expiry,
prohibitions. A terms template has nowhere to put an issuer.

## What it costs

She cannot write a policy like "only agents from this issuer." She can decide
per agent, per tier and per operation, and she can revoke a connection — but
she cannot express a rule over an identity system she is deliberately blind to.

Today that is the point rather than the limitation: it is what lets an agent
from an organisation she has never heard of ask her for something without
either side onboarding to the other. A deployment that wants issuer rules is
describing a different trust model and should say so.
