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
| `UMA_AS_OWNER` | `alice` | The one owner this authority serves. Set it and every request naming anybody else is refused at the door rather than served and filtered. Leave it unset for a deployment holding many, where `UMA_AS_DEFAULT_OWNER` names the one an unqualified request means |
| `UMA_AS_DEFAULT_OWNER` | `alice` | On a server holding many owners, the one an unqualified request means. Ignored where `UMA_AS_OWNER` is set, which is its own answer |
| `UMA_AS_OWNER_KEY_OWNER` | the default owner | Which owner the enrolled device key speaks for. A signature proves a holder, not a name, so on a server holding many owners the binding has to be configured rather than inferred |
| `UMA_AS_RS_META_TTL` | `300` | Seconds a resource server's RFC 9728 document is cached after it checked out |
| `UMA_AS_RS_MISS_TTL` | `30` | Seconds a resource that did **not** check out is remembered as refused. Bounds how much outbound fetching an unauthenticated caller can cause — the opposite policy to `UMA_AS_DIRECTORY_TTL` above, and the reasoning is in [many owners](/docs/overview/multi-owner/) |
| `UMA_AS_RS_MAX_BYTES` | `65536` | How much of a document fetched from a caller-named origin is read before it is refused |
| `UMA_AS_SEED_RS` | `1` | Whether to seed a resource server this authority was provisioned alongside. `0` seeds none, which is the case where the authority is the owner's and nobody could have configured both ends — the resource server introduces itself instead |
| `UMA_AS_PEND_BUDGET` | `5` | How many requests from agents with no standing, and nobody checkable behind them, may wait for her at once. `0` makes her authority introduce-yourself-first |
| `UMA_AS_PEND_BUDGET_ATTRIBUTED` | `40` | The same cap for agents whose named operator published their key. A separate lane, so a flood of the cheap kind cannot fill it |
| `UMA_AS_MAX_REASON` | `512` | How much the requesting side may write about its own errand. Small on purpose: a sentence for a person to read in an approval, not a document |
| `UMA_AS_TRAJECTORY_WINDOW` | `7d` | How far back a rule about an agent's recent behaviour looks. One window for all of them, so a rule reads *recently* and the deployment says how long that is |
| `UMA_AS_DIRECTORY_TTL` | `300` | Seconds an operator key directory is cached **for a hit only**. A miss is always re-fetched, because a stale hit keeps attesting a key the operator has disowned while a stale miss merely fails to recognise one just published |
| `UMA_AS_OWNER_CLIENTS` | `meridian-portal` | Comma-separated audiences accepted on owner tokens |
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
| `UMA_AS_RS_CLIENT_SECRET` | `gateway-dev-secret` | Its secret, where one authority was provisioned alongside it |
| `UMA_PEP_RS_SECRETS` | `{"<owner>": "<secret>"}` | Per owner, and the interesting part is who is missing. An owner named here is one whose authority this resource server holds a credential for. Any other owner it serves is one it must introduce itself to, by signing with the key it publishes at its own origin |
| `UMA_EXTRA_OWNERS` | — | Comma-separated. Every owner named gets `/mcp/<owner>`, with her own tool namespace, her own PAT and her own RFC 9728 metadata |
| `UMA_OWNER_AUTHORITIES` | — | JSON, owner → `{public, internal}`. Which authority governs which owner. This is the one thing that stays configuration: which server speaks for a person is a fact only that person holds, so she tells the resource server, the way she tells it an address |
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

## The organization's authority

Only present where an organization owns resources that are shared with
members — see [shared ownership](/docs/overview/shared-ownership/). With none
of it set, every line of that layer is inert.

| Variable | Default | Meaning |
|---|---|---|
| `ORG_ISSUER` | `https://northwind-org.uma.lab` | The organization's own origin. Members' authorities verify its notices, and enforcement points verify the grants it signs, against the keys published here |
| `ORG_ID` / `ORG_NAME` | `northwind` / `Northwind Capital` | What members are shown |
| `OPA_URL` | `http://opa:8181` | The policy engine. The charter's declarative conditions and the administrator's own Rego are both evaluated there |
| `ORG_ADMIN_ISSUER` | `…/realms/northwind` | The realm administrators sign in to. Deliberately not a member's realm — an identity provider that minted both would collapse the two layers |
| `ORG_ADMIN_CLIENTS` | `meridian-org-console` | Which client's tokens the admin API accepts |
| `ORG_ADMIN_TOKEN` | unset | A static credential for acceptance jobs with no browser. Never set where an identity provider is configured |
| `ORG_RS_TOKEN` | `org-rs-dev-token` | What an enforcement point presents to read membership and check the grants this service signs |
| `ORG_JOIN_CODE` | `NW-7K2F-QX` | The shared enrolment code. Invitations carry their own, addressed to one person |
| `ORG_BREAK_GLASS_AUDIENCE` | `https://gateway.uma.lab` | Who an override is issued *for*. Configuration rather than a field on the request: an audience the caller chooses is one it can aim at another resource server that also trusts this organization |
| `ORG_OPA_GRACE_S` | `60` | How long a decision may be answered from cache when the engine cannot be reached. Past it the answer is a refusal — a charter is the organization's protection of its own data, and a request that slipped through while the engine was down is exactly what it exists to prevent |

## A member's side of it

Read by the owner's authorization server. Naming an organization is not
enrolment and grants nothing: until she enters a code or accepts an
invitation, none of it does anything.

| Variable | Default | Meaning |
|---|---|---|
| `UMA_AS_ORG_ISSUER` | unset | Where an enrolment code is redeemed. One organization, because a code says nothing about who issued it; a deployment with many needs a directory, which the lab does not pretend to have |
| `UMA_AS_ORG_CALLBACK` | the AS issuer | The address the organization posts notices back to — its view of this server, which need not be the issuer an agent is challenged with |
| `UMA_AS_ORG_TTL_S` | `30` | How often the ceiling is re-read |
| `UMA_AS_ORG_STALE_MAX_S` | `600` | How long a copy that could not be refreshed still stands. Past it, requests over the organization's resources are refused: a ceiling nobody can read is not a ceiling |
| `UMA_AS_RESOURCE_REFRESH_S` | `15` | How often her own resource listing re-reads what the resource server publishes, while she is enrolled. What an organization shares with her changes elsewhere, and on a replicated authority only one replica is notified — so the listing repairs itself on a clock rather than waiting for a miss |
| `UMA_AS_ORG_TIMEOUT_S` | `5` | Per-request timeout when talking to the organization. A refusal, not a hang: her own resources are unaffected either way |

## The enforcement point's side of it

| Variable | Default | Meaning |
|---|---|---|
| `UMA_PEP_ORG_ISSUER` | unset | The organization above the owners this gateway fronts. Configured here rather than discovered from an owner's authority — that is the point: an owner may name any authorization server she likes, so the check that the organization's ceiling was applied has to come from somewhere she does not control |
| `UMA_PEP_ORG_INTERNAL` | the issuer | Where to reach it on the cluster network |
| `UMA_PEP_ORG_TOKEN` | unset | What this gateway presents to it |
| `UMA_PEP_MEMBERSHIP_TTL_S` | `10` | How long a cached answer about who is a member may be acted on. The window is somebody's access to the organization's resources *after* it was withdrawn, so it is short. Listings are always read fresh |
| `UMA_PEP_SHARED_PREFIX` | `mcp/shared` | The path an organization's resources are reached at, one segment per member |
| `UMA_PEP_SHARED_NAMESPACE` | `northwind-vault` | The resource-id namespace those resources publish under |

## The tally, for resources held jointly

Read by the party that counts verdicts over a resource with several owners of
equal standing — see [joint ownership](/docs/overview/joint-ownership/). With
none of it set, no account is jointly held and the whole layer is inert.

| Variable | Default | Meaning |
|---|---|---|
| `TALLY_ISSUER` | `https://joint-tally.uma.lab` | Its own origin. Holders' authorities verify its requests, and enforcement points verify its grants, against the keys published here |
| `TALLY_MANDATES` / `TALLY_MANDATES_FILE` | unset | The mandates it counts for. Configuration rather than an API, because a mandate names the electorate and a coordinator that could edit it would be deciding who gets a say |
| `TALLY_THRESHOLD_FLOOR` | `0` | A minimum the holders may not vote themselves below. A mandate under it is refused at startup, by name. This is what an account agreement or a regulator supplies in the world, and the only answer to what quorum sets the quorum |
| `TALLY_RS_SECRET` | `tally-rs-dev-secret` | What an enforcement point presents to mint tickets and introspect. It buys nothing that matters: the verdicts inside a grant are checked against the holders' published keys, not against this |
| `TALLY_SIGNING_KEY` | `/keys/tally-ed25519.pem` | Persisted, not generated per process — both holders' authorities cache what this service publishes, and a key that changed on restart reads as a broken mandate |

And on the enforcement point:

| Variable | Default | Meaning |
|---|---|---|
| `UMA_PEP_JOINT_TALLY` | unset | The tally it will accept grants from. Named rather than read off a token: a resource server that accepted whichever issuer embedded a plausible mandate would be taking the electorate from the party that assembled it |
| `UMA_PEP_JOINT_ACCOUNTS` | unset | Which accounts it fronts, at `/mcp/joint/<account>` |

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
