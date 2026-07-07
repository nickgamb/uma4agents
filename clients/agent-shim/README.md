# agent-shim

Lets an **unmodified agent** (Claude Code, Claude Desktop, any MCP client) act
as Bob's requesting agent against Alice's vault. The shim is to UMA-for-agents
what `mcp-remote` is to MCP OAuth: it holds the agent's signing key, signs
requests (RFC 9421), and runs the four-beat grant dance when the gateway
challenges — surfacing Alice's dictated terms to Bob *inside his agent* via
MCP elicitation, with his standing config as the fallback for clients that
don't render elicitation yet.

## Connect Claude Code

From the repo root (so cert/lib paths resolve):

```bash
claude mcp add alice-vault -- \
  env PYTHONPATH=lib UMA4A_CACERT=certs/rootCA.pem \
  uv run --with 'mcp>=1.13' --with httpx --with 'pyjwt[crypto]' \
  python clients/agent-shim/shim.py
```

Then ask Claude something like *"what's in Alice's portfolio?"* — the first
tool call triggers the challenge, and Alice's terms appear as an elicitation
form for you to approve. `execute_trade` pends until Alice approves it in
[her portal](https://portal.uma.lab).

## Verify headlessly

`make shim-test` runs the shim under a scripted stdio MCP client that
exercises both approval paths (elicitation and standing config).
