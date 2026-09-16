---
title: "Federated Authorization for Autonomous Agents"
abbrev: "FedAuthz for Agents"
docname: draft-gamb-uma4agents-fedauthz-00
date: 2026-09-15
category: info
submissiontype: IETF
ipr: trust200902
area: Security
keyword: [UMA, authorization, federated, resource registration, discovery]
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
  RFC8414:
  RFC7662:
  RFC9421:
  RFC9530:
  RFC9728:
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
  I-D.hardt-aauth-protocol:
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

This document extends Federated Authorization for User-Managed Access (UMA) 2.0
in three places where the agent era exposes an assumption.

Resource registration becomes declarative: the resource server publishes its
structure in protected resource metadata and serves its owner-bound instances
only to the owner's authorization server, which pulls rather than being pushed
to. A resource server establishes its relationship with an owner's authorization
server by signing as the origin it serves, rather than by a credential somebody
had to provision at both ends. And the protection API's introspection response
says why a token is inactive, so an enforcement point can tell a refusal that
further negotiation might change from one it cannot.

--- middle

# Introduction

{{UMAFedAuthz}} separates the resource server from the authorization server so
that the owner's policy can live with a party the resource server does not
control. It then assumes the two are already acquainted: the resource server
holds a protection API access token (PAT), pushes descriptions of the owner's
resources under it, and asks it for permission tickets.

Each of those assumptions holds when one operator runs both sides and stops
holding when the authorization server is the owner's. Nobody can provision a
secret at both ends when the two ends belong to different people. Pushing
owner-bound resource descriptions requires the resource server to know, per
owner, which authorization server to push to. And a resource server that has
registered a resource with one owner's authority has published, to that
authority, which resources that named person owns — which the resource server
was in a position to know and the metadata document it publishes to the world
must not be.

This document keeps the direction {{UMAFedAuthz}} chose — the authorization
server is the owner's, and the resource server is its client — and specifies
the three things it left to deployment.

## Relationship to the Set

This document extends {{UMAFedAuthz}} and is REQUIRED to implement alongside
{{U4ACore}}. Its identifying URI is `https://u4a.ai/spec/fedauthz/1.0`.

## Notational Conventions

{::boilerplate bcp14-tagged}

# Discovery in Two Layers {#discovery}

Discovery is split by who may ask.

## The Public Layer {#public-layer}

A resource server MUST publish protected resource metadata {{RFC9728}} for each
resource it serves. That document describes the *structure* of the resource:
what operations it offers and with what scopes. It MUST NOT name which owners
have instances behind it.

This document adds two members to the metadata:

tool_surfaces:
: OPTIONAL. An array of objects, each with a `tool` member naming an operation,
  a `resource_scopes` member listing the scopes that operation requires, and an
  OPTIONAL `consequence` member declaring what performing it leaves behind.
  Structural only.

A resource server MAY declare a `consequence` for an operation. Where it does,
the value MUST be one of `reversible`, `compensatable`, `forward_recoverable`
or `irreversible`, ordered by how much remedy remains after the act, and the
declaration MUST be covered by `signed_metadata` so that a relayed copy stays
attributable to the party that made it.

The declaration is the resource server's because it is the party that would
have to undo the act. An authorization server MUST NOT read the absence of the
member as a declaration in either direction: an operation nobody has described
is undescribed, which is neither a claim that it is harmless nor evidence that
it is grave.

owner_resources_endpoint:
: REQUIRED. The URL of the protected listing of {{protected-layer}}.

The document MUST carry `signed_metadata` as {{RFC9728}} Section 2.2, signed by
a key published at the resource's own `jwks_uri`, so that a relayed copy stays
attributable to the resource.

A resource server MAY publish the same structural facts in more than one
encoding — for example the metadata of {{I-D.hardt-aauth-protocol}} alongside
{{RFC9728}} — from one registry. The instance layer beneath them, and the
permission ticket, do not change with the encoding.

## The Protected Layer {#protected-layer}

A resource server MUST serve, at `owner_resources_endpoint`, the owner-bound
resource instances it holds for one owner — their identifiers, names, and
scopes — and MUST serve them only to a request signed with {{RFC9421}} by the
authorization server that owner has named, verified against that authorization
server's published keys.

Where a resource server declares a `consequence` for an operation in
{{public-layer}}, it MUST carry the same declaration on that operation's entry
in this listing. This listing is what an authorization server reads into its
registry, and a class that appeared only in the public document would describe
the resource to clients while leaving the party that decides unable to read
it.

The signature profile is that of {{U4ACore}} Section 6.1, with `@authority` taken
from the resource server's configuration.

This is the privacy split. The public document says what the resource is; whose
things sit behind it is served only to the party the owner's own consent already
connected. Publishing the second at an unauthenticated URI is a disclosure that
push registration, for all its other costs, never made.

# Declarative Registration {#registration}

An authorization server implementing this document MUST be able to learn what a
resource server protects by fetching, and MUST NOT require the resource server
to push resource descriptions. The classic resource registration endpoint of
{{UMAFedAuthz}} Section 3 remains conformant and MAY be offered alongside.

To register a resource server's resources for an owner, the authorization
server:

1. fetches the resource server's protected resource metadata;
2. verifies `signed_metadata` against the keys at the document's `jwks_uri`, and
   verifies that the signed claims name this resource as `iss`;
3. sends a signed request to `owner_resources_endpoint`;
4. materializes its registry for that owner from the response, and removes any
   registration from that source for that owner that the response no longer
   carries.

One fetch replaces N registration calls, and there is one registry with one
writer.

## Staleness {#staleness}

The registry the authorization server holds may lag what the resource server
serves. When a permission request names a resource identifier the authorization
server does not hold, it MUST attempt a fresh pull before answering
`invalid_resource_id`.

This is the mirror of what {{UMAFedAuthz}} asked of the resource server —
noticing `invalid_resource_id` after an authorization server restart and
re-pushing — placed with the party that can act on it without a round trip.

## Liveness {#liveness}

The pull and its verification form a call cycle: the authorization server
fetches from the resource server, and the resource server authenticates that
fetch by dereferencing the authorization server's published keys. An
authorization server MUST NOT condition its own readiness on the pull having
completed, and a resource server verifying a signed request MUST either tolerate
a live back-call to the authorization server or verify against keys it already
holds.

Gating readiness on "my registry is populated" deadlocks: the authorization
server will not serve its keys until it has pulled, and the resource server will
not serve the pull until it has the keys. The general form is that in a profile
where two parties authenticate each other by dereference, neither party's
liveness may be conditioned on the exchange completing.

# Establishment {#establishment}

{{UMAFedAuthz}} Section 1.4 requires that the PAT be issued with the resource
owner's authorization, and says nothing about how the resource server comes to
be a client of the authorization server at all. Where one operator runs both
sides, a provisioned client credential models that gap adequately. Where the
authorization server is the owner's, nobody is in a position to configure both
ends.

## Registration by Origin {#rs-register}

A resource server MAY introduce itself to an owner's authorization server by
sending a request naming the owner and the resource it serves, signed with
{{RFC9421}} using a key published at the origin of that resource.

The request MUST carry a `Content-Digest` {{RFC9530}} covered by the signature.

~~~
POST /rs/register HTTP/1.1
Host: alice-as.example
Content-Type: application/json
Content-Digest: sha-256=
  :Tmn1PBTGYjBHkU9XV2NHLt2YstMuZTPQqpEBaE28JJM=:
Signature-Input: sig1=("@method" "@authority" "@path"
  "authorization" "content-digest");created=1789430000;
  keyid="rs-1";alg="ed25519"
Signature: sig1=:bbN8ISG...:

{
  "owner": "alice",
  "resource_uri": "https://rs.example/mcp/alice",
  "name": "Meridian Vault"
}
~~~
{: title="A resource server registering by origin signature. Line breaks are for display only."}

The authorization server MUST verify the signature by:

1. fetching the protected resource metadata for `resource_uri` from that
   resource's own origin;
2. refusing unless the document's `resource` equals `resource_uri`, its
   `jwks_uri` is same-origin with `resource_uri`, and its `authorization_servers`
   names this authorization server;
3. fetching the keys at `jwks_uri` and verifying the signature against them.

A resource server that cannot be reached, or whose document fails any of the
three checks, MUST be refused. This is a deliberate departure from how an
authorization server treats an operator's key directory, where an unreachable
document leaves an agent's claim where it was. There, the document attests a
claim already made by other means. Here, the document *is* the credential, and a
credential that cannot be fetched has not been presented. A profile that reuses
the attestation language here has specified an authentication that fails open.

## The Answer Is the Owner's {#pending}

A verified signature settles who is asking and nothing else. On success the
authorization server MUST respond `202 Accepted` with a body carrying
`status` of `pending` and `error` of `authorization_pending`, MUST record the
resource server in the owner's registry as pending, and MUST issue no PAT until
the owner has approved it.

~~~ json
{
  "client_id": "https://rs.example",
  "status": "pending",
  "error": "authorization_pending",
  "error_description": "the owner has been asked"
}
~~~

The `client_id` of a resource server registered this way is its origin.

Registration reaches an owner; it MUST NOT create one. The signature proves
control of an origin and says nothing about whether the owner named beside it
exists. An authorization server that seeds an owner on demand has turned an
unauthenticated endpoint into unbounded state.

## Obtaining the PAT {#pat}

Once the owner has approved, the resource server obtains a PAT with the
`client_credentials` grant {{RFC6749}} and `scope` of `uma_protection`, as
{{UMAFedAuthz}} Section 1.5, authenticating in the same way it registered: by an
{{RFC9421}} signature over the token request, verified against keys at the
origin it registered as. Which authentication applies — a provisioned secret or
an origin signature — is a property of the stored registration, so that a
resource server registered by signature cannot later fall back to guessing a
secret.

While the owner has not answered, the token endpoint MUST respond `403` with
`error` of `authorization_pending`. After the owner has revoked the resource
server, it MUST respond `403` with `error` of `access_denied`.

## Withdrawal {#withdrawal}

The owner MUST be able to revoke a resource server, and on revocation the
authorization server MUST stop honouring that resource server's PAT on every
protection API call, from every replica, at once.

A resource server that registers again after being revoked MUST land in the
pending state, not the active one. A second request is not a reversal of the
owner's first decision, and re-registration MUST NOT be a way to undo a
withdrawal.

# Introspection Reasons {#introspection}

An authorization server MUST include, in an introspection response {{RFC7662}}
whose `active` member is `false`, an `error` member. The following values are
defined:

`expired`:
: The token's lifetime has passed.

`invalid_signature`:
: The token did not verify.

`unknown_token`:
: The token was not issued by this authorization server, or its record is gone.

`already_consumed`:
: A single-use token has been spent.

`connection_revoked`:
: The owner has ended the standing relationship under which this token was
  issued. See {{U4ACore}} Section 9.

`revoked`:
: The token was invalidated when the owner ended the relationship it was issued
  under, and a relationship with the same agent has since been re-established.
  The token stays inactive; a grant under the new relationship is negotiated
  afresh.

Of these, `connection_revoked` is terminal: an enforcement point receiving it
MUST refuse without issuing a fresh challenge, because renegotiation cannot
change an outcome the owner has settled. The others MAY be answered with a
fresh challenge.

An extension MAY define further values. {{U4AMultiParty}} defines
`organization_revoked`.

## Non-Consuming by Default {#non-consuming}

Introspection MUST NOT consume a single-use token. Consumption is a separate
operation, taken by the enforcement point as the last step of enforcement, as
{{U4ACore}} Section 8.2. An authorization server MUST offer that operation at
the URL it advertises as `consume_endpoint` in its metadata, MUST require the
protection API access token on it as on introspection, and it MUST report to
its caller whether that caller was the one that consumed the token.

The request carries the token as introspection does; the response is a JSON
object with a `consumed` member. `true` means this caller spent the token;
`false` means it was already spent, or was not a single-use token, and MUST be
accompanied by an `error` member saying which.

# Reporting Allowed Access {#audit}

An enforcement point SHOULD report each call it allows to the authorization
server, naming the negotiation it was made under and what was reached, so that
the owner's record holds what was done alongside what was promised.

An enforcement point MUST NOT be told, and MUST NOT report, the identity handle
of the client. The authorization server resolves it from the
negotiation. The enforcement point is the resource server's component, and the
owner's record of which agent did what is not the resource server's to hold.

# Security Considerations

The considerations of {{UMAFedAuthz}} Section 7 apply.

## An Endpoint That Dereferences Will Dereference What It Is Told

{{rs-register}} carries no credential the authorization server issued; the
signature checked against the origin's own published document is the
credential. Any caller can therefore cause an outbound fetch to a host they
name. An authorization server MUST bound the response size it will read, MUST
NOT follow redirects, MUST require `https`, and SHOULD keep a short memory of
resources that did not check out so that a flood of registrations is not a flood
of fetches.

The bound this document deliberately does not require is an address blocklist. A
resource server legitimately sits on a private range whenever it is deployed
near its owner's authority, so refusing those would break the honest case and
not the dishonest one. Naming the hosts an authorization server may reach is an
egress policy and belongs to the deployment.

## The Owner's Policy Is Not on the Protection API

The protection API is scoped to the PAT, and it carries no operation that
returns the owner's policy. An implementation SHOULD be able to demonstrate that
the enforcement point is refused the owner's policy and is allowed her published
keys, on the same origin.

## Revocation Reads the Store

{{withdrawal}} requires that a revoked PAT stop working on every replica at
once, which means the resource server's status MUST be read on each protection
API call rather than cached in process. A revocation that reached only the
replica that served the request would leave the others honouring a credential
the owner had just withdrawn.

# Privacy Considerations

The considerations of {{UMAFedAuthz}} Section 8 apply.

The split in {{discovery}} exists because the alternative is a disclosure. A
public document listing the resources a named person owns is readable by anyone
who can guess its URL, and a resource server serving many owners has published a
directory of them. The structural layer says nothing about any person; the
instance layer is served only to the authority that person named, and that
authority already knew.

# IANA Considerations

This document has no IANA actions. The identifiers it uses are listed in
{{used-identifiers}}.

--- back

# Identifiers Used by This Document {#used-identifiers}

This appendix lists the identifiers this document defines. It is informative and
requests no registration.

| Name | Kind | Meaning | Defined in |
|---|---|---|---|
| `tool_surfaces` | Protected resource metadata {{RFC9728}} | Operations the resource offers, each with the scopes it requires | {{public-layer}} |
| `owner_resources_endpoint` | Protected resource metadata {{RFC9728}} | URL of the protected listing of owner-bound resource instances | {{protected-layer}} |
| `consume_endpoint` | Authorization server metadata {{RFC8414}} | URL of the operation that spends a single-use requesting party token | {{non-consuming}} |
| `error` | Token introspection response {{RFC7662}} | Why an inactive token is inactive | {{introspection}} |
{: title="Identifiers used by this document."}

# Implementation Status {#implementation-status}

This section records the status of known implementations in the sense of
{{?RFC7942}}, and is to be removed before publication as an RFC.

The reference implementation {{U4ALAB}} implements this document in full. Both
registration methods — declarative pull and the classic push endpoint of
{{UMAFedAuthz}} — were built against an otherwise identical stack and measured
before push was retired to a preserved branch. The deadlock of {{liveness}} and
the fail-open reading that {{rs-register}} warns against were both found by
running it.

# Acknowledgments
{:numbered="false"}

This document rests on {{UMAFedAuthz}}, whose separation of resource server from
authorization server is the arrangement everything here depends on.
{{RFC9728}} supplied the public half of discovery, and the observation that a
resource may name its authorization servers is what made the split in
{{discovery}} possible.
