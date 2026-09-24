---
templateKey: doc
title: Issue the challenge
description: Turning a refusal into the start of a negotiation — what the challenge carries, and the check that stops it being redirected.
diagram: rogue-challenge
diagramCaption: The check that stops a refusal from redirecting an agent to an authority the resource never claimed.
next:
  - title: Dictate terms, take an agreement
    to: /docs/guides/terms/
    blurb: What happens when the agent brings the ticket back.
  - title: Discovery, public and protected
    to: /docs/overview/discovery/
    blurb: The metadata the challenge is checked against.
---

Beat one. An agent calls a protected tool without sufficient authorization, and
the enforcement point refuses in a way that tells it what to do about it.

Getting this right is most of the value of the first beat, because a refusal
that does not carry enough information leaves the agent guessing, and a refusal
that carries too much is an oracle.

## Prerequisites

- An [enforcement point](/docs/guides/enforcement-point/) that can control the
  response body
- An authorization server that can register a permission and return a ticket
- A resource that publishes [metadata](/docs/overview/discovery/) naming its
  authorization servers

## 1. Decide what is protected

Deny by default, and name the protected set rather than the open set.

An allow-list of open methods silently admits every method a future protocol
revision invents. MCP's 2026-07-28 revision alone added `tasks/*`,
`server/discover` and `subscriptions/listen`; a deployment that listed what was
closed would have opened all three on upgrade.

In the lab, session bootstrap and discovery pass unauthenticated and only
`tools/call` is protected. Discovery being open is deliberate — an agent should
be able to find out what exists before it is refused for asking.

## 2. Register the attempt

Before returning anything, the enforcement point tells the owner's authorization
server what was attempted, using the protection API and its PAT:

```
POST /perm
{ "resource_id": "alice-vault/execute_trade",
  "resource_scopes": ["trades:execute"] }
```

The authorization server returns a ticket. Two things are worth enforcing here,
on the authorization server's side:

- **reject unknown resources.** A ticket for a resource the authority has never
  heard of is a ticket for nothing.
- **reject excess scopes.** The enforcement point asking for more than the tool
  needs is either a bug or an escalation attempt.

## 3. Return the challenge

The refusal carries four things:

```json
{
  "authorization_details": [{
    "type": "https://u4a.ai/spec/core/1.0#tool-call",
    "locations": ["https://gateway.uma.lab"],
    "identifier": "alice-vault/execute_trade",
    "actions": ["execute_trade"],
    "datatypes": ["trades:execute"]
  }],
  "authorization_reference": "s256:6cR6qTmCj6s0S95MxCfdfwfXJ8myLtBg-PiL8v93H0g",
  "authorization_server": "https://alice-as.uma.lab",
  "ticket": "<ticket>"
}
```

`authorization_details` and `authorization_reference` describe **what** was
refused, in Rich Authorization Requests shape. `authorization_server` and
`ticket` are what make a third-party decision possible: they say **where** to
negotiate and **which** attempt this is.

That pair is the addition worth understanding. The RAR-metadata pattern hands a
client a template to submit to *its own* authorization server. Here the client
must go to somebody else's — the owner's — and it has to be told which one.

## 4. Express it in your binding

The four fields above are the payload. How they ride depends on your transport.

Over HTTP, `WWW-Authenticate` is the conventional home, and the lab emits it for
compatibility. Over JSON-RPC there is no such header, and the same JSON rides
the error object byte for byte.

That is the argument for treating the challenge as **parameters rather than a
header**: the payload is portable and only the envelope is binding-specific. A
challenge defined as a header format needs reinventing for every non-HTTP
transport.

## 5. Have the agent corroborate it

This step belongs to the agent, and an enforcement point that does not expect it
is one an attacker can exploit.

The challenge names an authorization server. The resource's published metadata
also names authorization servers. The agent must check one against the other,
and refuse a challenge naming an authority the resource has never claimed.

Without that check, anything able to return a 401 can send an agent off to
negotiate with a server of its choosing — and the agent will sign terms, present
credentials, and hand over whatever the attacker's "authorization server" asks
for.

The check is two lines and closes the hole entirely.

## Troubleshooting

**Everything returns 403 with no ticket.** The authorization service is
returning a verdict but not a body. Confirm your gateway's ext-authz mechanism
can carry a response body on denial.

**The tool name is missing and you get "unknown method".** The body was
truncated before the authorizer saw it. Check the partial-body flag and refuse
explicitly rather than parsing what arrived.

**Signatures fail after moving gateways.** The authority used to rebuild the
signature base is coming from the transport. Take it from configuration.

**Tickets are accepted for resources that do not exist.** The authorization
server is not validating `resource_id` against its registry, usually because the
registry was populated by a push that half-failed. A
[pulled registry](/docs/overview/discovery/) fixes the class of problem.
