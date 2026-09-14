---
title: "Owner-Proffered Terms for User-Managed Access (UMA) 2.0"
abbrev: "Owner-Proffered Terms"
docname: draft-gamb-uma4agents-terms-00
category: info
submissiontype: IETF
ipr: trust200902
area: Security
keyword: [UMA, authorization, terms, consent, receipts]
stand_alone: yes
pi: [toc, sortrefs, symrefs]
author:
  -
    ins: N. Gamb
    name: Nick Gamb
    organization: MindGarden LLC
    email: nickgamb@gmail.com
  -
    ins: E. Maler
    name: Eve Maler
    organization: Venn Factory
normative:
  RFC7515:
  RFC7517:
  UMAGrant:
    title: "User-Managed Access (UMA) 2.0 Grant for OAuth 2.0 Authorization"
    author:
      - ins: E. Maler
        name: Eve Maler
      - ins: M. Machulak
        name: Maciej Machulak
      - ins: J. Richer
        name: Justin Richer
    date: 2018-01-07
    seriesinfo:
      Kantara: Recommendation
    target: https://docs.kantarainitiative.org/uma/wg/rec-oauth-uma-grant-2.0.html
  U4ACore:
    title: "User-Managed Access (UMA) 2.0 Profile for Autonomous Agents"
    author:
      - ins: N. Gamb
        name: Nick Gamb
      - ins: E. Maler
        name: Eve Maler
    date: 2026
    seriesinfo:
      Internet-Draft: draft-gamb-uma4agents-core-00
    target: https://u4a.ai/spec/draft-gamb-uma4agents-core-00.html
informative:
  IEEE7012:
    title: "IEEE Standard for Machine Readable Personal Privacy Terms"
    date: 2025
    seriesinfo:
      IEEE: Std 7012-2025
    target: https://standards.ieee.org/ieee/7012/7192/
  ODRL:
    title: "ODRL Information Model 2.2"
    author:
      - ins: R. Iannella
        name: Renato Iannella
      - ins: S. Villata
        name: Serena Villata
    date: 2018-02-15
    seriesinfo:
      W3C: Recommendation
    target: https://www.w3.org/TR/odrl-model/
  UMAClaims2010:
    title: "Simple Access Authorization Claims"
    author:
      - ins: E. Maler
        name: Eve Maler
      - ins: P. Bryan
        name: Paul Bryan
    date: 2010-04
  U4APolicy:
    title: "Owner Policy, Assurance and Attention for User-Managed Access (UMA) 2.0"
    author:
      - ins: N. Gamb
        name: Nick Gamb
      - ins: E. Maler
        name: Eve Maler
    date: 2026
    seriesinfo:
      Internet-Draft: draft-gamb-uma4agents-policy-00
    target: https://u4a.ai/spec/draft-gamb-uma4agents-policy-00.html
  U4AMultiParty:
    title: "Multi-Party Authorization for User-Managed Access (UMA) 2.0"
    author:
      - ins: N. Gamb
        name: Nick Gamb
      - ins: E. Maler
        name: Eve Maler
    date: 2026
    seriesinfo:
      Internet-Draft: draft-gamb-uma4agents-multiparty-00
    target: https://u4a.ai/spec/draft-gamb-uma4agents-multiparty-00.html
  U4ALAB:
    title: "UMA for Agents: a reference implementation"
    author:
      - ins: N. Gamb
        name: Nick Gamb
      - ins: E. Maler
        name: Eve Maler
    date: 2026
    target: https://github.com/nickgamb/uma4agents

--- abstract

This document extends the claims-gathering loop of the User-Managed Access (UMA)
2.0 Grant so that the authorization server proffers the *content* of the claim it
requires, rather than only naming acceptable claim formats.

The resource owner's authorization server publishes a terms document — purpose,
scope, duration and prohibitions — at a persistent, dereferenceable URI. The
requesting side echoes that document, signs it with the key it will later prove
possession of, and presents it as the claim token. The grant returns a receipt,
counter-signed by the authorization server, embedding the signed agreement, so
that both parties hold identical records of what was agreed.

--- middle

# Introduction

{{UMAGrant}} Section 3.3.6 lets an authorization server tell a client what claims
it needs by naming claim types and acceptable formats. The client then gathers
those claims from wherever it can and presents them. The authorization server
asks *what can you tell me about yourself*.

This extension adds the other direction. The authorization server proffers a
document stating what the resource owner requires of anyone who wants this
access, and the claim the requesting side returns is that document, signed. The
authorization server asks *will you agree to this*.

The pattern is that of {{IEEE7012}}, in which an individual proffers
machine-readable terms as first party and a counterparty's agent agrees to them
as second party. This document extends it from privacy terms to terms of access,
and carries the agreement inside a grant so that the terms are conditions on an
authorization rather than a record kept beside one. It is also a direct
descendant of UMA's own 2010 work {{UMAClaims2010}}, which defined a "requesting
party policy" claim for exactly this purpose and which the 2.0 specifications did
not carry forward.

## Relationship to the Set

This document extends {{UMAGrant}} and is REQUIRED to implement alongside
{{U4ACore}}. It is separable: a UMA deployment with no agents in it can adopt
this extension on its own, and nothing here depends on the requesting side being
autonomous.

Its identifying URI, for the `uma_profiles_supported` metadata of {{UMAGrant}}
Section 4, is `https://u4a.ai/spec/terms/1.0`.

## Notational Conventions

{::boilerplate bcp14-tagged}

The notation `s256(x)` is as defined in {{U4ACore}}.

# The Terms Document {#terms-document}

An authorization server implementing this extension MUST serve, for each set of
terms it proffers, a document at a URI that resolves for as long as the
authorization server serves the owner whose terms they are.

A terms document MUST carry:

template_id:
: REQUIRED. A stable identifier for this version of these terms, namespaced by
  owner.

purpose:
: REQUIRED. What the access is for, in the owner's words.

scope:
: REQUIRED. An array of scope strings the terms cover.

expires_in:
: REQUIRED. The maximum lifetime, in seconds, of access granted under these
  terms.

prohibited:
: REQUIRED. An array of identifiers naming what the requesting side undertakes
  not to do. MAY be empty.

proffered_by:
: REQUIRED. The issuer identifier of the authorization server that proffers them.

A terms document MAY carry any other member; a member this document does not
define is an undertaking the requesting side signs, not a control the
enforcement point applies. One member is defined here:

per_operation:
: OPTIONAL. Boolean. Where `true`, a grant under these terms is bound to one
  operation and spent once, as {{U4ACore}} Section 7.2, and the agreement MUST
  name the operation proposed.

## Versions Are Immutable {#immutable}

The content of a terms document at a given `template_id` MUST NOT change. An
authorization server that changes the owner's terms MUST issue a new
`template_id` and MUST continue to serve every previous version.

An agreement is a signature over a document. A document that can change after it
is signed makes every agreement over it unverifiable later, which removes the
only property that distinguishes this from a consent dialog.

## Representations {#representations}

An authorization server MUST serve a terms document as JSON, and MUST serve, at
the same URI, a plain-language representation intended for a person, selected by
HTTP content negotiation. It SHOULD additionally serve a representation in a
rights expression language such as {{ODRL}}.

The three representations satisfy {{IEEE7012}} Sections 4.4.1 and 4.4.2. The
requirement that they share a URI is what makes the human-readable statement and
the machine-readable one the same terms rather than two documents that may drift.

# Proffering {#proffering}

Where the authorization server requires agreement to terms before it will decide,
it responds to a ticket presentation with `need_info` as {{UMAGrant}} Section
3.3.6, carrying a required claim whose `claim_type` is
`urn:uma4agents:claim:myterms-agreement` and whose `claim_token_format` array
includes `urn:uma4agents:format:myterms-agreement-v1+jws`.

The required claim MUST additionally carry a `terms_template` member: the terms
document of {{terms-document}}, plus

terms_uri:
: REQUIRED. The URI at which this version of this document is served.

nonce:
: REQUIRED. A value the authorization server has not previously used, to be
  echoed in the agreement.

family:
: REQUIRED. The identifier of this negotiation, stable across ticket rotations.

resource_id:
: REQUIRED. The resource the terms are being proffered over.

~~~ json
{
  "error": "need_info",
  "ticket": "MWRlNzE4ZjgtMGY0OS00NDg2",
  "required_claims": [{
    "claim_type": "urn:uma4agents:claim:myterms-agreement",
    "claim_token_format": [
      "urn:uma4agents:format:myterms-agreement-v1+jws"
    ],
    "friendly_name": "Alice's terms: Holdings summary",
    "terms_template": {
      "template_id": "alice/advisor/v2",
      "terms_uri": "https://alice-as.example/terms/alice/advisor/v2",
      "proffered_by": "https://alice-as.example",
      "purpose": "Suitability review for advisory onboarding",
      "scope": ["positions:read"],
      "expires_in": 172800,
      "prohibited": ["retention-after-review", "marketing"],
      "resource_id": "alice-vault/get_positions",
      "family": "fam_8f3aQ2Xc",
      "nonce": "n5Kd2pQrTgWs"
    }
  }]
}
~~~
{: title="A need_info response proffering terms."}

The authorization server MUST offer exactly one set of terms per demand. There is
no counter-offer and no negotiation beyond the single choice of agreeing or not,
per {{IEEE7012}} Section 5.2.2. A protocol that let the requesting side propose
amendments would make the owner a party to a conversation she is not present for.

## Authorization Server Metadata {#terms-metadata}

This document adds the following member to the authorization server metadata of
{{U4ACore}} Section 2:

terms_endpoint:
: The URL of the owner's terms roster. An authorization server implementing this
  document MUST include it.

# The Agreement {#agreement}

The requesting side agrees by presenting a claim token whose
`claim_token_format` is `urn:uma4agents:format:myterms-agreement-v1+jws` and
whose value is the base64url encoding of a JWS {{RFC7515}} in compact
serialization with a `typ` of `myterms-agreement-v1+jws`. The compact
serialization is encoded as a whole, so decoding the claim token yields the JWS.

## The Signing Key {#signing-key}

The JWS protected header MUST carry exactly one of:

jwk:
: A public JWK {{RFC7517}}, where the requesting side is pseudonymous.

agent_token:
: A credential from an issuer that asserts the client's identity and
  names the signing key, where the requesting side is identified.

The authorization server MUST verify the JWS against the key so named, and MUST
refuse an agreement carrying neither. The key that signs the agreement is the key
that is confirmed in the grant, so that the party that agreed and the party that
later acts are provably the same.

## Claims {#agreement-claims}

The agreement MUST echo, unchanged, the `template_id`, `terms_uri`, `purpose`,
`nonce` and `family` of the proffered template, and MUST carry an `aud` naming
the authorization server that proffered them.

It MUST carry a positive `expires_in` no greater than the template's, a `scope`
array that is a subset of the template's, and a `prohibited` array that is a
superset of the template's.

Where the template's `per_operation` is `true`, the agreement MUST carry an
`operation` member: an object whose `tool` member names the operation proposed
and whose `params` member is a JSON object holding the parameters proposed for it.

~~~ json
{
  "iss": "agent:6cR6qTmCj6s0S95M",
  "aud": "https://alice-as.example",
  "iat": 1789430000,
  "template_id": "alice/advisor/v2",
  "terms_uri": "https://alice-as.example/terms/alice/advisor/v2",
  "purpose": "Suitability review for advisory onboarding",
  "scope": ["positions:read"],
  "expires_in": 172800,
  "prohibited": ["retention-after-review", "marketing"],
  "family": "fam_8f3aQ2Xc",
  "nonce": "n5Kd2pQrTgWs",

  "reason": "Suitability review before Thursday's client meeting.",
  "mission": {
    "approver": "https://ps.example",
    "s256": "s256:zrAKkVJdpk-xcbEDrjDvO4F_o7x47N6ZuITu2-kTEAM"
  }
}
~~~
{: title="An agreement. Everything above the blank line is the owner's template, echoed."}

The superset test on `prohibited` is deliberate: binding yourself to more than
was asked is agreement, and refusing it would make the honest case fail. Every
other echoed member is compared for equality, because a requesting side that can
alter the purpose it signed up to has signed a different document from the one
the owner published. `scope` and `expires_in` are the same test pointed the other
way: agreeing to less than was offered is agreement, and agreeing to more is not.

A grant issued on an agreement MUST NOT outlive the agreement's `expires_in`. An
agreement for a shorter time is a statement about how long the access will be
used, and a grant issued past it would leave the receipt and the grant
disagreeing about what was agreed.

## What the Requesting Side May Author {#requester-claims}

The agreement MAY carry the following, and MUST NOT carry anything else that
affects the decision:

reason:
: OPTIONAL. A string stating why the access is wanted. The authorization server
  MUST bound its length, MUST record it, and MUST NOT parse it, compare it to the
  purpose in the terms, or let its content affect the decision.

mission:
: OPTIONAL. An object citing a mandate the requesting side is acting under, with
  an `approver` member that is an `https` URL and an `s256` member that is a
  content digest. The authorization server MUST record the citation and MUST NOT
  dereference it.

Policy MAY read the *absence* of either. It MUST NOT read the content of either.
See {{U4APolicy}}.

An authority that reads a stated reason and rules on whether it is plausible has
put a judgement about natural language inside an authorization decision: the same
request becomes answerable two ways, and the requesting side learns to write
whatever gets through. Bound it, record it, show it to the owner, and let policy
do exactly one thing with it — notice when it is missing.

A mission citation is recorded rather than dereferenced because the issuers that
serve missions serve them to their own administrators. A relying party in another
trust domain has nothing to fetch, so an agent citing a real mandate and one
inventing a digest are indistinguishable to it. That is why the citation is a
record for the owner to read and never an input to the decision.

# The Receipt {#receipt}

On issuing a grant against an agreement, the authorization server MUST return a
receipt alongside the token, as a member named `receipt` in the token endpoint
response.

The receipt MUST be a JWS signed by the authorization server with a `typ` of
`myterms-receipt+jws`, and MUST carry:

terms_uri:
: REQUIRED. The document that was agreed to.

template_id:
: REQUIRED. The version that was agreed to.

agreement:
: REQUIRED. `s256` over the octets of the agreement as transmitted: the JWS
  compact serialization obtained by decoding the claim token.

agreement_jws:
: REQUIRED. The complete agreement JWS, as received.

family:
: REQUIRED. The negotiation this receipt completes.

~~~ json
{
  "iss": "https://alice-as.example",
  "sub": "jkt:ESqNMeKw-z8gcDH-8y96ckX3h7TU6FtF9lqluDQ1Now",
  "iat": 1789430010,
  "family": "fam_8f3aQ2Xc",
  "terms_uri": "https://alice-as.example/terms/alice/advisor/v2",
  "template_id": "alice/advisor/v2",
  "agreement": "s256:RqgXOcbufB1e0ITn3oQ6fteUNc1EVRPk3VxOWsOV-0s",
  "agreement_jws": "eyJ0eXAiOiJteXRlcm1zLWFncmVlbWVudC12MStqd3Mi..."
}
~~~
{: title="A receipt's claims."}

Embedding the whole agreement rather than a reference to it is what makes the two
records identical: the owner's side retains it with her decision record and the
requesting side retains the receipt, and neither has to ask the other for the
half it is missing. This satisfies {{IEEE7012}} Sections 5.2.2 and 5.4.4.

# Declining {#declining}

A requesting side that will not agree to the proffered terms MUST be able to say
so. An authorization server MUST accept a `decline` parameter with the value
`true` at the token endpoint while a negotiation is awaiting a claim, MUST end
the negotiation, and MUST record the refusal against the terms that were
declined.

A refusal is a record too, per {{IEEE7012}} Section 5.2.4. It is also the only
signal an owner has that her terms are the reason nobody uses a resource she has
published.

A declining requesting side has signed nothing, so there is no key and no identity
to file the record under. An authorization server MUST record such a refusal
without attributing it to a party. An implementation that invents an attribution
here is asserting something it does not know.

# Security Considerations

## The Agreement Binds the Key That Will Act

See {{signing-key}}. If the agreement could be signed by one key and the grant
confirmed to another, the party that agreed and the party that acts would be
different parties, and the agreement would say nothing about the requests made
under it.

## The Digest Is Over the Transmitted Octets

The `agreement` member of the receipt, and any digest of the agreement recorded
with the grant, MUST be computed over the agreement exactly as transmitted, not
over a re-serialization of its claims. A digest over re-serialized JSON is a
digest of the verifier's serializer, and two conforming implementations will
disagree about it.

## Terms Are Not a Sandbox

An owner's prohibitions divide into two kinds, and an implementation SHOULD be
able to say which is which for each one it supports. A prohibition on something
that must cross the owner's boundary to happen — placing an order outside
approved parameters, reusing an approval for a second action — can be refused at
the enforcement point. A prohibition on what happens afterwards on the requesting
side's own systems — retention, onward sharing, training — cannot.

Both belong in the terms, and only one is a control. The second is what the
dually-signed record exists for: it makes the undertaking checkable against
conduct rather than preventing the conduct. Describing the second kind as
enforcement is the overstatement this section exists to prevent.

# Privacy Considerations

## The Roster Is the Owner's

{{IEEE7012}} Section 4.2 places the roster of proffered terms with a neutral
non-profit, so that an individual chooses from a small set of well-understood
agreements rather than authoring her own. This document places it with the
owner's own authorization server, because the terms here are conditions inside a
grant that server issues and it has to be able to serve them for as long as the
grant is checkable.

The divergence is real and has a cost: terms nobody else proffers are terms
nobody else has read. A deployment SHOULD proffer terms drawn from a published
roster where one exists for its domain, and the `template_id` namespacing in
{{terms-document}} is designed so that a roster identifier can be used directly.

## The Terms Document Is Public

A terms document is dereferenced by a requesting side that holds no token, so its
content is public to anyone who can guess or observe its URI. It states what the
owner requires, which is a statement about her. An authorization server MUST NOT
place anything in a terms document that identifies the owner beyond what the
resource identifier already discloses.

Where a layer above the owner has narrowed her terms, the narrowing appears in
the document, which is deliberate — see {{U4AMultiParty}}. An agent reads the
document before it signs, and that is the only moment at which "these terms are
not hers alone" is information it can act on.

# IANA Considerations

This document has no IANA actions. The identifiers it uses are listed in
{{used-identifiers}}.

--- back

# Identifiers Used by This Document {#used-identifiers}

This appendix lists the identifiers this document defines. It is informative and
requests no registration.

| Identifier | Kind | Defined in |
|---|---|---|
| `terms_endpoint` | Authorization server metadata | {{terms-metadata}} |
| `decline` | Token endpoint request parameter | {{declining}} |
| `receipt` | Token endpoint response member | {{receipt}} |
| `application/myterms-agreement-v1+jws` | Media type | {{agreement}} |
| `application/myterms-receipt+jws` | Media type | {{receipt}} |
| `urn:uma4agents:claim:myterms-agreement` | URN | {{proffering}} |
| `urn:uma4agents:format:myterms-agreement-v1+jws` | URN | {{agreement}} |
{: title="Identifiers used by this document."}

# Implementation Status {#implementation-status}

This section records the status of known implementations in the sense of
{{?RFC7942}}, and is to be removed before publication as an RFC.

The reference implementation {{U4ALAB}} described in {{U4ACore}} implements this extension
in full, including all three representations of {{representations}}, the
immutability requirement of {{immutable}}, the receipt of {{receipt}} and the
unattributed refusal record of {{declining}}. It was checked clause by clause
against {{IEEE7012}}; the divergences found are the ones stated in this document
rather than a longer list kept elsewhere.

# Acknowledgments
{:numbered="false"}

The direction this extension reverses — an authorization server that proffers
rather than demands — is the "requesting party policy" claim of
{{UMAClaims2010}}, and this document is its descendant. {{IEEE7012}} supplied the
pattern, the three representations, the single-choice rule and the dual-record
requirement, and the divergences in {{privacy-considerations}} are stated in its
terms rather than around them.
