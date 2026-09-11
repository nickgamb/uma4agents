---
title: "AAuth Binding for User-Managed Access (UMA) 2.0 for Autonomous Agents"
abbrev: "AAuth Binding for UMA"
docname: draft-gamb-uma4agents-aauth-00
category: std
submissiontype: IETF
ipr: trust200902
area: Security
keyword: [UMA, authorization, AAuth, agents, binding, proof-of-possession]
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
  RFC7519:
  RFC8693:
  RFC9421:
  RFC9728:
  I-D.hardt-aauth-protocol:
  I-D.hardt-httpbis-signature-key:
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
  U4ATerms:
    title: "Owner-Proffered Terms for User-Managed Access (UMA) 2.0"
    author:
      - ins: N. Gamb
        name: Nick Gamb
      - ins: E. Maler
        name: Eve Maler
    date: 2026
    seriesinfo:
      Internet-Draft: draft-gamb-uma4agents-terms-00
    target: https://u4a.ai/spec/draft-gamb-uma4agents-terms-00.html
  U4AFedAuthz:
    title: "Federated Authorization for Autonomous Agents"
    author:
      - ins: N. Gamb
        name: Nick Gamb
      - ins: E. Maler
        name: Eve Maler
    date: 2026
    seriesinfo:
      Internet-Draft: draft-gamb-uma4agents-fedauthz-00
    target: https://u4a.ai/spec/draft-gamb-uma4agents-fedauthz-00.html
informative:
  U4ALineage:
    title: "Agent Lineage for User-Managed Access (UMA) 2.0"
    author:
      - ins: N. Gamb
        name: Nick Gamb
      - ins: E. Maler
        name: Eve Maler
    date: 2026
    seriesinfo:
      Internet-Draft: draft-gamb-uma4agents-lineage-00
    target: https://u4a.ai/spec/draft-gamb-uma4agents-lineage-00.html
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

This document binds the UMA 2.0 profile for autonomous agents to the AAuth
protocol: the agent credential AAuth issues is the identified-agent credential
of the profile, AAuth's HTTP message signature conventions are its proof of
possession, the requesting party token is an AAuth authorization token, and a
resource may publish its structure in AAuth's resource metadata beside RFC
9728. AAuth's four-party access mode is the topology the profile runs.

--- middle

# Introduction

{{I-D.hardt-aauth-protocol}} defines agent identity bound to a session key, a
signature convention over HTTP requests, and four access modes, of which the
fourth — federated, where an authorization server the resource names decides
— is the topology of {{U4ACore}}. What AAuth leaves to the authorization
server is how it knows the owner's policy. That is what the profile supplies.

The two compose without either bending. AAuth's resource token and UMA's
permission ticket are the same object minted on opposite sides — both
produced at a refused access, both naming what was attempted, both a pointer
to the authority that could grant it. The difference is where the state sits:
AAuth's is minted by the resource, UMA's by the owner's authorization server
when the resource registers the attempt. For a grant that can wait on an
absent owner, only the second has anywhere to keep the pending request, and
this binding uses it.

## Relationship to the Set

This document is a binding of {{U4ACore}} in the sense of its Section 1.3.
Its identifying URI is `https://u4a.ai/spec/aauth/1.0`.

## Notational Conventions

{::boilerplate bcp14-tagged}

# The Identified Agent {#agent}

A requesting agent presenting itself at the identified level of {{U4ACore}}
Section 5.1 under this binding carries an AAuth agent credential — a JWT
{{RFC7519}} with `typ` of `aa-agent+jwt` — in the `agent_token` header of the
agreement JWS of {{U4ATerms}} Section 4.1.

The authorization server MUST:

- refuse a credential whose `iss` does not use the `https` scheme;
- resolve the issuer's keys through the agent server metadata AAuth publishes
  at `/.well-known/aauth-agent.json` under the issuer, following its
  `jwks_uri`, and verify the credential against them, selecting by `kid`
  where one is present;
- refuse a credential carrying no `cnf.jwk`;
- treat `cnf.jwk` as the key that signed the agreement and that the grant is
  confirmed to.

The connection handle is the credential's `sub`, qualified by the host of its
`iss` as `sub@host`, and MUST NOT be derived from the key. AAuth binds a fresh
key per session; the subject is what persists.

Where the credential carries an `act` claim {{RFC8693}} naming another agent's
subject, an authorization server implementing {{U4ALineage}} reads it as that
document's Section 2.2 specifies. Nothing further is defined.

# Proof of Possession {#pop}

The message signature profile of {{U4ACore}} Section 6.1 — {{RFC9421}} over
`@method`, `@authority`, `@path` and `authorization` — is AAuth's convention
as {{I-D.hardt-httpbis-signature-key}} describes it, with two constraints this
binding adds.

The signature label MUST be `sig1`. The `alg` parameter MUST be `ed25519`,
and every key this binding mints or verifies is an Ed25519 key in OKP form;
an implementation MAY accept other algorithms from third-party issuers whose
keys it fetches, choosing the permitted algorithms from the key's type and
never from the token's own header.

# The Grant {#grant}

The requesting party token of {{U4ACore}} Section 7.1 is issued as an AAuth
authorization token: a JWT with `typ` of `aa-auth+jwt`, its `cnf.jwk` naming
the agent's key, and the `permissions`, `owner` and `contract` claims the
profile requires. `sub` is the agent credential's `sub`, or the literal
`aauth:pseudonymous-agent` for an agent at the pseudonymous level.

~~~ json
{
  "iss": "https://alice-as.example",
  "sub": "advisory-agent@ps.example",
  "owner": "alice",
  "aud": "https://rs.example",
  "jti": "rpt_3f9c1a7e2b4d",
  "exp": 1789433600,
  "cnf": {"jwk": {"kty": "OKP", "crv": "Ed25519", "x": "…"}},
  "permissions": [{
    "resource_id": "alice-vault/get_positions",
    "resource_scopes": ["positions:read"],
    "exp": 1789602800
  }],
  "contract": "s256:mNTA0Zjg1YTBkYzQxZWY4YjkyMWM4ZGIy"
}
~~~
{: title="A requesting party token under this binding."}

An enforcement point verifies possession against `cnf.jwk` as returned by
introspection, as {{U4ACore}} Section 8.2 step 3.

# Resource Metadata {#metadata}

A resource MAY publish, at `/.well-known/aauth-resource.json`, the same
structural facts its {{RFC9728}} document carries, in AAuth's encoding:

resource:
: The resource identifier, as {{RFC9728}}.

access_mode:
: `four-party`.

access_servers:
: The authorization servers the owner names; the same array as
  `authorization_servers`.

jwks_uri:
: The resource's keys, as {{RFC9728}}.

r3_vocabularies:
: An array of vocabularies, each with `format`, an `operations` array naming
  each operation and its `resource_scopes`, and a `digest` that is `s256`
  over the canonical serialization of `operations` with keys sorted.

owner_resources_endpoint:
: The protected listing of {{U4AFedAuthz}} Section 2.2. The same URL as in
  the RFC 9728 document.

signed_metadata:
: A JWT over the document with `typ` of `aauth-resource+jwt`, signed by a key
  at `jwks_uri`.

Both documents MUST be generated from one registry of the resource's
operations. The instance layer beneath them, and the permission ticket, do not
change with the encoding: `owner_resources_endpoint` points at one listing.

The content digest gives the operation surface a stable identifier that no
owner's instances appear in. A vocabulary describes what the resource's
operations are; the owner's terms describe what she permits; they compose, and
neither absorbs the other.

# The Challenge {#challenge}

This binding uses the HTTP challenge of {{U4ACore}} Section 3.2 unchanged.
AAuth's own challenge header is not used; the permission ticket already
carries what AAuth's resource token would, minted on the side that can hold a
pending request.

# Security Considerations

The considerations of {{U4ACore}} and {{I-D.hardt-aauth-protocol}} apply.

## Issuers Are Trusted by Dereference

{{agent}} resolves an issuer over TLS and believes the keys it publishes.
{{U4ACore}} Section 5.1 requires a deployment to say which issuers it will
believe, and this binding does not relieve it of that.

## Algorithms Come From the Key

{{pop}}. A verifier that lets a token's header choose the algorithm it is
verified with has let the token choose whether it is verified.

# Privacy Considerations

The considerations of {{U4ACore}} apply. An agent credential names its
subject to every authorization server it is presented to, which is the
identified level's purpose; an agent that does not wish to be named presents
at the pseudonymous level and this binding changes nothing about that.

# IANA Considerations

This document makes no request of IANA. The media types `aa-agent+jwt`,
`aa-auth+jwt` and `aauth-resource+jwt` are defined by
{{I-D.hardt-aauth-protocol}}.

--- back

# Implementation Status {#implementation-status}

This section records the status of known implementations in the sense of
{{?RFC7942}}, and is to be removed before publication as an RFC.

The reference implementation {{U4ALAB}} runs this binding against the AAuth
reference person server, pinned at a fixed upstream revision, for its
identified-agent path, and serves both metadata encodings of {{metadata}}
from one registry. A check runs the same negotiation at both identity levels
and asserts that the terms, the grant and the authority named are identical
across them.

# Acknowledgments
{:numbered="false"}

{{I-D.hardt-aauth-protocol}} supplied the agent identity and signature
conventions this binding composes with, and the observation that a resource
token and a permission ticket are one object minted on opposite sides.
