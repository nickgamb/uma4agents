---
templateKey: doc
title: Endpoints
description: Every surface each party exposes, who may call it, and what it answers.
next:
  - title: Events
    to: /docs/reference/events/
    blurb: What each of these emits, and how the ledger is projected from it.
  - title: Configuration
    to: /docs/reference/configuration/
    blurb: The settings that point these at each other.
---

Grouped by the party that operates them. Authorization column says who may call.

## The owner's authorization server

### Public

| Endpoint | Auth | Answers |
|---|---|---|
| `GET /.well-known/uma4agents-configuration` | none | Issuer, endpoints, `jwks_uri`, accepted claim formats |
| `GET /jwks` | none | Signing keys for RPTs, receipts and PATs |
| `GET /terms` | none | The owner's terms roster |
| `GET /terms/{template_id}` | none | A proffered terms document, every version dereferenceable |

`GET /terms/{template_id}` serves three representations at one URI: JSON by
default, plain-language HTML on `Accept: text/html`, and JSON-LD with ODRL
permissions and prohibitions on `?format=jsonld`.

### Token endpoint

| Grant type | Caller | Answers |
|---|---|---|
| `urn:ietf:params:oauth:grant-type:uma-ticket` | the agent | The four-beat loop |
| `client_credentials`, `scope=uma_protection` | an owner-authorized resource server | A PAT |

The PAT is an ordinary access token this authority issues: signed, expiring,
carrying the owner as subject and the resource server as authorized party. The
owner can revoke a resource server, which kills issuance and verification at
once.

A resource server holds one PAT per owner it serves, so `client_credentials`
takes the owner it is asking about — there is no default. It authenticates
with a client secret where the pair was provisioned together, and otherwise
with an RFC 9421 signature over the request from a key its own origin
publishes. Which of the two applies follows from the stored record, so a
resource server that registered by signature cannot fall back to guessing a
secret. While the owner has not yet authorized it, the answer is `403
authorization_pending` rather than a refusal.

### Establishment

| Endpoint | Auth | Answers |
|---|---|---|
| `POST /rs/register` | an RFC 9421 signature from a key published at the origin of the resource being claimed | `202` with `status: pending` |

How a resource server introduces itself to an authority nobody configured it
against. The authority fetches the RFC 9728 document at the claimed resource
and the JWKS it names, and requires that the document claim *this* resource,
name *this* authority, and be same-origin with its keys. Nothing is
provisioned in advance and no secret is transmitted.

Success settles who is asking and nothing else: the registration waits in the
owner's registry until she answers. See
[many owners, one resource server](/docs/overview/multi-owner/).

### Protection API

Resource servers only, PAT-authorized. FedAuthz shape.

| Endpoint | Answers |
|---|---|
| `POST /perm` | Registers attempted permissions, returns a ticket. Rejects unregistered resources (`invalid_resource_id`) and excess scopes (`invalid_scope`) |
| `POST /introspect` | RPT introspection with the `permissions` array. Never consumes; an inactive answer carries a reason |
| `POST /consume` | Burns a single-use RPT. The atomic last step of enforcement |
| `POST /audit/access` | The enforcement point reports an allowed call, grounding the ledger's "touched" column |

There is no `/rreg` on this line. Registration is declarative — the authority
reads what the resource server publishes. Classic push registration remains
conformant and is preserved on the `legacy/rreg-baseline` branch.

### Owner API

Takes a credential that is hers. Two are defined and a deployment may accept
both: an OIDC access token validated against her realm's published keys, or an
RFC 9421 signature from a key she enrolled. No static owner credential exists
either way. See [put the authority on her device](/docs/guides/personal-authority/).

| Endpoint | Answers |
|---|---|
| `GET /owner/pending` | Requests in awaiting-owner state |
| `POST /owner/pending/{family}/decision` | Approve or deny |
| `GET /owner/policies` | Tier policy |
| `POST /owner/policies` | Add a tier of her own, over resources that are registered and not already governed |
| `PUT /owner/policies/{tier_id}` | Edit a tier's terms, its ask-me flag, or its rules |
| `DELETE /owner/policies/{tier_id}` | Remove a tier. Its resources become ungoverned, and ungoverned is denied |
| `GET /owner/policy-vocabulary` | The conditions a rule may use, and which of them may relax one |
| `GET /owner/resources` | Registered resources joined with tiers |
| `GET /owner/resource-servers` | Resource servers holding her protection access, each `pending`, `active` or `revoked` |
| `POST /owner/resource-servers/decision` | Approve one that introduced itself, or withdraw one. Takes the `client_id` in the body, because a self-registered resource server is identified by an https URL |
| `POST /owner/resource-servers/{id}/revoke` | The same withdrawal by path, for relationships whose ids are plain names |
| `GET /owner/connections` | Standing agent relationships |
| `POST /owner/connections/{handle}/revoke` | Revoke a connection and its live RPTs |
| `GET /owner/operators` | The operators behind those connections, and whether any are blocked |
| `POST /owner/operators/block` | Shut out every agent one operator runs, revoking what is connected in the same step |
| `POST /owner/operators/unblock` | Restores the right to negotiate, not the access that was withdrawn |
| `GET /owner/ledger` | The activity ledger |
| `GET /owner/events` | Server-sent event stream for portal notification |

### The organization above her, if she has joined one

Only present where an organization owns resources shared with this owner —
see [shared ownership](/docs/overview/shared-ownership/).

| Endpoint | Answers |
|---|---|
| `GET /owner/organization` | Whether she administers resources for anyone, what it shares with her, what its ceiling does to each of her tiers, and any invitation waiting on her |
| `POST /owner/organization/preview` | What a code would commit her to, and exactly what it would change about terms she has already written. Nothing happens |
| `POST /owner/organization` | Join. Refused without an explicit `agreed`, because joining hands another party standing authority over her agents |
| `POST /owner/organization/decline` | Refuse an invitation, recorded as an answer rather than a silence |
| `DELETE /owner/organization` | Leave. Takes back the access; leaves every narrowing in place |
| `POST /org/notice` | A signed notice from her organization — the charter moved, her role changed, the glass was broken. Verified against the keys that organization publishes, never a shared secret |
| `GET`/`POST /org/admin/{owner}/…` | An administrator acting on the agents that touch **the organization's** resources: `pending`, `connections`, `operators`, `ledger`. Scoped by the charter's claims before anything is answered, and everything written into her record under his name |

### Health

| Endpoint | Purpose |
|---|---|
| `GET /health` | Local liveness. Deliberately independent of the registry pull |
| `GET /health/registry` | Has the pull landed. For waits and dashboards — never a readiness probe |

The asymmetry is the point: the pull dereferences this server's own public
hostname, which routes back to it. Gating readiness on the pull deadlocks.

## The resource server's enforcement point

| Endpoint | Auth | Answers |
|---|---|---|
| `GET /.well-known/oauth-protected-resource[/mcp]` | none | RFC 9728 metadata, OAuth+DPoP binding |
| `GET /.well-known/aauth-resource.json` | none | The same structural facts, AAuth binding |
| `GET /jwks` | none | The resource's signing keys |
| `GET /owner-resources` | RFC 9421-signed query by the owner's authority | Owner-bound resource instances |
| `/check{path}` | the gateway | The external authorization decision |

The public documents are structural only. Which instances sit behind the
resource — whose positions, whose vault — is served only to a querier that
proves possession of the owner's authority's signing key. Publishing that at an
unauthenticated URI would be a privacy leak.

### RFC 9728 members

Standard: `resource`, `authorization_servers`, `scopes_supported`, `jwks_uri`,
`signed_metadata`.

Extension members: `tool_surfaces` (tool names and scopes, structural only) and
`owner_resources_endpoint` (the protected instance layer, advertised by both
public documents).

`signed_metadata` carries the same claims as a JWT under the resource's key, so
a relayed copy stays attributable.

### AAuth binding document

`access_mode` (`four-party` for this topology) and `r3_vocabularies`, an
operation list content-addressed by a digest. Both public documents point at the
same `owner_resources_endpoint`; only the encoding differs.

## The organization's authority

A party of its own, not a table inside anyone's authorization server.

| Endpoint | Answers |
|---|---|
| `GET /.well-known/u4a-organization` | Discovery: issuer, JWKS, where to enrol, where decisions come from |
| `GET /jwks` | Its signing keys. Members verify notices against these; enforcement points verify the grants it signs itself |
| `POST /member/preview` | The charter in sentences, before anybody has joined |
| `POST /member/join` | Enrol, by shared code or by an invitation addressed to one person. Returns a membership token her authority holds |
| `GET /member/envelope` | The ceiling, and what her role shares with her. Polled, not pushed — a push that failed would be silent on both sides |
| `POST /decision` | The organization's answer about one request: `allow`, `ask` or `refuse`, and never anything that widens |
| `POST /member/compliance` | Her authority reporting that the ceiling was applied and which of its fields bit. Never what her terms say |
| `GET /member/invitation` | Whether this organization has asked for a named person |
| `GET /membership/{owner}` | For an enforcement point: whether this owner is governed here, what is shared with her, and the ceiling to check grants against |
| `POST /break-glass` | An agent redeeming a window, signing with the key the grant will bind to |
| `POST /introspect`, `/consume` | RFC 7662 over the grants this service signed, shaped exactly like a member authority's answers |
| `/admin/…` | The console's backend: charter versions, members and their groups, invitations, break-glass windows, activity |

Groups are charter data, so the four endpoints that manage them publish a
charter version rather than editing the one in force:

| Endpoint | Answers |
|---|---|
| `GET /admin/roles` | The groups this charter defines, which one joiners land in, and who is in each. Membership is state this service holds, not something the engine is asked |
| `PUT /admin/roles/{id}` | Create a group or change what it reaches. Refused if it grants anything the charter does not claim |
| `DELETE /admin/roles/{id}` | Remove a group. Refused while anybody is in it — deleting one fails closed for its members, which is an access change nobody would see happen |
| `POST /admin/roles/default` | Which group somebody lands in when they join. `null` is valid: joining grants nothing until an administrator says what this person is |
| `POST /admin/members/{owner}/role` | Move one member. The only endpoint in this console that widens anything |

## The requesting party's operator

| Endpoint | Answers |
|---|---|
| CIMD document | The firm's public client identity metadata |
| Web Bot Auth key directory | Keys for the `Signature-Agent` header |

Neither becomes an authorization input. The verifying key is always the RPT's
`cnf`, and the connection handle is unchanged by either.

## Registration flow

The resource server publishes; it never registers.

1. The authority fetches the public RFC 9728 document.
2. It verifies `signed_metadata` against the resource's `jwks_uri`.
3. It queries the advertised `owner_resources_endpoint` with an RFC 9421-signed
   request.
4. It materializes its registry from the response.

One fetch replaces N registration calls, and there is one registry with one
writer. Staleness is the price, and repairing it is the authority's job: an
unknown `resource_id` at `/perm` triggers a re-pull.
