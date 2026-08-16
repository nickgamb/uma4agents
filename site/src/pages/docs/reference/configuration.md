---
templateKey: doc
title: Configuration
description: Every setting each component reads, its default, and the two settings people get wrong.
next:
  - title: Endpoints
    to: /docs/reference/endpoints/
    blurb: The surfaces these settings point at each other.
  - title: Deploy it at scale
    to: /docs/guides/at-scale/
    blurb: Where the split-horizon settings start to matter.
---

Environment variables, by component. Defaults are the lab's, and every default
assumes the `*.uma.lab` names the lab issues certificates for.

## The authorization server

| Variable | Default | Meaning |
|---|---|---|
| `UMA_AS_ISSUER` | `https://alice-as.uma.lab` | The issuer this authority claims in tokens it mints |
| `UMA_AS_SIGNING_KEY` | `/keys/uma-as-ed25519.pem` | Signing key for RPTs, receipts and PATs |
| `UMA_AS_OWNER_AUTH` | `oidc` | Comma-separated: `oidc`, `local-key`, or both. Each accepted credential is independently sufficient |
| `UMA_AS_OWNER_KEY` | `/keys/owner-ed25519.pub` | Her enrolled device key, for `local-key`. Public half only |
| `UMA_AS_OWNER_AUTHORITY` | host part of the issuer | The authority her signature base is rebuilt against. Configuration, never the request |
| `UMA_AS_OWNER_ISSUER` | `https://keycloak.uma.lab/realms/alice` | The issuer the owner's tokens must claim |
| `UMA_AS_OWNER_METADATA_URL` | `{OWNER_ISSUER}/.well-known/openid-configuration` | Where to fetch her identity provider's metadata |
| `UMA_AS_OWNER` | `alice` | The owner's username |
| `UMA_AS_OWNER_CLIENTS` | `alice-portal` | Comma-separated audiences accepted on owner tokens |
| `UMA_AS_PENDING_TTL` | `3600` | How long a held ask-me ticket stays valid, in seconds |
| `UMA_AS_STORE` | `memory` | `memory` or `postgres` |
| `UMA_AS_DATABASE_URL` | — | Required when the store is `postgres` |
| `UMA4A_CA_BUNDLE` | — | Trust bundle used when dereferencing agent-token issuers |

Replicated deployments need `postgres` and a **shared signing key**. Three
instances minting their own keys are three authorities wearing one name.

`UMA_AS_PENDING_TTL` defaults to an hour because the premise is that the owner
may be asleep. That is only safe because the requesting side hands the wait up
rather than holding a call open across it.

## The enforcement point

| Variable | Default | Meaning |
|---|---|---|
| `UMA_AS_PUBLIC` | `https://alice-as.uma.lab` | The authority's public identifier, put in challenges |
| `UMA_AS_INTERNAL` | `http://uma-as:9000` | Where to reach it for protection API calls |
| `UMA_AS_RS_CLIENT_ID` | `meridian-gateway` | This resource server's client id, for PAT issuance |
| `UMA_AS_RS_CLIENT_SECRET` | `gateway-dev-secret` | Its secret |
| `UMA_REALM` | `alice-vault` | Protection realm named in the challenge |
| `UMA_OWNER` | `alice` | The owner whose resources are protected |
| `UMA_PEP_SIGNING_KEY` | `/keys/uma-pep-ed25519.pem` | Key for `signed_metadata` and signed queries |
| `UMA_EXPECTED_AUTHORITY` | `gateway.uma.lab` | The authority used to rebuild the RFC 9421 signature base |
| `UMA_ALLOWED_ORIGINS` | derived from the authority | Origins accepted on MCP requests |
| `UMA_PEP_SCHEME` | `https` | The scheme of the URLs it publishes. `http` for a deployment with no certificate authority |

`UMA_EXPECTED_AUTHORITY` is the setting to get right. The signature base needs
an authority, and taking it from the `Host` header gives the caller control of
an authorization input. It also breaks portability: behind a proxy, `Host`
frequently arrives as the authorization service's own address, and no
configuration change fixes it after the fact.

## The resource

| Variable | Default | Meaning |
|---|---|---|
| `ENFORCEMENT_MODE` | `gateway` | `gateway` or `embedded` |
| `UMA_EXPECTED_AUTHORITY` | `gateway.uma.lab` | As above, when enforcing in-process |
| `UMA_AS_INTERNAL`, `UMA_AS_PUBLIC` | as above | Read by the embedded enforcement core |

Under `gateway` the resource holds no authorization code. Under `embedded` it
runs the same enforcement core in-process and there is no gateway in the
authorization path.

## The owner's portal

| Variable | Default | Meaning |
|---|---|---|
| `UMA_AS_INTERNAL` | `http://uma-as:9000` | Where to reach the owner API |
| `VAULT_MCP_URL` | `http://alice-vault-mcp:9020/mcp` | The resource, for her own reads |
| `PORTAL_AUTH` | `oidc` | Authentication mode |
| `OIDC_ISSUER` | `https://keycloak.uma.lab/realms/alice` | The issuer her tokens must claim |
| `OIDC_METADATA_URL` | derived from the issuer | Where to fetch that provider's metadata |
| `PORTAL_PUBLIC_URL` | — | The address her browser reaches the portal at |
| `OIDC_CLIENT_ID` | `alice-portal` | Client id |
| `PORTAL_SESSION_SECRET` | `dev-session-secret` | Session signing secret. Set it in any real deployment |

## The agent shim

| Variable | Default | Meaning |
|---|---|---|
| `UMA4A_GATEWAY` | `https://gateway.uma.lab/mcp` | The resource endpoint |
| `UMA4A_KEYSTORE` | `~/.uma4agents/agent-key.pem` | The agent's signing key |
| `UMA4A_RECEIPTS` | `<keystore dir>/receipts` | Where the agent's copies of receipts are kept |
| `UMA4A_CACERT` | `certs/rootCA.pem` | Trust bundle for the lab's names |
| `UMA4A_STANDING_MAX_EXPIRES` | `604800` | Longest `expires_in` a standing configuration will accept |
| `UMA4A_AGENT_ISSUER` | — | Set to run identified rather than pseudonymous |
| `UMA4A_PERSON_TOKEN` | — | The person token used to obtain an agent token |
| `UMA4A_PEND_HANDBACK` | `15` | Seconds before the wait is handed up to the agent's user |
| `UMA4A_TRACING` | `1` | `0`, `false` or `no` disables traceparent generation |

**Each agent gets its own keystore.** The key is the pseudonymous identity, so
two agents sharing a keystore are one agent to the owner. Point
`UMA4A_KEYSTORE` somewhere distinct per agent and each gets its own connection,
its own terms agreements and its own grants.

## The two settings people get wrong

**Issuer versus metadata URL.** An issuer is an *identifier* — what a token
claims. A metadata URL is a *fetch location* — where keys are read from.
Normally the same origin answers both, and they come apart the moment a
deployment is reachable under two names: a tunnel, a preview environment, an
internal address alongside a public one. The token then claims the address the
browser used, while this process can only reach the internal one.

Configure them separately. `UMA_AS_OWNER_ISSUER` and
`UMA_AS_OWNER_METADATA_URL`, `OIDC_ISSUER` and `OIDC_METADATA_URL`, are the same
split applied twice.

**Trust bundles that replace rather than add.** On some runtimes, setting a
certificate file **replaces** the system trust store. That is fine inside a mesh
where every name is yours, and it breaks the instant a component has to fetch
something from a public URL. Symptom: TLS failures reaching a real identity
provider or a tunnelled hostname, while everything internal works. Keep the
private bundle for private names and leave platform trust in place for
everything else.

## Split-horizon deployments

When the deployment is reachable under two names, these are the settings that
have to be told about the public one:

| Component | Setting |
|---|---|
| Identity provider | Its own hostname setting, plus dynamic backchannel resolution |
| Portal | `PORTAL_PUBLIC_URL`, `OIDC_ISSUER`, `OIDC_METADATA_URL` |
| Authorization server | `UMA_AS_OWNER_ISSUER`, `UMA_AS_OWNER_METADATA_URL` |
| Identity provider clients | Redirect URIs matching the public address |

The lab's Codespaces path does this in `.devcontainer/expose-web.sh`, which is
worth reading as a worked example rather than copied.
