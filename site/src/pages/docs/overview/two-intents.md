---
templateKey: doc
seoTitle: "Whose intent? Owner intent and agent intent in AI agent authorization"
title: The two intents
description: A grant has two parties who want something. What the owner requires is checked; what the agent says it wants is recorded. The difference is the whole design.
diagram: two-intents
diagramCaption: Four things she stated. Two of them a machine can test on every call; two of them nothing can.
next:
  - title: Terms as first-class
    to: /docs/overview/terms/
    blurb: The artifact her half is written in.
  - title: Agent assurance
    to: /docs/overview/assurance/
    blurb: The axes her policy may read, and the rule all of them obey.
---

Alice writes a tier before any agent exists. It says what the access is for,
what she will not have done with it, how far it reaches, how long it lasts,
and whether a request has to name one specific act:

```json
"tier3": {
  "name": "Trade execution",
  "resources": ["alice-vault/execute_trade"],
  "ask_me": true,
  "terms": {
    "template_id": "alice/advisor-tier3/v2",
    "purpose": "Execution of one client-approved order",
    "scope": ["trades:execute"],
    "expires_in": 900,
    "prohibited": [
      "orders-beyond-approved-parameters",
      "discretionary-reuse-of-authority"
    ],
    "per_operation": true
  }
}
```

No agent is named in it. Editing any field bumps `template_id` to a new
version, and every version stays dereferenceable, so an agreement signed last
month still names terms that resolve.

## The agent's half

Beat 2 hands that template to whoever is asking. Beat 3 is the agent signing
it back with the key it will later prove possession of:

```json
{
  "template_id": "alice/advisor-tier3/v2",
  "purpose": "Execution of one client-approved order",
  "scope": ["trades:execute"],
  "expires_in": 900,
  "prohibited": ["orders-beyond-approved-parameters",
                 "discretionary-reuse-of-authority"],
  "operation": { "tool": "execute_trade",
                 "params": { "symbol": "VTI", "side": "sell", "quantity": 40 } },
  "reason": "Trimming an overweight position the client approved by phone.",
  "mission": { "approver": "https://ps.example", "s256": "…" }
}
```

Everything down to `operation` is hers, repeated. The last three lines are the
agent's: the act it proposes, why it says it is asking, and the mandate it is
acting under if its operator gave it one.

## What the comparison does

`verify_contract` is the only place both halves are in hand at once, and it is
deliberately narrow. The echo is compared to the template field by field:

| Check | Fails when |
|---|---|
| `purpose` | the echoed purpose is not the dictated one |
| `prohibited` | the echoed list is not a superset of hers |
| `expires_in` | it asks for longer than the tier allows |
| `operation` | a per-operation tier gets a contract naming no act |

The prohibitions check is a subset test rather than an equality test. An agent
may bind itself to more than she asked, never less — a valid signature over
weakened terms is what an adversarial agent would send, and it is the case the
check exists for.

Nothing reads the agent's own three lines and judges them. There is no
natural-language comparison anywhere in the grant, and adding one would make
the same request answerable two ways.

## Two of the four survive to the door

Of the things she stated, two can be tested on every later call and two cannot.

**Testable.** The grant carries the scope and expiry, a digest of the exact
operation, and the key that must sign the request. The enforcement point checks
all three before the call reaches the resource, in a fixed order, and spends a
single-use grant last. A grant issued for one order and presented against
another is refused, though the signature is valid and the token has not expired.

**Not testable by anything.** Purpose and prohibitions are prose about the
future. Nothing at the wire level stops an agent that agreed not to retain data
from retaining it.

So they are recorded instead. The grant returns a receipt embedding the
complete signed agreement, counter-signed, and the ledger holds a `promised`
row with the purpose, the prohibitions, the terms URI and the agreement hash.
That is a weaker guarantee than enforcement and a stronger one than a consent
checkbox: the signature buys attribution, not prevention.

## What the agent says it is for

`reason` is free text, capped, and never compared to anything. It exists so a
person reading an approval has more than a hash to go on. Her policy may do
exactly one thing with it:

```json
{"when": ["request.reason_absent"], "then": "ask"}
```

That rule may only tighten — the authorization server refuses to store it under
`then: auto`, at the point policy is saved rather than when it is evaluated.
Silence costs an agent friction, and so does a lie. It is the same bargain
every requester-supplied claim makes here, and it is what lets her authority
read a self-asserted sentence without inheriting a trust framework.

## The mandate behind it

The market's version of agent intent lives on the requesting side.
[AP2](https://ap2-protocol.net/)'s Intent Mandate is signed by the user inside
their own client; drift detection binds a session to a declared task and
watches for departures from it. All of it is one principal defending against
their own agent, which works because the party declaring the intent and the
party owning the resource are the same. Here they are not.

The nearest artifact is an **AAuth mission**: a durable record of a requesting
party setting their agent a task, approved at that party's own person server
and named by content hash. An agreement can cite one in AAuth's own shape,
`approver` and `s256`, so nothing here invents a field.

What that citation is worth is the interesting part, and the honest answer is
*less than it looks*. Her authority cannot dereference it — AAuth serves
missions to administrators, and a relying party in another trust domain has
nothing to fetch. So an agent citing a real mandate and one inventing a hash
are, from her side, the same agent. It is carried as a claim beside the
free-text reason it is currently no stronger than, and her policy may notice
its absence.

It is deliberately not an [assurance](/docs/overview/assurance/) axis for that
reason. Those mean what her authority verified for itself, and awarding a level
for an assertion nobody checked would be a comment about the call path rather
than a check. If a projection a relying party may read ever exists, a verified
mandate earns an axis — who runs an agent and who set it this task are
different questions.

Containment is not hers in any case. Whether a request falls inside someone
else's mandate is a question for the party who approved it, and AAuth is
explicit that the protocol supplies correlation rather than containment. What
she could establish, given something to dereference, is that a mandate exists
at all.

## Where drift shows

**Before the fact**, her rules face the requesting side without naming an
agent. The shipped policy uses one for exactly this:

```json
{"when": ["standing.first_at_tier"], "then": "ask"}
```

Being admitted is not being admitted *here*. Two more read her own record over
a configured window — how often she has denied this agent, and how many
different tiers it has reached. Neither can be written into a relaxation.

**After the fact**, every ledger entry names the agent it was about, so one
agent's promises, her decisions and what it went on to touch are a single list:

![Alice's activity ledger in the lab's portal. One negotiation runs bottom to top: a promised row carrying the purpose, the two prohibitions the agent accepted, the exact order it proposed, the terms version and the hash of the agreement; then her approval; then a touched row naming the tool that was actually called with the same parameters. Every row is tagged with the negotiation it belongs to.](/img/docs/owner-ledger.png)

Drift is the distance between the promised row and the touched rows, and
reading it needs no model of the agent. Above, the two carry the same three
parameters, because on this tier the grant would not have opened the door for
any others.

One entry can never be attributed, and that is a property rather than a gap. A
decline arrives at beat 2, before the requesting side has signed anything, so
there is no key and nothing to file it under.

## The limits

- **Purpose is unenforceable.** Stating it buys a record that can be produced
  afterwards, not a control.
- **This authorizes calls, not sessions.** A session-scoped intent checked
  against every tool call is a requester-side control. It composes with this;
  it is not supplied by it.
- **Her terms cover her resources.** What an agent does elsewhere belongs to
  whoever operates it.

## Where to go next

- [Terms as first-class](/docs/overview/terms/) — the artifact her half is written in
- [Agent assurance](/docs/overview/assurance/) — the four axes, and the asymmetry they share
- [Single-use means indivisible](/docs/overview/single-use/) — why the operation binding holds under replication
