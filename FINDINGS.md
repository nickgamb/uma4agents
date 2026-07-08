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
| Resource registration model | **Transform** | Durable resources → registered *tool/capability surfaces*, declared outward via RFC 9728 Protected Resource Metadata (see below) |
| Interactive claims gathering (browser redirect) | **Transform** | Same slot, new interlocutors: agent-side elicitation, owner-side push |
| Trust-elevation levels, multi-AS, legal framework | **Parking lot** | Real and implicated, out of scope for a first POC; revival conditions noted |

The POC also surfaced four capabilities the agent era demands. They split
into two groups.

**Named uses of classic machinery** — no new primitives; UMA 2.0 already
carries the parts, but the agent-era *use* deserves normative naming:

| Capability | Status in POC | Classic ancestry |
|---|---|---|
| Owner-mediated agent registration ("day-1 handshake") | Built | The RO-approves-the-relationship shape (as with PAT issuance), applied to the **requesting-agent side** rather than the RS side. Distinct from client registration: DCR-style AS↔client credentials are orthogonal (the agent's PoP key plays that role); what's new-in-use is the *owner* approving a standing RqP-agent relationship. |
| Standing-relationship handle (agent key thumbprint) | Built | The PCT is the closest ancestor — persisted state for a returning requesting side. Here it is keyed by the agent's key thumbprint and made **owner-visible and owner-revocable** (a registry with a revoke switch), which classic PCT semantics never required. |

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

**5. Relocate the FedAuthz resource-server burden to a gateway, and pair it
with Protected Resource Metadata.** The 2015 adoption friction — resource
servers making active calls to the AS — is answered by conferring UMA
protection at a gateway (here, an MCP gateway): naive resources sit behind it
unmodified while the gateway registers their tool surfaces, catches
unauthorized calls, and introspects tokens. The discovery direction is
covered by RFC 9728: the POC's gateway serves a Protected Resource Metadata
document announcing the owner's authorization server and — as an extension
member — the protected *tool surfaces* themselves, so an agent can find the
AS declaratively before it is ever challenged. Registration pushes inward,
metadata declares outward; together they answer the old friction from both
directions. Whether the tool-surface extension belongs in an enhanced PRM
profile is a good working-group question.

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
