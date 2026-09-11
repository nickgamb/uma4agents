---
templateKey: doc
title: The specification set
seoTitle: "UMA 2.0 for Agents — the specification set"
description: Nine Internet-Drafts profiling and extending UMA 2.0 for autonomous agents, written from this lab, with every requirement mapped to the check that proves it.
next:
  - title: Deviations from UMA 2.0
    to: /docs/reference/deviations/
    blurb: The register the drafts are numbered from, with the reasoning for each.
  - title: Findings
    to: /docs/reference/findings/
    blurb: The recommendations the drafts answer.
---

What this lab found is written as a set of Internet-Drafts. Three are required
to implement together and constitute the profile; four are optional
extensions; two are bindings, one to a transport and one to an agent identity
layer. Each has an identifying
URI, and the authorization server advertises the ones it implements in
`uma_profiles_supported`, as UMA 2.0 Grant §4 asks.

| Draft | Title | Status in the set | URI |
|---|---|---|---|
| [core](/spec/draft-gamb-uma4agents-core-00.html) ([txt](/spec/draft-gamb-uma4agents-core-00.txt)) | User-Managed Access (UMA) 2.0 Profile for Autonomous Agents | **Required** | `https://u4a.ai/spec/core/1.0` |
| [terms](/spec/draft-gamb-uma4agents-terms-00.html) ([txt](/spec/draft-gamb-uma4agents-terms-00.txt)) | Owner-Proffered Terms for UMA 2.0 | **Required** | `https://u4a.ai/spec/terms/1.0` |
| [fedauthz](/spec/draft-gamb-uma4agents-fedauthz-00.html) ([txt](/spec/draft-gamb-uma4agents-fedauthz-00.txt)) | Federated Authorization for Autonomous Agents | **Required** | `https://u4a.ai/spec/fedauthz/1.0` |
| [policy](/spec/draft-gamb-uma4agents-policy-00.html) ([txt](/spec/draft-gamb-uma4agents-policy-00.txt)) | Owner Policy, Assurance and Attention | Optional | `https://u4a.ai/spec/policy/1.0` |
| [lineage](/spec/draft-gamb-uma4agents-lineage-00.html) ([txt](/spec/draft-gamb-uma4agents-lineage-00.txt)) | Agent Lineage | Optional | `https://u4a.ai/spec/lineage/1.0` |
| [multiparty](/spec/draft-gamb-uma4agents-multiparty-00.html) ([txt](/spec/draft-gamb-uma4agents-multiparty-00.txt)) | Multi-Party Authorization | Optional | `https://u4a.ai/spec/multiparty/1.0` |
| [owner](/spec/draft-gamb-uma4agents-owner-00.html) ([txt](/spec/draft-gamb-uma4agents-owner-00.txt)) | The Resource Owner's API | Optional | `https://u4a.ai/spec/owner/1.0` |
| [mcp](/spec/draft-gamb-uma4agents-mcp-00.html) ([txt](/spec/draft-gamb-uma4agents-mcp-00.txt)) | Model Context Protocol Binding | Binding | `https://u4a.ai/spec/mcp/1.0` |
| [aauth](/spec/draft-gamb-uma4agents-aauth-00.html) ([txt](/spec/draft-gamb-uma4agents-aauth-00.txt)) | AAuth Binding | Binding | `https://u4a.ai/spec/aauth/1.0` |

The drafts are in Internet-Draft form. Whether they go to the datatracker is a
separate decision, and nothing in them depends on it.

One term differs between the drafts and these pages. What the lab and every
page here calls a **tier** — a group of resources with one terms document,
one ask-me switch and its rules — the drafts call a **policy unit**, so that
the word carries no suggestion of rank. They are the same object.

## What each one carries

**Core** narrows UMA 2.0 in one place and extends it in several: the challenge
is a set of parameters rather than a header, so an enforcement point with no
status line can emit it; the requesting agent is a key it proves possession
of, at one of two identity levels; the requesting party token is
proof-of-possession and carries its permissions as a claim; a grant may be
bound to one operation and spent once; enforcement has a normative order and
single use must survive replication; the owner holds a standing, revocable
relationship with each agent; and every owner-scoped artifact carries its
owner. Its §11 is the register the [deviations page](/docs/reference/deviations/)
is numbered from.

**Owner-Proffered Terms** transforms claims-gathering: the authorization server
proffers the content of the claim it requires, at a persistent URI in three
representations, and the grant returns a counter-signed receipt embedding the
signed agreement. Adoptable by any UMA deployment, agents or not.

**Federated Authorization for Agents** makes registration declarative, splits
discovery into a public structural layer and a protected instance layer, lets a
resource server establish itself with an owner's authority by signing as its
own origin, and gives introspection a reason.

**Owner Policy, Assurance and Attention** states the asymmetry — evidence from
the requesting side may only tighten; only the owner's own decisions may relax
— and enforces it where policy is stored. Assurance is three axes with no
composite; the pending queue has a depth limit in two lanes; the owner's record
names the counterparty on every row it honestly can.

**Agent Lineage** lets an agent introduce a sibling that skips first contact
and then negotiates its own grant. Nothing is handed down; depth is one by an
explicit check; revocation cascades.

**Multi-Party Authorization** answers the two ways one-deciding-party fails: a
layer above the owner that may only narrow, and owners of equal standing whose
signed verdicts travel in the grant and are re-verified at the enforcement
point.

**The Owner's API** is the surface through which her portal, a command line or
her own agent operate her authorization server: the queue and its decisions,
her relationships with agents, operators and resource servers, her policy and
terms, and the record. Left to the deployment by UMA 2.0; specified here so
that software she runs can act for her against any conforming server.

**The AAuth binding** makes AAuth's agent credential the identified-agent
credential, its signature conventions the proof of possession, its
authorization token the grant, and its resource metadata a second encoding of
the same structural facts.

**The MCP binding** says how the challenge parameters travel over MCP in both
hosting shapes, how a client discovers before its first call that it must
negotiate, and what an enforcement point reading MCP's routing headers must do
to avoid being steered.

## Every requirement, and its check

`make spec-check` reads the rendered drafts and the register in
`spec/conformance.yaml`, and fails unless every normative statement in the set
has a register row, every row names a check that exists, and every check named
is run by a suite. The register itself is the honest map of what the reference
implementation proves: a requirement on a *deployment* — an issuer allow-list,
an egress policy — is marked as one rather than claimed.

## Building them

```bash
make spec
```

renders `spec/src/*.md` through kramdown-rfc and xml2rfc in a container, into
`site/static/spec/`. The reference cache is committed, so a render reaches no
network.
