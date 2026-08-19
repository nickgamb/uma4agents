---
templateKey: doc
title: Glossary
seoTitle: "AI agent authorization glossary: resource owner, requesting party, permission ticket"
description: Terms as this documentation uses them, including the places where a word means something narrower here than it does elsewhere.
next:
  - title: Wire contract
    to: /docs/reference/wire-contract/
    blurb: Where these terms appear on the wire.
---

Where a term comes from a specification, the specification is named. Where this
profile narrows a meaning, the entry says so.

**Agent token** — a credential asserting an agent's identity, issued by an agent
identity provider and bound to a session key. Optional: a
[pseudonymous](#pseudonymous-agent) agent has none.

**Authorization server (AS)** — the party that holds the owner's policy and
answers on her behalf. UMA 2.0 term. In this profile it also dictates terms and
keeps the ledger.

**Beat** — one of the four exchanges in a negotiation: challenge, attempt,
commit, grant. Not a UMA term; used here because the sequence is easier to hold
than the endpoint names.

**Claim token** — what the agent presents to satisfy the authorization server's
demand for information. Here it carries the signed agreement.

**Connection** — a standing relationship between one agent and one owner,
created when she first approves it. Keyed by the agent's identity, so revoking
one touches no other.

**Family** — the identifier that ties every message in one negotiation together,
assigned when the permission ticket is created and stable across rotations. The
correlation id in every event.

**Identified agent** — an agent whose identity is asserted by an issuer rather
than by its key alone. Its continuity survives key rotation, because the
connection is keyed by issuer and subject.

**JWK / JWK thumbprint (jkt)** — a key in JSON form, and the
[RFC 7638](https://www.rfc-editor.org/rfc/rfc7638.html) hash that names it
compactly. A pseudonymous agent's connection handle is its jkt.

**Ledger** — the append-only record of what was promised, approved, denied,
touched and revoked. A projection over the event stream, not a separate store.

**MCP (Model Context Protocol)** — the protocol the lab uses to expose the
resource as tools an agent can call. One binding of the grant, not a
requirement of it; the four beats are binding-independent.

**need_info** — the authorization server's answer when it wants something before
it will decide. Carries the terms it requires. UMA 2.0 term.

**Operation binding** — a grant tied to one operation and one set of parameters,
so approving a specific trade does not authorise trading.

**Owner / resource owner (RO)** — the party whose resource is being reached, and
the only party whose permission the profile treats as decisive. `resource owner`
in UMA 2.0 and OAuth 2.0; these docs say *owner* in prose and RO where the
abbreviation is doing work, as in **RO ≠ RqP**.

**PAT (protection API token)** — the token a resource server holds to call the
authorization server's protection API. Issued in the owner's name, and
revocable by her.

**Permission ticket** — the opaque handle the enforcement point hands back when
it refuses. Single-use; presenting it starts the negotiation. UMA 2.0 term.

**Proof-of-possession (PoP)** — a token that names a key, where every request
must be signed with that key. The alternative to a bearer token, which anyone
holding it can spend.

**Pseudonymous agent** — an agent with no issued identity, which *is* its key.
The connection handle is the key's [RFC 7638](https://www.rfc-editor.org/rfc/rfc7638.html)
thumbprint.

**Requesting agent** — the software making the request. Distinct from the
requesting party. A 2010-era UMA term, revived here because the distinction has
started to matter again.

**Requesting party (RqP)** — the human or organisation on whose behalf the agent
asks. Accountable; not present at the keyboard. **RO ≠ RqP** is the shorthand
for the case this profile exists for: the party asking is not the party who
owns the thing.

**Resource server (RS)** — the party holding the resource and performing the
enforcement obligations. Does not hold the owner's policy and cannot read it.

**PEP (policy enforcement point)** — the component that actually refuses: it
challenges, verifies proof-of-possession, checks scope and operation binding,
and spends single-use grants. Sits on the resource server's side and holds none
of the owner's policy. Term borrowed from XACML, and in wide use since.

**PDP (policy decision point)** — the component that decides. In this profile
the owner's authorization server is the PDP for her resources, which is the
whole argument: the decision belongs to her side, not to the RS.

**RPT (requesting party token)** — the grant issued at the end of a successful
negotiation. Here it is proof-of-possession rather than bearer, and for
sensitive operations it is also single-use and operation-bound.

**Terms** — the machine-readable statement the authorization server dictates and
the agent signs: purpose, scope, expiry, prohibitions. Follows the
[IEEE 7012](https://standards.ieee.org/ieee/7012/7192/) pattern.

**Tier** — a policy grouping written against resources: which tools it covers,
what terms it dictates, and whether the owner must be asked. Names no agent.

**Waypoint** — a service-mesh proxy that evaluates policy at layer 7. Mesh
terminology rather than UMA; it appears in the deployment pages because a
path-scoped rule is meaningless without one.
