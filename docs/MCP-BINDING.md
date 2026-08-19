# The MCP binding

How the UMA-for-agents grant rides Model Context Protocol 2026-07-28. A
companion to [PROTOCOL.md](PROTOCOL.md), which is the binding-independent wire
contract; everything here is about encoding, not semantics.

Written against a running implementation. Each mechanism below is marked
implemented, proposed, or future in the summary at the end — the proposals are
things MCP does not yet have, not things this repo is missing.

## Why MCP is the urgent binding

MCP's 2026-07-28 revision independently arrived at most of the machinery this
grant needs, from a completely different direction:

| UMA 2.0 (2018) | MCP 2026-07-28 |
|---|---|
| Permission ticket: opaque, server-minted, single-use, rotated per step | MRTR `request_state`: opaque, server-minted, echoed back unmodified (SEP-2322) |
| `request_submitted` — a negotiation that is waiting, not failed | `input_required` — a call that is waiting, not failed |
| `interval` for re-presenting a held ticket | `pollIntervalMs` on a task (SEP-2663) |
| Ticket state survives the connection | Sessions removed; state rides the message (SEP-2567/2575) |

The convergence is the argument. Two designs reaching the same shapes eight
years apart suggests the shapes are forced. What MCP does *not* have is the
thing UMA exists for — a second principal — and that gap is now expressible in
MCP's own terms rather than as an abstract complaint.

## Discovery: three channels, one registry

A client can learn it must negotiate a grant, and where, before its first
call. Which channel it uses depends on the deployment, and all three are
generated from the same tool registry.

1. **RFC 9728 Protected Resource Metadata** — `authorization_servers`,
   `tool_surfaces`, `jwks_uri`, `signed_metadata`. Mandatory for MCP servers
   since 2026-07-28; fetched, not negotiated.
2. **AAuth resource metadata** — the same structural facts under an R3
   content-addressed vocabulary, for the AAuth binding.
3. **`capabilities.extensions`** — new here. A resource enforcing in-process
   advertises `dev.uma4agents/uma-enforcement` in its `server/discover`
   response:

   ```jsonc
   "extensions": {
     "dev.uma4agents/uma-enforcement": {
       "grant_type": "urn:ietf:params:oauth:grant-type:uma-ticket",
       "authorization_servers": ["https://alice-as.uma.lab"],
       "challenge": {"jsonrpc_error_code": -32001}
     }
   }
   ```

   This is the only one that is *negotiated* rather than fetched — it arrives
   in the handshake the client was already doing, with no extra round trip and
   no well-known URI.

**`server/discover`, not `initialize`.** 2026-07-28 is unreachable through the
legacy handshake by construction: the reference SDK splits
`HANDSHAKE_PROTOCOL_VERSIONS` (topping out at 2025-11-25) from
`MODERN_PROTOCOL_VERSIONS`. A client that asks `initialize` for 2026-07-28 is
answered 2025-11-25 and nothing appears wrong. Clients should assert the
negotiated version rather than assume it.

## Beat 1: the challenge has two encodings

The parameters are fixed — `realm`, `error`, `as_uri`, `ticket`,
`resource_metadata`, `scope`, `authorization_remediation`. How they travel
depends on whether the enforcement point has a status line.

**Gateway host** (an ext_authz service ahead of the resource):

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: UMA realm="alice-vault", error="insufficient_authorization",
  as_uri="https://alice-as.uma.lab", ticket="tkt_…",
  resource_metadata="https://gateway.uma.lab/.well-known/oauth-protected-resource/mcp",
  scope="trades:execute", authorization_remediation="<base64url JSON>"
```

**In-process host** — an MCP `Extension`, i.e. the shape with no gateway in
the path, where the MCP server handles the grant itself. It has no status line
to put a header on:

```jsonc
{"jsonrpc": "2.0", "id": 4, "error": {
  "code": -32001,
  "message": "authorization required: present this ticket to the resource owner's AS",
  "data": {"error": "uma_challenge", "as_uri": "https://alice-as.uma.lab",
           "ticket": "tkt_…", "resource_metadata": "…", "realm": "alice-vault"}}}
```

A client should accept both; the shim in this repo does, and negotiates
identically after either.

**The `authorization_remediation` object is byte-for-byte the same in both.**
That is the point of carrying it: `draft-zehavi-oauth-rar-metadata` defines
the payload against `WWW-Authenticate`, and this shows the payload survives a
transport that has no status line. The envelope is binding-specific; the
remediation is not.

> **An ext_authz service can never answer beat 1 with a JSON-RPC *result*.**
> In agentgateway a 2xx from the auth service means *allow* and the body is
> discarded — only non-2xx bodies reach the client. Any design that has a
> gateway-hosted PEP return `InputRequiredResult` or `CreateTaskResult` is
> impossible, which is why the challenge is an error in both encodings and why
> an authorization plane hosted at a gateway needs its own route rather than a
> body trick.

## Beats 2–4 are not MCP

The negotiation happens at the owner's authorization server over HTTP, exactly
as in [PROTOCOL.md](PROTOCOL.md). MCP carries the challenge and the eventual
call; it does not carry the grant. This is deliberate — it is what lets the
same grant serve the AAuth and OAuth+DPoP bindings unchanged.

## The pend: `input_required`, and what it cannot say

When the owner's decision is outstanding, a requesting side that can render a
wait should hand it up rather than hold the call open. On 2026-07-28 the SDK
turns a server-side elicitation into an `InputRequiredResult` carrying a
`request_state` handle, so the call suspends and resumes instead of hanging.

That machinery is right. The type is not:

```
input_requests: dict[str, CreateMessageRequest | ListRootsRequest | ElicitRequest]
```

All three address the client's own user — its model, its filesystem, its
human. **There is no member for "blocked on a different principal, who is not
on this connection and cannot be reached through it."** So today the shim asks
Bob the only question that is genuinely his — keep waiting, or stop — and
describes the owner's role in prose. A conforming client reading only the
typed structure sees an elicitation and will try to satisfy the wait from its
own user, which is precisely wrong.

To be unambiguous about what is built: **this implementation does not emit a
`subject` block.** The elicitation message describes the owner's role in
prose, and that is the honest ceiling of what the current type allows. The
proposal in
[ext-auth-third-party-authorization.md](ext-auth-third-party-authorization.md)
adds a `subject` whose one required field is `reachable_by_client`.

## SEP-2243 routing headers: a new confusion class

`Mcp-Method` and `Mcp-Name` are required on 2026-07-28 and let an enforcement
point route and decide without parsing a body. They also let it be *steered*:
send `Mcp-Method: tools/list` (open) with a `tools/call` body (protected) and a
header-trusting PEP waves it through to a resource that dispatches on the
body. Two parsers over one message is the request-smuggling shape, arriving in
a new protocol.

Any enforcement point that reads these headers **MUST** reconcile them against
the body, and **SHOULD** require them on protected methods rather than merely
checking them when present — an absent header is as steerable as a lying one.
The reference SDK rejects both cases for `mcp-name`, which is corroboration
that this is real. The spec does not currently say so.

## Step-up remediation (SEP-2643 / draft-zehavi-oauth-rar-metadata)

![RAR metadata alone, and U4A](rar-at-a-glance.svg)

SEP-2643 applies the RAR-metadata pattern to MCP: when a call fails for want
of authority, the server returns machine-readable guidance instead of leaving
the client to construct a step-up request from out-of-band documentation. U4A
does not compete with it. The challenge above **is** that guidance, plus two
parameters.

| | RAR-metadata / SEP-2643 | U4A |
|---|---|---|
| payload | `authorization_details` array | the same array, plus `authorization_server` and `ticket` |
| nature | a template the client fills in and submits | a handle to a negotiation already open |
| who authors the request | the client | nobody — the resource registered it, the owner's AS decides |
| whose authorization server | the client's own | the resource owner's |
| server-side state | none by design | a negotiation, which is what makes a pend possible |

The step that does not survive the move to RqP ≠ RO is *"client takes the
template to its authorization server."* Bob's AS cannot grant access to
Alice's vault. Naming `authorization_server` in the remediation object, and
returning a ticket rather than a template, is what makes the same failure
decidable by a party who is not the caller — and it is a small enough
addition that it belongs in that draft rather than in a rival one. See
[ext-auth-third-party-authorization.md](ext-auth-third-party-authorization.md).

The other thing statelessness costs is the pend. A template has nowhere to
hold "the owner has been asked and has not answered yet."

## Tasks (SEP-2663): not implemented, and why

MRTR already carries the pend, so Tasks would add durable server-side handles
for the case where the owner is asleep for hours rather than seconds. It is
**explicitly future here**, not stubbed — `tasks/*` is refused with
`unknown_method` rather than half-answered.

Two things should be settled before implementing it, and both are findings
rather than blockers:

- **`taskId` should not be a bearer token.** SEP-2663 says it cannot scope
  `tasks/list` because "servers cannot reliably correlate two unrelated
  handles to the same caller," and settles for unguessable ids. U4A does not
  need to correlate handles: authority to observe or act on a negotiation is a
  signature verifying against the key that signed the intent contract, over a
  single-use rotating ticket. With that, `taskId` can be a stable, public
  `u4a:<family>` and `tasks/list` becomes scopeable — "negotiations bound to
  the key that signed this request."
- **A U4A task augments the *authorization decision*, not the work.** SEP-2663
  assumes a task wraps the tool call, so `completed` means the tool finished.
  An ext_authz PEP structurally cannot observe the tool result. A
  `taskKind: "authorization"` would let `completed` honestly mean "the decision
  resolved — retry your original request."

One refinement worth carrying into any implementation: **`tasks/get` should
verify the ticket without consuming it.** UMA's single-use rule exists to stop
a replayed ticket escalating into a grant; a read-only observation advances no
state, and a consuming poll makes a lost response brick the negotiation.

## Conformance summary

| Mechanism | Status |
|---|---|
| `server/discover`, stateless transport, `_meta` client identity | implemented |
| RFC 9728 PRM, AAuth R3 metadata, `capabilities.extensions` | implemented |
| Challenge in both encodings; one client understands both | implemented |
| MRTR pend hand-back with `request_state` | implemented |
| `Mcp-Method`/`Mcp-Name` reconciliation, required on protected methods | implemented |
| Origin validation | implemented |
| RAR-metadata remediation in the challenge (both encodings) | implemented |
| `authorization_server` + `ticket` inside the remediation object | **proposed** for the RAR-metadata draft |
| `subject` on an input request | **proposed** |
| Tasks (`tasks/get|update|cancel`), `taskKind`, `proofOfPossession` | **future** |
