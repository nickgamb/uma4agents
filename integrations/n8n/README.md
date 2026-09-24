# n8n

Put a U4A enforcement point in front of an MCP server n8n generated. n8n is not
modified and does not know this happened.

The same files work for any tool that publishes a streamable-HTTP MCP
endpoint — StitchOps, Zapier, a hand-written FastMCP server. Change
`UMA_PEP_UPSTREAM` and you have integrated that one instead.

![U4A in front of n8n. An MCP client calls a tool and is answered 401 with a
UMA challenge by the sidecar, which n8n never sees. The client negotiates the
owner's terms at her authorization server and comes back with a grant bound to
its own key. The sidecar introspects it and forwards to n8n, stripping the
agent's Authorization and adding its own credential and the contract digest.
Before any of that, the sidecar registers itself with her authority and waits
for her to approve it.](../../docs/n8n-sidecar.svg)

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

## Run it yourself, against the lab

The lab already has an authorization server, an owner and a CA, so it is the
cheapest place to watch the whole thing work. `lab/e2e-pod.yaml` puts a live
n8n and a live sidecar in one pod, with an ordinary agent beside them — three
containers so every hop is localhost and the shape stays obvious.

**1 · Bring the lab up** and make sure it is healthy.

```bash
make kind-up && make k8s-status
```

**2 · Load the fixtures.** The workflow, its header credential, the tool
surface the sidecar protects, and the agent script.

```bash
kubectl create cm n8n-fixtures -n meridian   --from-file=wf.json=integrations/n8n/lab/e2e-workflow.json   --from-file=creds.json=integrations/n8n/lab/e2e-credentials.json   --from-file=e2e.py=integrations/n8n/lab/e2e-client.py
kubectl create cm sidecar-tools -n meridian   --from-file=tools.json=integrations/n8n/lab/e2e-tools.json
kubectl create cm demo-lib -n meridian   --from-file=lib/uma4a_grant.py --from-file=lib/uma4a_http_sig.py   --from-file=lib/uma4a_org.py --from-file=lib/uma4a_joint.py
```

**3 · Start it.** n8n imports the workflow, publishes it, and comes up; the
sidecar registers itself with Alice's authority as `https://n8n.uma.lab`,
under its own service account and a key it generated at start. It is a
resource server she has never seen, and she is asked about it as one.

```bash
kubectl apply -f integrations/n8n/lab/e2e-pod.yaml
kubectl -n meridian logs -f n8n-e2e -c n8n | grep -m1 "published workflows"
```

**4 · Alice authorizes the resource server.** Until she does, every call
through the sidecar answers `authorization_pending`. In her portal at
`https://portal.uma.lab` (**alice** / **alice-demo**) it is under
**Settings → Security → Agent Authorization → Resource servers**, as
**n8n workflow (lab)** at `https://n8n.uma.lab`.

**5 · Run the agent**, and answer its first contact in her portal when the
badge appears.

```bash
kubectl -n meridian exec n8n-e2e -c client -- python3 /driver/e2e.py
```

What it prints:

```
1 initialize through the sidecar -> 200 session True
2 tools/call with no grant -> 401
  challenge from -> https://alice-as.uma.lab
3 grant negotiated -> True
4 same call with the grant -> 200
  n8n answered -> {"served_by":"n8n","tool":"get_positions", ...}
```

**6 · Check that n8n is not reachable around the sidecar.**

```bash
kubectl -n meridian exec n8n-e2e -c client -- python3 -c   "import httpx; print(httpx.post('http://127.0.0.1:5678/mcp/u4a-protected', json={}, timeout=10).status_code)"
```

`403`. The sidecar holds a header credential n8n requires and nothing else
has it.

**Tear it down.** Revoke `https://n8n.uma.lab` under **Resource servers** in
her portal first: deleting the pod removes the resource server, and only she
can remove her authority's approval of it.

```bash
kubectl delete -f integrations/n8n/lab/e2e-pod.yaml
kubectl -n meridian delete cm n8n-fixtures sidecar-tools demo-lib
```

The workflow in `lab/` exposes the lab's own tool names, so Alice's existing
tiers govern it and no policy has to be written to see the whole loop. The
template at the top of this directory keeps the billing example, which is the
shape you would actually start from.

## What the sidecar does to the request

On the way out it adds two headers and removes one.

`X-Uma-Contract` is the agreement digest — a fact about the call the upstream
may want to log, and useless for obtaining anything. The credential named by
`UMA_PEP_UPSTREAM_HEADER` is the one the upstream requires, which only the
sidecar holds.

The agent's `Authorization` is **not** forwarded. That grant is addressed to
the owner's authority and spent at the sidecar; an upstream holding it could
replay it.

`UMA_PEP_UPSTREAM` naming a path means it *is* the endpoint — the request's own
path is not appended. That is the ordinary case in front of a workflow tool,
whose MCP server lives at one generated URL. A bare origin keeps the request
path instead, for fronting a server with several.
