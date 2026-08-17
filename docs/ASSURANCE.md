# Agent assurance, and the cost of her attention

Alice's tiers say what may be asked of her resources. They name no agent, which
is what lets one policy hold for an unbounded number of strangers.

The question that keeps coming back is whether she can say anything about the
*asking* side without giving that up — and the honest fallback, an allow-list
of agents she trusts, is an ACL wearing a new hat. This is the alternative.

Run it: `make assurance-check`. Unit tests: `make policy-test`.

## It is assurance, so it is called assurance

And deliberately not an assurance **level**. Identity assurance spent a decade
on one ordinal scale — LOA 1–4 — before NIST SP 800-63-3 pulled it apart into
IAL, AAL and FAL. The decomposition happened because a single scale forces
unrelated evidence into one order, so a deployment needing strong credentials
gets pushed into identity proofing it never wanted, and a strong showing on one
axis silently compensates for a weak one on another.

An "Agent Assurance Level 1–4" would repeat that, in a domain where the axes
are *less* correlated than they were for people. An agent can be perfectly
recognisable and completely unaccountable. So there are three axes, they are
never added up, and **there is deliberately no composite score** — a composite
is precisely the mechanism by which strong binding excuses an unknown operator.

| Axis | The question | What the lab can produce |
|---|---|---|
| `binding` | Can this request be tied to a key she will recognise next time? | 1 always — the grant requires an RFC 9421 signature and a PoP key. It is on the list so a profile that relaxes it has to say so. |
| `provenance` | Can her authority check where the credential came from? | 0 for a bare key. 1 for an `aa-agent+jwt` whose signature verified against its issuer's published keys. |
| `accountability` | Is anyone named and reachable standing behind it? | 0 for none. 1 for a CIMD that resolved and claims the URL it was fetched from. **2 is defined and never emitted** — see below. |

Assurance is always *derived from what this server verified*. An agent cannot
claim a level. That was already the rule for client metadata — "resolved and
shown, never trusted" — and this generalises it.

## Assurance is what they can show; standing is what she has seen

Her own record of an agent is kept separate and given a different name:
**standing**. Whether she has met it, how long ago, whether she has ever
revoked it, whether it has been granted at *this* tier before.

The distinction is the safety rule, and it is the whole design:

> **Assurance may only tighten a requirement. Only standing may relax one.**

That is not a rule bolted on afterwards; it falls out of who produced the
evidence. Axes 1–3 are attested by the requesting side or by an issuer she did
not choose. Standing was produced by her own authority, and is the only
evidence here she has a reason to believe unconditionally.

The consequence is what makes any of this safe to build:

> **A lie can only cost the liar friction.**

Which is why her policy can afford to read a self-asserted operator name at
all. `make assurance-check` demonstrates it: an agent presenting metadata that
does not resolve is admitted exactly like any stranger, and gains nothing on
the second request either.

## What she writes

One list per tier. Conjunction inside a rule, disjunction across rules, and
nothing else — no negation, no nesting, no expressions. `policy.py` stays a
legible document rather than becoming a policy language.

```json
"rules": [
  {"when": ["assurance.accountability_below:1"], "then": "ask"},
  {"when": ["standing.age_above:90d", "standing.never_revoked"], "then": "auto"}
]
```

`then` is `auto`, `ask` or `refuse`. Relaxations are applied first and
restrictions last, so no combination of matched rules can land more permissive
than the strictest thing that matched. `then: "auto"` is the only requirement
that can loosen, and `validate_rules` **refuses to store** one whose conditions
touch anything but standing — rejected at the owner API rather than ignored at
evaluation time, because a control that is silently inert is worse than one
that was never claimed.

Note what the vocabulary does *not* contain: no issuer, no `cimd`, no
thumbprint, no `agent_token`. `accountability_below:1` says "nobody I can
check is standing behind this", not "no CIMD document". Swap the mechanism
tomorrow and her policy is unchanged. That is the flow property surviving
contact with client-facing policy — see [FLOW.md](FLOW.md).

## What ships in her default policy

| Tier | Rule | Why |
|---|---|---|
| Holdings | `accountability_below:1 → ask` | Nobody named behind it, nobody to complain to. It still gets to negotiate; it just does not get to do so quietly. |
| Transactions | `standing.first_at_tier → ask` | See below. |
| Trades | *(none)* | Deliberately. |

The trades tier is the only one where a relaxation could do anything, and "we
have known each other a while" is not a reason to stop asking about money. The
mechanism exists and her default policy declines to use it; a deployment that
disagrees has to write it out deliberately.

**The transactions rule fixes a real over-grant.** Approving a first contact
used to admit an agent to everything below the ask-me line — so an agent she
let in to look at her holdings could read her transaction history and cost
basis without ever asking again. She approved a *holdings* request and got a
broader relationship than she was shown. `standing.first_at_tier` makes the
first request at each new tier come back to her. Note that the fix is a
predicate, not a list of tiers per agent: an ACL would have worked and would
have been the wrong shape.

## What stops her being spammed

Nothing above does. Keys are free, so anyone can mint ten thousand of them and
put ten thousand first-contact requests in front of her. Her attention is the
scarcest resource in the system and, until this, the only one with no limit on
it — which means the property that makes U4A worth having (she decides) was
also its denial-of-service surface.

A rate limit per key is theatre. Per source address is the wrong layer. The
thing that actually matters is not *how fast* strangers arrive but **how much
of her queue they can occupy at once**, so the control is a depth limit:

> At most `UMA_AS_PEND_BUDGET` requests from agents she has no standing with
> may be waiting for her at any moment. Past that they are refused, with a
> reason, rather than queued.

Three properties make this the right shape:

- **It is self-healing.** Every request she answers frees a slot. The cap is on
  the backlog, never on the relationship.
- **A flood cannot crowd out the people she knows.** An agent with standing is
  never counted and never refused for budget. The failure mode of an attack is
  that strangers are turned away — not that Bob's agent stops working. That is
  the assertion at the end of `make assurance-check`.
- **It needs no new state.** The outstanding count is a read of the pending
  queue her portal already lists.

The refusal is honest rather than silent: `429`, and the agent is told the
owner is not accepting new requests right now, which is true, and that it may
come back. Silence would be indistinguishable from a broken server and would
push a legitimate agent into retrying — the behaviour the cap exists to
prevent.

Setting the budget to `0` makes her authority invitation-only: no agent without
standing reaches her at all. That is a legitimate posture and it is one
environment variable. It is not the default, because the whole argument of this
profile is that a stranger can negotiate.

## What is not here, and why

**Accountability level 2 is never emitted.** A CIMD is fetched over TLS and
checked for self-consistency; there is no signature over the document and no
third party attesting anything. "This firm says it operates this agent" is the
whole of the evidence. The level exists so a deployment that *does* have an
attestation has somewhere to put it, and so this does not quietly imply the lab
checked something it did not.

**No accreditation, no registry, no trust framework.** Saying "agents of type
X" requires somebody authoritative about what type an agent is. UMA deliberately
punted on that; GNAP has been arguing about it for years. Choosing a side would
be a bigger claim than this lab has evidence for. The asymmetry is what lets us
avoid choosing: because assurance can only add friction, it does not matter very
much who is asserting it.

**No relaxation on anything the agent influences**, including its issuer.
Verifying *who signed* a credential is not the same as trusting *what they say*
about the agent, and letting an issuer's assertion lower a requirement delegates
Alice's judgement to a party she never chose.

**De-escalation deserves more scrutiny than escalation.** "Clean history" is a
judgement about the past, and her ledger is only as good as what the resource
server reported. The escalation half is safe under every threat model we can
construct. The loosening half needs a real argument, which is why nothing in the
shipped policy uses it.

## See also

- [FLOW.md](FLOW.md) — why her policy still names no identity system
- [PROTOCOL.md](PROTOCOL.md) — the wire contract this decides within
- [FINDINGS.md](../FINDINGS.md) — recommendations 13 and 14
- `services/uma-as/assurance.py`, `services/uma-as/policy.py`
