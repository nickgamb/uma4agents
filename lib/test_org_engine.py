"""The organization's policy engine, when it forgets what it was told.

OPA holds the organization's modules in memory, and they are pushed by the
organization authority rather than read from disk. An engine that restarts on
its own comes back empty. This drives the authority's own decision path
against a fake engine that can lose its modules, and asserts that the
authority puts them back and asks again — and that when the engine still has
no answer, or cannot be reached, the request is refused, never allowed.

Run with `make org-test`.
"""

import asyncio
import copy
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "lib"), str(ROOT / "services" / "org-authority")]
os.environ["ORG_SIGNING_KEY"] = str(Path(tempfile.mkdtemp(prefix="u4a-org-")) / "key.pem")
os.environ["ORG_ADMIN_ISSUER"] = ""
os.environ["ORG_ADMIN_TOKEN"] = "test"

import httpx  # noqa: E402

import charter as charter_mod  # noqa: E402

spec = importlib.util.spec_from_file_location("org_app", ROOT / "services/org-authority/app.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

PASSED = FAILED = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if ok:
        PASSED += 1
        print(f"ok   {name}")
    else:
        FAILED += 1
        print(f"FAIL {name}  {detail}")


class Engine:
    """Just enough of OPA: modules by id, and a decision only while the
    organization's module is loaded."""

    def __init__(self):
        self.modules: dict[str, str] = {}
        self.up = True
        self.stays_empty = False
        self.decisions = 0

    async def __call__(self, method: str, path: str, **kw) -> httpx.Response:
        request = httpx.Request(method, f"http://opa{path}")
        if not self.up:
            raise httpx.ConnectError("connection refused", request=request)
        if path.startswith("/v1/policies/"):
            name = path.rsplit("/", 1)[-1]
            if method == "PUT" and not self.stays_empty:
                self.modules[name] = kw["content"].decode()
            elif method == "DELETE":
                self.modules.pop(name, None)
            return httpx.Response(200, json={}, request=request)
        self.decisions += 1
        if "u4a-org" not in self.modules:
            return httpx.Response(200, json={}, request=request)
        return httpx.Response(200, json={"result": {
            "decision": {"effect": "allow", "because": []},
            "custom_loaded": "u4a-custom" in self.modules}}, request=request)


engine = Engine()
app.opa = engine
app.CHARTERS.append({"version": 1, "charter": charter_mod.validate(
    copy.deepcopy(charter_mod.DEFAULT_CHARTER)), "published_at": "", "by": "test"})
events: list[str] = []
real_event = app.event
app.event = lambda name, corr=None, **d: (events.append(name), real_event(name, corr, **d))


def decide(member: str = "alice", tool: str = "get_positions") -> dict:
    app._OPA_CACHE.clear()
    return asyncio.run(app.org_decision(member, {"resource_id": f"northwind-vault/{tool}"}))


asyncio.run(app.load_shipped_rego())

print("\n== an engine that holds the policy ==")
check("answers, and nothing is reloaded",
      decide()["effect"] == "allow" and "engine.reloaded" not in events)

print("\n== an engine that restarted and lost it ==")
engine.modules.clear()
events.clear()
result = decide()
check("the authority puts the modules back and asks again",
      result["effect"] == "allow" and "u4a-org" in engine.modules, str(result))
check("and says so in its record", "engine.reloaded" in events, str(events))
check("the next decision needs no reload",
      decide()["effect"] == "allow" and events.count("engine.reloaded") == 1)

print("\n== an engine that stays empty ==")
engine.modules.clear()
engine.stays_empty = True
result = decide()
check("is refused, not allowed, and says why",
      result["effect"] == "refuse" and "holds none of" in result["because"][0],
      str(result))
check("and does not call a running engine unreachable",
      "could not be reached" not in result["because"][0], str(result))
engine.stays_empty = False

print("\n== an engine that kept the base module and lost the admin's rules ==")
asyncio.run(app.load_shipped_rego())
app.CHARTERS.append({"version": 2, "charter": charter_mod.validate({
    **copy.deepcopy(charter_mod.DEFAULT_CHARTER),
    "rego": "package u4a.custom\n\ndeny contains \"no\" if false\n"}),
    "published_at": "", "by": "test"})
asyncio.run(app.load_custom_rego(app.current()["charter"]["rego"]))
events.clear()
check("a charter with rules, held in full, needs no reload",
      decide()["effect"] == "allow" and "engine.reloaded" not in events)
engine.modules.pop("u4a-custom")
result = decide()
check("the authority notices they are gone, puts them back and asks again",
      result["effect"] == "allow" and "u4a-custom" in engine.modules
      and "engine.reloaded" in events, str(result))
engine.modules.pop("u4a-custom")
engine.stays_empty = True
result = decide()
check("and refuses, naming them, when they will not stay",
      result["effect"] == "refuse"
      and "does not hold the organization's own rules" in result["because"][0],
      str(result))
engine.stays_empty = False

print("\n== an engine that cannot be reached ==")
engine.up = False
result = decide()
check("is refused, not allowed, as unreachable",
      result["effect"] == "refuse" and "could not be reached" in result["because"][0],
      str(result))
engine.up = True

print("\n== a break-glass window she cannot be told about ==")
from fastapi import HTTPException  # noqa: E402
from unittest.mock import AsyncMock  # noqa: E402

app.CHARTERS.append({"version": 3, "charter": charter_mod.validate({
    **copy.deepcopy(charter_mod.DEFAULT_CHARTER),
    "claims": ["northwind-vault/*"],
    "break_glass": {"enabled": True, "resources": ["northwind-vault/*"],
                    "require_reason": True}}),
    "published_at": "", "by": "test"})
app.MEMBERS["alice"] = {"owner": "alice", "token_jti": "m1", "role": None}
app.require_admin = lambda request: "dana"
app.notify_member = AsyncMock(return_value=False)


class Open:
    async def json(self):
        return {"owner": "alice", "reason": "regulatory hold", "window_s": 60}


before = set(app.VOUCHERS)
try:
    asyncio.run(app.admin_open_voucher(Open()))
    check("is not opened", False, "opened")
except HTTPException as exc:
    check("is not opened, and the administrator is told why",
          exc.status_code == 503 and set(app.VOUCHERS) == before, str(exc.detail))

print("\n-- where its counterparts reach it --")
meta = asyncio.run(app.discovery())
check("it advertises every endpoint a member's authority and an enforcement point call",
      all(meta.get(k) for k in (
          "enrolment_endpoint", "enrolment_preview_endpoint", "invitation_endpoint",
          "leave_endpoint", "envelope_endpoint", "decision_endpoint", "clearance_endpoint",
          "compliance_endpoint", "membership_endpoint", "introspection_endpoint",
          "consumption_endpoint", "audit_endpoint")),
      str(sorted(meta)))

print("\n-- what a member's authority presents, and what it is told --")


class Member:
    def __init__(self, token: str, body: dict | None = None):
        self.headers = {"authorization": f"Bearer {token}"}
        self._body = body or {}

    async def json(self):
        return self._body


app.MEMBERS["bob"] = {"owner": "bob", "token_jti": "", "role": None, "as_uri": "https://bob-as.example",
                      "charter_version": 1, "compliance": None, "clearance": {}}
current_token = app.membership_token("bob")
stale_token = app.membership_token("bob")
app.MEMBERS["bob"]["token_jti"] = app.jwt.decode(current_token, options={"verify_signature": False})["jti"]
try:
    asyncio.run(app.member_envelope(Member(stale_token)))
    check("a membership credential from an earlier enrolment opens nothing", False, "opened")
except HTTPException as exc:
    check("a membership credential from an earlier enrolment opens nothing",
          exc.status_code == 403, str(exc.detail))
try:
    asyncio.run(app.member_clearance(Member(current_token)))
    check("no attestation is a 404, not an empty one", False, "answered")
except HTTPException as exc:
    check("no attestation is a 404, not an empty one", exc.status_code == 404, str(exc.detail))
asyncio.run(app.member_compliance(Member(current_token, {
    "charter_version": 1, "resources_governed": 2, "tiers_governed": 1,
    "clamped_fields": ["max_expires_in"], "within": True,
    "tiers": {"tier1": {"scopes": ["positions:read"]}}})))
check("a compliance report keeps counts and field names, nothing from her policy",
      "tiers" not in app.MEMBERS["bob"]["compliance"]
      and app.MEMBERS["bob"]["compliance"]["clamped_fields"] == ["max_expires_in"],
      str(app.MEMBERS["bob"]["compliance"]))

print(f"\n{PASSED} passed, {FAILED} failed")
sys.exit(1 if FAILED else 0)
