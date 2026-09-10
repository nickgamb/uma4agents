---
templateKey: doc
title: Put U4A in front of something you did not write
seoTitle: "Adopt U4A for an existing MCP server without changing it"
description: Most resources worth protecting cannot be modified. The enforcement point runs as a sidecar, answers the protocol, and forwards what it allows.
next:
  - title: Run the lab
    to: /docs/guides/run-the-lab/
  - title: The architecture
    to: /docs/overview/architecture/
---

Most resources worth protecting were not built with this profile in mind, and
most of them cannot be changed. A workflow tool generates an MCP server; a
vendor ships an endpoint; an internal service belongs to another team. The
adoption question is never *how do we rewrite this to speak UMA*. It is *what
do we put in front of it*.

One container. The enforcement point runs as a sidecar, answers the protocol,
and forwards what it allows. Nothing upstream changes, and nothing upstream
needs to know this exists.

```
  agent ──►  U4A enforcement point  ──►  your MCP server
               │
               ▼
       the owner's authorization server
```

## Why in front, and not inside

The protocol's first beat is an HTTP status line: `401` with a
`WWW-Authenticate: UMA` header naming the owner's authorization server and a
ticket. Most tools that generate MCP servers cannot emit one.

n8n is a good example precisely because it is a capable tool. Its MCP Server
Trigger supports bearer and header authentication and has no way to return a
custom challenge or publish RFC 9728 metadata. So there is no version of
"configure n8n to speak U4A" — and there does not need to be.

That constraint is the good news. If the resource cannot participate, the
resource does not have to, and adoption stops being a development project.

## What a protected resource owes

Four things. The sidecar does all of them; they are listed because this is the
contract, and it is what makes the approach portable to a tool nobody has
written a folder for yet.

| # | Obligation |
|---|---|
| 1 | Answer an unauthorized call with `401` + `WWW-Authenticate: UMA`, naming the authorization server and a ticket |
| 2 | Publish RFC 9728 protected-resource metadata, so the agent can corroborate that authority rather than trust the header |
| 3 | Hold a PAT with the owner's authority and introspect the grant **on every call** — never cache the verdict |
| 4 | Verify the RFC 9421 proof-of-possession signature against the key bound into the grant, and check the operation digest |

Your MCP server keeps doing the work. It never sees a grant: the sidecar
strips the agent's `Authorization` header before forwarding, because that
credential is addressed to this authority and spent here, and an upstream that
received it could replay it.

## The same integration for every vendor

The sidecar speaks HTTP to an HTTP upstream and parses MCP from the body. It
knows nothing about the tool behind it. n8n and StitchOps are two instances of
one integration, not two integrations.

Two things differ per vendor, and both are configuration:

- **where the upstream URL comes from** — for n8n, the MCP Server Trigger's
  production URL;
- **how the tool surface is described**, so the owner's tiers can name
  individual tools rather than the whole endpoint.

## Drawing the tiers is the real work

The technical integration is a compose file. What deserves thought is the part
no tool can do for you.

**Who is the owner?** This profile is owner-authoritative: a resource belongs
to somebody and that person's authority answers for it. For a back-office
workflow the owner is often a team rather than a person, which is fine — but
it should be a decision rather than a default.

**What are the tiers?** Not "read" and "write". A tier is a bargain the owner
would recognise: *list invoices*, *issue a refund*. Tiers are the unit she
approves once and the unit rules attach to, so drawing them badly is the thing
most worth getting right early. Exposing one endpoint as one resource means she
can only ever say yes to all of it.

**Which calls should ever wake somebody?** Most should not. The policy layer
exists so that standing rules answer nearly everything and a person is
interrupted only where they said they wanted to be.

**Where does the sidecar run?** Inside whatever boundary already protects the
resource. Its value depends entirely on the upstream not being reachable
around it.

## Checking it

That last point is the one most often missed, so it is asserted rather than
assumed:

```bash
python3 integrations/conformance.py https://your-endpoint \
    --upstream http://your-mcp-server-internal:5678/mcp/path
```

It works from outside, in the order an agent meets things: discover the tool
surface from the published document, make a call with no grant and require a
challenge, check the document corroborates the authority the challenge named,
confirm a made-up bearer token gets nowhere — and then confirm the resource
itself refuses a call that did not come through the enforcement point.

Everything above that last check can pass while the resource is still wide
open on another port. A suite that only proves the allows would pass against an
endpoint with no enforcement at all.

## Files

[`integrations/`](https://github.com/nickgamb/uma4agents/tree/main/integrations)
in the repository: the vendor-neutral contract, a worked n8n example with an
importable workflow and a compose file, and the conformance checker.
