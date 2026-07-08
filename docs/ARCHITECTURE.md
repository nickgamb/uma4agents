# Architecture

A reference for understanding, operating, or reimplementing the lab. The wire
contract itself — every endpoint, claim, and error — is in
[PROTOCOL.md](PROTOCOL.md); this document is the system view.

## The cast

```
┌────────────────────┐         ┌──────────────────────────────────────────┐
│  Bob's agent       │         │  Alice's authorization server (her side)  │
│  (Claude, or any   │         │                                            │
│   MCP client)      │         │   keycloak      identity, OIDC login       │
│        │           │         │   uma-as        grant loop, policy,        │
│   agent-shim  ─────┼─signed──┼─▶               tickets, RPTs, ledger,     │
│   (keys, RFC 9421, │  MCP    │                 connections                │
│    grant dance)    │         │   alice-portal  Alice's brokerage UI +     │
└────────────────────┘         │                 agent-authorization panel  │
         │                     └──────────────────────────────────────────┘
         ▼                                    ▲
┌────────────────────┐   ext_authz (HTTP)     │ owner API / introspection
│  agentgateway      │─────────▶ uma-pep ─────┘
│  (the PEP/gateway) │           (enforcement: challenge, introspect,
│        │           │            proof-of-possession, tool scoping)
│        ▼           │
│  alice-vault-mcp   │  Alice's brokerage data (positions, transactions,
│  (unmodified MCP)  │  execute) — contains zero auth code
└────────────────────┘

Supporting: person-server (the AAuth agent-identity component, present for the
identified-level path; the demo default is pseudonymous keys), Grafana + Loki
+ Promtail (protocol-event observability), Envoy edge (TLS for *.uma.lab),
hickory-dns.
```

The defining split: **Alice reads and trades her own vault directly** through
her portal (she owns it). **Other people's agents** reach the same vault only
through the gateway, and only after negotiating a grant against her policy.
The gateway and the grant loop exist for the second case.

## Services

| Service | Role | Language / base |
|---|---|---|
| `uma-as` | Alice's authorization server: the four-beat grant loop, tiered policy, ticket lifecycle, RPT issuance, connections, ledger, owner API, SSE | Python / FastAPI |
| `uma-pep` | Policy-enforcement point behind the gateway: challenges, RPT introspection, proof-of-possession verification, tool→resource scoping, single-use operation binding | Python / FastAPI |
| `agentgateway` | The MCP gateway/PEP host; delegates authz to `uma-pep` via HTTP ext_authz | Solo.io agentgateway |
| `alice-vault-mcp` | Alice's brokerage vault as an MCP server (fixture data); unaware it is protected | Python / MCP SDK |
| `alice-portal` | Meridian Wealth: dashboard, holdings, trade, and Settings → Security → Agent Authorization | Python / FastAPI + vanilla SPA |
| `keycloak` | Alice's identity provider and OIDC login for the portal | Keycloak |
| `person-server` | AAuth Person/Agent server — the agent-identity component for the identified-level path (the demo default signs pseudonymously) | upstream (pinned) |
| `agent-shim` | Local proxy that lets an unmodified MCP client be the requesting agent | Python / MCP SDK |
| observability | Grafana + Loki + Promtail; one structured event per protocol step, ticket = correlation id | Grafana stack |

Shared code in `lib/`: `uma4a_http_sig.py` (RFC 9421 signing/verification, used
by both shim and PEP so signer and verifier can't drift) and `uma4a_grant.py`
(the requesting-agent side of the grant loop, used by both the shim and the
headless demo driver).

## The four-beat grant (agent's view)

1. **Challenge** — agent calls a tool through the gateway; gets `401` +
   `WWW-Authenticate: UMA` carrying the AS location and a permission ticket.
2. **Attempt** — agent presents the ticket at Alice's AS token endpoint; the
   AS answers `need_info` with the terms template it dictates for that tier.
3. **Commit** — agent signs the intent contract (echoing the dictated terms)
   and re-presents it. For a new agent, or an ask-me tier, the AS returns
   `request_submitted` and holds the ticket until Alice decides in her portal.
4. **Grant** — the AS issues a proof-of-possession RPT; the agent retries the
   signed call and the gateway lets it through after introspection.

Everything else — resource registration, the PAT, introspection — is setup the
agent never sees. Discovery is declarative too: the gateway publishes RFC 9728
Protected Resource Metadata (`/.well-known/oauth-protected-resource`) naming
the owner's AS and the protected tool surfaces. See [PROTOCOL.md](PROTOCOL.md)
for the exact messages.

## The day-1 handshake (first contact)

Trust between Alice and a new agent is established the first time that agent
presents her terms:

- An agent with **no standing connection** pends on first contact regardless of
  tier — UMA's `request_submitted` doing double duty as owner-mediated agent
  registration. Alice sees the request in her portal (identity level, the
  agent's key thumbprint, the operation, the prohibitions it signed).
- **Approval** records a connection keyed by the agent's RFC 7638 JWK
  thumbprint. Thereafter, non-ask-me tiers auto-grant *for that connection*;
  ask-me tiers still pend per operation.
- **Revocation** (Connected Agents → Revoke) deactivates the connection and any
  live RPTs immediately.

This is how the standing relationship — "my advisor's agent" versus "a stranger
who happened to accept my terms" — is formed and governed.

## Tiers and policy

Alice's policy is a small, legible document (`services/uma-as/policy.py`),
editable from the portal as a form or as JSON in the Monaco editor. Each tier
names the resources it covers, the terms template the AS dictates, and whether
granting requires asking her:

- **Tier 1 — holdings summary**: auto-grant under standard terms.
- **Tier 2 — transaction history**: auto-grant under visibly stricter terms.
- **Tier 3 — trade execution**: `ask_me` — pends for per-operation approval and
  yields a single-use, operation-bound grant.

## Ports and hostnames

TLS everywhere via the Envoy edge and a local CA (`make init`). Browser access
uses the hostnames; the smoke tests and demo driver pin DNS and the CA
explicitly so they work without host configuration.

| Hostname | Service |
|---|---|
| `portal.uma.lab` | Alice's portal |
| `gateway.uma.lab` | agentgateway (agents connect here: `/mcp`) |
| `alice-as.uma.lab` | uma-as (token, introspection, owner API) |
| `keycloak.uma.lab` | Keycloak |
| `grafana.uma.lab` | Grafana |
| `ps.uma.lab` | person-server |

## Reimplementing this

The grant semantics live entirely in `uma-as` and `uma-pep` and are
transport-agnostic in shape: `uma-as` depends on Keycloak only for Alice's
identity and signs its own tokens; `uma-pep` is a generic ext_authz service any
Envoy-family gateway can call. To port the pattern, keep the four-beat contract
and the connection model from [PROTOCOL.md](PROTOCOL.md) and swap the identity
provider, gateway, or resource layer as needed.
