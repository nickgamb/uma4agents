---
templateKey: doc
title: Findings
seoTitle: "UMA 2.0 for AI agents: findings and recommendations to the working group"
description: What the build produced for the people writing the specifications — verdicts on each UMA 2.0 primitive, seventeen recommendations, and what was parked.
next:
  - title: Deviations from UMA 2.0
    to: /docs/reference/deviations/
    blurb: The extension register each recommendation came out of.
  - title: Standards this composes
    to: /docs/overview/standards/
    blurb: Everything the profile is built from.
---

The point of building this was to produce evidence about what UMA 2.0 needs in
order to serve agentic access. This page is the summary; the full document is
[`FINDINGS.md`](https://github.com/nickgamb/uma4agents/blob/main/FINDINGS.md) in
the repository.

## Verdicts on each primitive

| Primitive | Verdict | Rationale |
|---|---|---|
| Cross-principal grant topology | **Keep** | The idea the rest hangs off; nothing else on the table has it |
| Permission ticket as negotiation handle | **Keep** | Carried clean; its single-use rotation is what makes pending safe |
| `request_submitted` pending state | **Keep** | Already specifies ask-me; the agent era adds only *where* the owner is asked |
| Claims-gathering | **Keep, transform** | Becomes the owner *proffering* a terms template, not just naming claim formats |
| RPT | **Keep semantics, replace token** | Keep the per-permission array; drop the bearer token for proof-of-possession |
| Resource-server registration and PAT | **Keep direction, relocate work** | The direction is right; the burden is relocatable — a gateway, a framework, or the resource itself |
| Resource registration model | **Transform** | Durable resources become tool surfaces, and registration becomes method-agnostic |
| Interactive claims gathering | **Transform** | Same slot, new interlocutors: agent-side elicitation, owner-side push |
| Trust elevation, multi-AS, legal framework | **Parking lot** | Real and implicated, out of scope for a first build |

## Four capabilities the agent era demands

Two are named uses of machinery UMA already has.

**Owner-mediated agent registration** — the day-one handshake. The shape where
the owner approves a relationship, applied to the requesting-agent side rather
than the resource-server side. Distinct from client registration: the agent's
proof-of-possession key already plays that role. What is new in use is the owner
approving a standing relationship with a requesting agent.

**A standing-relationship handle.** The persisted claims token is the closest
ancestor. Here it is made owner-visible and owner-revocable — a registry with a
revoke switch — which classic semantics never required. The handle's shape has
to follow the identity level, because an identified agent's session keys rotate
and a thumbprint-keyed connection forgets it every run. That bit the build.

Two are genuinely new surface.

**Per-operation, single-use grants.** Approving one trade must not become
authorizing trading. Classic scopes authorize classes of action.

**The owner's own agent or app as the consent surface.** The 2010 out-of-band
consent wireframes, with an interlocutor that finally exists.

## The seventeen recommendations

**1. A core grant specification, transport-agnostic.** Carry forward the party
model — owner, requesting party, and reviving the 2010 term, *requesting agent*
— the ticket loop, offline grants and owner-dictated claims. Write it against
properties rather than a wire protocol, so no vendor's roadmap can strand it.

**2. Make the owner's terms first-class.** The single most valuable
transformation: claims-gathering becomes an owner-proffered terms artifact the
requesting side echoes and signs, following IEEE 7012 and descending from UMA's
own Requesting Party Policy claim. Terms as persistent documents in three
representations at one URI; a single choice with no haggling; identical dual
records including a counter-signed receipt; refusals recorded too.

*Honest divergence:* 7012 places the terms roster with a neutral nonprofit; here
it lives on the owner's own authorization server.

**3. Specify the day-one handshake precisely.** What happens the first time an
owner meets an agent she has no relationship with, and how the resulting
relationship is named, stored and revoked.

**4. Retire the bearer RPT.** Keep the introspection semantics; bind to modern
proof-of-possession.

**5. Make resource registration method-agnostic.** Keep push registration; add a
declarative profile built on RFC 9728, with the owner context split out behind a
protected listing. Both were built against an otherwise identical stack, so the
trade is measured rather than argued, and the push implementation is preserved
on a branch so the comparison stays checkable.

What is lost from push registration, measured: authorization-server naming
authority over resource ids, immediate consistency, and the bootstrap forcing
function that made PAT issuance happen on day one. What is gained: one fetch
instead of N calls, one registry with one writer, and a privacy split where
public metadata stays structural.

The sharper statement inside this one: **the specification should describe the
job, not the box.** FedAuthz already does — it gives the resource server a job
list and never names the software that performs it. Earlier drafts of this work
read as though a gateway were where the burden *belongs*. It is where it
happened to be put.

**6. Bindings as thin, separate documents.** Ship the core with a first binding
to a concrete identity and proof-of-possession layer, and plan a second for the
OAuth and DPoP installed base. MCP is the third and most urgent: it has a formal
extension track and its 2026-07-28 revision independently grew most of the
machinery this grant needs.

**7. Specify the challenge as parameters, not as `WWW-Authenticate`.** Building
two enforcement hosts is what exposed this. A gateway has a status line to
decorate; a resource enforcing in-process does not. Mandating the header would
have excluded every in-process deployment — the resource-side frameworks most
likely to adopt this. Require the parameters; let each binding say how they
travel.

**8. An input request needs a subject.** MCP's resumable-request machinery hands
back a state handle, but its input-request union addresses only the client's own
model, filesystem and human. There is no member for *blocked on a different
principal who is not on this connection*. The fix is small: a `subject` block
whose one required field is `reachable_by_client: false`. A related finding
concerns task identifiers acting as bearer tokens.

**9. Say that single-use means indivisible, not merely once.** UMA 2.0 says a
ticket is single-use and does not say how "once" is enforced, because in 2018 an
authorization server was tacitly one process — and one process makes the
question invisible. That is a property of the deployment, not of the design, and
it does not survive the deployment changing. This build's own consume endpoint
was check-then-act before it was fixed.

**10. Say how the owner authenticates to her own authorization server.** UMA 2.0
and FedAuthz are silent on it, which was reasonable in 2018 when an authorization
server was tacitly a web application she logged in to. It stops being reasonable
the moment the authority can be *personal* — on her laptop, or inside a personal
AI — because the profile then requires her to stand up an identity provider
before she can answer a single request. Two credential modes cost one code path,
and the second reuses a verifier already present: a message signature over her
request, checked against a key she enrolled. Specify **both at once**, each
independently sufficient and independently revocable, with neither a fallback for
the other.

**11. A message-signature profile has to say which requests cover their body.**
Method, authority and path say who is asking and what they are asking of. They
say nothing about the bytes, and that is invisible until an endpoint carries its
meaning in a body rather than a URL. The owner's decision endpoint does: with
those components alone an intermediary can leave her signature untouched and
invert her answer. Two rules, not one. A verifier must be able to **require** a
content digest rather than merely accept one — optional coverage is not coverage.
And verifying the signature and verifying the digest are **two obligations**: the
signature base is built from the header field, and nothing in that says the
header is true.

**12. Identity levels are two, and description is not one of them.** The same
negotiation against four requesting-side arrangements — a bare key, a verified
issuer with rotating session keys, a metadata document, a published key directory
— produces **two** connection handles. Either the key is the identity, or a
verified issuer stands behind it; everything else is additive description. A core
spec should say so, because the failure mode is attractive and quiet: an
implementation that lets a directory lookup tip a decision has changed the trust
model without changing the wire. The test that catches it is the negative one —
the owner's policy contains no identity vocabulary at all.

**13. Agent assurance should be decomposed, not scaled.** The recurring request
is policy that faces the requesting side; the recurring fallback is an allow-list,
which is an access-control list with extra steps. Identity assurance already ran
this experiment — LOA 1–4 was one ordinal scale until SP 800-63-3 split it, because
a single scale lets a strong showing on one axis compensate for a weak one on
another. Agents make that worse: an agent can be perfectly recognisable and wholly
unaccountable. So **three independent axes — binding, provenance, accountability —
and no composite score**, plus the rule that makes client-facing policy safe at
all: assurance may only tighten a requirement, and only the owner's own decisions
may relax one. Its consequence belongs in a spec verbatim — **a lie can only cost
the liar friction** — because that is what lets an authorization server read a
self-asserted operator name without inheriting a trust framework that does not
exist.

**14. The owner's attention needs a budget, and the spec should say so.** UMA 2.0
has a pending state and no opinion about how many of them a person can be made to
hold. Keys are free, so an unbounded queue turns the property that justifies the
profile into its own denial-of-service surface, and every one of those requests
is individually well-formed. Rate limiting is the wrong instrument; a **depth**
limit expresses the thing that matters, is self-healing, and needs no new state.
Split the queue on something an agent cannot assert for itself, because a single
queue defends continuity and leaves *onboarding* undefended — the agent you want
to admit is a stranger too, the first time. Refuse past the cap rather than
queueing, and say why.

**15. Give the requesting side somewhere to say what it is asking for, and make
it tighten-only.** Before this, the agreement was the owner's template echoed
back: on a tier without per-operation binding the requester contributed a
signature and nothing else. Every agent-intent design in the market is that
missing field — and all of them assume the party declaring the intent owns the
resource. The constraint matters more than the field: it must be carried and
never evaluated. An authority that rules on whether a stated purpose is
plausible has put a judgement about natural language inside an authorization
decision, and the property that four differently-arranged requesting sides
produce one unchanged answer is gone. Bound it, record it, show it to her, and
let policy notice only its absence.

**16. A decision record keyed only by transaction cannot answer a question about
a party.** Correlating by negotiation answers "what happened in this exchange",
not "what has this agent been doing" — and the second is the question an owner
asks. The sharp edge is not a missing filter: a denied or refused negotiation
issues no token, so nothing links that entry to an agent at all. A spec should
say a decision record carries the counterparty, and should name the class that
cannot — a decline arrives before anything is signed, so it is honestly
anonymous. Related deployment note: the enforcement point reports what it
allowed and must not be told the handle. It enforces for a policy it cannot
read; the authority resolves the attribution itself.

**17. Not every policy input needs the atomicity a single-use artifact needs.**
Recommendation 9 asks for indivisible consumption, and the over-correction is to
treat every input that way. The question that separates them: can a stale read
widen access beyond what a differently-timed arrival would have? A count that
only tightens is monotone inside its window, so a replica one write behind
behaves as if the request came a moment earlier. A single-use burn fails that
test immediately, which is why it is in the other class.

## Parking lot

Each with a revival condition, so parking is a decision rather than an omission.

| Item | Revive when |
|---|---|
| Trust-elevation levels | Tiers need graduated assurance — stepping up from pseudonymous to a verified organization |
| Multi-authorization-server federation | An owner's resources span authorization servers they do not control |
| The business-legal framework | Agents act with legal effect and liability questions become concrete |

## How to read these

Every recommendation came out of something that broke, or something that could
not be built as specified. The [deviations register](/docs/reference/deviations/)
is the same material organized by wire surface rather than by argument, and each
entry there names the finding it produced.
