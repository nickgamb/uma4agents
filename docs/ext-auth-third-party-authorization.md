# Third-Party Authorization for MCP

**Status: proposal.** A draft for the `modelcontextprotocol/ext-auth`
extension track, written from a working implementation rather than from
first principles. Not adopted, not submitted; published here so the shape can
be argued over against running code.

Each addition below exists because the build hit the gap, and each cites the
part of MCP 2026-07-28 that makes it necessary.

## Problem

MCP's authorization model assumes the party operating the client and the party
who can authorize are the same person, reachable through the same connection.
`Authorization` carries a token the client obtained on its user's behalf;
`input_required` asks that user for more.

An agent acting for one person against another person's resources breaks that
assumption. The requesting party is Bob; the resource owner is Alice; Alice is
not on the connection and may be asleep. Her policy still has to be satisfied,
and she may want to be asked. Today MCP can express the *wait* but not *who is
being waited on*, and its Tasks extension concedes it cannot scope task access
because it has no way to bind a handle to a caller.

Everything below is additive, optional, and composable in the sense the
extensions track requires. Nothing changes core behaviour for a client that
does not implement it.

## 1. `subject` on an input request

**Why.** `InputRequiredResult.input_requests` is a closed union:

```
dict[str, CreateMessageRequest | ListRootsRequest | ElicitRequest]
```

Sampling asks the client's model. Roots asks the client's filesystem.
Elicitation asks the client's human. There is no member — and no extension
point on the members — for input that must come from someone else. A server
that is blocked on a third party can only misuse elicitation, and a conforming
client will then try to satisfy the wait from its own user.

**Proposal.** An optional `subject` on an input request:

```jsonc
"subject": {
  "party": "end_user" | "resource_owner" | "operator" | "third_party",
  "is_requesting_party": false,
  "reachable_by_client": false,
  "display_name": "the owner of this account",
  "notified": true,
  "notified_at": "2026-07-29T18:21:27Z"
}
```

`reachable_by_client` is the field that does the work. When it is `false` the client
**MUST NOT** attempt to satisfy the request from its own user; it may surface
the wait, and it may ask its user whether to keep waiting or abandon — a
distinct question the client owns.

`display_name` is deliberately vague-able. Telling Bob *which* customer is
being asked can itself be a disclosure, so a server may name a role rather
than a person.

**Compatibility.** A client that ignores `subject` behaves as it does today.
The failure mode it prevents — prompting the wrong human — is silent, which is
why the field is worth having even though ignoring it is legal.

## 2. `taskKind: "authorization"`

**Why.** SEP-2663 assumes a task augments the *work*: `completed` means the
tool call finished and `result` is a `CallToolResult`. An enforcement point
that sits beside or ahead of the resource never observes the tool result — it
decides whether the call may proceed. Reporting `completed` with a tool result
it does not have is not something it can honestly do.

**Proposal.** An optional discriminator on the task:

```jsonc
{"taskId": "u4a:fam_8f3a2b", "taskKind": "authorization", "status": "input_required"}
```

When `taskKind` is `"authorization"`, `completed` means *the authorization
decision resolved* and the client should retry its original request; the task
carries the decision, not a tool result. Absent the field, tasks mean what
they mean today.

## 3. `proofOfPossession`, and task ids that are not credentials

**Why.** SEP-2663 is explicit that it cannot define scoping for `tasks/list`:
"servers cannot reliably correlate two unrelated handles to the same caller
without additional state," so task ids end up functioning as bearer tokens and
`tasks/list` becomes unsafe to offer at all.

There is a way out that does not require correlating handles: **verify proof
instead.** If acting on a task requires a signature from a key the server
already associated with the negotiation, the task id stops being a credential
and can be public and stable.

**Proposal.** An optional descriptor on an input request or task:

```jsonc
"proofOfPossession": {
  "method": "http-message-signatures",
  "alg": "ed25519",
  "covered_components": ["@method", "@authority", "@path", "authorization"],
  "state_header": "Authorization",
  "state_scheme": "UMA-Ticket"
}
```

A client that sees this signs its `tasks/*` requests accordingly. Consequences
worth stating: task ids need no entropy budget, `tasks/list` becomes
definable — "tasks bound to the key that signed this request" — and a leaked
id grants nothing.

**A refinement for whoever implements this.** A read-only `tasks/get` should
verify the state handle **without consuming it**, even where the underlying
protocol treats handles as single-use. Single-use exists to stop a replayed
handle escalating into a grant; observing state advances nothing, and a
consuming poll means one lost response bricks the negotiation.

## Relationship to RAR metadata / SEP-2643

`draft-zehavi-oauth-rar-metadata` and SEP-2643 solve the neighbouring problem:
when a call fails for want of authority, the resource returns machine-readable
guidance rather than leaving the client to build a step-up request from
documentation. The two efforts compose, and the addition needed is small.

![RAR metadata alone, and U4A](rar-at-a-glance.svg)

That draft's `authorization_remediation` object carries `authorization_details`
(RFC 9396) and an optional `authorization_reference`. Its flow assumes the
client then submits those details to **its own** authorization server. That
assumption holds whenever the person who can authorize is the client's user.
It fails whenever the resource belongs to someone else: the requesting party's
authorization server has no standing to grant, and a template has nowhere to
hold "the owner has been asked and has not answered."

Two optional members close it:

```jsonc
{
  "authorization_details": [ /* unchanged */ ],
  "authorization_reference": "…",
  "authorization_server": "https://alice-as.example",   // whose policy decides
  "ticket": "…"                                          // handle to the negotiation
}
```

A client that does not understand them behaves exactly as it does today. A
client that does knows not to take the details to its own AS, and knows where
to take the ticket instead.

The reference implementation emits this object over both a
`WWW-Authenticate` header and a JSON-RPC error, unchanged, which also
demonstrates that the payload is transport-portable.

## Prior art

This is not a new idea, only a new home for it. User-Managed Access 2.0
(Kantara, 2018) specifies exactly this topology — a resource owner whose
policy governs a requesting party they may never meet, a permission ticket
that carries a negotiation across time, and a `request_submitted` state for a
decision that has not been made yet. What UMA lacked was a transport where
agents actually live. What MCP lacks is the second principal. The two compose
better than either does alone.

Reference implementation and measurements:
[github.com/nickgamb/uma4agents](https://github.com/nickgamb/uma4agents) —
`docs/MCP-BINDING.md` for the binding, `FINDINGS.md` for what the build
learned.
