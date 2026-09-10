---
templateKey: doc
title: Sub-agent grants
seoTitle: "Sub-agent delegation without passing a token or a key"
description: An agent spawns workers. None of them carry its key, none of them inherit its access, and each one is authorized on its own terms.
next:
  - title: Her own agent
    to: /docs/overview/first-party/
    blurb: The other case where a fleet is involved, and the owner runs it.
  - title: Revocation and the ledger
    to: /docs/overview/revocation/
    blurb: What taking it back actually does, and how fast.
---

An orchestrator that spawns workers is the ordinary shape of agent software.
The usual way to authorize those workers is to hand each one the parent's
token, and it is the one thing this profile will not do.

An agent here is individuated by its key. A worker handed the parent's key
simply *is* the parent — indistinguishable in the owner's records, not
separately revocable, and never something she agreed to. A worker with its own
key is a stranger, and strangers are introduced from nothing, which costs her a
decision per worker.

So there is a third case. An agent she already deals with may **introduce** a
sibling: the worker arrives with its own key and a signed statement that it is
a spawn of that agent. The statement confers nothing. Her authority checks it
against her own records, and then the worker negotiates its own terms, under
its own key, for its own grant.

The task graph can be as deep as you like. The authority graph is flat.

![Bob's domain holds the parent agent, the sub-agent, and the operator key
directory that publishes both their keys where neither agent can write to it.
Alice's domain holds her authorization server and her portal. The parent signs
an introduction naming the sub-agent's key, which confers no tier or scope — or
the operator's AAuth agent server names the parent in the sub-agent's `act`
claim instead; the
sub-agent sends its own contract carrying it; her authority checks it against
her own records and returns a grant bound to the sub-agent's own key; revoking
the parent takes its sub-agents with it in the same action.](/img/docs/subagent-grants.svg)

The same sequence, with what is actually on the wire at each beat:

![Six numbered steps, each beside an editor window showing the real message: the
401 UMA challenge naming her authority and a ticket, the introduction's JWS
claims, the connection record her authority looks up, the sub-agent's own RPT
with cnf bound to its own key rather than the parent's, the pend it gets when it
reaches a tier the lineage never had, and the revoke response carrying the
cascade counts.](/img/docs/subagent-grants-wire.svg)

## What the worker skips

One thing: being introduced from nothing. Not the tiers, not the terms, not the
ceiling, not the ledger.

| | Handed the parent's token | Introduced |
|---|---|---|
| Key | the parent's | its own |
| In her records | indistinguishable from the parent | a connection of its own |
| Grant | the parent's, reused | its own, negotiated |
| Revocable alone | no | yes |
| Ceiling | whatever the parent had | every tier's own rules |

## Approval belongs to the lineage

The unit she deals with is the fleet, not the key. She approved transaction
history for this orchestrator; which member of it asks is not a second
question.

That runs both ways, and the upward direction is the one people do not expect.
If a worker is the one approved at a tier the parent never reached, the parent
stops being asked about that tier too. They are one relationship, and she
settled it once. Revoking the member that earned a tier withdraws it from the
lineage — the only reading consistent with revocation meaning anything.

## The three things she can say

Per tier, in her own editor. The default is the first and needs no rule.

**Per-agent.** Every agent is asked about once per tier, workers included.

```
When:  it is the first time this agent has asked at this tier
Then:  ask me
```

**Lineage-wide.** Ask once per fleet instead of once per agent.

```
When:  it is the first time this agent has asked at this tier
  and  no agent in this lineage has been approved for this tier
Then:  ask me
```

**Always ask about sub-agents.** Stricter than the default.

```
When:  the agent was introduced by another agent
Then:  ask me
```

Note what the second one is not. It is not "grant when the lineage is
approved" — it is the ask she already had, made narrower. That distinction is
the reason it can exist at all.

A fact may only *lower* a requirement if it traces to a decision she personally
made and the requesting side had no hand in producing. Which agents join a
lineage is chosen by the operator running them. So both new conditions are
observed rather than relaxing, neither can appear in a rule that grants
automatically, and the test suite asserts it. Written as a narrowed
restriction, the requesting side can only ever cause the ask to remain.

## Two ways to prove a lineage

**A sibling signs for it.** The parent signs a compact JWS naming the worker's
key — `sub` is the worker's RFC 7638 thumbprint, `aud` is this authority, with
a short expiry — and it rides the worker's own contract. Nothing in its claims
is trusted for identity. An `iss` naming the parent would have to be either
ignored or believed, and believing it would let any agent nominate another
agent's handle as its sponsor, so the signing key travels in the header where
the signature checks it.

**Or the agent's issuer names it.** An identified agent already carries an
`aa-agent+jwt`, and AAuth uses RFC 8693's `act` claim — which it nests to
record a delegation chain — to name the entity a request was made on behalf of.
An agent server that sets `act.sub` to the spawning agent has asserted the
lineage itself, and AAuth's agent token is explicitly extensible for this.
Nothing new is defined; the claim is read.

The second is the better attestation. A sibling-signed introduction is the
requesting side describing its own shape; an `act` claim is the operator's own
signing authority describing it. The first exists because a pseudonymous agent
has no issuer to speak for it.

AAuth reaches the same conclusion this profile does about what a downstream
call inherits: its call-chaining rules say the downstream authorization "is not
required to be a subset of the upstream scopes." A spawned agent is authorized
on its own terms in both models.

## What her authority checks

All of it itself.

1. The signing key resolves to an **active** connection of hers.
2. That connection has a tier she **approved in person** — never one an
   organization administrator approved on her behalf. Without this, one
   automatic grant could seed a population of agents from a decision she never
   made.
3. The introducing connection **was not itself introduced**. Explicit, not
   emergent: the moment she approves a worker at any tier it would otherwise
   satisfy the check above.
4. The worker has **no revoked prior record**. Otherwise revoking an agent
   would be undone by re-introducing it seconds later.
5. The claim **names the key that signed the contract**, so a copied
   introduction admits nobody.
6. **One operator published both keys**, in a directory that operator controls
   and the agents do not — or one issuer signed both credentials.
7. Fan-out is under a hard ceiling, and sub-agents count against her attention
   budget. Skipping first contact skips the relationship question, not the
   queue discipline.

A document that does not hold up is a bad request. A document that is fine but
says nothing she acts on falls back to first contact — which is what would have
happened with no introduction at all.

## Revoking the parent

Revoking an agent revokes the ones it introduced, in the same action. The
parent goes first, so a negotiation arriving mid-cascade cannot find it still
active and be admitted behind the sweep. There is no recursion to do, because
depth is one.

Propagation costs one call and needs no action per link: the enforcement point
introspects at her authority on every call, so a worker's live grants stop
working on its next call rather than at their expiry.
