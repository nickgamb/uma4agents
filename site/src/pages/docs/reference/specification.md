---
templateKey: doc
title: The specification set
seoTitle: "UMA 2.0 for Agents — the specification set"
description: The nine Internet-Drafts that specify UMA 2.0 for agents — what each covers, their identifying URIs, and how to build them.
next:
  - title: Deviations from UMA 2.0
    to: /docs/reference/deviations/
    blurb: The register the drafts are numbered from, with the reasoning for each.
  - title: Findings
    to: /docs/reference/findings/
    blurb: The recommendations the drafts answer.
---

Nine Internet-Drafts specify this profile. Three are required and together
constitute it, four are optional extensions, and two are bindings.

Each document has an identifying URI. An authorization server lists the ones it
implements in its `uma_profiles_supported` metadata, as UMA 2.0 Grant §4 asks.
A binding is listed where it places obligations on the authorization server:
the AAuth binding does, and the MCP binding, which governs only how a challenge
travels between agent and resource, does not.

| Draft | Title | In the set | URI |
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

They are drafts, and comment on them is wanted. Open an issue on
[the repository](https://github.com/nickgamb/uma4agents/issues), or read
[the findings](/docs/reference/findings/) for the recommendations behind each.

**Terminology.** These pages say *tier* where the drafts say *policy unit*.
Same object: a group of resources with one terms document, one ask-me switch,
and its rules.

## What each document covers

**Core** — the grant. The challenge as a set of parameters rather than an HTTP
header; two identity levels for the client; a proof-of-possession
token carrying its permissions as a claim; operation binding and single use;
the order an enforcement point runs its checks in; the standing connection;
the owner's credential to her own server; and which artifacts carry an owner.
Its §12 is the extension register the
[deviations page](/docs/reference/deviations/) follows.

**Owner-Proffered Terms** — claims-gathering in which the authorization server
proffers the claim's content. The terms document and its three
representations, version immutability, the signed agreement, what the
requesting side may author in it, the counter-signed receipt, and declining.
Usable by any UMA deployment, agents or not.

**Federated Authorization for Agents** — declarative registration; discovery
split into a public structural layer and a protected instance layer;
resource-server establishment by a signature from the origin it serves; and
the reason an introspection response gives for an inactive token.

**Owner Policy, Assurance and Attention** — which conditions may relax a
requirement and which may only tighten, enforced when a policy is saved;
three assurance axes with no composite score; a depth limit on the owner's
pending queue, in two lanes; operator blocking; and what her record carries.

**Agent Lineage** — one agent introducing another. The introduction document
and the RFC 8693 `act` alternative, the six admission checks, approval pooled
across a lineage, the fan-out ceiling, and the revocation cascade.

**Multi-Party Authorization** — Part I, an organization above the owner: its
charter, the envelope clamped into her terms, roles carrying `delegation`, and
break-glass. Part II, owners of equal standing: a published mandate, a signed
verdict from each owner's authority, and a tally that carries them in the
grant.

**The Resource Owner's API** — the surface her portal, a command line or an
agent she runs uses to operate her authorization server: the queue and its
decisions, her connections and the operators behind them, her resource
servers, her policy and terms, the condition vocabulary, the record, and an
event stream.

**MCP binding** — the challenge in both hosting shapes, the three discovery
channels, reconciling MCP's routing headers against the body, origin
validation, and truncated bodies.

**AAuth binding** — AAuth's agent credential as the identified-agent
credential, its signature conventions as proof of possession, its
authorization token as the grant, and its resource metadata as a second
encoding of the same structural facts.

## Requirements and checks

[`spec/conformance.yaml`](https://github.com/nickgamb/uma4agents/blob/main/spec/conformance.yaml)
maps every normative statement in the set to what verifies it: a make target
and the assertion that target prints, or a note that the requirement falls on
a deployment or on a binding rather than on this implementation.

`make spec-check` fails the build if a statement has no row, a row quotes text
that is no longer in the draft, a row names a make target that does not exist,
or a row cites an assertion that no suite prints.

## Building them

```bash
make spec
```

Renders `spec/src/*.md` through kramdown-rfc and xml2rfc in a container, into
`site/static/spec/`. The bibliographic reference cache is committed, so the
render needs no network.
