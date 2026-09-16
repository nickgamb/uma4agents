---
templateKey: doc
title: What an operation leaves behind
seoTitle: "Declared consequence: reversible, compensatable, irreversible operations"
description: A resource declares what each of its operations leaves behind, and the owner's policy reads it — so a rule can name the act rather than the tool.
next:
  - title: Single-use means indivisible
    to: /docs/overview/single-use/
    blurb: What the profile already did about acts that cannot be repeated.
  - title: Agent assurance
    to: /docs/overview/assurance/
    blurb: The same tighten-only asymmetry, applied to the agent instead of the act.
---

Alice can write *ask me about anything that cannot be undone* only if something
says which operations those are.

Every deployment knows. This lab has always treated executing a trade as an act
you cannot take back — it is single-use, bound to one operation, and her policy
asks her about it every time. What it did not do was **say so**: the knowledge
lived in two hardcoded lists inside two processes, and an owner who wanted that
rule had to name tools one by one.

Now the resource says it, her authority reads it, and the rule she writes names
no tool at all.

## Four classes

The vocabulary is [Nat Sakimura's](https://nat.sakimura.org/2026/05/19/when-software-becomes-staff-governance-security-safety-for-agentic-ai/),
from his work on governance for agentic AI. They are ordered by **how much
remedy remains**:

| Class | The act can be | Example |
|---|---|---|
| `reversible` | undone completely, by whoever did it | reading a holdings summary |
| `compensatable` | offset by a counter-action, which leaves a trace | cancelling a booking |
| `forward_recoverable` | not undone, but recovered from by going on | repairing a workflow |
| `irreversible` | neither undone nor offset | placing a trade; disclosing a document |

The order is about remedy, **not severity** — how much of the world can still be
put back, not how bad it would be. A reversible act can still be catastrophic
while it stands. Nothing adds these up, for the same reason
[assurance](/docs/overview/assurance/) refuses a single score.

## Who declares it

The **resource server**, in the metadata it already signs. It is the party that
would have to undo the act, so it is the only one in a position to say.

This is the opposite of how the profile treats an agent's description of
*itself*, and deliberately so. A client ID metadata document or a key directory
is [display only](/docs/overview/identity/): a party describing its own
trustworthiness is advertising. A resource describing what its own tools do is
not — it is the party that will perform them.

Her authorization server pulls the declaration into her registry along with
everything else the resource publishes, so what her rules read is what the
resource said, rather than what her deployment happened to be configured with.

## Three rules make it safe to read

**It may only tighten.** Her policy editor refuses to save a rule that would
grant automatically *because* an act is irreversible. That is the same
asymmetry assurance has: evidence may raise what a request needs, and only her
own decisions lower it.

**Absent is unknown.** Not benign, and not severe. MCP's tool annotations
default to assuming the worst of an unannotated tool, which is right for a
client deciding whether to show a confirmation box and wrong here — it would
make every undescribed operation everywhere look irreversible on the day this
shipped. So an undeclared operation satisfies no rule about remedy, and she has
a separate condition for "nobody has said", which is hers to use.

**A resource cannot quietly raise it.** The grant records the class it was
issued against. If the resource later re-declares the operation as less
recoverable — a read that has become a disclosure — the enforcement point
refuses. Her authority answered a question about the operation as described;
that answer does not transfer to a different question.

## The rule she ends up with

```json
{"when": ["request.consequence_at_or_above:irreversible"], "then": "ask"}
```

No tool, no agent, no operator. It holds for tools she has never seen, at
resource servers she has never heard of, on the day they are added.

The class also reaches the agent **in the challenge**, before it negotiates, so
an agent that would rather not ask for something irreversible without its
operator's say-so can find that out at the first refusal rather than afterwards.

## Compared to MCP's tool annotations

MCP has `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`,
and a proposed `reversibleHint`. U4A consumes them where a server publishes
them, and never inherits their defaults — a default is not a statement anybody
made.

Three differences are worth naming:

1. **Who reads it.** MCP's hints are published by a server to a client that may
   ignore them. Here the same fact is read by the party that bears the
   consequence, and enforced by the resource itself.
2. **What it may do.** A hint that can only inform a dialog cannot be a control.
   A class that may tighten a requirement and never relax one can.
3. **Absent is not false.** Defaulting an unannotated tool to destructive is a
   safe posture for a prompt and a poor one for policy.

Run it: `make consequence-check`, or `make k8s-consequence-check` in the
cluster.
