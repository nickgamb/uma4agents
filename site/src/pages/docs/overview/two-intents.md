---
templateKey: doc
seoTitle: "Whose intent? Owner intent and agent intent in AI agent authorization"
title: The two intents
description: Who decides whether an AI agent is doing what it said it would — the agent's operator, or the owner of the data it is touching. How U4A answers that, and what the owner can check for herself.
diagram: two-intents
diagramCaption: Her register, filling up. The last row is the only interesting one, and she did not have to be told about it.
next:
  - title: Terms as first-class
    to: /docs/overview/terms/
    blurb: The artifact her half is written in.
  - title: Agent assurance
    to: /docs/overview/assurance/
    blurb: The axes her policy may read, and the rule all of them obey.
---
Two parties want something out of a grant, and both of them have an intent.

Alice has decided, in advance, what she will accept being done with her things.
Bob's agent has arrived wanting to do something specific, now, for a reason of
its own.

Almost all current work on agent intent handles the second one and puts it on
the requesting side: the agent declares a task, its own platform watches the
session, and a departure is reported. That works while one party owns both the
agent and the data. It stops working here, because Alice cannot see inside
Bob's infrastructure and has no way to check a report that comes out of it.

She does not need one. Every request that agent ever made of her arrived at her
side.

## What each side puts in

Alice's half is a tier, written before any agent exists:

```json
"tier3": {
  "name": "Trade execution",
  "resources": ["alice-vault/execute_trade"],
  "ask_me": true,
  "terms": {
    "purpose": "Execution of one client-approved order",
    "scope": ["trades:execute"],
    "expires_in": 900,
    "prohibited": ["orders-beyond-approved-parameters",
                   "discretionary-reuse-of-authority"],
    "per_operation": true
  }
}
```

No agent is named anywhere in it. Editing any field publishes a new version, and
every version stays fetchable, so an agreement signed last month still points at
terms that resolve.

The agent's half is that template signed back, plus up to three things of its
own:

| | |
|---|---|
| `operation` | the exact act it proposes, on tiers that require one |
| `reason` | free text — why it says it is asking |
| `mission` | a reference to a mandate its operator approved, in [AAuth](https://github.com/dickhardt/AAuth)'s `approver`/`s256` shape |

## What her authority checks

The echo, field by field. A rewritten purpose, a dropped prohibition or a
stretched expiry ends the negotiation. Binding itself to *more* than she asked
is allowed, because that direction costs her nothing.

Her authority never reads the reason and never compares it to her purpose. That
would put a judgement about natural language inside an authorization decision,
and the same request would start coming out two ways.

The mission is recorded and not resolved. AAuth serves missions to
administrators, so there is nothing for a relying party in another trust domain
to fetch — from her side, an agent citing a real mandate and an agent inventing
a hash look identical. Both the reason and the mission are therefore claims, and
her policy may do one thing with either: notice it is missing.

```json
{"when": ["request.reason_absent"], "then": "ask"}
```

Rules like that can only add friction. Her authorization server refuses to store
them under `then: auto`, at the point policy is saved rather than when it runs.
Silence costs an agent something; so does a lie.

## Which prohibitions can actually be refused

Not all of them. What divides the two is whether the forbidden thing has to
**cross her boundary** to happen.

Her trade tier forbids orders beyond the approved parameters and discretionary
reuse of authority. Both of those are calls. Placing such an order means
invoking her tool while the enforcement point holds a digest of the parameters
she approved, so it is refused. Reusing the authority means presenting a spent
grant, which is refused too. Neither check was added for this — both have been
running since the grant loop was built, and her terms simply never said so.

Her holdings tier forbids retention after review, marketing, and model training.
Those happen on the requester's own disks after the bytes have left. Nothing
reaches them.

So her published terms mark each line with the mechanism that refuses it, and
say nothing where there is none:

```json
"prohibited": ["orders-beyond-approved-parameters",
               "discretionary-reuse-of-authority"],
"enforced":   {"orders-beyond-approved-parameters": "operation-binding",
               "discretionary-reuse-of-authority": "single-use"}
```

The annotation is computed when the document is read, never written into it. A
published version's bytes never change — that is what lets an old agreement stay
checkable — and her enforcement posture can change without the terms changing at
all, so it is shown alongside rather than folded in.

The half that stays unenforceable is what the dually-signed record is for. That
is a weaker thing than enforcement and a stronger one than a consent checkbox.

## What she can see afterwards

Everything, which is the part the requester-side framing misses.

Her register holds what each agent promised, what she decided, what it went on
to call, and which of her tiers each call was made against. One agent's history
is one query — `GET /owner/ledger?handle=…`, or its handle in the Connected
agents tab.

![Alice's activity ledger in the lab's portal. One negotiation runs bottom to top: a promised row carrying the purpose, the two prohibitions the agent accepted, the exact order it proposed, the terms version and the hash of the agreement; then her approval; then a touched row naming the tool that was actually called with the same parameters. Every row is tagged with the negotiation it belongs to.](/img/docs/owner-ledger.png)

An agent admitted to read holdings that starts reaching further does not need to
be reported. It looks different in her own record, and rules she writes can read
that while deciding:

| Condition | What it notices |
|---|---|
| `standing.first_at_tier` | it is reaching somewhere new |
| `standing.tiers_above:<n>` | how far across her resources it has spread |
| `standing.calls_above:<n>` | how much it did with what it was given |
| `standing.denials_above:<n>` | it is asking again after she said no |

None of them name an agent, and none can be written into a relaxation.

One entry in her register can never be attributed to anyone. A decline arrives
before the requesting side has signed anything, so there is no key and nothing
to file it under. Her record says her terms were refused, which is true and is
all that is knowable.

## What this does not do

- **A stated purpose is not enforceable.** Recording it buys something that can
  be produced later, not a control.
- **This authorizes calls, not sessions.** A session-scoped intent checked
  against every tool call is a requester-side control, and it composes with this
  rather than being supplied by it.
- **Her terms cover her resources.** What an agent does elsewhere belongs to
  whoever operates it.

## Where to go next

- [Terms as first-class](/docs/overview/terms/) — the artifact her half is written in
- [Agent assurance](/docs/overview/assurance/) — what her authority verified, and the rule all of it obeys
- [Revocation and the ledger](/docs/overview/revocation/) — the record this reads, and ending a relationship
