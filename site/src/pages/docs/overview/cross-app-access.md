---
templateKey: doc
title: Cross App Access
seoTitle: "Cross App Access and UMA: two halves of one authorization question"
description: An enterprise identity provider says which employee and which application. The owner's authority says what may be done, on whose terms. Neither can answer the other's question.
next:
  - title: Shared ownership
    to: /docs/overview/shared-ownership/
    blurb: The organization layer this rides on — a firm above the owner.
  - title: Agent identity
    to: /docs/overview/compare-agent-identity/
    blurb: Where this profile sits among the identity-provider-centric designs.
---

Cross App Access and this profile get read as competitors. They are not. They
answer different questions about the same request, and a request over an
organization's resources needs both answers.

    Cross App Access (ID-JAG)   which employee is this agent acting for,
                                and did an administrator approve this
                                application reaching that resource at all

    this profile                and therefore what may it do to the
                                resource, on whose terms, for how long,
                                and at what depth of delegation

Northwind cannot know what Alice's terms say. Alice's authority cannot know
whether Northwind's administrator approved this application at all. Each party
answers the question it is actually in a position to answer.

## What an ID-JAG is

An **Identity Assertion JWT Authorization Grant** —
[`draft-ietf-oauth-identity-assertion-authz-grant`](https://datatracker.ietf.org/doc/draft-ietf-oauth-identity-assertion-authz-grant/),
also called XAA. A client exchanges the employee's ID token at the identity
provider for a short-lived assertion audienced at **one** authorization server
and naming **one** resource. It is not an access token and it carries no
entitlement.

That last property is what makes it compose. An assertion that carried
entitlement would have to be honoured or overridden; one that carries only
identity and approved reach can be *asked for* by whoever needs to know, and
answered without settling anything else.

## The wire

The assertion arrives as a claim against an open permission ticket — the slot
UMA has always had for "prove something about yourself before I dictate
terms". The negotiation gains one beat, and each beat asks exactly one party's
question.

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

Identity comes first because the answer decides what follows: which tier
applies, and what her terms may say, both depend on which member the agent
acts for.

## It is the resource side that starts it

Cross App Access is usually drawn outwards from the identity provider, which
makes it sound like something an enterprise pushes at an application. Nothing
here is pushed.

The agent begins knowing nothing about Northwind. It calls a tool, is refused,
and is **told** which provider to go to, what to name as the audience and the
resource, and which scope to ask for — all of it inside the `required_claims`
object. Only then does it go and get one.

This is the same shape as every other beat in this profile: the resource side
states what it needs, and the requesting side decides whether to satisfy it.
An agent carrying no enterprise credentials is refused at that point in plain
terms rather than left guessing.

## Three ceilings, one per party

    the provider's connection scope     what an administrator approved
  ∩ the charter's grants                what the organization allows the role
  ∩ her terms                           what she is willing to offer
  = what the grant actually carries

None of the three can widen another, and each is set by a party with standing
to set it. A scope no administrator approved is refused at the identity
provider. An agent somebody else operates is refused by the charter's
`first-party-only` role **despite** a perfectly good assertion — whose agent
it is remains the member's own declaration, not something an employer
asserts. And her terms narrow whatever is left.

## Where the enterprise half stops

The identity provider is consulted only where the organization actually
reaches the resource. That test already subtracts anything the member holds
jointly with somebody else, and it never matched her own accounts to begin
with.

So her personal vault is never governed by this. No assertion is asked for
over it, and none would help — there is no beat in that negotiation where one
would be accepted. The boundary is the same one the
[organization layer](/docs/overview/shared-ownership/) already draws; Cross
App Access does not move it.

## Enrolling because the directory says so

Where a charter names a provider, an employee enrols as a member on the
strength of her employer's own directory rather than a shared code. The
charter is what makes that legitimate: she reads that the organization
federates identity to a named provider before she agrees to anything, so an
organization cannot start accepting somebody else's word about who its people
are without republishing the bargain.

Omit `identity_provider` from the charter and none of this exists — members
enrol with a code exactly as before, and no assertion is asked for or
accepted.

## Running it

`make xaa-check` walks the whole arrangement: the federated charter, enrolment
by assertion, the two-beat negotiation, all three ceilings biting separately,
and the boundaries — one authority, one person, one use, and nothing outside
the organization's own resources.

The exchange endpoint in the lab is a small service beside Keycloak, because
Keycloak can *receive* an ID-JAG but cannot yet issue one. An Okta tenant with
Cross App Access enabled does both halves in one place; the split is a
property of the lab rather than of the design. See
[deviation 17](/docs/reference/deviations/) for why the assertion is carried
as a claim rather than as a `jwt-bearer` grant.
