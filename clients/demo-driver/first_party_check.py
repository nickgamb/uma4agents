"""The degenerate case: an agent Alice activated herself.

RO == RqP, and the requesting *agent* is still a third thing. She is not at the
keyboard, it holds its own key, and her policy governs every request it makes.
So the grant does not change, and this check exists to prove that rather than
to assert it.

**Her signals arrive the way anyone's would.** An agent is first-party when the
operator it names is an origin she claimed *and* her authority found that
agent's signing key in that operator's own key directory. Both halves, and the
second is the one with teeth:

    a metadata document proves only that it claims the URL it came from,
    so any agent may point at one she publishes;
    only she can put a key in her directory.

Without that, "this is my agent" would be a sentence an agent could say about
itself — and it is the one fact in the profile that makes a requirement looser,
so it is the one place a claim can never be enough.

**Being hers buys less friction, never more access.** Her tiers are the ceiling
either way. A first-party agent on a tier she reserved is asked, exactly like
anybody else's, until she writes a rule saying otherwise — and the rule she
writes names no agent.

Run against the full stack with `make first-party-check`.
"""

from __future__ import annotations

import os
import sys
import time
import uuid

import httpx

sys.path.insert(0, "/driver/lib")
from uma4a_grant import (  # noqa: E402
    AgentKeys, GrantDenied, mcp_call, mcp_meta, parse_challenge, run_grant,
)

GATEWAY = os.environ.get("UMA4A_GATEWAY", "https://gateway.uma.lab/mcp")
AS_PUBLIC = os.environ.get("UMA4A_AS", "https://alice-as.uma.lab")
KEYCLOAK = os.environ.get("UMA4A_OIDC", "https://keycloak.uma.lab")
HER_OPERATOR = os.environ.get("UMA4A_ALICE_OPERATOR", "https://alice-agent.uma.lab")
HIS_OPERATOR = os.environ.get("UMA4A_AGENT_OPERATOR", "https://agent.uma.lab")
CA = os.environ.get("UMA4A_CACERT", "/driver/rootCA.pem")
KEYS = "/driver/keys"
RUN = uuid.uuid4().hex[:8]
META = mcp_meta("u4a-first-party-check")

PASS, FAIL = [], []


def say(msg: str) -> None:
    print(f"   {msg}", flush=True)


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"   {'ok  ' if ok else 'FAIL'} {name}"
          + (f" — {detail}" if detail and not ok else ""), flush=True)


def hdrs(client: httpx.Client) -> dict:
    r = client.post(f"{KEYCLOAK}/realms/alice/protocol/openid-connect/token",
                    data={"grant_type": "password", "client_id": "meridian-portal",
                          "username": "alice",
                          "password": os.environ.get("ALICE_PASSWORD", "alice-demo")},
                    timeout=15.0)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def operators(client: httpx.Client) -> dict:
    rows = client.get(f"{AS_PUBLIC}/owner/operators", headers=hdrs(client),
                      timeout=15.0).json()
    return {r["origin"]: r for r in rows}


def negotiate(client, keys, tool, args=None, max_wait_s=12):
    """One negotiation. Returns (granted, asked)."""
    r = mcp_call(client, GATEWAY, "tools/call",
                 {"name": tool, "arguments": args or {}}, META)
    ch = parse_challenge(r.headers.get("www-authenticate", ""))
    if ch is None:
        # The body, not just the code. A bare status here sends whoever is
        # debugging to the wrong layer: 403 from the gateway, from the pend
        # budget and from a revoked connection all look identical until you
        # read what came back.
        raise SystemExit(f"no challenge for {tool}: {r.status_code} {r.text[:300]}")
    asked = {"v": False}

    def status(msg: str) -> None:
        if "has been asked" in msg:
            asked["v"] = True

    op = ({"tool": tool, "params": args} if tool == "execute_trade" else None)
    try:
        run_grant(client, ch.as_uri, ch.ticket, keys, lambda t: True,
                  operation=op, on_status=status, max_wait_s=max_wait_s)
        return True, asked["v"]
    except GrantDenied:
        return False, asked["v"]
    except Exception as exc:                                   # noqa: BLE001
        # Not swallowed into "she was asked". A timeout, a refused commit and
        # a genuine pend are three different outcomes, and reporting all of
        # them as the third sends the reader looking at policy when the fault
        # is somewhere else entirely.
        say(f"   [negotiate {tool}] {type(exc).__name__}: {str(exc)[:200]}")
        return False, asked["v"]


def set_rules(client, tier: str, rules: list) -> None:
    r = client.put(f"{AS_PUBLIC}/owner/policies/{tier}", json={"rules": rules},
                   headers=hdrs(client), timeout=15.0)
    r.raise_for_status()


def decide_all(client, decision: str) -> int:
    h, n = hdrs(client), 0
    for p in client.get(f"{AS_PUBLIC}/owner/pending", headers=h,
                        timeout=15.0).json():
        client.post(f"{AS_PUBLIC}/owner/pending/{p['family']}/decision",
                    json={"decision": decision}, headers=h, timeout=15.0)
        n += 1
    return n


def approving(client, seconds: float):
    import threading
    import time as _t
    stop = threading.Event()

    def loop() -> None:
        end = _t.time() + seconds
        while _t.time() < end and not stop.is_set():
            try:
                decide_all(client, "approved")
            except Exception:                                  # noqa: BLE001
                pass
            _t.sleep(0.8)

    threading.Thread(target=loop, daemon=True).start()
    return stop


# ---------------------------------------------------------------------------
# The contrast, with her actually deciding
#
# One rule, one tier, two agents. Hers trades without waking her; an attested
# agent that is somebody else's is asked anyway. The suite proves that with a
# background approver; this puts the asking in front of a person, because
# "she was not asked" only means something if you have just watched her be
# asked about the other one.
#
# Her first contacts are answered here rather than by her. They are the same
# handshake every other demo already shows, and three taps before the contrast
# starts is how a room loses the thread.
# ---------------------------------------------------------------------------

PORTAL = os.environ.get("UMA4A_PORTAL", "https://portal.uma.lab")


def live(wait_s: int) -> int:
    with httpx.Client(verify=CA, timeout=60.0, follow_redirects=True) as client:
        h = hdrs(client)
        print("\n== An agent she activated herself ==")
        client.post(f"{AS_PUBLIC}/owner/operators/claim",
                    json={"origin": HER_OPERATOR}, headers=h, timeout=15.0)
        print(f"   she claims the origin: {HER_OPERATOR}")
        set_rules(client, "tier3", [{"when": ["standing.first_party"],
                                     "then": "auto"}])
        print("   her rule on tier 3: an agent of hers may trade without asking")
        print("   the rule names no agent — only that it is hers")

        # From here on the rule is in place, and it has to come back out
        # however this run ends. Leaving `standing.first_party -> auto` on her
        # trade tier is not a cosmetic leftover: it is a live relaxation of her
        # policy that the next demo inherits, and it is how a later run of
        # org-check started failing for reasons that had nothing to do with it.
        try:
            return _live_body(client, h, wait_s)
        finally:
            set_rules(client, "tier3", [])
            print("\n   (her tier-3 rule has been put back)")


def _live_body(client: httpx.Client, h: dict, wait_s: int) -> int:
    hers = AgentKeys.load_or_create(f"{KEYS}/fp-live-hers-{RUN}.pem")
    hers.client_id = f"{HER_OPERATOR}/agent.json"
    hers.signature_agent = hers.publish(client, HER_OPERATOR)
    his = AgentKeys.load_or_create(f"{KEYS}/fp-live-his-{RUN}.pem")
    his.client_id = f"{HIS_OPERATOR}/agent.json"
    his.signature_agent = his.publish(client, HIS_OPERATOR)

    print("\n   connecting both agents (the ordinary first-contact handshake)")
    stop = approving(client, 90)
    try:
        negotiate(client, hers, "get_positions")
        negotiate(client, his, "get_positions")
    finally:
        stop.set()
    time.sleep(1.0)

    print("\n-- 1. her own agent asks to trade --")
    granted, asked = negotiate(client, hers, "execute_trade",
                               {"symbol": "VTI", "side": "buy", "quantity": 2},
                               max_wait_s=20)
    if granted and not asked:
        print("   granted, and she was never asked.")
        print("   Nothing appeared in her portal. Say so out loud.")
    else:
        print(f"   granted={granted} asked={asked} — expected a quiet grant")

    print("\n-- 2. the same rule, the same tier, Bob's agent --")
    print(f"   it is attested too, and it is not hers: {HIS_OPERATOR}")
    print(f"   Decide it at {PORTAL}  (alice / alice-demo)")
    print("   Settings -> Security -> Agent Authorization")
    granted, asked = negotiate(client, his, "execute_trade",
                               {"symbol": "VTI", "side": "buy", "quantity": 3},
                               max_wait_s=wait_s)
    print()
    if not asked:
        print("   it was not asked — the rule relaxed for an operator she")
        print("   never claimed, which would be the bug this demo looks for")
    elif granted:
        print("   she was asked, and she allowed it.")
    else:
        print("   she was asked, and she refused it.")
    print("\n== What that showed ==")
    print("   Being hers bought less friction and no more access. The")
    print("   ceiling is her tier either way, and the only thing that")
    print("   moved was whether she had to be woken.")
    return 0


def main() -> int:
    with httpx.Client(verify=CA, timeout=60.0, follow_redirects=True) as client:
        h = hdrs(client)

        # ---------------------------------------------------------------
        print("\n== Claiming an origin is a decision, and only half of one ==")
        # ---------------------------------------------------------------
        client.post(f"{AS_PUBLIC}/owner/operators/claim",
                    json={"origin": HER_OPERATOR}, headers=h, timeout=15.0)
        rows = operators(client)
        check("her origin shows as hers", (rows.get(HER_OPERATOR) or {}).get("mine") is True)
        check("Bob's does not", (rows.get(HIS_OPERATOR) or {}).get("mine") in (False, None))
        check("an https origin is required",
              client.post(f"{AS_PUBLIC}/owner/operators/claim",
                          json={"origin": "alice-agent.uma.lab"},
                          headers=h, timeout=15.0).status_code == 400)

        # ---------------------------------------------------------------
        print("\n== The impostor: her origin, a key she never published ==")
        # ---------------------------------------------------------------
        # This is the assertion the whole feature rests on. A Client ID
        # Metadata Document only claims the URL it was fetched from, so
        # pointing at hers is free. Putting a key in her directory is not.
        set_rules(client, "tier3", [{"when": ["standing.first_party"],
                                     "then": "auto"}])
        impostor = AgentKeys.load_or_create(f"{KEYS}/fp-impostor-{RUN}.pem")
        impostor.client_id = f"{HER_OPERATOR}/agent.json"      # claimed, not published

        stop = approving(client, 45)
        try:
            granted, asked = negotiate(client, impostor, "get_positions")
            check("it connects like any stranger", granted)
            granted, asked = negotiate(client, impostor, "execute_trade",
                                       {"symbol": "VTI", "side": "buy", "quantity": 1})
            check("but the trade tier still asks her about it", asked,
                  "it was auto-granted — naming her origin was enough, which is the bug")
        finally:
            stop.set()

        # ---------------------------------------------------------------
        print("\n== Her own agent: claimed origin, and a key she published ==")
        # ---------------------------------------------------------------
        hers = AgentKeys.load_or_create(f"{KEYS}/fp-hers-{RUN}.pem")
        hers.client_id = f"{HER_OPERATOR}/agent.json"
        hers.signature_agent = hers.publish(client, HER_OPERATOR)
        check("her operator published its key", bool(hers.signature_agent))

        stop = approving(client, 45)
        try:
            granted, _ = negotiate(client, hers, "get_positions")
            check("first contact still pends, and she connects it", granted)
        finally:
            stop.set()

        granted, asked = negotiate(client, hers, "execute_trade",
                                   {"symbol": "VTI", "side": "buy", "quantity": 2})
        check("her rule then grants a trade without asking", granted and not asked,
              f"granted={granted} asked={asked}")

        # ---------------------------------------------------------------
        print("\n== The same rule, the same tier, somebody else's agent ==")
        # ---------------------------------------------------------------
        his = AgentKeys.load_or_create(f"{KEYS}/fp-his-{RUN}.pem")
        his.client_id = f"{HIS_OPERATOR}/agent.json"
        his.signature_agent = his.publish(client, HIS_OPERATOR)

        stop = approving(client, 45)
        try:
            negotiate(client, his, "get_positions")
        finally:
            stop.set()
        granted, asked = negotiate(client, his, "execute_trade",
                                   {"symbol": "VTI", "side": "buy", "quantity": 3},
                                   max_wait_s=6)
        check("an attested agent that is not hers is still asked", asked,
              "the rule relaxed for an operator she never claimed")

        # ---------------------------------------------------------------
        print("\n== Disclaiming takes effect, and takes nothing away ==")
        # ---------------------------------------------------------------
        client.post(f"{AS_PUBLIC}/owner/operators/disclaim",
                    json={"origin": HER_OPERATOR}, headers=h, timeout=15.0)
        check("the origin is no longer hers",
              (operators(client).get(HER_OPERATOR) or {}).get("mine") is not True)
        granted, asked = negotiate(client, hers, "execute_trade",
                                   {"symbol": "VTI", "side": "buy", "quantity": 4},
                                   max_wait_s=6)
        check("her agent is asked again on the very next request", asked,
              "the relaxation outlived the claim")

        conns = client.get(f"{AS_PUBLIC}/owner/connections", headers=h,
                           timeout=15.0).json()
        check("and its connection survives — the claim bought friction, not access",
              any(c.get("status") == "active" for c in conns))

        # ---------------------------------------------------------------
        print("\n== And the rule is hers to write, not the agent's to earn ==")
        # ---------------------------------------------------------------
        r = client.post(f"{AS_PUBLIC}/owner/policies", headers=h, timeout=15.0,
                        json={"id": f"fp{RUN}", "name": "should not save",
                              "resources": [], "ask_me": True,
                              "rules": [{"when": ["assurance.accountability_below:2"],
                                         "then": "auto"}],
                              "terms": {"purpose": "x", "expires_in": 900}})
        check("a rule relaxing on what the agent showed is still unstorable",
              r.status_code >= 300)
        r = client.post(f"{AS_PUBLIC}/owner/policies", headers=h, timeout=15.0,
                        json={"id": f"fpok{RUN}", "name": "storable",
                              "resources": [], "ask_me": True,
                              "rules": [{"when": ["standing.first_party"],
                                         "then": "auto"}],
                              "terms": {"purpose": "x", "expires_in": 900}})
        check("a rule relaxing on whom she activated is storable", r.status_code < 300,
              r.text[:160])
        if r.status_code < 300:
            client.delete(f"{AS_PUBLIC}/owner/policies/fpok{RUN}", headers=h,
                          timeout=15.0)

        set_rules(client, "tier3", [])
        decide_all(client, "denied")

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        for f in FAIL:
            print(f"   FAILED: {f}")
        return 1
    print("\nPASS: an agent she activated herself ran the same grant as anyone")
    print("      else's, met less friction only where she had said so, and")
    print("      an impostor naming her origin got none of it.")
    return 0


if __name__ == "__main__":
    if os.environ.get("UMA4A_SIMULATE_OWNER", "1") == "0":
        raise SystemExit(live(int(os.environ.get("UMA4A_LIVE_WAIT_S", "900"))))
    raise SystemExit(main())
