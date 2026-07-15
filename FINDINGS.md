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
| RS-side registration + PAT (FedAuthz) | **Keep direction, relocate work** | The owner-authoritative direction is right; the RS burden belongs in a gateway |
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
both fit). This POC runs both methods against an otherwise identical stack
— `REGISTRATION_MODE=push|pull` — so the trade is measured, not argued.
The gateway relocation stands in either mode: naive resources sit behind an
MCP gateway that carries the FedAuthz obligations; the MCP server cannot
tell it's protected.

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

**6. Bindings as thin, separate documents.** Ship the core with a first
binding to a concrete agent-identity/PoP layer (this POC binds to AAuth) and
plan a second for the OAuth+DPoP installed base. One spec, multiple bindings,
each recruiting a different implementer community.

---

## Binding notes (AAuth)

Observations from binding the grant layer onto AAuth as it exists today,
offered as engineering notes on a foundation:

- **AAuth's resource token is permission-ticket-shaped, with the negotiation
  state on the opposite side.** UMA mints the ticket at the *owner's* AS
  (owner-authoritative from message one); AAuth mints the resource token at
  the *resource*. For an owner holding a pending "ask-me" request, the UMA
  direction is the one that carries. Worth a joint look at where pending state
  should live.
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
