# Cross App Access beside UMA

An enterprise identity provider and an owner's authorization server answer
different questions about the same request. This is the lab wiring both into
one negotiation, to show that they compose rather than compete.

    Cross App Access (ID-JAG)   which employee is this agent acting for,
                                and did an administrator approve this
                                application reaching that resource at all

    this profile (UMA)          and therefore what may it do to the
                                resource, on whose terms, for how long,
                                and at what depth of delegation

Neither can answer the other's. Northwind cannot know what Alice's terms say.
Alice's authority cannot know whether Northwind's administrator approved this
application. A request over the firm's book needs both answers, and gets them
from the two parties entitled to give them.

![Cross App Access beside UMA in seven beats. An agent calls Northwind's book at Meridian's gateway and is refused with a UMA challenge naming the member's own authorization server. That authority answers need_info, but not with terms: it asks first who the agent acts for, and names the identity provider it will accept, the audience, the resource and the scope. The agent — which knew nothing about Northwind when it started — takes that to Okta and performs an ordinary RFC 8693 token exchange. Okta returns an ID-JAG naming the employee, the application and the approved scope, and carrying no entitlement over any resource. Only then does her authority dictate her terms, capped by Northwind's charter rather than by Okta. The agent signs, receives an ordinary RPT and spends it. The last beat lays out three ceilings side by side — the connection an administrator approved, the charter's grants, and her own terms — each set by a different party, none able to widen another.](cross-app-access.gif)

Run it with `make xaa-check`.

## What ID-JAG is

An **Identity Assertion JWT Authorization Grant** —
[`draft-ietf-oauth-identity-assertion-authz-grant`](https://datatracker.ietf.org/doc/draft-ietf-oauth-identity-assertion-authz-grant/),
also called Cross App Access or XAA. A client exchanges a subject token (here,
an OpenID Connect ID token) at the identity provider for a short-lived
assertion audienced at one authorization server and naming one resource:

```
POST /token                                    at the identity provider
grant_type=urn:ietf:params:oauth:grant-type:token-exchange
requested_token_type=urn:ietf:params:oauth:token-type:id-jag
subject_token=<the employee's ID token>
subject_token_type=urn:ietf:params:oauth:token-type:id_token
audience=https://alice-as.uma.lab                  the authorization server
resource=https://gateway.uma.lab/mcp               the resource server
scope=get_positions
```

What comes back is a JWT with `typ: oauth-id-jag+jwt`, carrying `iss`, `sub`,
`aud`, `client_id`, `resource`, `scope` and `jti`. It is **not an access
token** and it carries no entitlement — which is exactly what lets it be a
*claim* here rather than a competing grant.

## Where the two meet

The spec's own step 4 has the client present the assertion at the resource
authorization server as `grant_type=jwt-bearer` with `assertion=…`, and get an
access token back. This profile does not do that, deliberately. See deviation
17 for the reasoning; the short version is that a `jwt-bearer` exchange would
have the identity provider's assertion produce the access token directly,
which would make the provider the deciding party over somebody else's
resource.

Instead the assertion arrives as a **claim against an open permission
ticket** — the slot UMA has always had for "prove something about yourself
before I dictate terms". The negotiation gains one beat, and each beat asks
exactly one party's question:

```
agent → resource server            tools/call
     ← 401 WWW-Authenticate: UMA   as_uri, ticket

agent → authorization server       ticket
     ← 403 need_info               required_claims: [id-jag]
                                   + which provider, what audience,
                                     what resource, which scope

agent → identity provider          token exchange
     ← ID-JAG

agent → authorization server       ticket + claim_token=<ID-JAG>
     ← 403 need_info               required_claims: [agreement]
                                   + terms_template

agent → authorization server       ticket + claim_token=<signed agreement>
     ← 200                         RPT
```

Identity is asked for **first**, because the answer decides what comes next:
which tier applies and what her terms may say both follow from which member
the agent acts for.

## Why it is the resource side that starts it

Cross App Access is usually drawn from the identity provider outwards, which
makes it sound like something an enterprise pushes. Nothing here is pushed.

The agent begins knowing nothing about Northwind. It calls a tool, is refused,
and is *told* which provider to go to, what to name as the audience and the
resource, and which scope to ask for — all of it in the `required_claims`
object. Only then does it go. The resource side names the identity provider it
will accept, which is the same shape as every other beat in this profile.

An agent that carries no enterprise credentials gets a clear refusal at that
point rather than a puzzle.

## Three ceilings, one per party

```
    the provider's connection scope     what an administrator approved
  ∩ the charter's grants                what the organization allows the role
  ∩ her terms                           what she is willing to offer
  = what the grant actually carries
```

Each is set by a different party and none of them can widen another. The check
demonstrates all three biting separately: a scope no administrator approved is
refused at the identity provider; an agent somebody else operates is refused
by the charter's `first-party-only` role *despite* a perfectly good assertion;
and her terms narrow what is left.

## What the assertion is bound to

- **one authorization server.** `aud` is the authority the provider minted it
  for. Northwind's book is administered by two members who each run their own
  authority, so the provider mints assertions audienced at each — and one
  presented at the other's is refused.
- **one person.** The name in the assertion has to be the member whose
  authority it is presented at, or an assertion for one employee would open a
  negotiation over another's administration.
- **one use.** Spent by `jti` until it expires.
- **the organization's own resources, and nothing else.** The provider is
  consulted only where `org.reaches` says the organization reaches the
  resource — which already subtracts anything the member holds jointly with
  somebody else. Her own accounts never reach that branch. No assertion is
  asked for over them and none would help.

## Who masters what

Three parties, and each masters exactly one thing:

| party | masters |
|---|---|
| the identity provider | who its **employees** are |
| the member | whether her authority comes **under the charter** |
| the organization | what the **charter** says |

That division answers the awkward case. An employee's agent turns up with a
perfectly good assertion at a resource belonging to an organization she has
not joined: the request is refused, and the assertion does not enrol her.

It cannot be allowed to. Joining is a bargain — the charter narrows her terms,
but it also gives the organization powers over her agents, break-glass among
them. Those are acquired by agreeing to a document, not by being on a payroll.
An employer able to enrol somebody by asserting they work there could put a
stranger's authority under a charter they never read, which is the arrangement
this whole layer exists to make impossible.

So the enforcement point refuses outright, without a challenge — there is
nothing to negotiate about a resource nobody has shared. What the refusal does
carry is the organization's name and how membership is come by:

```json
{
  "error": "not_shared",
  "error_description": "this resource belongs to Northwind Capital and is not shared with that member",
  "organization": { "name": "Northwind Capital", "issuer": "https://northwind-org.uma.lab" },
  "how_to_join": "Northwind Capital federates identity to https://…. Whoever this authority belongs to can enrol from their own portal by signing in there — no enrolment code."
}
```

None of that is privileged; the organization publishes all of it. It is the
difference between a dead end and something the person can act on.

## Federated enrolment

Where a charter names a provider, an employee can enrol as a member because
the organization's own directory vouches for her, rather than by entering a
shared code:

```
POST /owner/organization        at her authorization server
{"assertion": "<her ID token from the organization's realm>", "agreed": true}
```

The charter is what makes this legitimate. A member reads "Northwind federates
identity to this provider" before she agrees to anything, so an organization
cannot start accepting somebody else's word about who its people are without
republishing the bargain. One employee's token does not enrol another.

Omit `identity_provider` from the charter and none of this exists: members
enrol with a code exactly as before, and no assertion is asked for or
accepted. Every other check in the lab runs against an unfederated charter.

## What runs it

| | |
|---|---|
| `services/xaa-broker/` | Northwind's exchange endpoint — what an Okta tenant does when an administrator approves one application's reach into another |
| `keycloak/northwind-realm.json` | the employee directory, and the application they sign into |
| `services/org-authority/charter.py` | `identity_provider` in the charter, and federated enrolment |
| `services/uma-as/app.py` | `verify_id_jag`, the identity beat, and the binding checks |
| `lib/uma4a_grant.py` | `Enterprise`, and the exchange an agent performs when asked |
| `clients/demo-driver/xaa_check.py` | `make xaa-check` |

### Two identity providers, and they are different companies

The lab runs two, and conflating them is the easiest mistake to make here:

| | |
|---|---|
| `keycloak.uma.lab` | **Meridian's.** It authenticates people into Meridian's own surfaces — Alice's portal, and the org console Dana signs into. Its `northwind` realm exists because Meridian hosts a console for its institutional clients |
| `northwind-idp.uma.lab` | **Northwind's.** A customer's own infrastructure: its employee directory, its administrator, and the issuer a charter federates identity to |

They are separate processes because they are separate companies, and modelling
the second as another realm on the first would say the opposite of what it is.
Meridian's word about who Northwind employs is worth nothing, and the lab
asserts that: a token from Meridian's realm presented to Northwind's provider
is refused, and so is one presented as an employee assertion at enrolment.

Northwind's is Keycloak here only because the lab needs a real OpenID provider
to stand in for an Okta tenant. Keycloak cannot issue an ID-JAG — its support
is receiver-side, behind an experimental flag — so the exchange endpoint is a
small service beside it. An Okta tenant with Cross App Access does both halves
in one place, and `services/xaa-broker/` is what disappears when you point the
charter at one.

### Pointing it at a real tenant

A step-by-step version of this, against a free trial, is
[Try it with Okta](https://u4a.ai/docs/guides/okta-cross-app-access/) on the
docs site. The short version:

Only the charter changes: set `identity_provider.issuer` to the tenant, and
leave `directory` blank so it is discovered. Three things were built for that
rather than for the lab's own provider:

- **keys are found by discovery.** `{issuer}/.well-known/openid-configuration`
  (then `oauth-authorization-server`), and `{issuer}/jwks` only as a fallback,
  because that last one is this lab's convention and no real tenant serves it;
- **any asymmetric algorithm.** The lab's provider signs EdDSA and a tenant
  will sign RS256. Permitted algorithms come from the key's type, never from
  the token's own header;
- **the subject claim is not assumed.** `preferred_username`, `email`, its
  local part, and `sub` are all compared against the member; a charter may
  name one claim explicitly with `identity_provider.subject_claim`;
- **the subject token type is negotiated.** A tenant exchanges the *refresh
  token* from the employee's sign-in; the provider shipped here exchanges an
  ID token. The provider advertises what it takes and the challenge carries
  the list, so an agent is not configured with a fact its provider publishes.

### Mapping to an Okta tenant

Okta's objects line up with this profile's without much translation. From
**Directory → AI agents → Register AI agent → Register manually**:

| Okta | here |
|---|---|
| the **AI agent** (requesting app) | the agent, and the `client_id` in the assertion |
| **Client registration → Client secret** | what `Enterprise` carries |
| the **resource app**, *Resource Server* tab → Cross App Access | the member's authorization server |
| its **Issuer URL** | that authority's issuer — what goes in `identity_provider.issuer`'s `aud` |
| **Resource connections → Resource indicator** | the resource server URI |
| **Resource connections → Scopes** | the enterprise ceiling, the first of the three |

Two practical notes for anyone trying it. The agent's subject token is a
refresh token from a real sign-in, so the flow has to have happened once
before an exchange can be made. And Okta's `sub` is a tenant-local
identifier rather than a member's name, so either the employee's email local
part matches the member or the charter names a claim.

Registering an AI agent needs an org with SSO and a super admin. It does not
need Okta for AI Agents, which raises the ID-JAG ceiling above the SSO
allowance rather than unlocking the flow.
