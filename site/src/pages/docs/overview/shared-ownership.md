---
templateKey: doc
title: Shared ownership
description: A firm owns a book, shares parts of it with the people who work on it, and sets policy over it that none of them can waive — while each of them still administers access under her own authority.
next:
  - title: Joint ownership
    to: /docs/overview/joint-ownership/
    blurb: The other co-administration — owners of equal standing, none above the rest.
  - title: Many owners, one resource server
    to: /docs/overview/multi-owner/
    blurb: The arrangement this builds on.
  - title: Compared to policy engines
    to: /docs/overview/compare-policy-engines/
    blurb: Which layer gets the engine, and why.
---

The question this profile is about is *can your agent access my stuff*. This
page is what happens when some of that stuff is not mine.

A firm owns a book. It shares it with the people who work on it. It has
obligations about it that none of them can waive. And the party who decides
whether an agent may touch it is neither the firm nor the agent's operator —
it is whichever member of staff that part of the book was shared with.

UMA has had a name for her role since 2015: **resource rights administrator**,
the party who administers access to resources she does not necessarily own.
The Kantara UMA Work Group's 2022 report on the Julie Adams healthcare use
case calls the general shape **delegation of control** and lays out the four
states it can be in. What neither has had is a mechanism.

![Shared ownership in seven beats. One resource server holds three owners of record: Alice's account, Carol's account, and Northwind Capital's book. The firm shares its book with Alice under a role that grants two resources and sets delegation to first-party-only, so the book appears in her authorization server as something she administers rather than owns. She writes the terms an agent must accept and the charter's ceiling is clamped into that same document. Bob's agent asks for the book and is refused — not by her terms but by the organization's engine, because somebody else operates it. An agent she operates herself makes the identical request and is granted. Two columns then list what the organization can do — see and shut out the agents that touch its book, answer requests about its own resources, break the glass under a clause she was shown — against what it cannot: see the agents that touch her own accounts, read her policy, widen anything, or act as her. Leaving takes back the access and leaves every narrowing in place.](/img/docs/shared-ownership.gif)

## Against the four states of delegated control

The healthcare analysis that names this problem lays it out as four states —
one administrator or several, and a data subject who can or cannot manage her
own resources. Three need no new protocol. Naming which one did is the useful
result:

| State | Status |
|---|---|
| **Self-administration** | The base profile: she administers her own resources. |
| **Administration by proxy** | Nothing changes in the grant loop. What it needs is the thing an owner's authority already does implicitly and no specification names: who may administer this owner's policy. Worth specifying — it is the difference between a guardian, a power of attorney, and an account takeover. |
| **Co-administration** | This page. Several administrators over one subject's resources, each deciding through **her own authority**. |
| **Co-administration by proxy** | The two above composed. Nothing further needed. |

What made the third hard is not the number of administrators. It is that each
decides through her own authorization server, so the enforcement point has to
know which one to ask — and the answer has to be per (resource,
administrator) rather than per resource. Everything else follows from that.

## Three kinds of owner behind one resource server

| | |
|---|---|
| **A customer** | Her account is hers. Nobody else has any say over it, and nothing on this page changes that. |
| **Another customer** | The same, separately — see [many owners](/docs/overview/multi-owner/). |
| **A company** | It owns a book, shares parts of it with named people under a role, and sets policy over it that none of them can waive. |

The third is the new one. It is an owner in the protocol sense — it holds
resources and decides about them — and it differs in two ways that matter: the
deciding is done by an administrator on its behalf, and what it owns is
*administered by other people*, each under her own authorization server.

## One resource, many administrators

The firm's book is one process, reached at a path per member:

```
/mcp                    her own account       -> her authority
/mcp/shared/alice       the firm's book       -> her authority
/mcp/shared/carol       the firm's book       -> a different authority
```

The last two are the same resource. The member segment does not select which
resource; it selects **whose authorization server the enforcement point will
ask**, and therefore whose terms an agent has to accept. That is the whole of
shared ownership at the routing layer, and it is why a challenge for the
firm's book names a member's authority rather than the firm's.

## Joining is an exchange

A governance layer that only narrowed would be a strange thing to volunteer
for. Membership is a trade: the organization gets policy over its own
resources and a say about the agents that touch them, and the member gets
access to those resources — under a role, expressed as resources her own
authority protects and her own terms govern.

The role carries one field that has nowhere else to live:

```json
"analyst": {
  "grants": ["firm-book/get_positions", "firm-book/get_transactions"],
  "delegation": "first-party-only"
}
```

`delegation` does not say what may be accessed. It says **whose agent** may do
the accessing, on behalf of which person:

| | |
|---|---|
| `none` | She may reach the book herself. Nothing she delegates reaches it. |
| `first-party-only` | An agent she operates may be granted access under her terms. Somebody else's may not — whatever her own terms say. |
| `any-agent` | Any agent, subject to her terms and the charter. |

That sentence is not expressible in an authorization system built around one
party, because it is not about permissions. It is about parties. It rests on
her authority already knowing the difference between an agent she activated
and an agent somebody else runs — a fact the requesting side cannot assert,
because only she can claim an operator and only that operator can publish an
agent's key in its own directory. See [agent
assurance](/docs/overview/assurance/).

Roles are groups, and an administrator manages them as such: create one, set
what it reaches, mark the one joiners land in, move people between them. Three
rules shape that surface, and each could reasonably have gone the other way.

A group may only grant what the charter **claims** — a group handing out
`alice-vault/*` is refused before it can become a version, because otherwise
"create a group" is a route into somebody's personal accounts. Saving a group
publishes a charter version, because a group is a set of grants that every
member was shown and widening one is handing out access. And a group with
members in it cannot be deleted: they would be left holding an id that
resolves to nothing, which fails *closed*, so their access would quietly stop
working with no event anyone would think to look at.

Authority here is **partitioned**: Alice administers the book for herself,
Carol for herself, and their decisions never meet — every request has exactly
one member authority plus the firm's ceiling. The *conjoint* case, where two
authorities must answer the same request and neither is above the other, is
[joint ownership](/docs/overview/joint-ownership/).

## The two mechanisms, and why they are different

**A ceiling is clamped.** A bound on what her terms may say is an algebra over
two documents, so it is computed when she edits and the result is written into
her policy. The obvious alternative — leave her policy alone, apply the
ceiling at grant time — is less code and is wrong: the terms document is what
an agent dereferences, reads and signs, and a document that says 24 hours
while the grant lasts one lies to both of them. Clamping on write means what
the organization requires is *in* what the agent agreed to.

Every field of it moves one way. Nothing in a charter can lengthen an expiry,
add a scope, remove a prohibition or turn off an ask.

The other design that suggests itself — publish the ceiling as a second
document and let the agent read both — is worse in three ways: it makes the
requesting side compute an intersection it has every incentive to compute
generously, it allows two documents to disagree with nothing saying which
wins, and the signature would be over her terms alone, leaving the
organization's requirements as the only part of the arrangement nobody
signed.

**A decision is asked for.** Whether one particular request is acceptable is a
judgement about that request, made at the organization's own decision point
against policy the member's authority never sees.

Here is what an agent actually dereferences, from a running lab:

```json
{
  "template_id": "alice/firmbook/v2",
  "purpose": "Desk research on the firm book",
  "expires_in": 3600,
  "prohibited": [
    "client-benchmarking",
    "model-training", "sharing-outside-engagement-team",
    "retention-after-engagement"
  ],
  "organization": {
    "name": "Northwind Capital",
    "charter_version": 6,
    "requires": [
      "Only agents you operate yourself may act on them. Somebody else's agent may not, whatever your own terms say.",
      "No grant over its resources may last longer than 1 hour, whatever your own terms say."
    ]
  }
}
```

The first prohibition is hers; the rest are the charter's, added on write.
`expires_in` is an hour because she asked for a day. And the `organization`
block is there so the agent reading this — before it has a token, before it
signs anything — can see that the party proffering these terms is not the only
party behind them.

The composition rule is one sentence: **both layers must allow, and either may
refuse.** Her policy is what permits; the organization's `allow` means it has
no objection.

## Which layer gets the engine

An organization is the case a policy engine was built for: the operator **is**
the deciding party, there is a compliance function, and the policy outlives
whoever wrote it. A person editing her own sharing rules is the opposite case
— she should never need a debugger to understand what she permitted.

So the member's layer stays a small legible document and the organization's
layer gets [OPA](https://www.openpolicyagent.org). Each party has the tool
that fits whose policy it is, which is the concrete version of the claim on
the [policy engines](/docs/overview/compare-policy-engines/) page that the two
compose. The administrator's own Rego can contribute exactly two things —
`deny` and `ask` — and there is no third, so nothing an organization writes
can make a request easier than the member's own policy already makes it.

### Charter or rule?

The charter and the engine are not two ways of saying the same thing. **The
test is whether a member would have to agree to it again.**

The charter is the bargain: versioned, shown to her in full before she joins,
agreed to by name — the organization's counterpart to the terms she proffers
her own agents. What it may say is deliberately small, because it is a
document people read. The rules are the organization's operating controls. She
is told they exist and is shown the sentence of any rule that stops her, but
not the text, because they are not part of what she agreed to; they move on a
compliance function's clock rather than a membership's, and they can only
refuse or interrupt.

Widening what a group may reach is charter. A close period, market hours, or a
limit the firm is trying for one quarter is a rule:

```rego
deny contains msg if {
	input.role.id == "analyst"
	input.request.expires_in > 900
	msg := "an analyst's access to the firm's book is granted a quarter of an hour at a time"
}
```

That rule is also the join between the layers, and the reason neither collapses
into the other. A settings form cannot express "for analysts, during the close
period" — the combinations are open-ended and an engine has a clock and a
standard library. An engine holding its own membership list would be a
directory with a worse query language. **Who is in which group is state; what
that group may do today is a decision.** The charter remembers, the group
arrives in the engine's input, and the engine decides.

## Where the organization's reach stops

An administrator can see and act on **what touches the organization's
resources**. Not her queue, not her agents, not her record — her authority
filters by what the charter claims before it answers anything. An agent that
reads only her own account appears on no organizational surface, cannot be
denied from one, and cannot be revoked from one.

What the organization learns about her policy is a count and the names of its
own fields that narrowed her. Never a value out of her terms. It is entitled
to know its ceiling is being applied; it is not entitled to read the
arrangements she made underneath it.

Revocation is scoped the same way. An administrator shutting an agent out of
the firm's book does not end her relationship with that agent — it may be
reading her own portfolio for her every morning. And everything an
administrator does is written into *her* record under his name, live on her
screen. A record in which one party's decision appeared as another's would be
worse than no record: it is a record that would be believed.

## Consent, and the one override

Joining hands another party standing authority over her agents, so she is
shown the whole charter in sentences — what it would share with her, what it
would let the organization do, what it could never touch, and exactly what it
would change about terms she has already written — and has to agree to that
explicitly. Her authorization server refuses a join that does not carry the
agreement.

The exception to everything above is **break-glass**: grants the organization
signs with its own key, which never pass through her authority at all — the
enforcement point recognises the issuer and checks them with the organization
instead. It is the only shape in which "the organization owns this data" is a
technical fact rather than a request. It reaches only resources the charter both claims and
names for it, it is short and single-use, and it cannot be done quietly — she
is told the moment a window opens, before any data moves, and every use lands
in her own record.

## What a specification would have to say

Most of this is deployment. Three things are not:

1. **The authority is selected per (resource, administrator), not per
   resource.** A shared resource may name a different authorization server
   depending on which administrator is being asked, and something on an
   unauthenticated first call has to be able to say which.
2. **`delegation`, and its three values** — `none`, `first-party-only`,
   `any-agent`. Whose agent may act, on behalf of which person.
3. **Two obligations on the layer above.** It may only narrow, and the
   narrowing belongs in the terms document rather than being applied at the
   door. And its reach, including what it can read, stops at the resources it
   claims — with the scoping performed by the owner's authority rather than
   left to the upper layer's good manners.

Two things should *not* be specified, because specifying them buys nothing and
costs adoption: the internal shape of a charter, and what evaluates it. An
organization with Cedar, or with a compliance system nobody has heard of,
should be able to answer the decision endpoint and be conformant.

## Leaving

Membership is what granted the access, so leaving takes it back and the firm's
resources disappear from her authority. Her terms keep every narrowing the
charter required: leaving withdraws a ceiling, it does not raise what is
underneath one. Anything she wants back she widens herself, deliberately.
