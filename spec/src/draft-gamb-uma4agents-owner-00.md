---
title: "The Resource Owner's API for User-Managed Access (UMA) 2.0"
abbrev: "Owner API for UMA"
docname: draft-gamb-uma4agents-owner-00
date: 2026-09-15
category: info
submissiontype: IETF
ipr: trust200902
area: Security
keyword: [UMA, authorization, resource owner, personal AI, agents]
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
  RFC8414:
  RFC9421:
  RFC9530:
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
informative:
  SSE:
    title: "Server-Sent Events"
    author:
      - org: WHATWG
    date: 2026
    target: https://html.spec.whatwg.org/multipage/server-sent-events.html
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

This document specifies the interface a resource owner uses to operate her
own User-Managed Access (UMA) 2.0 authorization server: to answer the requests
that wait on her, to see and end her relationships with clients and
with the operators behind them, to write the policy and terms her server
decides from, and to read the record of what it did.

UMA 2.0 leaves this surface to the deployment, which was right when the
authorization server belonged to a service she had a session with. When the
server is hers, the surface is what makes it hers: it is how a portal, a
command line, or a personal agent running on her own device acts for her, and
a surface only one vendor's portal can reach is a server only that vendor
operates.

--- middle

# Introduction

Every requirement in the rest of this set is placed on the authorization
server, the enforcement point, or the client. The one party they
serve has no wire surface of her own in UMA 2.0 {{UMAGrant}}. The owner's
decisions arrive through whatever the deployment built.

That was adequate while the authorization server was operated by a service
the owner already had an account with. {{U4ACore}} Section 11 makes the
server the owner's choice, and {{U4ACore}} Section 10 specifies how she
authenticates to it — including with a key she holds, so that software she
runs can act for her with nobody else in the path. This document is the rest
of that: what such software can ask her server to do.

The reference implementation {{U4ALAB}} has three clients of this surface —
a browser portal, a command-line tool, and a personal AI holding her device
key — and one server behind them.

## Relationship to the Set

This document is an OPTIONAL extension of {{U4ACore}} and depends on
{{U4ATerms}} and {{U4APolicy}}. Its identifying URI is
`https://u4a.ai/spec/owner/1.0`.

## Notational Conventions

{::boilerplate bcp14-tagged}

# Discovery and Authentication {#discovery}

An authorization server implementing this document MUST advertise the base
URL of the owner's API in its metadata {{RFC8414}}:

owner_endpoint:
: REQUIRED. The URL under which the operations of this document are served.

Every operation below is relative to `owner_endpoint`. Every operation MUST
require the owner's credential as {{U4ACore}} Section 10, and MUST act on the
owner that credential proved rather than on any owner the request names.

Where the credential is an {{RFC9421}} signature, the signature base is the one
{{U4ACore}} Section 6.1 specifies, with the `authorization` component covering
the empty string when no `Authorization` header is sent, and MUST cover a
`Content-Digest` {{RFC9530}} on every request that carries a body. The
operations that carry a body are the ones that decide something; a body
that can be altered under a valid signature turns an approval into a refusal
without leaving a mark.

Request and response bodies are JSON. An error is reported with a 4xx status
and a JSON object whose `detail` member is a sentence the owner can be shown.

# The Queue {#queue}

## Listing {#pending}

`GET /pending` returns the requests waiting on the owner, as an array. Each
element MUST carry:

family:
: The negotiation identifier ({{U4APolicy}} Section 8.1).

kind:
: `connection` or `operation` ({{U4ACore}} Section 4.2).

tier:
: The policy unit the request falls under.

purpose, prohibited:
: From the terms the requesting side signed.

operation, reason, mission:
: What the requesting side authored in its agreement, where it did
  ({{U4ATerms}} Section 4.3). `reason` MUST be carried verbatim, unescaped and
  unparsed; it is the one field here the counterparty wrote, and a surface
  SHOULD render it as text.

identity:
: The verified identity record: its level, and what was resolved about the
  operator, as {{U4ACore}} Section 5.

assurance, assurance_notes:
: The axes of {{U4APolicy}} Section 4.1, and one sentence per axis saying what
  was checked, so that a surface has the sentence to show beside the level.

because:
: The rule conditions that caused the request to wait, where a rule did.

handle:
: The client's connection handle, or null before first contact.

organization:
: Where a layer above the owner had a say ({{U4AMultiParty}}), what it said,
  separately from her own rules.

## Deciding {#decision}

`POST /pending/{family}/decision` with a body `{"decision": "approved"}` or
`{"decision": "denied"}` answers one request.

The authorization server MUST record the decision in one indivisible step that
reports whether this call was the one that decided it, as {{U4ACore}}
Section 8.3; a second answer to a decided request MUST be refused with 404.
Two portals open on the same request are two callers, and the tap that lands
second must not be recorded as a second decision.

Where the credential proves someone acting for the owner rather than the
owner ({{U4AMultiParty}} Section 2.7), the decision MUST be recorded as
theirs.

# Relationships {#relationships}

## Agents {#connections}

`GET /connections` returns every standing connection ({{U4ACore}} Section 9),
each carrying its `handle`, `identity`, `label`, `status`, `first_seen`,
`last_access`, the policy units the owner personally approved it at, the units
it has been granted at, its revocation count, and where another agent
introduced it, that agent's handle.

`POST /connections/{handle}/revoke` ends one. The response carries
`rpts_deactivated` — how many live grants the revocation invalidated in the
same step — and `connections_revoked`, how many connections the revoked one
had introduced and which ended with it. Both numbers are the owner's evidence
that the revocation reached everything it should have.

## Operators {#operators}

`GET /operators` returns every operator the owner's server has met, assembled
from her connections rather than kept as a registry: each with its `origin`,
a display `name`, how many `agents` of its she has connections with and how
many are `active`, whether it is `blocked` and since when, and whether it is
`mine` — one she has claimed as her own — and since when.

`POST /operators/block` and `POST /operators/unblock`, with a body
`{"origin": "https://…"}`, are the operations of {{U4APolicy}} Section 7. The
block response carries `connections_revoked` and `rpts_deactivated`.

`POST /operators/claim` and `POST /operators/disclaim`, with the same body,
are the operations of {{U4APolicy}} Section 5. An origin MUST use the `https`
scheme; a claim of anything else MUST be refused.

## Resource Servers {#resource-servers}

`GET /resource-servers` returns every resource server that holds, or has
asked for, protection API access in the owner's name ({{U4AFedAuthz}}
Section 4): its `client_id`, `name`, `resource_uri`, `status` of `pending`,
`active` or `revoked`, how it authenticates, and when it registered. A stored
client secret MUST NOT be returned.

`POST /resource-servers/decision` with `{"client_id": …, "decision":
"approved"}` or `"revoked"` answers a registration or withdraws one. The
`client_id` travels in the body because a resource server registered by its
origin is identified by an `https` URL, which survives neither a path segment
nor a proxy that normalises a doubled slash.

# Policy {#policy}

## Resources {#resources}

`GET /resources` returns every resource the owner's server protects, joined
with the policy unit governing it: `_id`, `name`, `type`, `resource_scopes`,
the unit's identifier and name, its `ask_me`, and how the resource was
registered. A resource an organization shares with her rather than one she
owns carries `shared_by` naming the organization, since the two are not the
same thing and the difference decides what happens when she leaves.

## Units and Terms {#units}

`GET /policies` returns the owner's policy units keyed by identifier, each in
the shape {{U4APolicy}} Section 2 describes, with the terms document currently
proffered for it ({{U4ATerms}} Section 2).

`POST /policies` creates a unit from a body carrying `id`, `name`,
`resources`, `ask_me`, `rules` and `terms`. The server MUST refuse a unit over
a resource it does not protect, over a resource another unit already governs,
or whose rules fail the validation of {{U4APolicy}} Section 3, and MUST say
which in `detail`.

`PUT /policies/{id}` edits one: `ask_me`, `rules`, and the `purpose`,
`expires_in`, `prohibited` and `scope` of its terms. Resources are fixed by
registration and MUST NOT be editable here. Every edit MUST produce a new
terms version ({{U4ATerms}} Section 2.1); the response carries the unit as
stored, and where a layer above the owner narrowed what she wrote, a
`clamped` array of sentences saying what moved ({{U4AMultiParty}}
Section 2.4).

`DELETE /policies/{id}` removes one. Its resources become ungoverned, which
is denied ({{U4APolicy}} Section 2); the response names them. Published
terms versions MUST NOT be deleted with it.

## Vocabulary {#vocabulary}

`GET /policy-vocabulary` returns the conditions a rule may name, as an array
of objects each carrying `condition` (the name, with its level where the
condition is one sentence per level), `takes` (`duration`, `count` or null),
`label` (the sentence shown to the owner), and `may_relax`. This is the
publication {{U4APolicy}} Section 3.4 requires; a surface that offers the
owner a condition it does not list will compose a rule the server refuses.

# The Record {#record}

`GET /ledger` returns the record of {{U4APolicy}} Section 8, oldest first.
With `?handle=` it returns one agent's part of it: every promise that agent
made, every decision about it, and everything it touched, in order.

`GET /events` is a server-sent event stream {{SSE}} carrying a message for
each thing that happens that the owner may want to act on: a request arriving
to wait on her, a decision landing, a resource server introducing itself, an
organization or a co-holder changing something. The event name is the
message's `type`. On a replicated authorization server the subscription MUST
be a property of the shared state rather than of the process serving the
stream, since the decision the owner is waiting for may be produced by any
replica.

# Arrangements {#arrangements}

Where an authorization server implements {{U4AMultiParty}}, the owner's side
of it is served here.

`GET /organization` says whether she administers resources for anyone, and
under what charter version, with the ceiling as it currently binds each of
her units — and, where she is not a member, whether an invitation is waiting
on her. `POST /organization/preview` with `{"code": …}` returns what a code
would commit her to and what it would change about terms she has already
written, without doing it. `POST /organization` enrols her and MUST be refused
without `"agreed": true` in the body. `POST /organization/decline` records a
refused invitation. `DELETE /organization` leaves.

`POST /joint/preview` with `{"tally": …, "account": …}` returns a mandate and
what agreeing would mean for her terms; `POST /joint` agrees to it and MUST be
refused without `"agreed": true`; `GET /joint` lists the accounts she holds
jointly; `DELETE /joint/{account}` stops.

Both joins are refused without explicit agreement for the reason
{{U4AMultiParty}} gives: each hands another party standing authority over
her agents, and that is not something to acquire by forgetting to say no.

# Security Considerations

## The Credential Proves the Owner

Every operation acts on the owner the credential proved. An implementation
that lets a request name its owner, and checks the credential only for
validity, has built a surface where one owner's valid key answers another
owner's questions.

## Bodies Are Covered

See {{discovery}}. The four base components of {{U4ACore}} Section 6.1 say
who is asking and what they are asking of; the word in the body of
{{decision}} is the entire meaning of the request.

## The Queue Is Read by Whoever Is Entitled to Decide

{{pending}} is the same list whether the owner or an administrator acting for
her reads it, filtered for the administrator to what their charter claims. An
administrator who saw a different set of pending requests from the person
they co-administer with would be looking at a different system.

## Revocation Reports Its Reach

{{connections}} returns counts rather than success. A revocation that reports
`rpts_deactivated: 0` against an agent the owner believes is active is
information she needs, and a bare 200 would have hidden it.

# Privacy Considerations

This surface exposes, to the owner and to nobody else, everything her
authorization server knows about the agents that have approached her. The
`reason` an agent stated is shown to her verbatim, which is why {{pending}}
requires it be rendered as text: it is the one field on this surface that the
counterparty authored.

An organization's view of the same data is not this surface; it is the scoped
view of {{U4AMultiParty}} Section 2.6, and the scoping is applied by the
owner's server before it answers.

# IANA Considerations

This document has no IANA actions. The identifiers it uses are listed in
{{used-identifiers}}.

--- back

# Identifiers Used by This Document {#used-identifiers}

This appendix lists the identifiers this document defines. It is informative and
requests no registration.

| Name | Kind | Meaning | Defined in |
|---|---|---|---|
| `owner_endpoint` | Authorization server metadata {{RFC8414}} | URL of the resource owner's API | {{discovery}} |
{: title="Identifiers used by this document."}

# Implementation Status {#implementation-status}

This section records the status of known implementations in the sense of
{{?RFC7942}}, and is to be removed before publication as an RFC.

The reference implementation {{U4ALAB}} serves this surface from its
authorization server and has three clients of it: a browser portal
authenticating with an OpenID Connect session, a command-line tool and a
personal AI each authenticating with the owner's enrolled key. Every
operation is exercised by the checks that drive those clients; the two-caller
property of {{decision}} is tested with thirty-two concurrent callers against
both store backends.

# Acknowledgments
{:numbered="false"}

The 2010 UMA wireframes for out-of-band consent described this surface before
there was an interlocutor to put on the other end of it.
