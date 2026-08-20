---
templateKey: doc
seoTitle: "First-party AI agents: when the owner activated the agent herself"
title: Her own agent
description: The case where the person asking and the person who owns the data are the same. Why it needs the same protocol anyway, and what changes when she activated the agent herself.
diagram: side-by-side
diagramCaption: The same grant, twice. One row differs — which operator vouched for the key, and whether she claimed that origin.
next:
  - title: Agent assurance
    to: /docs/overview/assurance/
    blurb: The check this depends on, and the rule it obeys.
  - title: The three parties
    to: /docs/overview/parties/
    blurb: Why her own agent is still not her.
---

Everything else here is written from somebody else's agent asking. This is the
other case: an agent Alice activated, reaching Alice's own resources.

It is not a curiosity. The UK Pensions Dashboards Programme's [technical
standards](https://www.pensionsdashboardsprogramme.org.uk/standards/technical-standards) describe a consent and authorisation service built on UMA
profiles, and Kantara's UMA working group published a [use-case report](https://kantara.atlassian.net/wiki/spaces/uma/pages/135659525)
for it in which the person first views the pensions discovered for her through
her own authorization server, with delegation to a financial adviser as a
separate later act.

The same machinery serves both, and the order is the adoption path: put
owner-authoritative authorization under your own users' agents first, and the
cross-principal case becomes a policy change rather than a rebuild.

## Her agent is still not her

The three parties are what make this work without a special case. Alice is the
owner. Alice is also the requesting party. The **requesting agent** is a third
thing, and it stays third: she is not at the keyboard, it holds its own key, it
signs her terms, and her policy answers every request it makes.

So nothing about the grant changes. Same four beats, same ticket, same dictated
terms, same proof-of-possession, same ledger row. A profile that needed a
branch here would be telling you its party model was wrong.

## How her authority knows

Two things have to hold: something she decided, and something her authority
checked.

**She claimed the origin.** The agent names an operator, the way any agent
does, and that operator's origin is one she marked as hers — the mirror of
shutting one out.

**That operator published this agent's key.** Her authority fetches the
directory and looks for the key that signed the contract, which is the same
check that reaches the top of the
[accountability axis](/docs/overview/assurance/).

Without the second, "this is my agent" would be a sentence an agent could say
about itself. A metadata document only proves it claims the URL it came from,
so pointing at one she publishes is free. Putting a key in her directory is
not.

The attestation carries more weight here than anywhere else in the profile,
because this is the only fact that makes a requirement **looser**. Everywhere
else, evidence can add friction and nothing more. `make first-party-check` asserts the attack
directly: an agent naming her origin, whose key she never published, gets
nothing.

## Claiming is not the same shape as blocking

She can already shut out an operator. The two actions read as opposites and are
not equivalent:

| | Direction | May rest on |
|---|---|---|
| Block an operator | restriction | what the agent claims about itself — a liar lies into a refusal |
| Claim an operator | relaxation | her decision, **and** a check her authority ran |

Claiming an origin she does not control buys nothing, because she cannot
publish keys there.

## What she can then write

One condition, and it names no agent:

```json
{"when": ["standing.first_party"], "then": "auto"}
```

Her authorization server will store that under `then: auto`, and still refuses
every requester-supplied condition there. It holds for the next agent she
activates, too.

Two things the rule cannot do.

**It cannot skip first contact.** An agent with no standing connection pends
whatever any rule says. She meets her own agent once, like anybody else's.

**It cannot beat a restriction.** Relaxations are applied first and
restrictions win, so a rule she wrote to tighten a tier still tightens it for
her own agent.

## Less friction, never more access

Her tiers are the ceiling either way. Before she writes the rule, a trade from
her own agent pends exactly like a trade from her advisor's. After she writes
it, the same rule on the same tier still asks her about his.

Disclaiming an origin takes effect on the next request and revokes nothing.
What the relaxation bought was fewer interruptions, not access she had not
already granted, so there is nothing to take back.

## Where to go next

- [Agent assurance](/docs/overview/assurance/) — the check this rests on
- [The three parties](/docs/overview/parties/) — why the agent is a third party even here
- [Revocation and the ledger](/docs/overview/revocation/) — ending it, for her agent or anyone's
