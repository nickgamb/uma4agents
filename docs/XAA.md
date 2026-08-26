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

### On the broker being a separate service

Keycloak is Northwind's identity provider here and holds the employee
directory, but it cannot issue an ID-JAG: its support is receiver-side only,
and behind an experimental feature flag at that. So the exchange endpoint is a
small service beside it, trusting that realm for subject tokens.

An Okta tenant with Cross App Access enabled does both halves in one place.
The split is a property of this lab, not of the design.
