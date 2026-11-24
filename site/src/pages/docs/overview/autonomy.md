---
templateKey: doc
seoTitle: "Earned autonomy for AI agents: the Agentic Trust Framework, profiled for a second party"
title: Earned autonomy
description: How much an agent the owner has already met may do without asking her — the CSA Agentic Trust Framework's maturity ladder, held twice, because under UMA there are two parties where ATF has one.
next:
  - title: Agent assurance
    to: /docs/overview/assurance/
    blurb: What can be known about an agent before she has met it.
  - title: Let the owner write her own policy
    to: /docs/guides/owner-policy/
    blurb: Adding the earned-autonomy preset to a tier is one of the rules she can write.
---

[Assurance](/docs/overview/assurance/) answers what the owner's authority can
establish about an agent it has never met. This page is about the question
that comes after: **once she has met it, how much may it do without asking
her?**

The vocabulary is the Cloud Security Alliance's
[Agentic Trust Framework](https://github.com/massivescale-ai/agentic-trust-framework)
(ATF). It has four maturity levels, and an agent earns its
way up them: an **intern** observes and reports, a **junior** may act once a
person approves, a **senior** acts and a person is told, and a **principal**
acts on its own within a domain.

## Two ladders, because there are two parties

ATF describes one ladder, held by the organization that deploys the agent.
Inside one enterprise that is the whole story, because the party governing the
agent and the party whose systems it reaches are the same party.

UMA's whole contribution is that they are not. The firm running the agent is
the requesting side, and the person whose things it asks for is the owner. So
**every agent stands on two ladders at once**:

| | The operator's ladder | The owner's ladder |
|---|---|---|
| Kept by | the firm running the agent | her authorization server |
| Published as | an `atf` member in the operator's client metadata document | nothing: it is her record |
| Moved by | the firm's own ATF governance | **her alone**, one rung at a time, upwards. She may lower it any distance, and revoking the agent resets it |
| Can make her rules | **stricter only** | easier or stricter |
| A stranger starts at | wherever its firm says | intern, always |

Nothing adds the two together, for the same reason assurance keeps its three
axes apart. A combined level is how a firm's confidence in its own agent would
come to stand in for hers.

> **Whichever ladder stands lower governs. Nobody's promotion reaches anybody
> else's resources. A firm's demotion reaches every owner on the agent's next
> request.**

## Her ladder

Every agent is an intern with her: a stranger, a connection she has just
admitted, and an agent she revoked and later let back in. ATF says the same
thing ("initial maturity level: always intern"), and U4A arrives there
independently, because a level another party granted is not standing with her.

From there:

- **Only she raises it.** No administrator, operator or automatic process can.
  That is what lets her level relax one of her rules, which is otherwise
  something only her own decisions may do. The level rises only by her hand,
  so whatever it reads is at or below a level she granted.
- **One rung at a time.** ATF's promotion gates are per rung, and time at a
  rung is the only evidence she will ever have of how the agent behaves there.
- **Any distance down, at once.** A restriction never needs an argument.
- **A stale screen cannot undo a newer change.** Her portal sends the level it
  showed her, and the change lands only if the agent still stands there.

Before she promotes, her portal shows what her own record says about ATF's
gates: how long the agent has been at this rung, how many of the requests it
put to her she approved, and whether her policy refused anything on its own
merits. A refusal because of the agent's level is the ladder working, not an
incident. Security validation and business value are about the firm's programme
rather than this agent with her, and are labelled as the firm's, or an
evaluator's, to show. Governance sign-off is
her pressing the button.

## The firm's ladder

The firm says where it has put its agent, in the metadata document the agent
already names:

```json
"atf": {"version": "0.9.0", "maturity_level": "senior",
        "conformance": "compatible", "statement_uri": "https://firm.example/atf"}
```

Her authority reads it, and it can only make her rules stricter. That makes it
safe to read without verifying it: a firm that overstates its agent gains
nothing, and one that understates it costs only itself. **A lie can only cost
the liar friction**, as with assurance. A firm that says nothing is not saying
its agent is an intern; she can require a declaration if she wants one.

A firm can also say its programme is **ATF Certified**, which means audited by
an independent party. Her authority shows that as a claim and credits nothing
for it. An outside party standing behind the firm is exactly what
[assurance](/docs/overview/assurance/) says is missing above accountability
level 2. Crediting it needs somewhere her authority can ask, and that does not
exist yet.

## The profile: ATF as her rules

There is no new machinery in how the levels act. The profile is eight rules
over conditions she could already write, plus the
[consequence](/docs/overview/consequence/) the resource declares for each
operation. It is published as a preset she adds to a tier:

| With her | A read | An act that can be compensated | An act that cannot be undone |
|---|---|---|---|
| intern | as the tier says | refused | refused |
| junior | as the tier says | asked | asked |
| senior | granted | granted, and she is told | asked |
| principal | granted | granted, and she is told | granted, and she is told |

The firm's ladder is read the same way and can only make a cell stricter. An
agent its own firm still calls an intern does not act on her resources however
far she has promoted it.

## See it run

`make autonomy-check` puts two agents from one firm through both ladders. One is
an advisor its firm calls a principal, and the other a research assistant its
firm calls an intern. The advisor's first trade is refused, because it is an
intern with her. She promotes it one rung at a time until it trades without
asking. The research assistant stays out of her trades even after she promotes
it to principal, because its own firm has not. Revoking the advisor makes it an
intern again.

`make fixture-autonomy` runs the same check with no identity provider and no
gateway. The normative text is
[§9 of the policy draft](/spec/draft-gamb-uma4agents-policy-00.html). Its
appendix judges each of ATF's 25 requirements on the owner's side of the
exchange: 9 met, 8 partly met, 5 that belong to the operator, and 3 gaps (rate
limiting, a circuit breaker, and rollback).
