---
title: "User-Managed Access (UMA) 2.0 Profile for Autonomous Agents"
abbrev: "UMA 2.0 for Agents"
docname: draft-gamb-uma4agents-core-00
category: std
submissiontype: IETF
ipr: trust200902
area: Security
keyword: [UMA, authorization, agents, delegation, proof-of-possession]
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
  RFC6749:
  RFC6750:
  RFC7515:
  RFC7517:
  RFC7519:
  RFC7638:
  RFC7662:
  RFC8414:
  RFC9396:
  RFC9421:
  RFC9530:
  RFC9728:
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
  UMAFedAuthz:
    title: "Federated Authorization for User-Managed Access (UMA) 2.0"
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
    target: https://docs.kantarainitiative.org/uma/wg/rec-oauth-uma-federated-authz-2.0.html
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
  RFC9635:
  RFC9449:
  I-D.ietf-oauth-rar-metadata-remediation:
  I-D.ietf-oauth-identity-assertion-authz-grant:
  I-D.meunier-webbotauth-httpsig-protocol:
  I-D.meunier-webbotauth-registry:
  I-D.ietf-oauth-client-id-metadata-document:
  I-D.hardt-aauth-protocol:
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
  U4AOwner:
    title: "The Resource Owner's API for User-Managed Access (UMA) 2.0"
    author:
      - ins: N. Gamb
        name: Nick Gamb
      - ins: E. Maler
        name: Eve Maler
    date: 2026
    seriesinfo:
      Internet-Draft: draft-gamb-uma4agents-owner-00
    target: https://u4a.ai/spec/draft-gamb-uma4agents-owner-00.html
  U4AAAuth:
    title: "AAuth Binding for User-Managed Access (UMA) 2.0 for Autonomous Agents"
    author:
      - ins: N. Gamb
        name: Nick Gamb
      - ins: E. Maler
        name: Eve Maler
    date: 2026
    seriesinfo:
      Internet-Draft: draft-gamb-uma4agents-aauth-00
    target: https://u4a.ai/spec/draft-gamb-uma4agents-aauth-00.html
  U4AMCP:
    title: "Model Context Protocol Binding for User-Managed Access (UMA) 2.0"
    author:
      - ins: N. Gamb
        name: Nick Gamb
      - ins: E. Maler
        name: Eve Maler
    date: 2026
    seriesinfo:
      Internet-Draft: draft-gamb-uma4agents-mcp-00
    target: https://u4a.ai/spec/draft-gamb-uma4agents-mcp-00.html
  UMAClaims2010:
    title: "Simple Access Authorization Claims"
    author:
      - ins: E. Maler
        name: Eve Maler
      - ins: P. Bryan
        name: Paul Bryan
    date: 2010-04
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

This document profiles and extends the User-Managed Access (UMA) 2.0 Grant so
that an autonomous software agent, operated by a party who is not the resource
owner, can negotiate access to that owner's resources while the owner is not
present.

It narrows UMA 2.0 in one place and extends it in several. The requesting side
is an agent identified by a key it proves possession of rather than by a client
credential; the requesting party token is a proof-of-possession token carrying
its permissions as a claim; a grant may be bound to a single operation and spent
exactly once; the owner holds a standing, revocable relationship with each agent
individually; and the challenge that begins a negotiation is specified as a set
of parameters rather than as an HTTP header, so that an enforcement point with no
status line can emit it.

--- middle

# Introduction

UMA 2.0 {{UMAGrant}} describes a topology that almost nothing else has: the
party who authorizes access is not the party operating the client, and the
authorization server holds the owner's policy rather than the resource server's.
That arrangement was designed for a person sharing a resource with another
person. It turns out to be the arrangement an agent economy needs, because the
question an agent economy has to answer is not "is this my agent doing my task"
but "may your agent touch my resource".

What UMA 2.0 assumes, and what this profile changes, is everything downstream of
that topology. The requesting side is assumed to be a registered OAuth client
operated by a human who can be redirected to a browser. An agent is neither. It
holds a key rather than a client secret, it may have no prior relationship with
the authorization server at all, and the owner it needs an answer from may be
asleep.

This profile is written against a reference implementation {{U4ALAB}} in which
every requirement below is exercised by an automated check.
{{implementation-status}} says what that implementation covers and where the
register of requirement-to-check mappings lives.

## Design Rule

The rule this profile was written under, and the reason its surface is as small
as it is: **stay inside UMA 2.0's wire surface wherever it already fits, and
make every departure explicit.** `WWW-Authenticate: UMA`, the `uma-ticket` grant
type, `need_info`, `request_submitted` and the introspection `permissions` array
are all used as specified. {{profiles-and-extensions}} is the complete list of
departures; anything not named there is intended to be stock UMA 2.0.

## Relationship to Other Authorization Work

This profile is an extension grant on OAuth 2.0 {{RFC6749}}, as UMA 2.0 is.

GNAP {{RFC9635}} is the more interesting comparison, and in several respects the
better carrier: its interaction model is more general than OAuth's, key binding
is native rather than an extension, and its request format expresses what a
client wants far better than a scope string. What GNAP does not decide is whose
policy the answer expresses. It negotiates between a client and the resource
owner reachable through that client's own interaction, and has no notion of a
second principal who is not the requester, is not present, and whose policy must
be satisfied anyway — nor of that principal proffering terms the requesting side
must sign. Those two are the whole of this work. A GNAP binding of this profile
would be a reasonable document and probably a cleaner one than the OAuth-shaped
binding here; it is not a substitute for it.

DPoP {{RFC9449}} solves the same problem as {{proof-of-possession}} for the
OAuth installed base. This profile uses {{RFC9421}} instead because the signature
must cover the request rather than only bind the token, and because the same
mechanism authenticates four different parties here, in both directions. A DPoP
binding is a reasonable second binding and would recruit a different set of
implementers.

## Specification Set

This document is the core of a set. {{U4ATerms}} and {{U4AFedAuthz}} are REQUIRED
to implement alongside it; this document together with those two constitutes the
UMA 2.0 profile for autonomous agents.

{{U4APolicy}}, {{U4ALineage}}, {{U4AMultiParty}} and {{U4AOwner}} are OPTIONAL
extensions of this document. {{U4AMCP}} binds this profile to a transport and
{{U4AAAuth}} to an agent identity and signature layer; other bindings are
possible and this document is written so that they are.

## Roles

The roles of {{UMAGrant}} apply, with the following additions and narrowings.

Requesting agent:
: The software making the request. UMA used this term in 2010 {{UMAClaims2010}}
  and dropped it; the agent era makes the distinction load-bearing again. A
  requesting agent is individuated by a key it proves possession of, and is
  distinct from the requesting party, who is accountable for it and is not
  present. Nothing in this profile lets the requesting agent be the responsible
  party; it lets the agent be the acting one.

Operator:
: The party that runs a requesting agent and publishes a directory of the keys
  its agents hold. The operator is a party the owner may act against as a whole
  — see {{U4APolicy}} — and is never an authorization input on its own.

Enforcement point:
: The component that discharges the resource-server obligations of
  {{UMAFedAuthz}}: holding the protection API access token, obtaining a
  permission ticket, introspecting, and refusing. {{UMAFedAuthz}} Section 1.4
  divides responsibility between *parties* and names no component, and this
  profile keeps it that way. An enforcement point MAY be a gateway in front of
  the resource, or the resource itself. It is a role, not a product.

## Notational Conventions

{::boilerplate bcp14-tagged}

Base64url encoding is as defined in {{RFC7515}} Section 2, without padding.

The notation `s256(x)` denotes the string `"s256:"` followed by the base64url
encoding, without padding, of the SHA-256 digest of the octets `x`.

The notation `jkt(k)` denotes the string `"jkt:"` followed by the JWK Thumbprint
{{RFC7638}} of the JSON Web Key `k`. The value after the prefix is the same
thumbprint DPoP {{RFC9449}} carries in its `jkt` confirmation method; the prefix
marks it as a handle rather than a confirmation.

# Authorization Server Metadata

An authorization server conforming to this profile publishes OAuth 2.0
Authorization Server Metadata {{RFC8414}}, extended by {{UMAGrant}} Section 2 and
by this document.

The authorization server MUST include in its metadata the value
`https://u4a.ai/spec/core/1.0` in the `uma_profiles_supported` array, and MUST
include the identifying URI of each extension in this set that it implements.
{{UMAGrant}} Section 4 asks a profile to be given a uniquely identifying URI and
asks a server supporting one to advertise it; this profile's URIs are listed in
{{iana-considerations}}.

The following metadata member is added:

terms_endpoint:
: OPTIONAL. The URL of the owner's terms roster, as defined in {{U4ATerms}}. An
  authorization server implementing {{U4ATerms}} MUST include it.

An authorization server MUST NOT advertise a grant type or claim token format it
will not accept, and MUST advertise every grant type and claim token format it
will. This is not pedantry about completeness: a requesting agent that has never
met this authorization server decides from this document alone what to attempt,
and an unadvertised-but-accepted format is indistinguishable to it from an
unsupported one.

# The Challenge {#the-challenge}

## Parameters, Not a Header {#challenge-parameters}

{{UMAGrant}} Section 3.2 requires the resource server to return an HTTP 401 with
a `WWW-Authenticate: UMA` header. This profile requires the *parameters* and
lets each binding say how they travel.

An enforcement point MUST convey the following parameters when it refuses a
request for want of authorization:

realm:
: REQUIRED. As {{RFC6750}}.

error:
: REQUIRED. The value `insufficient_authorization`.

as_uri:
: REQUIRED. The issuer identifier of the authorization server that decides
  access to this resource for this owner.

ticket:
: REQUIRED. The permission ticket, as {{UMAGrant}}.

resource_metadata:
: REQUIRED. The URL of the protected resource metadata document {{RFC9728}} that
  describes this resource, as {{RFC9728}} Section 5.1. An enforcement point
  MUST name the document for the resource identifier the request was made
  to, formed as {{RFC9728}} Section 3 forms it, and not the document of
  another identifier the same resource is reachable by; a client following
  the pointer is required by {{RFC9728}} Section 3.3 to reject any other.

scope:
: OPTIONAL. A space-delimited list of the scopes that would satisfy the attempted
  access, as {{RFC6750}} Section 3.

authorization_remediation:
: REQUIRED. See {{remediation}}.

A binding of this profile MUST define how these parameters are carried, and MUST
carry all of those marked REQUIRED. The HTTP binding is given in
{{challenge-http}}; {{U4AMCP}} defines a binding for a transport that has no
status line to decorate.

The reason for the narrowing is that mandating the header excludes the
deployments most likely to adopt this profile. An enforcement point running
in-process inside the resource returns a domain result, not a status line; a
JSON-RPC method handler has nowhere to put a `WWW-Authenticate`. Both encodings
run in the reference implementation against one authorization server, and one
requesting agent reads both.

## The HTTP Binding {#challenge-http}

Over HTTP, an enforcement point MUST return `401 Unauthorized` with a
`WWW-Authenticate` header whose auth-scheme is `UMA` and whose auth-params are
the parameters of {{challenge-parameters}}:

~~~
HTTP/1.1 401 Unauthorized
WWW-Authenticate: UMA realm="alice-vault",
  error="insufficient_authorization",
  as_uri="https://alice-as.example",
  ticket="MWRlNzE4ZjgtMGY0OS00NDg2",
  resource_metadata="https://rs.example/.well-known/
    oauth-protected-resource/mcp",
  scope="trades:execute",
  authorization_remediation="eyJhdXRob3JpemF0aW9uX2RldGFpbHMi..."
~~~
{: title="A challenge over HTTP. Line breaks are for display only."}

## Structured Remediation {#remediation}

`authorization_remediation` is the parameter of
{{I-D.ietf-oauth-rar-metadata-remediation}}, carrying the same base64url-encoded
JSON object that draft defines, with two additional members. The object has:

authorization_details:
: REQUIRED. An array of authorization detail objects {{RFC9396}} describing what
  was attempted.

authorization_reference:
: REQUIRED. `s256` over the canonical JSON serialization of
  `authorization_details`, with object keys sorted and no insignificant
  whitespace.

authorization_server:
: REQUIRED by this profile. The issuer identifier of the authorization server
  that decides. Same value as the `as_uri` parameter.

ticket:
: REQUIRED by this profile. Same value as the `ticket` parameter.

~~~ json
{
  "authorization_details": [{
    "type": "urn:uma4agents:authorization-details:tool-call",
    "locations": ["https://rs.example"],
    "identifier": "alice-vault/execute_trade",
    "actions": ["execute_trade"],
    "datatypes": ["trades:execute"]
  }],
  "authorization_reference": "s256:6cR6qTmCj6s0S95MxCfdfwfXJ8m",
  "authorization_server": "https://alice-as.example",
  "ticket": "MWRlNzE4ZjgtMGY0OS00NDg2"
}
~~~
{: title="A decoded authorization_remediation object."}

Those two additional members are what make a decision by a third party possible.
{{I-D.ietf-oauth-rar-metadata-remediation}} hands the client a template to submit
to *its own* authorization server, which cannot work when the resource belongs to
someone else and the client's authorization server has no standing to grant.
Naming the owner's authorization server, and handing back a ticket rather than a
template, is the whole of the difference: the client authors nothing and cannot
widen what it was given.

Emitting the {{RFC9396}} vocabulary costs an enforcement point nothing, since it
already knows the resource identifier and the scopes, and buys three things. A
client that implements {{I-D.ietf-oauth-rar-metadata-remediation}} can read most
of the challenge without knowing UMA. A downstream policy engine receives typed
fields rather than only a digest. And `authorization_reference` lets a client
holding many grants decide whether it already has one for this shape without
parsing the details.

## Corroborating the Authorization Server {#corroboration}

A requesting agent MUST fetch the document named by `resource_metadata`, MUST
verify that its `resource` member identifies the resource being accessed as
required by {{RFC9728}} Section 3.3, and MUST refuse a challenge whose `as_uri`
does not appear in that document's `authorization_servers` array.

Without this, the only statement of which authorization server decides is an
unauthenticated header on a refused request. With it, the challenge gains a
second witness anchored in the resource's own TLS-protected origin. The challenge
remains authoritative for the ticket, which is the one value the metadata
document cannot carry.

# The Negotiation

The requesting agent presents the ticket at the authorization server's token
endpoint using the `urn:ietf:params:oauth:grant-type:uma-ticket` grant type, as
{{UMAGrant}} Section 3.3.1. This profile does not change the grant type, the
ticket's single-use rotation, or the meaning of `need_info`,
`request_submitted`, `request_denied` or `invalid_grant`.

## Claim Token Formats

Where {{UMAGrant}} lets the authorization server name acceptable claim token
*formats*, this profile additionally lets it proffer the claim's *content*. That
extension is specified in {{U4ATerms}} and is REQUIRED to implement.

An authorization server MAY accept other claim token formats alongside it. One is
worth naming because it is the case an enterprise deployment reaches for first:
an identity assertion authorization grant
{{I-D.ietf-oauth-identity-assertion-authz-grant}} MAY be accepted as a
`claim_token` with `claim_token_format` of
`urn:ietf:params:oauth:token-type:id-jag`, in which case the authorization server
MUST treat it as a claim about identity and reach, and MUST NOT treat it as
conferring access.

Presenting the same assertion as a `jwt-bearer` grant would have the identity
provider's assertion produce the access token directly, which makes the identity
provider the deciding party over a resource it does not own. An identity
assertion proves who an agent acts for and carries no entitlement of its own,
which is what a UMA claim is for. Where both are demanded, identity is demanded
first, because which terms apply follows from which party the agent acts for.

## Responses

The authorization server's responses are those of {{UMAGrant}} Section 3.3.1.
Two are constrained by this profile.

A `request_submitted` response indicates that the owner has been asked and has
not yet answered. The authorization server MUST distinguish two kinds of pending
request, and MUST make the kind available to the owner's decision surface:

connection:
: The requesting agent has no standing relationship with this owner. The question
  put to the owner is whether to have one. See {{connections}}.

operation:
: The requesting agent has a standing relationship, and the owner's policy
  requires her to answer for this particular access.

A `request_denied` response MAY carry an `error_description`. Where the refusal
was reached without evaluating the owner's policy — because a quota was exhausted
or the operator was blocked — the authorization server SHOULD say so, so that a
well-behaved requesting agent can distinguish a refusal it might overcome from
one it cannot.

## Waiting

`request_submitted` is a state to render, not a call to hold open. A requesting
agent that can express waiting to its own user SHOULD hand the wait up rather
than block, and a binding SHOULD define how. The decision belongs to the owner
either way; what changes is whether the requesting party's client hangs on it.

A binding that surfaces the wait MUST be able to say that the party being waited
on is not the requesting party's own user, and that the requesting agent's client
MUST NOT attempt to satisfy the wait from that user. A wait that cannot name its
subject will be answered by the wrong person.

# The Requesting Agent {#requesting-agent}

## Identity Levels {#identity-levels}

A requesting agent presents itself at exactly one of two levels. The level
determines the shape of the standing connection handle and nothing else.

Pseudonymous:
: The agent presents a bare public JWK {{RFC7517}}. The key is the identity. The
  connection handle is `jkt(k)`.

Identified:
: The agent presents a credential from an issuer asserting its identity and
  binding it to a key — for example an `aa-agent+jwt` as defined by
  {{I-D.hardt-aauth-protocol}}, whose `cnf.jwk` is the signing key. The
  authorization server MUST verify that credential against keys published by its
  issuer, MUST require that the issuer identifier use the `https` scheme, and
  MUST derive the connection handle from the issuer and subject rather than from
  the key.

The handle for an identified agent MUST NOT be derived from its key. Issuers that
attest agents commonly bind a fresh key per session; a thumbprint-keyed
relationship forgets such an agent on every run, which presents to the owner as
an agent she has approved asking to be approved again. This was found by running
it.

Which issuers an authorization server will believe is deployment policy, not a
wire-protocol rule. This profile deliberately specifies no issuer allow-list, and
a deployment MUST supply one.

## Descriptive Metadata {#descriptive-metadata}

A requesting agent MAY additionally present descriptive metadata, so that an
owner who has never met it can be told something true about it:

- a client identifier that is an `https` URL resolving to a client ID metadata
  document {{I-D.ietf-oauth-client-id-metadata-document}}, which the
  authorization server MUST resolve and MUST reject unless the document's own
  `client_id` matches the URL it was fetched from;
- a `Signature-Agent` {{I-D.meunier-webbotauth-registry}} naming a directory of
  keys the operator publishes, which MUST be covered by the request signature
  where it is present.

Neither is an authorization input. The key that verifies a request is always the
one confirmed by the grant, the connection handle is unchanged by the presence or
absence of either, and an authorization server MUST NOT admit a request it would
otherwise refuse on the strength of descriptive metadata alone. Failure to
resolve descriptive metadata MUST leave the request where it was rather than
refusing it; an operator's outage is not evidence about an agent.

A metadata document proves only that it claims its own URL. Anyone can publish
one, so resolving it establishes a name to display and nothing more. What raises
the metadata above a name is the operator directory, which the agent does not
control — see {{U4APolicy}}.

# Proof of Possession {#proof-of-possession}

The requesting party token issued under this profile is a proof-of-possession
token. A requesting agent MUST prove possession of the confirmed key on every
request to the protected resource, and an enforcement point MUST verify it.

## The Message Signature Profile {#signature-profile}

Proof of possession uses HTTP Message Signatures {{RFC9421}}.

A signature MUST cover at least the components `"@method"`, `"@authority"`,
`"@path"` and `"authorization"`. A signer MAY cover more, and a verifier MUST
accept a superset rather than requiring an exact set.

Requiring an exact list is the intuitive implementation and it is wrong. It makes
this profile and {{I-D.meunier-webbotauth-httpsig-protocol}} unable to coexist on
one request, because each adds a component the other did not expect. Covering
`"authorization"` is the security property; an exact list was never one.

A verifier MUST reconstruct the signature base using the `@authority` value it is
configured with, and MUST NOT take it from the `Host` header or from any
forwarded header. An authority read from the request is an authority the caller
chose. This is a security rule and a portability rule with one cause: an
enforcement point that recovers its authority from the routing layer breaks
silently when the routing layer changes, with signatures failing to verify for a
reason nothing in its logs names.

A verifier MUST echo the received `@signature-params` value verbatim when
reconstructing the base, rather than re-serializing it from parsed components.

## Covering the Body {#content-digest}

Where a request carries meaning in its body, the signature MUST cover a
`Content-Digest` {{RFC9530}} header, and the verifier MUST recompute the digest
from the received body as well as verifying the signature over it.

The four required components say who is asking and what they are asking of. They
say nothing about the bytes. That is adequate for a request whose meaning is in
its URL and unsafe for one whose meaning is in its body — and the endpoints where
an owner says yes or no are exactly the latter. Without this, an intermediary can
leave the signature untouched and change the word.

These are two obligations, not one. Recomputing the digest from the received body
without reading the header is safe and is not conformant, and would reject any
third-party signer whose serialization differs. A verifier MUST be able to
*require* the digest rather than merely accept it when present, since a signer
that omits it must not thereby escape the check.

# The Grant {#the-grant}

## The Requesting Party Token {#rpt}

On success the authorization server responds as {{UMAGrant}} Section 3.3.5, with
`token_type` of `PoP`:

~~~ json
{
  "access_token": "eyJ0eXAiOiJhYS1hdXRoK2p3dCIsImFsZyI6...",
  "token_type": "PoP",
  "expires_in": 3600
}
~~~

The requesting party token MUST be a JWT {{RFC7519}} signed by the authorization
server, and MUST carry:

cnf:
: REQUIRED. A confirmation claim whose `jwk` member is the public key the
  requesting agent must prove possession of. This is the key that signed the
  claim token, and the key the enforcement point verifies requests against.

permissions:
: REQUIRED. The array defined by {{UMAFedAuthz}} Section 5.1.1 — each element
  carrying `resource_id`, `resource_scopes` and OPTIONAL `exp`, `iat` and `nbf` —
  carried here as a claim rather than being visible only through introspection.

owner:
: REQUIRED. The resource owner on whose behalf this token was issued. See
  {{owner-scoped}}.

A bearer requesting party token is a credential that works for whoever picks it
up, which is an unreasonable thing to hand software that makes thousands of calls
across networks it does not control. Carrying `permissions` inline lets an
enforcement point see what was granted without a round trip; introspection
remains the authority on whether the grant is still live, which is a different
question and the one that changes.

## Operation Binding and Single Use {#operation-binding}

Where the owner's policy requires her to approve a particular access rather than
a class of access, the authorization server MUST bind the grant to that access.
Such a token MUST carry:

single_use:
: REQUIRED. Boolean `true`.

operation:
: REQUIRED. An object with a `tool` member naming the operation and a
  `params_s256` member carrying `s256` over the canonical JSON serialization of
  the exact parameters approved, with object keys sorted.

~~~ json
{
  "single_use": true,
  "operation": {
    "tool": "execute_trade",
    "params_s256": "s256:mNTA0Zjg1YTBkYzQxZWY4YjkyMWM4ZGIy"
  }
}
~~~

Classic OAuth and UMA scopes authorize classes of action. "She approved this
trade" and "she authorized trading" are different facts, and a protocol with only
scopes can express the second. This is the narrowest useful addition that
expresses the first.

# Enforcement {#enforcement}

## Obligations, Not a Topology {#obligations}

{{UMAFedAuthz}} gives the resource server a list of obligations and never names
the component that discharges them. This profile states them as a conformance
profile that any resource-side implementation may satisfy.

An enforcement point MUST hold a protection API access token issued in the
owner's name, MUST register attempted access to obtain a permission ticket, MUST
introspect a presented token before allowing a call, and MUST refuse by default.
Whether it is a gateway, a service mesh filter, a framework middleware, or the
resource itself is out of scope.

Naming a topology here would exclude in-process deployments, which are the
resource-side implementations most likely to adopt this profile.

## Ordering {#ordering}

An enforcement point MUST perform the following steps in this order, and the
order is normative:

1. Introspect the presented token, without consuming it, and establish that it is
   active and that the relationship behind it still stands.
2. Establish that the resource being accessed appears in `permissions` with a
   scope that covers the attempted access.
3. Verify proof of possession against the key named by `cnf` in the introspection
   response.
4. Where the token carries `single_use`, establish that the attempted operation
   matches `operation.tool` and that `s256` over the received parameters equals
   `operation.params_s256`.
5. Consume the token.

An enforcement point MUST NOT consume a single-use token before step 5.

Consuming at step 1 is the intuitive placement and it is a denial of service.
Anyone who observes the token can replay it with a garbage signature: the replay
is correctly refused, and the grant is already spent, so the one legitimate call
— the operation the owner personally approved seconds earlier — then fails. An
attacker who cannot forge a signature can still destroy the grant.

An enforcement point MUST verify proof of possession against the key returned by
introspection rather than the key carried inside the token, so that a token
accepted at step 1 and a key trusted at step 3 come from the same answer.

## Indivisibility {#indivisibility}

A single-use artifact — a permission ticket, or a token carrying `single_use` —
MUST be consumed by an operation that decides and records in one indivisible
step, and that reports to its caller whether that caller was the one that
consumed it. A caller told that it was not MUST refuse the request.

A read followed by a write is correct in one process and wrong the moment there
are two. Two callers read `consumed = false`, both are told yes, and one
owner-approved action is performed twice. The failure is silent, it appears only
under replication, and it cannot be tested for in a single-process deployment —
which is where the specification has to carry it, because the implementation will
not.

{{UMAGrant}} Section 3.3.1 says a permission ticket is single-use and does not say
where in enforcement it is spent, nor what "single-use" means when the
authorization server has more than one replica. Both are stated here.

## Introspection Responses {#introspection}

An authorization server MUST include, in an introspection response {{RFC7662}}
whose `active` member is `false`, an `error` member naming the reason. At minimum
it MUST distinguish a reason that further negotiation cannot change from one that
it can.

An enforcement point receiving a reason of the first kind MUST refuse without
issuing a fresh challenge. A bare `{"active": false}` sends a requesting agent
around a negotiation whose outcome the owner has already settled, which wastes
the agent's time and puts a request in front of the owner that she has already
answered.

# Standing Connections {#connections}

A connection is the standing relationship an owner has with one requesting agent,
keyed by the handle of {{identity-levels}}.

An authorization server implementing this profile MUST:

- refuse to grant, and instead put the request to the owner as a `connection`
  pending request, where no active connection exists for the requesting agent's
  handle, whatever the owner's policy would otherwise decide;
- record the connection when the owner approves, retaining at least the handle,
  the identity level, and the time of first contact;
- offer the owner an operation that ends a connection, and on that operation
  invalidate every live requesting party token issued under it in the same
  indivisible step that ends the connection;
- retain the fact that a connection was previously ended, across any later
  re-establishment of a connection with the same handle.

A revocation that ends the relationship and then fails to invalidate the tokens
leaves the agent holding exactly the authority the owner just withdrew, which is
why the two are one step and not two.

Retaining the prior revocation matters because the owner's policy may read it
(see {{U4APolicy}}), and a counter that an agent can clear by asking again is not
a fact about the agent.

The persisted claims token of {{UMAGrant}} is the closest ancestor of this
construct. What is added is that the relationship is visible to the owner and
revocable by her individually, rather than being state the authorization server
keeps for its own convenience.

# The Owner's Own Credential {#owner-authentication}

{{UMAGrant}} says nothing about how the resource owner authenticates to her own
authorization server, because in its deployments the authorization server
belonged to a service that already had a session with her. Here it is hers,
and the question has to be answered.

An authorization server MUST accept at least one of the following as the
owner's credential on every owner-facing operation, and MAY accept both:

- an access token from an identity provider the owner has designated, verified
  against that provider's published keys;
- an {{RFC9421}} signature over the request from a key the owner enrolled, under
  the profile of {{signature-profile}}, with the `Content-Digest` requirement of
  {{content-digest}} on any request carrying a body.

Each accepted credential MUST be independently sufficient and independently
revocable, and MUST NOT be a fallback for another. An authorization server MUST
NOT hold a static owner credential of its own.

The second form is what lets the owner's authority be reached by something she
runs — a personal agent on her own device — without a browser session and
without an identity provider in the path. It is the same message-signature
profile the requesting agent uses, pointed the other way. Every handler MUST act
on the owner the credential proved rather than on one the request named. What
that software can ask her authority to do is specified in {{U4AOwner}}.

# Owner-Scoped Artifacts {#owner-scoped}

A resource server serves resources belonging to more than one owner, and each of
those owners may name a different authorization server. Every artifact in this
profile that is scoped to an owner MUST carry or resolve to that owner:

- the permission ticket, which MUST resolve only at the authorization server that
  minted it;
- the requesting party token, through its `owner` claim;
- the resource identifier;
- the protected resource metadata document {{RFC9728}}, which MUST be
  per-resource and whose `authorization_servers` array names that owner's choice.

**The authorization server named in a challenge is the owner's choice, and two
owners of one resource server MAY name two different ones.** This is a
conformance property of an implementation, testable from outside, and not a
deployment style.

Nothing in {{UMAGrant}} prevents a resource server from naming one authorization
server for every owner it serves. Such a deployment is conformant, is
multi-tenant, and has quietly lost the property the cross-principal topology
exists for: the authority is the operator's again, and the owner's policy is a
row in the operator's table. One sentence distinguishes the two, so the
specification should carry it.

Where a resource is reachable at more than one URL, each URL is a distinct
resource for the purposes of {{RFC9728}}, and each metadata document MUST name
the URL it was fetched from. {{RFC9728}} Section 3.3 has a client reject a
document whose `resource` is not the resource it is accessing, so serving one
canonical document at an alias hands every client at that alias a document it is
required to reject. Aliases are resources too.

# Profiles and Extensions {#profiles-and-extensions}

This document is both a profile and an extension of {{UMAGrant}} in the sense of
its Section 4: it restricts UMA's available options in two places and defines new
use of its extensibility points in several.

The complete list of departures from {{UMAGrant}} and {{UMAFedAuthz}} follows.
Anything not named here, in this document or in another document of this set, is
intended to be stock UMA 2.0.

| # | Departure | Baseline | Where specified |
|---|---|---|---|
| 1 | The authorization server proffers claim *content*, dereferenceable and counter-signed | The server names acceptable claim formats | {{U4ATerms}} |
| 2 | Proof-of-possession requesting party token carrying `permissions` as a claim | Bearer token; permissions visible only through introspection | {{rpt}} |
| 3 | `operation` and `single_use` claims | Per-permission scopes and expiry only | {{operation-binding}} |
| 4 | Owner intervention as two kinds of pending request | Resource-owner intervention out of scope | {{connections}} |
| 5 | A standing connection keyed by an identity handle, owner-visible and owner-revocable | Nothing directly; the persisted claims token is the ancestor | {{connections}} |
| 6 | Discovery in more than one binding encoding from one registry, and challenge corroboration | Metadata documents predate this; the challenge carries `as_uri` on faith | {{corroboration}}, {{U4AFedAuthz}} |
| 7 | Public metadata stays structural; owner-bound instances served only to the owner's authority | The resource server pushes owner-bound registrations under the protection token | {{U4AFedAuthz}} |
| 8 | The challenge is a set of parameters; each binding says how they travel | `WWW-Authenticate` is mandated | {{challenge-parameters}} |
| 9 | Enforcement obligations stated as a conformance profile, not a component | Obligations named, host unnamed | {{obligations}} |
| 10 | Consumption ordering normative; introspection carries a reason | Unspecified where a single-use token is spent | {{ordering}}, {{introspection}} |
| 11 | Descriptive agent metadata, display only | The agent is its key, or its issuer's token | {{descriptive-metadata}} |
| 12 | Structured remediation in the challenge, plus the two members that let a third party decide | The challenge carries `as_uri` and `ticket` | {{remediation}} |
| 13 | A resource server introduces itself to an owner's authority by signing as its own origin | How a resource server comes to hold a protection token is unspecified | {{U4AFedAuthz}} |
| 14 | Every owner-scoped artifact carries its owner; the authority is the owner's choice | One authorization server per protected resource, owner implicit in the deployment | {{owner-scoped}} |
| 15 | A depth limit on the owner's pending queue, in two lanes | No opinion on how many pending requests an owner may be made to hold | {{U4APolicy}} |
| 16 | Owner-side refusal at operator granularity | No notion of the party operating a requesting agent | {{U4APolicy}} |
| 17 | Assurance may only tighten; only the owner's own decisions may relax | No vocabulary for either | {{U4APolicy}} |
| 18 | An agent holding a connection may introduce a sibling, which then negotiates its own grant | No object between "a stranger" and "the same client" | {{U4ALineage}} |
| 19 | A layer above the resource owner that may only narrow | The resource rights administrator is named and given no wire surface | {{U4AMultiParty}} |
| 20 | Several owners of equal standing, with signed verdicts carried in the grant | Exactly one authorization server per protected resource | {{U4AMultiParty}} |
| 21 | The owner's own credential to her authorization server: a designated identity provider, an enrolled key, or both, each independently sufficient | Silent on how the owner authenticates | {{owner-authentication}} |
| 22 | The owner's API: the surface through which her portal, her tools or her own agent operate her authorization server | Left to the deployment | {{U4AOwner}} |
{: title="Departures from UMA 2.0."}

# Security Considerations

The considerations of {{UMAGrant}} Section 5 and {{UMAFedAuthz}} Section 7 apply.
The following are specific to this profile.

## Authorization Inputs Never Come From the Transport

The signature base is reconstructed from the enforcement point's configuration
and from the credential presented, never from the routing layer that delivered
the request. See {{signature-profile}}. An authority taken from a header is an
authority the caller can choose.

## Consumption Is Ordered and Last

See {{ordering}}. The failure this prevents is not forgery — it is destruction.
An observer who cannot forge a signature can still spend a grant, if the grant is
spent before the signature is checked.

## Single Use Must Survive Replication

See {{indivisibility}}. An implementation that is correct on one replica and
wrong on two is the normal outcome of reading this requirement as "spend it
once", and the resulting double-spend is silent.

## Descriptive Metadata Is Not Authorization

See {{descriptive-metadata}}. A client ID metadata document proves that it claims
its own URL and nothing further; a key directory proves that whoever controls
that origin published a key. Treating either as an authorization input means that
anyone able to publish a document can influence a decision. An implementation
that displays a resolved name to the owner should expect that name to be the
thing an implementer reaches for when writing policy, and must refuse it there.

## Issuers Are Trusted by Dereference

An authorization server that verifies an identified agent's credential resolves
the issuer over TLS and believes the keys it publishes. TLS on the issuer origin
is the trust root, which is why non-`https` issuers are refused. This profile
specifies no allow-list of issuers; a deployment MUST supply one, and a
deployment that does not has delegated the question of which parties may attest
agents to the DNS.

## Revocation Is Atomic

See {{connections}}. Ending a relationship and invalidating the grants under it
are the same decision and MUST be the same operation.

## A Truncated Request Must Fail Closed

Where an enforcement point receives a request body that an intermediary may have
truncated, it MUST refuse with a reason naming the truncation. A cut-off
structured body does not parse, so the operation being attempted disappears from
a request that was merely padded. Deny-by-default catches this and misreports it,
which means the deployment learns nothing from a log full of unknown-operation
refusals.

## The Resource Server Must Not Read the Owner's Policy

This is the cross-principal property the whole profile exists for, and it is
structural rather than advisory: the protection API is scoped to a token the
owner authorized, and it carries no operation that returns her policy. An
implementation SHOULD be able to demonstrate the paired assertion — that the
enforcement point is refused the owner's policy and allowed her published keys,
on the same origin.

## Not Addressed

Signing-key rotation is possible through published key sets and is not exercised
by the reference implementation. Revocation propagation between authorization
servers that do not share state is out of scope. {{RFC9728}} permits an array of
authorization servers per resource and this profile is written for one.

# Privacy Considerations

The considerations of {{UMAGrant}} Section 6 apply. The following are specific to
this profile.

## Public Metadata Is Structural

Which resources a named person owns MUST NOT be published at an unauthenticated
URI. {{U4AFedAuthz}} specifies the split: the public document describes the
resource's shape, and whose instances sit behind it is served only to the
authority that owner named.

## The Record Names a Counterparty

An authorization server implementing this profile keeps a record of what was
promised, decided and done, and that record names the requesting agent. It is
the owner's record of her own decisions and it is also a per-agent history, which
is a more sensitive object than either half. Retention is deployment policy; this
profile requires only that a decision the owner did not personally take MUST NOT
be recorded as one she did.

## A Stated Purpose Is Not Evaluated

Where a requesting agent states why it wants access, the authorization server
records it and shows it to the owner. It MUST NOT parse it, compare it to the
purpose in the owner's terms, or let it affect the decision other than by its
absence. An authority that reads a stated purpose and rules on whether it is
plausible has put a judgement about natural language inside an authorization
decision, which makes the same request answerable two ways. See {{U4ATerms}} and
{{U4APolicy}}.

# IANA Considerations {#iana-considerations}

## Profile Identifiers

{{UMAGrant}} Section 4 asks that a profile or extension be given a uniquely
identifying URI and that an authorization server supporting one advertise it in
`uma_profiles_supported`. There is no IANA registry for these; they are recorded
here.

| Document | Identifying URI |
|---|---|
| This document | `https://u4a.ai/spec/core/1.0` |
| {{U4ATerms}} | `https://u4a.ai/spec/terms/1.0` |
| {{U4AFedAuthz}} | `https://u4a.ai/spec/fedauthz/1.0` |
| {{U4APolicy}} | `https://u4a.ai/spec/policy/1.0` |
| {{U4ALineage}} | `https://u4a.ai/spec/lineage/1.0` |
| {{U4AMultiParty}} | `https://u4a.ai/spec/multiparty/1.0` |
| {{U4AOwner}} | `https://u4a.ai/spec/owner/1.0` |
| {{U4AMCP}} | `https://u4a.ai/spec/mcp/1.0` |
| {{U4AAAuth}} | `https://u4a.ai/spec/aauth/1.0` |
{: title="Profile identifying URIs."}

## JSON Web Token Claims Registration

IANA is asked to register the following in the "JSON Web Token Claims" registry
established by {{RFC7519}}.

Claim Name:
: `permissions`

Claim Description:
: Permissions granted to the requesting party, as defined by {{UMAFedAuthz}}
  Section 5.1.1

Change Controller:
: IETF

Specification Document(s):
: {{rpt}} of this document

Claim Name:
: `owner`

Claim Description:
: The resource owner on whose behalf a token was issued

Change Controller:
: IETF

Specification Document(s):
: {{owner-scoped}} of this document

Claim Name:
: `single_use`

Claim Description:
: Whether the token may be spent exactly once

Change Controller:
: IETF

Specification Document(s):
: {{operation-binding}} of this document

Claim Name:
: `operation`

Claim Description:
: The single operation and parameter digest a token is bound to

Change Controller:
: IETF

Specification Document(s):
: {{operation-binding}} of this document

## Authorization Details Type Registration

IANA is asked to register the following in the "OAuth Authorization Server
Metadata" sub-registry for authorization details types established by
{{RFC9396}}.

Type Name:
: `urn:uma4agents:authorization-details:tool-call`

Type Description:
: An attempted invocation of one named operation on a protected resource

Change Controller:
: IETF

Specification Document(s):
: {{remediation}} of this document

## OAuth Authorization Server Metadata Registration

IANA is asked to register the following in the "OAuth Authorization Server
Metadata" registry established by {{RFC8414}}.

Metadata Name:
: `terms_endpoint`

Metadata Description:
: URL of the resource owner's terms roster

Change Controller:
: IETF

Specification Document(s):
: {{U4ATerms}}

--- back

# Implementation Status {#implementation-status}

This section records the status of known implementations in the sense of
{{?RFC7942}}, and is to be removed before publication as an RFC.

## UMA for Agents Reference Implementation

Organization:
: Independent

Description:
: A running deployment of this profile and the rest of its set: an authorization
  server, an enforcement point in two hosting shapes, a protected resource, an
  operator key directory, and requesting agents at both identity levels. It runs
  under container orchestration and on a single host, against both an in-memory
  and a replicated store. It carries two requesting-agent implementations that
  share no code — one in Python, one in TypeScript — which meet on the wire and
  nowhere else; the second was written from these documents rather than from
  the first, and found one defect in the enforcement point on its first run.

Level of maturity:
: Research. The implementation exists to establish that the requirements in this
  document can be met and to find the ones that cannot.

Coverage:
: Every normative requirement in this document is exercised by an automated
  check, except those addressed to deployments or to bindings rather than to this
  profile's own components. The register at
  https://u4a.ai/spec/conformance.yaml names, for each requirement, the check
  that verifies it and the assertion that check prints.

Licensing:
: Apache 2.0.

Contact:
: {{U4ALAB}}

Notes:
: Several requirements in this document exist because the intuitive
  implementation was written first and was wrong. {{ordering}}, {{indivisibility}},
  {{signature-profile}} and {{identity-levels}} each record a defect found by
  running the implementation rather than by reading the specification it was
  built from.

# Acknowledgments
{:numbered="false"}

This profile rests on {{UMAGrant}} and {{UMAFedAuthz}}, and on the decade of
Kantara UMA Work Group discussion behind them. The idea that a resource owner
might proffer terms rather than receive them appears in UMA's own 2010 work on
access authorization claims {{UMAClaims2010}}.

{{I-D.hardt-aauth-protocol}} supplied the agent identity and key-binding
mechanics this profile composes with, and the observation that its resource
token and UMA's permission ticket are the same object minted on opposite sides.
{{I-D.meunier-webbotauth-registry}} supplied the operator key directory.
{{I-D.ietf-oauth-rar-metadata-remediation}} supplied the remediation payload that
{{remediation}} extends by two members.
