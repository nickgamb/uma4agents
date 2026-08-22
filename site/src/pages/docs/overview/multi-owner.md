---
templateKey: doc
title: Many owners, one resource server
description: A firm holds many people's accounts, and each of them may name a different authorization server — including one the firm was never configured against.
next:
  - title: Put the authority on her device
    to: /docs/guides/personal-authority/
    blurb: What it takes to run one of these yourself.
  - title: Deploy it at scale
    to: /docs/guides/at-scale/
    blurb: The other direction — one authority, many replicas.
---

Two questions that sound different and are the same question from two sides:

- can one resource server hold many people's accounts, each governed by its
  own owner's policy?
- can an owner name an authorization server the resource server has never
  heard of?

The first is what a firm asks. The second is what a person asks. Answer only
the first and you have multi-tenancy — one operator running one authority over
many customers, which is the arrangement UMA was written to replace. Answering
the second is what makes the first worth having, because it is the point at
which "her policy" stops being a row in someone else's table.

![One resource server, two owners, two authorities. On the left, an agent that
runs the same four beats against each owner it meets. In the middle, the
firm's enforcement point holding two protected resources, one per owner, at
/mcp/alice and /mcp/carol. On the right, two authorization servers that share
nothing: Alice's is three replicas over a synchronous Postgres cluster and was
provisioned alongside the gateway with a shared secret; Carol's is one small
process holding its own state, which the firm was never configured against and
which the resource server had to introduce itself to. Along the bottom, the
five steps of that introduction: register, verify, pend, she decides, and then
a PAT.](/img/docs/multi-owner.svg)

## What belongs to an owner

| | |
|---|---|
| Her authorization server | Named in the challenge for her resource, and nowhere else. Two owners of one resource server can name two different ones. |
| Its signing key | A grant for one owner does not verify against the other's published keys. |
| Her identity provider | A realm of her own. An authority that accepts another party's tokens for its owner is only partly hers — whoever runs that provider can mint her. |
| Her policy | Her tiers, over her resources. Nothing in one owner's tiers can name another's. |
| Her terms | Dereferenceable without a token, because an agent has to read them before it has one. |
| Her record | Her ledger, her connections, her pending queue, and the budget that bounds it. |
| Her instance of the resource | A separate vault holding her positions, not a row in someone else's. |

What is shared belongs to the firm rather than to either of them: the resource
server process, the enforcement point, the gateway, and the origin those
publish under.

## How a request says whose resource it is

On the first call there is no credential, so the path is the only thing that
can say. Every owner has one — there is no default owner served at the bare
path with the others hanging off it, because that shape makes one person's
account the special case.

| | |
|---|---|
| `/mcp/<owner>` | The protected resource, one per owner. |
| `/.well-known/oauth-protected-resource/mcp/<owner>` | RFC 9728 metadata naming **her** server in `authorization_servers`. This is where an agent finds out whose authority governs what it was just refused by. |
| the challenge | Carries `as_uri`. An agent that cannot be told which authority to go to cannot be sent to one of her choosing, which is why this is on the wire and not in configuration. |
| the ticket and the grant | Both carry the owner, so neither resolves anywhere else. |
| resource ids | Namespaced per owner, so a tool id never resolves against another owner's policy. |

How many owners live in one process is a packaging choice the grant loop
cannot observe — one each, or a thousand in one. What must not vary is which
rows an owner can reach, and that is best made structural rather than a
parameter passed to every query: a parameter can be forgotten in one place,
and that failure is silent.

## Bringing your own authorization server

FedAuthz begins with a resource server that already holds a protection API
token and says nothing about how it got one. Where a single operator runs both
sides, a provisioned client secret is a fair account of that: somebody stood up
the authority and the gateway together and configured each against the other.

It stops being an account of anything the moment the authority is the owner's.
There is no point at which anyone could configure her server and the firm's
gateway against each other, because the two belong to different people. She
will not paste a secret into her broker's console and the broker will not hold
one secret per customer. This is the gap where most deployments quietly become
multi-tenant instead.

The pieces already imply the answer: **the resource server authenticates as its
origin.**

```
1  register   RS  →  AS    a request signed (RFC 9421) with a key the resource's
                           own origin publishes. No credential, nothing seeded.
2  verify     AS  →  RS    fetch the RFC 9728 document at the claimed resource
                           and the JWKS it names, and check the signature
3  pend       AS  →  her   the registration lands in her registry as pending
4  decide     her →  AS    she approves it, or she doesn't
5  PAT        RS  →  AS    signed the same way. The four beats run from here.
```

Three things must hold about the document fetched at step 2, and each closes
one way of registering as somebody else: it claims **this** resource, its
`jwks_uri` is **same-origin**, and it names **this** authorization server. The
party being trusted is whoever controls the origin — which is the address the
challenge already pointed at, so nothing new is being trusted.

## What a verified signature buys

Who is asking. That is all.

Whether they may is hers, and until she answers the registration sits in her
registry as `pending` and opens nothing. The refusals are the substance:

| | |
|---|---|
| an origin that does not publish the key that signed | refused |
| a claim to a resource whose own metadata names another | refused |
| a signature old enough to have been captured and replayed | refused |
| a verified registration, before she has answered | `authorization_pending` — and the call it was for says so, rather than failing generically |
| after she withdraws it | the next call stops. Registering again returns it to `pending`, never to `active` |

That last row is the one worth reading twice. A withdrawn resource server may
ask again — the same shape as an agent she has blocked asking a second time —
and asking is not a way to undo her answer.

There is one thing this deliberately does not remove. Which authorization
server speaks for a person is a fact only that person holds, so she still tells
the resource server where hers is, the way she tells it a mailing address. What
goes away is the part that had to be arranged *between the two companies*, and
that was the part that made a personal authorization server impossible.

## Small enough to be a person's

The two authorities in the reference deployment are the same image running the
same code at deliberately different sizes: one is three replicas over a
synchronous Postgres cluster; the other is a single process, 128Mi, holding its
own state. Nothing on the wire distinguishes them.

The small shape is correct only because the store is in the process. Two
replicas of an in-process store are two authorities answering behind one name,
and a single-use artifact minted by one would be unspendable at the other.

Which is the useful boundary if you are thinking about pushing this further
out: policy evaluation is pure and runs anywhere, terms and keys are static
artifacts, and an "ask me" decision is already wherever she is. What has to
hold still is two functions — burning a ticket and burning a grant — because
each has to be indivisible.

## Where to go next

- [Put the authority on her device](/docs/guides/personal-authority/) — the credential it needs, and what stays the server's job
- [Single-use means indivisible](/docs/overview/single-use/) — why those two functions are the ones that cannot move
- [Deploy it at scale](/docs/guides/at-scale/) — the same protocol, the other direction
- [Discovery, public and protected](/docs/overview/discovery/) — the metadata document the registration check reuses
