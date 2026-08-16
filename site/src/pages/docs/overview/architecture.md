---
templateKey: doc
title: Architecture
description: Which party holds which responsibility, and why the boundaries between them are the design.
diagram: trust-boundary
diagramCaption: The seam the profile exists to hold. Meridian enforces a policy it is refused permission to read.
next:
  - title: Concepts
    to: /docs/overview/concepts/
    blurb: The vocabulary the rest of the docs uses.
  - title: The roles you must fill
    to: /docs/guides/roles/
    blurb: What you need in your own stack, before any product names.
---

Four parties, and the boundaries between them are the point. Each is a separate
trust domain because in the case this profile exists for, they are genuinely
separate — different organisations, different operators, different lawyers.

## The owner's side

The **authorization server** holds Alice's policy and answers on her behalf. It
dictates terms, decides tiers, issues grants, records connections, and keeps the
ledger. It is the only component that speaks for her.

Her **surface** is where she writes terms, sees what has been asked, and
revokes. In the lab that is a portal she signs in to, with her **identity
provider** as the source of the token her authorization server checks when she
approves something. It can equally be a personal AI holding her key, which
authenticates with a signature instead of a login — the authority accepts
either, or both, and neither is a fallback for the other.

Either way the surface holds no authority of its own. It does not decide and it
does not keep a record; it reaches the one thing that does, and a decision made
through either surface lands in the same ledger.

See [Put the authority on her device](/docs/guides/personal-authority/) for what
a surface actually has to provide.

## The resource server's side

The **resource** is the thing being protected. In the lab it is a brokerage
vault exposed as an MCP server, and it contains no authorization code at all.

The **enforcement point** is what refuses. It challenges unauthorized calls,
verifies proof-of-possession, checks that a grant covers the tool being called,
and burns single-use grants. It performs those obligations *for* an authority it
does not hold: it enforces Alice's policy and must not be able to read or
rewrite it.

That separation is the one worth testing. In the deployed shape a service mesh
enforces it rather than a document asserting it, and the suite proves it with a
pair of assertions on the same port and the same workload — the enforcement
point is refused Alice's policy, and allowed her published keys.

## The requesting side

The **requesting party** is the human or organisation asking — Bob, the advisor.
The **requesting agent** is the software doing the asking. Keeping them distinct
matters: the terms are signed by the agent, the identity attested is the
agent's, and the party who is accountable is Bob.

An agent may be **pseudonymous**, in which case it is its key and the connection
is handled by that key's thumbprint, or **identified** through an agent identity
protocol, in which case its continuity survives key rotation.

## Two planes

The **grant plane** is the negotiation: challenge, terms, agreement, grant. It is
binding-independent — the same four beats carry over MCP, over HTTP, or over
anything else that can return a challenge and carry a token.

The **data plane** is the authorized call. This is where the enforcement point
verifies the signature, checks the operation binding, and spends the grant.

Keeping them apart is what lets one enforcement core run in two places. The lab
ships it as a gateway callout and embedded in the resource, and `make
embedded-check` proves the two reach identical verdicts from the same
implementation.

## What is deliberately absent

No shared secret between the resource server and the authorization server. No
static owner credential. No path by which the resource server can read the
owner's policy. Those absences are the architecture; the rest is arrangement.
