---
templateKey: doc
seoTitle: "Resource owner, requesting party, requesting agent: who decides"
title: The three parties
description: Owner, requesting party, requesting agent — and what it costs to treat the last two as one.
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

OAuth has two parties on the requesting side: a resource owner and a client. UMA
2.0 added a third, the requesting party, because the person asking might not be
the person who owns the resource. Agents make a fourth distinction do real work.

## Who is who

The **owner** owns the resource and is the only party whose permission decides
anything. She is not present.

The **requesting party** is the human or organisation on whose behalf the
request is made. Bob, the advisor. He is accountable for what his agent agrees
to, and he is also not present at the moment the request happens.

The **requesting agent** is the software making the call. It holds a key, signs
requests, accepts terms, and acts continuously without anyone watching.

## Why the last two came apart

UMA's 2010 drafts had both terms. UMA 2.0 collapsed them into "requesting
party", which was reasonable at the time: the client was a web app that Bob was
sitting in front of, so the party and the software were in the same room and the
same session.

That is no longer true, and three things now attach to the agent rather than to
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
