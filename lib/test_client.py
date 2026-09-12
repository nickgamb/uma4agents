"""The agent's side of the grant, and the owner's side of a decision.

What these check is where a client's trust ends. An agent talks to resources
it has never heard of, and everything they send it — which provider to ask,
where that provider is, what a receipt is called, what a challenge looks like
— is something the other side chose. Some of it the agent should follow and
some it must not; this suite pins which is which. The owner ability is here
for the same reason from the other end: it is her answer, and a failure to
deliver it must not be recorded as delivered.

Run: make client-test
"""
import base64
import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "lib"), str(ROOT / "kwaai/ability")]

import httpx  # noqa: E402

from u4a_authority import OwnerAuthority  # noqa: E402
from uma4a_grant import (  # noqa: E402
    ID_JAG_CLAIM, Enterprise, GrantDenied, id_jag_request, jsonrpc_challenge,
    receipt_filename)

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASSED if ok else FAILED).append(name)
    print(("ok   " if ok else "FAIL ") + name + (f" — {detail}" if detail and not ok else ""))


def denied(name: str, attempt, because: str) -> None:
    try:
        attempt()
    except GrantDenied as exc:
        check(name, because in str(exc), str(exc))
        return
    check(name, False, "the credentials would have been sent")


print("\n== where enterprise credentials may go ==")


def asked(issuer="https://idp.example", endpoint="https://idp.example/oauth2/v1/token") -> dict:
    return {"claim_type": ID_JAG_CLAIM,
            "identity_provider": {"issuer": issuer, "token_endpoint": endpoint},
            "audience": "https://alice-as.example", "resource": "https://rs.example/mcp",
            "scope": ["get_positions"]}


def holding(**over) -> Enterprise:
    return Enterprise(**{"subject_token": "employee-token", "client_id": "app",
                         "client_secret": "app-secret", "issuer": "https://idp.example",
                         **over})


endpoint, payload = id_jag_request(asked(), holding())
check("the provider the credentials belong to is asked, at the endpoint it names",
      endpoint == "https://idp.example/oauth2/v1/token"
      and payload["client_secret"] == "app-secret")
denied("credentials that name no provider are sent nowhere",
       lambda: id_jag_request(asked(), holding(issuer="")), "name no identity provider")
denied("a challenge naming a different provider is refused",
       lambda: id_jag_request(asked(issuer="https://collector.example",
                                    endpoint="https://collector.example/token"), holding()),
       "belong to https://idp.example")
denied("a token endpoint off the provider's origin is refused",
       lambda: id_jag_request(asked(endpoint="https://collector.example/token"), holding()),
       "not at https://idp.example")
endpoint, _ = id_jag_request(asked(endpoint="https://collector.example/token"),
                             holding(token_endpoint="https://idp.example/custom/token"))
check("an endpoint the agent was configured with is used whatever the challenge says",
      endpoint == "https://idp.example/custom/token", endpoint)

print("\n== where a receipt is written ==")


def receipt(payload: dict) -> str:
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"header.{body}.signature"


check("a receipt is kept under its negotiation's name",
      receipt_filename(receipt({"family": "fam_Ab3-x_9"})) == "fam_Ab3-x_9.receipt.jws")
for family in ("../escaped", "/etc/cron.d/job", "a/b", "..", "", None):
    check(f"a family of {family!r} does not choose the path",
          receipt_filename(receipt({"family": family})) == "unknown.receipt.jws")
check("nor does a receipt that is not a token",
      receipt_filename("not-a-receipt") == "unknown.receipt.jws")

print("\n== the challenge a resource sends in-process ==")
emitted = {"jsonrpc": "2.0", "id": 1, "error": {
    "code": -32001, "message": "authorization required",
    "data": {"error": "insufficient_authorization", "as_uri": "https://alice-as.example",
             "ticket": "tkt-1", "resource_metadata": "https://rs.example/prm"}}}
check("the challenge the resource emits is recognised",
      jsonrpc_challenge(emitted) == ("https://alice-as.example", "tkt-1"))
check("an ordinary error is not mistaken for one",
      jsonrpc_challenge({"error": {"code": -32602, "message": "bad params"}}) is None)

print("\n== her answer, when it does not arrive ==")


class Host:
    def __init__(self) -> None:
        self.logs: list[tuple[str, dict]] = []
        self.asks = 0

    def sign(self, payload: bytes) -> bytes:
        return b"\x00" * 64

    def public_key_pem(self) -> bytes:
        return b""

    def ask(self, question) -> bool:
        self.asks += 1
        return True

    def log(self, event: str, detail: dict) -> None:
        self.logs.append((event, detail))


posts: list[int] = []


def authority(request: httpx.Request) -> httpx.Response:
    if request.method == "GET":
        return httpx.Response(200, json=[{"family": "fam_1", "kind": "operation",
                                          "tier": "tier3", "purpose": "sell 40 VTI"}])
    posts.append(1)
    return httpx.Response(500 if len(posts) == 1 else 200, json={})


host = Host()
rounds = iter([False, False, True])
with httpx.Client(transport=httpx.MockTransport(authority)) as client, \
        patch("u4a_authority.time.sleep", return_value=None):
    OwnerAuthority(host, "https://alice-as.example", "alice-as.example").run(
        should_stop=lambda: next(rounds), client=client)
events = [e for e, _ in host.logs]
check("she is asked once", host.asks == 1, f"asked {host.asks} times")
check("an answer her authority failed to record is sent again", len(posts) == 2,
      f"{len(posts)} attempts")
check("and is recorded as decided only once it was",
      events.count("decided") == 1
      and events.index("decision.unsent") < events.index("decided"), str(events))

print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
raise SystemExit(1 if FAILED else 0)
