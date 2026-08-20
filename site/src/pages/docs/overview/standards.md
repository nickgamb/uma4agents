---
templateKey: doc
seoTitle: "Standards for agent authorization: UMA 2.0, RFC 9421, RFC 9728, MCP"
title: Standards this composes
description: Every specification U4A builds on, what each one supplies, and where it appears in the flow.
diagram: standards-map
diagramCaption: Almost nothing here is invented. Step through to see what each layer supplies.
next:
  - title: Compared to UMA 2.0
    to: /docs/overview/compare-uma/
    blurb: What the profile keeps and changes from its base.
  - title: Wire contract
    to: /docs/reference/wire-contract/
    blurb: Where each of these shows up on the wire.
---

Almost nothing here is invented. The profile is mostly composition — existing
specifications, each doing the job it was designed for, arranged so the owner
ends up holding the authority.

This page is the full list, so you can see what you would be adopting.

## The base

| Specification | Supplies | Where it appears |
|---|---|---|
| [UMA 2.0 Grant](https://docs.kantarainitiative.org/uma/wg/rec-oauth-uma-grant-2.0.html) | The grant type, the permission ticket, claims-gathering | [All four beats](/docs/overview/four-beats/) |
| [Federated Authorization for UMA 2.0](https://docs.kantarainitiative.org/uma/wg/rec-oauth-uma-federated-authz-2.0.html) | The party split, the protection API, the PAT | [Architecture](/docs/overview/architecture/) |
| [OAuth 2.0](https://www.rfc-editor.org/rfc/rfc6749.html) | The token endpoint and the credential shapes UMA extends | Beats 2 and 3 |
| [OpenID Connect](https://openid.net/specs/openid-connect-core-1_0.html) | How the owner authenticates to her own authority | Owner approval path |

## What makes the grant hold

| Specification | Supplies | Where it appears |
|---|---|---|
| [RFC 9728](https://www.rfc-editor.org/rfc/rfc9728.html) — Protected Resource Metadata | The public half of discovery, and the array that lets a resource name its authorization servers | [Beat 0](/docs/overview/discovery/) |
| [RFC 9421](https://www.rfc-editor.org/rfc/rfc9421.html) — HTTP Message Signatures | Proof-of-possession on every request, in both directions | [Beat 4](/docs/overview/proof-of-possession/), and the protected discovery endpoint |
| [RFC 7638](https://www.rfc-editor.org/rfc/rfc7638.html) — JWK Thumbprint | The stable name for a pseudonymous agent, which becomes its connection handle | [Parties](/docs/overview/parties/) |
| [RFC 9396](https://www.rfc-editor.org/rfc/rfc9396.html) — Rich Authorization Requests | The structure the challenge uses to say what is being asked for | [Beat 1](/docs/overview/four-beats/) |

## What makes it about a person

| Specification | Supplies | Where it appears |
|---|---|---|
| [IEEE 7012-2025](https://standards.ieee.org/ieee/7012/7192/) — Machine Readable Personal Privacy Terms | The pattern where the individual proffers terms and the counterparty agrees | [Terms](/docs/overview/terms/) |

This is the one that changes the character of the thing. Without it the profile
is a well-bound token; with it, the owner is stating requirements rather than a
service offering conditions.

## Agent identity

| Specification | Supplies | Where it appears |
|---|---|---|
| [AAuth](https://github.com/dickhardt/AAuth) | Verifiable agent identity, bound to a session key | The identified path |
| Web Bot Auth | A directory where an operator publishes its agents' keys | Display and discovery only |
| Client ID Metadata Documents | A client described by URL rather than pre-registration | Display only |

All three are consumed as inputs. None becomes an authorization input — see
[identity is not authorization](/docs/overview/identity/).

## The binding

| Specification | Supplies | Where it appears |
|---|---|---|
| [Model Context Protocol](https://modelcontextprotocol.io) 2026-07-28 | The tool surface the agent actually calls | [MCP binding](/docs/reference/mcp-binding/) |

MCP is one binding, not a requirement. The four beats are transport-independent
by design, and the same challenge payload rides a JSON-RPC envelope byte for
byte.

## What is original

Three things, and each is written up as a
[finding](/docs/reference/findings/) rather than asserted here:

- **operation binding** — a grant tied to one act with one set of parameters
- **indivisible single-use** — the store interface that makes "once" survive
  replication
- **the terms-in-grant composition** — IEEE 7012 terms carried as the claim that
  satisfies a UMA claims-gathering demand

Everything else on this page already existed. The contribution is the
arrangement.

## Licensing and IPR

UMA 2.0 and FedAuthz are published by the Kantara Initiative under its IPR
Policy, option "Reciprocal Royalty Free with Opt-Out to RAND". Article 4.1(a)
of that policy grants a royalty-free patent licence to any person or entity
implementing the specification, to the extent needed for a fully compliant
implementation. Article 3's copyright licence to prepare derivative works runs
between Kantara Participants, and covers the specification documents rather
than the protocol they describe. This profile reproduces no specification
text, so the copyright grant is not engaged.

Section 4 of the grant specification asks that a profile or extension be given
a uniquely identifying URI, and that an authorization server supporting one
advertise that URI in its `uma_profiles_supported` metadata. U4A does not do
this yet. What such a URI would name is already written down, in the
[deviations register](/docs/reference/deviations/).

The RFCs above are cited under the IETF Trust Legal Provisions. IEEE 7012 is
cited by section and is not redistributed here. Full attribution for every
specification and component, with versions, is in
[NOTICE](https://github.com/nickgamb/uma4agents/blob/main/NOTICE).

"UMA" and "User-Managed Access" originate with Kantara's UMA Work Group. This
is an independent implementation and not a Kantara product.
