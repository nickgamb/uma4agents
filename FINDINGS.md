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
| Claims-gathering (`need_info` demand loop) | **Keep, transform** | Becomes the owner *dictating* an intent-contract template, not just naming claim formats |
| RPT (requesting party token) | **Keep semantics, replace token** | Keep the per-permission introspection array; drop the bearer token for a PoP token |
| RS-side registration + PAT (FedAuthz) | **Keep direction, relocate work** | The owner-authoritative direction is right; the RS burden belongs in a gateway |
| Resource registration model | **Transform** | Durable resources → registered *tool/capability surfaces* |
| Interactive claims gathering (browser redirect) | **Transform** | Same slot, new interlocutors: agent-side elicitation, owner-side push |
| Trust-elevation levels, multi-AS, legal framework | **Parking lot** | Real and implicated, out of scope for a first POC; revival conditions noted |

And four capabilities the agent era needs that UMA 2.0 does not describe:

| New capability | Status in POC | Why it's new |
|---|---|---|
| Owner-mediated agent registration ("day-1 handshake") | Built | First contact pends; approval establishes a standing relationship |
| Standing-relationship handle (agent key thumbprint / PCT) | Built | Distinguishes "known advisor's agent" from "stranger who signed the terms" |
| Per-operation, single-use grants | Built | "Approve this trade" must not become "may trade"; approval permits one action |
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

**2. Make the intent contract first-class.** The single most valuable
transformation is claims-gathering becoming an *owner-dictated* terms
template that the requesting side echoes and signs. This is the direct
descendant of the 2010 "Requesting Party Policy" claim (Maler/Bryan) —
purpose-bound, counterparty-dictated, persistent for audit. It is the
mechanism that makes a declared intent *enforceable and testable* rather than
merely displayed. An attestation from the requesting side (e.g. an AAuth
mission reference) fits cleanly as *one acceptable claim type* the owner's AS
may demand — subsuming that model rather than competing with it.

**3. Specify the day-1 handshake.** The first question any reviewer asks —
"how do Alice and a new agent establish trust?" — is answered by the pending
state doing double duty as owner-mediated agent registration, with a standing
handle (key thumbprint; the PCT is the spec-native candidate) distinguishing a
connected agent from a stranger. This deserves normative text; the POC shows
it needs no new primitive, only a named use of `request_submitted` plus a
relationship record.

**4. Retire the bearer RPT; bind to modern proof-of-possession.** Keep the
rich per-permission introspection semantics; carry them inside a
sender-constrained token. In the POC the RPT is issued as a PoP token whose
key binding is verified at enforcement time, and per-operation grants add an
operation hash so a single-use approval authorizes exactly one call.

**5. Relocate the FedAuthz resource-server burden to a gateway.** The 2015
adoption friction — resource servers making active calls to the AS — is
answered by conferring UMA protection at a gateway (here, an MCP gateway):
naive resources sit behind it unmodified while the gateway registers their
tool surfaces, catches unauthorized calls, and introspects tokens. This is
both an adoption argument and a clean home for a protocol binding.

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
