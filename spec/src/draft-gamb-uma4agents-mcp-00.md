---
title: "Model Context Protocol Binding for User-Managed Access (UMA) 2.0"
abbrev: "MCP Binding for UMA"
docname: draft-gamb-uma4agents-mcp-00
date: 2026-09-15
category: info
submissiontype: IETF
ipr: trust200902
area: Security
keyword: [UMA, authorization, MCP, Model Context Protocol, agents, binding]
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
  I-D.ietf-oauth-rar-metadata-remediation:
  RFC6454:
  RFC9728:
  MCP:
    title: "Model Context Protocol Specification, revision 2026-07-28"
    author:
      - org: Model Context Protocol project
    date: 2026-07-28
    target: https://modelcontextprotocol.io/specification/2026-07-28
  JSONRPC:
    title: "JSON-RPC 2.0 Specification"
    author:
      - org: JSON-RPC Working Group
    date: 2013-01-04
    target: https://www.jsonrpc.org/specification
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
  I-D.hardt-aauth-protocol:
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

This document binds the UMA 2.0 profile for autonomous agents to the Model
Context Protocol. It specifies how a resource offering MCP tools emits the
authorization challenge, in the two shapes an enforcement point may take; how a
client discovers before its first call that it must negotiate a grant and where;
and what an enforcement point that routes on MCP's request headers must do to
avoid being steered by them.

The negotiation itself is not MCP. The challenge and the eventual call ride
MCP; the grant is obtained over HTTP from the owner's authorization server
exactly as in the core profile, which is what lets the same grant serve other
bindings unchanged.

--- middle

# Introduction

{{MCP}} is the protocol autonomous agents call tools over, and its 2026-07-28
revision requires a protected MCP server to publish protected resource metadata
{{RFC9728}} and to challenge with it. That is most of what {{U4ACore}} needs
from a transport. What MCP does not have is a second principal: a party who is
not the client's own user, is not present, and whose policy decides.

This binding adds nothing to MCP. It says how the parameters of {{U4ACore}}
Section 3.1 travel over it, in each of the two places an enforcement point may
sit, and it names one hazard in MCP's routing headers that any enforcement point
reading them must handle.

## Relationship to the Set

This document is one binding of {{U4ACore}}. Others are possible; a binding to
the challenge header of {{I-D.hardt-aauth-protocol}} is the obvious second, and
{{U4ACore}} Section 1.2 names a third. Its identifying URI is
`https://u4a.ai/spec/mcp/1.0`.

## Notational Conventions

{::boilerplate bcp14-tagged}

# Discovery {#discovery}

A client MAY learn that a resource requires a grant under this profile, and from
which authorization server, through any of three channels. A resource MUST offer
the first and MAY offer the others, and all MUST be generated from one registry
of the resource's tools.

Protected resource metadata:
: As {{RFC9728}} and {{U4AFedAuthz}} Section 2.1, which {{MCP}} already
  requires. Fetched, not negotiated.

Alternative metadata encodings:
: The same structural facts under another convention, such as the resource
  metadata of {{I-D.hardt-aauth-protocol}}.

Capability advertisement:
: A resource enforcing in-process MAY advertise this profile in the
  `capabilities.extensions` member of its handshake response under the
  identifier `dev.uma4agents/uma-enforcement`, carrying the grant type, the
  authorization servers, and the JSON-RPC error code of {{challenge-jsonrpc}}.

~~~ json
{
  "extensions": {
    "dev.uma4agents/uma-enforcement": {
      "grant_type": "urn:ietf:params:oauth:grant-type:uma-ticket",
      "authorization_servers": ["https://alice-as.example"],
      "challenge": {"jsonrpc_error_code": -32001}
    }
  }
}
~~~
{: title="The capability advertisement."}

The third channel is the only one that is negotiated rather than fetched: it
arrives in the handshake the client was already doing, with no extra round
trip and no well-known URI. A client that receives it knows, before its first
tool call, that it must negotiate a grant and where.

Whichever channel a client learns from, it MUST corroborate the authorization
server named in any later challenge against the metadata document as
{{U4ACore}} Section 3.4.

# The Challenge {#challenge}

Only tool invocation is protected. An enforcement point MUST allow session
bootstrap and discovery methods without authorization, and MUST refuse, by
default, any method it does not recognise as either open or protected.
Deny-by-default matters here more than usual: one revision of {{MCP}} added
several method families at once, and an allow-list written against the previous
revision would have let each of them through.

The parameters of the challenge are those of {{U4ACore}} Section 3.1. How they
travel depends on whether the enforcement point has an HTTP status line to
decorate.

## At a Gateway {#challenge-http}

An enforcement point in front of the resource, answering at the HTTP layer,
MUST use the HTTP binding of {{U4ACore}} Section 3.2: `401 Unauthorized` with
`WWW-Authenticate: UMA`. The JSON-RPC body of the refused request is not
answered; the client never reached the resource.

An enforcement point hosted as an external authorization service of a gateway
can answer a refusal with a body and a status, and can answer an allow with
nothing the client will see. It therefore MUST NOT attempt to answer a
challenge as a JSON-RPC *result*; a pending grant cannot be expressed from that
position, and the challenge is an error in both encodings for this reason.

## In Process {#challenge-jsonrpc}

An enforcement point inside the resource — an MCP server that applies this
profile to itself — has no status line. It MUST answer a `tools/call` it refuses
for want of authorization with a JSON-RPC error {{JSONRPC}} whose `code` is
`-32001`, and whose `data` member is an object carrying every parameter of
{{U4ACore}} Section 3.1 under its own name:

~~~ json
{
  "jsonrpc": "2.0",
  "id": 4,
  "error": {
    "code": -32001,
    "message": "authorization required",
    "data": {
      "error": "insufficient_authorization",
      "realm": "alice-vault",
      "as_uri": "https://alice-as.example",
      "ticket": "MWRlNzE4ZjgtMGY0OS00NDg2",
      "resource_metadata":
      "https://rs.example/.well-known/oauth-protected-resource/mcp",
      "scope": "trades:execute",
      "authorization_remediation": {
        "authorization_details": [{
          "type": "urn:uma4agents:authorization-details:tool-call",
          "locations": ["https://rs.example"],
          "identifier": "alice-vault/execute_trade",
          "actions": ["execute_trade"],
          "datatypes": ["trades:execute"]
        }],
        "authorization_reference":
          "s256:ij_r5Jn2rOT7fL8gSvNaOY1XBnRZnWOwasceTRKB42E",
        "authorization_server": "https://alice-as.example",
        "ticket": "MWRlNzE4ZjgtMGY0OS00NDg2"
      }
    }
  }
}
~~~
{: title="The challenge as a JSON-RPC error."}

`authorization_remediation` is carried as the object itself rather than
base64url-encoded, since JSON-RPC carries JSON. Its content MUST be identical to
what the HTTP binding would have encoded. That the same object rides both
envelopes byte for byte is what shows the remediation payload of
{{I-D.ietf-oauth-rar-metadata-remediation}} is portable, and only the envelope
is binding-specific.

A refusal for any other reason MUST use code `-32002`, with `data` carrying
`error` and `status` as the HTTP binding would have.

## A Client Reads Both {#client}

A client implementing this binding MUST recognise both encodings and MUST
negotiate identically after either. The reference implementation's client does, and the two hosting shapes run against one authorization server.

# The Negotiation and the Call {#negotiation}

The negotiation of {{U4ACore}} Section 4 is carried over HTTP with the owner's
authorization server and is not MCP. This is deliberate: MCP carries the
challenge and the eventual call, and nothing about the grant depends on it.

The eventual call is the original `tools/call`, re-sent with the requesting
party token in an `Authorization` header with the `PoP` scheme and signed as
{{U4ACore}} Section 6. Where the enforcement point is in process, the signature
components are the HTTP request that carried the JSON-RPC message.

For a single-use grant ({{U4ACore}} Section 7.2), the operation is the call's
`params.name` and its parameters are `params.arguments`.

# Waiting {#waiting}

When the owner has been asked and has not answered, a requesting side that can
render a wait SHOULD hand it up as an input-required result carrying a
resumable request state, as {{MCP}} defines, rather than hold the call open.

The requesting side MUST NOT attempt to satisfy that wait from its own user.
{{MCP}}'s input-required result addresses the client's own model, filesystem or
human, and has no member for a principal who is not on this connection. Until
it does, an implementation MUST convey in the human-readable content of the
request that the party being waited on is the resource owner and is not
reachable by the client, and MUST limit what it asks its own user to the one
question that is genuinely theirs: keep waiting, or stop.

# Routing Headers {#routing-headers}

{{MCP}} 2026-07-28 requires `Mcp-Method` and `Mcp-Name` request headers so that
an intermediary can route and decide without parsing the body. They also let
an intermediary be steered. A header naming an open method over a body naming a
protected one is two parsers disagreeing about one message, which is the
request-smuggling shape arriving in a new protocol.

An enforcement point that reads these headers MUST reconcile each against the
body and MUST refuse a request on which they disagree. On protocol version
2026-07-28 and later it MUST require both headers on protected methods rather
than checking them only when present; an absent header is as steerable as a
lying one.

# Origin {#origin}

An enforcement point MUST validate the `Origin` header {{RFC6454}} of a request
against the origins it is configured to serve, where one is present, and MUST
refuse a request from an origin it does not serve.

# Truncated Bodies {#truncation}

Where an enforcement point is hosted behind a gateway that forwards a bounded
prefix of the request body, it MUST detect that the body it received was
truncated and MUST refuse with a reason naming the truncation, as {{U4ACore}}
Section 13.7. A truncated JSON-RPC body does not parse, the method disappears,
and deny-by-default catches it under the wrong name.

# Security Considerations

The considerations of {{U4ACore}} apply. The following are specific to this
binding.

## Two Parsers, One Message

See {{routing-headers}}. Every header that lets an intermediary skip parsing
the body is a header that lets an attacker tell the intermediary one thing and
the resource another.

## The Challenge Is an Error

See {{challenge-http}}. A gateway-hosted enforcement point cannot return a
result the client will see, so a design that expresses a pending grant as a
result from that position cannot be implemented. Both encodings use an error
so that a client need not care which host it reached.

## Deny by Default Is Not Optional

See {{challenge}}. The method surface of {{MCP}} grows between revisions, and
an enforcement point that enumerates what to refuse rather than what to allow
will be wrong after the next one.

# Privacy Considerations

The considerations of {{U4ACore}} apply. The capability advertisement of
{{discovery}} discloses the owner's authorization server to any client that
completes a handshake, which the protected resource metadata already discloses
to anyone who fetches it. No additional disclosure is made.

# IANA Considerations

This document makes no request of IANA. The JSON-RPC error codes `-32001` and
`-32002` are in the range {{JSONRPC}} reserves for implementation-defined
server errors, and the extension identifier `dev.uma4agents/uma-enforcement`
follows {{MCP}}'s convention for vendor-prefixed extension identifiers.

--- back

# Implementation Status {#implementation-status}

This section records the status of known implementations in the sense of
{{?RFC7942}}, and is to be removed before publication as an RFC.

The reference implementation {{U4ALAB}} runs both hosting shapes of
{{challenge}} against one authorization server — an external authorization
service ahead of an unmodified MCP server, and an MCP server extension
applying the profile in process — and one client negotiates through
either. The routing-header hazard of {{routing-headers}} was found by sending
the mismatched pair and watching a header-trusting enforcement point wave it
through; the reference MCP SDK independently rejects the same pair. The
truncation of {{truncation}} was found by sending a body one byte over a
gateway's limit and reading the refusal it produced.

# Acknowledgments
{:numbered="false"}

{{MCP}}'s 2026-07-28 revision arrived, from a different direction, at most of
the shapes this profile needs: an opaque server-minted state that the client
echoes back, a result that means waiting rather than failure, and a polling
interval. Two designs reaching the same shapes eight years apart suggests the
shapes are forced.
