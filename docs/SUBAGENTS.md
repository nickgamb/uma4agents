# Sub-agent grants

An orchestrator that spawns workers is the ordinary shape of agent software.
The usual way to authorize those workers is to hand each one the parent's
token, and it is the one thing this profile will not do.

An agent here is individuated by its key. A worker handed the parent's key
simply *is* the parent — the owner cannot tell them apart, cannot revoke one,
and never agreed to any of them. A worker with its own key is a stranger, and
strangers are introduced to the owner from nothing, which costs her a decision
per worker.

This is the third case. An agent the owner already deals with may **introduce**
a sibling: the worker arrives with its own key and a signed statement that it
is a spawn of that agent. The statement confers nothing. Her authority checks
it against her own records, and then the worker negotiates its own terms, under
its own key, for its own grant.

**The task graph can be as deep as you like. The authority graph is flat.**

![Bob's domain holds the parent agent, the sub-agent and the operator key
directory that publishes both their keys, and the AAuth agent server that can
name the parent in the sub-agent's `act` claim instead. Alice's domain holds her
authorization
server and her portal. The sub-agent sends its own contract carrying it; her authority checks it
against her own records and returns a grant bound to the sub-agent's own key;
revoking the parent takes its sub-agents with it.](subagent-grants.svg)

The same sequence, with what is actually on the wire at each beat:

![Six numbered steps, each beside an editor window showing the real message: the
401 UMA challenge, the introduction's JWS claims, the connection record her
authority looks up, the sub-agent's own RPT with cnf bound to its own key, the
pend when it reaches a tier the lineage never had, and the revoke response
carrying the cascade counts.](subagent-grants-wire.svg)

Run it: `make subagent-check`, or `make k8s-subagent-check` in the cluster.

## What the worker actually skips

One thing: being introduced from nothing. Not the tiers, not the terms, not the
ceiling, and not the ledger.

| | Handed the parent's token | Introduced |
|---|---|---|
| Key | the parent's | its own |
| Identity to the owner | indistinguishable from the parent | a connection of its own |
| Grant | the parent's, reused | its own, negotiated |
| Revocable alone | no | yes |
| Ceiling | whatever the parent had | every tier's own rules |

## Approval belongs to the lineage

The unit the owner deals with is the fleet, not the key. She approved
transaction history for this orchestrator; it does not matter which member of
it asks.

That runs both ways, and the upward direction is the one people do not expect.
If a worker is the one that gets approved at a tier the parent never reached,
the parent stops being asked about that tier too. They are one relationship,
and she settled it once.

Revoking the member that earned a tier withdraws it from the lineage, which is
the only reading consistent with revocation meaning anything.

## The three things she can say

Per tier, in her own policy editor. The default is the first one and needs no
rule at all.

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

On a tier she marked ask-me, the second posture means clearing that switch and
carrying the ask in the rule — *ask me the first time this fleet wants to
trade*, rather than *always ask me* with an exception underneath. That is a
consequence of how rules compose rather than a special case: relaxations are
applied first, restrictions last, and restrictions win.

## Why neither condition may relax

`standing.introduced` and `standing.lineage_new_at_tier` are both in
`OBSERVED_CONDITIONS`. Neither can appear in a rule that grants
automatically, and `lib/test_policy.py` asserts it.

That is not an oversight. A fact may only lower a requirement if it traces to a
decision the owner personally made *and* the requesting side had no hand in
producing. Which agents join a lineage is chosen by the operator running them.
So the lineage posture is not written as "grant when the lineage is approved" —
it is written as a *narrower ask*, and the requesting side can only ever cause
that ask to remain.

## Two ways to prove a lineage

**A sibling signs for it.** The parent signs a compact JWS naming the worker's
key: `sub` is the worker's RFC 7638 thumbprint, `aud` is this authority, with a
short expiry. It rides the worker's own contract. Nothing in its claims is
trusted for identity — an `iss` naming the parent would have to be either
ignored or believed, and believing it would let any agent nominate another
agent's handle as its sponsor. The signing key is in the header, where the
signature checks it and the authority re-derives a handle to look up.

**Or the agent's issuer names it.** An identified agent already carries an
`aa-agent+jwt`, and AAuth uses RFC 8693's `act` claim — which it nests to
record a delegation chain — to name the entity a request was made on behalf of.
An agent server that sets `act.sub` to the spawning agent's identifier has
asserted the lineage itself, and AAuth's agent token is explicitly extensible
for exactly this. Nothing new is defined; the claim is read.

The second is the better attestation, and it is worth being clear why: a
sibling-signed introduction is the requesting side describing its own shape,
held up by the operator directory check beside it. An `act` claim is the
operator's own signing authority describing it. The first exists because a
pseudonymous agent has no issuer to speak for it.

AAuth reaches the same conclusion this profile does about what a downstream
call inherits: its call-chaining rules say the downstream authorization "is not
required to be a subset of the upstream scopes." A spawned agent is authorized
on its own terms in both models.

## What her authority checks

All of it itself, against her own records.

1. The signing key resolves to an **active** connection of hers.
2. That connection has a tier she **approved in person** — written only when
   she answers a pend herself, never when an organization administrator
   answers on her behalf. Without this, one automatic grant could seed an
   unbounded population of agents from a decision she never made.
3. The introducing connection **was not itself introduced**. This is an
   explicit check, not an emergent one: the moment she approves a worker at
   any tier it gains an approved tier and would otherwise satisfy (2).
4. The worker has **no revoked prior record**. A revoked agent goes back
   through first contact; otherwise revoking an agent would be undone by
   re-introducing it seconds later, and Revoke would be advisory.
5. The claim **names the key that signed the contract**, so a copied
   introduction admits nobody.
6. **One operator published both keys**, in a directory that operator controls
   and the agents do not — or, on the `act` path, one issuer signed both
   credentials.
7. Fan-out is under `UMA_AS_SUBAGENT_FANOUT` (default 3).

A document that does not hold up — wrong key, wrong authority, expired — is a
bad request, and answering it with a silent downgrade would leave a
well-behaved agent guessing why it was suddenly asked to wait. A document that
is fine but says nothing she acts on — an unapproved sponsor, another
operator's agent — is not the agent's mistake, and it falls back to first
contact, which is what would have happened with no introduction at all.

## Depth is one, and stays one

Check 3 is the whole mechanism. A worker cannot introduce, so there is no
chain, no recursion in the cascade, and no question about what a third hop
would inherit.

## Revocation

Revoking an agent revokes the ones it introduced, in the same action. The
parent goes first, so a negotiation arriving mid-cascade cannot find it still
active and be admitted behind the sweep.

Propagation costs one call and needs no action per link, because the
enforcement point introspects at her authority on every call: a worker's live
grants stop working on its next call rather than at their expiry. Her portal
reports the sub-agents that went with it, the way blocking an operator already
reports its own cascade.

## Attention

An introduced agent is counted against her attention budget, and its
per-operation pends are counted with it. Skipping first contact skips the
relationship question, not the queue discipline — first contact was the only
thing bounding how many questions one agent could put in front of her, and
removing it without this would let one approved orchestrator flood her queue.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `UMA_AS_SUBAGENT_FANOUT` | `3` | Live sub-agents one agent may have. A hard ceiling, not a policy rule: the rule governing sub-agents is hers to write, and this holds whether or not she has written one. |

## What is asserted

`make introduction-test` — 25 unit assertions over the document and the
decision, with the introduction minted by the client helper and verified by the
server module so the two implementations are checked against each other rather
than assumed to agree.

`make subagent-check` / `make k8s-subagent-check` — 21 assertions end to end:
admission without a second first contact, all three postures, the ceiling,
approval reaching the parent from a worker that earned it, every refusal, and
the revocation cascade including that a revoked worker cannot be re-introduced
by its sponsor.
