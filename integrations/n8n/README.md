# n8n

Put a U4A enforcement point in front of an MCP server n8n generated. n8n is not
modified and does not know this happened.

The same files work for any tool that publishes a streamable-HTTP MCP
endpoint — StitchOps, Zapier, a hand-written FastMCP server. Change
`UMA_PEP_UPSTREAM` and you have integrated that one instead.

## 1 · Publish the MCP server in n8n

Add an **MCP Server Trigger** to a workflow, connect the tool nodes you want
exposed, and activate it. Copy the **production** MCP URL — it looks like
`https://your-n8n/mcp/<path>`.

Set the trigger's authentication to **Header auth** with a value only the
sidecar knows, and put it in `.env` as `UPSTREAM_AUTH`. That is not what
authorizes agents — the sidecar does that, before anything reaches n8n. It is
there so the endpoint cannot be reached around the sidecar by anyone who
learns the URL. Defence in depth, not the control.

`workflow-template.json` is an importable starter with the trigger and two
example tools already wired.

## 2 · Describe the tools

Edit `tools.json`. Each entry maps an MCP tool name to a resource id and the
scopes it needs:

```json
{
  "get_invoices":   { "resource": "billing/get_invoices",   "scopes": ["invoices:read"] },
  "issue_refund":   { "resource": "billing/issue_refund",   "scopes": ["refunds:write"] }
}
```

This is what lets the owner write a tier about *issuing a refund* rather than
about *the billing endpoint*. Splitting tools across tiers is the whole reason
her approvals mean anything, so it is worth more thought than the rest of this
page combined.

## 3 · Run the sidecar

```bash
cp .env.example .env      # then edit it
docker compose up -d
```

Point your agents at the **sidecar's** URL, not n8n's. An agent that has never
been here gets a `401` naming the owner's authority, negotiates her terms, and
comes back with a grant.

## 4 · Check it

```bash
python3 ../conformance.py https://your-sidecar-url
```

Asserts the four obligations from outside, the way an agent would meet them:
the challenge, the metadata document, that an unsigned grant is refused, and —
the one people forget — that the upstream is not reachable around the sidecar.

## What this does not do

It does not protect n8n's own UI, its REST API, or any other workflow. It
protects one MCP endpoint. If n8n is reachable directly, this is a suggestion
rather than a control: put both in a network where only the sidecar is exposed,
and let the conformance check tell you whether you got that right.
