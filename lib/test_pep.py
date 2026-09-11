"""The enforcement point's refusals that need no network, and the challenge.

Everything the enforcer decides before it talks to anybody: which methods are
open, which headers may steer it, whose origin it serves, which scheme a grant
must arrive under. And the one property of the challenge worth pinning in a
unit test — that the object inside a WWW-Authenticate header and the object
inside a JSON-RPC error are the same object, because they are produced by the
same function.

Run: make pep-test
"""
import asyncio
import base64
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from uma4a_pep import AuthzFacts, Decision, Enforcer  # noqa: E402

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASSED if ok else FAILED).append(name)
    print(("ok   " if ok else "FAIL ") + name + (f" — {detail}" if detail and not ok else ""))


enforcer = Enforcer(
    as_internal="http://uma-as.invalid:9000",
    as_public="https://alice-as.example",
    client_id="rs",
    client_secret="unused",
    realm="alice-vault",
    tools={"get_positions": ("alice-vault/get_positions", ["positions:read"]),
           "execute_trade": ("alice-vault/execute_trade", ["trades:execute"])},
    single_use_tools={"execute_trade"},
    protected_methods={"tools/call"},
    open_methods={"initialize", "tools/list", "server/discover"},
    expected_authority="rs.example",
    allowed_origins={"https://rs.example"},
    resource_metadata_url="https://rs.example/.well-known/oauth-protected-resource/mcp",
    event=lambda *a, **k: None,
)


def decide(**facts) -> Decision:
    base = dict(tool="get_positions", args={}, mcp_method="tools/call",
                header_mcp_method="tools/call", header_mcp_name="get_positions",
                protocol_version="2026-07-28")
    base.update(facts)
    return asyncio.run(enforcer.authorize(AuthzFacts(**base)))


print("\n== what is refused before anyone is asked ==")
d = decide(tool=None, mcp_method="tools/list", header_mcp_method="tools/list",
           header_mcp_name=None)
check("an open method passes without authorization", d.outcome == "allow", d.error)

d = decide(tool=None, mcp_method="tasks/get", header_mcp_method="tasks/get",
           header_mcp_name=None)
check("an unknown method is refused, not forwarded",
      d.outcome == "deny" and d.error == "unknown_method", d.error)

d = decide(header_mcp_method="tools/list")
check("a header naming an open method over a body naming a protected one is refused",
      d.outcome == "deny" and d.error == "header_body_mismatch", d.error)

d = decide(header_mcp_name="get_transactions")
check("and a header naming a different tool than the body is refused",
      d.outcome == "deny" and d.error == "header_body_mismatch", d.error)

d = decide(header_mcp_method=None, header_mcp_name=None)
check("a tools/call with no routing headers on 2026-07-28 is refused",
      d.outcome == "deny" and d.error == "missing_routing_headers", d.error)

d = decide(origin="https://evil.example")
check("a request from an origin the resource does not serve is refused",
      d.outcome == "deny" and d.error == "invalid_origin", d.error)

d = decide(authorization="Bearer not-a-pop-token")
check("a bearer token is refused: grants here are proof-of-possession",
      d.outcome == "deny" and d.error == "invalid_token", d.error)

d = decide(tool="nonexistent", header_mcp_name="nonexistent")
check("an unknown tool is refused", d.outcome == "deny" and d.error == "unknown_tool", d.error)


print("\n== the challenge, in both encodings ==")
details = [{"type": "urn:uma4agents:authorization-details:tool-call",
            "locations": ["https://rs.example"],
            "identifier": "alice-vault/execute_trade",
            "actions": ["execute_trade"], "datatypes": ["trades:execute"]}]
ch = Decision(outcome="challenge", status=401, error="uma_challenge",
              ticket="tkt-1", as_uri="https://alice-as.example",
              resource_metadata=enforcer.resource_metadata_url,
              scopes=["trades:execute"], authorization_details=details,
              authorization_reference="s256:abc")
header = enforcer.www_authenticate(ch)
params = {}
for part in header[len("UMA "):].split(", "):
    k, v = part.split("=", 1)
    params[k] = v.strip('"')
check("the header carries every required parameter",
      all(k in params for k in ("realm", "error", "as_uri", "ticket",
                                "resource_metadata", "authorization_remediation"))
      and params["error"] == "insufficient_authorization", header[:120])
blob = params["authorization_remediation"]
decoded = json.loads(base64.urlsafe_b64decode(blob + "=" * (-len(blob) % 4)))
check("the remediation object is identical in both encodings",
      decoded == enforcer.remediation(ch), json.dumps(decoded)[:120])
check("and it names the authorization server and the ticket",
      decoded["authorization_server"] == ch.as_uri and decoded["ticket"] == ch.ticket)

print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
if FAILED:
    raise SystemExit(1)
