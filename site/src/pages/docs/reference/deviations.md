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

Each entry names where the [specification set](/docs/reference/specification/)
states it normatively. The numbering is the one Core §12 uses; entries 1–22 are that table.

## 1. Terms proffered inside `required_claims`

**Baseline.** The authorization server names acceptable claim *formats*.

**Here.** A `terms_template` inside the required claim, so the authority proffers
the claim's *content*, dereferenceable at a persistent `terms_uri`, with a
counter-signed receipt returned on grant.

**Why.** Owner-proffered terms, following the IEEE 7012 pattern extended from
privacy to agentic access. It descends directly from UMA's own 2010 Requesting
Party Policy claim. Both sides end up holding identical dually-signed records.

**Specified in.** [Owner-Proffered Terms §3–5](/spec/draft-gamb-uma4agents-terms-00.html#proffering)

## 2. Proof-of-possession RPT

**Baseline.** A bearer RPT; permissions visible only through introspection.

**Here.** The RPT is an `aa-auth+jwt`, `cnf`-bound, `token_type: PoP`, carrying
the `permissions` array as a claim.

**Why.** A bearer token for an agent is a credential that works for whoever
picks it up. Carrying `permissions` inline lets an enforcement point see scope
without a round trip; introspection remains the authority on liveness.

**Specified in.** [Core §7.1](/spec/draft-gamb-uma4agents-core-00.html#rpt)

## 3. `operation` and `single_use` claims

**Baseline.** Per-permission scopes and expiry only.

**Here.** An operation hash and a single-use flag on ask-me grants.

**Why.** Approving one action must not become authorizing a class of actions.
Classic UMA scopes authorize classes.

**Specified in.** [Core §7.2](/spec/draft-gamb-uma4agents-core-00.html#operation-binding)

## 4. Owner push notification on `request_submitted`

**Baseline.** Resource-owner intervention is out of scope.

**Here.** Two kinds of pending item — connection and operation — pushed to the
owner's surface.

**Why.** The agent era's consent surface, and the day-one handshake. The 2010
out-of-band consent wireframes finally have an interlocutor that exists.

**Specified in.** [Core §4.2 and §9](/spec/draft-gamb-uma4agents-core-00.html#connections)

## 5. Standing connection keyed by an identity handle

**Baseline.** Nothing directly; the persisted claims token is the closest
ancestor.

**Here.** A connection keyed by JWK thumbprint when pseudonymous, by verified
issuer-qualified subject when identified, plus a `contract` hash on the RPT.

**Why.** Owner-visible, owner-revocable relationships, with promise, action and
consent in one ledger. The identity-level split is not cosmetic: identified
agents rotate session keys, so a thumbprint-keyed connection forgets an enrolled
agent every session. That bit the build.

**Specified in.** [Core §9](/spec/draft-gamb-uma4agents-core-00.html#connections)

## 6. Public structural discovery in two binding encodings

**Baseline.** RFC 9728 and AAuth resource metadata both predate this. UMA's
challenge carries `as_uri` on faith.

**Here.** One registry serving both encodings, `resource_metadata` on the
challenge, and clients corroborating `as_uri` against published
`authorization_servers`.

**Why.** The encodings are stock. Composing them with the UMA challenge — so it
gains a TLS-anchored second witness — and sharing one protected instance layer
beneath both is the extension.

**Specified in.** [Core §3.4, and Federated Authorization for Agents §2.1](/spec/draft-gamb-uma4agents-core-00.html#corroboration)

## 7. `owner_resources_endpoint` and the protected listing

**Baseline.** FedAuthz: the resource server pushes owner-bound registrations
under the PAT.

**Here.** Public metadata stays structural; whose instances sit behind the
resource is served only to the owner's authority, over an RFC 9421-signed query.

**Why.** The privacy split. Publishing which resources a named person owns at an
unauthenticated URI is a leak the old push registration never had. It also
enables declarative registration. Classic push remains conformant and is
preserved on the `legacy/rreg-baseline` branch.

**Specified in.** [Federated Authorization for Agents §2.2 and §3](/spec/draft-gamb-uma4agents-fedauthz-00.html#protected-layer)

## 8. Challenge specified as parameters

**Baseline.** UMA 2.0 mandates the `WWW-Authenticate` header.

**Here.** Parameters — `as_uri`, `ticket`, `resource_metadata`, `realm` — with
per-host encodings: a 401 with the header where there is a status line, a
JSON-RPC error where there is not.

**Why.** An enforcement point running in-process has no status line. Mandating
the header excludes exactly the resource-side frameworks most likely to adopt
this. Both encodings run here against one authorization server, and one client
reads both.

**Specified in.** [Core §3.1, and the MCP binding §3](/spec/draft-gamb-uma4agents-core-00.html#challenge-parameters)

## 9. Enforcement obligations hosted by either party's component

**Baseline.** FedAuthz names the obligations, not their host.

**Here.** `ENFORCEMENT_MODE=gateway|embedded`, from one core.

**Why.** The enforcement point is a role, not a product. Two conformant hosts on
one stack means the claim is measured rather than argued.

**Specified in.** [Core §8.1](/spec/draft-gamb-uma4agents-core-00.html#obligations)

## 10. Consumption ordering made normative

**Baseline.** UMA 2.0 §5.5 makes permission tickets single-use but does not say where in enforcement a single-use
token is spent.

**Here.** Introspect (non-consuming) → permissions → proof-of-possession →
operation binding → consume, atomic and last. Inactive introspection carries a
reason, and `connection_revoked` is terminal.

**Why.** The intuitive order — consume first — lets an unsigned replay destroy an
approval the owner just gave. And a bare `{"active": false}` sends a revoked
agent round a negotiation whose outcome is already settled.

**Specified in.** [Core §8.2–8.4, and Federated Authorization for Agents §6](/spec/draft-gamb-uma4agents-core-00.html#ordering)

## 11. Requesting-agent identity metadata

**Baseline.** The agent is its key, or its issuer's token.

**Here.** An optional CIMD `client_id` in the agreement header — resolved,
self-reference enforced, **display only** — and a Web Bot Auth `Signature-Agent`
covered by the request signature.

**Why.** The cold-start problem: a party who has never met this agent needs to be
able to say something true about it. Neither ever becomes an authorization
input. The verifying key is always the RPT's `cnf`, and the connection handle is
unchanged.

**Specified in.** [Core §5.2](/spec/draft-gamb-uma4agents-core-00.html#descriptive-metadata)

## 12. Structured remediation in the challenge

**Baseline.** UMA's challenge carries `as_uri` and `ticket` only.

**Here.** `error="insufficient_authorization"` plus `authorization_remediation`
carrying RFC 9396 `authorization_details` and an `authorization_reference`, with
`authorization_server` and `ticket` inside it.

**Why.** A superset of `draft-ietf-oauth-rar-metadata-remediation` rather than a rival: the
same remediation payload, plus the two parameters that let a party who is not the
caller decide. The same JSON rides the JSON-RPC encoding byte for byte, which
demonstrates that the payload is portable and only the envelope is
binding-specific.

**Specified in.** [Core §3.3](/spec/draft-gamb-uma4agents-core-00.html#remediation)

## 13. A resource server introduces itself by its origin

**Baseline.** FedAuthz §1.4 requires the protection API token to be issued
with the resource owner's authorization, and says nothing about how the
resource server comes to be a client of the authorization server at all.

**Here.** `POST /rs/register`: the resource server signs the request (RFC
9421) with a key published at the origin of the resource it claims to serve.
The authority fetches that resource's own RFC 9728 document, checks that it
claims *this* resource, that its `jwks_uri` is same-origin, and that it names
*this* authorization server, and verifies the signature against the keys it
publishes. Success is `202 pending`: the owner approves it from her registry
before any PAT is issued, and `/token` then accepts the same signature in
place of a client secret.

**Why.** Where one operator runs both sides, a provisioned secret models the
gap adequately. It does not when the authority is the owner's, because nobody
is in a position to configure both ends. Trusting control of the origin adds
no party the protocol did not already depend on — it is the address the
challenge pointed at. Unreachable is refused: here the document *is* the
credential, and a credential that cannot be fetched has not been presented.

**Specified in.** [Federated Authorization for Agents §4](/spec/draft-gamb-uma4agents-fedauthz-00.html#establishment)

## 14. Every owner-scoped artifact carries its owner

**Baseline.** One authorization server per protected resource, with the owner
implicit in the deployment.

**Here.** The ticket resolves only at the authority that minted it; the RPT
carries an `owner` claim; resource ids and terms `template_id`s are namespaced
by owner; and the RFC 9728 document is per-owner, at `/mcp/<owner>`, naming
*her* `authorization_servers`.

**Why.** Two owners of one resource server can name two different authorities,
which is the difference between multi-tenancy and an authority that is hers.
The specification states it as one testable sentence: *the authorization
server named in the challenge is the owner's choice, and two owners of one
resource server may name two different ones.* The store enforces it
structurally rather than by parameter.

**Specified in.** [Core §11](/spec/draft-gamb-uma4agents-core-00.html#owner-scoped)

## 15. A cap on the owner's pending queue

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

**Specified in.** [Owner Policy, Assurance and Attention §6](/spec/draft-gamb-uma4agents-policy-00.html#attention)

## 16. Owner-side blocking at operator granularity

**Baseline.** UMA 2.0 has no notion of the party operating a client,
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

**Specified in.** [Owner Policy, Assurance and Attention §7](/spec/draft-gamb-uma4agents-policy-00.html#operators)

## 17. Assurance may only tighten; only her decisions may relax

**Baseline.** UMA 2.0 has no vocabulary for what the authorization server may
know about a requesting party before the owner has met it, nor for what may
lower a requirement.

**Here.** Every condition a rule may name is classed as *relaxing* or
*observed*. A rule whose effect is `auto` may name only relaxing conditions —
the owner personally approved this agent here, she has never revoked it, she
has known it longer than a stated time, or it is one she activated herself.
Assurance is three independent axes, derived from checks that ran, with no
composite score. The rule is enforced when a policy is *saved*, so the mistake
cannot be stored.

**Why.** The party being decided about supplies most of the evidence. A rule
that widens on that evidence is a rule the agent can satisfy by producing it.
And "we have granted here before" may record an automatic grant, so relaxing on
it would let one automatic grant justify the next.

**Specified in.** [Owner Policy, Assurance and Attention §3–5](/spec/draft-gamb-uma4agents-policy-00.html#asymmetry)

## 18. An agent may introduce a sibling

**Baseline.** UMA 2.0 has no object between "a stranger" and "the same
client", and no notion of one requesting party standing for another.

**Here.** An agent holding a connection signs a short introduction naming the
newcomer's key (`u4a-introduction-v1+jws`), or its issuer names the lineage in
an RFC 8693 `act` claim. The newcomer skips first contact and then negotiates
its own terms under its own key for its own grant. Her authority verifies the
introducer against her own active connections, requires a tier she approved in
person, refuses an agent that was itself introduced, and requires one operator
to have published both keys. Approval pools across the lineage in both
directions; revoking the introducer revokes the introduced.

**Why.** The usual answer is to pass the parent's token down, which makes the
workers indistinguishable from the parent in the owner's records, individually
unrevocable, and never something she agreed to. Keeping the authority graph
one level deep while the task graph nests means every agent is separately
visible, separately revocable and separately bounded.

**Specified in.** [Agent Lineage](/spec/draft-gamb-uma4agents-lineage-00.html#admission)

## 19. A layer above the resource owner

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
a shared resource as on a personal one — a client cannot tell the
difference, and does not need to.

**Specified in.** [Multi-Party Authorization, Part I](/spec/draft-gamb-uma4agents-multiparty-00.html#organization)

## 20. Several owners of equal standing over one resource

**Baseline.** UMA 2.0 has exactly one authorization server per protected
resource. There is no object for "these parties must both agree", and no way
for a relying party to check that they did.

**Here.** Three objects, and a party that is not trusted:

- a **mandate**, published beside the resource and agreed to by the holders,
  naming who is entitled to be counted, at what weight, and how many it takes;
- a **verdict** — one owner's authorization server signing its answer to one
  negotiation, bound to that negotiation and to the exact agreement digest, so
  it cannot carry a later request;
- a **tally**, which folds every holder's terms into the single document the
  agent signs, collects the verdicts, and issues a grant **carrying them**.
  The enforcement point verifies each verdict against the keys that holder's
  authority publishes and re-runs the count from the mandate.

**Why.** With no party above the owners, the decision cannot be put anywhere
without privileging the place it is put. Carrying the signed verdicts in the
grant makes the counting party *unable to lie* rather than trusted, which is
what lets it be an ordinary service instead of a ledger — there is no ordered
history here to agree on and no long-lived state a fork could damage. See
[joint ownership](/docs/overview/joint-ownership/) and recommendation 26.

**What is deliberately not extended.** The four beats again, and the
requesting side with them: a tally speaks an ordinary authorization-server
surface, so an unmodified agent negotiates with it exactly as with an
authorization server. Claims-gathering is also deliberately *not* used to
collect verdicts — a claim the requesting party gathers is a claim it can
decline to gather, and a refusal has to reach the decision point without the
cooperation of the party it refuses.

**Specified in.** [Multi-Party Authorization, Part II](/spec/draft-gamb-uma4agents-multiparty-00.html#joint)

## 21. The owner's own credential

**Baseline.** UMA 2.0 says nothing about how the resource owner authenticates
to her own authorization server; in its deployments the server belonged to a
service that already had a session with her.

**Here.** `UMA_AS_OWNER_AUTH` names one or both of an OIDC access token from
her designated provider and an RFC 9421 signature from a device key she
enrolled, with a required body digest on any request carrying one. Each is
independently sufficient and independently revocable; neither is a fallback
for the other; no static owner credential exists.

**Why.** The second form is what lets her authority be reached by something
she runs — a personal agent on her own device — without a browser session and
without an identity provider in the path. It is the client's
message-signature profile, pointed the other way.

**Specified in.** [Core §10](/spec/draft-gamb-uma4agents-core-00.html#owner-authentication)

## 22. The owner's API

**Baseline.** UMA 2.0 has no surface for the resource owner. Her decisions
arrive through whatever the deployment built.

**Here.** `owner_endpoint` in the authorization server's metadata, and under it
the queue and its decisions, her connections and the operators behind them,
her resource servers, her policy units and terms, the vocabulary her rules may
use, the record, an event stream, and the owner's side of the organization and
joint arrangements. Every operation takes the credential of #21 and acts on
the owner it proved.

**Why.** When the authorization server is hers, the surface is what makes it
hers. A portal, a command line and a personal AI holding her device key are
three clients of one server here; a surface only one vendor's portal can reach
is a server only that vendor operates.

**Specified in.** [The Resource Owner's API](/spec/draft-gamb-uma4agents-owner-00.html)

## Not a deviation: an enterprise identity assertion as a claim

**What it departs from.** Cross App Access
([`draft-ietf-oauth-identity-assertion-authz-grant`](https://datatracker.ietf.org/doc/draft-ietf-oauth-identity-assertion-authz-grant/))
has the client present an ID-JAG at the resource authorization server as
`grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer` with `assertion=…`,
and receive an access token.

**Here.** The ID-JAG arrives as a `claim_token` against an open permission
ticket, with `claim_token_format=urn:ietf:params:oauth:token-type:id-jag`. The
authorization server names that format in `required_claims` — so the resource
side asks for the assertion — and answers with a second `need_info` carrying
the owner's terms. The grant is issued against the signed agreement, as it is
for every other request.

**Why.** A `jwt-bearer` exchange would have the identity provider's assertion
produce the access token directly, which makes the provider the deciding party
over the resource. That is the right design when the enterprise owns the data
and the wrong one here, where an organization's charter governs its own book
and the member administering it sets the terms. An ID-JAG proves *identity and
approved reach* and carries no entitlement of its own, which is precisely what
a UMA claim is for. Nothing is invented: this is stock claims-gathering, one
claim per beat, with the ticket rotating.

The order matters too. Identity is asked for before terms are dictated,
because which tier applies and what her terms may say both follow from which
member the agent acts for.

**What is deliberately not extended.** The exchange at the identity provider
is unmodified — ordinary RFC 8693 token exchange with the draft's parameters
and `typ: oauth-id-jag+jwt` on the result. An enterprise's existing provider
needs no knowledge of this profile, and the assertion it mints is the one the
draft describes. See [cross app access](/docs/overview/cross-app-access/).

This is stock UMA claims-gathering, one claim per beat, with the ticket rotating. The departure is from the Cross App Access draft's `jwt-bearer` exchange, not from UMA, which is why it is listed here and not numbered. See [Core §4.1](/spec/draft-gamb-uma4agents-core-00.html#claim-token-formats).

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
- **The resource server must not be able to read the owner's policy.** The owner
  API takes only her credential, which the resource server never holds, so the
  public path refuses it; in the Kubernetes reference the mesh also refuses the
  direct hop. `k8s-policy-test` asserts both.
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

- **What an operation leaves behind is declared by the resource** that would
  have to undo it, published in the metadata it already signs, and read by the
  owner's policy as a condition that may only tighten. An operation nobody has
  described is undescribed — not safe, and not grave.
- **A clearance is obtained from somebody other than the requesting party.**
  A licence or a jurisdiction may be adverse to the party being asked about,
  so it travels authority-to-authority and is refused before terms are
  dictated. The grant carries a digest that the check happened; the facts stay
  on the owner's side.

**Not addressed.** Signing-key rotation — the key is minted once and shared by
all replicas, and while `jwks_uri` makes rotation possible, nothing here
exercises it. Multiple authorization servers behind one resource server — RFC
9728 makes `authorization_servers` an array; this profile configures one. And
revocation propagation beyond a single shared store.
