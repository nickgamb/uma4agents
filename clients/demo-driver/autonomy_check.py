"""Earned autonomy — the CSA Agentic Trust Framework's ladder, twice.

ATF describes one ladder: intern, junior, senior, principal, climbed by an
agent as the organisation running it comes to trust it. Under UMA there are
two parties where ATF has one — the operator running the agent and the owner
whose things it asks for — so every agent stands on two ladders at once. This
check runs Bob's agents up and down both, against the running stack, and
asserts the four things the composition rests on:

  1. **A stranger is an intern with her**, whatever its operator says. An
     agent its own firm has made a principal still cannot place a trade the
     first time it meets Alice.
  2. **Only she raises her ladder**, one rung at a time, and a stale view of
     it cannot overwrite a move she did not see.
  3. **The operator's ladder can only tighten.** An agent its firm still
     calls an intern stays out of her trades however far she promotes it.
  4. **Whichever stands lower governs**, and lowering either one takes
     effect on the agent's next request — demotion by her, or revocation,
     which makes it an intern again when she readmits it.

Every one of these is an ordinary rule in her trade tier: the profile is a
preset of conditions her policy vocabulary already had, saved through the
same validation as anything she types. Her policy is put back afterwards.

Run against the full stack with `make autonomy-check`. It also runs against
the fixture's shape — no identity provider, no gateway — when
UMA4A_OWNER_KEY names Alice's own key: her owner-API requests are then signed
with it (RFC 9421) instead of carrying a token from her realm, exactly as
`fixture_check.py` does, and UMA4A_GATEWAY names the resource itself.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import uuid

import httpx

sys.path.insert(0, "/driver/lib")
from uma4a_grant import (  # noqa: E402
    AgentKeys, GrantDenied, mcp_call, mcp_json, mcp_meta, parse_challenge,
    run_grant,
)
from uma4a_http_sig import jwk_thumbprint  # noqa: E402
from uma4a_http_sig import sign as http_sign  # noqa: E402

GATEWAY = os.environ.get("UMA4A_GATEWAY", "https://gateway.uma.lab/mcp")
AS_PUBLIC = os.environ.get("UMA4A_AS", "https://alice-as.uma.lab")
KEYCLOAK = os.environ.get("UMA4A_OIDC", "https://keycloak.uma.lab")
OPERATOR = os.environ.get("UMA4A_AGENT_OPERATOR", "https://agent.uma.lab")
CA = os.environ.get("UMA4A_CACERT", "/driver/rootCA.pem")
# Set where Alice authenticates with a key she holds rather than through an
# identity provider: the fixture's shape.
OWNER_KEY = os.environ.get("UMA4A_OWNER_KEY")
OWNER_AUTHORITY = os.environ.get("UMA_AS_OWNER_AUTHORITY", "alice-as.local")
KEYS = "/driver/keys"
RUN = uuid.uuid4().hex[:8]
META = mcp_meta("u4a-autonomy-check")
TRADE = {"symbol": "VTI", "side": "buy", "quantity": 1}
UMA_CHALLENGE = -32001

PASS, FAIL = [], []


def say(msg: str) -> None:
    print(f"   {msg}", flush=True)


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"   {'ok  ' if ok else 'FAIL'} {name}" + (f" — {detail}" if detail else ""),
          flush=True)


# --- her side ---------------------------------------------------------------


def owner_hdrs(client: httpx.Client) -> dict:
    """Her credential from her realm. Only used where there is one."""
    r = client.post(f"{KEYCLOAK}/realms/alice/protocol/openid-connect/token",
                    data={"grant_type": "password", "client_id": "meridian-portal",
                          "username": "alice",
                          "password": os.environ.get("ALICE_PASSWORD", "alice-demo")},
                    timeout=15.0)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def owner(client: httpx.Client, method: str, path: str,
          body: dict | None = None, params: dict | None = None) -> httpx.Response:
    """One owner-API request, however this deployment lets her make one."""
    target = path + (f"?{httpx.QueryParams(params)}" if params else "")
    raw = json.dumps(body).encode() if body is not None else None
    if OWNER_KEY:
        from cryptography.hazmat.primitives import serialization
        with open(OWNER_KEY, "rb") as fh:
            key = serialization.load_pem_private_key(fh.read(), password=None)
        headers = http_sign(method=method, authority=OWNER_AUTHORITY, path=target,
                            authorization="", key=key, keyid="owner", body=raw)
    else:
        headers = owner_hdrs(client)
    if raw is not None:
        headers["Content-Type"] = "application/json"
    return client.request(method, f"{AS_PUBLIC}{target}", headers=headers,
                          content=raw, timeout=15.0)


def listen(client: httpx.Client, seen: list, stop: threading.Event) -> None:
    """Her event stream, as her portal holds it: every event type that
    arrives is appended to `seen` until `stop` is set."""
    def loop() -> None:
        if OWNER_KEY:
            from cryptography.hazmat.primitives import serialization
            with open(OWNER_KEY, "rb") as fh:
                key = serialization.load_pem_private_key(fh.read(), password=None)
            headers = http_sign(method="GET", authority=OWNER_AUTHORITY,
                                path="/owner/events", authorization="", key=key,
                                keyid="owner")
        else:
            headers = owner_hdrs(client)
        try:
            with client.stream("GET", f"{AS_PUBLIC}/owner/events", headers=headers,
                               timeout=httpx.Timeout(10.0, read=None)) as r:
                for line in r.iter_lines():
                    if stop.is_set():
                        return
                    if line.startswith("event:"):
                        seen.append(line.split(":", 1)[1].strip())
        except Exception:                                          # noqa: BLE001
            return

    threading.Thread(target=loop, daemon=True).start()


def pending(client: httpx.Client) -> list:
    return owner(client, "GET", "/owner/pending").json()


def decide_all(client: httpx.Client, decision: str) -> int:
    n = 0
    for p in pending(client):
        owner(client, "POST", f"/owner/pending/{p['family']}/decision",
              {"decision": decision})
        n += 1
    return n


def approve_in_background(client: httpx.Client, seconds: float) -> threading.Event:
    """Alice, saying yes to whatever reaches her. Blind on purpose: what this
    check is about is what reaches her at all."""
    stop = threading.Event()

    def loop() -> None:
        deadline = time.time() + seconds
        while time.time() < deadline and not stop.is_set():
            try:
                decide_all(client, "approved")
            except Exception:                                      # noqa: BLE001
                pass
            time.sleep(0.8)

    threading.Thread(target=loop, daemon=True).start()
    return stop


def connection(client: httpx.Client, keys: AgentKeys) -> dict:
    """Her record of this agent. A pseudonymous agent's handle is its key's
    RFC 7638 thumbprint, so this run's agents are found by key, not by the
    operator document they name — which earlier runs' agents named too."""
    handle = jwk_thumbprint(keys.public_jwk())
    rows = owner(client, "GET", "/owner/connections").json()
    return next((c for c in rows if c["handle"] == handle), {})


def move(client: httpx.Client, handle: str, level: str,
         expect: str | None = None) -> httpx.Response:
    return owner(client, "POST", "/owner/connections/autonomy",
                 {"handle": handle, "level": level,
                  **({"expect": expect} if expect else {})})


def ledger(client: httpx.Client, handle: str) -> list:
    return owner(client, "GET", "/owner/ledger", params={"handle": handle}).json()


# --- the agent's side --------------------------------------------------------


def negotiate(client: httpx.Client, keys: AgentKeys, tool: str,
              arguments: dict | None = None, max_wait_s: int = 25):
    """One negotiation: (granted, asked, why-not)."""
    args = arguments or {}
    r = mcp_call(client, GATEWAY, "tools/call",
                 {"name": tool, "arguments": args}, META)
    ch = parse_challenge(r.headers.get("www-authenticate", ""))
    if ch is not None:
        as_uri, ticket = ch.as_uri, ch.ticket
    else:
        # A resource enforcing in-process (the fixture's shape) answers in
        # MCP's own terms rather than HTTP's: a JSON-RPC error carrying the
        # same ticket and authority.
        err = (mcp_json(r).get("error") or {})
        if err.get("code") != UMA_CHALLENGE:
            raise SystemExit(f"no challenge for {tool}: {r.status_code}")
        as_uri, ticket = err["data"]["as_uri"], err["data"]["ticket"]
    asked = {"v": False}

    def status(msg: str) -> None:
        if "has been asked" in msg:
            asked["v"] = True

    try:
        run_grant(client, as_uri, ticket, keys, lambda t: True,
                  operation=({"tool": tool, "params": args} if args else None),
                  on_status=status, max_wait_s=max_wait_s)
        return True, asked["v"], None
    except GrantDenied as exc:
        return False, asked["v"], str(exc)


def agent(name: str, document: str) -> AgentKeys:
    keys = AgentKeys.load_or_create(f"{KEYS}/autonomy-{name}-{RUN}.pem")
    keys.client_id = f"{OPERATOR}{document}"
    return keys


def climb(client: httpx.Client, handle: str, to: str) -> list[str]:
    """Promote one rung at a time to `to`, as she would have to. Returns the
    levels it passed through."""
    rungs = ["intern", "junior", "senior", "principal"]
    seen = []
    view = owner(client, "GET", "/owner/connections/autonomy",
                 params={"handle": handle}).json()
    at = rungs.index(view.get("level") or "intern")
    while rungs[at] != to:
        r = move(client, handle, rungs[at + 1], expect=rungs[at])
        if r.status_code >= 300:
            raise SystemExit(f"promotion to {rungs[at + 1]} refused: {r.text}")
        at += 1
        seen.append(rungs[at])
    return seen


def main() -> int:
    ca = CA if os.path.exists(CA) else True
    with httpx.Client(verify=ca, timeout=30.0) as client:
        decide_all(client, "denied")
        tiers = owner(client, "GET", "/owner/policies").json()
        trade_tier, held = next(
            (t, v) for t, v in tiers.items()
            if "alice-vault/execute_trade" in (v.get("resources") or []))
        presets = owner(client, "GET", "/owner/policy-presets").json()
        profile = next(p for p in presets if p["id"] == "earned-autonomy")["rules"]
        # Hers as she wrote them, so a run that died half way does not make
        # the profile permanent by restoring it.
        hers = [r for r in held.get("rules") or [] if r not in profile]
        made: list[AgentKeys] = []

        try:
            print("\n== The profile is rules she could have written ==")
            r = owner(client, "PUT", f"/owner/policies/{trade_tier}",
                      {"rules": hers + profile})
            check("she adds the earned-autonomy preset to her trade tier",
                  r.status_code < 300, r.text[:200])
            say(f"{len(profile)} rules, every condition from her existing vocabulary")
            bad = owner(client, "PUT", f"/owner/policies/{trade_tier}",
                        {"rules": hers + profile + [
                            {"when": ["operator.autonomy_below:principal"],
                             "then": "auto"}]})
            check("a rule relaxing on the operator's ladder cannot be saved",
                  bad.status_code == 400 and "operator" in bad.text, bad.text[:200])
            bad = owner(client, "PUT", f"/owner/policies/{trade_tier}",
                        {"rules": hers + profile + [
                            {"when": ["standing.autonomy_at_least:intern"],
                             "then": "auto"}]})
            check("nor one relaxing on 'at least an intern', which every stranger is",
                  bad.status_code == 400, bad.text[:200])

            # Bob's firm runs two kinds of agent, and has put them on
            # different rungs of its own ladder.
            advisor = agent("advisor", "/agent.json")
            researcher = agent("researcher", "/agents/research.json")
            made += [advisor, researcher]
            for keys, doc in ((advisor, "/agent.json"),
                              (researcher, "/agents/research.json")):
                said = client.get(f"{OPERATOR}{doc}", timeout=15.0).json()
                say(f"{doc}: operator declares "
                    f"{(said.get('atf') or {}).get('maturity_level')}")

            print("\n== A principal at its firm is an intern with her ==")
            approving = approve_in_background(client, 150)
            ok, asked, _ = negotiate(client, advisor, "get_positions")
            check("the advisor meets her by reading her holdings", ok and asked)
            conn = connection(client, advisor)
            view = conn.get("autonomy_view") or {}
            check("its firm says principal; she says intern",
                  view.get("operator", {}).get("level") == "principal"
                  and view.get("level") == "intern", str(view))
            handle = conn.get("handle", "")

            ok, asked, why = negotiate(client, advisor, "execute_trade", TRADE,
                                       max_wait_s=5)
            check("an intern's trade is refused without reaching her",
                  not ok and not asked, why or "")
            check("and the refusal names her ladder, not its firm's",
                  "standing.autonomy_below:junior" in (why or ""), why or "")

            print("\n== Only she raises it, one rung at a time ==")
            r = move(client, handle, "senior", expect="intern")
            check("she cannot skip a rung", r.status_code == 400, r.text[:160])
            r = move(client, handle, "junior", expect="intern")
            check("she promotes it to junior", r.status_code < 300, r.text[:160])
            ok, asked, why = negotiate(client, advisor, "execute_trade", TRADE)
            check("a junior's trade is put to her, and goes through when she says yes",
                  ok and asked, why or "")
            r = move(client, handle, "senior", expect="intern")
            check("a promotion from a view that has gone stale is refused",
                  r.status_code == 409, r.text[:160])

            climb(client, handle, "senior")
            ok, asked, why = negotiate(client, advisor, "execute_trade", TRADE)
            check("a senior still asks about what cannot be undone",
                  ok and asked, why or "")

            approving.set()
            time.sleep(1.5)
            decide_all(client, "denied")
            climb(client, handle, "principal")
            events: list[str] = []
            hearing = threading.Event()
            with httpx.Client(verify=ca, timeout=30.0) as stream_client:
                listen(stream_client, events, hearing)
                time.sleep(1.0)
                ok, asked, why = negotiate(client, advisor, "execute_trade", TRADE,
                                           max_wait_s=10)
                time.sleep(1.5)
                hearing.set()
            check("a principal with her, and with its firm, trades without asking",
                  ok and not asked, why or "")
            check("and she is told it acted, as it happens — ATF's act and notify",
                  "acted" in events, str(events))
            relaxed = [e for e in ledger(client, handle) if e.get("kind") == "relaxed"]
            check("and her record says which of her decisions let it",
                  any("standing.autonomy_at_least:senior" in (e.get("because") or [])
                      for e in relaxed), str(relaxed[-1:]))
            moves = [e["kind"] for e in ledger(client, handle)
                     if e.get("kind", "").startswith("autonomy_")]
            check("every promotion is in her record, by her",
                  moves.count("autonomy_promoted") == 3, str(moves))

            print("\n== The operator's ladder can only tighten ==")
            approving = approve_in_background(client, 150)
            ok, asked, _ = negotiate(client, researcher, "get_positions")
            check("the researcher meets her too", ok and asked)
            r_conn = connection(client, researcher)
            r_handle = r_conn.get("handle", "")
            check("its firm declares it an intern",
                  (r_conn.get("autonomy_view") or {}).get("operator", {}).get("level")
                  == "intern", str(r_conn.get("autonomy_view")))
            passed = climb(client, r_handle, "principal")
            say(f"she promotes it: {' → '.join(passed)}")
            ok, asked, why = negotiate(client, researcher, "execute_trade", TRADE,
                                       max_wait_s=5)
            check("her principal stays out of her trades while its firm calls it an intern",
                  not ok and not asked, why or "")
            check("and the refusal names the operator's ladder",
                  "operator.autonomy_below:junior" in (why or ""), why or "")
            say("whichever stands lower governs — and only hers could ever relax")

            print("\n== Lowering either takes effect at once ==")
            r = move(client, handle, "junior", expect="principal")
            check("she demotes the advisor two rungs in one step",
                  r.status_code < 300, r.text[:160])
            ok, asked, why = negotiate(client, advisor, "execute_trade", TRADE)
            check("and its next trade is put to her again", ok and asked, why or "")

            owner(client, "POST", "/owner/connections/revoke", {"handle": handle})
            ok, asked, _ = negotiate(client, advisor, "get_positions")
            again = connection(client, advisor)
            check("revoked and readmitted, it is an intern again",
                  ok and asked
                  and (again.get("autonomy_view") or {}).get("level") == "intern",
                  str(again.get("autonomy_view")))
            ok, asked, why = negotiate(client, advisor, "execute_trade", TRADE,
                                       max_wait_s=5)
            check("and an intern's trade is refused, as on the first day",
                  not ok and not asked, why or "")
            approving.set()
        finally:
            restored = owner(client, "PUT", f"/owner/policies/{trade_tier}",
                             {"rules": hers})
            check("her trade tier is put back as she wrote it",
                  restored.status_code < 300, restored.text[:160])
            time.sleep(1.0)
            decide_all(client, "denied")
            # This run's agents only. Its keys are new each run, so nothing it
            # leaves connected would ever be used again.
            for keys in made:
                conn = connection(client, keys)
                if conn.get("status") == "active":
                    owner(client, "POST", "/owner/connections/revoke",
                          {"handle": conn["handle"]})

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        return 1
    print("\nPASS: every agent started as an intern with her whatever its firm said,")
    print("      only she promoted it and one rung at a time, the firm's own")
    print("      ladder only ever made her rules stricter, and lowering either")
    print("      ladder took effect on the agent's next request.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
