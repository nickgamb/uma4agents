# Findings: UMA for Agents

A decomposition study with a working lab behind it. We took UMA 2.0 apart into
its primitives, carried the ones that fit agentic authorization into a running
proof-of-concept, and recorded what translated cleanly, what needed reshaping,
and what the agent era demands that the 2018 specification has no slot for.

The thesis the POC set out to test: *every agent protocol today answers "is
this my agent doing my task?" None answers "may your agent touch my stuff?"
UMA answered that question a decade ago — it needs agent-shaped mechanics, not
a new primitive.* The build supports that thesis, with specific reshaping
required. Each verdict below is backed by running code; deeper evidence is
available on request.

---

## Verdicts at a glance

| UMA 2.0 primitive | Verdict | One-line rationale |
|---|---|---|
| Cross-principal grant topology (RO ≠ RqP; AS is the owner's policy home) | **Keep** | The idea the rest hangs off; nothing else on the table has it |
| Permission ticket as negotiation handle | **Keep** | Carried clean; its single-use rotation is exactly what makes "pending" safe |
| `request_submitted` pending state | **Keep** | Already specifies "ask me"; the agent era only adds *where* the owner is asked |
| Claims-gathering (`need_info` demand loop) | **Keep, transform** | Becomes the owner *proffering* a terms template (MyTerms / IEEE 7012-shaped), not just naming claim formats |
| RPT (requesting party token) | **Keep semantics, replace token** | Keep the per-permission introspection array; drop the bearer token for a PoP token |
| RS-side registration + PAT (FedAuthz) | **Keep direction, relocate work; specify the bootstrap** | The owner-authoritative direction is right; the RS burden is *relocatable* — a gateway, a framework, or the resource itself (rec 7). Both hosts run here against one AS. What is missing is how the RS becomes a client of *her* authority at all: FedAuthz assumes it already is, which holds only where one operator runs both sides. The RS can authenticate as its own origin instead (rec 21) |
| One AS per protected resource (implicit) | **Transform** | A resource server holds many people's accounts and each of them may name a different authorization server. Every owner-scoped artifact has to carry its owner — the ticket, the RPT, the resource id, the terms template, and the RFC 9728 document itself. Two owners run here over one resource server, one of them on an authority the resource server was never configured against |
| Resource registration model | **Transform** | Durable resources → *tool/capability surfaces*; and registration itself becomes method-agnostic — classic push RReg, or declarative pull from RFC 9728 metadata plus a protected owner-resources listing (rec 5; both run in this POC) |
| Interactive claims gathering (browser redirect) | **Transform** | Same slot, new interlocutors: agent-side elicitation, owner-side push |
| Resource rights administration (RO ≠ the person at the console) | **Transform** | Named since 2015, never mechanised. Three of PP2PI's four co-administration states are deployments of the existing party model; the fourth — one resource owned by an organization, administered by several people under *their own* authorities — needs the authority selected per (resource, administrator) and one new field in the organization's policy: whose agent may act. See rec 25 |
| Trust-elevation levels, multi-AS, legal framework | **Parking lot** | Real and implicated, out of scope for a first POC; revival conditions noted |

The POC also surfaced four capabilities the agent era demands. They split
into two groups.

**Named uses of classic machinery** — no new primitives; UMA 2.0 already
carries the parts, but the agent-era *use* deserves normative naming:

| Capability | Status in POC | Classic ancestry |
|---|---|---|
| Owner-mediated agent registration ("day-1 handshake") | Built | The RO-approves-the-relationship shape (as with PAT issuance), applied to the **requesting-agent side** rather than the RS side. Distinct from client registration: DCR-style AS↔client credentials are orthogonal (the agent's PoP key plays that role); what's new-in-use is the *owner* approving a standing RqP-agent relationship. |
| Standing-relationship handle (identity-shaped) | Built | The PCT is the closest ancestor — persisted state for a returning requesting side. Here it is made **owner-visible and owner-revocable** (a registry with a revoke switch), which classic PCT semantics never required. The handle's shape follows the identity level: a pseudonymous agent *is* its key, so the RFC 7638 thumbprint carries; an identified agent's session keys rotate (AAuth binds a fresh key per session), so the handle must be the verified issuer-qualified subject — **the key cannot be the relationship key once real agent identity arrives**. This bit us in the build: thumbprint-keyed connections forgot an enrolled agent on every run. |

**Outside the classic lines** — genuinely new surface:

| Capability | Status in POC | Why it's new |
|---|---|---|
| Per-operation, single-use grants | Built | "Approve this trade" must not become "may trade"; the RPT carries an operation hash and is consumed on use. Classic UMA scopes authorize *classes* of action, not one action. |
| Owner's agent / app as the consent surface | Built (portal) | The 2010 out-of-band-consent wireframes, with an interlocutor that finally exists |
| Delegation by party (`none` / `first-party-only` / `any-agent`) | Built | The organization can say *whose* agent may act on a resource it shares, which is a statement about parties rather than permissions. Nothing in UMA 2.0, OAuth or any policy engine has a place for it, and it only becomes expressible once the owner's authority can distinguish an agent she activated from one somebody else runs |

---

## Recommendations to the working group

**1. A core "UMA for agents" grant spec, transport-agnostic.**
Carry forward the party model (owner, requesting party, and — reviving the
2010 term — *requesting agent*), the ticket/negotiation loop, offline grants,
and owner-dictated claims. Write it against *properties* ("a requesting agent
with verifiable identity," "proof-of-possession on requests"), not a specific
wire protocol, so no single vendor's roadmap can strand it. This is the UMA 2.0
maneuver run again: recompose as a grant layer, not a rival stack.

*Why not GNAP.* RFC 9635 has been a published standard since October 2024, it
is literally the Grant **Negotiation** and Authorization Protocol, and its
continuation handles look a great deal like tickets — so the question deserves
an answer rather than a silence. GNAP negotiates between a client and *its
own* resource owner: the party operating the client and the party who can
authorize are assumed to be reachable through one interaction, and its
interaction model is built around getting that person in front of the AS.
What it has no notion of is a second principal who is not the requester, is
not present, and whose policy must be satisfied while they are asleep — nor of
an owner *proffering* terms the requesting side must sign. Those two are the
whole of this work. GNAP is a better host for this grant than OAuth 2.0 would
be, and a GNAP binding is a reasonable third document; it is not a substitute
for the core, because the thing the core adds is exactly the thing GNAP
assumes away.

*A note on where enforcement runs.* This recommendation says "transport
agnostic"; the build showed the same has to be said about **which software
enforces**. FedAuthz gives the resource server a job list — hold a PAT (§1.5),
keep the AS's view of its resources current (§3), ask for a permission ticket
(§4), introspect before allowing a call (§5) — and never names the component
that does the work. §1.4 divides responsibility between the *parties*, not
between processes.

So this POC runs two shapes against one authorization server
(`ENFORCEMENT_MODE=gateway|embedded`): a gateway with plain MCP servers behind
it that know nothing about UMA, and no gateway at all, with the MCP server
handling the grant itself. Same ticket, same terms, same token. The one thing
that does not survive the move is the *challenge encoding* — rec 7.

*What makes an enforcement point portable, found by moving one.* Carrying the
gateway shape from a configuration file to a Kubernetes control plane put the
claim under load, and it held: the request body, the signature headers and the
path rewrite all arrive unchanged, and the expression that rewrites the path
transfers character for character. Exactly one thing does not survive — the
`Host` header, which arrives as the *authorization service's* own address and
cannot be configured to do otherwise.

It cost nothing here, and the reason is worth stating as guidance rather than
luck. The enforcer reconstructs the RFC 9421 signature base from its
*configured* expected authority and never from the request, a decision made so
that an attacker cannot set the authority it is checked against. That single
decision is also what made the move survivable: an enforcement point that had
recovered the authority from the transport would have broken silently, with
signatures failing to verify for a reason nothing in the logs would name. So:
**an enforcement point must take its authorization inputs from its
configuration and from the credential, never from the routing layer that
delivered them.** It is a security rule and a portability rule with one cause,
which is usually the sign of a good one.

**2. Make the owner's terms first-class — as MyTerms, extended.** The single
most valuable transformation is claims-gathering becoming an *owner-proffered*
terms artifact that the requesting side echoes and signs. This is the shape of
**IEEE Std 7012-2025 ("MyTerms"): the individual proffers machine-readable
terms as first party; the entity's agent agrees as second party** — and the
direct descendant of UMA's own 2010 "Requesting Party Policy" claim
(Maler/Bryan). The POC was checked against the published standard and speaks
the pattern on the wire:

- *Terms as persistent documents* — every version of the owner's terms is
  dereferenceable for the life of her AS (`GET /terms/{template_id}`), with a
  consistent name, version, and purpose (7012 §4.3), in three representations
  at one URI: plain-language HTML (§4.4.1), JSON, and JSON-LD using ODRL
  permissions/prohibitions (§4.4.2 and Annex A's own recommendation).
- *Single choice, no haggling* — the AS proffers one terms set per tier; the
  agent signs or declines (§5.2.2's "no negotiation beyond the single
  choice").
- *Identical dual records* — the grant returns a receipt, counter-signed by
  the AS, that embeds the complete agent-signed agreement, so both parties
  hold the same dually-signed artifact (§5.2.2, §5.4.4); refusals are
  recorded too (§5.2.4), on both the owner-decision and agent-decline sides.
- *Party identifiers* — the agent is identified pseudonymously by its public
  key thumbprint (§5.4.5).

Honest divergences from the published standard, each a working-group
question: 7012 §4.2 places the terms roster with a **neutral nonprofit**
(Customer-Commons-style), where this POC's roster is the owner's own AS —
bespoke, authored terms rather than a bounded shared list chosen through a
§5.2.1.2 chooser; there is no lawyer-readable contract text (§4.4.3); and the
requesting side has no §5.3.1(b) counter-offer affordance. Whether agentic
*access* terms (purpose, scope, expiry, prohibited actions) become a MyTerms
extension with a shared roster is exactly the standardization opportunity.
What this profile adds over base MyTerms is that the terms are *enforced
inside a grant* rather than merely recorded — which is what makes intent
testable rather than displayed. An attestation from the requesting side
(e.g. an AAuth mission reference) fits as one acceptable claim type the
owner's AS may demand.

**3. Specify the day-1 handshake — precisely.** The first question any
reviewer asks — "how do Alice and a new agent establish trust?" — is answered
by the pending state doing double duty as owner-mediated agent registration.
To place it against classic UMA's two adjacent mechanisms: it is *not* client
registration (DCR-style AS↔client credentials remain orthogonal; the agent's
proof-of-possession key plays that role), and it is *not* PAT issuance (which
introduces the RS). It is the RO-approves-the-relationship shape applied to
the **requesting-agent side**: the owner admits a specific agent, identified
by its key, into a standing relationship her policy can then reference — with
the PCT as the spec-native ancestor for the persisted state. This deserves
normative text; the POC shows it needs no new primitive, only a named use of
`request_submitted` plus an owner-visible, owner-revocable relationship
record.

**4. Retire the bearer RPT; bind to modern proof-of-possession.** Keep the
rich per-permission introspection semantics; carry them inside a
sender-constrained token. In the POC the RPT is issued as a PoP token whose
key binding is verified at enforcement time, and per-operation grants add an
operation hash so a single-use approval authorizes exactly one call.

**5. Make resource registration method-agnostic: keep RReg, add a
declarative profile built on RFC 9728 — with the owner context split out
behind a protected listing.** This is the same maneuver UMA already made on
the client side (client registration is method-agnostic; DCR and now CIMD
both fit). Both methods were built and run against an otherwise identical stack, so
the trade below is measured rather than argued. Only the declarative profile
is carried forward on the main line; the RReg implementation is preserved
and runnable on the `legacy/rreg-baseline` branch, which is what makes the
comparison checkable rather than merely reported.

Moving the RS-side burden works in either method, and the sharper statement
is that **the spec should describe the job, not the box**. FedAuthz already
does — it gives the resource server a job list and never names the software
that performs it. A gateway is one way, and it is the one that lets a plain
MCP server participate untouched; the MCP server doing the work itself is
another, which is what a deployment with no gateway in the path looks like
(MCP SDK 2.x exposes `Extension.intercept_tool_call` for exactly that).

Our own earlier drafts got this wrong, reading as though the gateway were
where the burden *belongs*. It is where we happened to put it. The
recommendation is that the spec state the resource-server obligations as a
conformance profile any resource-side implementation may satisfy, rather
than in terms that imply a topology.

*What the pull profile is.* The RS stops calling the AS and only publishes:
a public RFC 9728 document carrying **structure** (tool surfaces + scopes,
`authorization_servers`, `jwks_uri`, `signed_metadata` so a relayed copy
stays attributable) and an `owner_resources_endpoint` extension member; the
owner-bound **instances** are served at that endpoint only to a querier
proving possession of the owner's AS signing key (RFC 9421 — the same
message-signature profile the agent uses for proof-of-possession, pointed
the other way). The AS pulls both layers and materializes its registry; one
fetch replaces N registration calls. Eve's phrase for the protected layer
named the design: **"a kind of protected webfinger for Alice's stuff."**
Discovery at both layers, each with the right audience.

*What is lost from RReg — measured.* (a) **AS naming authority**: resource
ids move from AS-assigned to RS-published; they need namespacing under the
resource identifier or two RSs can collide. (b) **Immediate-consistency
CRUD**: push registration is transactional; publication is pull-with-cache,
so staleness is a real state — repaired here by the AS re-pulling when
`/perm` names an unknown id, the exact mirror of push mode's RS-side
re-push after an AS restart (both failure paths hit and fixed in this
build). (c) **The bootstrap forcing function**: RReg forced PAT issuance on
day one; without it, the owner↔AS↔RS triangle must still be established —
the RS-side onboarding handshake. Both halves now run here. Alice's
relationship with her brokerage keeps the seeded day-0 secret, which is the
true account of an authority stood up alongside the resource server it
protects. Carol's is established at runtime by the resource server signing
with a key published at its own origin, because nobody was ever in a
position to configure her server and that firm against each other. See
recommendation 21 and [docs/MULTI-OWNER.md](docs/MULTI-OWNER.md). The PAT
itself is unchanged either way: `client_credentials`, `uma_protection`
scope, expiring, owner-revocable. (d) **Privacy
inversion, resolved by the split**: RReg was a private RS→AS channel, so it
could carry owner-bound descriptions; a public well-known document cannot —
publishing which resources Alice owns would be a leak RReg never had. The
owner context was never really in the resource description anyway; it was
in the PAT — and the PAT survives untouched on the permission and
introspection APIs. (In this POC the registry was *already* inert on the
grant path before the switch: `/perm` + tier policy carried the load. The
heavyweight part of RReg did no work a published document couldn't do.)

*What PRM needs — little, and 9728 anticipated it.* Extension members with
an IANA registry, `signed_metadata`, `jwks_uri`, path-inserted well-known
URIs, and the §5.1 `resource_metadata` challenge parameter all exist. The
profile registers two members (structural `tool_surfaces`, the
owner-resources endpoint) and composes `resource_metadata` with the UMA
challenge — which also buys a security improvement the baseline lacked:
clients corroborate the challenge's `as_uri` against the resource's
published `authorization_servers` instead of taking an unauthenticated
header on faith. Multi-owner resource servers need guidance (per-instance
metadata must not become an enumerable list of owners); the protected
listing is the shape that avoids it.

*Is plain "OpenAPI documentation in PRM form" sufficient for all users?*
No — sufficient to route, insufficient to authorize. API-shape metadata
answers "what exists and what scopes govern it." It cannot answer whose AS
governs which instance or under what terms, because those are per-owner and
must not be public. The permission ticket remains the intent artifact 9728
explicitly scopes out; PRM tells you the shape of the door, the ticket
tells you whose door and the terms of entry.

*Deployment note for any pull profile* (learned as a live deadlock): the
pull and its verification form a call cycle — the AS queries the RS while
the RS authenticates the AS against the AS's own published keys. Verifiers
must tolerate a live back-call or verify against pre-cached keys.

That cycle has a second edge, found by putting the same stack behind an
orchestrator that gates traffic on a readiness check. The obvious readiness
signal for an AS in a pull profile is "my registry is populated" — and it
deadlocks: the AS has no ready endpoint, so the RS's back-call to its JWKS
fails, so the pull fails, so readiness never goes green, and what an operator
sees is a healthy-looking process stuck at zero-of-one until it gives up
quietly. **Readiness must depend on the grant endpoints, not on the pull.**
Whether the pull has completed is worth exposing — the lab serves it
separately — but it is a diagnostic, never a gate. The general form: in a
profile where two parties authenticate each other by dereference, neither
party's liveness may be conditioned on the exchange completing.

**6. Bindings as thin, separate documents.** Ship the core with a first
binding to a concrete agent-identity/PoP layer (this POC binds to AAuth) and
plan a second for the OAuth+DPoP installed base. One spec, multiple bindings,
each recruiting a different implementer community. **MCP is now the third and
most urgent**: it has a formal, composable authorization-extension track
(`modelcontextprotocol/ext-auth`), and its 2026-07-28 revision independently
grew most of the machinery this grant needs. Draft in
[docs/MCP-BINDING.md](docs/MCP-BINDING.md).

**7. Specify the challenge as parameters, not as `WWW-Authenticate`.** The
obvious core text would require a `401` carrying `as_uri`, `ticket` and
`resource_metadata` in a `WWW-Authenticate: UMA` header. That would have been
a mistake, and building two enforcement hosts is what exposed it. A gateway
has a status line to decorate; a resource enforcing in-process does not — an
MCP `Extension.intercept_tool_call` returns a domain result, so beat 1 has to
be a JSON-RPC error carrying the same three values. Mandating the header would
have excluded every in-process deployment, which is to say the resource-side
frameworks most likely to adopt this. **Require the parameters; let each
binding say how they travel.** This POC runs both encodings against one
authorization server, and one client understands both.

**8. `input_required` needs a subject — and the authorization context MCP
could not define is a proof-of-possession key plus a rotating ticket.** Two
findings against MCP 2026-07-28, stated in its own vocabulary because that is
what makes them actionable:

- MRTR (SEP-2322) gives a server a way to say "I need input before I can
  finish" and hand back a resumable `request_state`. But `input_requests` is a
  *closed* union of `CreateMessageRequest | ListRootsRequest | ElicitRequest`
  — sampling the client's model, reading the client's filesystem, asking the
  client's human. There is no member, and no extension point on the members,
  for *blocked on a different principal who is not on this connection*. MCP's
  type system cannot express the case this entire experiment is about. The fix
  is small: a `subject` block on an input request, whose one required field is
  `reachable_by_client: false`. Without it a conforming client will try to
  satisfy the wait from its own user, who has no part in the decision.
- The Tasks extension (SEP-2663) states plainly that it cannot scope
  `tasks/list`, because "servers cannot reliably correlate two unrelated
  handles to the same caller," and concedes task ids act as bearer tokens.
  UMA has an answer it arrived at in 2018: **do not correlate handles, verify
  proof.** Bind the task to the key that signed the intent contract and a
  single-use rotating ticket, and the handle stops being a credential.

*Convergent work worth citing rather than competing with.* RFC 9396 Rich
Authorization Requests is the closest neighbour and was missing from earlier
drafts of this document: UMA's introspection `permissions` array is the same
idea — an array of typed objects describing fine-grained authority — arrived
at five years earlier. Expressing it *as* RAR is what the OAuth+DPoP binding
should do, and it has a second benefit worth naming, since policy engines are
increasingly asked to map token claims directly (Cedar and Cedarling being the
current example): RAR entries carry typed fields, where a content-addressed
digest carries none. This POC's operation binding is a hash by design, which
is right for integrity and leaves a downstream policy engine able to do
equality and nothing else. Carrying both — the digest for binding, typed
details for legibility — is the resolution. AP2 (donated to the
FIDO Alliance) has a Cart Mandate that is our single-use operation-bound grant
in the payments vertical — with the instructive difference that AP2's mandates
are signed by the *requesting* side while ours are owner-dictated.
`draft-oauth-transaction-tokens-for-agents` is the same short-lived
per-transaction idea one layer down. The proposed IETF BoF on AI-agent
auditing is the natural home for the ledger's promised/touched/approved
projection. And MCP's own deprecation of Dynamic Client Registration in favour
of Client ID Metadata Documents is the exact precedent rec 5 argues from: a
registration mechanism made method-agnostic, then replaced, without breaking
the thing that depended on it.

*Considered and not adopted: AuthZEN.* The Authorization API 1.0 became an
OpenID final specification in 2026 and standardises precisely the PEP→PDP call
this stack makes. It was not adopted because the decision here carries a `cnf`
key, an operation-parameters hash, and single-use consumption semantics that
its request/response model has no natural slot for, and because "any gateway
can enforce this" is already served by ext_authz. Most of its practical value
— a PEP that can tell *why* a token was refused — was obtained instead by
adding reason codes to introspection.

**9. Say that single-use means indivisible, not merely once.** UMA 2.0 says a
permission ticket is single-use, and this profile adds a single-use,
operation-bound RPT. Neither the specification nor our own first
implementation says *how* "once" is enforced, because in 2018 an authorization
server was tacitly one process, and one process makes the question invisible:
read the flag, decide, write the flag, and nothing can interleave.

That is a property of the deployment, not of the design, and it does not
survive the deployment changing. Our `/consume` endpoint was check-then-act
and correct only because a single asyncio event loop never yielded between the
read and the write — its own docstring said the burn "has to be the atomic
step" while the code around it made that true by luck. At more than one
replica the same code lets one owner-approved trade be spent twice, and the
failure is silent: both callers are told yes.

So the normative text should say the thing the 2018 text could take for
granted. **A single-use artifact must be consumed by an operation that both
decides and records in one indivisible step, and that reports to the caller
whether it won.** A caller told it lost must deny. That sentence is
implementable as one SQL statement, one Lua script, or one compare-and-swap;
what it rules out is the shape that reads first and writes second, which is
what everybody writes when the question never came up.

Two related places the same reasoning applies, both of which bit us: the
owner's decision (a double tap, or two portals open on the same pending
request, must produce one decision, not two), and revocation (deactivating a
standing relationship and burning the grants issued under it are one act — a
revocation that flipped the connection and then failed would leave the agent
holding exactly the authority the owner had just withdrawn). The lab races
thirty-two callers at each of these against both of its storage backends
(`make store-test`), which is the cheapest possible way to keep the claim
honest.

*Why this is a spec finding and not an implementation note.* Every
implementer will meet it, none of them will be warned by the current text, and
the symptom is a replayed transaction rather than an error. It costs one
sentence.

**10. Say how the owner authenticates to her own authorization server.** UMA
2.0 and FedAuthz are silent on it, which was reasonable in 2018 when an AS was
tacitly a web application the owner logged in to. It stops being reasonable the
moment the authority can be *personal* — on her laptop, or inside a personal AI
— because the profile then requires her to stand up an identity provider before
she can answer a single request. Two credential modes cost one code path, and
the second reuses the verifier already present: an RFC 9421 signature over her
request, checked against a key she enrolled, which is the same message-signature
profile the agent uses for proof-of-possession pointed the other way.

The configuration worth specifying is **both at once**. A person reaches her own
things more than one way — a browser, a phone, a personal AI holding a key —
and each credential should be independently sufficient and independently
revocable, with none a fallback for another. The reference stack runs
`oidc,local-key`, and a decision lands in the same ledger either way. See
[docs/KWAAI-BINDING.md](docs/KWAAI-BINDING.md).

**11. A message-signature profile has to say which requests cover their body.**
The four components this profile signs — `@method`, `@authority`, `@path`,
`authorization` — say who is asking and what they are asking of. They say
nothing about the bytes, and that distinction is invisible until an endpoint
carries its meaning in a body rather than a URL.

Ours does. `POST /owner/pending/{family}/decision` is the owner saying yes or
no, and with those four components alone an intermediary can leave her
signature untouched and change the word. The family is in the path and cannot
be retargeted; the answer can be inverted, which is worse, because it is silent
and it is hers. This implementation had exactly that gap, and the case is
recorded because the shape of the mistake generalises: a signature profile
defined once, for one endpoint, and then reused for another whose meaning
moved from the URL into the body.

The fix is RFC 9530 `Content-Digest` as a covered component, and there are two
rules worth writing into a spec rather than one.

**A verifier must be able to require the digest, not merely accept it.**
Optional coverage is not coverage — a signer that omits it still produces a
signature that verifies. Endpoints whose body is the decision should mandate it.

**Verifying the signature and verifying the digest are two obligations.** RFC
9421 builds the base from the `Content-Digest` *header field value*; RFC 9530
says nothing about whether that header is true. Our first fix recomputed the
digest from the received body and never read the header. That is safe — a
tampered body cannot match — and it is not conformant, so it would have
rejected any third-party signer whose encoding differed from ours. Reading the
header for the base and *separately* asserting it against the bytes that
arrived satisfies both. A verifier that does only the first trusts the
attacker's arithmetic; one that does only the second is not verifying what was
signed.

**12. Identity levels are two, and description is not one of them.** Running the
same negotiation against four requesting-side arrangements — a bare key, an
AAuth-identified agent with rotating session keys, a CIMD-described agent, and
one published in a Web Bot Auth directory — produces **two** connection handles,
not four. Either the key is the identity, or a verified issuer stands behind it.
CIMD and Web Bot Auth are additive *description*: they let a party who has never
met this agent say something true about who operates it, and change nothing
about how it is filed or judged. Terms, grant and policy are byte-identical
across all four.

A core spec should say this plainly, because the failure mode is attractive and
quiet: an implementation that lets a directory lookup or a metadata document tip
a decision has changed the trust model without changing the wire. The test that
catches it is the negative one — the owner's policy contains no identity
vocabulary at all. See [docs/FLOW.md](docs/FLOW.md) and `make flow-check`.

*Refined by recommendation 13.* Description can now tip a decision in exactly
one direction — towards asking her — and still cannot tip one towards granting.
The negative test above still holds, because the vocabulary her policy uses
names properties of evidence rather than identity systems.

**13. Agent assurance should be decomposed, not scaled.** The recurring request
is for policy that faces the requesting side, and the recurring fallback is an
allow-list of agents, which is an ACL with extra steps. There is a better shape,
and the first thing to get right is not to write it as a level.

Identity assurance already ran this experiment. LOA 1-4 was one ordinal scale
until NIST SP 800-63-3 split it into IAL, AAL and FAL, because a single scale
forces unrelated evidence into one order and lets a strong showing on one axis
compensate for a weak one on another. Agents make that worse, not better: an
agent can be perfectly recognisable and wholly unaccountable. So: **three
independent axes — binding, provenance, accountability — and no composite
score.** A composite is the mechanism by which strong key binding excuses an
unknown operator, which is a trade nobody would make if asked directly.

Second, and this is the part that makes client-facing policy safe at all,
separate what the agent can *show* from what the owner has *seen*, and make
them asymmetric:

> Assurance may only tighten a requirement. Only standing — the owner's own
> record of this agent — may relax one.

The rule is not arbitrary; it follows from who produced the evidence — and the
line wants drawing one notch finer than "the owner's side", because one of the
owner's own facts is circular. "We have granted here before" may record an
*automatic* grant, so relaxing on it lets one automatic grant justify the next.
What may safely relax is what the owner herself decided: she admitted this
agent, she approved at this tier, she has never revoked it. Everything else,
including the authority's own issuance records, may only tighten.

The rule has a consequence worth putting in a spec verbatim: **a lie can only
cost the liar friction.** That is what lets an authorization server read a self-asserted
operator name without inheriting a trust framework, an accreditation scheme, or
a registry — none of which exist, and choosing one would be a larger claim than
this problem needs. Enforce it where policy is *stored* rather than where it is
evaluated: a rule that could widen access on evidence the counterparty controls
should fail to save, not fail silently.

One more thing a spec can say without inventing a trust framework. The step
from "an operator says it runs this agent" to something checkable does not
need accreditation — it needs the operator to publish *this agent's key* and
the relying party to go and look. A Web Bot Auth key directory, fetched by the
authorization server and required to be same-origin with the client identifier,
turns a self-assertion into an attestation by the only party with standing to
make one. Failure to resolve must leave the claim where it was rather than
counting against the agent: an operator's outage is not evidence about an
agent.

See [docs/ASSURANCE.md](docs/ASSURANCE.md), `make assurance-check`,
`make rules-test`.

**14. The owner's attention needs a budget, and the spec should say so.** UMA
2.0 has `request_submitted` and no opinion about how many of them a resource
owner can be made to hold. Keys are free, so an unbounded pend queue makes the
property that justifies the whole profile — she decides — into its own
denial-of-service surface. Nothing in the protocol notices; every one of those
requests is individually well-formed.

Rate limiting is the wrong instrument. Per key it is theatre, per source
address it is the wrong layer, and neither expresses the thing that matters,
which is not how fast strangers arrive but **how much of her queue they may
occupy at once**. A depth limit does express it, and has three properties a
rate limit does not:

- it is self-healing — every answer frees a slot, so the cap is on the backlog
  and never on the relationship;
- **a flood crowds out neither the agents she has standing with nor a newcomer
  that can be named**, which is the property that decides whether an attack is
  an annoyance or an outage — and the second half is easy to miss. A single
  queue protects continuity and leaves *onboarding* undefended, because the
  agent you want to let in is a stranger too the first time. Split the queue on
  something an agent cannot assert for itself (here: its named operator having
  published its key), so a flood of the cheap kind cannot reach the lane where
  new relationships form. A lane is not permission — everything in it still
  faces the owner's policy unchanged;
- it needs no new state, being a read of the pending queue she already has.

Refuse past the cap rather than queueing, and say why: an honest 429 lets a
legitimate agent come back, where silence is indistinguishable from a broken
server and provokes exactly the retry storm the cap exists to prevent. A cap of
zero is a coherent posture (invitation-only) and should be expressible, but is
the wrong default for a profile whose argument is that a stranger can negotiate.

And say what the owner does about a flood once it *is* attributable, because
one connection at a time is not an answer: a single action against the operator,
which shuts out every agent it runs and revokes what is already connected in the
same step. Blocking is a restriction, so it may rest on the agent's own claim —
an agent that lies about its operator lies itself into a refusal. A spec should
also be honest that this does not remove anyone from the internet: dropping the
claim returns the same party as an anonymous stranger, which is precisely why
the queue split matters more than the block.

See [docs/ASSURANCE.md](docs/ASSURANCE.md) and `make assurance-check`.


**15. Give the requesting side somewhere to say what it is asking for — and
make it tighten-only.** Nothing in UMA 2.0, and nothing in this profile before
this build, lets the requester state its own errand. The agreement is the
owner's template echoed back; on a tier without per-operation binding the
requesting side contributes a signature and nothing else. Meanwhile every
agent-intent design in the market is exactly that missing field: AP2's Intent
Mandate, the verifiable-intent work on top of it, session-intent drift
detection. They are all requester-side, and they all assume the party declaring
the intent owns the resource.

So the field is worth specifying, and the constraint on it matters more than
the field. It must be **carried, never evaluated.** An authority that reads a
stated purpose and rules on whether it is plausible has put a judgement about
natural language inside an authorization decision — the same request becomes
answerable two ways, and the property that four differently-arranged requesting
sides produce one unchanged decision (rec 12) is gone. Bound it, record it,
show it to the owner, and let policy do exactly one thing with it: notice when
it is missing. Then a lie costs the liar friction, which is rec 13's rule
arriving at the same place from a different direction.

**16. Say which prohibitions a resource server can actually refuse, and mark
them as such.** A terms document that lists five prohibitions in one flat array
tells the reader that all five are equally a matter of trust. In this profile
that was false for two of them, and had been since before the terms existed:
the trade tier forbids "orders beyond the approved parameters" and
"discretionary reuse of authority", and the enforcement point had always
refused exactly those two — an operation digest and a spent single-use grant.
Nothing connected the words to the mechanism.

The distinction is not terms against enforcement. It is whether the forbidden
thing **has to cross the owner's boundary to happen**. Placing an order means
calling her tool. Retaining the data afterwards happens on disks she will never
see. Both belong in her terms; only the first can be refused, and a
specification should require the document to say which is which — derived from
the profile's own mechanisms rather than asserted, so it cannot drift from what
is actually switched on. The half that remains unenforceable is not weakened by
being labelled; it is the half the dually-signed record exists for, and calling
it a control was the overstatement.

**17. Intent drift is the resource owner's observation, not the requesting
side's report.** The prevailing designs put drift detection with the requester:
declare a task, watch the session, flag a departure. That is coherent while one
party owns both the agent and the data, and it collapses the moment they come
apart. It asks the owner to accept a report from infrastructure she cannot
inspect, about an agent belonging to the party producing the report, with
nothing to check it against. An agent can attest anything.

She does not need the report. Every request that agent ever made of her arrived
at her side, and once the record names the agent (rec 16 above) the shape is
already there: what it declared, what she decided, what it then called, and
against which of her resources. Breadth, volume, and persistence after a
refusal are all readable without cooperation from anyone.

So a core spec should locate drift evaluation at the **authorization server**,
say that the inputs are the owner's own record rather than requester
attestations, and keep the whole vocabulary tighten-only — an agent must not be
able to improve its own standing by describing itself, which is rec 13 arriving
here from a third direction. Requester-side session-intent work is complementary
and belongs in a different document: it protects the requesting party from their
own agent, which is a real problem and not this one.

**18. A decision record keyed only by transaction cannot answer a question
about a party.** Our ledger correlated everything by negotiation, which answers
"what happened in this exchange" and not "what has this agent been doing" — and
the second is the question an owner actually asks. Eleven write sites, four
carrying an agent handle, inconsistently, inside the entry body.

The sharp edge is not the missing filter. A **denied or refused** negotiation
issues no token, so nothing anywhere links that entry to an agent, and the one
pattern most worth seeing — *this agent has asked four times and I have said no
four times* — was underivable from what we stored. Normative text should say a
decision record carries the counterparty, and should name the class that
genuinely cannot: a decline arrives before the requesting side has signed
anything, so there is no key and nothing to file it under. That entry is
honestly anonymous, and a spec that does not say so invites an implementation
to invent an attribution.

One deployment note that generalises past this profile: the enforcement point
reports the calls it allowed and **must not be told the handle**. It enforces
for an authority whose policy it cannot read, and the standing relationship is
the owner's record. The authority resolves the attribution itself, from the
grant the call was made under.

**19. Not every policy input needs the atomicity a single-use artifact needs,
and the test that separates them is short.** Recommendation 9 asks for
indivisible consumption, and the natural over-correction is to treat every
input the same way. Policy that reads an agent's recent history — how often the
owner refused it, how many tiers it has reached — is a count over an append-only
record, and making it indivisible would buy nothing.

The distinguishing question: **can a stale read widen access beyond what a
differently-timed arrival would have?** A count that only ever tightens is
monotone inside its window, so a replica one write behind behaves exactly as if
the request had arrived a moment earlier — an ordering the deployment already
permits. A single-use burn fails that test immediately, which is why it is in
the other class. Worth one sentence in a spec, because the cost of guessing
wrong runs in both directions: an unnecessary transaction on a hot path, or a
replayed grant.

**20. Do not specify the owner-is-the-requester case as a special case.** UMA
2.0's cross-principal topology is usually introduced by contrasting it with the
degenerate one, and the contrast invites an implementation to branch. It should
not, and a profile that has to is telling you its party model is wrong.

The reason is the party the 2010 drafts named and 2.0 dropped. When Alice's own
agent asks for Alice's resources the *requesting party* collapses into the
owner, and the **requesting agent** does not: she is still not present, it still
holds its own key, it still signs her terms, and her policy still answers every
request. Everything the profile does for a stranger's agent it does here, for
the same reasons and through the same messages. Building it confirmed that —
the grant needed no branch, and what the case actually required was one policy
condition.

Two things a spec should say about that condition, because they generalise.

**Recognise the owner's agent through the channels every agent already uses.**
Here it is the operator a request names and the key directory that operator
publishes — the same two facts read about anybody. A dedicated enrolment path
for the owner's own agents would work and would be worse: it makes the
degenerate case a different mechanism, which is the thing this recommendation
is against.

**It is the one fact that may loosen a requirement, so it needs both halves.**
The owner claiming an origin is her decision; the operator having published
*this agent's key* is a check the authority ran. Either alone is insufficient,
and the attestation is the half an agent cannot supply for itself — a metadata
document proves only that it claims its own URL, so pointing at the owner's is
free. Drop the attestation
and "this is my agent" becomes a sentence an agent can say about itself, which
inverts recommendation 13 in the one place it must not bend.

Worth noting why this matters beyond conformance. The degenerate case is the
adoption path: an organisation can put owner-authoritative authorization under
its own users' agents first and reach the cross-principal case by writing
policy rather than by rebuilding. That order is not hypothetical — the UK
Pensions Dashboards Programme's technical standards describe a consent and
authorisation service on UMA profiles, and this working group's own [pensions
dashboard use-case report](https://kantara.atlassian.net/wiki/spaces/uma/pages/135659525) puts the person viewing her own discovered
pensions first and delegation to an adviser second. A specification that treats
the first step as a footnote is mis-describing where its adopters will start.

**21. Say how a resource server comes to hold a PAT when nobody could have
configured both ends.** FedAuthz requires the PAT to be issued with the
resource owner's authorization and is silent on how the resource server
becomes a client of her authorization server at all. That silence is
survivable in exactly one topology — the one where a single operator runs both
sides and provisions each against the other — and it is the topology the
specification exists to move past.

The gap becomes structural the moment the authority is the owner's. A person
will not paste a client secret into her broker's console, the broker will not
hold one secret per customer, and there is no moment at which any single party
could arrange the pair, because the pair spans two organisations and a person.
Every deployment that hits this either invents something or quietly becomes
multi-tenant, and multi-tenancy is the arrangement UMA was written to replace.

The mechanism the pieces already imply: **the resource server authenticates as
its origin.** It signs the registration (RFC 9421) with a key it publishes in
the RFC 9728 document that resource already has to serve, and the authorization
server fetches that document itself and checks three things — that it claims
*this* resource, that its `jwks_uri` is same-origin, and that it names *this*
authorization server. No secret is transmitted, nothing is provisioned in
advance, and the party being trusted is the one the challenge already pointed
at, so no new trust is introduced. It is the same discipline a profile should
already be applying to an agent's operator metadata, pointed at the resource
side.

Three things a specification should say about it, because each is a place an
implementation will get it wrong:

**A verified signature settles who is asking and nothing else.** Registration
must land in a state the owner has to leave — `pending`, visible in whatever
surface she uses, granting no PAT. FedAuthz already requires her authorization;
what this adds is that the request may now arrive from a party she has never
heard of, which makes the pending state the whole of the security rather than
a formality.

**Unreachable is refused, and that is a departure worth stating.** Where a
document merely *attests* a claim made by other means, failing to fetch it
should leave the claim where it was — a third party's outage is not evidence
about anybody. Here the document **is** the credential, and a credential that
cannot be fetched has not been presented. A profile that reuses the attestation
language here has specified an authentication that fails open.

**Re-registration must not be a way to undo a withdrawal.** A resource server
the owner has cut off may ask again — that is the same shape as an agent she
has blocked asking again — and asking must return it to `pending`, never to
`active`. The resource server also needs to throttle itself: re-registering on
every request puts the same question in front of her as fast as traffic
arrives, which is a way of pestering someone into a yes.

What this does *not* remove, and should not: which authorization server speaks
for a person is a fact only that person holds. The resource server still has to
be told, by her, the way she tells it a mailing address. What the mechanism
removes is the part that had to be arranged between the two companies — and
that was the part that made a personal authorization server impossible.

Implemented at `POST /rs/register` with `clients/demo-driver/establishment_check.py`
covering the refusals; extension register entry 13 in
[docs/PROTOCOL.md](docs/PROTOCOL.md).

**22. Enumerate what carries the owner — and make the resource identifier one
of them.** UMA 2.0 never says which artifacts are owner-scoped, because with
one authorization server per protected resource the owner is implicit in the
deployment and nothing has to carry her. The moment a resource server holds
two people's accounts, every artifact that crosses a boundary needs an answer,
and the specification currently supplies none. Building it produced this list,
and each entry is somewhere a missing owner is a cross-owner read:

- the permission ticket, so it resolves only at the authority that minted it;
- the token, so a grant for one owner cannot be spent against another;
- the resource identifier and the ids beneath it, so a tool id from one
  namespace never resolves against another owner's policy;
- the terms document identifier, so a version history is hers;
- the protected-resource metadata document itself.

The last one is the trap, and it is an interoperability trap rather than a
local one. Once the resource is `…/mcp/<owner>`, a deployment will still want
a bare path for clients configured before owners existed. RFC 9728 §3.3 has
the client refuse a document whose `resource` is not the resource it is
accessing — so the alias must name *itself*, not the owner's canonical path.
Serving one canonical answer at both is the intuitive choice and it is wrong:
it hands every client at the alias a document it is required to reject. It
cost us a working adapter and a working fixture, and it failed in a way that
looked like the authorization server was down.

A profile should say plainly: **one resource identifier per owner, every
document self-referential, and aliases are resources too.**

**23. Distribution has exactly two fixed points, and they are small.** The
question that follows any owner-scaling claim is whether an authorization
server can be pushed outward — to a person's own hardware, to an edge
isolate, to a million of them. The useful answer is not "yes" or "no" but
which parts resist, and the experiment gives a short list:

| | |
|---|---|
| policy evaluation | pure. Inputs to a verdict, no writes. Runs anywhere, including per request. |
| terms documents, keys, discovery | static artifacts. Cacheable and replicable without coordination. |
| an ask-me decision | human latency. Already wherever she is; the pend outlives the request. |
| **burning a permission ticket, burning a grant** | **indivisible.** Each is spent exactly once, in one step that either happens or does not. |

Only the last row has to hold still, and only because single-use has to mean
indivisible rather than merely once — recommendation 9, and the reason this
build races thirty-two callers at each of those two functions on both storage
backends.

That is a better answer than a scaling number, because it is the shape of the
constraint rather than a measurement of one deployment. It also says what a
personal deployment costs: the two functions serialize *somewhere*, and if
that somewhere is one small process holding its own state, then the process
must be one — this build marks the single-replica authority `Recreate` for
exactly that reason, since two of her would be two authorities behind one
name.

**24. An authorization server the owner names is a conformance property, not
a deployment style.** Nothing in UMA 2.0 prevents a resource server from
naming the same authorization server for every owner it serves, and a
deployment that does is conformant, multi-tenant, and has quietly lost the
property the cross-principal topology exists for: the authority is the
operator's again, and "her policy" is a row in the operator's table.

The distinction is testable from outside and costs one sentence to specify:
**the authority named in the challenge is the owner's choice, and two owners
of one resource server may name two different ones.** Everything else follows
— per-owner metadata, per-owner protection tokens, and the establishment
problem in recommendation 21, which only exists because the answer is allowed
to be an authority the resource server has never met.

**25. Resource rights administration needs a mechanism, and the missing field
is `delegation`.** UMA has named the role since 2015 — a *resource rights
administrator* administers access to resources she does not necessarily own —
and PP2PI's healthcare analysis lays out the four states of co-administration
without a mechanism for any of them. The agent era makes the gap urgent rather
than academic: the moment a resource is shared with someone, "may her agent
touch it" is a question about **parties**, and there is nowhere in UMA 2.0 to
express it.

What the POC found is that three of the four states already work with what UMA
has, and the fourth needs one new field.

*Administration by proxy* needs nothing from the grant loop. What it needs is
one thing the owner's authority already does implicitly and no specification
names: **who may administer this owner's policy**. The lab expresses it as
configuration — `UMA_AS_OWNER_AUTH` says what kind of credential counts and
`UMA_AS_OWNER_KEY_OWNER` says whose it is, because a signature proves a holder
and not an owner — and a real deployment needs that as a managed list rather
than two environment variables. Naming it is cheap and worth doing: it is the
difference between a guardian, a power of attorney and an account takeover,
and today each deployment invents it.

What is genuinely absent is the shape where **the resource stays the
organization's and the administration is distributed to several people, each
under her own authorization server**. One resource, several administrators,
several authorities — and the enforcement point has to know which one to ask.
That resolves cleanly and needs no new primitive: the authority is selected
per (resource, administrator), which is recommendation 24 read once more with
the pair rather than the owner as the key. In the POC it is a path segment.

The new field is on the organization's side. A charter that shares a resource
with a member has to say **whose agent may act on it for her**:

    none | first-party-only | any-agent

Not what may be accessed — *whose agent* is doing the accessing on behalf of
which person. No authorization system built around a single party has anywhere
to put that sentence, and every organization sharing data with staff who run
agents will want it within a year. It is expressible only because the owner's
authority already distinguishes an agent she activated from one somebody else
operates (recommendation 12's first-party fact), and it is safe to rest a rule
on because the requesting side cannot assert it.

Three properties are worth specifying alongside it, because each is easy to
get wrong in ways that are invisible afterwards:

- **A layer above the owner may only narrow, and the narrowing belongs in the
  terms.** The obvious implementation applies an organization's ceiling at
  grant time and leaves the owner's policy alone. It is less code and it is
  wrong: the terms document is what the requesting side dereferences, reads
  and signs, so a document stating what the owner wrote while the grant
  reflects what the organization allows is a document that lies to both of
  them. Clamp on write and the ceiling is *in* what the agent agreed to.
- **The upper layer's reach stops at its own resources — including what it can
  see.** An organization that can enumerate every agent connected to a member
  has replaced her layer rather than sat above it. The scoping has to be the
  owner authority's, applied before it answers, and it has to cover the
  read surfaces as much as the write ones: her pending queue, her connections,
  her operators and her record. Revocation likewise: shutting an agent out of
  the organization's resources must not touch its standing with her.
- **The upper layer's policy has two halves with different disclosure
  obligations, and the boundary is re-consent.** What a member agrees to must
  be a bounded, versioned document she is shown in full — what the
  organization claims, what her group may reach, the ceiling on her terms.
  What the organization enforces operationally — a close period, market hours,
  a limit tried for one quarter — moves on a compliance function's clock, not
  a membership's, and cannot be re-consented to every time it changes. Fusing
  the two gives either a bargain nobody can read or an agreement that changes
  under the people who signed it. The workable line is that the operational
  half may only refuse or interrupt, and that a member is shown the sentence
  of any rule that stops her even though she is not shown the rules. A related
  containment matters as much: a group may only grant what the charter
  *claims*, or "create a group" becomes a route into a member's personal
  resources — the single most dangerous edit in an administrator's console.

And one honest note for the spec: an override *does* have to exist — the
organization owns the data — but it cannot be a flag on a decision the
member's authority makes, because that authority may be hers to run. It has to
be a grant the organization signs itself, checked at the enforcement point
*with the organization* rather than with the member's authority, bounded by a
clause the member was shown before she joined, and unable to be quiet:
notified at the moment a human decides, and written into her record. In the
POC the check is introspection at the organization, which is also where the
single-use burn serializes; the grant is a JWS over published keys, so local
verification is available to a deployment willing to solve single use itself.

Built and demonstrated: `make org-check` (90 assertions over six processes),
`docs/ORG.md`.

---

## Binding notes (AAuth)

Observations from binding the grant layer onto AAuth as it exists today,
offered as engineering notes on a foundation:

- **This POC is already an AAuth four-party (federated) deployment — the
  contribution is a richer AS, not a rival to one.** AAuth's four roles map
  onto what runs here almost one-to-one: the person server is AAuth's **PS**
  (represents Bob, the requesting person), the gateway/PEP is the
  **Resource**, and `uma-as` is precisely AAuth's **AS** (the access server
  that "evaluates resource policy on behalf of the resource"). The permission
  ticket is AAuth's resource token (`aud` = the AS); the RPT is AAuth's auth
  token. What AAuth leaves deliberately open — *how* the AS evaluates policy
  and reaches the owner — is exactly the surface this experiment fills: the
  dictated-terms demand loop, the ask-me hold, the MyTerms agreement. So the
  sharper framing (correcting our own hero line, which over-broadly implied no
  agent protocol is near the "may" question): **AAuth puts an authority in the
  right place and specifies the cross-domain token plumbing; UMA-for-agents is
  the negotiation grammar that authority runs.** Neither spec "answers may" on
  its own — both slot it to the AS — and that slot is the new agent-era
  surface.
- **AAuth's resource token is permission-ticket-shaped, with the negotiation
  state on the opposite side.** UMA mints the ticket at the *owner's* AS
  (owner-authoritative from message one); AAuth mints the resource token at
  the *resource*. For an owner holding a pending "ask-me" request, the UMA
  direction is the one that carries. Worth a joint look at where pending state
  should live.
- **Discovery is binding-shaped; the split is not.** The public/structural
  layer has a natural encoding per binding: `tool_surfaces` in the RFC 9728
  document for the OAuth+DPoP binding, and AAuth's own
  `/.well-known/aauth-resource.json` with an R3 vocabulary
  (`r3_vocabularies`, content-addressed) for the AAuth binding — this POC now
  serves both, from one tool registry. R3's content-addressing is the better
  fit for the *type layer* and sharpens the point the pull work surfaced with
  Eve: operations-and-scopes are universal facts, so a content digest gives
  them a stable identifier independent of any owner. What does **not** change
  with the binding is the layer above it: the protected owner-resources
  listing ("protected webfinger") and the permission ticket are shared across
  both discovery formats — both documents here point at the *same*
  `owner_resources_endpoint`. R3 describes what the *resource's* operations
  are (resource-authored); MyTerms describes what the *owner* permits
  (owner-authored). They compose — R3 does not absorb the ticket or the terms.
- **Proof-of-possession composes for free.** An AAuth auth token is already
  key-bound; carrying UMA's permission array as a claim delivers "rich
  introspection over a PoP token" with no new token type.
- **Deployment reality: TLS is a protocol precondition, not hygiene.** The
  reference AAuth implementation rejects non-HTTPS agent issuers off loopback,
  so cross-host agent identity — the premise of an agent *economy* — requires
  HTTPS on every issuer from the first exchange.
- **A mission reference is only worth carrying if a relying party can
  dereference it.** AAuth's mission layer is the natural counterpart to the
  owner's terms: a durable record, at the requesting party's own person server,
  of that party setting an agent a task, referenced by content hash. This
  profile carries a citation in AAuth's own `approver`/`s256` shape, and stops
  there, because `GET /missions/{s256}` is served to administrators only. From
  the owner's side an agent citing a real mandate and one inventing a hash are
  indistinguishable, so the citation cannot become an assurance axis — awarding
  a level for an assertion nobody checked is the thing rec 13 exists to
  prevent. Karl McGuinness's own three-artifact model already names the piece
  that would close this: the durable record stays private, and the **projected
  ref** is the shareable one. A projection a relying party may fetch would turn
  a claim into an attestation by the only party with standing to make it —
  which is exactly the step from level 1 to level 2 on accountability, and the
  same move the Web Bot Auth key directory makes. Worth a joint look. Note also
  what stays out of scope on the owner's side either way: containment is the
  approver's question, and AAuth is right that the protocol supplies
  correlation rather than containment.
- **Requester-side consent support is uneven across clients.** The interactive
  claims-gathering successor (agent-side elicitation of the owner's terms)
  works where the client supports it and needs a standing-config fallback
  where it does not — itself a note for any future MCP binding.

---

## Parking lot (with revival conditions)

- **Trust-elevation levels** — revisit when tiers need graduated assurance
  (e.g. step-up from pseudonymous to a verified organization).
- **Multi-AS federation** — matters when an owner's resources span authorization
  servers they don't control; out of scope while one owner has one AS.
- **The business-legal framework** (entity-to-entity access licensing, the
  Requesting Agent's legal status) — cite as prior art now; specify when agents
  act with legal effect and liability questions become concrete.
