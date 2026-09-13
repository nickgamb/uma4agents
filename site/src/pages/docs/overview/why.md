---
templateKey: doc
seoTitle: "Why the resource owner decides who her AI agents answer to"
title: Why the owner decides
description: What breaks when the party who owns a resource is not the party who configured access to it.
next:
  - title: The three parties
    to: /docs/overview/parties/
    blurb: Owner, requesting party, client — and why collapsing them costs you.
  - title: Architecture
    to: /docs/overview/architecture/
    blurb: Where each responsibility lives.
---

Almost every authorization system in production answers a question of the form
*"is this caller allowed?"*, where **allowed** means allowed by whoever operates
the service. That is correct for the workloads those systems were built for. The
operator holds the data, the operator sets the rules, and the caller is an
employee or an application the operator also runs.

Agents break the assumption quietly, because they still look like callers.

## The case the assumption misses

Alice banks at a brokerage. Her advisor Bob has an AI agent, and it would like
to read her holdings and, later, place a trade.

Three parties, and none of the usual shortcuts apply:

- **The brokerage** holds the assets and enforces access, but it is not the
  party whose permission matters. It can decide what its systems will do; it
  cannot decide what Alice consents to.
- **Bob** is not Alice. His agent has a legitimate reason to ask, and no
  standing to grant itself anything.
- **Alice** is the only party who can answer, and she is asleep.

An access control list at the brokerage can express *"Bob's firm may read
holdings"*. It cannot express *"Alice agreed, on these terms, for this purpose,
for the next fifteen minutes, and can take it back"* — because the brokerage
was never the one agreeing.

## What follows from taking that seriously

If the owner is the deciding party, three things stop being optional.

**She needs an authority of her own.** Something that holds her policy, answers
on her behalf, and that the resource server cannot overrule. In UMA this is the
authorization server, and the important property is not where it runs but whose
policy it expresses.

**The decision has to survive her absence.** Any design that requires her to be
online is a design that fails at 3am. Her policy has to be able to answer for
the ordinary cases and hold the sensitive ones until she can look.

**The terms have to be recorded.** If she is agreeing to something, there has to
be a durable statement of what was agreed, signed by both sides — otherwise
"she consented" is a claim nobody can check afterwards.

## Why this is not solved already

It is worth being precise about the adjacent work, because it is good work
aimed at different problems.

Policy engines decentralise **where** a decision runs. Agent identity protocols
establish **who** is asking. Enterprise agent-authorization schemes handle the
case where an organisation delegates to agents it operates — a real case, and
one where the operator genuinely is the deciding party.

None of them change **whose policy the decision expresses**. That is the axis
this profile moves along, and it is why the pages that follow are about parties
and boundaries rather than rule syntax. Where the two fit together is covered
in [Compare](/docs/overview/compare-policy-engines/).

## The shape of the answer

The owner writes terms once, against resources rather than against callers. An
agent she has never met arrives, is refused, is told where to negotiate, is
handed her terms, signs them, and is let in — or held until she taps. She is
not consulted about agents she has never heard of, because her policy already
covers the case.

That negotiation is [four beats long](/docs/overview/four-beats/).
