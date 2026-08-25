# Joint ownership: when the stuff is several people's at once

[Shared ownership](ORG.md) answers "some of this is the firm's". This answers
a different question, and it is the one with no mechanism anywhere: **what if
a resource has two owners of equal standing, and neither can decide alone.**

A joint bank account is the ordinary case. The awkward ones are worse — a data
set with several subjects whose interests genuinely conflict, where there is
no party above them to arbitrate and no obvious reason any one of them should
be able to release it.

![One resource held by Alice and Carol: the tally asks each of them for her
terms, folds them into the one document the agent signs, collects a verdict
signed by each owner's own authority, and issues a grant carrying those
verdicts — which the enforcement point verifies and counts
again.](joint-ownership.gif)

```bash
make joint-check
```

Expect **29 passed, 0 failed** across six processes.

## What is actually new

Three objects, and the third is the one that needed thinking about.

```
mandate    who is entitled to be counted, at what weight, and how many it takes
verdict    one owner's authority, signing its answer to one negotiation
tally      the party that collects verdicts and does arithmetic
```

A mandate is agreed to by the holders and published beside the resource. A
verdict is a JWS from a holder's own authorization server. And a tally is the
awkward one: something has to put one question to several authorities and
combine the answers, and whatever does that sits in a structurally privileged
position.

The reflex is to make the privileged thing trustworthy — replicate it,
distribute it, put it on a ledger. This takes the other route. **The tally is
made unable to lie, and then it does not matter who runs it.**

## Why this is not consensus, and not a ledger

The word "consensus" does real damage here. Distributed consensus solves
agreement on an *ordered history* among parties who need a coordinator they
cannot trust. None of that applies:

- **there is no ordering.** Verdicts about one negotiation are a set. Nothing
  depends on which arrived first;
- **there is no long-lived state to protect.** Grants are short and
  re-negotiated. There is no balance that a fork could double-spend;
- **replay is a signature problem, not a ledger problem.** Each verdict names
  the negotiation and the exact agreement it is about, so it cannot carry a
  later request;
- **the coordinator does not have to be trusted**, so it does not have to be
  decentralised. You decentralise a coordinator when you are forced to trust
  one. Making it unable to fabricate a yes removes the requirement rather
  than satisfying it.

What is left is a fold and a comparison.

## The three things a tally cannot do

**It cannot manufacture a yes.** It holds no key that any relying party
accepts as a verdict. The grant it issues carries the holders' signed
verdicts *inside it*, and the enforcement point verifies each one against the
keys that holder's own authorization server publishes and re-runs the count
from the mandate. A tally that forged a verdict, replayed an old one, or
reported a threshold it never reached is refused at the door.

```
joint: {
  mandate:  { holders: [...], rule: { kind: "all", threshold: 2 }, resources: [...] },
  verdicts: [ <JWS signed by alice-as>, <JWS signed by carol-as> ],
  tally:    { effect: "allow", for: 2, threshold: 2 }
}
```

The last field is the tally's own claim. The enforcement point ignores it and
recomputes, which is why the field is safe to carry at all.

**And it recomputes against the mandate the tally *publishes*, never the copy
in the grant.** That distinction is the whole difference between a check and a
formality. Counting against the embedded copy would leave the electorate in
the gift of the party being checked: a tally could ship one genuine verdict
beside a mandate saying one is enough, every signature would verify, and the
arithmetic would agree with it. The published document is the one the holders
saw and can check for themselves, so it is the one the count runs on — and a
mandate that cannot be read is a refusal rather than a fallback.

**It cannot weaken anybody's terms.** It folds every holder's terms into the
one document an agent signs — see below — and each holder's authority
independently compares what was signed against what she published, refusing on
any difference in the direction of *more*.

**It decides nothing about identity.** It verifies that the agreement was
signed by the key it names, because that key is bound into the grant, and
stops there. Whether the agent is identified, who operates it, and whether
that operator published the key are judgements the holders' authorities make
with their own evidence. A coordinator that graded identity would be a
coordinator holding policy.

## One document, everybody's terms

An agent cannot usefully sign four documents, and an intersection computed by
the requesting side is an intersection computed by the party that benefits
from getting it wrong. So the tally publishes the fold as one terms document:

| | |
|---|---|
| expiry | the shortest any holder set |
| scopes | only those every holder offers |
| prohibitions | every one any holder wrote |
| asks a person | if any holder wants asking |

That is the same operation as an organization applying a ceiling, pointed
sideways instead of down — so it is the same code. `uma4a_org.clamp` narrows
one terms document by another and is proved one-directional by
`lib/test_org.py`; folding expresses each holder's terms as a ceiling and
clamps the running document by each in turn. A second implementation of
"narrower" would be a second chance to disagree about what the word means, in
the two places where disagreeing is worst.

The safety of letting an untrusted party do the folding is that **it is
checked afterwards by everyone it could have cheated.**

## Why a verdict is not a claim the agent gathers

The obvious UMA-shaped answer is claims-gathering: `need_info` names the
claims required, the requesting party goes and collects them, and comes back.
That machinery is older than UMA 2.0 — the UMA1-era [claim
profiles](https://docs.kantarainitiative.org/uma/draft-uma-claim-profiles.html)
draft imagined `need_info` carrying a great deal of structure, which is also
the lineage of the `terms_template` this protocol puts inside `required_claims`
(extension 1). So it is a fair question why the co-owners' verdicts are not
claims of exactly that kind.

Because **a claim the client gathers is a claim the client can decline to
gather.**

If a holder's verdict were a claim, the agent would collect one from each
authority and present the set. An agent that collected two allows and one
refusal has every incentive to present two claims and say the third is still
coming — and a missing claim is indistinguishable from one that has not been
answered yet. The refusal would never arrive. Under any rule short of
unanimity it would simply be lost; under unanimity it would present as an
indefinite wait, which is a denial of service against the *holder*, not
against the agent.

So the split is:

| | |
|---|---|
| gathered by the requesting party | the signed agreement — the folded terms |
| never touched by the requesting party | the holders' verdicts |

A refusal has to be able to reach the decision point without the cooperation
of the party it refuses, so verdicts travel authority-to-authority and the
agent never handles one. It does end up carrying them, inside the grant — but
by then the count is settled, and the enforcement point re-checks it anyway.

The general form is worth stating because it applies beyond this: **claims
work when the requesting party is the only one who has the fact, and fail when
the fact might be adverse to it.**

## Silence is not consent

A holder who has written no terms over the resource quotes nothing, and is
left out of the fold rather than defaulted into anything. Under a rule that
needs everybody, that stops the request. An owner who has not said what she
permits has not permitted anything, and an authority that is unreachable is
not a yes either — the count fails closed in both cases.

## The rule, and who sets it

```json
"rule": { "kind": "all" }          // every holder
"rule": { "kind": "any" }          // the lightest holder alone
"rule": { "kind": "threshold", "threshold": 3 }
```

Everything normalises to a number, because everything downstream compares
weights and a rule left as a word would be re-interpreted at each place that
read it. Holders may carry different weights; `any` means the *lightest* of
them can act alone, or the word would quietly exclude somebody.

A refusal does not wait for everybody. The moment the weight still outstanding
cannot carry the request over the threshold, it is refused — under `all`, that
is the first refusal. Waiting would leave people answering a settled question
and an agent polling for an outcome that cannot change.

**And a group cannot answer what quorum sets the quorum.** A mandate carries a
floor it may not go below, supplied by something other than the holders — an
account agreement, or a regulator. In the lab it is `TALLY_THRESHOLD_FLOOR`;
a mandate below it is refused at startup, by name. This is the same shape as
an organization's ceiling, which is worth noticing: **peers compose
horizontally, and an authority above them clamps vertically.** The two
arrangements are orthogonal rather than competing.

## Against the four states of delegated control

The [PP2PI report](ORG.md#against-the-four-states-of-delegated-control) lays
out **co-administration** as several administrators over one subject's
resources. Shared ownership implements that with authority **partitioned**:
Alice administers the firm's book for herself, Carol for herself, and their
decisions never meet — every request has exactly one member authority plus the
organization's ceiling.

This is co-administration with authority **conjoint**: two authorities
answering *the same* request, with no ceiling above either of them. Both are
real, and the second is the one that needed a new object.

## What the agent sees

Nothing. It gets an ordinary UMA challenge, an ordinary `need_info` with terms
to sign, and an ordinary wait while people are asked. The `as_uri` happens to
name a party that owns nothing, and the terms document says so:

```json
"joint": {
  "account": "meridian-joint",
  "holders": ["alice", "carol"],
  "quoted":  ["alice", "carol"],
  "rule": "all",
  "threshold": 2,
  "requires": ["Held jointly by alice, carol, over …",
               "Every holder has to allow a request before it is granted. …"]
}
```

An unmodified agent negotiates with a tally exactly as it negotiates with an
authorization server. That is deliberate: a shape that required the requesting
side to know about joint ownership would not be adoptable.

## What a specification would have to say

- **A verdict is a document.** Making one authority's answer a portable,
  signed artifact bound to a negotiation and an agreement digest is the whole
  enabling move. Everything else follows from it.
- **The party that counts must not be the party that is trusted.** Carry the
  verdicts in the grant and let the enforcement point re-derive the result.
  The cost is a larger token.
- **Re-derive against the published electorate, not the one in the token.**
  Otherwise the party being checked supplies the standard it is checked
  against, and one honest verdict beside a rewritten threshold passes.
- **The electorate is not the coordinator's to edit.** A mandate is published
  by the resource server and agreed to by the holders; a tally that could add
  a holder or lower a threshold would be deciding who gets a say.
- **Fail closed on silence and on unreachability**, and distinguish them in
  what is logged but not in what is granted.
- **A threshold may come from outside the group**, and when it does the group
  may not lower it.
- **One holder's standing in one resource is not standing anywhere else.**
  Being a co-owner gives no view of a co-owner's other resources, her queue,
  or her terms over anything else.
- **Say which facts the requesting party may carry.** A claim it gathers is a
  claim it can decline to gather, so anything that might be adverse to it —
  a refusal above all — has to travel between authorities. This is a general
  rule about claims-gathering that this case makes unavoidable.

## Limits

Honest ones, in a lab.

- **The tally keeps negotiations in memory and runs as one replica.** The
  authorization servers here persist theirs and a real deployment of this
  would too; nothing in the design needs the simplification.
- **Mandates are configuration.** There is no flow for holders to author one
  together, which is a real gap: the bootstrapping of a mandate is exactly
  where the "who decides who decides" problem lives, and this defers it to
  whoever writes the config.
- **A holder leaving is a fact her authority stops answering to, not an
  amendment to the mandate.** The other holders' document still names her
  until it is republished.
- **Weights are integers in a document.** Where a real weight would come from
  — a relationship, a shareholding, a degree of relatedness — is a claims
  problem with its own provenance question, and it is not solved here.
- **Disagreement is a stable state.** A request that cannot reach its
  threshold is refused, and nothing here escalates, arbitrates, or offers a
  partial outcome. Per-scope thresholds are the obvious next thing and are
  not built.

## See also

- [ORG.md](ORG.md) — the layer above an owner, and how it composes with this
- [MULTI-OWNER.md](MULTI-OWNER.md) — one resource server, several owners
- [PROTOCOL.md](PROTOCOL.md) — the grant loop these extend
