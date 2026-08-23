"""Four agents, four identity regimes, one unchanged owner.

The claim this checks is the one that makes the whole design work, and it is
easy to state and easy to get wrong: **agent identity and governance stay on
the requesting side.** Alice sets her terms and her policy. She does not need
to know how Bob's agent is identified, who issued its credentials, whether its
keys rotate, or that any of those things exist.

So: run the same negotiation four times against the same authorization server,
with the requesting side arranged four different ways —

    pseudonymous    a bare Ed25519 key and nothing else. No issuer anywhere.
    identified      an AAuth aa-agent+jwt from Bob's agent server, with a
                    fresh session key each run
    described       a CIMD document saying who operates the agent
    published       a Web Bot Auth directory the key can be looked up in

— and compare what Alice's side did. Her policy, her tiers, the terms she
proffers and the shape of the grant she issues should be *identical*, and the
only thing that should move is the handle her connection is filed under.

If any identity signal had become an authorization input, this would show it:
the four runs would not agree.

Run against the full stack with `make flow-check`.
"""

from __future__ import annotations

import json
import os
import sys
import time

import httpx

sys.path.insert(0, "/driver/lib")
from uma4a_enroll import EnrollmentDenied, enroll  # noqa: E402
from uma4a_grant import (  # noqa: E402
    AgentKeys, GrantDenied, mcp_call, mcp_meta, parse_challenge, run_grant,
)

GATEWAY = os.environ.get("UMA4A_GATEWAY", "https://gateway.uma.lab/mcp")
AS_PUBLIC = os.environ.get("UMA4A_AS", "https://alice-as.uma.lab")
KEYCLOAK = os.environ.get("UMA4A_OIDC", "https://keycloak.uma.lab")
OPERATOR = os.environ.get("UMA4A_AGENT_OPERATOR", "https://agent.uma.lab")
ISSUER = os.environ.get("UMA4A_AGENT_ISSUER", "https://ps.uma.lab")
PS_ADMIN = os.environ.get("PS_ADMIN_TOKEN", "uma4agents-ps-admin")
CA = os.environ.get("UMA4A_CACERT", "/driver/rootCA.pem")
KEYS = "/driver/keys"

META = mcp_meta("u4a-flow-check")


def say(msg: str) -> None:
    print(f"   {msg}", flush=True)


def owner_token(client: httpx.Client) -> str:
    r = client.post(f"{KEYCLOAK}/realms/alice/protocol/openid-connect/token",
                    data={"grant_type": "password", "client_id": "meridian-portal",
                          "username": "alice",
                          "password": os.environ.get("ALICE_PASSWORD", "alice-demo")},
                    timeout=15.0)
    r.raise_for_status()
    return r.json()["access_token"]


def owner_get(client: httpx.Client, path: str) -> object:
    r = client.get(f"{AS_PUBLIC}{path}",
                   headers={"Authorization": f"Bearer {owner_token(client)}"},
                   timeout=15.0)
    r.raise_for_status()
    return r.json()


def approve_everything(client: httpx.Client, deadline: float) -> None:
    """Alice, answering. Deliberately blind to who is asking."""
    hdrs = {"Authorization": f"Bearer {owner_token(client)}"}
    while time.time() < deadline:
        try:
            for p in client.get(f"{AS_PUBLIC}/owner/pending", headers=hdrs,
                                timeout=10.0).json():
                client.post(f"{AS_PUBLIC}/owner/pending/{p['family']}/decision",
                            json={"decision": "approved"}, headers=hdrs, timeout=10.0)
        except Exception:                                          # noqa: BLE001
            pass
        time.sleep(1)


def challenge_for(client: httpx.Client, tool: str):
    r = mcp_call(client, GATEWAY, "tools/call",
                 {"name": tool, "arguments": {}}, META)
    ch = parse_challenge(r.headers.get("www-authenticate", ""))
    if ch is None:
        raise SystemExit(f"no UMA challenge from the gateway: {r.status_code} "
                         f"{r.text[:200]}")
    return ch


# --- the four requesting sides ------------------------------------------------


def build_pseudonymous(client: httpx.Client) -> AgentKeys:
    """Level 0. The key is the identity; there is no issuer in the picture."""
    return AgentKeys.load_or_create(f"{KEYS}/flow-pseudonymous.pem")


def build_identified(client: httpx.Client) -> AgentKeys:
    """AAuth. A stable enrolled identity, and a session key that rotates."""
    keys = AgentKeys.load_or_create_identified(f"{KEYS}/flow-identified.pem")
    keys.agent_token = enroll(client, ISSUER, keys.stable, keys.key,
                              "Sterling & Vance — flow check",
                              person_token=PS_ADMIN, on_status=lambda s: None)
    return keys


def build_described(client: httpx.Client) -> AgentKeys:
    """CIMD. A URL that says who operates this agent. Display only."""
    keys = AgentKeys.load_or_create(f"{KEYS}/flow-described.pem")
    keys.client_id = f"{OPERATOR}/agent.json"
    return keys


def build_published(client: httpx.Client) -> AgentKeys:
    """Web Bot Auth. The operator publishes the key so a stranger can
    attribute it. Discovery, never authority."""
    keys = AgentKeys.load_or_create(f"{KEYS}/flow-published.pem")
    keys.signature_agent = keys.publish(client, OPERATOR)
    return keys


REGIMES = [
    ("pseudonymous", "a bare key, no issuer", build_pseudonymous),
    ("identified", "AAuth token, rotating session key", build_identified),
    ("described", "CIMD operator document", build_described),
    ("published", "Web Bot Auth directory", build_published),
]


def negotiate(client: httpx.Client, keys: AgentKeys) -> dict:
    """One full grant. Returns what Alice's side put on the wire."""
    seen: dict = {}

    def capture_terms(template: dict) -> bool:
        # Everything except the per-negotiation nonce and family id, which
        # are supposed to differ — they are what stop a replay.
        seen["terms"] = {k: v for k, v in sorted(template.items())
                         if k not in ("nonce", "family")}
        return True

    ch = challenge_for(client, "get_positions")
    seen["as_uri"] = ch.as_uri
    rpt = run_grant(client, ch.as_uri, ch.ticket, keys, capture_terms,
                    on_status=lambda m: None)

    import jwt as pyjwt

    claims = pyjwt.decode(rpt, options={"verify_signature": False})
    seen["grant"] = {
        # Timestamps are dropped: they differ per negotiation by design, and
        # comparing them would only ever prove that time passed.
        "permissions": [{k: v for k, v in sorted(p.items()) if k != "exp"}
                        for p in claims.get("permissions", [])],
        "has_contract_hash": bool(claims.get("contract")),
        "cnf_is_agent_key": "jwk" in (claims.get("cnf") or {}),
        "single_use": claims.get("single_use", False),
    }
    seen["subject"] = claims.get("sub")
    return seen


def main() -> int:
    ca = CA if os.path.exists(CA) else True
    with httpx.Client(verify=ca) as client:
        print("\n== Alice's side, before anyone asks for anything ==")
        policy_before = owner_get(client, "/owner/policies")
        say(f"her policy: {len(policy_before)} tiers")
        blob = json.dumps(policy_before)
        for word in ("issuer", "aauth", "cimd", "thumbprint", "jkt", "agent_token"):
            if word in blob.lower():
                print(f"FAIL: her policy mentions {word!r} — identity leaked into it")
                return 1
        say("nothing in it names an agent, an issuer or an identity scheme")

        import threading
        threading.Thread(target=approve_everything,
                         args=(client, time.time() + 240), daemon=True).start()

        results: list[tuple[str, str, dict]] = []
        for name, blurb, build in REGIMES:
            print(f"\n== {name}: {blurb} ==")
            try:
                keys = build(client)
            except EnrollmentDenied as exc:
                print(f"FAIL: could not set up {name}: {exc}")
                return 1
            say("requesting side ready")
            try:
                seen = negotiate(client, keys)
            except GrantDenied as exc:
                print(f"FAIL: {name} was denied: {exc}")
                return 1
            say(f"granted — subject as Alice files it: {seen['subject']}")
            results.append((name, blurb, seen))

        print("\n== What Alice's side did, across all four ==")
        first = results[0][2]
        for field in ("terms", "grant", "as_uri"):
            values = [json.dumps(r[2][field], sort_keys=True) for r in results]
            if len(set(values)) != 1:
                print(f"FAIL: {field} differed across identity regimes:")
                for (name, _, _), v in zip(results, values):
                    print(f"   {name}: {v[:200]}")
                return 1
            say(f"{field}: identical in all four")

        policy_after = owner_get(client, "/owner/policies")
        if json.dumps(policy_after, sort_keys=True) != json.dumps(policy_before, sort_keys=True):
            print("FAIL: her policy changed while agents were negotiating")
            return 1
        say("her policy: unchanged")

        print("\n== The one thing that moved ==")
        for name, blurb, seen in results:
            print(f"   {name:<14} {seen['subject']}")

        # Two identity *levels* — the key, or a verified issuer — and that is
        # the only axis Alice's side has. CIMD and Web Bot Auth are additive
        # description: they tell her something true about who operates the
        # agent, and they change nothing about how it is filed or judged.
        by_subject: dict[str, list[str]] = {}
        for name, _, seen in results:
            by_subject.setdefault(seen["subject"], []).append(name)
        if len(by_subject) != 2:
            print(f"FAIL: expected two identity levels, saw {len(by_subject)}: "
                  f"{ {k: v for k, v in by_subject.items()} }")
            return 1

        described = {"pseudonymous", "described", "published"}
        for subject, names in by_subject.items():
            if set(names) not in (described, {"identified"}):
                print(f"FAIL: {subject} grouped {names}, which is not a level")
                return 1
        say("")
        say("Two levels — a key, or a verified issuer. Adding a CIMD document or")
        say("a Web Bot Auth directory told her more about the operator and moved")
        say("nothing: same handle, same terms, same grant.")

        conns = owner_get(client, "/owner/connections")
        say(f"her connections list: {len(conns)} standing relationships")

    print("\nPASS: agent identity stayed on the requesting side.")
    print("      Alice governed all four without knowing what any of them were.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
