---
title: "AAuth Agent Tokens as Agent Credentials for User-Managed Access (UMA) 2.0 for Autonomous Agents"
abbrev: "AAuth Agent Credentials for UMA"
docname: draft-gamb-uma4agents-aauth-00
date: 2026-09-15
category: info
submissiontype: IETF
ipr: trust200902
area: Security
keyword: [UMA, authorization, AAuth, agents, identity, credential]
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
  RFC9864:
  I-D.hardt-oauth-aauth-protocol:
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
informative:
  I-D.hardt-aauth-protocol:
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

This document specifies how an authorization server implementing the UMA 2.0
profile for autonomous agents accepts an AAuth agent token as the credential
of an identified agent: how the token is verified, how the agent's standing
connection is named from it, and how a sub-agent's parent is read from it.
Nothing else of AAuth is used. The grant, the challenge and the enforcement of
the profile are unchanged by an agent identifying itself this way.

--- middle

# Introduction

{{U4ACore}} Section 5.1 lets a client present itself at one of two levels: by
a bare key, or by a credential from an issuer that binds an identity to a key.
It does not say which credentials; several serve. This document specifies one
of them, the agent token of {{I-D.hardt-oauth-aauth-protocol}}: a JWT an agent
provider signs, binding an `aauth:local@domain` identifier to the key in its
`cnf` claim.

AAuth also defines access modes, tokens a resource issues, and a person server
that federates with an access server. None of those are used here. The
profile's grant is UMA's, decided by the owner's authorization server; what
AAuth contributes is a way for the agent to say who it is that the
authorization server can verify for itself.

Agents are in use with tokens shaped by more than one revision. This document
accepts the token as {{I-D.hardt-oauth-aauth-protocol}} defines it and as the
revisions of {{I-D.hardt-aauth-protocol}} before it did. The two shapes prove
the same thing — an Ed25519 key, bound by its issuer to a subject — and differ
in what they name: the current one names the algorithm `Ed25519` {{RFC9864}}
and requires `dwk`, `jti` and `iat`; earlier ones name `EdDSA` and did not all
require those claims.

## Relationship to the Set

This document is an OPTIONAL part of the set of {{U4ACore}} Section 1.3. Its
identifying URI is `https://u4a.ai/spec/aauth/1.0`.

## Notational Conventions

{::boilerplate bcp14-tagged}

# The Agent Token {#agent-token}

A client presenting itself at the identified level with an AAuth agent token
carries it in the `agent_token` header of the agreement JWS of {{U4ATerms}}
Section 4.1.

## Verification {#verification}

The authorization server MUST verify the token against the keys its issuer
publishes, and MUST refuse it unless:

- its header carries `typ` of `aa-agent+jwt` and an `alg` of `Ed25519` or
  `EdDSA`;
- `iss` is an `https` origin the deployment has configured it to believe, and
  `dwk`, where present, is `aauth-agent.json`;
- the document at `{iss}/.well-known/aauth-agent.json` carries an `issuer`
  equal to `iss` by exact comparison, where it carries one;
- the key at that document's `jwks_uri` whose `kid` is the header's — or, where
  the header names none, the only key there — is an Ed25519 key, names the
  header's `alg` or no algorithm, and verifies the token;
- `sub` and `exp` are present, `exp` is in the future, and a `sub` of the form
  `aauth:local@domain` has the host of `iss` as its domain;
- `cnf.jwk` is present and is an Ed25519 key.

A token whose `alg` is `Ed25519` MUST also carry `dwk`, `jti` and `iat`, and
both the issuer's key and `cnf.jwk` MUST name `Ed25519`, as
{{I-D.hardt-oauth-aauth-protocol}} requires.

The authorization server MUST NOT fetch anything from an issuer it has not
been configured to believe. It MUST NOT fetch an issuer's key set more often
than once a minute, and an attempt that failed counts toward that bound as one
that succeeded does. A token naming a `kid` the set it holds does not contain
is the occasion to fetch it again, within that bound; it is how a rotation is
noticed.

The key in `cnf.jwk` is the key that signed the agreement, and the key the
grant is confirmed to. The authorization server MUST verify the agreement's
signature with the algorithm that key names, or `EdDSA` where it names none,
and MUST NOT take the algorithm from the agreement's own header.

## The Connection Handle {#handle}

The connection handle is formed from `sub` and `iss` as {{U4ACore}} Section 5.1
specifies, and MUST NOT be derived from the key. An `aauth:local@domain`
subject from an issuer whose identifier is `https://domain` already ends in
the suffix that rule appends, so its handle is the subject itself; from an
issuer whose identifier carries a port or a path it does not, and the suffix
is appended. The agent provider binds a fresh key each session; the subject is
what persists.

## Sub-Agents {#sub-agents}

A token carrying `parent_agent` is a sub-agent's, and the claim names its
parent. The authorization server MUST refuse a `parent_agent` that is not an
agent identifier under the same domain as `sub`, or that equals `sub`. An
authorization server implementing {{U4ALineage}} reads the claim as that
document's Section 2.2 specifies. The parent's connection handle is formed
from `parent_agent` and `iss` as {{handle}}.

# Security Considerations

The considerations of {{U4ACore}} and {{I-D.hardt-oauth-aauth-protocol}} apply.

## Issuers Are Trusted by Dereference

{{verification}} resolves an issuer over TLS and believes the keys it
publishes, and only for an issuer the deployment named. An agent token is a
provider vouching for an agent; a provider anyone may stand up vouches for
nothing, and an authorization server that fetched from whatever issuer a
token named would also be one any requester could make fetch a URL of its
choosing. The issuer comparison is what stops a document served at one host
from speaking for the keys of another.

## Algorithms Come From the Key

A verifier that lets a token's header choose the algorithm it is verified with
has let the token choose whether it is verified. The header's `alg` here is
checked against the key, and the key against its type and curve.

{{RFC9864}} deprecated the polymorphic `EdDSA` because the name alone does not
say which curve. That ambiguity is closed here by the key, which MUST be an
Ed25519 key whatever it names, so accepting `EdDSA` from an earlier issuer
admits no second operation.

## Revocation Reaches the Next Token

An agent provider that withdraws an agent stops issuing it tokens. A token it
already issued stays valid at the authorization server until its `exp`, so the
lifetime the provider gives its tokens is how long a withdrawal takes to reach
the authorization server. The owner's standing connection with the agent is
hers, and is not ended by the provider; she revokes it herself.

## What a Verified Token Establishes

A verified agent token establishes that its issuer vouches for this subject
holding this key. It establishes nothing about what the agent may do: the
owner's terms, her policy and her approval decide that, exactly as for an agent
presenting a bare key. The identity level changes how the connection is named
and nothing about how it is judged.

# Privacy Considerations

The considerations of {{U4ACore}} apply. An agent token names its subject to
every authorization server it is presented to, which is the identified level's
purpose; an agent that does not wish to be named presents at the pseudonymous
level, and this document changes nothing about that.

# IANA Considerations

This document makes no request of IANA. The media type `aa-agent+jwt` and the
`parent_agent` claim are defined by {{I-D.hardt-oauth-aauth-protocol}}.

--- back

# Implementation Status {#implementation-status}

This section records the status of known implementations in the sense of
{{?RFC7942}}, and is to be removed before publication as an RFC.

The reference implementation {{U4ALAB}} verifies agent tokens as {{verification}}
specifies, with a unit test for each refusal and for each shape, including a
token minted by the Python `aauth` package. Its identified agents enroll with
an independent implementation, Christian Posta's AAuth person server, pinned
at a fixed upstream revision, which issues tokens in the earlier shape. A check
runs the same negotiation for an agent presenting such a token and for agents
presenting a bare key, asserts that the terms and the grant are identical
across them, and asserts that an agent the person server has withdrawn is
issued no fresh token.

# Acknowledgments
{:numbered="false"}

{{I-D.hardt-oauth-aauth-protocol}} supplied the agent credential this document
accepts.
