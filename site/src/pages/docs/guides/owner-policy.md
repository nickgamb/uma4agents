---
templateKey: doc
title: Let the owner write her own policy
description: Terms she adds herself, rules about the requests that reach her, and the one validation that has to happen where policy is stored rather than where it is evaluated.
next:
  - title: Agent assurance
    to: /docs/overview/assurance/
    blurb: What the rules below are allowed to read.
  - title: Wire the owner's approval path
    to: /docs/guides/approval/
    blurb: Where the requests these rules hold back end up.
---

An owner-decides design that ships a fixed policy is not owner-decides. This is
what her surface has to let her do, and the two mistakes that are easy to make
while building it.

## Prerequisites

- Resources [registered](/docs/overview/discovery/) with her authority
- A [terms document](/docs/guides/terms/) per policy group, versioned and served
- Somewhere she can be [asked](/docs/guides/approval/)

## 1. Terms are hers to add, not just to edit

The seeded policy is a starting point, not the shape of her life. She needs to
create a group of her own — a name, a purpose agents must accept, an expiry, a
prohibited list, and whether it must be put to her.

Two constraints are worth enforcing rather than documenting:

- **A group may only cover resources her authority already protects.** Terms
  over something nobody is protecting is a rule that can never fire. Resources
  arrive by registration; she attaches policy to them.
- **One resource belongs to one group.** Two groups over one resource makes
  which terms apply depend on the order they happen to be stored in, and that
  is not a policy.

Deleting a group leaves its resources ungoverned, and ungoverned should mean
**denied**. A destructive edit that fails towards withdrawing access is the only
kind that fails safely.

Published terms documents are not deleted with the group. An agreement signed
against them stays checkable, which is the whole reason they are versioned.

## 2. Rules read evidence, and name no agent

Beyond "who may ask for what", she needs to say something about the *request*.
The shape that stays legible is one list per group:

```json
"rules": [
  {"when": ["assurance.accountability_below:1"], "then": "ask"},
  {"when": ["standing.age_above:90d", "standing.never_revoked"], "then": "auto"}
]
```

Conjunction inside a rule, disjunction across rules, and nothing else. No
negation, no nesting, no expressions. The moment a policy document can express
anything it needs a debugger, and she is not going to open one.

`then` is one of *grant quietly*, *ask me*, or *refuse*. Relaxations apply first
and restrictions last, so no combination of matched rules can land more
permissive than the strictest thing that matched.

Conditions name **properties of evidence**, never identity systems — no issuer,
no metadata URL, no key thumbprint. `accountability_below:1` says *nobody I can
check is behind this*, not *no metadata document*. That is what keeps a rule
true after the mechanism underneath it changes.

## 3. Only her own decisions may relax

This is the line that needs drawing one notch finer than it first appears.

"Facts her side produced" is too coarse, because one of them is circular:
*we granted here before* may record an **automatic** grant, so relaxing on it
would let one automatic grant justify the next. What may safely lower a
requirement is what she personally decided — she admitted this agent, she
approved at this tier, she has never revoked it.

Everything else, including her own authority's issuance records and everything
in [agent assurance](/docs/overview/assurance/), may only raise one.

When a relaxation does lower an ask-me tier, write it to her ledger naming the
rule that fired. A grant that skipped her should be something she can go and
find rather than infer.

## 4. Validate where policy is stored

A rule that could widen access on evidence the agent controls must **fail to
save**.

Not fail to apply. A control that is silently inert is worse than one that was
never claimed, because a deployment then believes it has a boundary it does not
have. Reject it at the API her surface writes through, and say which condition
and why — the rule is easier to learn from a refusal that explains itself than
from documentation nobody opened.

Validate arguments too, not only condition names. A condition that stores
cleanly and then raises during evaluation is a 500 on the token endpoint caused
by an edit that reported success — and if the bad rule is a relaxation it can
stay latent until the first ask-me request evaluates it, so it surfaces on the
most sensitive tier and nowhere else.

Then make evaluation fail towards the owner regardless: a rule that cannot be
evaluated should be treated as *matching* if it is a restriction and *not
matching* if it is a relaxation. Both land on more friction rather than less.

## 5. Being admitted is not being admitted everywhere

One default rule is worth copying, because the bug it fixes is easy to ship.

If approving a first contact admits an agent to everything below the ask-me
line, then an agent she let in to look at one thing can read another without
asking again — a broader relationship than she was shown when she approved it.
A predicate on *the first request at each group* brings it back to her.

Note the shape: a predicate, not a per-agent list of what that agent may reach.
The list works, and it is an access-control list, which is the thing this whole
approach exists to avoid.

## What her surface should show

Rules as sentences, not JSON — *"If nobody named and reachable is standing
behind the agent, ask me first"* — composed from a vocabulary the authorization
server publishes, so the surface cannot offer her something the server will
reject.

And when a request is put to her, show what her authority could and could not
establish about the agent, and which rule routed it to her. Deciding without
that is deciding blind.

## Verify it

- A rule that would relax on evidence the agent controls is refused, and the
  refusal names the condition
- A rule with a missing or unparseable argument is refused at save time
- A group over an already-governed resource is refused
- Deleting a group causes requests for its resources to be denied, not allowed
- An automatic grant that a relaxation produced appears in the ledger

## Troubleshooting

**Her edits appear to save and change nothing.** The surface is sending a subset
of the document — the classic version of this drops the rules and keeps the
terms. Check what the request body actually contains, then check the response is
being read at all: a client that discards error bodies reports every rejection
as a success.

**A rule fires on the tier below the one she wrote it for.** Conditions that
read "at this tier" need the tier in the evaluation facts. Passing the tier
implicitly, or defaulting it, produces exactly this.

**Everything is suddenly denied.** A group was deleted and its resources are
ungoverned. That is the safe direction, and it is why the message says so.
