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
| Cross-principal grant topology (RO ≠ RqP; AS is the owner's policy home) | **Keep** | The load-bearing idea; nothing else on the table has it |
| Permission ticket as negotiation handle | **Keep** | Carried clean; its single-use rotation is exactly what makes "pending" safe |
| `request_submitted` pending state | **Keep** | Already specifies "ask me"; the agent era only adds *where* the owner is asked |
| Claims-gathering (`need_info` demand loop) | **Keep, transform** | Becomes the owner *proffering* a terms template (MyTerms / IEEE 7012-shaped), not just naming claim formats |
| RPT (requesting party token) | **Keep semantics, replace token** | Keep the per-permission introspection array; drop the bearer token for a PoP token |
| RS-side registration + PAT (FedAuthz) | **Keep direction, relocate work** | The owner-authoritative direction is right; the RS burden is *relocatable* — a gateway, a framework, or the resource itself (rec 7). Both hosts run here against one AS |
| Resource registration model | **Transform** | Durable resources → *tool/capability surfaces*; and registration itself becomes method-agnostic — classic push RReg, or declarative pull from RFC 9728 metadata plus a protected owner-resources listing (rec 5; both run in this POC) |
| Interactive claims gathering (browser redirect) | **Transform** | Same slot, new interlocutors: agent-side elicitation, owner-side push |
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
the RS-side onboarding handshake (this POC seeds Alice's day-0 consent and
labels it honestly; a real PAT remains: issued via `client_credentials`
with `uma_protection` scope, expiring, owner-revocable). (d) **Privacy
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
  is small: a `subject` block on an input request, whose load-bearing field is
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
`make policy-test`.

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
- **a flood cannot crowd out the agents she already has standing with**, which
  is the property that decides whether an attack is an annoyance or an outage;
- it needs no new state, being a read of the pending queue she already has.

Refuse past the cap rather than queueing, and say why: an honest 429 lets a
legitimate agent come back, where silence is indistinguishable from a broken
server and provokes exactly the retry storm the cap exists to prevent. A cap of
zero is a coherent posture (invitation-only) and should be expressible, but is
the wrong default for a profile whose argument is that a stranger can negotiate.

See [docs/ASSURANCE.md](docs/ASSURANCE.md) and `make assurance-check`.


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
