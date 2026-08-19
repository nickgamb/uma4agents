---
templateKey: doc
title: MCP binding
seoTitle: "MCP authorization: carrying an owner's grant over Model Context Protocol"
description: How the grant travels over Model Context Protocol — discovery channels, both challenge encodings, the pend, and what MCP's types cannot yet express.
next:
  - title: Deviations from UMA 2.0
    to: /docs/reference/deviations/
    blurb: The extension register, each entry a finding.
  - title: Findings
    to: /docs/reference/findings/
    blurb: What this produced for the people writing the specs.
---

MCP carries the challenge and the eventual call. It does not carry the grant —
beats two through four happen at the owner's authorization server over HTTP,
unchanged. That separation is what lets one grant serve multiple bindings.

The repository's draft is
[`docs/MCP-BINDING.md`](https://github.com/nickgamb/uma4agents/blob/main/docs/MCP-BINDING.md).

## Discovery: three channels, one registry

A client can learn that it must negotiate, and where, before its first call. All
three channels are generated from the same tool registry.

| Channel | Nature | Notes |
|---|---|---|
| RFC 9728 Protected Resource Metadata | fetched | Mandatory for MCP servers since 2026-07-28 |
| AAuth resource metadata | fetched | The same structural facts under a content-addressed R3 vocabulary |
| `capabilities.extensions` | negotiated | Arrives in the handshake the client was already doing |

The third is new here. A resource enforcing in-process advertises the extension
in its `server/discover` response:

```jsonc
"extensions": {
  "dev.uma4agents/uma-enforcement": {
    "grant_type": "urn:ietf:params:oauth:grant-type:uma-ticket",
    "authorization_servers": ["https://alice-as.uma.lab"],
    "challenge": {"jsonrpc_error_code": -32001}
  }
}
```

No extra round trip and no well-known URI.

**Use `server/discover`, not `initialize`.** The 2026-07-28 revision is
unreachable through the legacy handshake by construction — the reference SDK
separates handshake protocol versions (topping out at 2025-11-25) from modern
ones. A client that asks `initialize` for 2026-07-28 is answered 2025-11-25 and
nothing appears wrong. Assert the negotiated version rather than assuming it.

## The challenge, in two encodings

The parameters are fixed: `realm`, `error`, `as_uri`, `ticket`,
`resource_metadata`, `scope`, `authorization_remediation`. How they travel
depends on whether the enforcement point has a status line.

**Gateway host** — an external authorization service ahead of the resource:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: UMA realm="alice-vault", error="insufficient_authorization",
  as_uri="https://alice-as.uma.lab", ticket="tkt_…",
  resource_metadata="https://gateway.uma.lab/.well-known/oauth-protected-resource/mcp",
  scope="trades:execute", authorization_remediation="<base64url JSON>"
```

**In-process host** — an MCP extension, no gateway in the path, no status line
to decorate:

```jsonc
{"jsonrpc": "2.0", "id": 4, "error": {
  "code": -32001,
  "message": "authorization required: present this ticket to the resource owner's AS",
  "data": {"error": "uma_challenge", "as_uri": "https://alice-as.uma.lab",
           "ticket": "tkt_…", "resource_metadata": "…", "realm": "alice-vault"}}}
```

A client should accept both. The `authorization_remediation` object is
byte-for-byte identical in each, which is the point of carrying it: the
RAR-metadata draft defines that payload against `WWW-Authenticate`, and this
shows the payload survives a transport with no status line.

> **A gateway-hosted enforcement point can never answer beat one with a
> JSON-RPC result.** In an external-authorization callout a 2xx means allow and
> the body is discarded; only non-2xx bodies reach the client. Any design where
> a gateway-hosted enforcement point returns a typed result rather than an error
> is impossible, which is why the challenge is an error in both encodings.

## The pend

When the owner's decision is outstanding, a requesting side that can render a
wait should hand it up rather than hold the call open. On 2026-07-28 the SDK
turns a server-side elicitation into a result carrying a `request_state` handle,
so the call suspends and resumes instead of hanging.

That machinery is right. The type is not:

```
input_requests: dict[str, CreateMessageRequest | ListRootsRequest | ElicitRequest]
```

All three address the client's own user — its model, its filesystem, its human.
There is no member for *blocked on a different principal, who is not on this
connection and cannot be reached through it*.

**This implementation does not emit a `subject` block.** The shim asks the
agent's human the only question that is genuinely theirs — keep waiting, or stop
— and describes the owner's role in prose. That is the honest ceiling of what
the current type allows.

The proposal adds a `subject` whose one required field is
`reachable_by_client`:

```jsonc
"subject": {
  "party": "resource_owner",
  "is_requesting_party": false,
  "reachable_by_client": false,
  "notified": true
}
```

Without it, a conforming client reading only the typed structure sees an
elicitation and tries to satisfy the wait from its own user, who has no part in
the decision.

## Routing headers, and a new confusion class

`Mcp-Method` and `Mcp-Name` are required on 2026-07-28 and let an enforcement
point route and decide without parsing a body. They also let it be **steered**:
send `Mcp-Method: tools/list` — open — with a `tools/call` body — protected — and
a header-trusting enforcement point waves it through to a resource that
dispatches on the body.

Two parsers over one message is the request-smuggling shape, arriving in a new
protocol.

Any enforcement point reading these headers **must** reconcile them against the
body, and **should** require them on protected methods rather than merely
checking them when present. An absent header is as steerable as a lying one. The
reference SDK rejects both cases for `mcp-name`, which is corroboration that the
concern is real; the specification does not currently say so.

## Step-up remediation

SEP-2643 applies the RAR-metadata pattern to MCP: when a call fails for want of
authority, the server returns machine-readable guidance instead of leaving the
client to construct a step-up request from documentation. The challenge above
**is** that guidance, plus two parameters.

| | RAR-metadata / SEP-2643 | U4A |
|---|---|---|
| Payload | `authorization_details` array | the same array, plus `authorization_server` and `ticket` |
| Nature | a template the client fills in and submits | a handle to a negotiation already open |
| Who authors the request | the client | nobody — the resource registered it, the owner's authority decides |
| Whose authorization server | the client's own | the resource owner's |
| Server-side state | none by design | a negotiation, which is what makes a pend possible |

The step that does not survive the move to a third-party owner is *the client
takes the template to its authorization server*. The agent's authorization
server cannot grant access to somebody else's vault. Naming
`authorization_server` in the remediation object, and returning a ticket rather
than a template, is what makes the same failure decidable by a party who is not
the caller — a small enough addition that it belongs in that draft rather than
in a rival one.

Statelessness costs the pend too. A template has nowhere to hold "the owner has
been asked and has not answered yet."

## Tasks: not implemented, and why

The resumable-request machinery already carries the pend, so Tasks would add
durable server-side handles for the case where the owner is asleep for hours
rather than seconds. It is explicitly future here rather than stubbed —
`tasks/*` is refused with `unknown_method` rather than half-answered.

Two things should be settled first.

**`taskId` should not be a bearer token.** SEP-2663 says it cannot scope
`tasks/list` because servers cannot reliably correlate two unrelated handles to
the same caller, and settles for unguessable ids. This profile does not need to
correlate handles: authority to observe or act on a negotiation is a signature
verifying against the key that signed the agreement, over a single-use rotating
ticket. With that, `taskId` can be a stable public identifier and `tasks/list`
becomes scopeable — negotiations bound to the key that signed this request.

**A task here augments the authorization decision, not the work.** SEP-2663
assumes a task wraps the tool call, so `completed` means the tool finished. A
gateway-hosted enforcement point structurally cannot observe the tool result. A
`taskKind: "authorization"` would let `completed` honestly mean the decision
resolved — retry your original request.

One refinement for any implementation: `tasks/get` should verify the ticket
**without consuming it**. Single-use exists to stop a replayed ticket escalating
into a grant; a read-only observation advances no state, and a consuming poll
makes a lost response brick the negotiation.

## Conformance summary

| Mechanism | Status |
|---|---|
| `server/discover`, stateless transport, `_meta` client identity | implemented |
| RFC 9728 PRM, AAuth R3 metadata, `capabilities.extensions` | implemented |
| Challenge in both encodings; one client understands both | implemented |
| Pend hand-back with `request_state` | implemented |
| `Mcp-Method` / `Mcp-Name` reconciliation, required on protected methods | implemented |
| Origin validation | implemented |
| RAR-metadata remediation in the challenge, both encodings | implemented |
| `authorization_server` + `ticket` inside the remediation object | proposed |
| `subject` on an input request | proposed |
| Tasks, `taskKind`, proof-of-possession on tasks | future |
