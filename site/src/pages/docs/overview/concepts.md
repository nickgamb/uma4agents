---
templateKey: doc
title: Concepts
seoTitle: "Core concepts of owner-authoritative AI agent authorization"
description: Every idea the rest of the documentation assumes, each in a paragraph, in the order the pieces meet each other.
next:
  - title: The four beats
    to: /docs/overview/four-beats/
    blurb: The negotiation, step by step.
  - title: Glossary
    to: /docs/overview/glossary/
    blurb: Terms and their exact meanings.
---

This is the whole design in short form, in the order the pieces meet each other.
Every idea below has a page of its own further down the section, starting at
[the four beats](/docs/overview/four-beats/) — except the last, which is small
enough to be finished here.

No count, deliberately. A list that advertises how long it is has to be edited
twice every time the design grows.

## The four beats

A negotiation is **challenge**, **attempt**, **commit**, **grant**. The
enforcement point refuses and hands back a ticket; the agent presents the ticket
at the owner's authorization server; the server dictates terms and the agent
signs them; the server issues a grant. Everything else is detail hung off those
four exchanges.
[Read more →](/docs/overview/four-beats/)

## Owner, requesting party, client

Three roles, not two. The **owner** decides. The **requesting party** is the
human or organisation asking. The **client** is the software that does the
asking — in this profile, usually an autonomous agent. When the client was a web
app somebody sat in front of, the requesting party and the client shared a
session; an agent separates them.
[Read more →](/docs/overview/parties/)

## Terms as an artifact

The authorization server does not just decide — it **dictates** machine-readable
terms and requires the agent to sign them. Purpose, scope, expiry, and what is
prohibited. Both sides keep the receipt, so what was agreed is checkable
afterwards rather than asserted.
[Read more →](/docs/overview/terms/)

## Identity is not authorization

Knowing which agent is calling tells you nothing about whether it may proceed.
Identity is an input to a decision the owner's authority makes. The lab supports
a **pseudonymous** agent, which *is* its key, and an **identified** agent, whose
continuity survives key rotation.
[Read more →](/docs/overview/identity/)

## Discovery has two layers

What a resource *is* — its tool surfaces, its scopes, which authorization server
speaks for it — is public. **Whose** instances sit behind it is not. The public
layer is an RFC 9728 document; the owner-bound layer is behind an endpoint only
the owner's authorization server may query.
[Read more →](/docs/overview/discovery/)

## Grants bind to keys

A bearer token is a token anyone who holds it can spend. Grants here are
**proof-of-possession**: the token names a key, and every request is signed with
it. Sensitive grants bind further, to one operation with one set of parameters.
[Read more →](/docs/overview/proof-of-possession/)

## Single-use means indivisible

A permission ticket is spent once. A per-operation grant is spent once. Once
means once **across every replica**, which makes it a property of how the store
is written rather than of the protocol. Read-then-write is correct in a single
process and wrong the moment there are two.
[Read more →](/docs/overview/single-use/)

## Revocation and the ledger

Every negotiation writes structured events correlated by one id. What the agent
promised, what the owner personally approved, what was actually touched.
Revoking a connection burns live grants in the same operation that ends it, so
there is no window where the agent still holds what the owner just withdrew.
[Read more →](/docs/overview/revocation/)

## Assurance is verified, never attested

What the owner's authority knows about an agent is what it **checked itself** —
a signature against a key it can name, a credential against its issuer's
published keys, an operator's own directory holding this very key. Three
independent axes, never added into a total, because a total is how strong key
binding comes to excuse an unknown operator. And the reading is one-way:
evidence may only add friction, and only her own past decisions may remove it.
[Read more →](/docs/overview/assurance/)

## Her attention is attackable

Keys are free, so an unbounded queue of first-contact requests turns "she
decides" into a denial-of-service surface. The control is a depth limit rather
than a rate limit, split into lanes so a flood of anonymous strangers cannot
crowd out the newcomer she actually wanted to admit — who is a stranger too, the
first time.
[Read more →](/docs/overview/attention/)

## Tiers

Policy is written against **resources**, not against agents. A tier names the
tools it covers, the terms it dictates, and whether the owner must be asked. An
agent she has never seen is not a gap in her configuration — it is the next one
to negotiate against terms that already exist.
