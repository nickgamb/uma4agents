---
title: "Multi-Party Authorization for User-Managed Access (UMA) 2.0"
abbrev: "Multi-Party Authorization"
docname: draft-gamb-uma4agents-multiparty-00
category: std
submissiontype: IETF
ipr: trust200902
area: Security
keyword: [UMA, authorization, organization, co-ownership, joint accounts, delegation]
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
  RFC7519:
  RFC9728:
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
  PP2PI:
    title: "Solving Data Sharing Challenges with UMA: The Julie Adams Healthcare Use Case from PP2PI"
    author:
      - ins: N. Lush
        name: Nancy Lush
        role: editor
      - org: Kantara Initiative User-Managed Access Work Group
    date: 2023-03
    seriesinfo:
      Kantara: Editors' Draft Report
    target: https://kantara.atlassian.net/wiki/spaces/uma/pages/4850258/Notes+drafts+and+WIP
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

User-Managed Access (UMA) 2.0 has one deciding party per protected resource.
That holds while a resource has one owner and fails in two directions.

Part I of this document specifies a layer above the resource owner: an
organization that shares a resource with its members publishes a charter, each
member's authorization server narrows her terms to the charter's envelope on
write, and the organization is asked once per request over a resource it
claims. It may only narrow. Its role model carries one field UMA has no place
for — whose agent may act on a shared resource.

Part II specifies owners of equal standing: a mandate naming who is entitled to
be counted and how many it takes, a signed verdict from each owner's
authorization server bound to one negotiation and one agreement, and a tally
that folds the owners' terms into the single document the agent signs and issues
a grant carrying the verdicts. The enforcement point re-verifies every verdict
and re-runs the count, so the counting party is unable to lie rather than
trusted.

--- middle

# Introduction

{{UMAGrant}} names a *resource rights administrator* — someone who administers
access to resources she does not necessarily own — and gives the role no wire
surface. {{PP2PI}} lays out four states of co-administration of one person's
records and a mechanism for none of them. And nothing in UMA expresses "these
parties must both agree", nor lets a relying party check that they did.

The agent era makes both gaps urgent rather than academic. The moment a
resource is shared, "may her agent touch it" is a question about *parties* —
about whose agent, acting for whom, under whose ceiling — and there is nowhere
in UMA 2.0 to put the answer.

This document adds two arrangements. In both, the four beats of {{U4ACore}} are
untouched: the challenge, the ticket, the proffered terms, the agreement and the
grant are the same on a shared resource as on a personal one. A requesting agent
cannot tell the difference and does not need to. Everything added is either a
document one party publishes or a question asked of a party that already
existed.

## Relationship to the Set

This document is an OPTIONAL extension of {{U4ACore}} and depends on
{{U4ATerms}}, {{U4AFedAuthz}} and {{U4APolicy}}. Its identifying URI is
`https://u4a.ai/spec/multiparty/1.0`. An implementation MAY implement Part I,
Part II, or both.

## Notational Conventions

{::boilerplate bcp14-tagged}

Throughout, a *policy unit* is as defined in {{U4APolicy}} Section 2.

# Part I: A Layer Above the Owner {#organization}

## Parties {#org-parties}

Organization:
: A party that holds resources and shares administration of them with its
  members. It publishes a charter, answers a decision endpoint, and signs
  documents its members' authorization servers verify against keys it
  publishes.

Member:
: A resource owner under {{U4ACore}} who has enrolled with an organization.
  Her authorization server is hers; the organization is a party it consults.

The organization and the member's user agent have no relationship, and this
document does not invent one. Every message from the organization is addressed
to the member's authorization server.

## The Charter {#charter}

An organization MUST publish a charter, versioned, carrying:

claims:
: REQUIRED. Patterns naming the resources the organization holds. A pattern
  MUST name a namespace: it MUST NOT place a wildcard in the segment that
  identifies whose resource it is, since such a claim would reach a member's
  own resources and jointly held ones alike.

roles:
: REQUIRED. Named roles, each with `grants` (patterns within `claims` the role
  may reach) and `delegation` ({{delegation}}).

envelope:
: OPTIONAL. A ceiling on the terms a member may write over claimed resources
  ({{envelope}}).

break_glass:
: OPTIONAL. Whether and over which claimed resources the organization may reach
  past a member ({{break-glass}}).

The pattern language MUST be segment-wise, with a wildcard matching one segment
and never crossing a separator, and MUST offer neither alternation nor a
recursive wildcard. Four evaluators have to agree on what a pattern matches —
the organization's service, the member's authorization server, the enforcement
point, and any policy engine the organization runs — and a language small enough
to be checked by reading is the only kind that can be.

## Delegation {#delegation}

Each role MUST carry a `delegation` value, one of:

`none`:
: The member may reach the resource herself. No agent acting for her may.

`first-party-only`:
: An agent the member activated herself ({{U4APolicy}} Section 5) may be
  granted access under her terms. An agent somebody else runs may not,
  whatever her own terms say.

`any-agent`:
: Any agent, subject to her terms and the charter.

`delegation` does not say what may be accessed. It says *whose agent* may do
the accessing, on behalf of which person. That is a statement about parties
rather than permissions, and it is only expressible because the member's
authorization server can already distinguish an agent she activated from one
somebody else operates.

## The Envelope, Clamped on Write {#envelope}

An envelope MAY carry:

max_expires_in:
: A member's `expires_in` over claimed resources comes down to this.

allowed_scopes:
: Scopes not in it are removed from her terms.

require_prohibited:
: Prohibitions missing from her terms are added.

always_ask:
: Patterns over which her policy units are set to ask her every time.

Every envelope field moves a member's terms in one direction only. There MUST
be no field that lengthens an expiry, adds a scope, removes a prohibition, or
turns off an ask.

A member's authorization server MUST apply the envelope when a policy unit over
a claimed resource is written, and again whenever the charter changes, by
issuing a new version of the unit's terms document through the same path as
one of her own edits. It MUST NOT apply the envelope only at grant time.

The clamp is applied on write so that the ceiling appears in the terms document
the requesting side dereferences and signs, rather than being applied invisibly
at the door. A terms document MUST state that a layer above the owner is in
force over its resources: an agent reads the document before it signs anything,
and that is the only moment at which "these terms are not hers alone" is
information it can act on.

## The Decision {#decision}

For each request over a resource the charter claims, the member's authorization
server MUST ask the organization's decision endpoint once, presenting the facts
of the request, and MUST fold the answer into its own. The facts are a JSON
object carrying `resource_id`, the `scopes` attempted, the policy unit as
`tier`, the `expires_in`, `purpose`, `reason`, `mission` and `operation` of the
agreement, and the `assurance` and `standing` facts of {{U4APolicy}}; the
member's authorization server presents its membership credential with them.

The organization answers `allow`, `ask` or `refuse`, with reasons. `allow` means
the organization has no objection, not that the request is granted. The
composition rule is one sentence: **both layers must allow, and either may
refuse.** An organization's `ask` raises the member's `auto` to `ask`, and the
member MUST be shown the organization's reasons separately from her own.

An organization's decision MUST NOT widen what the member's policy would decide.
Where the organization cannot be reached, the member's authorization server MUST
refuse requests over claimed resources; a ceiling nobody can read is not a
ceiling.

A request over a resource the charter does not claim MUST NOT be sent to the
organization.

## What the Organization May See {#org-visibility}

An organization MAY be given a view of a member's pending requests,
connections, operators and record, filtered by the member's authorization
server to entries concerning resources the charter claims. It MUST NOT be able
to read the member's policy; at most it may be told which of its envelope fields
bound and whether her units are within the envelope.

The filtering is the member's authorization server's, applied before it
answers, and is not the organization's to respect.

## Acting for a Member {#org-acting}

An organization MAY answer a pending request on a member's behalf, and MAY end
an agent's reach to claimed resources. When it does:

- the record MUST name the organization's administrator, and MUST NOT record the
  decision as the member's ({{U4APolicy}} Section 8.4);
- an agent shut out by the organization loses its reach to claimed resources
  only, held in the membership record so that it ends when the membership does,
  and its standing with the member over her own resources is untouched;
- an introspection response for a grant so affected carries `error` of
  `organization_revoked` ({{U4AFedAuthz}} Section 6).

## Enrolment and Leaving {#enrolment}

A member's authorization server MUST NOT enrol her with an organization without
her explicit agreement to a specific charter version, and MUST show her, before
she agrees, what enrolling would change about terms she has already written.

The organization issues a membership credential to her authorization server at
enrolment — a JWT with `typ` of `u4a-membership+jwt`, signed by the
organization, naming the member as `sub` and the organization as `org` —
and that server presents it as a bearer credential on every call to the
organization. The organization MUST be able to end a membership and MUST
notify the member's authorization server when it does, when her role changes,
or when the charter changes. A notice is a JWT with `typ` of
`u4a-org-notice+jwt`, signed by the organization and verified by the member's
server against the keys it publishes, whose `kind` is one of
`membership_ended`, `role_changed`, `charter_changed`, `break_glass_opened`,
`break_glass` or `break_glass_used`.

Leaving MUST withdraw the member's access to claimed resources and the ceiling
over her, and MUST leave every narrowing the ceiling applied in place. Her terms
were narrowed with her agreement and republished under a new version; undoing
that would silently widen what agents holding agreements over those versions are
held to.

## Break-Glass {#break-glass}

Where the charter enables it, the organization MAY reach a claimed resource
without the member's authorization server, by issuing a grant it signs itself.
Such a grant MUST be single-use, bound to a key, short-lived, and over a
resource the charter both claims and names for this purpose. The enforcement
point MUST recognise it by issuer and MUST introspect it with the organization
rather than with the member's authorization server.

The member MUST be notified at the moment the window opens, before any data
moves. Break-glass cannot be a flag on an ordinary grant: it has to be a grant
the organization signs, checked with the organization, bounded by a clause the
member was shown before she joined, and unable to be quiet.

# Part II: Owners of Equal Standing {#joint}

## Parties {#joint-parties}

Holder:
: A resource owner under {{U4ACore}} who holds a resource jointly with others.
  Each holder has her own authorization server.

Tally:
: A party that publishes the mandate, folds the holders' terms into one
  document, collects verdicts, and issues a grant carrying them. It speaks the
  authorization-server surface of {{U4ACore}} to the requesting agent, which
  cannot tell it from an authorization server and does not need to.

With no party above the holders, the decision cannot be put anywhere without
privileging the place it is put. The tally is that place, and the rest of Part
II is what makes it unable to lie rather than trusted.

## The Mandate {#mandate}

The tally MUST publish, for each jointly held resource, a mandate carrying:

resources:
: REQUIRED. At least one resource identifier or pattern.

holders:
: REQUIRED. At least two, each with `owner`, an `https` `issuer` naming her
  authorization server, and an integer `weight` of at least one. An owner MUST
  NOT appear twice.

rule:
: REQUIRED. `kind` of `all`, `any` or `threshold`, normalised to a numeric
  `threshold`: the total weight for `all`, the lightest holder's weight for
  `any`, and a stated value between one and the total for `threshold`.

A holder's authorization server MUST store the mandate she agreed to, MUST
re-ask her when the published mandate differs from it in holders, threshold or
resources, and MUST refuse to count a holder who has written no terms over the
resource.

A deployment MAY fix a floor below which no mandate's threshold may go. The
interesting real-world version of this is not a group choosing its own quorum;
it is a regulator or an account agreement fixing one, and a floor set from
outside answers the question a self-chosen quorum cannot.

Authoring a mandate is where "who decides who decides" lives, and this document
leaves it to configuration.

## The Fold {#fold}

When a requesting agent presents a ticket for a jointly held resource, the tally
MUST obtain each holder's terms over it from her authorization server and MUST
fold them into one terms document: the shortest expiry, the intersection of
scopes, the union of prohibitions, and ask-me if any holder asks. It proffers
that document under {{U4ATerms}}, and the agent signs it once.

The fold is the clamp of {{envelope}} applied sideways: each holder's terms are
a ceiling on the running document. An implementation SHOULD use one
implementation of the narrowing for both, since two would be two chances to
disagree about what "narrower" means in the two places where disagreeing is
worst.

## Verdicts {#verdict}

Each holder's authorization server, asked by the tally about one negotiation,
MUST answer with a verdict: a JWS {{RFC7515}} signed by that server with a `typ`
of `u4a-verdict+jwt`, carrying:

holder:
: REQUIRED. The holder.

account:
: REQUIRED. The jointly held resource.

negotiation:
: REQUIRED. The negotiation identifier this verdict answers.

contract:
: REQUIRED. The digest of the agreement the agent signed, as {{U4ATerms}}.

effect:
: REQUIRED. `allow` or `refuse`.

because:
: OPTIONAL. Reasons, for a refusal.

exp:
: REQUIRED. Short.

A verdict is bound to one negotiation and one agreement so that it cannot carry
a later request. Before answering `allow`, a holder's authorization server MUST
compare the folded document the agent signed against the terms she published,
and MUST refuse on any difference in the direction of *more*: a longer expiry,
an extra scope, a dropped prohibition. Differences in the direction of *less*
are expected, since another holder's terms were folded in. This is what lets the
folding party be untrusted.

~~~ json
{
  "iss": "https://alice-as.example",
  "holder": "alice",
  "account": "joint-brokerage-1",
  "negotiation": "fam_8f3aQ2Xc",
  "resource_id": "joint-brokerage-1/get_positions",
  "contract": "s256:mNTA0Zjg1YTBkYzQxZWY4YjkyMWM4ZGIy",
  "effect": "allow",
  "iat": 1789430000,
  "exp": 1789430300
}
~~~
{: title="A verdict's claims."}

Where the holder's policy asks her, the verdict is withheld until she answers,
and the tally holds the negotiation pending as {{UMAGrant}} `request_submitted`.

## Verdicts Are Not Claims {#not-claims}

A verdict MUST travel from the holder's authorization server to the tally. It
MUST NOT be gathered by the requesting agent and presented as a claim.

A claim the requesting party gathers is a claim it can decline to gather. A
holder's refusal has to reach the decision point without the cooperation of the
party it refuses, and claims-gathering cannot carry it. The general boundary:
claims work when the requesting party is the only one who holds the fact, and
fail when the fact may be adverse to it.

## The Count {#count}

The tally MUST sum the weight of holders whose verdict is `allow` and compare it
to the threshold. It MUST refuse the moment the weight still outstanding cannot
carry the request over the threshold — under `all`, the first refusal ends it —
rather than waiting for every holder. Silence and unreachability MUST both fail
closed; only the record distinguishes them.

## The Grant Carries the Verdicts {#joint-grant}

A grant the tally issues MUST carry a `joint` claim with:

account:
: REQUIRED. The jointly held resource.

mandate:
: REQUIRED. The mandate as the tally holds it.

verdicts:
: REQUIRED. Every verdict received, as issued.

tally:
: OPTIONAL. The tally's own count, for display.

~~~ json
{
  "joint": {
    "account": "joint-brokerage-1",
    "mandate": {
      "holders": [
        {"owner": "alice", "issuer": "https://alice-as.example",
         "weight": 1},
        {"owner": "carol", "issuer": "https://carol-as.example",
         "weight": 1}
      ],
      "rule": {"kind": "all", "threshold": 2},
      "resources": ["joint-brokerage-1/*"]
    },
    "verdicts": ["eyJ0eXAiOiJ1NGEtdmVyZGljdCtqd3Qi...",
                 "eyJ0eXAiOiJ1NGEtdmVyZGljdCtqd3Qi..."],
    "tally": {"effect": "allow", "for": 2, "threshold": 2}
  }
}
~~~
{: title="The joint claim on a grant."}

## Re-Verification at the Enforcement Point {#reverify}

An enforcement point protecting a jointly held resource MUST, before allowing a
call under such a grant:

1. fetch the mandate from where the tally publishes it, and MUST NOT use the
   copy embedded in the grant;
2. verify each verdict against the keys published by the issuer the *published*
   mandate names for that holder;
3. establish that each verdict names this negotiation and this agreement;
4. re-run the count of {{count}} and refuse unless it allows.

The `tally` member of the grant is for display and MUST NOT be trusted.

Reading the mandate from the grant would let the party being checked supply the
standard it is checked against: a single genuine verdict beside a rewritten
threshold would pass with every signature verifying. Carrying the verdicts in
the grant and re-verifying them at the resource is what makes the tally an
ordinary service rather than a ledger — there is no ordered history here to
agree on and no long-lived state a fork could damage.

## No Organization Reaches a Jointly Held Resource {#no-org-joint}

A charter claim MUST NOT match a jointly held resource, and a holder's
authorization server MUST refuse to apply an organization's envelope or decision
to one regardless. A jointly held resource MUST NOT share a policy unit with any
other resource, since a ceiling applies to a whole unit once it reaches any
resource in it.

Peers compose horizontally; an authority above them clamps vertically. The two
are orthogonal rather than rival, and this document keeps them apart.

# Security Considerations

## A Layer Above May Only Narrow

See {{envelope}} and {{decision}}. The one-directionality of every envelope
field and of the decision's effect on the member's own result is the property
the whole of Part I rests on. An implementation SHOULD be able to demonstrate
over its full envelope that no combination of envelope and terms produces wider
terms than it started with.

## Reach Stops at the Claim

See {{org-visibility}} and {{org-acting}}. Everything the organization can see
or do stops at the resources its charter claims, and the scoping is applied by
the member's authorization server before it answers. An organization given a
member's whole record because it is easier has been given her relationships
with parties that have nothing to do with it.

## An Administrator's Decision Is Not the Owner's

See {{org-acting}}. "The owner personally approved" may relax a rule under
{{U4APolicy}}; a decision taken for her must not produce that fact.

## The Mandate Is Read Where It Is Published

See {{reverify}}. This is the single check that makes the tally untrusted.

## Silence Is Not Consent

See {{count}}. A holder who has not answered and a holder who cannot be reached
both count for nothing.

## Break-Glass Is Loud

See {{break-glass}}. An emergency path that can be exercised quietly is an
ordinary path with a better name.

# Privacy Considerations

## Members Are Not Visible to Each Other

Under Part I, an organization's view of one member is filtered to claimed
resources and says nothing about any other member. Under Part II, a holder's
authorization server MUST NOT expose another holder's pending queue, decisions
or record; each holder sees her own verdicts and the count.

## The Ceiling Is Disclosed to the Agent

{{envelope}} requires that a terms document state when a layer above the owner
is in force. That discloses to the requesting side that the owner is a member
of some organization, which is a fact about her. The alternative — a ceiling
applied invisibly — asks the agent to sign terms that are not the terms it will
be held to, and this document prefers the disclosure.

# IANA Considerations

## Media Type Registration

IANA is asked to register `application/u4a-verdict+jwt`,
`application/u4a-membership+jwt`, `application/u4a-org-notice+jwt` and
`application/u4a-org-admin+jwt` in the "Media Types" registry, each with:

Required parameters:
: N/A

Optional parameters:
: N/A

Encoding considerations:
: binary; a JWT in compact serialization

Security considerations:
: See {{security-considerations}} of this document

Interoperability considerations:
: N/A

Applications that use this media type:
: Applications implementing UMA 2.0 with this extension

Change controller:
: IETF

and with the following published specifications: {{verdict}} for
`u4a-verdict+jwt`; {{enrolment}} for `u4a-membership+jwt` and
`u4a-org-notice+jwt`; {{org-acting}} for `u4a-org-admin+jwt`.

## JSON Web Token Claims Registration

IANA is asked to register the following in the "JSON Web Token Claims" registry
established by {{RFC7519}}.

Claim Name:
: `joint`

Claim Description:
: The mandate and verdicts under which a jointly held resource was released

Change Controller:
: IETF

Specification Document(s):
: {{joint-grant}} of this document

Claim Name:
: `break_glass`

Claim Description:
: That a grant was issued by an organization under its emergency clause, and
  the justification

Change Controller:
: IETF

Specification Document(s):
: {{break-glass}} of this document

--- back

# Implementation Status {#implementation-status}

This section records the status of known implementations in the sense of
{{?RFC7942}}, and is to be removed before publication as an RFC.

The reference implementation {{U4ALAB}} implements both parts. The clamp of
{{envelope}} is tested exhaustively for one-directionality over every
combination of envelope field and terms. The fold, the mandate validator and the
count are tested in isolation; the full arrangement — two holders on two
authorization servers, a tally, and an enforcement point re-verifying against
the published mandate — runs end to end, including refusal of a grant whose
embedded mandate rewrites who was entitled to be counted. Part I runs end to end
including enrolment by invitation, the ceiling appearing in signed terms,
`first-party-only` refusing a third party's agent, the organization's scoped
view, administrator decisions not counting as the member's, break-glass, and
leaving.

# Acknowledgments
{:numbered="false"}

{{PP2PI}} supplied the four states of co-administration that Part I answers and
the observation, made in {{UMAGrant}}'s own terminology, that the resource
rights administrator had been named and never mechanised. The metadata of
{{RFC9728}} is what lets one resource server name a different authority for a
shared, a personal and a jointly held resource at three paths.
