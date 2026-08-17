---
templateKey: doc
title: Wire contract
description: Every message that travels between the parties, in order, with the fields that carry meaning.
diagram: wire-inspector
diagramCaption: A quick index into the sections below, which carry the same messages in reading order with the detail around them.
next:
  - title: Endpoints
    to: /docs/reference/endpoints/
    blurb: The surfaces each party exposes.
  - title: Deviations from UMA 2.0
    to: /docs/reference/deviations/
    blurb: Which of these fields are extensions, and why each one exists.
---

The messages of the four-beat grant, in the order they travel. Conceptual
background is in [The four beats](/docs/overview/four-beats/); this page is the
field-by-field contract.

The repository's own copy is [`docs/PROTOCOL.md`](https://github.com/nickgamb/uma4agents/blob/main/docs/PROTOCOL.md).

## Beat 1 — Challenge

The enforcement point registers the attempt with the owner's authority, then
refuses. Over HTTP:

```
HTTP/1.1 401 Unauthorized
WWW-Authenticate: UMA realm="alice-vault",
  error="insufficient_authorization",
  as_uri="https://alice-as.uma.lab",
  ticket="<ticket>",
  resource_metadata="https://gateway.uma.lab/.well-known/oauth-protected-resource/mcp",
  scope="trades:execute",
  authorization_remediation="<base64url JSON>"
```

| Parameter | Source | Meaning |
|---|---|---|
| `realm` | UMA 2.0 | Protection realm |
| `as_uri` | UMA 2.0 | The owner's authorization server |
| `ticket` | UMA 2.0 | The negotiation handle |
| `scope` | RFC 6750 §3 | Scopes the call needed |
| `resource_metadata` | RFC 9728 §5.1 | The document that lets the client corroborate `as_uri` |
| `error`, `authorization_remediation` | `draft-zehavi-oauth-rar-metadata` | Structured remediation |

`authorization_remediation` decodes to:

```json
{
  "authorization_details": [{
    "type": "urn:uma4agents:authorization-details:tool-call",
    "locations": ["https://gateway.uma.lab"],
    "identifier": "alice-vault/execute_trade",
    "actions": ["execute_trade"],
    "datatypes": ["trades:execute"]
  }],
  "authorization_reference": "s256:6cR6qTmCj6s0S95MxCfdfwfXJ8myLtBg-PiL8v93H0g",
  "authorization_server": "https://alice-as.uma.lab",
  "ticket": "<ticket>"
}
```

`authorization_details` and `authorization_reference` are that draft unchanged.
`authorization_server` and `ticket` are the two additions, and they are what let
a party who is not the caller decide.

**Non-HTTP encoding.** Where there is no status line, the same JSON rides a
JSON-RPC error (code `-32001`). The challenge is specified as *parameters*; each
binding says how they travel. See [MCP binding](/docs/reference/mcp-binding/).

## Beat 2 — Attempt

```
POST /token
grant_type = urn:ietf:params:oauth:grant-type:uma-ticket
ticket     = <ticket>
```

Answered with `403 need_info`, a rotated ticket, and the owner's terms:

```json
{
  "error": "need_info",
  "ticket": "<rotated>",
  "required_claims": [{
    "claim_type": "urn:uma4agents:claim:myterms-agreement",
    "claim_token_format": ["urn:uma4agents:format:myterms-agreement-v1+jws"],
    "friendly_name": "Alice's terms: Holdings summary",
    "terms_template": {
      "template_id": "alice/advisor-tier1/v2",
      "terms_uri": "https://alice-as.uma.lab/terms/alice/advisor-tier1/v2",
      "proffered_by": "https://alice-as.uma.lab",
      "purpose": "Suitability review for advisory onboarding",
      "scope": ["positions:read"],
      "expires_in": 172800,
      "prohibited": ["retention-after-review", "marketing", "model-training"],
      "resource_id": "alice-vault/get_positions",
      "family": "<negotiation-family-id>",
      "nonce": "<nonce>"
    }
  }]
}
```

An AAuth mission reference (`approver` + `s256`) may be offered as an additional
acceptable `claim_token_format`.

## Beat 3 — Commit

```
POST /token
grant_type         = urn:ietf:params:oauth:grant-type:uma-ticket
ticket             = <rotated>
claim_token        = <base64url(agreement JWS)>
claim_token_format = urn:uma4agents:format:myterms-agreement-v1+jws
```

The agreement is the template echoed and signed by the agent's key:

```json
{
  "iss": "aauth:agent:<keyid>",
  "aud": "https://alice-as.uma.lab",
  "iat": 1751900000,
  "template_id": "alice/advisor-tier1/v2",
  "terms_uri": "https://alice-as.uma.lab/terms/alice/advisor-tier1/v2",
  "purpose": "Suitability review for advisory onboarding",
  "scope": ["positions:read"],
  "expires_in": 172800,
  "prohibited": ["retention-after-review", "marketing", "model-training"],
  "family": "<negotiation-family-id>",
  "nonce": "<nonce>"
}
```

The header may also carry `client_id`, a URL describing who operates the agent,
and `signature_agent`, the operator's key directory. Both are optional and
neither widens anything: the authorization server resolves them itself, and what
it learns can only make a request stricter. See
[agent assurance](/docs/overview/assurance/).

The JWS protected header carries either `jwk` (pseudonymous bare key) or an
`agent_token` (an `aa-agent+jwt` whose `cnf.jwk` is the signing key, verified
against the issuer's published keys). The same key signs the agreement and later
proves possession of the grant.

**Verification.** Signature against the header key; echo matches the proffered
template on nonce, family, template id, terms URI and purpose; `prohibited` not
weakened; `expires_in` not extended; an operation present if the tier is
per-operation. Then policy, then one of:

| Outcome | Response |
|---|---|
| Known connection, non-ask-me tier | Grant (beat 4) |
| New agent, any tier | `403 request_submitted`, `kind=connection` |
| Ask-me tier | `403 request_submitted`, `kind=operation` |
| Weakened echo, bad signature, policy failure | `request_denied` |

A requesting side that will not accept the terms may end the negotiation with
`decline=true`; the refusal is recorded in the owner's ledger.

## Beat 4 — Grant

```json
{
  "access_token": "<RPT: aa-auth+jwt, cnf-bound>",
  "token_type": "PoP",
  "expires_in": 3600,
  "receipt": "<myterms-receipt+jws>"
}
```

The RPT:

```json
{
  "iss": "https://alice-as.uma.lab",
  "sub": "<agent id or pseudonymous handle>",
  "aud": "https://gateway.uma.lab",
  "jti": "rpt_<id>",
  "exp": 1751910000,
  "cnf": { "jwk": { "…agent signing key…": "" } },
  "permissions": [
    { "resource_id": "alice-vault/get_positions",
      "resource_scopes": ["positions:read"], "exp": 1752072800 }
  ],
  "contract": "s256:<agreement-hash>"
}
```

Ask-me grants additionally carry:

```json
  "single_use": true,
  "operation": { "tool": "execute_trade",
                 "params_s256": "<hash of the exact approved order>" }
```

The `receipt` is a JWS counter-signed by the owner's authority that embeds the
complete agent-signed agreement alongside the terms URI, agreement hash, agent
key thumbprint and negotiation family. Both sides hold identical, dually-signed
copies.

## The authorized call

The agent retries with an RFC 9421 signature over `@method @authority @path
authorization`, the RPT in an `Authorization: PoP …` header.

The enforcement point checks **in this order**, and the order is normative:

1. `POST /introspect` — non-consuming. Is the token live, does the connection
   still stand?
2. The tool maps to a `resource_id` present in `permissions`.
3. The request signature verifies against the RPT's `cnf` key.
4. For single-use grants, an exact `operation.params_s256` match.
5. `POST /consume` — atomic, and only now.

Consuming earlier lets an unsigned replay destroy an approval the owner
personally gave. A caller that loses the consume race is told `consumed: false`
and must deny.

## Introspection reasons

An inactive answer carries a reason, so a re-negotiable failure is
distinguishable from a settled one:

| Reason | Enforcement point's response |
|---|---|
| `connection_revoked` | `403 access_revoked` — terminal, do not re-challenge |
| `already_consumed` | Fresh challenge |
| `expired` | Fresh challenge |
| `unknown_token` | Fresh challenge |
| `invalid_signature` | Fresh challenge |

## Ticket lifecycle

<!--figure:ticket-lifecycle-->

Every presentation consumes the ticket and, if the negotiation continues, issues
a fresh one. The **family** id, assigned when the permission is registered, is
stable across rotations and is the correlation id for logging, audit and owner
decisions.

## Connections

A connection is the standing relationship between an owner and a specific agent,
keyed by a handle whose shape follows the agent's identity level:

| Identity level | Handle | Why |
|---|---|---|
| Pseudonymous | RFC 7638 JWK thumbprint (`jkt:…`) | The key is the identity, so it must persist for the relationship to persist |
| Identified | Issuer-qualified subject of the verified `aa-agent+jwt` | Session keys rotate; a thumbprint-keyed connection would forget the agent every session |

While no active connection exists, first contact pends regardless of tier. Once
active, non-ask-me tiers auto-grant for that agent; ask-me tiers still pend per
operation. Revoking a connection marks every live grant bound to that handle
consumed in the same operation.
