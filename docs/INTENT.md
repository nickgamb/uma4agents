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

## Which prohibitions can be refused

A prohibition is enforceable exactly when the thing it forbids has to cross the
owner's boundary to happen.

| Tier | Prohibition | Refused by |
|---|---|---|
| tier3 | `orders-beyond-approved-parameters` | `operation-binding` — the grant carries a digest of the parameters she approved |
| tier3 | `discretionary-reuse-of-authority` | `single-use` — the grant is consumed on use |
| tier1 | `retention-after-review`, `marketing`, `model-training` | nothing. They happen on the requester's disks after disclosure |

Neither mechanism is new. Both have been enforced since the grant loop was
built (`operation_mismatch`, `already_consumed` in `lib/uma4a_pep.py`); her
terms just never said so, which left every line reading as equally a matter of
trust.

`policy.enforced_prohibitions(tier)` derives the mapping from the tier's own
switches and both the proffered template and the published document carry it:

```json
"enforced": {"orders-beyond-approved-parameters": "operation-binding",
             "discretionary-reuse-of-authority": "single-use"}
```

Gated on the switch that turns the mechanism on, so a tier that forbids reuse
without setting `per_operation` is honestly reported as undertaken. It is
**not** echoed: the agent agrees to the prohibitions, not to her account of how
she keeps them.

It is also **not part of the published document**, and the reason is worth
stating because the first implementation got it wrong. `publish_terms` is
idempotent per `template_id` — a version's content never changes, which is what
lets an agreement signed last year still be checked against exactly the bytes
that were proffered. Anything that can change *without the terms changing* has
no business inside one, and her enforcement posture is exactly that: she can
flip `per_operation` without rewriting a word.

So it is annotated on the endpoint at read time, and only while that version is
the one in force. A superseded version carries no annotation, because labelling
it with today's posture is a different kind of wrong from saying nothing.

The mistake was invisible under the in-memory store, which starts empty and
republishes every version on each boot. It surfaced the first time the check
ran against Postgres, where the tier-3 document had been published days
earlier and the new field was silently dropped by `ON CONFLICT DO NOTHING` —
the idempotency doing exactly its job.

What remains unenforceable is genuinely so, and the dually-signed record is the
remedy path rather than the control.

## What is checked on every later call

Scope, expiry, the operation digest, and the key that must sign. The
enforcement point checks all four in a fixed order and spends a single-use
grant last. A grant issued for one order and presented against another is
refused, though the signature is valid and the token has not expired.

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

## Drift, from the side that can see it

The prevailing approach asks the requesting side whether its agent is behaving:
declare a task, watch the session, report a departure. That is coherent when
one party owns both the agent and the data. It does not survive the split this
profile exists for — it asks the owner to accept a report from infrastructure
she cannot inspect, about an agent belonging to the party producing the report.
There is nothing for her to check it against.

She does not need it. Every request that agent has ever made of her arrived at
her side. Her record holds what it promised, what she decided, what it called,
and which tier each call was made against, and drift is a shape in that record.

**Before the fact.** Rules read it while deciding, and name no agent:

| Condition | The shape it catches |
|---|---|
| `standing.first_at_tier` | reaching somewhere new |
| `standing.tiers_above:<n>` | breadth — how far across her resources it has spread |
| `standing.calls_above:<n>` | volume — how much it did with what it was given |
| `standing.denials_above:<n>` | persistence after she has already said no |

All four are in `OBSERVED_CONDITIONS`, over `UMA_AS_TRAJECTORY_WINDOW`. None can
be written into a relaxation; `validate_rules` refuses them under `then: auto`.

**After the fact.** `GET /owner/ledger?handle=…` is one agent's history: the
errand it declared, her decisions, and the calls it then made. Every `touched`
row carries the tier it was made against, resolved by the authority from the
grant the call was issued under — the enforcement point is never told either.

One entry cannot be attributed and that is a property rather than a gap: a
decline arrives at beat 2, before the requesting side has signed anything, so
there is no key and nothing to file it under.

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
