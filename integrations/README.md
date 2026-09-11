# Putting U4A in front of something you did not write

Most resources worth protecting were not built with this profile in mind, and
most of them cannot be changed. A workflow tool generates an MCP server; a
vendor ships an endpoint; an internal service is owned by another team. The
adoption question is never "how do we rewrite this to speak UMA" — it is
"what do we put in front of it."

The answer is one container. The enforcement point runs as a sidecar, answers
the protocol, and forwards what it allows. **Nothing upstream changes**, and
nothing upstream needs to know any of this exists.

```
  agent ──► U4A enforcement point ──► your MCP server
              │                        (n8n, StitchOps, FastMCP,
              │                         a vendor endpoint, anything)
              ▼
        the owner's authorization server
```

## Why in front, and not inside

The protocol's first beat is an HTTP status line: `401` with a
`WWW-Authenticate: UMA` header naming the authorization server and a ticket.
Most tools that generate MCP servers cannot emit one. n8n's MCP Server Trigger,
for instance, offers bearer and header auth and has no way to return a custom
challenge or publish RFC 9728 metadata — so there is no version of "configure
n8n to speak U4A." There does not need to be.

That constraint is the good news. If the resource cannot participate, the
resource does not have to, and adoption stops being a development project.

## The four things a protected resource must do

The sidecar does all of them. They are listed here because this is the contract
any host has to meet, and it is what makes the approach portable to a tool this
directory has no folder for.

| # | Obligation | Who does it |
|---|---|---|
| 1 | Introduce itself to the owner's authority, signing with a key published at its own origin — and **wait for her to authorize it** | sidecar |
| 2 | Answer an unauthorized call with `401` + `WWW-Authenticate: UMA`, naming the owner's authorization server and a ticket | sidecar |
| 3 | Publish RFC 9728 protected-resource metadata, so the agent can corroborate that authority rather than trust the header | sidecar |
| 4 | Hold a PAT with the owner's authority and introspect each grant on every call — never cache the verdict | sidecar |
| 5 | Verify the RFC 9421 proof-of-possession signature against the key bound into the grant, and check the operation digest | sidecar |
| — | Do the actual work | your MCP server |

Obligation 1 is the one people are surprised by, and it is the most
characteristic of this profile. A resource server is not configured into an
owner's authority by an administrator; it introduces itself, holding nothing
that authority issued, and sits inert until the owner says yes from her
portal. There is no client secret to exchange, because a shared string would
be a way around her.

## Vendor neutrality

The sidecar speaks HTTP to an HTTP upstream and parses MCP from the body. It
has no knowledge of the tool behind it. Anything reachable at a URL that speaks
streamable-HTTP MCP works the same way — n8n and StitchOps are two instances of
one integration, not two integrations.

What differs per vendor is only:

- **where the upstream URL comes from** (n8n: the MCP Server Trigger's
  production URL), and
- **how the tool surface is described** to the owner's authority, so her tiers
  can name individual tools rather than the whole endpoint.

Both are configuration. See [`n8n/`](n8n/) for a worked example, and copy it
for any other tool — the compose file changes by one line.

## What an enterprise actually has to decide

The technical work is small; these are the parts worth thinking about first.

**Who is the owner?** U4A is owner-authoritative — a resource belongs to
somebody, and that person's authority answers for it. For a back-office
workflow the owner is often a team or a service account rather than a person,
which is fine, but it should be a deliberate choice rather than a default.

**What are the tiers?** Not "read" and "write". A tier is a bargain the owner
would recognise: *portfolio holdings*, *transaction history*, *execute a
trade*. Tiers are the unit she approves once and the unit rules attach to, so
drawing them badly is the thing most worth getting right early.

**Which calls should ever wake somebody?** Most should not. The point of the
policy layer is that standing rules answer nearly everything and a person is
interrupted only where they said they wanted to be.

**Where does the sidecar run?** Beside the resource, inside whatever boundary
already protects it. Its value depends on the upstream not being reachable
around it — see [the non-bypassability
suite](https://u4a.ai/docs/guides/run-the-lab/#prove-it-works) for how the lab
asserts exactly that.

## Getting started

1. Stand up an authorization server for the owner. The lab's is a reference
   implementation, not a product — read
   [PROTOCOL.md](../docs/PROTOCOL.md) for what any implementation must do.
2. Put the sidecar in front of your MCP server (`n8n/docker-compose.yml`).
   There is no published image; it builds from this repository.
3. Describe your tools in a `tools.json` and point `UMA_PEP_TOOLS` at it. That
   surface is what the owner's tiers can name, so the split there is the split
   she gets to approve.
4. Approve the resource server from the owner's portal. Until then it answers
   `authorization_pending` and protects nothing.
5. Check it with `python3 conformance.py https://your-endpoint --upstream
   <internal url>` — it asserts the obligations above from outside, the way an
   agent would meet them.

## What has been run, and what has not

The sidecar path is exercised end to end against the lab's authorization
server: no grant is answered `401` with a UMA challenge and the upstream is
never reached; a real negotiated grant is forwarded and answered `200`; the
upstream receives an `X-Uma-Contract` header and never the agent's
`Authorization`. The registration and owner-approval steps above are the ones
the lab's own gateway performs on every start.

What has not been run is a full n8n instance behind it. The sidecar speaks HTTP
to an HTTP upstream and parses MCP from the body — it has no knowledge of the
tool behind it — so the n8n-specific part is configuration rather than code,
but it is worth saying plainly that the vendor half is untested.
