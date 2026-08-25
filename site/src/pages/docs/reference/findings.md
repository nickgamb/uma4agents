---
templateKey: doc
title: Findings
seoTitle: "UMA 2.0 for AI agents: findings and recommendations to the working group"
description: What the build produced for the people writing the specifications — verdicts on each UMA 2.0 primitive, twenty-five recommendations, and what was parked.
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
| Resource-server registration and PAT | **Keep direction, relocate work; specify the bootstrap** | The direction is right and the burden is relocatable — a gateway, a framework, or the resource itself. What is missing is how the resource server becomes a client of *her* authority at all, which FedAuthz assumes it already is |
| One authorization server per protected resource | **Transform** | A resource server holds many people's accounts and each may name a different authority. Every owner-scoped artifact has to carry its owner |
| Resource registration model | **Transform** | Durable resources become tool surfaces, and registration becomes method-agnostic |
| Interactive claims gathering | **Transform** | Same slot, new interlocutors: agent-side elicitation, owner-side push |
| Trust elevation, multi-AS, legal framework | **Parking lot** | Real and implicated, out of scope for a first build |

## Five capabilities the agent era demands

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

Three are genuinely new surface.

**Per-operation, single-use grants.** Approving one trade must not become
authorizing trading. Classic scopes authorize classes of action.

**The owner's own agent or app as the consent surface.** The 2010 out-of-band
consent wireframes, with an interlocutor that finally exists.

**Delegation by party.** Where a resource is *shared* — an organization's book,
administered by the people who work on it — the organization has to be able to
say whose agent may act on it: nobody's, only ones the member operates
herself, or anyone's. That is a statement about parties rather than
permissions, and it has nowhere to live in UMA 2.0, in OAuth, or in a policy
engine. It becomes expressible only because the owner's authority already
knows which agents she activated.

## The twenty-five recommendations

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

**16. Say which prohibitions a resource server can actually refuse.** A terms
document listing five prohibitions in one flat array tells the reader all five
are equally a matter of trust. Here that was false for two, and had been since
before the terms existed: the trade tier forbids orders beyond the approved
parameters and discretionary reuse of authority, and the enforcement point had
always refused exactly those two. The distinction is not terms against
enforcement — it is whether the forbidden thing has to cross the owner's
boundary to happen. Placing an order means calling her tool; retaining the data
afterwards happens on disks she will never see. A spec should require the
document to mark which is which, derived from the profile's own mechanisms so it
cannot drift from what is switched on.

**17. Intent drift is the owner's observation, not the requesting side's
report.** Prevailing designs put drift detection with the requester: declare a
task, watch the session, flag a departure. That collapses the moment the agent
and the data belong to different parties — it asks the owner to accept a report
from infrastructure she cannot inspect, about an agent belonging to whoever
produced the report. She does not need it. Every request that agent made of her
arrived at her side, so breadth, volume and persistence after a refusal are all
readable from her own record. Locate drift evaluation at the authorization
server, read the owner's record rather than requester attestations, and keep the
vocabulary tighten-only. Requester-side session intent is complementary and
belongs in a different document: it protects the requesting party from their own
agent.

**18. A decision record keyed only by transaction cannot answer a question about
a party.** Correlating by negotiation answers "what happened in this exchange",
not "what has this agent been doing" — and the second is the question an owner
asks. The sharp edge is not a missing filter: a denied or refused negotiation
issues no token, so nothing links that entry to an agent at all. A spec should
say a decision record carries the counterparty, and should name the class that
cannot — a decline arrives before anything is signed, so it is honestly
anonymous. Related deployment note: the enforcement point reports what it
allowed and must not be told the handle. It enforces for a policy it cannot
read; the authority resolves the attribution itself.

**19. Not every policy input needs the atomicity a single-use artifact needs.**
Recommendation 9 asks for indivisible consumption, and the over-correction is to
treat every input that way. The question that separates them: can a stale read
widen access beyond what a differently-timed arrival would have? A count that
only tightens is monotone inside its window, so a replica one write behind
behaves as if the request came a moment earlier. A single-use burn fails that
test immediately, which is why it is in the other class.

**20. Do not specify the owner-is-the-requester case as a special case.** The
cross-principal topology is usually introduced by contrasting it with the
degenerate one, and the contrast invites an implementation to branch. When the
owner's own agent asks, the requesting *party* collapses into the owner and the
requesting **agent** does not — she is still absent, it still holds its own key,
it still signs her terms. Building it confirmed the grant needs no branch; what
the case required was one policy condition. Recognise the owner's agent through
the channels every agent already uses rather than a dedicated enrolment path,
and require both halves of the signal, because this is the one fact that may
*loosen* a requirement. It also matters commercially: the degenerate case is the
adoption path, and Kantara's own [pensions dashboard use-case report](https://kantara.atlassian.net/wiki/spaces/uma/pages/135659525)
describes exactly that order — the person views her own pensions first,
delegation to an adviser comes second.

**21. Say how a resource server comes to hold a protection token when nobody
could have configured both ends.** FedAuthz requires the token to be issued
with the owner's authorization and is silent on how the resource server becomes
a client of her authority in the first place. That silence survives in exactly
one topology — a single operator running both sides — and it is the topology
the specification exists to move past. A person will not paste a client secret
into her broker's console, the broker will not hold one per customer, and no
single party is in a position to arrange the pair.

The pieces already imply the answer: the resource server authenticates as its
origin, signing the registration with a key published in the RFC 9728 document
that resource already serves, checked by the authority against that document —
which must claim this resource, be same-origin with its keys, and name this
authority. Nothing is provisioned in advance and the party trusted is the one
the challenge already pointed at.

Three things to state, because each is where an implementation goes wrong. A
verified signature settles *who is asking* and nothing else, so registration
must land in a state the owner has to leave. Unreachable must be **refused**,
not shrugged at — elsewhere a document merely attests a claim and an outage is
not evidence, but here the document is the credential. And re-registering after
a withdrawal must return to pending, never to active, or asking again becomes a
way to undo her answer.

What it does not remove, and should not: which authority speaks for a person is
a fact only that person holds, so she still tells the resource server where hers
is. What goes away is the part that had to be arranged between two companies —
the part that made a personal authorization server impossible. See
[many owners, one resource server](/docs/overview/multi-owner/).

**22. Enumerate what carries the owner — and make the resource identifier one
of them.** With one authorization server per protected resource the owner is
implicit in the deployment and nothing has to carry her. The moment a resource
server holds two people's accounts, every artifact crossing a boundary needs
an answer: the permission ticket, the token, the resource identifier and the
ids beneath it, the terms document identifier, and the metadata document
itself. Each is somewhere a missing owner becomes a cross-owner read.

The last is an interoperability trap rather than a local one. Once the
resource is `…/mcp/<owner>`, a deployment still wants a bare path for clients
configured before owners existed — and RFC 9728 §3.3 has the client refuse a
document whose `resource` is not the resource it is accessing. So an alias
must name *itself*. Serving one canonical answer at both is the intuitive
choice and it hands every client at the alias a document it is required to
reject. One resource identifier per owner, every document self-referential,
and aliases are resources too.

**23. Distribution has exactly two fixed points, and they are small.** Asked
whether an authority can be pushed outward — to a person's hardware, to an
edge isolate — the useful answer is which parts resist. Policy evaluation is
pure and runs anywhere. Terms, keys and discovery are static artifacts. An
ask-me decision is already wherever she is. What has to hold still is burning
a permission ticket and burning a grant, because each is spent exactly once in
a step that either happens or does not.

That is a better answer than a scaling number: it is the shape of the
constraint rather than a measurement of one deployment. It also prices a
personal deployment — those two functions serialize somewhere, and where that
somewhere is a single process holding its own state, the process must be one.

**24. An authorization server the owner names is a conformance property, not a
deployment style.** Nothing in UMA 2.0 stops a resource server naming the same
authority for every owner it serves. Such a deployment is conformant,
multi-tenant, and has lost the property the cross-principal topology exists
for. One sentence fixes it: the authority named in the challenge is the
owner's choice, and two owners of one resource server may name two different
ones. Everything else follows — including the establishment problem in
recommendation 21, which exists only because the answer is allowed to be an
authority the resource server has never met.

**25. Resource rights administration needs a mechanism, and the missing field
is `delegation`.** UMA has named the role since 2015 — a resource rights
administrator administers access to resources she does not necessarily own —
and PP2PI's healthcare analysis lays out the states of co-administration
without a mechanism for any of them. The agent era makes that urgent: the
moment a resource is shared with someone, "may her agent touch it" is a
question about parties, and there is nowhere in UMA 2.0 to express it.

Most of the shape needs no new primitive. An organization that owns a resource
and distributes its administration to several people, each under her own
authorization server, resolves by selecting the authority per (resource,
administrator) — recommendation 24 read once more with the pair as the key.

The new field is on the organization's side: a charter that shares a resource
has to say **whose agent** may act on it for the member — `none`,
`first-party-only`, or `any-agent`. Not what may be accessed; whose agent is
doing the accessing on behalf of which person. It is expressible only because
the owner's authority already distinguishes an agent she activated from one
somebody else operates, and safe to rest a rule on because the requesting side
cannot assert it.

Two properties belong in the specification alongside it. A layer above the
owner may only narrow, and the narrowing belongs **in the terms** — applying a
ceiling at grant time while leaving her policy alone produces a terms document
that lies to the agent signing it. And the upper layer's reach stops at its own
resources *including what it can see*: an organization able to enumerate every
agent connected to a member has replaced her layer rather than sat above it.

An override does have to exist — the organization owns the data — but it
cannot be a flag on a decision the member's authority makes, because that
authority may be hers to run. It has to be a grant the organization signs
itself, checked at the enforcement point with the organization rather than
with her authority, bounded by a clause she was shown before joining, and
impossible to perform quietly.

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
