---
templateKey: doc
title: FAQ
description: The questions that come up first, answered directly, including the ones where the answer is that this does not do that.
next:
  - title: Compare against UMA 2.0
    to: /docs/overview/compare-uma/
    blurb: What this profile keeps, changes, and adds.
  - title: Run the lab
    to: /docs/guides/run-the-lab/
    blurb: Decide for yourself whether it works.
---

## Is this a specification?

No. It is a working profile with a
[list of recommendations](/docs/reference/findings/) for the people who write
the specifications. The code exists so the recommendations are backed by
something that runs rather than by argument.

## Do I have to use UMA to use these ideas?

No. The [guides](/docs/guides/roles/) name each role before naming any product
or protocol, and several of the primitives stand alone — operation-bound grants
and indivisible single-use are useful whatever issues your tokens. UMA is the
part that gives the owner an authority of her own, which is hard to reproduce
without something shaped like it.

## Does this replace my policy engine?

No, and the two compose. A policy engine decides; this profile is about whose
policy the decision expresses. You will probably want an engine *inside* the
authorization server described here. See
[Policy engines](/docs/overview/compare-policy-engines/).

## Do I need solo.io, Istio, or Kubernetes?

None of them. The lab uses agentgateway, kgateway and Istio ambient because
they filled the roles cleanly and are worth showing, but every guide states the
role first and the product second. The compose stack runs the same code with
none of that, and the same enforcement core also runs embedded in the resource
with no gateway at all.

## Does the owner have to be online?

That is the case the design exists for. Her policy answers the ordinary requests
while she is asleep. Requests on an ask-me tier are held — the negotiation
survives the authorization server being deleted and the database failing over,
which `make k8s-chaos` demonstrates by doing both mid-request.

## What happens the first time an agent she has never seen arrives?

It pends, whatever the tier. First contact is a decision about the relationship
rather than about the request, so she is asked once. After that her existing
terms cover it, and she is only asked again for operations her policy says she
must approve personally.

## How many agents can this handle?

Connections are stored one row per agent with no ceiling, and her policy names
tools rather than agents, so an agent she has never seen is not a gap in her
configuration. Each gets its own approval, terms, ledger trail and revocation.

## Is the agent identity part required?

No. An agent can be pseudonymous, in which case it *is* its key and that key's
thumbprint is the connection handle. Identity buys continuity across key
rotation and something true to display to the owner. It never becomes an
authorization input — the verifying key is always the one named in the grant.

## Can I use this in production?

Not as it stands, and the repository says so in several places. It ships fixed
development credentials, one authorization server per resource server, and no
signing-key rotation. What it is for is deciding whether the shape is right
before you build your own.

## Who is behind it?

A collaboration between [Nick Gamb](https://www.linkedin.com/in/nickgamb/) and
[Eve Maler](https://www.linkedin.com/in/evemaler/), who co-authored the UMA
specifications. Apache-2.0, and the
[repository](https://github.com/nickgamb/uma4agents) is the whole of it.
