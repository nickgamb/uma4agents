# The two intents

A grant has two parties who want something, and the word *intent* is doing a
different job for each.

Alice states, before any agent exists, what she will accept being done with her
things and on what conditions. An agent states, per request, what it proposes to
do and — if it has one — the mandate it is doing it under. The negotiation is
the only place both are in hand at once, and what it does there is narrow on
purpose.

Run it: `make intent-check`, or `make k8s-intent-check` in the cluster. Unit
tests, needing nothing running: `make rules-test` and `make store-test`.

## What each side contributes

| | Written by | When | Where it lives |
|---|---|---|---|
| Her tier's `terms` | Alice | before any agent asks | `services/uma-as/policy.py`, served at `GET /terms/{template_id}` |
| The signed echo | the agent | per request | the agreement JWS, hashed into the RPT and the receipt |
| `operation` | the agent | per request, on per-operation tiers | the RPT's `operation` claim, checked at every call |
| `reason` | the agent | per request, optional | recorded and shown to her; never compared to anything |
| `mission` | the agent, citing its operator | per request, optional | an AAuth mission reference, recorded, never dereferenced |

Everything above `operation` in an agreement is hers, repeated back. That is the
whole of the echo, and it is why beat 3 is a commitment rather than a proposal.

## What the echo is checked against

`verify_contract` compares the agreement to the template it proffered, field by
field. In order, and each one ends the negotiation:

| Check | Fails when |
|---|---|
| `nonce`, `family`, `template_id`, `terms_uri` | it names different terms, or a different negotiation |
| `purpose` | the echoed purpose is not the dictated one |
| `prohibited` | the echoed list is not a **superset** of hers |
| `expires_in` | it asks for longer than the tier allows |
| `operation` | a per-operation tier gets a contract naming no act |
| `reason` | it is not a string, or is over `UMA_AS_MAX_REASON` bytes |
| `mission` | it is not an object with an https `approver` and a content hash |

The prohibitions check is a subset test rather than an equality test: an agent
may bind itself to more than she asked, never less. A valid signature over
weakened terms is what an adversarial agent would send, and it is the case the
check exists for.

Note what is absent. Her authority does not read the agent's stated purpose and
judge whether it is plausible; there is no natural-language comparison anywhere
in the grant. Adding one would make the same request answerable two ways, which
is the property `make flow-check` exists to protect.

## What survives to the door

Of the things she stated, two are testable on every later call and two are not.

**Enforced.** The grant carries the scope and expiry, the digest of the exact
operation, and the key that must sign the request. `lib/uma4a_pep.py` checks all
three in a fixed order and spends a single-use grant last. A grant issued for
one order and presented against another is refused, though the signature is
valid and the token has not expired.

**Recorded.** Purpose and prohibitions are prose about the future. Nothing at
the wire level stops an agent that agreed not to retain data from retaining it,
and no protocol will. What they get instead is a dually-signed record: the
receipt embeds the complete agent-signed agreement and counter-signs it, and the
ledger holds a `promised` row carrying the purpose, the prohibitions, the terms
URI and the hash.

That is a weaker guarantee than enforcement and a stronger one than a consent
checkbox. The signature buys attribution, not prevention.

## What the agent says it is for

`reason` is free text, capped, and the only claim in the agreement the
requesting side authors from nothing. It is bounded because it is stored and
displayed. It is not parsed, scored, or compared.

Her policy may do exactly one thing with it:

```json
{"when": ["request.reason_absent"], "then": "ask"}
```

It sits in `ASSURANCE_CONDITIONS`, so it may only tighten — `validate_rules`
refuses to store it under `then: auto`. Silence costs an agent friction, and so
does a lie, which is the same bargain every requester-supplied claim makes here.

Because it is authored by the counterparty and rendered on the owner's surface,
every display path escapes it. The authority stores what arrived, verbatim; the
portal is where it stops being markup.

## The mandate behind the request

An [AAuth mission](../aauth/upstream/aauth-person-server/MISSIONS.md) is the
durable record of a requesting party setting their agent a task: approved at
that party's own person server, named by content hash. An agreement may cite
one in AAuth's own shape, so nothing here invents a field:

```json
"mission": {"approver": "https://ps.example", "s256": "…"}
```

Those are the fields the `AAuth-Mission` request header already carries.

**It is a request fact, not an assurance axis, and the difference is the
point.** Assurance means what her authority verified for itself. Verifying a
citation means dereferencing it at the approver, and AAuth serves
`GET /missions/{s256}` to administrators only — a relying party in another
trust domain has nothing to fetch. So from here, an agent that cites a real
mission and one that invents a hash are the same agent, and awarding a level
for the difference would be a comment about the call path rather than a check.

It sits beside `reason`, which it is currently no stronger than, and her policy
may notice its absence:

```json
{"when": ["request.mission_absent"], "then": "ask"}
```

If a projection a relying party may read ever exists, a *verified* mandate
becomes a fourth axis — who runs an agent and who set it this task are
different questions, and an agent can answer either without answering the
other. Until then the honest position is the smaller one.

Containment is not hers to check in any case. AAuth is explicit that the
protocol gives correlation rather than containment, and containment lives at
the approver: whether this request falls inside Bob's mandate is Bob's person
server's question. What she could establish, given something to dereference,
is that somebody on the other side is running a mandate at all.

## Drift, and the two places it shows

**Before the fact.** Rules face the requesting side without naming an agent. The
shipped policy uses one for exactly this:

```json
{"when": ["standing.first_at_tier"], "then": "ask"}
```

Being admitted is not being admitted *here*. Two more read her own record over
`UMA_AS_TRAJECTORY_WINDOW`: `standing.denials_above:<n>` and
`standing.tiers_above:<n>` — repetition and breadth. Both are in
`OBSERVED_CONDITIONS`, so neither can be written into a relaxation. "She has
denied you repeatedly, so grant automatically" is not a storable sentence.

**After the fact.** Every ledger entry names the agent it was about, so one
agent's promises, her decisions, and what it went on to touch are a single list
— `GET /owner/ledger?handle=…`, and the Connected agents tab in her portal.
Drift is the distance between the promised row and the touched rows.

One entry cannot be attributed and that is a property rather than a gap: a
decline arrives at beat 2, before the requesting side has signed anything, so
there is no key and nothing to file it under. Her record says her terms were
refused, which is true and is all that is knowable.

### Why the trajectory count is not one of the indivisible operations

Everything else in `services/uma-as/store.py` is indivisible because a wrong
answer is an access-control failure. A trajectory count is not that. It only
ever tightens, and it is monotone inside its window, so a replica reading one
write stale behaves exactly as if the request had arrived a moment earlier — an
ordering the system already permits.

The question that separates the two classes, worth asking of any new policy
input: **can a stale read widen access beyond what a differently-timed arrival
would have?** If it can, it belongs with the single-use operations instead.

## What this does not do

- **Purpose is unenforceable.** Stating it buys a record that can be produced
  afterwards, not a control.
- **Intent is per call, not per session.** The grant authorizes an operation. A
  session-scoped intent that every tool call is checked against is a
  requester-side control and composes with this rather than being supplied by it.
- **She cannot express intent about the agent's other work.** Her terms cover
  her resources. What the agent does elsewhere is its operator's to govern.

## See also

- [ASSURANCE.md](ASSURANCE.md) — the three axes her authority verifies, and
  the asymmetry these facts share with them
- [PROTOCOL.md](PROTOCOL.md) — the agreement on the wire
- [FINDINGS.md](../FINDINGS.md) — what this produced for the people writing the
  specifications
