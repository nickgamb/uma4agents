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
details = [{"type": "https://u4a.ai/spec/core/1.0#tool-call",
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

import time  # noqa: E402
from unittest.mock import AsyncMock  # noqa: E402

import jwt  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from jwt.algorithms import OKPAlgorithm  # noqa: E402

from uma4a_http_sig import sign as http_sign  # noqa: E402
from uma4a_joint import key_thumbprint, mandate_digest  # noqa: E402
from uma4a_pep import s256  # noqa: E402

AGENT = Ed25519PrivateKey.generate()
AGENT_JWK = json.loads(OKPAlgorithm.to_jwk(AGENT.public_key()))
INTRUDER = Ed25519PrivateKey.generate()
INTRUDER_JWK = json.loads(OKPAlgorithm.to_jwk(INTRUDER.public_key()))
CHALLENGE = Decision(outcome="challenge", status=401, error="uma_challenge")
CONFIG = dict(
    as_internal="http://uma-as.invalid:9000", as_public="https://alice-as.example",
    client_id="rs", realm="alice-vault",
    tools={"get_positions": ("alice-vault/get_positions", ["positions:read"]),
           "execute_trade": ("alice-vault/execute_trade", ["trades:execute"])},
    single_use_tools={"execute_trade"}, protected_methods={"tools/call"},
    open_methods={"tools/list"}, expected_authority="rs.example",
    allowed_origins=set(),
    resource_metadata_url="https://rs.example/.well-known/oauth-protected-resource/mcp",
    event=lambda *a, **k: None)


def granting(info: dict, **over) -> Enforcer:
    """An enforcer whose authority answers with `info`, and nothing else
    reaches the network."""
    e = Enforcer(**{**CONFIG, **over})
    e.introspect = AsyncMock(return_value=info)
    e.consume = AsyncMock(return_value={"consumed": True})
    e.report_access = AsyncMock()
    e.challenge = AsyncMock(return_value=CHALLENGE)
    return e


def present(e: Enforcer, tool="get_positions", args=None, key=AGENT,
            body=None, sent=None, cover_body=True) -> Decision:
    authorization = "PoP grant"
    headers = http_sign("POST", "rs.example", "/mcp", authorization, key, "agent",
                        body=body if cover_body else None)
    return asyncio.run(e.authorize(AuthzFacts(
        tool=tool, args=args or {}, mcp_method="tools/call",
        header_mcp_method="tools/call", header_mcp_name=tool,
        protocol_version="2026-07-28", authorization=authorization,
        signature=headers["Signature"], signature_input=headers["Signature-Input"],
        body=body if sent is None else sent,
        content_digest=headers.get("Content-Digest"))))


def grant(rid="alice-vault/get_positions", scopes=("positions:read",), **over) -> dict:
    at = int(time.time())
    out = {"active": True, "family": "fam_g", "exp": at + 300,
           "cnf": {"jwk": AGENT_JWK},
           "permissions": [{"resource_id": rid, "resource_scopes": list(scopes),
                            "exp": at + 300}]}
    out.update(over)
    return out


print("\n== what a grant has to cover ==")
d = present(granting(grant()))
check("a grant covering the tool's resource and scope is honoured", d.outcome == "allow", d.error)

d = present(granting(grant(scopes=())))
check("a grant over the resource without the tool's scope is not",
      d.outcome == "challenge", d.error)

expired = grant()
expired["permissions"][0]["exp"] = int(time.time()) - 5
d = present(granting(expired))
check("a permission past its own expiry is not honoured", d.outcome == "challenge", d.error)

early = grant()
early["permissions"][0]["nbf"] = int(time.time()) + 600
d = present(granting(early))
check("nor one before it becomes valid", d.outcome == "challenge", d.error)

print("\n== a resource may not raise what an operation costs under a grant ==")
# Her authority answered a question about an operation the resource described.
# If the description changes afterwards, the answer was to a different question.
d = present(granting(grant(consequence="reversible"),
                     consequence={"get_positions": "irreversible"}))
check("a grant does not survive the operation being re-declared worse",
      d.outcome == "deny" and d.error == "consequence_changed", d.error)

d = present(granting(grant(consequence="irreversible"),
                     consequence={"get_positions": "irreversible"}))
check("the class it was issued against is honoured", d.outcome == "allow", d.error)

d = present(granting(grant(consequence="irreversible"),
                     consequence={"get_positions": "reversible"}))
check("a resource that lowers its own claim invalidates nothing",
      d.outcome == "allow", d.error)

# The day a deployment first describes its tools, every standing grant predates
# the description. Refusing those would revoke the lot; the next negotiation
# carries the class, and the check holds from then on.
d = present(granting(grant(), consequence={"get_positions": "irreversible"}))
check("a grant issued before anything was declared is not refused for it",
      d.outcome == "allow", d.error)

_declaring = Enforcer(**{**CONFIG, "consequence": {"execute_trade": "irreversible"}})
_detail = _declaring.authorization_details(
    "alice-vault/execute_trade", "execute_trade", ["trades:execute"])[0]
check("the remediation object says what the act would leave behind, so an "
      "agent learns it before it negotiates",
      _detail.get("consequence") == "irreversible")
_plain = _declaring.authorization_details(
    "alice-vault/get_positions", "get_positions", ["positions:read"])[0]
check("and says nothing where the resource has declared nothing",
      "consequence" not in _plain)


print("\n== operation binding follows the grant ==")
trade = {"symbol": "VTI", "qty": 40}
d = present(granting(grant("alice-vault/execute_trade", ("trades:execute",), single_use=True)),
            tool="execute_trade", args=trade)
check("a single-use tool refuses a grant bound to no operation",
      d.outcome == "deny" and d.error == "operation_required", d.error)

bound = {"tool": "execute_trade",
         "params_s256": s256(json.dumps(trade, sort_keys=True, separators=(",", ":"),
                                        ensure_ascii=False).encode())}
e = granting(grant("alice-vault/execute_trade", ("trades:execute",),
                   single_use=True, operation=bound))
d = present(e, tool="execute_trade", args=trade)
check("and honours one bound to exactly this call, spending it",
      d.outcome == "allow" and e.consume.await_count == 1, d.error)

once = {"tool": "get_positions", "params_s256": s256(b"{}")}
e = granting(grant(single_use=True, operation=once))
d = present(e)
check("a grant marked single-use is spent even at a tool not listed as one",
      d.outcome == "allow" and e.consume.await_count == 1, d.error)
e = granting(grant(single_use=True, operation=once))
d = present(e, args={"account": "someone-else"})
check("and refused for a different call to that tool",
      d.outcome == "deny" and d.error == "operation_mismatch", d.error)

print("\n== why a grant is not live, and what the agent is told ==")
for reason in ("expired", "unknown_token", "revoked"):
    d = present(granting({"active": False, "error": reason}))
    check(f"{reason}: the agent is sent to negotiate again", d.outcome == "challenge", d.error)
for reason in ("connection_revoked", "organization_revoked"):
    d = present(granting({"active": False, "error": reason}))
    check(f"{reason}: refused without a challenge",
          d.outcome == "deny" and d.error == "access_revoked", d.error)
d = present(granting({"active": False, "error": "a_reason_from_a_later_draft"}))
check("a reason this side does not recognise is refused without a challenge",
      d.outcome == "deny" and d.error == "access_revoked", d.error)
d = present(granting({"active": False, "error": "introspection_unavailable"}))
check("an authority that could not be asked is not a verdict on the grant",
      d.outcome == "deny" and d.status == 503, d.error)

e = granting(grant(single_use=True, operation=once))
e.consume = AsyncMock(return_value=None)
d = present(e)
check("a spend that could not be attempted is not reported as a lost race",
      d.outcome == "deny" and d.status == 503 and d.error != "already_consumed", d.error)
e = granting(grant(single_use=True, operation=once))
e.consume = AsyncMock(return_value={"consumed": False, "error": "already_consumed"})
d = present(e)
check("a spend someone else won is refused as already spent",
      d.outcome == "deny" and d.error == "already_consumed", d.error)
e = granting(grant(single_use=True, operation=once))
e.consume = AsyncMock(return_value={"consumed": False, "error": "connection_revoked"})
d = present(e)
check("a grant revoked between the check and the spend is refused as revoked",
      d.outcome == "deny" and d.error == "access_revoked", d.error)

print("\n== a body the signature covers ==")
d = present(granting(grant()), body=b'{"arguments":{}}')
check("a covered body that arrives unchanged verifies", d.outcome == "allow", d.error)
d = present(granting(grant()), body=b'{"arguments":{}}', sent=b'{"arguments":{"all":true}}')
check("a covered body changed after signing is refused",
      d.outcome == "deny" and d.error == "invalid_token", d.error)
d = present(granting(grant(), require_content_digest=True), body=b"{}", cover_body=False)
check("where the body must be covered, a signature that does not cover it is refused",
      d.outcome == "deny" and d.error == "invalid_token", d.error)

print("\n== a jointly held resource: the grant must be what the holders agreed ==")
TALLY = "https://tally.example"
HOLDERS = {name: Ed25519PrivateKey.generate() for name in ("alice", "carol")}
MANDATE = {"account": "joint", "resources": ["joint/*"], "rule": {"kind": "all"},
           "holders": [{"owner": n, "issuer": f"https://{n}.example", "weight": 1}
                       for n in HOLDERS]}


def verdict(name: str, key=None, **over) -> str:
    at = int(time.time())
    claims = {"iss": f"https://{name}.example", "holder": name, "account": "joint",
              "negotiation": "fam_j", "resource_id": "joint/read",
              "contract": "s256:agreement", "effect": "allow", "iat": at, "exp": at + 300,
              "cnf_jkt": key_thumbprint(AGENT_JWK), "scope": ["read"],
              "expires_in": 300, "mandate_s256": mandate_digest(MANDATE)}
    claims.update(over)
    return jwt.encode(claims, key or HOLDERS[name], algorithm="EdDSA",
                      headers={"typ": "u4a-verdict+jwt"})


def joint_grant(verdicts=None, scopes=("read",), lasts=300, **over) -> dict:
    out = grant("joint/read", scopes, family="fam_j", contract="s256:agreement",
                joint={"account": "joint", "verdicts": verdicts if verdicts is not None
                       else [verdict("alice"), verdict("carol")]})
    out["exp"] = out["permissions"][0]["exp"] = int(time.time()) + lasts
    out.update(over)
    return out


def jointly(info: dict, published: dict | None = None) -> Enforcer:
    e = granting(info, tools={"read": ("joint/read", ["read"])},
                 single_use_tools=set(), joint_issuer=TALLY, realm="joint")
    later = time.time() + 3600
    e._mandates["joint"] = (later, published or MANDATE)
    for name, key in HOLDERS.items():
        e._holder_jwks[f"https://{name}.example"] = (
            later, [json.loads(OKPAlgorithm.to_jwk(key.public_key()))])
    return e


def refused_jointly(d: Decision) -> bool:
    return d.outcome == "deny" and d.error == "joint_mandate_unsatisfied"


# One holder's verdict signed by a key she never published, everything else
# genuine: only the verdict signature check can refuse this.
d = present(jointly(joint_grant(verdicts=[
    verdict("alice", key=Ed25519PrivateKey.generate()), verdict("carol")])), tool="read")
check("a verdict signed by a key its holder never published is not counted",
      refused_jointly(d), d.error)


d = present(jointly(joint_grant()), tool="read")
check("a grant both holders' verdicts describe is honoured", d.outcome == "allow",
      f"{d.error}: {d.description}")

d = present(jointly(joint_grant(verdicts=[verdict("alice")])), tool="read")
check("one verdict of the two it takes is not enough", refused_jointly(d), d.error)

d = present(jointly(joint_grant(cnf={"jwk": INTRUDER_JWK})), tool="read", key=INTRUDER)
check("genuine verdicts do not carry a grant bound to another key",
      refused_jointly(d), d.error)

d = present(jointly(joint_grant(scopes=("read", "admin"))), tool="read")
check("nor a grant with scopes the agreement did not have", refused_jointly(d), d.error)

d = present(jointly(joint_grant(lasts=86400)), tool="read")
check("nor one that outlives the agreement", refused_jointly(d), d.error)

per_op = {"tool": "read", "params_s256": s256(b"{}")}
d = present(jointly(joint_grant(verdicts=[verdict("alice", operation=per_op),
                                          verdict("carol", operation=per_op)])), tool="read")
check("nor one stripped of the operation the holders agreed to", refused_jointly(d), d.error)

d = present(jointly(joint_grant(family="fam_other")), tool="read")
check("nor verdicts about a different negotiation", refused_jointly(d), d.error)

heavier = {**MANDATE, "rule": {"kind": "threshold", "threshold": 2},
           "holders": [dict(MANDATE["holders"][0], weight=2), MANDATE["holders"][1]]}
d = present(jointly(joint_grant(verdicts=[verdict("alice")]), published=heavier), tool="read")
check("a published mandate that reweights a holder is not the one agreed to",
      refused_jointly(d), d.error)

elsewhere = {**MANDATE, "resources": ["unrelated/*"]}
d = present(jointly(joint_grant(), published=elsewhere), tool="read")
check("a published mandate that does not cover the resource counts for nothing",
      refused_jointly(d) and "does not cover" in (d.description or ""), d.description)

bare = joint_grant()
bare.pop("joint")
d = present(jointly(bare), tool="read")
check("a jointly held resource refuses a grant carrying no verdicts at all",
      refused_jointly(d), d.error)

print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
if FAILED:
    raise SystemExit(1)
