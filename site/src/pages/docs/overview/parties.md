---
templateKey: doc
seoTitle: "Resource owner, requesting party, client: who decides"
title: The three parties
description: Owner, requesting party, client — and what it costs to treat an agent and the party behind it as one.
diagram: who-answers
diagramCaption: Three parties, one question. Only one of them has standing to answer it.
next:
  - title: Terms as first-class
    to: /docs/overview/terms/
    blurb: What the owner requires, made into an artifact.
  - title: Identity is not authorization
    to: /docs/overview/identity/
    blurb: Which of the three the identity layer describes.
---

UMA 2.0 has three entities in a sharing arrangement: the resource owner, the
requesting party on whose behalf access is sought, and the client — the software
that makes the request. When the client is an autonomous agent, the difference
between the requesting party and the client does real work.

## Who is who

The **owner** owns the resource and is the only party whose permission decides
anything. She is not present.

The **requesting party** is the human or organisation on whose behalf the
request is made. Bob, the advisor. He is accountable for what his agent agrees
to, and he is also not present at the moment the request happens.

The **client** is the software making the call. In this profile it is usually an
autonomous agent: it holds a key, signs requests, accepts terms, and acts
continuously without anyone watching.

UMA's legal work names the parties responsible for these entities. The
**Requesting Agent** is the party that seeks access through a client, and the
**Client Operator** is the party responsible for the client software. The
profile uses those names for parties, never for software.

## Why the requesting party and the client come apart

In most UMA 2.0 deployments the client was a web app that Bob was sitting in
front of, so the party and the software shared a session, and treating them as
one rarely mattered.

An agent changes that, and three things now attach to the client rather than to
Bob:

- **The signature.** Terms are signed by the agent's key, not by Bob.
- **The attested identity.** Whatever identity layer is in play describes the
  agent — its issuer, its subject, its key.
- **The revocation.** The owner revokes an agent, not a person. Bob may have
  several, and she may want one gone.

What stays with Bob is accountability. If his agent agreed to something, he
agreed to it. Nothing in the protocol lets the agent be the responsible party;
it lets the agent be the *acting* one.

## What it costs to collapse them

If you model only "requesting party", you end up with one of two problems.

Treat the agent as the party, and you lose the human who is accountable — the
audit trail says a key did something, and nobody can say on whose behalf.

Treat the human as the party, and every agent Bob runs shares one relationship.
Revoking one revokes all of them, and the owner cannot tell which piece of
software did what. She approved *Bob*, and Bob is now plural.

Keeping them separate costs one extra concept and buys a connection that can be
revoked precisely, an audit trail that names both, and terms whose signature
belongs to something that actually signed them.

## How the lab expresses it

A **connection** is the standing relationship between one owner and one agent.
Its handle comes from the agent's identity: for a pseudonymous agent, the
thumbprint of its key; for an identified one, its issuer and subject.

Bob appears in the display metadata — who operates this agent, where its keys
are published — and never as an authorization input. The verifying key is always
the one named in the grant.

That division is why an agent she has never met
[pends on first contact](/docs/overview/revocation/) whatever Bob's standing
with her already is. She is meeting a new actor, not a new person.
