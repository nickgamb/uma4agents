"""A real agent: through the sidecar, into a live n8n MCP server."""
import json, os, sys, httpx
sys.path.insert(0, "/driver/lib")
from uma4a_grant import AgentKeys, parse_challenge, run_grant, signed_headers

SIDECAR = "http://127.0.0.1:9002/mcp"
CA = "/certs/rootCA.pem"
keys = AgentKeys()
H = {"content-type": "application/json", "accept": "application/json, text/event-stream",
     "mcp-protocol-version": "2025-06-18"}

def rpc(c, method, params, extra=None):
    return c.post(SIDECAR, json={"jsonrpc": "2.0", "id": 1, "method": method,
                                 "params": params}, headers={**H, **(extra or {})})

with httpx.Client(verify=CA, timeout=60.0) as c:
    r = rpc(c, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                              "clientInfo": {"name": "u4a-e2e", "version": "1"}})
    sid = r.headers.get("mcp-session-id")
    print("1 initialize through the sidecar ->", r.status_code, "session", bool(sid))
    s = {"mcp-session-id": sid} if sid else {}
    rpc(c, "notifications/initialized", {}, s)

    r = rpc(c, "tools/call", {"name": "get_positions", "arguments": {}}, s)
    print("2 tools/call with no grant ->", r.status_code)
    ch = parse_challenge(r.headers.get("www-authenticate", ""))
    print("  challenge from ->", ch.as_uri)

    rpt = run_grant(c, ch.as_uri, ch.ticket, keys, lambda t: True, max_wait_s=120)
    print("3 grant negotiated ->", bool(rpt))

    body = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                       "params": {"name": "get_positions", "arguments": {}}}).encode()
    h = signed_headers("POST", "n8n.uma.lab", "/mcp", rpt, keys)
    r = c.post(SIDECAR, content=body, headers={**H, **s, **h})
    print("4 same call with the grant ->", r.status_code)
    print("  n8n answered ->", r.text[:260])
