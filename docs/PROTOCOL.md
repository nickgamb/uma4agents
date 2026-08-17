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
| agentgateway + uma-pep | `gateway.uma.lab` | RS-side PEP in the default deployment; holds the PAT; carries the FedAuthz obligations |
| alice-vault-mcp | (internal) | The resource. Holds no auth code under `ENFORCEMENT_MODE=gateway`; under `embedded` it runs the same enforcement core in-process and there is no gateway in the authorization path |
| agent-operator | `agent.uma.lab` | The requesting firm's public presence: its CIMD document and Web Bot Auth key directory |
| uma-as | `alice-as.uma.lab` | Alice's authorization server (beside Keycloak) |
| alice-portal | `portal.uma.lab` | Alice's consent / policy / audit surface |

### uma-as endpoints

```
GET  /.well-known/uma4agents-configuration   discovery: issuer, endpoints, jwks_uri,
                                             claim formats accepted
GET  /jwks                                   uma-as signing keys (RPTs, receipts, PATs)
GET  /terms                                  the owner's terms roster (MyTerms pattern)
GET  /terms/{template_id}                    a proffered terms document; every version
                                             stays dereferenceable (persistent record).
                                             Three representations at one URI: JSON
                                             (default), plain-language HTML
                                             (Accept: text/html — IEEE 7012 4.4.1),
                                             JSON-LD/ODRL (?format=jsonld — 4.4.2)

# Protection API (resource servers only, PAT-authorized — FedAuthz shape).
# The PAT is an OAuth access token this AS issues (see /token below): signed,
# expiring, scope uma_protection, carrying the owner (sub) and the RS (azp).
# Registration is declarative — there is no /rreg on this line; the AS reads
# what the RS publishes (see Registration below). /perm rejects unregistered
# resources (invalid_resource_id) and excess scopes (invalid_scope).
POST   /perm            register attempted permissions -> ticket
POST   /introspect      RPT introspection (permissions array). Never consumes by
                        default; an inactive answer carries an `error` reason
                        (invalid_signature | unknown_token | connection_revoked |
                        already_consumed | expired) so the PEP can tell a
                        re-negotiable failure from a settled one
POST   /consume         burn a single-use RPT — the atomic last step of
                        enforcement, called only after PoP and operation binding
                        have passed
POST   /audit/access    the PEP reports an allowed call (grounds the ledger's "touched")

# Token endpoint (agent-facing UMA 2.0 Grant shape, plus RS-facing PAT issuance)
POST /token         grant_type=uma-ticket            the four-beat negotiation loop
POST /token         grant_type=client_credentials    PAT for an owner-authorized RS
                    (scope=uma_protection; the owner can revoke the RS, which
                    kills issuance and verification at once)

# Owner API (portal only; takes the owner's own OIDC access token, validated
# against her realm's published keys — no static owner credential exists)
GET  /owner/pending                        requests in awaiting-owner state
POST /owner/pending/{family}/decision      approve | deny
GET  /owner/policies                       tier policy
POST /owner/policies                       add a tier of her own (over resources
                                           registered and not already governed)
PUT  /owner/policies/{tier_id}             edit a tier's terms / ask-me / rules
DELETE /owner/policies/{tier_id}           remove one; its resources become
                                           ungoverned, and ungoverned is denied
GET  /owner/policy-vocabulary              conditions a rule may use, and which
                                           of them may relax one
GET  /owner/resources                      registered resources joined with tiers
GET  /owner/resource-servers               RSs holding her protection access
POST /owner/resource-servers/{id}/revoke   cut an RS off from the Protection API
GET  /owner/connections                    standing agent relationships
POST /owner/connections/{handle}/revoke    revoke a connection + its live RPTs
GET  /owner/operators                      operators behind those connections
POST /owner/operators/block                shut out every agent one operator
                                           runs, revoking what is connected in
                                           the same step
POST /owner/operators/unblock              restores the right to negotiate, not
                                           the access that was withdrawn
GET  /owner/ledger                         the activity ledger
GET  /owner/events                         SSE stream -> the portal notification
```

### uma-pep endpoints (behind the gateway)

```
GET  /.well-known/oauth-protected-resource[/mcp]   RFC 9728 metadata (OAuth+DPoP
                                                   binding): structural, signed,
                                                   jwks_uri + tool_surfaces +
                                                   owner_resources_endpoint
GET  /.well-known/aauth-resource.json              AAuth-binding encoding of the same
                                                   public layer: access_mode +
                                                   r3_vocabularies (content-addressed),
                                                   same owner_resources_endpoint
GET  /jwks                                         the resource's signing keys
GET  /owner-resources                              owner-bound instances; served only
                                                   to an RFC 9421-signed query by the
                                                   owner's AS ("protected webfinger")
/check{path}                                       ext_authz decision endpoint
```

## The four beats

### Beat 0 — Discovery (two layers, two audiences)

Discovery is split by who may ask:

**Public — structure.** The gateway serves RFC 9728 Protected Resource
Metadata at `GET /.well-known/oauth-protected-resource[/mcp]`: the resource
identifier, the owner's `authorization_servers`, `scopes_supported`,
`jwks_uri`, `signed_metadata` (the same claims as a JWT under the resource's
key, so a relayed copy stays attributable), and two extension members —
`tool_surfaces` (tool names + scopes, *structural only*) and
`owner_resources_endpoint` (below). What the public document deliberately
omits is whose instances sit behind the resource: publishing which resources
Alice owns at an unauthenticated URI would be a privacy leak the old push
registration never had.

The public layer has **two binding encodings of the same structural facts**,
served side by side from one tool registry:

- **OAuth+DPoP binding** — the RFC 9728 document above (`tool_surfaces`).
- **AAuth binding** — `GET /.well-known/aauth-resource.json`: an
  `access_mode` (`four-party`, the federated topology this stack runs) and an
  R3 vocabulary (`r3_vocabularies`, content-addressed via a `digest` over the
  operation list), per AAuth's resource-metadata convention. R3 is the better
  home for the type layer — the content digest gives universal operations +
  scopes a stable id independent of any owner.

**Protected — instance.** `GET /owner-resources` (advertised by *both* public
documents, which point at the same endpoint) returns the owner-bound resource
instances — ids, names, scopes, owner — only to a querier that proves
possession of the owner's AS signing key: RFC 9421 message signatures over the
same profile the agent uses for proof-of-possession, verified against the AS's
published JWKS. A "protected webfinger" for Alice's stuff: discoverable, but
only by the party her consent already connected. This instance layer, and the
permission ticket, are **binding-independent** — only the public encoding
changes.

Agents consume the public layer: both clients fetch it (the driver before
any call; the shim on first challenge), validate `resource` (RFC 9728
§3.3), and **corroborate every challenge's `as_uri` against the published
`authorization_servers`** — a challenge naming an AS the resource never
published is refused. The AS consumes both layers (see Registration below).
The challenge remains authoritative for the ticket.

### Registration — how the AS learns what the RS protects

**Declarative, and the only method here.** The RS publishes; it never
registers. The AS fetches the public RFC 9728 document, verifies
`signed_metadata` against the resource's `jwks_uri`, then queries the
advertised `owner_resources_endpoint` with an RFC 9421-signed request and
materializes its registry from the response. One fetch replaces N
registration calls, and there is one registry with one writer.

Staleness is the price, and repairing it is the AS's job: an unknown
`resource_id` at `/perm` triggers a re-pull. That is the exact mirror of what
classic RReg demanded of the *RS* — noticing `invalid_resource_id` after an AS
restart and re-pushing.

*On the comparison.* Both methods were built and measured against an otherwise
identical stack, which is what [FINDINGS](../FINDINGS.md) rec 5 rests on. Push
registration is not carried forward here: the trade has been made, and keeping
two writers alive to re-argue it is cost without evidence. The RReg
implementation is preserved and runnable on the **`legacy/rreg-baseline`**
branch.

Deployment note (learned as a deadlock): in pull mode the pull and its
verification form a call cycle — the AS queries the RS while the RS
authenticates the AS against the AS's own JWKS. Signed-query verification
must either tolerate a live back-call (the AS must not block its service
loop on the pull) or verify against pre-cached keys.

### Beat 1 — Challenge

The agent calls a gateway-fronted MCP tool without (sufficient) authorization.
MCP session bootstrap and discovery (`initialize`, `tools/list`) pass
unauthenticated; only `tools/call` is protected. The PEP registers the attempt
at uma-as (`POST /perm` with `resource_id`, `resource_scopes`) and the gateway
answers:

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

**The challenge is a superset of the RAR-metadata step-up challenge, not a
rival to it.** `error` and `authorization_remediation` are
`draft-zehavi-oauth-rar-metadata`'s parameters, carrying the same base64url
JSON it defines; `scope` is RFC 6750 §3. Decoded:

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

`authorization_details` and `authorization_reference` are that draft
unchanged. `authorization_server` and `ticket` are the two additions, and
they are what make a third-party decision possible: the RAR-metadata flow
hands the client a template to submit to **its own** authorization server,
which cannot work when the resource belongs to someone else. Naming the
owner's AS, and handing back a ticket rather than a template, is the whole
difference — the client authors nothing and cannot widen what it was given.

Emitting the RAR vocabulary costs nothing (the resource id and scopes are
already known) and buys three things: a client that implements the
RAR-metadata draft can read most of this challenge without knowing UMA; a
downstream policy engine gets typed fields rather than only a digest; and the
`authorization_reference` lets a client holding many grants check whether it
already has a token for this shape without parsing it.

`resource_metadata` is RFC 9728 §5.1: the challenge names the document that
lets the client corroborate `as_uri` instead of taking an unauthenticated
header's word for it.

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
`agent_token` (an `aa-agent+jwt` from the agent's server, which the AS
verifies against the issuer's published keys via AAuth dwk discovery; its
`cnf.jwk` is the signing key) — so the same key both signs the agreement and,
later, proves possession of the RPT.

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

**The pend is a state to render, not a call to hold open.** A requesting side
that can express waiting to its own user should hand the wait up rather than
block. The shim does: after a short window it asks Bob the one question he can
answer — keep waiting, or stop — and on MCP 2026-07-28 the SDK turns that into
an `InputRequiredResult` with a `request_state` handle, so the call is
suspended and resumable instead of held. Alice's decision is still Alice's;
Bob's client just stops hanging on it.

What cannot be said in that structure is *who* is being waited on. MRTR's
`input_requests` is a closed union of `CreateMessageRequest |
ListRootsRequest | ElicitRequest`, all three of which address the client's own
user. A pend on a different principal has no typed slot.

**So today the subject travels as prose in the elicitation message — the block
below is a proposal, not something this implementation emits.** It is what
[MCP-BINDING.md](MCP-BINDING.md) and the ext-auth draft ask MCP to add:

```jsonc
"subject": {
  "party": "resource_owner",
  "is_requesting_party": false,
  "reachable_by_client": false,   // the client MUST NOT try to satisfy this
  "notified": true
}
```

`reachable_by_client` is the load-bearing field: without it a conforming
client will try to satisfy the wait from its own user, who has no part in the
decision.

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
owner's AS that **embeds the complete agent-signed agreement JWS** alongside
the `terms_uri`, agreement hash, agent key thumbprint, and negotiation
family. Both sides therefore hold identical, dually-signed copies of the
record (IEEE 7012 5.2.2/5.4.4): the owner's AS retains it with her ledger;
the shim persists the agent's copy to its receipts directory.

A requesting side that does not accept the proffered terms may end the
negotiation with `decline=true` at the token endpoint; the refusal is a
record too (IEEE 7012 5.2.4) — the owner's ledger gains a `refused` entry
naming the terms that were declined.

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
PoP …` header. The PEP then enforces **in this order**, and the order is
normative:

1. `POST /introspect` (PAT-authorized, non-consuming) — is the token live, and
   does the connection behind it still stand?
2. The tool maps to a `resource_id` present in `permissions`.
3. The request signature verifies against the RPT's `cnf` key — this is what
   makes the RPT proof-of-possession rather than bearer.
4. For single-use RPTs, an exact `operation.params_s256` match.
5. `POST /consume` — only now is the grant spent.

Consuming earlier, at step 1, is the intuitive placement and it is a denial of
service: anyone who observes the token can replay it unsigned and destroy an
approval the owner personally gave, without ever passing a check. Because the
sequence is check-then-act, the burn has to be both last and atomic; a caller
that loses the race is told `consumed: false` and must deny.

An inactive introspection carries a reason. `connection_revoked` is terminal —
the PEP answers `403 access_revoked` rather than a fresh challenge, because
re-negotiating cannot change an outcome the owner has already settled.
Everything else re-challenges. The call then reaches alice-vault-mcp.

## Standing relationships (the day-1 handshake)

A **connection** is the standing relationship an owner has with a specific
agent, keyed by a **handle** whose shape follows the agent's identity level:

- *Pseudonymous* — the RFC 7638 JWK thumbprint (`jkt:…`). The key *is* the
  identity, so it must persist for the relationship to persist.
- *Identified* — the issuer-qualified subject of the verified `aa-agent+jwt`
  (e.g. `aauth:…@ps.uma.lab`). AAuth session keys rotate per run, so a
  thumbprint-keyed connection would forget an identified agent every session;
  continuity lives in the token's issuer+subject. (The AS validates the
  agent token against its issuer's published keys — AAuth dwk discovery over
  https — before believing any of it.)

A connection is created when Alice approves a `kind=connection` request
(first contact), and it holds the identity level, a label,
first-seen/last-access timestamps, and status.

- While no active connection exists, first contact pends regardless of tier.
- Once active, non-ask-me tiers auto-grant for that agent; ask-me tiers still
  pend per operation.
- `POST /owner/connections/{handle}/revoke` sets the connection inactive and
  marks every live RPT bound to that handle consumed, so introspection fails
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
`terms.published`, `terms.declined`, `permission.registered`,
`challenge.issued`, `ticket.presented`, `need_info.terms_dictated`,
`contract.committed`, `contract.rejected`, `policy.evaluated`,
`policy.updated`, `ticket.awaiting_owner`, `owner.notified`,
`owner.decision`, `connection.approved`, `connection.revoked`, `rpt.issued`,
`receipt.issued`, `rpt.introspected`, `rpt.consumed`, `access.allowed`,
`access.denied`.

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
| 5 | Standing connection keyed by an identity handle (JWK thumbprint when pseudonymous, verified issuer-qualified subject when identified); `contract` (s256) on the RPT | — | Owner-visible, revocable relationships; promise/action/consent in one ledger. Identified agents' session keys rotate, so the key cannot be the relationship key |
| 6 | Public structural discovery in two binding encodings from one registry — RFC 9728 `tool_surfaces` (OAuth+DPoP) and AAuth `aauth-resource.json` `r3_vocabularies`, content-addressed (AAuth); `resource_metadata` on the UMA challenge; clients corroborate `as_uri` against published `authorization_servers` | PRM and AAuth resource metadata both predate this; UMA's challenge carries `as_uri` on faith | Declarative discovery of the AS and the surface, per binding; the challenge gains a TLS-anchored second witness. The encodings are stock (9728 §5.1, AAuth R3) — composing them with the UMA challenge, and sharing one protected instance layer beneath both, is the extension |
| 7 | `owner_resources_endpoint` PRM member + the protected owner-resources listing (RFC 9421-signed query by the owner's AS) | FedAuthz: RS pushes owner-bound registrations under the PAT | The privacy split: public metadata stays structural; whose instances sit behind the resource is served only to the owner's AS — "protected webfinger." Enables declarative registration; classic push RReg remains conformant and is preserved on `legacy/rreg-baseline` |
| 8 | Challenge specified as *parameters* (`as_uri`, `ticket`, `resource_metadata`, `realm`) with per-host encodings: `401 + WWW-Authenticate: UMA` where there is a status line, JSON-RPC `-32001` where there is not | UMA 2.0 mandates the `WWW-Authenticate` header | An enforcement point running in-process has no status line. Mandating the header excludes exactly the resource-side frameworks most likely to adopt this; both encodings run here against one AS, and one client reads both |
| 9 | Enforcement obligations hosted by either a gateway or the resource itself (`ENFORCEMENT_MODE=gateway|embedded`), from one core | FedAuthz names the obligations, not their host | The PEP is a role, not a product. Same maneuver the registration work used: two conformant hosts, one stack, so the claim is measured rather than argued |
| 10 | Consumption ordering made normative: introspect (non-consuming) → permissions → PoP → operation binding → `POST /consume`, atomic and last. Inactive introspection carries an `error` reason; `connection_revoked` is terminal | UMA 2.0 §3.3.1 does not say where in enforcement a single-use token is spent | The intuitive order — consume first — lets an unsigned replay destroy an approval the owner just gave. And a bare `{"active": false}` sends a revoked agent round a negotiation whose outcome is settled |
| 11 | Requesting-agent identity metadata: an optional CIMD `client_id` in the contract header (resolved, self-reference enforced, **display only**) and a Web Bot Auth `Signature-Agent` covered by the request signature | The agent is its key, or its issuer's token | The RqP ≠ RO cold-start problem: a party that has never met this agent needs to be able to say something true about it. Neither ever becomes an authorization input — the verifying key is always the RPT's `cnf`, and the connection handle is unchanged |

| 12 | Challenge carries `error="insufficient_authorization"` + `authorization_remediation` (RFC 9396 `authorization_details` + `authorization_reference`), plus `authorization_server` and `ticket` inside it | UMA's challenge carries `as_uri` + `ticket` only | Superset of `draft-zehavi-oauth-rar-metadata` rather than a rival: the same remediation payload, plus the two parameters that let a party who is not the caller decide. The same JSON rides the JSON-RPC encoding byte for byte, which shows the payload is portable and only the envelope is binding-specific |

Everything not listed here is intended to be stock UMA 2.0 / stock AAuth.

## Security considerations

The properties this contract depends on, and what breaks each one. Every item
here is enforced somewhere in the code and most are covered by a test; the
tests that prove refusals rather than permissions are `make k8s-policy-test`
and `make store-test`.

**Single-use must be indivisible.** Both the permission ticket and the
operation-bound RPT are spent exactly once. A check-then-act implementation is
correct in one process and wrong the moment there are two — two callers read
`consumed = false` and both are told yes. The store interface therefore exposes
`consume_ticket` / `consume_rpt` as *intents* that decide and record in one
step and report who won; a `get`/`put` interface reintroduces the race over the
network. See rec 9 in [FINDINGS.md](../FINDINGS.md).

**Consumption is ordered and last.** Introspect (non-consuming) → permissions →
PoP → operation binding → `POST /consume`. Consuming first lets an unsigned
replay destroy an approval the owner just gave.

**Authorization inputs never come from the transport.** The RFC 9421 signature
base is reconstructed from the enforcer's configured `expected_authority`, never
from `Host` or any forwarded header. An authority taken from a header is an
authority the caller can choose.

**A truncated body must fail closed.** When the gateway buffers a request for
the ext-authz callout it may truncate rather than refuse. A cut-off JSON-RPC
body does not parse and the method name disappears, which deny-by-default
catches but misreports. The enforcement point checks
`x-envoy-auth-partial-body` and refuses with a named reason.

**The resource server must not be able to read the owner's policy.** This is
the cross-principal property the whole profile exists for, and it is
structural, not advisory: the Protection API is PAT-scoped, and in the
Kubernetes reference the mesh denies the path outright. The paired assertion —
the enforcement point is refused Alice's policy (403) and allowed her published
keys (200) on the same port and workload — is the shortest statement of it.

**Agent-token issuers are trusted by dereference.** `verify_agent_token`
resolves `iss` via AAuth discovery over TLS and believes the published keys.
TLS on the issuer origin is the trust root (AAuth's own precondition), and
non-`https` issuers are rejected. There is deliberately **no issuer allowlist**
here: which issuers may attest agents to a given authorization server is a
deployment policy, not a wire-protocol rule, and a real deployment must supply
one.

**Liveness must not depend on a mutual dereference.** The AS pulls what the RS
publishes; the RS authenticates that pull by fetching the AS's keys mid-request.
Gating readiness on the pull deadlocks. `/health` is local-only; the separate
`/health/registry` reports whether the pull has landed and is explicitly not a
readiness probe.

**Revocation is atomic and immediate.** Revoking a connection burns live RPTs in
the same operation that flips the connection, not in a second step that can fail
independently; introspection of a revoked token carries `connection_revoked`,
which is terminal rather than an invitation to renegotiate.

**Not addressed here.** Signing-key rotation (the key is minted once and shared
by all replicas; `jwks_uri` makes rotation possible but nothing exercises it);
multiple authorization servers behind one resource server (RFC 9728 makes
`authorization_servers` an array, this profile configures one); and revocation
propagation beyond a single shared store.
