"""Kwaai's pAI-OS, running in the lab, deciding for Alice.

Not a description of an integration — the integration, running. pAI-OS is
built from a pinned upstream ref, the U4A ability is installed under its
`abilities/` directory in the layout it scans for, and the ability holds
Alice's key and answers her authorization server.

Three things are checked, and the third is the one worth reading:

  1. pAI-OS discovers the ability. Its own AbilitiesManager finds it, parses
     its metadata, and reports the start command and dependencies.
  2. On a tier she has given standing consent to, the ability answers and the
     agent gets its grant.
  3. On an ask-me tier, the ability **refuses** — because pAI-OS gives an
     ability no channel to its person, and a request pends precisely because
     she has not said yes. The refusal is logged with the exact operation.

The third is the open question with Kwaai, demonstrated rather than asserted.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, "/opt/paios")
sys.path.insert(0, os.environ.get("U4A_LIB", "/opt/u4a/lib"))

import httpx  # noqa: E402

from uma4a_grant import (  # noqa: E402
    AgentKeys, GrantDenied, mcp_call, mcp_meta, parse_challenge, run_grant,
)

GATEWAY = os.environ.get("UMA4A_GATEWAY", "https://gateway.uma.lab/mcp")
CA = os.environ.get("U4A_CA_BUNDLE", "/certs/rootCA.pem")
LOG = os.environ.get("U4A_ABILITY_LOG", "/opt/paios/data/ability.log")
META = mcp_meta("u4a-paios-check")


def say(msg: str) -> None:
    print(f"   {msg}", flush=True)


ORDER = {"symbol": "VTI", "side": "sell", "quantity": 40}


def negotiate(client: httpx.Client, tool: str, keystore: str,
              arguments: dict | None = None):
    """One negotiation, as a real agent would make it.

    An ask-me tier is *per-operation*, so the signed contract has to name the
    operation and its parameters — that is what the owner is shown and what
    the grant is bound to. Calling with empty arguments gets the contract
    rejected by the authorization server before it ever pends, which looks
    like a refusal and is not the refusal under test.
    """
    args = arguments if arguments is not None else {}
    operation = {"tool": tool, "params": args} if args else None
    r = mcp_call(client, GATEWAY, "tools/call",
                 {"name": tool, "arguments": args}, META)
    ch = parse_challenge(r.headers.get("www-authenticate", ""))
    if ch is None:
        raise SystemExit(f"no challenge for {tool}: {r.status_code}")
    keys = AgentKeys.load_or_create(keystore)
    return run_grant(client, ch.as_uri, ch.ticket, keys, lambda t: True,
                     operation=operation, on_status=lambda m: say(f"[agent] {m}"))


def main() -> int:
    ca = CA if os.path.exists(CA) else True
    import uuid

    run = uuid.uuid4().hex[:8]

    print("\n== pAI-OS finds the ability ==")
    # Its own loader, in its own process. Not our reading of its layout.
    from backend.managers.AbilitiesManager import AbilitiesManager

    ab = next((a for a in AbilitiesManager().abilities
               if a.get("id", "").startswith("u4a")), None)
    if ab is None:
        print("FAIL: pAI-OS did not discover the ability")
        return 1
    say(f"{ab['id']} — {ab['name']}")
    say(f"start: {ab['scripts']['start']}   "
        f"dependencies: {', '.join(d['id'] for d in ab['dependencies'])}")
    say("found by its own AbilitiesManager, under abilities/<id>/<semver>/")

    with httpx.Client(verify=ca) as client:
        print("\n== A tier she has given standing consent to ==")
        try:
            negotiate(client, "get_positions", f"/driver/keys/paios-t1-{run}.pem")
        except GrantDenied as exc:
            print(f"FAIL: the ability did not answer a standing-consent tier: {exc}")
            return 1
        say("granted — the personal AI answered, she was not disturbed")

        print("\n== An ask-me tier, which needs her ==")
        denied = False
        try:  # the ability must be the thing that refuses it
            negotiate(client, "execute_trade", f"/driver/keys/paios-t3-{run}.pem",
                      ORDER)
        except GrantDenied:
            denied = True
        if not denied:
            print("FAIL: an ask-me tier was granted without her")
            return 1
        say("refused — and that is correct")

    logs = open(LOG).read() if os.path.exists(LOG) else ""
    if '"event": "decided.standing"' not in logs:
        print("FAIL: no standing decision in the ability's log")
        return 1
    if '"event": "cannot-ask"' not in logs:
        print("FAIL: the ability did not record why it could not answer")
        return 1
    reason = json.loads([l for l in logs.splitlines() if "cannot-ask" in l][-1])
    say("it recorded what it could not do:")
    say(f"  {reason['summary'][:110]}")
    say(f"  {reason['outcome']}")

    print("\nPASS: pAI-OS hosted the ability, and the ability decided for her.")
    print("      Where it could not reach her it refused, which is the safe")
    print("      answer and the open question to take to Kwaai.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
