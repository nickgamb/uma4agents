# n8n

Put a U4A enforcement point in front of an MCP server n8n generated. n8n is not
modified and does not know this happened.

The same files work for any tool that publishes a streamable-HTTP MCP
endpoint — StitchOps, Zapier, a hand-written FastMCP server. Change
`UMA_PEP_UPSTREAM` and you have integrated that one instead.

## 1 · Publish the MCP server in n8n

Import `workflow-template.json`, or add an **MCP Server Trigger** yourself and
connect the tool nodes you want exposed. Activate it, then copy the
**production** MCP URL.

Set the trigger's authentication to **Header auth** with a value only the
sidecar knows, and put it in `.env`. That is not what authorizes agents — the
sidecar does that, before anything reaches n8n. It is there so the endpoint
cannot be reached around the sidecar by anyone who learns the URL. Defence in
depth, not the control.

## 2 · Describe the tools

`tools.json` is the tool surface, and the sidecar reads it at startup
(`UMA_PEP_TOOLS`). Each entry maps an MCP tool name to a resource id and the
scopes it needs:

```json
{
  "get_invoices": { "resource": "billing/get_invoices", "scopes": ["invoices:read"] },
  "issue_refund": { "resource": "billing/issue_refund", "scopes": ["refunds:write"],
                    "single_use": true }
}
```

This is what the owner's authority is told about, so it is what her tiers can
name — the split here is the split she gets to approve. Exposing one endpoint
as one resource means she can only ever say yes to all of it, so this file
deserves more thought than the rest of this page combined.

`single_use` marks a tool whose grant is spent by one call. Use it for
anything with consequences.

A malformed file stops the sidecar rather than falling back to a default. A
resource server that silently protects the wrong tools is worse than one that
does not start, because nothing downstream would report it.

## 3 · Run the sidecar

```bash
cp .env.example .env      # then edit it
docker compose up -d
```

## 4 · The owner authorizes it — this is not automatic

On startup the sidecar introduces itself to the owner's authorization server.
It holds nothing that authority issued: it signs the registration with a key
it publishes at its own origin, so the credential *is* the origin, and
verifying it is a fetch the authority performs rather than a claim it is
handed.

The answer is hers. Until she gives it, calls through the sidecar return:

```json
{"error": "authorization_pending",
 "error_description": "this resource server has registered with the owner's
                       authorization server and is waiting for her to authorize it"}
```

She approves it in her portal, under **Resource servers**. Only then does the
sidecar get a PAT and begin protecting the endpoint. There is no client secret
to exchange — a shared string would be a way around her.

This step is the point rather than an obstacle. A resource server is something
she consents to, the same way an agent is.

## 5 · Check it

```bash
python3 ../conformance.py https://your-sidecar-url \
    --upstream http://your-n8n-internal:5678/mcp/your-path
```

It reads the published tool surface, makes a call with no grant and requires a
challenge, checks the metadata document corroborates the authority that
challenge named, confirms a made-up bearer token gets nowhere, and — the one
people forget — confirms the resource itself refuses a call that did not come
through the sidecar.

## What is verified, and what is not

The sidecar path has been run end to end against the lab's authorization
server: a call with no grant is answered `401` with a UMA challenge, the
upstream is never reached, and after a real grant is negotiated the call is
forwarded and answered `200`. The upstream sees an `X-Uma-Contract` header and
**does not** see the agent's `Authorization` — that grant is addressed to the
owner's authority and spent at the sidecar, and an upstream holding it could
replay it.

`workflow-template.json` imports into n8n 2.38.6 and round-trips back out with
all three nodes resolving at their current versions — `mcpTrigger` 2.1 and two
`toolCode` 1.3. Import it, replace the tool bodies, activate it.

```bash
n8n import:workflow --input=workflow-template.json
```

What has not been run is the two halves joined: a live n8n behind a live
sidecar. The sidecar speaks HTTP to an HTTP upstream and parses MCP from the
body, so that join is configuration rather than code — but it is worth saying
which part was tested and which was reasoned.
