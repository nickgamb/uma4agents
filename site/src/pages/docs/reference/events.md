---
templateKey: doc
title: Events
description: The structured event stream, every event name, and the ledger projected from it.
next:
  - title: MCP binding
    to: /docs/reference/mcp-binding/
    blurb: How the grant travels over JSON-RPC.
  - title: Revocation and the ledger
    to: /docs/overview/revocation/
    blurb: What the owner sees, and why it comes from here.
---

One JSON line per event to stdout. The dashboard, the audit command and the
owner's ledger are all views over this stream.

## Shape

```json
{ "ts": "2026-07-07T18:21:27Z", "event": "need_info.terms_dictated",
  "corr": "fam_8f3a…", "actor": "uma-as",
  "details": { "tier": "tier1", "template_id": "alice/advisor-tier1/v2",
               "resource_id": "alice-vault/get_positions" } }
```

| Field | Meaning |
|---|---|
| `ts` | UTC, RFC 3339 |
| `event` | Dotted name from the register below |
| `corr` | The negotiation family id, stable across every ticket rotation |
| `actor` | Which component emitted it |
| `details` | Event-specific, and deliberately free-form |

`corr` is the field that makes this usable. With a replicated authority, a single
negotiation's events are spread across every instance, so reading one pod's logs
shows a fragment. Correlate by family, not by process.

## Event register

### Registration and discovery

| Event | Emitted when |
|---|---|
| `resource.registered` | A resource lands in the authority's registry |
| `resources.registered_at_startup` | The startup pull completes |
| `terms.published` | A terms document version is published |
| `terms.declined` | The requesting side refuses the proffered terms |

### The negotiation

| Event | Emitted when |
|---|---|
| `permission.registered` | `POST /perm` issues a ticket |
| `challenge.issued` | The enforcement point refuses with a challenge |
| `ticket.presented` | The agent presents a ticket at the token endpoint |
| `need_info.terms_dictated` | The authority proffers terms |
| `contract.committed` | A signed agreement verifies |
| `contract.rejected` | An agreement fails verification |
| `assurance.assessed` | What her authority could verify about the agent asking |
| `operator_directory.checked` | An operator's key directory was fetched and searched for this agent's key |
| `operator_directory.rejected` | A directory was named that is not same-origin with the operator claimed |
| `operator_directory.unresolved` | A directory would not resolve; the claim stays where it was |
| `policy.evaluated` | A tier policy decision is made. `result` includes `attention-budget` when a lane is full and `operator-blocked` when she has shut that operator out |

### The owner

| Event | Emitted when |
|---|---|
| `ticket.awaiting_owner` | The negotiation is held pending her decision |
| `owner.notified` | The pending item reaches her surface |
| `owner.decision` | She approves or denies |
| `connection.approved` | A standing relationship is recorded |
| `connection.revoked` | She revokes one |
| `policy.updated` | She edits a tier |
| `policy.created` | She adds terms of her own |
| `policy.deleted` | She removes a tier; its resources become ungoverned |
| `operator.blocked` | She shuts out an operator, with the connections and grants it cost |
| `operator.unblocked` | She lets one ask again |

### The grant and its use

| Event | Emitted when |
|---|---|
| `rpt.issued` | A grant is minted |
| `receipt.issued` | The counter-signed receipt is returned |
| `rpt.introspected` | The enforcement point checks a grant |
| `rpt.consumed` | A single-use grant is spent |
| `access.allowed` | A call reaches the resource |
| `access.denied` | A call is refused |

## The ledger, as a projection

The owner's ledger is not a separate record. It is this stream, grouped by
family:

| Ledger column | Source event |
|---|---|
| **promised** | `contract.committed` |
| **personally approved / denied** | `owner.decision` |
| **touched** | `access.allowed` |
| **connected** | `connection.approved` |
| **revoked** | `connection.revoked`, and `operator.blocked` for every connection it ended |
| **relaxed** | a rule she wrote lowered an ask-me tier to automatic, naming the rule that fired |

Those first three columns answer the question she will actually ask: did what
happened match what I agreed to. Reading them side by side is the point —
`promised` without a matching `touched` is a grant that went unused, and
`touched` without a matching `owner.decision` is either a tier she opened
deliberately or something to investigate.

![The ledger in the lab's portal, newest first: a touched entry naming the
executed trade, the approval above it, and the promise below carrying the terms
that were signed and the agreement hash — all three sharing one negotiation
id.](/img/docs/owner-ledger.png)

The rightmost column is the negotiation family. Three rows of a single story sit
apart in time and are joined by that id, which is what makes the ledger
answerable rather than merely chronological.

## Reading it in the lab

```bash
make k8s-audit
```

Prints the three columns correlated by family. The compose equivalent is
`make audit`.

Reading pod logs directly will mislead you when the authority is replicated. Ship
the stream and query it, or use the audit command, which reads the store rather
than a process.

## Emitting your own

Two properties matter more than the schema:

**Assign the correlation id once**, when the permission is registered, and carry
it through every rotation. An id regenerated per presentation makes the stream
unjoinable, which is the failure mode that looks fine until the first time
somebody needs an answer.

**Emit refusals as loudly as successes.** `access.denied` and
`contract.rejected` are the events that tell you the system is working. A stream
with only the happy path cannot distinguish a healthy deployment from one where
enforcement is switched off.
