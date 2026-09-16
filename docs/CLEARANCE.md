# An authorization that is nobody's here to give

Alice's terms decide whether an agent may touch her things. They cannot decide
whether the act is *permitted at all*.

Whether the desk behind a trade holds a current licence, whether it is
registered where the order would be placed, whether the buyer is old enough —
these are facts about the world, established by somebody else. A grant that
asked the requesting party for them would be a compliance check performed by
the party it is about.

So U4A does not ask the agent. The requirement is hers, or her organization's;
the answer comes from the organization, to her authorization server, over her
authorization server's own credential.

Run it: `make clearance-check`, or `make k8s-clearance-check` in the cluster.
Unit tests, needing nothing running: `make org-test` and `make as-test`.

## The rule this follows

It is the rule the joint-ownership work arrived at from the other direction,
and it is worth stating plainly because it decides the whole shape:

> A claim works when the requesting party is the only one who holds the fact,
> and fails when the fact may be adverse to it.

A licence is adverse-capable. Its holder has every reason to say it is current,
and no counterparty can tell the difference from the assertion alone. That is
why a verdict in [joint ownership](JOINT.md) travels authority-to-authority
rather than as a claim, and it is why a clearance does too.

## What travels

| | |
|---|---|
| Who requires it | her tier, her organization's charter, or both |
| Who attests it | the organization, about its member |
| Who verifies it | her authorization server, against keys the organization publishes |
| How it travels | a signed `u4a-clearance+jwt`, fetched by her authority over its membership credential |
| Who never carries it | the agent |

The attestation names the member as `sub` and her authorization server as
`aud`, so an attestation about one person, issued to one authority, is not
evidence about another person or at another authority. It is short-lived on
purpose: a licence is exactly the kind of fact that lapses, and a statement
about one should not outlive it.

## The requirement

A requirement is a set of claims, each naming the values that satisfy it:

```json
{"licence_active": [true], "jurisdiction": ["US-NY", "US-NJ"]}
```

She may write one on a tier. Her organization may require one in its charter's
envelope, and then it reaches terms she has already written, the same way every
other ceiling field does — `make clearance-check` writes her terms, edits the
requirement away, and watches the ceiling put it back.

Where both require a claim, the two combine by **intersection**: a claim either
requires is required, and a claim both require is satisfied only by values both
accept. The layer above may add a claim and narrow an accepted value. It cannot
remove a requirement she wrote.

## What happens when it is unmet

The negotiation is refused **before her terms are dictated**, and the refusal
names the claim rather than saying "denied". An agent that signed an agreement
it was never going to be allowed to act under would be holding a record of a
bargain that never existed, and her ledger would carry an undertaking that
decided nothing.

Her record keeps the reason, in the same words she would be shown. An
organization that cannot be reached has not attested to anything, so that is a
refusal too — the same direction the [organization's ceiling](ORG.md) already
fails in.

## What the grant carries

A digest, and not the facts.

That a clearance was checked is the enforcement point's business. What it said
is the subject's: the facts are about *her* — her licence, where she is
registered — and the party that would read them out of the grant is the agent
that asked. So the RPT carries `clearance` as an `s256` over the attested
facts, her ledger keeps the facts on her side, and the check asserts both.

## Withdrawal

An administrator withdrawing the attestation is the same call with an empty
object. Access stops within the attestation's lifetime, and nobody edits a
policy to make it stop — which is the property a licence that can lapse
actually needs.

## Why not a claim token

Because there is no wire path for one, deliberately. Her authorization server
accepts two claim token formats — the signed agreement, and an enterprise
identity assertion — and a clearance offered by a client is refused as a format
this authority does not take. `make clearance-check` asserts that too.

An enterprise identity assertion is the neighbouring case and the contrast is
exact: an ID-JAG says *who the agent acts for*, which is a fact the requesting
side legitimately holds about itself. A clearance says *whether that party is
permitted*, which is not.
