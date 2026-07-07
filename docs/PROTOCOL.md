# PROTOCOL — the four-beat wire contract (v0.1 draft)

The API of `services/uma-as`, which is both the demo's authorization server and
the reference implementation of the core grant semantics. Grounded in the UMA
2.0 Grant and Federated Authorization specifications and the AAuth draft; see
[ARCHITECTURE.md](ARCHITECTURE.md) for the system view.

Design rule: **stay inside UMA 2.0's wire surface wherever it already fits**
(`WWW-Authenticate: UMA`, `uma-ticket` grant, `need_info`, `request_submitted`,
introspection `permissions`), and mark every deviation as an explicit
extension. The deviations are the findings.

## Parties and endpoints

| Party | Host | Role |
|---|---|---|
| Bob's Claude + agent-shim | (host machine) | Requesting agent; holds `aa-agent+jwt` + signing key |
| agentgateway + ext_authz | `gateway.uma.lab` | RS-side PEP; holds the PAT; all FedAuthz obligations |
| alice-vault-mcp | (internal) | The resource server's backend; never speaks UMA |
| uma-as | `alice-as.uma.lab` | Alice's authorization server (beside Keycloak) |
| alice-portal | `portal.uma.lab` | Alice's consent/policy/audit surface |

### uma-as endpoints

```
GET  /.well-known/uma4agents-configuration   discovery: issuer, endpoints, jwks_uri,
                                             claim formats accepted
GET  /jwks                                   uma-as signing keys (RPTs, receipts)

# Protection API (gateway only, PAT-authorized — FedAuthz shape)
POST /rreg                                   register tool surface as resource
GET/PUT/DELETE /rreg/{id}                    manage resource registrations
POST /perm                                   register attempted permissions -> ticket
POST /introspect                             RPT introspection (permissions array)

# Grant API (agent-facing — UMA 2.0 Grant shape)
POST /token                                  grant_type=uma-ticket negotiation loop

# Owner API (portal only)
GET  /owner/pending                          tickets in awaiting-owner state
POST /owner/pending/{ticket_id}/decision     approve | deny (+ constraints)
GET  /owner/policies                         tier policy read/write
PUT  /owner/policies/{tier}
GET  /owner/ledger                           the audit ledger (promised/touched/approved)
GET  /owner/events                           SSE stream -> the portal buzz
```

## The four beats

### Beat 1 — Challenge

Agent calls a gateway-fronted MCP tool without (sufficient) authorization.
The ext_authz service registers the attempt at uma-as (`POST /perm` with
`resource_id`, `resource_scopes`) and the gateway answers:

```
HTTP/1.1 401 Unauthorized
WWW-Authenticate: UMA realm="alice-vault",
  as_uri="https://alice-as.uma.lab",
  ticket="<ticket>"
```

The primary challenge is stock UMA 2.0. An `AAuth-Requirement:
requirement=grant; as_uri=…; ticket=…` form may be emitted alongside it as a
binding profile, so AAuth-native agents can discover the grant layer through
their own challenge header; this belongs in the AAuth binding document.

### Beat 2 — Attempt

Shim → `POST /token` (signed request, RFC 9421, `Signature-Key` carrying the
agent token):

```
grant_type = urn:ietf:params:oauth:grant-type:uma-ticket
ticket     = <ticket>
```

uma-as answers `403 need_info` with a **rotated ticket** and the owner's
dictated terms. `required_claims` is standard UMA; `terms_template` inside the
required claim is **extension #1** — UMA lets the AS name acceptable claim
formats, we make it *dictate the content*:

```json
{
  "error": "need_info",
  "ticket": "<rotated>",
  "required_claims": [{
    "claim_type": "urn:uma4agents:claim:intent-contract",
    "claim_token_format": ["urn:uma4agents:format:intent-contract-v1+jws"],
    "friendly_name": "Alice's terms for holdings access",
    "terms_template": {
      "template_id": "alice/advisor-tier1/v1",
      "dictated_by": "https://alice-as.uma.lab",
      "purpose": "Suitability review for advisory onboarding",
      "scope": ["positions:read", "allocation:read"],
      "expires_in": 172800,
      "prohibited": ["retention-after-review", "marketing", "model-training"],
      "ticket_ref": "s256:<hash-of-ticket>",
      "nonce": "<nonce>"
    }
  }]
}
```

The AAuth mission reference (`approver` + `s256`) may appear as an additional
acceptable `claim_token_format` — attestation demanded by the owner's side.

### Beat 3 — Commit

The shim surfaces the terms to Bob (MCP elicitation; fallback: standing
config), then re-presents:

```
grant_type         = urn:ietf:params:oauth:grant-type:uma-ticket
ticket             = <rotated>
claim_token        = <base64url(intent-contract JWS)>
claim_token_format = urn:uma4agents:format:intent-contract-v1+jws
```

The **intent contract** is the terms template echoed and signed by the agent's
key (the same key the agent token binds — one keypair, provable both ways):

```json
{
  "iss": "<agent-id from aa-agent+jwt>",
  "aud": "https://alice-as.uma.lab",
  "iat": 1751900000,
  "template_id": "alice/advisor-tier1/v1",
  "purpose": "…", "scope": ["…"], "exp": 1752072800,
  "prohibited": ["…"],
  "ticket_ref": "s256:…", "nonce": "…"
}
```

uma-as verifies the signature against the agent's key, checks the echo matches
the dictated template (nonce, ticket_ref, no weakened fields), evaluates
Alice's tier policy, and stores the contract (content-addressed, `s256`) with
a uma-as-signed receipt for the ledger. Then one of:

- **Tier 1/2** → Beat 4 immediately.
- **Tier 3** → `403 request_submitted` + rotated ticket + `interval`
  (standard UMA 2.0), and uma-as pushes the pending item to the portal
  (`owner.notified` event). Agent re-presents the ticket after `interval`
  (each poll rotates it). Alice's decision flips the ticket to grantable or
  denied. Denial → `request_denied`; timeout → `invalid_grant` (expired).
- Policy failure → `request_denied`.

### Beat 4 — Grant

```json
{
  "access_token": "<RPT: aa-auth+jwt, cnf-bound>",
  "token_type": "PoP",
  "pct": "<persisted claims token>",
  "expires_in": 3600
}
```

The RPT is an `aa-auth+jwt` (**extension #2**: UMA's introspection
`permissions` array carried as a claim inside AAuth's PoP token):

```json
{
  "iss": "https://alice-as.uma.lab",
  "sub": "<agent-id>", "aud": "https://gateway.uma.lab",
  "cnf": { "jwk": { …agent signing key… } },
  "exp": 1751910000,
  "permissions": [
    { "resource_id": "alice-vault/positions", "resource_scopes": ["positions:read"], "exp": 1752072800 }
  ],
  "contract": "s256:<intent-contract-hash>",
  "single_use": false
}
```

**Tier 3 RPTs** additionally carry the operation binding — authority for *this
trade*, not trading authority:

```json
  "single_use": true,
  "operation": { "tool": "execute_trade",
                 "params_s256": "<hash of the exact approved order>" }
```

The agent retries the original MCP call, signed, with the RPT. The ext_authz
service introspects (`POST /introspect`, PAT-authorized), verifies the request
signature against `cnf`, checks tool/scope against `permissions` (and
`operation.params_s256` for single-use), marks single-use RPTs consumed, and
the call passes to alice-vault-mcp.

## Ticket lifecycle

```
issued ──presented──> need_info(rotated) ──committed──> granted (consumed)
                            │                     │
                            │                     ├──> awaiting-owner(rotated per poll)
                            │                     │       ├─ approved ─> granted
                            │                     │       ├─ denied ──> request_denied
                            │                     │       └─ expired ─> invalid_grant
                            └──(weakened echo / bad sig)──> request_denied
Every presentation consumes the ticket and, if negotiation continues, issues a
fresh one (UMA 2.0 single-use rule). The ticket id family (first ticket's id)
is the correlation ID for logging and audit.
```

## Structured protocol events

One JSON line per event to stdout → Loki. `corr` = the ticket family id;
the Grafana demo dashboard and `make audit` are views over this stream.

```json
{ "ts": "…", "corr": "tkt_8f3a…", "event": "need_info.terms_dictated",
  "actor": "uma-as", "tier": 1, "resource_id": "alice-vault/positions",
  "scopes": ["positions:read"], "contract_s256": null,
  "details": { "template_id": "alice/advisor-tier1/v1" } }
```

Event names (enum, append-only): `permission.registered`, `challenge.issued`,
`ticket.presented`, `need_info.terms_dictated`, `contract.committed`,
`policy.evaluated`, `ticket.awaiting_owner`, `owner.notified`,
`owner.decision`, `rpt.issued`, `rpt.introspected`, `rpt.consumed`,
`access.allowed`, `access.denied`, `trade.executed`.

The dinner ledger is a projection: **promised** = `contract.committed`,
**touched** = `access.allowed` + `trade.executed`, **personally approved** =
`owner.decision`.

## Extension register (deviations from UMA 2.0, each a finding)

| # | Extension | UMA 2.0 baseline | Why |
|---|---|---|---|
| 1 | `terms_template` inside `required_claims`; AS dictates claim *content* | AS names acceptable claim formats | The owner-dictated intent contract (2010 Requesting Party Policy, restored) |
| 2 | RPT = `aa-auth+jwt` with `permissions` claim; `token_type: PoP` | Bearer RPT, permissions visible only via introspection | "Genome stays, organs replaced" — AAuth binding |
| 3 | `operation` + `single_use` RPT claims | Per-permission scopes/expiry only | Tier 3 per-operation grants — approval permits one walk through the door |
| 4 | Owner push notification on `request_submitted` | RO intervention out of scope | The agent-era consent surface; UMA already holds the pending state |
| 5 | `contract` (s256) claim on RPT + signed receipts | — | Promise/action/consent in one ledger |

Everything not listed here is intended to be stock UMA 2.0 / stock AAuth.
