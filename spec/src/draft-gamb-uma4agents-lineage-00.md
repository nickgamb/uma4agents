---
title: "Agent Lineage for User-Managed Access (UMA) 2.0"
abbrev: "Agent Lineage"
docname: draft-gamb-uma4agents-lineage-00
date: 2026-09-15
category: info
submissiontype: IETF
ipr: trust200902
area: Security
keyword: [UMA, authorization, agents, sub-agents, orchestration, revocation]
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
  RFC7515:
  RFC7517:
  RFC7638:
  RFC8693:
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
  U4APolicy:
    title: "Owner Policy, Assurance and Attention for User-Managed Access (UMA) 2.0"
    author:
      - ins: N. Gamb
        name: Nick Gamb
      - ins: E. Maler
        name: Eve Maler
    date: 2026
    seriesinfo:
      Internet-Draft: draft-gamb-uma4agents-policy-00
    target: https://u4a.ai/spec/draft-gamb-uma4agents-policy-00.html
informative:
  I-D.hardt-aauth-protocol:
  I-D.niyikiza-oauth-attenuating-agent-tokens:
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

This document lets an autonomous agent that holds a standing relationship with a
resource owner introduce another agent to her. The introduced agent skips the
owner's first-contact question and then negotiates its own terms, under its own
key, for its own grant. Nothing is handed down.

The task graph an orchestrating agent builds may nest as deeply as it likes.
The authority graph stays one level deep: every agent is separately visible to
the owner, separately bounded by her policy, and separately revocable, and
revoking the agent that introduced others revokes them with it.

--- middle

# Introduction

An orchestrating agent spawns workers. Under {{U4ACore}} each worker is
individuated by its own key, so each is a stranger to the owner and each costs
her a question. The usual answer is to hand the workers the parent's token, at
which point they are indistinguishable from the parent in the owner's records,
cannot be revoked individually, and hold authority the owner never agreed to
give them. Attenuated-token designs such as
{{I-D.niyikiza-oauth-attenuating-agent-tokens}} narrow what is handed down
without changing that it is handed down.

This document takes the other position. The parent may say *this is one of
mine*, and the owner's authorization server may act on that by not asking her
whether she wants a relationship with the newcomer. Everything after that is
the newcomer's own: it signs the owner's terms with its own key, is bound by
her policy as itself, and receives a grant confirmed to its own key. An
introduction admits an agent; it does not approve anything for it.

## Relationship to the Set

This document is an OPTIONAL extension of {{U4ACore}} and depends on
{{U4ATerms}} and {{U4APolicy}}. Its identifying URI is
`https://u4a.ai/spec/lineage/1.0`.

## Notational Conventions

{::boilerplate bcp14-tagged}

`jkt(k)` is as defined in {{U4ACore}}, over the JWK Thumbprint of {{RFC7638}}.

# Asserting a Lineage {#asserting}

A client asserts that another agent introduced it in exactly one of
two ways.

## By Introduction Document {#introduction-document}

The introducing agent signs a compact JWS {{RFC7515}} whose protected header
carries:

typ:
: REQUIRED. `u4a-introduction-v1+jws`.

jwk:
: REQUIRED. The introducing agent's public key {{RFC7517}}.

agent_token:
: OPTIONAL. The introducing agent's identity credential, where it is an
  identified agent under {{U4ACore}} Section 5.1. Its confirmed key MUST equal
  `jwk`.

and whose claims are:

sub:
: REQUIRED. `jkt(k)` for the introduced agent's key `k`.

aud:
: REQUIRED. The issuer identifier of the owner's authorization server.

exp:
: REQUIRED. Expiry. SHOULD be short; the reference implementation uses five
  minutes.

iat:
: REQUIRED.

jti:
: REQUIRED.

The introduction deliberately carries no `iss`. The introducing agent's
identity travels only in the header key, which the signature verifies against
and from which the authorization server re-derives a connection handle. An
`iss` naming the introducer would have to be either ignored or believed, and
believing it would let any agent nominate any other agent's handle as its
sponsor.

The introduced agent carries the introduction in its agreement ({{U4ATerms}})
as a claim named `introduction`. An authorization server MUST bound the size of
an introduction it will parse; the reference implementation refuses one over
4096 octets.

## By Issuer Attestation {#act-claim}

Where the introduced agent is an identified agent, its issuer MAY assert the
lineage instead, by placing the introducing agent's subject identifier in an
`act` claim {{RFC8693}} of the introduced agent's credential. No second document
is needed; the authorization server reads the claim it already verified.

{{I-D.hardt-aauth-protocol}} uses `act` on its auth token to record a delegation
chain, not in its agent credential. Its agent token permits additional claims,
and this document uses the same claim there.
Nothing new is defined here; the claim is read.

# Admission {#admission}

## What the Document Settles {#verify}

On receiving an assertion of lineage, the authorization server MUST first
establish what the document settles on its own: that it verifies against the
key in its header, that its `aud` names this authorization server, that it has
not expired, and that its `sub` equals the thumbprint of the key that signed the
agreement it arrived in. An assertion that fails any of these is a malformed
request and MUST be refused as one.

## What the Owner's Record Settles {#admit}

An assertion that holds up as a document is then decided against the owner's
record. The authorization server MUST refuse to act on it unless every one of
the following holds, and MUST check them in this order so that a refusal names
the strongest reason:

1. The introducing agent holds an active standing connection with this owner,
   looked up by the handle derived from the header key (or, under {{act-claim}},
   from the issuer and the `act` subject).
2. The owner has personally approved the introducing agent at at least one
   policy unit. An agent she has never said yes to cannot vouch for another.
3. The introducing agent was not itself introduced. Depth is capped at one by
   this check and by nothing else — an introduced agent becomes eligible under
   check 2 the moment the owner approves it at anything, so without this check
   the cap would be an accident of timing.
4. The introduced agent has no prior connection with this owner that is not
   active. A revoked agent goes back through first contact; an introduction
   MUST NOT restore what the owner withdrew.
5. Under {{introduction-document}}, one operator has published both keys: the
   introduced agent is at accountability level 2 ({{U4APolicy}} Section 4.2),
   and the *same* directory at the *same* origin also holds the introducing
   key. Under {{act-claim}}, the issuer's attestation satisfies this check.
6. The introducing agent has fewer live introduced agents than a deployment
   ceiling.

Check 5 exists because an agent cannot be allowed to point at a second
directory it runs itself. The directory that attests the child is the one that
must also attest the parent.

## Failure Falls Back {#fallback}

An assertion that holds up as a document but fails {{admit}} is not an error.
The authorization server MUST record why the introduction was not honoured, and
MUST then treat the request exactly as one that offered no lineage: the agent is
a stranger, and first contact is put to the owner. The introduction was a
shortcut that did not apply, not a credential that was rejected.

## The Introduced Connection {#introduced-connection}

Where the assertion is honoured, the authorization server MUST record a
standing connection for the introduced agent without asking the owner, carrying
the introducing agent's handle, and MUST NOT record any approval for it. It MUST
carry forward any prior revocation count for the same handle, as {{U4ACore}}
Section 9.

An introduced connection MUST be created only after every refusal the
authorization server would apply to a first contact — a blocked operator, a
policy refusal, the attention bound — has been passed. Persisting it earlier
leaves a live connection for an operator the owner has shut out.

The owner's record MUST show the connection as introduced, and by whom.

# Policy Over a Lineage {#policy}

## Approval Belongs to the Lineage {#pooling}

Approval the owner gives at a policy unit belongs to the lineage, not to the
connection that earned it, and flows in both directions. An authorization
server MUST make available to policy the set of units at which the owner has
personally approved any live member of a lineage — the introducing agent or any
agent it introduced — and MUST exclude revoked members from that set.

The owner approved a unit for this fleet; it does not matter which member
earned it. A worker that was approved to trade means the orchestrator that
spawned it need not be asked again to trade.

## Three Postures {#postures}

An owner MUST be able to express each of the following per policy unit, using
the conditions of {{U4APolicy}}:

Per agent:
: Every agent is asked once at this unit, introduced or not: an `ask` rule on
  the condition that this agent has never been granted here. A unit with no
  rules does not behave this way — it resolves to its baseline ({{U4APolicy}}
  Section 2) — so an authorization server that offers this posture by default
  does so by seeding the rule.

Lineage-wide:
: Whoever in the lineage earns this unit, the rest inherit it. Expressed by
  narrowing the per-agent ask to fire only when nothing in the lineage has been
  approved here.

Always ask for introduced agents:
: An introduced agent is asked at this unit every time, whatever its lineage
  has earned.

All three are tightening conditions on the observed side of the asymmetry in
{{U4APolicy}} Section 3. Lineage-wide is not "relax when the lineage is
approved" — it is "narrow the existing ask so that it fires only when the
lineage is new". Which agents join a lineage is chosen by the operator running
them, so the requesting side can only ever cause an ask to remain; it cannot
cause one to go away.

## The Ceiling {#ceiling}

A unit the lineage was never approved for pends for an introduced agent
exactly as it would have for the introducing agent. This is not configurable.
Introduction skips the relationship question; it does not skip the owner.

# Attention {#attention}

An introduced agent MUST be counted against the attention bound of {{U4APolicy}}
Section 6 as a first contact is, and the pending requests it generates at
policy units MUST be counted with it. An agent skips the relationship question,
not the queue discipline; otherwise one approved agent could flood the owner's
queue with introduced ones, each individually well-formed and none counted.

# Revocation {#revocation}

Revoking a connection MUST revoke every connection it introduced, in the same
operation. The authorization server MUST revoke the introducing connection
first, so that a negotiation arriving mid-cascade cannot find it active and be
admitted behind it, and MUST report the number of connections and grants the
cascade ended.

Because depth is one ({{admit}} check 3), the cascade need not recurse.

Every introduced agent's live grants stop working on its next call, through the
introspection of {{U4ACore}} Section 8.2, with no action per link. Revoking an
introduced agent that held the lineage's only approval at a unit returns the
lineage to pending at that unit, which is correct: the approval was hers and it
was for an agent she has now removed.

An agent revoked by cascade MUST NOT be re-admitted by an introduction from the
agent whose revocation ended it ({{admit}} check 4), and MUST NOT be re-admitted
by an introduction from any other agent either.

# Security Considerations

## Nothing Is Handed Down

The introduced agent's grant is confirmed to its own key, over terms it signed
itself, under a policy evaluated against it. The introduction confers no
permission, no scope, and no approval; it removes one question. An
implementation that lets an introduction carry anything else has reinvented
token passing with an extra document.

## The Introducer Is Looked Up, Never Named

See {{introduction-document}}. The only statement of who introduced an agent is
the key that signed the introduction, which the signature proves possession of
and the owner's record resolves. A design that let the introduction name its
signer would let any agent claim any sponsor.

## Depth Is a Check, Not an Emergent Property

See {{admit}} check 3. The reference implementation was first written on the
assumption that an introduced agent could never introduce, because it begins
with no approvals. That is false the moment the owner approves it at anything.
The cap has to be explicit.

## Same Operator Means Same Directory

See {{admit}} check 5. Level-2 accountability proves an operator published a
key. Two keys in two directories at two origins prove two operators, or one
operator and an impostor. The check is that one directory holds both.

## Fan-Out Is a Ceiling, Not a Rule

Check 6 bounds how many agents one connection may put forward, so that the
attention bound of {{attention}} is not the only thing standing between an
approved agent and an unbounded fleet. It is a deployment ceiling and not an
owner policy: the reference implementation defaults it to three.

# Privacy Considerations

The owner's record shows every introduced agent, who introduced it, and what it
did, as {{U4APolicy}} Section 8 requires of any agent. An orchestrator's
structure is therefore visible to the owner to the depth of one, which is the
depth at which she is asked to trust it.

# IANA Considerations

This document has no IANA actions. The identifiers it uses are listed in
{{used-identifiers}}.

--- back

# Identifiers Used by This Document {#used-identifiers}

This appendix lists the identifiers this document defines. It is informative and
requests no registration.

| Identifier | Kind | Defined in |
|---|---|---|
| `application/u4a-introduction-v1+jws` | Media type | {{introduction-document}} |
| `introduction` | Agreement claim ({{U4ATerms}}) | {{introduction-document}} |
{: title="Identifiers used by this document."}

# Implementation Status {#implementation-status}

This section records the status of known implementations in the sense of
{{?RFC7942}}, and is to be removed before publication as an RFC.

The reference implementation {{U4ALAB}} implements this document in full,
including both assertion forms of {{asserting}}. The admission decision is
tested by minting introductions with the client library and verifying them with
the server module, so the two sides are checked against each other; every
refusal in {{admit}} is exercised, as are the three postures of {{postures}},
the ceiling of {{ceiling}}, approval flowing from an introduced agent to the
agent that introduced it, and the cascade of {{revocation}} against live grants.

# Acknowledgments
{:numbered="false"}

{{RFC8693}} supplied the `act` claim and {{I-D.hardt-aauth-protocol}} the use of
it in an agent credential that {{act-claim}} reads.
