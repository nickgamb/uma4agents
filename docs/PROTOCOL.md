# PROTOCOL — the grant wire contract

The API of `services/uma-as`, which is both the demo's authorization server and
the reference implementation of the core grant semantics, plus the enforcement
`services/uma-pep` runs behind the gateway. Grounded in the UMA 2.0 Grant and
Federated Authorization specifications and the AAuth draft; see
[ARCHITECTURE.md](ARCHITECTURE.md) for the system view.

Design rule: **stay inside UMA 2.0's wire surface wherever it already fits**
(`WWW-Authenticate: UMA`, the `uma-ticket` grant, `need_info`,
`request_submitted`, introspection `permissions`), and mark every deviation as
an explicit extension. The deviations are the findings.

## Parties and endpoints

| Party | Host | Role |
|---|---|---|
| Requesting agent + agent-shim | (host machine) | Holds an Ed25519 signing key; optionally a PS-issued `aa-agent+jwt`. Default is pseudonymous (bare public key in the contract header) |
| agentgateway + uma-pep | `gateway.uma.lab` | RS-side PEP; holds the PAT; carries the FedAuthz obligations |
| alice-vault-mcp | (internal) | The resource server's backend; never speaks UMA |
| uma-as | `alice-as.uma.lab` | Alice's authorization server (beside Keycloak) |
| alice-portal | `portal.uma.lab` | Alice's consent / policy / audit surface |

### uma-as endpoints

```
GET  /.well-known/uma4agents-configuration   discovery: issuer, endpoints, jwks_uri,
                                             claim formats accepted
GET  /jwks                                   uma-as signing keys (RPTs, receipts)
GET  /terms                                  the owner's terms roster (MyTerms pattern)
GET  /terms/{template_id}                    a proffered terms document; every version
                                             stays dereferenceable (persistent record)

# Protection API (gateway/PEP only, PAT-authorized — FedAuthz shape)
POST /rreg          register a tool surface as a resource
GET  /rreg          list registered resources
POST /perm          register attempted permissions -> ticket
POST /introspect    RPT introspection (permissions array); consume=true burns single-use
POST /audit/access  the PEP reports an allowed call (grounds the ledger's "touched")

# Grant API (agent-facing — UMA 2.0 Grant shape)
POST /token         grant_type=uma-ticket negotiation loop

# Owner API (portal only, owner-token-authorized)
GET  /owner/pending                        requests in awaiting-owner state
POST /owner/pending/{family}/decision      approve | deny
GET  /owner/policies                       tier policy
PUT  /owner/policies/{tier_id}             edit a tier's terms / ask-me
GET  /owner/connections                    standing agent relationships
POST /owner/connections/{jkt}/revoke       revoke a connection + its live RPTs
GET  /owner/ledger                         the activity ledger
GET  /owner/events                         SSE stream -> the portal notification
```

### uma-pep endpoints (behind the gateway)

```
GET  /.well-known/oauth-protected-resource   RFC 9728 Protected Resource Metadata
/check{path}                                 ext_authz decision endpoint (all methods)
```

## The four beats

### Beat 0 — Discovery (optional)

The gateway serves RFC 9728 Protected Resource Metadata at
`GET /.well-known/oauth-protected-resource`: the resource identifier, the
owner's `authorization_servers`, `scopes_supported`, and — as an extension
member — `tool_surfaces`, the per-tool resource ids the gateway registers at
the AS. An agent can locate the owner's AS declaratively before its first
call; the challenge below remains authoritative for the ticket.

### Beat 1 — Challenge

The agent calls a gateway-fronted MCP tool without (sufficient) authorization.
MCP session bootstrap and discovery (`initialize`, `tools/list`) pass
unauthenticated; only `tools/call` is protected. The PEP registers the attempt
at uma-as (`POST /perm` with `resource_id`, `resource_scopes`) and the gateway
answers:

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

The agent presents the ticket at the AS token endpoint:

```
POST /token
grant_type = urn:ietf:params:oauth:grant-type:uma-ticket
ticket     = <ticket>
```

uma-as answers `403 need_info` with a **rotated ticket** and the owner's
proffered terms. `required_claims` is standard UMA; the `terms_template` inside
the required claim is **extension #1** — UMA lets the AS name acceptable claim
formats; here it *proffers the content* the requesting side must accept. This
is the MyTerms exchange (IEEE 7012, extended from privacy terms to agentic
access terms): the terms are a **persistent, dereferenceable document** on the
owner's roster (`terms_uri`, served at `GET /terms/…` for the life of the AS,
every version retained), and the signed echo returned in Beat 3 is the
reciprocal agreement.

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
acceptable `claim_token_format` — attestation demanded by the owner's side.

### Beat 3 — Commit

The shim surfaces the terms to the agent's human (MCP elicitation; fallback:
standing config), then re-presents the rotated ticket with the signed contract:

```
POST /token
grant_type         = urn:ietf:params:oauth:grant-type:uma-ticket
ticket             = <rotated>
claim_token        = <base64url(myterms-agreement JWS)>
claim_token_format = urn:uma4agents:format:myterms-agreement-v1+jws
```

The **agreement** is the terms template echoed and signed by the agent's key.
Its JWS protected header carries either `jwk` (the pseudonymous bare key) or an
`agent_token` (a PS-issued `aa-agent+jwt`, whose `cnf.jwk` is the signing key)
— so the same key both signs the agreement and, later, proves possession of
the RPT.

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

uma-as verifies the signature against the header key, checks the echo matches
the proffered template (nonce, family, template_id, `terms_uri` naming the
proffered document, purpose; prohibited not weakened; `expires_in` not
extended; an operation present if the tier is per-operation), evaluates
Alice's tier policy, and stores the agreement (content-addressed by `s256`).
Then one of:

- **Known connection, non-ask-me tier** → Beat 4 immediately.
- **New agent (no standing connection), any tier** → `403 request_submitted`
  as a *connection request*: uma-as holds the rotated ticket and pushes the
  pending item to the portal (`owner.notified`, `kind=connection`).
- **Ask-me tier (e.g. trade execution)** → `403 request_submitted` as an
  *operation approval* (`kind=operation`).
- **Policy failure / weakened echo / bad signature** → `request_denied`.

For a held ticket the agent re-presents after `interval` (each poll rotates
it). Alice's decision resolves it: approve → grant (and, for a connection
request, the standing relationship is recorded); deny → `request_denied`;
expiry → `invalid_grant`.

### Beat 4 — Grant

```json
{
  "access_token": "<RPT: aa-auth+jwt, cnf-bound>",
  "token_type": "PoP",
  "expires_in": 3600,
  "receipt": "<myterms-receipt+jws>"
}
```

The `receipt` completes the MyTerms exchange: a JWS counter-signed by the
owner's AS naming the `terms_uri`, the agreement hash, the agent's key
thumbprint, and the negotiation family — so **both sides hold the record**
(the owner's ledger keeps hers; the shim persists the agent's to its
receipts directory).

The RPT is an `aa-auth+jwt` (**extension #2**: UMA's introspection
`permissions` array carried as a claim inside a proof-of-possession token):

```json
{
  "iss": "https://alice-as.uma.lab",
  "sub": "<agent id or aauth:pseudonymous-agent>",
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

**Ask-me (tier 3) RPTs** additionally carry the operation binding — authority
for *this trade*, not trading authority:

```json
  "single_use": true,
  "operation": { "tool": "execute_trade",
                 "params_s256": "<hash of the exact approved order>" }
```

The agent retries the original MCP call — RFC 9421-signed over
`@method @authority @path authorization`, with the RPT in the `Authorization:
PoP …` header. The PEP introspects (`POST /introspect`, PAT-authorized),
verifies the request signature against the RPT's `cnf` key (this is what makes
the RPT proof-of-possession rather than bearer), checks the tool against
`permissions`, and — for single-use RPTs — requires an exact
`operation.params_s256` match and consumes the token. The call then reaches
alice-vault-mcp.

## Standing relationships (the day-1 handshake)

A **connection** is the standing relationship an owner has with a specific
agent, keyed by the agent's RFC 7638 JWK thumbprint (`jkt:…`). It is created
when Alice approves a `kind=connection` request (first contact), and it holds
the identity level, a label, first-seen/last-access timestamps, and status.

- While no active connection exists, first contact pends regardless of tier.
- Once active, non-ask-me tiers auto-grant for that agent; ask-me tiers still
  pend per operation.
- `POST /owner/connections/{jkt}/revoke` sets the connection inactive and marks
  every live RPT bound to that thumbprint consumed, so introspection fails
  immediately.

This is the standing-relationship handle discussed in
[FINDINGS.md](../FINDINGS.md); the PCT is its spec-native ancestor, here made
owner-visible and owner-revocable.

## Ticket lifecycle

```
issued ─present─▶ need_info(rotated) ─commit─▶ ┌─ known conn, open tier ─▶ granted (consumed)
                        │                       ├─ new agent (any tier) ──▶ awaiting-owner ┐
                        │                       └─ ask-me tier ───────────▶ awaiting-owner ┤
                        │                                                                   │
                        └─(weakened echo / bad sig / policy fail)─▶ request_denied          │
                                                                                            │
        awaiting-owner(rotated per poll):  approved ─▶ granted    denied ─▶ request_denied  │
                                           expired  ─▶ invalid_grant                        │
                                                       (connection recorded on approve) ◀───┘
```

Every presentation consumes the ticket and, if negotiation continues, issues a
fresh one (UMA 2.0 single-use rule). The negotiation **family** id (assigned at
`/perm`) is stable across rotations and is the correlation id for logging,
audit, and owner decisions.

## Structured protocol events

One JSON line per event to stdout → Loki. `corr` is the negotiation family id;
the Grafana dashboard, `make audit`, and the portal ledger are views over this
stream.

```json
{ "ts": "2026-07-07T18:21:27Z", "event": "need_info.terms_dictated",
  "corr": "fam_8f3a…", "actor": "uma-as",
  "details": { "tier": "tier1", "template_id": "alice/advisor-tier1/v2",
               "resource_id": "alice-vault/get_positions" } }
```

Emitted events: `resource.registered`, `resources.registered_at_startup`,
`terms.published`, `permission.registered`, `challenge.issued`,
`ticket.presented`, `need_info.terms_dictated`, `contract.committed`,
`contract.rejected`, `policy.evaluated`, `policy.updated`,
`ticket.awaiting_owner`, `owner.notified`, `owner.decision`,
`connection.approved`, `connection.revoked`, `rpt.issued`, `receipt.issued`,
`rpt.introspected`, `rpt.consumed`, `access.allowed`, `access.denied`.

The activity ledger is a projection: **promised** = `contract.committed`,
**touched** = `access.allowed`, **connected** = `connection.approved`,
**personally approved / denied** = `owner.decision`, **revoked** =
`connection.revoked`.

## Extension register (deviations from UMA 2.0, each a finding)

| # | Extension | UMA 2.0 baseline | Why |
|---|---|---|---|
| 1 | `terms_template` inside `required_claims`; AS proffers claim *content*, dereferenceable at a persistent `terms_uri`, with a counter-signed receipt returned on grant | AS names acceptable claim formats | Owner-proffered terms — MyTerms / IEEE 7012 extended to agentic access; descends from the 2010 Requesting Party Policy claim. Dual-held records: owner's ledger + agent's receipt |
| 2 | RPT = `aa-auth+jwt`, `cnf`-bound, `token_type: PoP`, `permissions` claim | Bearer RPT; permissions visible only via introspection | "Genome stays, organs replaced" — AAuth binding |
| 3 | `operation` + `single_use` RPT claims | Per-permission scopes/expiry only | Ask-me per-operation grants — approval permits one action |
| 4 | Owner push notification on `request_submitted`, in two kinds (connection / operation) | RO intervention out of scope | The agent-era consent surface; the day-1 handshake |
| 5 | Standing connection keyed by JWK thumbprint; `contract` (s256) on the RPT | — | Owner-visible, revocable relationships; promise/action/consent in one ledger |
| 6 | RFC 9728 PRM with a `tool_surfaces` extension member | PRM predates UMA; not profiled for it | Declarative discovery of the AS and the protected tool surface |

Everything not listed here is intended to be stock UMA 2.0 / stock AAuth.
