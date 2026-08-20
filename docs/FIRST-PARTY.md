# Her own agent

Everything else in this lab is written from somebody else's agent asking. This
is the case where the requesting party is Alice herself — an agent she
activated, reaching her own resources.

It is not a curiosity. The UK Pensions Dashboards Programme's [technical
standards](https://www.pensionsdashboardsprogramme.org.uk/standards/technical-standards) describe a consent and authorisation service built on UMA
profiles, and Kantara's own UMA working group published a [use-case report](https://kantara.atlassian.net/wiki/spaces/uma/pages/135659525)
for it in which the person first views the pensions discovered for her through
her authorization server — delegating access to a financial adviser is a
separate, later act.

The same machinery serves both, and the order is the adoption path: an
organisation can put owner-authoritative authorization under its own users'
agents first, and reach the cross-principal case by writing policy rather than
by rebuilding.

Run it: `make first-party-check`, or `make k8s-first-party-check` in the
cluster. As a demo act: `make demo-all ACT=first-party SIM=1`.

## RO == RqP, and the agent is still a third thing

The three-party model is what makes this work without a special case. Alice's
agent is not Alice. She is not at the keyboard, it holds its own key, it signs
her terms, and her policy governs every request it makes. Everything the
profile does for a stranger's agent it does here for the same reasons.

So the grant does not change. Same four beats, same ticket, same dictated
terms, same proof-of-possession, same ledger. `make first-party-check` exists
to demonstrate that rather than to assert it.

## How her authority knows

An agent is first-party when **both** of these hold — one her decision, one a
check her authority ran:

| | |
|---|---|
| the operator it names is an origin she claimed | `POST /owner/operators/claim`, stored in `owned_operators` |
| that operator published *this agent's key* | `operator_published_key`, the same check that reaches accountability level 2 |

The attestation is not a refinement on the claim. A Client ID Metadata Document
proves only that it claims the URL it was fetched from, so any agent may point
at one she publishes and reach level 1. Only she can put a key in her
directory. Without
the attestation, "this is my agent" would be a sentence an agent could say
about itself — and this is the one fact in the profile that makes a
requirement *looser*, so it is the one place a claim can never be enough.

`make first-party-check` asserts exactly that case: an agent naming her origin,
whose key she never published, gets nothing.

## Claiming is the mirror of blocking

She can already shut out an operator, and the two actions are deliberately not
symmetric in what they may rest on:

| | Direction | May rest on |
|---|---|---|
| Block an operator | restriction | the agent's own unverified claim — a liar lies into a refusal |
| Claim an operator | relaxation | her decision **and** a check her authority ran |

Claiming an origin she does not control buys nothing at all, because she cannot
publish keys there. That is worth knowing before reading the endpoint as
dangerous.

## What her policy may then say

One condition, no argument, and it is the only relaxing condition in the
vocabulary that is not a fact about one agent's history with her:

```json
{"when": ["standing.first_party"], "then": "auto"}
```

It sits in `RELAXING_CONDITIONS`, so `validate_rules` will store it under
`then: auto` — and still refuses every requester-supplied condition there. It
names no agent, so it holds for the next agent she activates too.

Two things it cannot do.

**It cannot skip first contact.** `if needs_connection or
needs_operation_approval` is evaluated after policy, so an agent with no
standing connection pends whatever any rule says. She meets her own agent once,
like anybody else's.

**It cannot beat a restriction.** `evaluate` applies relaxations first and
restrictions last, and restrictions win. A rule she wrote to tighten a tier
still tightens it for her own agent.

## Being hers buys less friction, never more access

Her tiers are the ceiling either way. A first-party agent on a tier she
reserved is asked exactly like anybody else's until she writes the rule, and
the rule only ever lifts the tier's own baseline. The demo act shows all three
states in order: no rule and she is asked; the rule and she is not; the same
rule and the same tier with Bob's agent, which is asked again.

Disclaiming takes effect on the next request and revokes nothing. What the
relaxation bought was fewer interruptions, not access she had not already
granted, so there is nothing to claw back.

## Her operator presence

`clients/agent-operator/` holds no authoritative state and is parameterised by
origin, which is what makes running more than one correct. The lab runs two:
Bob's firm at `agent.uma.lab`, and Alice's own at `alice-agent.uma.lab`. In
Kubernetes hers lives in her namespace, which is the point rather than an
accident of layout.

## See also

- [ASSURANCE.md](ASSURANCE.md) — the accountability axis this depends on, and
  the asymmetry all of it obeys
- [INTENT.md](INTENT.md) — what an agent may say about itself, and what that
  can never buy
- [FINDINGS.md](../FINDINGS.md) — why a specification should not carve this out
  as a special case
