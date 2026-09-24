---
templateKey: doc
title: Dictate terms, take an agreement
description: How the owner's side proffers the conditions of access, what a signed echo has to prove, and the checks that stop an agent agreeing to something weaker.
next:
  - title: Mint an operation-bound grant
    to: /docs/guides/grant/
    blurb: What happens after the agreement verifies.
  - title: Terms as first-class
    to: /docs/overview/terms/
    blurb: Why the terms travel with the request rather than beside it.
---

Beat two and beat three. The agent brings back the ticket, and instead of a
grant it gets the owner's conditions. It signs them, or the negotiation ends.

This is the beat with no equivalent in ordinary OAuth, and the one where the
implementation details decide whether you have a record or a decoration.

## Prerequisites

- A [challenge](/docs/guides/challenge/) that hands out a ticket
- A place to publish terms documents at stable URLs
- A signing key on the agent's side — the same one it will use for
  [proof-of-possession](/docs/overview/proof-of-possession/)

## 1. Publish the terms as documents

Before any negotiation, the owner's authority needs a roster of terms it can
point at.

Each terms document lives at a URL that keeps working — `GET /terms/{id}` — and
every version is retained. A term that is edited in place cannot be an agreement:
six months later there is no way to establish what was agreed to.

The pattern here is the one IEEE 7012 describes for individuals proffering their
own terms, applied to agentic access rather than to privacy. Serve both a machine
representation and a human one; someone will eventually need to read what their
agent signed.

## 2. Answer the ticket with `need_info`

The agent presents the ticket at the token endpoint. UMA's `need_info` response
is the right vehicle, and this profile puts something inside it that plain UMA
does not have.

Standard UMA names acceptable claim **formats**. Here the authority proffers the
claim's **content**:

```json
{
  "error": "need_info",
  "ticket": "<rotated>",
  "required_claims": [{
    "claim_type": "https://u4a.ai/spec/terms/1.0#myterms-agreement",
    "claim_token_format": ["https://u4a.ai/spec/terms/1.0#myterms-agreement-v1+jws"],
    "friendly_name": "Alice's terms: Holdings summary",
    "terms_template": {
      "template_id": "alice/advisor-tier1/v2",
      "terms_uri": "https://alice-as.uma.lab/terms/alice/advisor-tier1/v2",
      "proffered_by": "https://alice-as.uma.lab",
      "purpose": "Suitability review for advisory onboarding",
      "scope": ["positions:read"],
      "expires_in": 172800,
      "prohibited": ["retention-after-review", "marketing", "model-training"],
      "resource_id": "alice-vault/get_positions",
      "family": "<negotiation-family-id>",
      "nonce": "<nonce>"
    }
  }]
}
```

Three fields in the template are structural rather than editorial:

- **`terms_uri`** is what makes this a dereferenceable document rather than a
  blob. It has to be resolvable for the life of the negotiation and long after.
- **`family`** is the negotiation id, stable across every ticket rotation. It is
  what correlates the agreement, the owner's decision and the eventual access in
  the audit trail.
- **`nonce`** is what stops an agreement being replayed into a different
  negotiation.

Rotate the ticket on every presentation. That is UMA's single-use rule and it
holds here — each poll of a held ticket rotates it again.

## 3. Surface the terms to whoever can accept them

The agent's side has to get a human decision, or fall back to standing
configuration that a human set earlier.

If your agent speaks MCP, elicitation is the natural fit — the terms go to the
agent's own user, who is the party who can bind their side. Where no interactive
channel exists, a configured standing acceptance is legitimate as long as the
scope of what it accepts was decided by a person.

What is not legitimate is the agent signing on its own initiative because the
terms parsed.

## 4. Take a signed echo

The agent re-presents the rotated ticket with the agreement attached:

```
POST /token
grant_type         = urn:ietf:params:oauth:grant-type:uma-ticket
ticket             = <rotated>
claim_token        = <base64url(myterms-agreement JWS)>
claim_token_format = https://u4a.ai/spec/terms/1.0#myterms-agreement-v1+jws
```

The agreement is the template echoed back and signed. Its protected header
carries the signing key — either bare, for a pseudonymous agent, or as a token
from the agent's issuer for an identified one.

The important property: the key that signs the agreement is the key that will
later prove possession of the grant. One key, two jobs, so the party that
committed is demonstrably the party that calls.

## 5. Verify the echo properly

This is the step where an implementation quietly becomes theatre. Checking that
a signature verifies is not enough — a valid signature over weaker terms is
exactly what an adversarial agent would produce.

Verify all of it:

| Check | What it stops |
|---|---|
| Signature verifies against the header key | Anyone signing as someone else |
| `nonce` matches the one proffered | Replay into a different negotiation |
| `family` matches | An agreement moved between negotiations |
| `template_id` and `terms_uri` match | Agreement to a different document |
| `purpose` unchanged | Quiet repurposing |
| `prohibited` not weakened | Dropping the restrictions that mattered |
| `expires_in` not extended | Turning a two-day grant into a standing one |
| Operation present, if the tier needs one | A per-operation tier answered generically |

"Not weakened" is the direction that matters. An agent adding restrictions to
its own conduct is fine. An agent removing one is the whole attack.

Store the verified agreement content-addressed by its hash. The hash is what the
grant will carry, so a grant always names the exact terms behind it.

## 6. Return a counter-signed receipt

When the grant issues, it comes with a receipt: a JWS signed by the owner's
authority that **embeds the complete agent-signed agreement** along with the
terms URI, the agreement hash, the agent's key thumbprint and the negotiation
family.

Both sides then hold identical, dually-signed copies of the same record. Neither
can later produce a version the other cannot check.

Handle refusal the same way. An agent that will not accept the proffered terms
can end the negotiation explicitly, and that refusal is written to the owner's
ledger naming the terms declined. A record of "she offered, they said no" is
worth as much as a record of agreement.

## What this does and does not give you

> Signing terms does not enforce them. Nothing in the protocol stops an agent
> that agreed to `prohibited: ["model-training"]` from training on the data
> anyway.

What the exchange produces is a **record**: dually signed, content-addressed,
naming a persistent document, correlated to the access that followed. That is
the input to a conversation with a counterparty, a regulator, or a court — and
it is exactly what a click-through consent screen fails to produce.

Say this on your own pages too. Overstating it is how the mechanism loses
credibility with the people who would otherwise adopt it.

## Troubleshooting

**Every agreement fails verification on `nonce`.** The agent is echoing the
template from the *first* `need_info` after the ticket rotated again. Echo the
template that came with the ticket being presented.

**Agreements verify but the audit trail cannot correlate them.** `family` is
being regenerated per presentation instead of assigned once when the permission
is registered.

**The terms URI 404s a month later.** Versions are being overwritten. Retain
every version — the document has to outlive the negotiation.

**An agent signs instantly, every time, at any tier.** Its side has no human in
the loop and no standing configuration either. That is a bug on the requesting
side, and the owner's authority cannot detect it — which is an argument for
pending first contact regardless of tier.
