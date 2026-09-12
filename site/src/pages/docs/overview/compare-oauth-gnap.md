---
templateKey: doc
seoTitle: "OAuth 2.0, CIBA and GNAP for AI agent authorization: what each leaves open"
title: Compared to OAuth 2.0 and GNAP
description: OAuth, CIBA-style asynchronous authorization and GNAP can all carry a negotiation. None of them, on its own, puts the deciding party anywhere but the service.
next:
  - title: Compared to policy engines
    to: /docs/overview/compare-policy-engines/
    blurb: The other thing people already run.
  - title: Proof-of-possession
    to: /docs/overview/proof-of-possession/
    blurb: The mechanism both of these can supply.
---

If you already run OAuth, most of this profile will look familiar, because UMA
is built on OAuth and inherits its endpoints and its vocabulary. The question
worth answering is what OAuth alone leaves open.

## OAuth 2.0

In OAuth, a resource owner authorises a client to access their own resources.
The flow assumes the owner is present — the redirect goes to their browser,
they see a consent screen, they approve.

Three things follow from that assumption, and all three break here.

**The owner is the one logging in.** OAuth's authorization endpoint is a place
you send a human. If the owner is asleep and the request came from somebody
else's agent, there is nobody to redirect.

**The client belongs to the service.** Client registration is a relationship
between the application and the authorization server, which is usually operated
by the same party as the resource. An agent from an organisation the service has
never heard of has no obvious place in that model.

**Consent is a moment, not a record.** The consent screen is not an artifact
either side keeps. Nothing is signed and nothing is checkable later.

Extensions address parts of this. Rich Authorization Requests give a structured
way to say what is being asked for. DPoP binds tokens to keys. Token exchange
handles delegation between services. Backchannel authentication reaches a person
who is not at the browser. Each is useful and this profile uses ideas from all of
them — but none moves the authority to the owner's side, because that is not what
they were for.

## CIBA and asynchronous authorization

The extension worth its own heading, because it looks like the whole answer and
is half of one.

Client-Initiated Backchannel Authentication decouples the party asking from the
party approving. The client requests, the authorization server pushes to a
person's device out of band, and the client polls until they respond. The
asynchronous-authorization and human-in-the-loop features now shipping in agent
platforms are built on it, and they solve the problem OAuth's redirect could
not: **the human does not have to be in front of the browser that made the
request.**

That is real, and this profile needs the same capability. What CIBA supplies is
a way to *reach* an absent person. What it does not supply is any of the
following:

- **A policy she wrote.** The rule deciding when she is disturbed lives in the
  authorization server, which belongs to the service. She cannot author it,
  read it, or make it stricter.
- **Anything to state.** The push carries a decision request. There is nowhere
  in it for her to proffer terms — a purpose, an expiry, a prohibition — that
  the requester must accept and sign.
- **A relationship.** Each push is an event. Nothing persists that she can see
  listed, and nothing exists to revoke afterwards.
- **A party boundary.** CIBA assumes the approving user is *the authorization
  server's* user. When the person who must decide is a customer of a different
  company from the one operating the agent, the model has no seat for her — it
  has a notification channel and no authority behind it.

So the honest relationship is compositional rather than competitive: a
backchannel push is a good transport for the moment an owner-side authority
decides it must ask her. It is the [approval
path](/docs/guides/approval/), not the thing that decided to use it.

## GNAP

GNAP is the closer comparison, because it was designed with the limitations
above in view. It has a real negotiation: a client makes a request, the server
can say what it still needs, and there are defined ways to involve a party who
is not in the request path.

That is the same shape as UMA's claims-gathering, and GNAP does it more cleanly.
Its interaction model is more general, key binding is native rather than an
extension, and its request format expresses "here is what I want" far better
than a scope string.

GNAP also covers the absent owner. [RFC 9635 §1.6.4](https://www.rfc-editor.org/rfc/rfc9635.html#section-1.6.4)
describes a resource owner who is not the end user, reached by the authorization
server asynchronously while the client polls, and §1.4 expects the server to
follow her decisions, including automated rules.

What GNAP leaves to implementations is **what those rules may rest on, and what
is agreed**. It defines no terms the owner publishes and the requesting side
signs, no record of that agreement held by both parties, and no constraint on
which facts may relax a requirement. It also does not require the authorization
server to belong to a different party from the resource server, and in most
deployments it will not.

Those are the parts this profile specifies, and it is not a criticism of GNAP
to say it leaves them open. A GNAP-based binding of this profile would be a
reasonable thing to build, and probably a cleaner one than the OAuth-shaped
binding here.

## What this profile adds on top of either

Whichever you carry it on:

- an authority on the **owner's** side that the resource server cannot overrule
- **terms** the owner states and the requester signs, with a receipt both keep
- a grant bound to **one operation**, so approving an act is not authorising a
  capability
- a defined answer for **what happens while she is asleep**

The four beats are deliberately binding-independent. They can be carried over
OAuth endpoints, over GNAP, or over a JSON-RPC envelope, which is exactly what
the [MCP binding](/docs/reference/mcp-binding/) does.

## If you already have OAuth

You are most of the way to the transport. What you are missing is the party
model: something that holds the owner's policy and is not operated by the
service holding the data. That is the piece to build or adopt, and everything
else here can be layered onto endpoints you already run.

Sources: [OAuth 2.0](https://www.rfc-editor.org/rfc/rfc6749.html),
[GNAP](https://datatracker.ietf.org/doc/html/rfc9635).
