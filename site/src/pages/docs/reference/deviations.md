---
templateKey: doc
title: Deviations from UMA 2.0
description: The extension register — every place this profile departs from stock UMA, what the baseline says, and why each departure exists.
next:
  - title: Findings
    to: /docs/reference/findings/
    blurb: What these deviations produced as recommendations.
  - title: UMA 2.0
    to: /docs/overview/compare-uma/
    blurb: The conceptual comparison, if you want the shorter version.
---

The design rule was to stay inside UMA 2.0's wire surface wherever it already
fits — `WWW-Authenticate: UMA`, the `uma-ticket` grant, `need_info`,
`request_submitted`, introspection `permissions` — and mark every departure as an
explicit extension.

Everything not listed here is intended to be stock UMA 2.0 or stock AAuth.

## 1. Terms proffered inside `required_claims`

**Baseline.** The authorization server names acceptable claim *formats*.

**Here.** A `terms_template` inside the required claim, so the authority proffers
the claim's *content*, dereferenceable at a persistent `terms_uri`, with a
counter-signed receipt returned on grant.

**Why.** Owner-proffered terms, following the IEEE 7012 pattern extended from
privacy to agentic access. It descends directly from UMA's own 2010 Requesting
Party Policy claim. Both sides end up holding identical dually-signed records.

## 2. Proof-of-possession RPT

**Baseline.** A bearer RPT; permissions visible only through introspection.

**Here.** The RPT is an `aa-auth+jwt`, `cnf`-bound, `token_type: PoP`, carrying
the `permissions` array as a claim.

**Why.** A bearer token for an agent is a credential that works for whoever
picks it up. Carrying `permissions` inline lets an enforcement point see scope
without a round trip; introspection remains the authority on liveness.

## 3. `operation` and `single_use` claims

**Baseline.** Per-permission scopes and expiry only.

**Here.** An operation hash and a single-use flag on ask-me grants.

**Why.** Approving one action must not become authorizing a class of actions.
Classic UMA scopes authorize classes.

## 4. Owner push notification on `request_submitted`

**Baseline.** Resource-owner intervention is out of scope.

**Here.** Two kinds of pending item — connection and operation — pushed to the
owner's surface.

**Why.** The agent era's consent surface, and the day-one handshake. The 2010
out-of-band consent wireframes finally have an interlocutor that exists.

## 5. Standing connection keyed by an identity handle

**Baseline.** Nothing directly; the persisted claims token is the closest
ancestor.

**Here.** A connection keyed by JWK thumbprint when pseudonymous, by verified
issuer-qualified subject when identified, plus a `contract` hash on the RPT.

**Why.** Owner-visible, owner-revocable relationships, with promise, action and
consent in one ledger. The identity-level split is not cosmetic: identified
agents rotate session keys, so a thumbprint-keyed connection forgets an enrolled
agent every session. That bit the build.

## 6. Public structural discovery in two binding encodings

**Baseline.** RFC 9728 and AAuth resource metadata both predate this. UMA's
challenge carries `as_uri` on faith.

**Here.** One registry serving both encodings, `resource_metadata` on the
challenge, and clients corroborating `as_uri` against published
`authorization_servers`.

**Why.** The encodings are stock. Composing them with the UMA challenge — so it
gains a TLS-anchored second witness — and sharing one protected instance layer
beneath both is the extension.

## 7. `owner_resources_endpoint` and the protected listing

**Baseline.** FedAuthz: the resource server pushes owner-bound registrations
under the PAT.

**Here.** Public metadata stays structural; whose instances sit behind the
resource is served only to the owner's authority, over an RFC 9421-signed query.

**Why.** The privacy split. Publishing which resources a named person owns at an
unauthenticated URI is a leak the old push registration never had. It also
enables declarative registration. Classic push remains conformant and is
preserved on the `legacy/rreg-baseline` branch.

## 8. Challenge specified as parameters

**Baseline.** UMA 2.0 mandates the `WWW-Authenticate` header.

**Here.** Parameters — `as_uri`, `ticket`, `resource_metadata`, `realm` — with
per-host encodings: a 401 with the header where there is a status line, a
JSON-RPC error where there is not.

**Why.** An enforcement point running in-process has no status line. Mandating
the header excludes exactly the resource-side frameworks most likely to adopt
this. Both encodings run here against one authorization server, and one client
reads both.

## 9. Enforcement obligations hosted by either party's component

**Baseline.** FedAuthz names the obligations, not their host.

**Here.** `ENFORCEMENT_MODE=gateway|embedded`, from one core.

**Why.** The enforcement point is a role, not a product. Two conformant hosts on
one stack means the claim is measured rather than argued.

## 10. Consumption ordering made normative

**Baseline.** UMA 2.0 §3.3.1 does not say where in enforcement a single-use
token is spent.

**Here.** Introspect (non-consuming) → permissions → proof-of-possession →
operation binding → consume, atomic and last. Inactive introspection carries a
reason, and `connection_revoked` is terminal.

**Why.** The intuitive order — consume first — lets an unsigned replay destroy an
approval the owner just gave. And a bare `{"active": false}` sends a revoked
agent round a negotiation whose outcome is already settled.

## 11. Requesting-agent identity metadata

**Baseline.** The agent is its key, or its issuer's token.

**Here.** An optional CIMD `client_id` in the agreement header — resolved,
self-reference enforced, **display only** — and a Web Bot Auth `Signature-Agent`
covered by the request signature.

**Why.** The cold-start problem: a party who has never met this agent needs to be
able to say something true about it. Neither ever becomes an authorization
input. The verifying key is always the RPT's `cnf`, and the connection handle is
unchanged.

## 12. Structured remediation in the challenge

**Baseline.** UMA's challenge carries `as_uri` and `ticket` only.

**Here.** `error="insufficient_authorization"` plus `authorization_remediation`
carrying RFC 9396 `authorization_details` and an `authorization_reference`, with
`authorization_server` and `ticket` inside it.

**Why.** A superset of `draft-zehavi-oauth-rar-metadata` rather than a rival: the
same remediation payload, plus the two parameters that let a party who is not the
caller decide. The same JSON rides the JSON-RPC encoding byte for byte, which
demonstrates that the payload is portable and only the envelope is
binding-specific.

## 13. A cap on the owner's pending queue

**Baseline.** UMA 2.0 defines `request_submitted` and has no opinion about how
many of them a resource owner can be made to hold at once.

**Here.** Requests from agents with no standing queue against a depth limit,
in two lanes split on whether the operator an agent names has published that
agent's key. Past the cap the answer is `429` with
`error="request_denied"` and a reason, rather than another pend.

**Why.** Keys are free, so an unbounded pending queue turns *the owner decides*
into its own denial-of-service surface, and every request in the flood is
individually well-formed. A rate limit does not express the constraint — the
scarce thing is queue depth, not arrival rate. The lanes exist because the agent
you want to admit is a stranger too on first contact, so a single queue defends
continuity and leaves onboarding undefended. See
[the owner's attention](/docs/overview/attention/).

## 14. Owner-side blocking at operator granularity

**Baseline.** UMA 2.0 has no notion of the party operating a requesting agent,
and so nothing to revoke at that level.

**Here.** `POST /owner/operators/block` ends every connection an operator holds
and burns the grants under them in one step, and refuses its future requests by
name.

**Why.** One connection at a time is not an answer to a flood, and the queue
lanes exist precisely to make a flood large enough to matter arrive
attributable. Blocking is a restriction, so it may rest on the agent's own
claim: an agent that misstates its operator only refuses itself. It does not
stop the same party returning anonymously, which is why the lanes matter more
than the block.

## 15. A layer above the resource owner

**Baseline.** UMA 2.0 has one deciding party per resource. The
*resource rights administrator* is named in the terminology and given no wire
surface: nothing in the protocol expresses an owner-of-record whose
administration is delegated, and nothing expresses a policy above the person
who is deciding.

**Here.** An organization is a party of its own, with:

- a **charter** it publishes an envelope from, which a member's authorization
  server clamps her tiers to on write — so the ceiling appears in the terms
  document the requesting side dereferences and signs, rather than being
  applied invisibly at the door;
- a **decision endpoint** the member's authority calls once per request over a
  resource the charter claims, returning `allow` / `ask` / `refuse` and
  nothing that can widen;
- **roles**, each carrying a `delegation` value — `none`,
  `first-party-only`, `any-agent` — which says *whose agent* may act on the
  shared resource rather than what may be accessed;
- a **path per administrator** (`/mcp/shared/<member>`) so one resource can be
  administered by several people, each under her own authorization server;
- **grants the organization signs itself** for a disclosed break-glass clause,
  recognised at the enforcement point by issuer and checked with the
  organization rather than with the member's authority.

**Why.** The moment a resource is *shared*, "may her agent touch it" is a
question about parties, and there is nowhere in UMA 2.0 to put the answer. See
[shared ownership](/docs/overview/shared-ownership/) and recommendation 25.

**What is deliberately not extended.** The four beats are untouched. The
challenge, the ticket, `need_info`, the agreement and the RPT are the same on
a shared resource as on a personal one — a requesting agent cannot tell the
difference, and does not need to.

## Security properties these depend on

Each is enforced somewhere in the code, and the tests that prove refusals rather
than permissions are the policy suite and the store tests.

- **Single-use must be indivisible.** Check-then-act is correct in one process
  and wrong in two. The store exposes consume as an *intent* that decides and
  records in one step and reports who won.
- **Consumption is ordered and last.**
- **Authorization inputs never come from the transport.** The signature base is
  rebuilt from configured values, never from `Host` or a forwarded header.
- **A truncated body must fail closed**, with a named reason rather than a
  misleading unknown-method error.
- **The resource server must not be able to read the owner's policy.** Structural
  rather than advisory: PAT-scoped protection API, and in the Kubernetes
  reference the mesh denies the path outright.
- **Agent-token issuers are trusted by dereference**, with TLS on the issuer
  origin as the trust root and non-`https` issuers rejected. There is
  deliberately no issuer allow-list here — which issuers may attest agents is
  deployment policy, and a real deployment must supply one.
- **Liveness must not depend on a mutual dereference.**
- **Revocation is atomic and immediate.**
- **A layer above the owner may only narrow**, and its reach — including what
  it can *see* — stops at the resources its charter claims. The scoping is the
  owner authority's, applied before it answers, rather than the upper layer's
  to respect.
- **An administrator's decision is never recorded as the owner's.** The fact
  "she personally approved something at this tier" is allowed to relax one of
  her rules, so a decision taken on her behalf must not produce it.

**Not addressed.** Signing-key rotation — the key is minted once and shared by
all replicas, and while `jwks_uri` makes rotation possible, nothing here
exercises it. Multiple authorization servers behind one resource server — RFC
9728 makes `authorization_servers` an array; this profile configures one. And
revocation propagation beyond a single shared store.
