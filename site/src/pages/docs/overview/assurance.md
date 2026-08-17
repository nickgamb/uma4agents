---
templateKey: doc
title: Agent assurance
description: Policy that faces the requesting agent without naming one — three axes of evidence, the asymmetry that makes them safe to use, and a limit on how much of the owner's attention a stranger can spend.
next:
  - title: Identity stays where it is
    to: /docs/overview/flow/
    blurb: Why her policy still names no identity system.
  - title: Revocation and the ledger
    to: /docs/overview/revocation/
    blurb: The other thing she can do about one agent in particular.
---

![Agent assurance starts at zero. Five steps, left to right, each one a check the owner's authority performed itself: nothing yet, with all three axes at zero, for an agent she has never seen; the agreement's signature verified against a key she can name (binding 1); the credential's issuer verified against its published keys (provenance 1); an operator metadata document resolved and self-consistent (accountability 1); and that operator's own key directory holding this very key, which the agent could not have added (accountability 2). Below, one real rule from her holdings tier — when accountability is below 1, ask — read against each step: it fires at the first three and is silent at the last two. It reads one axis, so binding and provenance move without changing its answer, and at the top the rule has simply stopped firing rather than granted anything her tier did not already allow.](/img/docs/assurance.svg)

The owner's tiers say what may be asked of her resources, and name no agent.
That is what lets one policy hold for an unbounded number of strangers.

So the question keeps coming back: can she say anything about the *asking*
side without giving that up? The honest fallback — a list of agents she
trusts — is an access-control list wearing a new hat. This is the alternative.

## It is assurance, so call it assurance

And deliberately not an assurance **level**.

Identity assurance already ran that experiment. LOA 1–4 was a single ordinal
scale until NIST SP 800-63-3 pulled it apart into three independent axes,
because one scale forces unrelated evidence into one order — so a deployment
that needs strong credentials gets pushed into identity proofing it never
wanted, and a strong showing on one axis silently compensates for a weak one
on another.

Agents make that worse rather than better. An agent can be perfectly
recognisable and completely unaccountable. So there are three axes, and
**no composite score** — a composite is precisely the mechanism by which
strong key binding excuses an unknown operator.

| Axis | The question it answers |
|---|---|
| `binding` | Can this request be tied to a key the authority will recognise next time? |
| `provenance` | Can the authority check where the agent's credential came from? |
| `accountability` | Is anyone named and reachable standing behind it? |

Levels are always **derived from what the authorization server verified**. An
agent cannot claim one.

And every axis starts at 0, raised only by a check that ran and passed in this
negotiation. Nothing is granted by construction or by the shape of the call
path — an unresolvable claim scores what no claim scores, and a check that did
not run counts as one that failed.

## Assurance is what they can show; standing is what she has seen

Her own record of an agent is kept separate, and given a different name:
**standing**. Has she met it, how long ago, has she ever revoked it, has it
been granted at *this* tier before.

The distinction is the safety rule:

> Assurance may only **tighten** a requirement. Only standing may **relax** one.

Worth stating the direction plainly, because the rule is easy to read backwards:
**strong assurance never makes a request stricter.** What adds friction is a
*gap* — no operator named, a key with nothing to check it against. An agent that
can show more is not penalised for it; it simply avoids friction that showing
less would have cost. And at the top of the scale it still gains no access it
would not otherwise have had: the ceiling is whatever Alice said about her own
resources.

That is not a rule bolted on afterwards — it follows from who produced the
evidence. The three axes are attested by the requesting side, or by an issuer
the owner never chose. Standing was produced by her own authority.

And it has a consequence worth stating on its own, because it is what makes
any of this safe to build:

> **A lie can only cost the liar friction.**

Which is why her policy can afford to read a self-asserted operator name at
all. An agent presenting metadata that does not resolve is admitted exactly
like any other stranger, and gains nothing on the second request either.

## What she writes

One list per tier. Conjunction inside a rule, disjunction across rules, and
nothing else — no negation, no nesting, no expressions.

```json
"rules": [
  {"when": ["assurance.accountability_below:1"], "then": "ask"},
  {"when": ["standing.age_above:90d", "standing.never_revoked"], "then": "auto"}
]
```

Relaxations apply first and restrictions last, so no combination of matched
rules can land more permissive than the strictest thing that matched. And a
rule that could widen access on evidence the agent controls **fails to save**
— rejected where policy is stored, not ignored where it is evaluated. A
control that is silently inert is worse than one that was never claimed.

The relaxing half needs one line finer than "her side produced it", because
one of her side's facts is circular: *we granted here before* may record an
automatic grant, so relaxing on it would let one automatic grant justify the
next. Only decisions she made herself — she admitted this agent, she approved
at this tier, she has never revoked it — may lower a requirement. And when a
relaxation actually lowers an ask-me tier, it is written to her ledger naming
the rule that fired, so a grant that skipped her is something she can find
afterwards rather than infer.

Notice what the vocabulary does not contain: no issuer, no CIMD, no key
thumbprint. `accountability_below:1` says *nobody I can check is standing
behind this*, not *no metadata document*. Swap the mechanism underneath and
her policy is unchanged — which is [the flow property](/docs/overview/flow/)
surviving contact with client-facing policy.

## Being admitted is not being admitted everywhere

One rule in the default policy fixes a real over-grant. Approving a first
contact used to admit an agent to everything below the ask-me line, so an
agent let in to look at holdings could read transaction history without ever
asking again — a broader relationship than the owner was shown when she
approved it.

`standing.first_at_tier` brings the first request at each new tier back to
her. Note the shape of the fix: a predicate, not a list of tiers per agent.
The list would have worked, and would have been the ACL.

## What stops her being spammed

Nothing above does. Keys are free, so anyone can mint ten thousand of them and
put ten thousand first-contact requests in front of her. Her attention is the
scarcest resource in the system, and an unbounded pending queue turns the
property that justifies the whole design — *she decides* — into its own
denial-of-service surface.

Rate limiting is the wrong instrument: per key it is theatre, per source
address it is the wrong layer, and neither expresses the thing that matters.
That is not how fast strangers arrive but **how much of her queue they may
occupy at once** — so the control is a depth limit rather than a rate.

At most *n* requests from agents she has no standing with may wait for her at
once. Past that they are refused, with a reason, rather than queued. Three
properties make it the right shape:

- **It is self-healing.** Every request she answers frees a slot. The cap is
  on the backlog, never on the relationship.
- **A flood cannot crowd out the agents she knows.** An agent with standing is
  never counted and never refused for budget, so an attack turns strangers
  away instead of taking her side down.
- **It needs no new state** — the count is a read of the queue her surface
  already lists.

Refuse honestly rather than silently. Silence is indistinguishable from a
broken server, and provokes exactly the retry storm the cap exists to prevent.

A cap of zero is a coherent posture — invitation-only — and should be
expressible. It is the wrong default for a profile whose whole argument is
that a stranger can negotiate.

## From self-assertion to attestation

Level 1 is a self-assertion. An operator publishes a document about itself, and
the only thing checked is that the document claims the URL it was fetched from
— which rules out third parties publishing metadata about someone else's agent,
and says nothing about *this* agent. Any agent can point at any operator's
public metadata.

Level 2 closes that without an accreditation scheme. The agent names the
operator's key directory; the authorization server fetches it and looks for the
thumbprint of the key that signed the contract. If it is there, the operator
published this agent's key — a claim made by the operator, about a key the agent
cannot add itself, checked by the party relying on it.

Two constraints keep it honest: the directory must be **same-origin with the
client identifier**, or an agent points at a directory it runs and attests to
itself; and a directory that will not resolve leaves the claim at level 1
rather than counting against the agent, because an operator's outage is not
evidence about an agent.

What is still missing is anyone *outside* the operator — an accreditation body,
a regulator. That would be a further level, it needs a trust framework that does
not exist, and this deliberately does not invent one.

## Where she writes them

In her portal, under Settings → Security → Agent Authorization → **My Terms**.
Rules render as sentences — *"If nobody named and reachable is standing behind
the agent — ask me first"* — composed from a vocabulary the authorization
server publishes, so the surface she edits through cannot offer her something
the server will reject.

The same page is where she **adds terms of her own**: a new tier, its purpose,
expiry and prohibited actions, over any resource her authority protects that no
tier governs yet. One resource belongs to one tier, or which terms apply would
depend on the order they happen to be stored in.

A rule that could widen access on evidence the agent controls does not save.
The refusal names the condition and says which facts may lower a requirement —
the rule is easier to learn from a refusal that explains itself than from
documentation nobody opened.

## What is deliberately not here

**No accreditation, registry, or trust framework.** Saying "agents of type X"
needs somebody authoritative about what type an agent is. UMA punted on that;
GNAP has been arguing about it for years. The asymmetry is what lets this
avoid choosing: because assurance can only add friction, it matters much less
who is asserting it.

**No relaxation on anything the agent influences, including its issuer.**
Verifying *who signed* a credential is not the same as trusting *what they
say* about the agent, and letting an issuer's assertion lower a requirement
delegates the owner's judgement to a party she never chose.

**Nothing in the shipped policy relaxes anything.** The only tier where a
relaxation could apply is trades, and "we have known each other a while" is
not a reason to stop asking about money. The mechanism exists; the default
policy declines to use it.
