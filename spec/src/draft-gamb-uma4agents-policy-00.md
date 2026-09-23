---
title: "Owner Policy, Assurance and Attention for User-Managed Access (UMA) 2.0"
abbrev: "Owner Policy for Agents"
docname: draft-gamb-uma4agents-policy-00
date: 2026-09-15
category: info
submissiontype: IETF
ipr: trust200902
area: Security
keyword: [UMA, authorization, policy, assurance, agents]
stand_alone: yes
pi: [toc, sortrefs, symrefs]
author:
  -
    ins: N. Gamb
    name: Nick Gamb
    organization: MindGarden LLC
    email: nickgamb@gmail.com
  -
    ins: E. Maler
    name: Eve Maler
    organization: Venn Factory
normative:
  RFC7638:
  I-D.meunier-webbotauth-registry:
  I-D.ietf-oauth-client-id-metadata-document:
  UMAGrant:
    title: "User-Managed Access (UMA) 2.0 Grant for OAuth 2.0 Authorization"
    author:
      - ins: E. Maler
        name: Eve Maler
      - ins: M. Machulak
        name: Maciej Machulak
      - ins: J. Richer
        name: Justin Richer
    date: 2018-01-07
    seriesinfo:
      Kantara: Recommendation
    target: https://docs.kantarainitiative.org/uma/wg/rec-oauth-uma-grant-2.0.html
  U4ACore:
    title: "User-Managed Access (UMA) 2.0 Profile for Autonomous Agents"
    author:
      - ins: N. Gamb
        name: Nick Gamb
      - ins: E. Maler
        name: Eve Maler
    date: 2026
    seriesinfo:
      Internet-Draft: draft-gamb-uma4agents-core-00
    target: https://u4a.ai/spec/draft-gamb-uma4agents-core-00.html
  U4AFedAuthz:
    title: "Federated Authorization for Autonomous Agents"
    author:
      - ins: N. Gamb
        name: Nick Gamb
      - ins: E. Maler
        name: Eve Maler
    date: 2026
    seriesinfo:
      Internet-Draft: draft-gamb-uma4agents-fedauthz-00
    target: https://u4a.ai/spec/draft-gamb-uma4agents-fedauthz-00.html
  U4ATerms:
    title: "Owner-Proffered Terms for User-Managed Access (UMA) 2.0"
    author:
      - ins: N. Gamb
        name: Nick Gamb
      - ins: E. Maler
        name: Eve Maler
    date: 2026
    seriesinfo:
      Internet-Draft: draft-gamb-uma4agents-terms-00
    target: https://u4a.ai/spec/draft-gamb-uma4agents-terms-00.html
informative:
  SP800-63-3:
    title: "Digital Identity Guidelines"
    author:
      - org: National Institute of Standards and Technology
    date: 2017-06
    seriesinfo:
      NIST: Special Publication 800-63-3
    target: https://doi.org/10.6028/NIST.SP.800-63-3
  U4ALineage:
    title: "Agent Lineage for User-Managed Access (UMA) 2.0"
    author:
      - ins: N. Gamb
        name: Nick Gamb
      - ins: E. Maler
        name: Eve Maler
    date: 2026
    seriesinfo:
      Internet-Draft: draft-gamb-uma4agents-lineage-00
    target: https://u4a.ai/spec/draft-gamb-uma4agents-lineage-00.html
  U4AMultiParty:
    title: "Multi-Party Authorization for User-Managed Access (UMA) 2.0"
    author:
      - ins: N. Gamb
        name: Nick Gamb
      - ins: E. Maler
        name: Eve Maler
    date: 2026
    seriesinfo:
      Internet-Draft: draft-gamb-uma4agents-multiparty-00
    target: https://u4a.ai/spec/draft-gamb-uma4agents-multiparty-00.html
  U4ALAB:
    title: "UMA for Agents: a reference implementation"
    author:
      - ins: N. Gamb
        name: Nick Gamb
      - ins: E. Maler
        name: Eve Maler
    date: 2026
    target: https://github.com/nickgamb/uma4agents

--- abstract

This document specifies what a resource owner's policy over autonomous agents
may say, what may be known about an agent before the owner has met it, and how
the owner's attention is defended.

Its central rule is an asymmetry: evidence supplied by the requesting side may
only tighten a requirement, and only the owner's own prior decisions may relax
one. Agent assurance is decomposed into three independent axes with no composite
score. The owner's pending queue has a depth limit, in two lanes, so that a party
who can mint keys for free cannot make "the owner decides" into a denial of
service. And the owner's record of what was promised, decided and done names the
counterparty on every row it honestly can.

--- middle

# Introduction

{{UMAGrant}} lets a resource owner's authorization server decide on her behalf
and says nothing about what the policy it decides from may contain. That was the
right silence for a specification meant to be profiled, and this document is
one such profile.

The policy an owner writes over agents differs from the policy an administrator
writes over users in one respect that changes everything: the party being
decided about supplies most of the evidence. An agent presents its own key, its
own operator's name, its own credential from its own issuer. A rule that widens
access when that evidence looks good is a rule the agent can satisfy by
producing the evidence. This document exists mainly to say, once and
structurally, that such a rule must not be storable.

## Relationship to the Set

This document is an OPTIONAL extension of {{U4ACore}} and depends on
{{U4ATerms}}. Its identifying URI is `https://u4a.ai/spec/policy/1.0`.

## Notational Conventions

{::boilerplate bcp14-tagged}

# The Shape of a Policy {#shape}

An owner's policy is written against resources, not against agents. Each policy
unit MUST name the resources it covers, MUST name the terms proffered for them
(see {{U4ATerms}}), MUST state whether the owner is asked before access is
granted, and MAY carry rules.

A resource MUST belong to exactly one policy unit. A resource that belongs to
none is ungoverned, and an authorization server MUST refuse access to an
ungoverned resource rather than apply a default.

A rule is a list of conditions and an effect. The conditions of one rule are
conjoined; the rules of one unit are disjoined; and an implementation MUST NOT
offer negation, nesting, or expressions. This is a small, legible document, not
a policy language: the owner reads it, and a policy she cannot read is a policy
she did not write.

~~~ json
{
  "ask_me": true,
  "rules": [
    {"when": ["assurance.accountability_below:1"], "then": "ask"},
    {"when": ["standing.age_above:90d", "standing.never_revoked"],
     "then": "auto"}
  ]
}
~~~
{: title="A unit that asks, except for an agent of ninety days' unbroken standing, unless nobody stands behind it."}

The effects are `auto`, `ask` and `refuse`, in increasing order of strictness.
`ask_me` is the unit's baseline: `ask` where true, `auto` where false.

# The Asymmetry {#asymmetry}

Every condition a rule may name is classed as either *relaxing* or *observed*.

A relaxing condition is a fact that traces to a decision the owner personally
made about this agent, or to a check the owner's authority ran on the owner's
own published material. An observed condition is anything else: what the
requesting side presented, what its operator published, what this server did
automatically, and what the owner did in aggregate.

**A rule whose effect is `auto` MUST name only relaxing conditions.** An
authorization server MUST refuse to store a rule that would relax a requirement
on an observed condition, and MUST refuse it at the moment the owner attempts to
save it rather than storing it and ignoring it at evaluation time.

Enforcing this where policy is stored, rather than where it is evaluated, is the
difference between a deployment that cannot express the mistake and one that
believes it has a control it does not have.

## What May Relax {#relaxing}

An implementation MUST NOT class any condition as relaxing unless it is one of
the following kinds, and MUST class every one of the following as relaxing if it
offers it:

- the owner personally approved access for this agent at this policy unit;
- the owner has never revoked this agent;
- the owner's relationship with this agent is older than a stated duration;
- the agent is one the owner activated herself, as {{first-party}}.

"The owner has previously granted here" is not on the list, and the distinction
is the point. A grant this server made may have been automatic, and relaxing on
it lets one automatic grant justify the next. What may safely relax is what the
owner herself decided. An implementation MUST keep the record of grants it made
and the record of approvals the owner gave apart, and MUST NOT write an approval
where the decision was taken by someone acting for her (see {{U4AMultiParty}}).

An authorization server MUST record who made a decision in the same step that
records the decision, and MUST NOT write an approval as the owner's unless that
record names her. Written in two steps, the moment between them holds a decision
with no author, and a grant loop reading it then has nothing to tell her approval
from an administrator's.

A recorded decision MUST NOT be undone by a later write of the negotiation it
decides. The writer is routinely holding a copy read before the decision was
made — the client's poll rotating its ticket — and writing that copy back
would put a request she has answered back in front of her.

## What May Only Tighten {#tightening}

Every other condition may appear only in a rule whose effect is `ask` or
`refuse`. This includes, without limit:

- the agent's assurance on any axis of {{assurance}};
- the absence of a stated reason or cited mission in the agreement
  ({{U4ATerms}});
- what this server has recently done regarding the agent: how many times the
  owner has denied it, how many policy units it has asked at, how many calls it
  has made;
- that the agent was introduced by another agent ({{U4ALineage}}).

A rule that tightens on the owner's own aggregate conduct — "she has denied this
agent four times" — reads the owner's decisions and is still observed rather
than relaxing, because "she has denied you repeatedly, so grant automatically"
is not a sentence anyone should be able to save.

## Declared Consequence {#consequence}

A resource server may declare what an operation leaves behind, as
{{U4AFedAuthz}} specifies: `reversible`, `compensatable`, `forward_recoverable`
or `irreversible`, ordered by how much remedy remains after the act. An
authorization server MAY offer conditions naming that declaration, so that an
owner can write "ask me about anything that cannot be undone" without naming a
tool — a rule that holds for operations she has never seen, at resource servers
she has never heard of.

An authorization server offering such a condition MUST treat it as one that may
only tighten, under {{tightening}}. The declaration is made by the resource
server rather than by the requesting party, which is what makes it readable at
all; it is still a fact about the request rather than a decision of the owner's,
and only her own decisions relax anything.

An authorization server MUST NOT treat an operation carrying no declaration as
satisfying a condition about how much remedy remains. It MAY offer a separate
condition that names the absence itself, so that an owner who wishes to refuse
what nobody will describe can say so. The two are different sentences: one is
about an act that cannot be undone, the other about an act nobody has described,
and an owner is entitled to hold different opinions of them.

The order is by remedy and not by severity. An authorization server MUST NOT
present it to an owner as a measure of harm, and MUST NOT combine it with the
axes of {{assurance}} into a single score: a reversible act may still be
catastrophic while it stands, and a composite is the mechanism by which one
reading quietly excuses another.

## Clearance {#clearance}

Some authorizations are not the owner's to give. Whether an act is lawful for
the party behind it — a licence that is current, a jurisdiction where the act is
permitted — is a fact about the world, established by somebody else, and the
owner's terms cannot settle it.

A policy unit MAY require such facts. A requirement is a set of claims, each
naming the values that satisfy it. Where a layer above the owner requires
clearance as well ({{U4AMultiParty}}), the two MUST be combined by intersection:
a claim either requires is required, and a claim both require is satisfied only
by values both accept. The layer above may add a claim and narrow an accepted
value, and MUST NOT remove a requirement the owner wrote.

An authorization server MUST obtain a clearance from the attesting party the
policy names, and MUST NOT accept one presented by the client as a claim token.
The rule is the one
{{U4AMultiParty}} arrives at for verdicts, from the other direction: a claim
works when the requesting party is the only one who holds the fact, and fails
when the fact may be adverse to it. A licence is adverse-capable — its holder
has every reason to say it is current — so the attestation travels from the
attesting party to the authorization server directly.

An authorization server MUST verify the attestation's signature against keys the
attesting party publishes, and MUST refuse it unless it names the subject the
negotiation is about and names that authorization server as its audience. An
attestation about one member, issued to one authority, is not evidence about
another member or at another authority.

Where a required clearance is unmet, an authorization server MUST refuse the
negotiation before it dictates terms, and MUST record the reason. An agent that
signed an agreement it was never going to be allowed to act under would hold a
record of a bargain that never existed, and the owner's record would carry an
undertaking that decided nothing.

An authorization server that cannot reach the attesting party has no
attestation, and so refuses under the rule above. A party that cannot be
reached has not attested to anything, and the direction to fail in is the one
the ceiling of {{U4AMultiParty}} already fails in.

## Evaluation Order {#evaluation}

An authorization server MUST evaluate a policy unit's rules in two passes: first
every rule whose effect is `auto`, then every rule whose effect is stricter than
the running result. A restriction that matches MUST win over a relaxation that
also matched, whatever order the rules were written in.

The running result starts at the unit's baseline. A matching `auto` rule in the
first pass sets it to `auto`, which is how an owner lets some requests through a
unit that otherwise asks; on a unit whose baseline is already `auto`, an `auto`
rule changes nothing.

A rule that cannot be evaluated — because a fact or condition it names is
absent, unknown or malformed — MUST be treated as matching if its effect is
`ask` or `refuse` and as not matching if its effect is `auto`. Both land on more
friction. The alternative treats a broken restriction as a working one and a broken
relaxation as a refusal, and the first of those is the one an owner would not
choose.

Until a client holds a standing connection with the owner, a matching rule
whose effect is `refuse` is the only outcome of evaluation an authorization
server may act on. It MUST otherwise put the first contact to the owner,
whatever the rules would decide, and MUST record a refusal made in its place
as {{record}} describes. A rule may turn away a client the owner has not met;
no rule may admit one.

## Publication {#vocabulary}

An authorization server MUST publish the conditions its rules may name, and for
each MUST state whether it may relax. The owner's editing surface then teaches
the rule at the moment it matters, rather than rejecting a save the owner has
already composed.

# Assurance {#assurance}

## Three Axes {#axes}

What an authorization server may know about an agent before the owner has met
it decomposes on three independent axes. An implementation MUST derive each
from a check that has run and passed, MUST NOT accept any of them from the
requesting side's own assertion, and MUST NOT combine them into a single score.

Binding:
: Whether the agreement's signature verified against a key this authority can
  name. Level 0: no. Level 1: yes.

Provenance:
: Whether the agent's credential traces to an issuer whose keys this authority
  fetched. Level 0: the agent is pseudonymous. Level 1: an issuer vouched for it.

Accountability:
: Whether anyone named and reachable stands behind the agent. Level 0: nobody.
  Level 1: the agent named a client metadata document
  {{I-D.ietf-oauth-client-id-metadata-document}} that resolved and claims its
  own URL. Level 2: the operator that document names publishes, in a key
  directory {{I-D.meunier-webbotauth-registry}} at the same origin, the JWK
  thumbprint {{RFC7638}} of the key that signed the agreement.

The decomposition follows the same reasoning as the separation of identity,
authentication and federation assurance in {{SP800-63-3}}: a composite is the
mechanism by which strong key binding excuses an unknown operator, which is a
trade nobody would make if asked directly.

## Level 2 Is the Only Level an Agent Cannot Reach Alone {#level-two}

A metadata document proves that it claims its own URL; anyone can publish one,
so level 1 on the accountability axis is available to any agent that wants it.
Level 2 requires that the key directory be at the *same origin* as the metadata
document, so that an agent cannot point at a directory it runs itself, and it
requires the directory to hold the specific key that signed. Only the operator
can put a key there.

A directory that cannot be resolved MUST leave the agent at level 1, not level
0. An operator's outage is not evidence about an agent. An implementation MUST
cache a directory hit and MUST NOT cache a miss, since a stale hit merely keeps
attesting a key the operator has disowned for the cache's lifetime, and a stale
miss fails to recognise a key the operator just published for the same lifetime
— and only the first of those is bounded by something the operator controls.

## Assurance Is Not a Gate {#not-a-gate}

Assurance MUST NOT decide admission. An agent at level 0 on every axis is
admitted to negotiation like any other stranger, and the owner is asked. What
assurance does is give the owner's rules something true to tighten on, and give
the attention budget of {{attention}} a lane.

A lie can only cost the liar friction. An agent that claims an operator it does
not belong to gains nothing, because the claim never widens anything; it loses
the attributable lane and the owner's trust.

# The Owner's Own Agent {#first-party}

An agent the owner activated herself is the one case where the requesting party
and the resource owner are the same person. This document does not specify it
as a special case, because a profile that has to branch on it is telling you its
party model is wrong. Terms, grant and enforcement are byte-identical; what the
case needs is one policy condition.

An authorization server MUST let the owner claim an operator origin as her own,
and MUST class an agent as the owner's own only where both hold: the operator it
names is one she has claimed, and that operator's key directory publishes the
key that signed. The first half is her decision; the second is a check her
authority ran on material only the operator controls. Neither is anything the
requesting side can assert.

This condition MAY relax a rule (see {{relaxing}}). It MUST NOT skip first
contact, and it MUST NOT beat a restriction that also matched.

The owner MUST be able to disclaim an origin. Disclaiming takes effect on the
next request and revokes nothing; the claim bought friction, not access.

# Attention {#attention}

## A Depth Limit, Not a Rate Limit {#depth}

Keys are free. An unbounded pending queue turns "the owner decides" into a
denial-of-service surface, and every request in the flood is individually
well-formed. A rate limit does not express the constraint: the scarce thing is
how many questions the owner can be made to hold, not how fast they arrive.

An authorization server MUST bound the number of pending requests from agents
that hold no standing connection. Past the bound it MUST refuse with `429` and
`error` of `request_denied`, and MUST NOT queue. An agent that holds an active
connection MUST NOT be counted against the bound and MUST NOT be refused for it,
unless it holds that connection by introduction ({{U4ALineage}} Section 5): an
introduced agent skipped the owner's first question, not her queue, and is
counted as a first contact would be.

{{UMAGrant}} Section 3.3.6 answers `request_denied` with `403`. The bound uses
`429` because the refusal reports the state of the owner's queue rather than a
decision about the request, and a client should not read it as one.

## Two Lanes {#lanes}

The bound MUST be applied in two lanes, split on whether the agent is at level 2
on the accountability axis. Each lane has its own depth, and an implementation
SHOULD set the attributable lane deeper.

The agent the owner wants to admit is a stranger too on first contact. A single
queue defends continuity and leaves onboarding undefended: one anonymous flood
and the agent she is expecting cannot reach her. Two lanes let a flood of
strangers fill the lane strangers use, while an agent whose operator has
published its key still gets through. The lane boundary is level 2 because it is
the only level an agent cannot reach on its own say-so ({{level-two}}).

# Operators {#operators}

## Blocking {#blocking}

The owner MUST be able to block an operator by origin. Blocking MUST end every
active connection held by an agent of that operator and MUST invalidate the
grants under them, in one step, and MUST cause future requests naming that
operator to be refused before the owner's policy is evaluated.

Blocking is a restriction, so it MAY rest on the agent's own claim of its
operator: an agent that misstates its operator only refuses itself.

Unblocking MUST NOT restore connections that blocking ended. It restores the
right to negotiate, not the access that was withdrawn.

## The Limit {#block-limit}

Blocking does not remove a party from the network. The same operator may drop
its client identifier and return as an anonymous stranger — in the
unattributable lane, with nothing standing behind it. That is the honest limit
of operator-level refusal, and it is why the lanes of {{lanes}} matter more than
the block does.

# The Record {#record}

An authorization server implementing this document keeps an append-only record
of what was promised, decided, done and withdrawn, and the following are
requirements on it.

## One Correlation Identifier {#correlation}

An authorization server MUST assign the identifier of a negotiation once, when
the permission ticket is first created, and MUST carry it unchanged through every
ticket rotation. The ticket is a credential for the negotiation; the negotiation
is the thing the record is about.

## Refusals Are Recorded {#refusals}

An authorization server MUST record a refusal — by policy, by a blocked
operator, by the attention bound, or by the owner — with the same prominence as
a grant. A record that shows only successes is indistinguishable from a
deployment with enforcement switched off.

## The Row Names the Counterparty {#counterparty}

Every entry in the record that concerns a client MUST carry that
client's connection handle as an indexed attribute of the row, and MUST do so
for refusals and denials as well as grants. A denied negotiation issues no
token, so nothing downstream links that entry to an agent; if the row does not
carry the handle, the question owners most want answered — *this agent has
asked four times and I have said no four times* — cannot be derived from what
was stored.

Exactly one class of entry cannot carry a handle: a refusal by the requesting
side that arrives before it has signed anything ({{U4ATerms}}). An
authorization server MUST record such an entry without an attribution rather
than invent one.

## Not the Owner's Decision {#attribution}

Where a decision was taken by someone acting for the owner, the record MUST
say who, and the decision MUST NOT be written as the owner's. This is the
requirement that keeps {{relaxing}} honest: "the owner personally approved" is
allowed to relax a rule, so a decision taken on her behalf must not produce that
fact.

## Enforcement Point Reports Do Not Carry the Handle {#pep-reports}

Where an enforcement point reports an allowed call to the authorization server,
the authorization server MUST resolve the agent from the negotiation and MUST
NOT accept a handle from the report. The enforcement point is the resource
server's component; which agent did what is the owner's record and not the
resource server's to assert.

# Security Considerations

## The Asymmetry Is the Security Model

Everything else in this document follows from {{asymmetry}}. A deployment that
lets an observed condition relax a rule has let the party being decided about
write the decision, and the mechanism by which it did so — a well-formed key, a
resolvable document, an operator's name — costs that party nothing.

## Assurance Is Derived, Never Claimed

An implementation that reads an assurance level from anything the requesting
side sent has reintroduced the problem {{axes}} exists to remove. Each level is
the result of a check this authority ran, and the check either ran and passed
or the level is zero.

## Trajectory Reads Are Not Atomic

The conditions of {{tightening}} that read the owner's recent record — denials,
policy units asked at, calls made — need not be read atomically. A count that
only ever tightens is monotone inside its window: a stale read behaves as an
earlier arrival would have, and cannot widen access beyond what a differently
timed arrival would have received. The test for whether a read needs the
indivisibility of {{U4ACore}} Section 8.3 is whether staleness can widen; these
cannot.

## The Bound Is a Depth, and the Depth Is Small

An implementation SHOULD default the unattributable lane to a single-digit
depth. The cost of a bound set too low is that a legitimate stranger is told to
try later; the cost of one set too high is an owner who cannot find the request
she is waiting for.

# Privacy Considerations

## The Record Is a Per-Agent History

{{counterparty}} makes the record queryable by agent, which is what the owner
needs and is also a history of one party's requests kept by another. Retention
is deployment policy. An implementation SHOULD let the owner see every entry
that names an agent, since she is the party it was kept for.

## Operator Claims Are Visible to the Owner

An agent's claimed operator is shown to the owner whether or not it verifies,
with the level it reached. An implementation MUST make the difference visible —
"named" and "published this agent's key" are different sentences — because a
resolved name is exactly what an owner starts keying decisions on, and
{{level-two}} is the only level that means what it appears to.

# IANA Considerations

This document makes no request of IANA. The conditions of {{relaxing}} and
{{tightening}} are described by kind rather than by name so that an
implementation may name them in its own vocabulary; {{shipped-vocabulary}}
records one such vocabulary without registering it.

--- back

# A Condition Vocabulary {#shipped-vocabulary}

This appendix is not normative. It records the vocabulary the reference
implementation {{U4ALAB}} publishes under {{vocabulary}}, as one concrete
instance of the kinds this document requires. Names are `namespace.condition`,
with an argument after a colon where the condition takes one. Durations are
written `90d`, `12h`, `45m` or as seconds.

| Condition | Class | Reads |
|---|---|---|
| `standing.approved_at_tier` | relaxing | the owner personally approved this agent at this unit |
| `standing.never_revoked` | relaxing | the owner has never revoked this agent |
| `standing.age_above:D` | relaxing | the connection is older than D |
| `standing.first_party` | relaxing | an agent the owner activated herself |
| `standing.none` | observed | no standing connection |
| `standing.first_at_tier` | observed | never granted at this unit before |
| `standing.revoked_before` | observed | the owner has revoked this agent before |
| `standing.age_below:D` | observed | the connection is younger than D |
| `standing.denials_above:N` | observed | recently denied more than N times |
| `standing.tiers_above:N` | observed | recently asked at more than N units |
| `standing.calls_above:N` | observed | recently made more than N calls |
| `standing.introduced` | observed | introduced by another agent |
| `standing.lineage_new_at_tier` | observed | nothing approved at this unit for this agent or the ones it works with |
| `assurance.binding_below:L` | observed | binding axis below L |
| `assurance.provenance_below:L` | observed | provenance axis below L |
| `assurance.accountability_below:L` | observed | accountability axis below L |
| `request.max_expiry` | observed | asked for the longest access the unit allows |
| `request.reason_absent` | observed | stated no reason |
| `request.mission_absent` | observed | cited no mandate |
{: title="The reference implementation's condition vocabulary."}

# Record Entry Kinds {#record-kinds}

This appendix is not normative. The reference implementation's record holds the
following kinds of entry, each carrying the negotiation identifier of
{{correlation}} and, where {{counterparty}} permits, the agent's handle.

`promised`, `approved`, `denied`, `connected`, `touched`, `relaxed`, `refused`,
`identity_refused`, `revoked`; `claimed`, `disclaimed` for the owner's own
operators; and the kinds defined by {{U4AMultiParty}} for organizations and
jointly held resources.

# Implementation Status {#implementation-status}

This section records the status of known implementations in the sense of
{{?RFC7942}}, and is to be removed before publication as an RFC.

The reference implementation {{U4ALAB}} implements this document in full. Its
rule engine is tested for the properties of {{evaluation}} directly, including
that the set of relaxing conditions is exactly the set the tests expect and that
every other condition is refused under `auto` at the moment of saving. The
attention bound and both lanes are exercised against a running authorization
server, as is the return of a blocked operator as an anonymous stranger.

# Acknowledgments
{:numbered="false"}

The decomposition of {{axes}} follows {{SP800-63-3}}. The operator key directory
of {{I-D.meunier-webbotauth-registry}} and the client metadata document of
{{I-D.ietf-oauth-client-id-metadata-document}} are what make the accountability
axis derivable rather than asserted.

The consequence vocabulary of {{consequence}} — reversible, compensatable,
forward-recoverable, irreversible — is Nat Sakimura's, from "When Software
Becomes Staff: Governance, Security & Safety for Agentic AI"
(https://nat.sakimura.org/2026/05/19/when-software-becomes-staff-governance-security-safety-for-agentic-ai/).
That work also states the objection this document answers structurally: a
capability an agent declares about itself is advertising, so the declaration
here is made by the resource and read by the party that bears the cost.
