---
templateKey: doc
title: Joint ownership
seoTitle: "Joint ownership: one resource, several owners, none above the rest"
description: Two people hold an account together and neither can release it alone. What counts the votes owns nothing, decides nothing, and does not have to be trusted.
next:
  - title: Shared ownership
    to: /docs/overview/shared-ownership/
    blurb: The other arrangement — a firm above the owner rather than a peer beside her.
  - title: Many owners, one resource server
    to: /docs/overview/multi-owner/
    blurb: The addressing both of them build on.
---

[Shared ownership](/docs/overview/shared-ownership/) answers *some of this is
the firm's*. This is a different question, and the one with no mechanism
anywhere: **what if a resource has two owners of equal standing, and neither
can decide alone.**

A joint bank account is the ordinary case. The hard one is a data set with
several subjects whose interests genuinely conflict, where nobody sits above
them to arbitrate and no single one of them should be able to release it.

![One resource held by two people: each owner's terms are quoted and folded
into a single document, each authority signs its own verdict, and the grant
carries them to a door that verifies and counts again.](/img/docs/joint-ownership.gif)

## Three objects

```
mandate    who is entitled to be counted, at what weight, and how many it takes
verdict    one owner's authority, signing its answer to one negotiation
tally      the party that collects verdicts and does arithmetic
```

The third is the awkward one. Something has to put one question to several
authorities and combine the answers, and whatever does that sits in a
structurally privileged position — while every party here is a peer, so there
is no principled place to put it.

The reflex is to make the privileged thing trustworthy: replicate it,
distribute it, reach for a ledger. This takes the other route. **The tally is
made unable to lie, and then it does not matter who runs it.**

## Why this is not consensus

The word does real damage here. Distributed consensus solves agreement on an
*ordered history* among parties who need a coordinator they cannot trust.
None of that applies.

Verdicts about one negotiation are a **set**, not a sequence — nothing depends
on which arrived first. There is no long-lived state to protect, because
grants are short and re-negotiated; no balance exists that a fork could
double-spend. Replay is prevented by binding each verdict to a negotiation and
an exact agreement digest, which is a signature problem rather than a ledger
one.

And the coordinator does not have to be trusted, so it does not have to be
decentralised. **You decentralise a coordinator when you are forced to trust
one.** Making it unable to fabricate a yes removes the requirement instead of
satisfying it.

What is left is a fold and a comparison.

## What the tally cannot do

**It cannot manufacture a yes.** It holds no key that any relying party
accepts as a verdict. The grant it issues carries the owners' signed verdicts
inside it, and the enforcement point verifies each against the keys *that
owner's authority* publishes, then re-runs the count. A tally that forged a
verdict, replayed an old one, or reported a threshold it never reached is
refused at the door.

The count runs against the mandate the tally **publishes**, never the copy
inside the grant. Otherwise the party being checked supplies the standard it
is checked against — one genuine verdict beside a mandate saying one is
enough would pass, with every signature verifying.

**It cannot weaken anybody's terms.** It folds every owner's terms into the
one document an agent signs, and each owner's authority independently compares
what was signed against what she published — refusing on any difference in
the direction of *more*.

**It decides nothing about identity.** It checks that the agreement was signed
by the key it names, because that key is bound into the grant, and stops.
Whether the agent is identified, who operates it, and whether that operator
published the key are judgements the owners' authorities make with their own
evidence. A coordinator that graded identity would be a coordinator holding
policy.

## One document, everybody's terms

An agent cannot usefully sign four documents, and an intersection computed by
the requesting side is one computed by the party that benefits from computing
it generously. So the agent is offered a single folded document:

| | |
|---|---|
| expiry | the shortest any owner set |
| scopes | only those every owner offers |
| prohibitions | every one any owner wrote |
| asks a person | if any owner wants asking |

That is the same operation as a firm applying a ceiling, pointed sideways
instead of down — so it is the same code, with the one-directional guarantee
already proved for the [organization's
envelope](/docs/overview/shared-ownership/). What makes it safe to let an
untrusted party do the folding is that **it is checked afterwards by everyone
it could have cheated.**

## Why a verdict is not a claim the agent gathers

The obvious UMA-shaped answer is claims-gathering: `need_info` names what is
required, the requesting party collects it and returns. That machinery is old
and rich — the UMA1-era claim-profiles work imagined `need_info` carrying a
great deal of structure, which is also where this profile's terms template
comes from.

It is still the wrong home for a verdict, because **a claim the client gathers
is a claim the client can decline to gather.**

An agent holding two allows and one refusal has every incentive to present the
two and report the third as outstanding — and a claim that is missing looks
exactly like one not yet answered. The refusal would never arrive. So verdicts
travel authority-to-authority and the requesting party never handles one. It
does end up carrying them, inside the grant, but by then the count is settled
and the enforcement point re-checks it anyway.

The general rule is worth stating: **claims work when the requesting party is
the only one who has the fact, and fail when the fact might be adverse to it.**

## Silence is not consent

An owner who has written no terms over the resource quotes nothing and is left
out of the fold rather than defaulted into anything. Under a rule that needs
everybody, that stops the request. An authority that cannot be reached is not
a yes either. Both fail closed, and only the logging tells them apart.

## Who sets the threshold

```json
"rule": { "kind": "all" }
"rule": { "kind": "any" }
"rule": { "kind": "threshold", "threshold": 3 }
```

Owners may carry different weights, and `any` means the *lightest* of them can
act alone — otherwise the word would quietly exclude somebody. A refusal does
not wait for everybody: the moment the outstanding weight cannot carry the
request over the threshold, it is refused.

**A group cannot answer what quorum sets the quorum.** So a mandate carries a
floor supplied by somebody other than the holders — an account agreement, or a
regulator — and a mandate below it is refused when it is loaded. That is the
same shape as a firm's ceiling, which means **peers compose horizontally while
an authority above them clamps vertically.** The two arrangements are
orthogonal rather than rival.

## What the agent sees

Nothing unusual. An ordinary challenge, an ordinary `need_info` with terms to
sign, an ordinary wait while people are asked. The `as_uri` happens to name a
party that owns nothing, and the terms document says so — who the holders are,
what the rule is, and how many it takes.

An unmodified agent negotiates with a tally exactly as it negotiates with an
authorization server. A shape that required the requesting side to know about
joint ownership would not be adoptable.

## Run it

```bash
make joint-check
```

**29 assertions across six processes.** The sharpest is the forgery: a grant
with one verdict replaced by a signature nobody's authority made, refused at
the enforcement point rather than believed.
