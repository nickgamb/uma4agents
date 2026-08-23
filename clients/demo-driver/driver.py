"""demo-driver — headless walker for the three demo acts.

Same grant-loop code path as the agent-shim (lib/uma4a_grant.py), driving
Alice's vault MCP through the gateway over plain streamable-http JSON-RPC.

  --act tier1   holdings summary: four beats, auto-grant
  --act tier2   transaction history: visibly stricter dictated terms
  --act tier3   a trade: ask-me pend -> single-use, operation-scoped grant
  --act all     the whole day

Bob's side approves terms via his standing config (STANDING). In tier 3,
--simulate-alice approves via the owner API for headless runs; without it the
driver waits for Alice to tap approve in her portal.
"""

import argparse
import json
import os
import sys

import httpx

from uma4a_enroll import EnrollmentDenied, enroll
from uma4a_grant import (
    AgentKeys,
    DiscoveryMismatch,
    GrantDenied,
    parse_challenge,
    run_grant,
    signed_headers,
    validate_resource_metadata,
    well_known_prm_url,
)

GATEWAY_AUTHORITY = "gateway.uma.lab"
MCP_PATH = "/mcp"

# Bob's standing terms policy: what his shim may accept without asking him.
STANDING = {"max_expires_in": 7 * 24 * 3600}


def say(msg: str) -> None:
    print(f"   {msg}")


def approve_terms(template: dict) -> bool:
    ok = template["expires_in"] <= STANDING["max_expires_in"]
    say(f"[bob-standing-config] terms {'accepted' if ok else 'refused'}: "
        f"purpose={template['purpose']!r} expires_in={template['expires_in']}"
        f" prohibited={template['prohibited']}")
    return ok


# 2026-07-28 is only reachable through server/discover: the SDK caps the
# `initialize` handshake at 2025-11-25 by construction.
PROTOCOL_VERSION = "2026-07-28"
# Client identity rides params._meta on every request instead of being
# exchanged once — what makes the transport stateless (SEP-2567/2575).
CLIENT_META = {
    "io.modelcontextprotocol/protocolVersion": PROTOCOL_VERSION,
    "io.modelcontextprotocol/clientCapabilities": {},
    "io.modelcontextprotocol/clientInfo": {
        "name": "uma4agents-demo-driver", "version": "0.2",
    },
}


class McpSession:
    def __init__(self, client: httpx.Client, url: str):
        self.client = client
        self.url = url
        self._id = 0

    def _post(self, msg: dict, headers: dict | None = None) -> httpx.Response:
        # No session id: sessions are gone in 2026-07-28.
        h = {"accept": "application/json, text/event-stream",
             "content-type": "application/json",
             "MCP-Protocol-Version": PROTOCOL_VERSION}
        # SEP-2243 routing headers. The receiver reconciles them against the
        # body rather than trusting either alone.
        if method := msg.get("method"):
            h["Mcp-Method"] = method
        if name := (msg.get("params") or {}).get("name"):
            h["Mcp-Name"] = name
        if headers:
            h.update(headers)
        return self.client.post(self.url, json=msg, headers=h)

    @staticmethod
    def _payload(r: httpx.Response) -> dict | None:
        ct = r.headers.get("content-type", "")
        if "text/event-stream" in ct:
            for line in r.text.splitlines():
                if line.startswith("data:"):
                    return json.loads(line[5:].strip())
            return None
        if r.content:
            try:
                return r.json()
            except ValueError:
                raise RuntimeError(
                    f"non-JSON response ({r.status_code}) — a proxy hop may "
                    f"still be settling; retry in a few seconds: {r.text[:200]}"
                ) from None
        return None

    def request(self, method: str, params: dict | None = None,
                headers: dict | None = None, notification: bool = False):
        p = dict(params or {})
        p["_meta"] = {**CLIENT_META, **(p.get("_meta") or {})}
        msg: dict = {"jsonrpc": "2.0", "method": method, "params": p}
        if not notification:
            self._id += 1
            msg["id"] = self._id
        r = self._post(msg, headers)
        return r, self._payload(r)

    def initialize(self) -> None:
        """The 2026-07-28 handshake, which is server/discover, not initialize."""
        r, payload = self.request("server/discover", {})
        if r.status_code != 200:
            raise RuntimeError(f"server/discover failed: {r.status_code} {r.text[:200]}")
        versions = ((payload or {}).get("result") or {}).get("supportedVersions", [])
        if PROTOCOL_VERSION not in versions:
            raise RuntimeError(
                f"resource does not speak {PROTOCOL_VERSION} (offers {versions})")


def call_tool(session: McpSession, keys: AgentKeys, tool: str, args: dict,
              client: httpx.Client, operation: dict | None = None,
              reason: str | None = None, mission: dict | None = None,
              simulate_alice: bool = False, owner_token=None,
              as_internal: str | None = None,
              resource_metadata: dict | None = None,
              resource_url: str | None = None,
              on_grant=None) -> dict:
    """tools/call with the full grant dance on 401.

    on_grant, if given, runs after the RPT is issued but before the authorized
    call — the window where a replay attack would land.
    """
    params = {"name": tool, "arguments": args}
    r, payload = session.request("tools/call", params)
    if r.status_code == 200:
        return payload

    challenge = parse_challenge(r.headers.get("www-authenticate", ""))
    if r.status_code != 401 or challenge is None:
        raise RuntimeError(f"unexpected response: {r.status_code} {r.text[:200]}")
    as_uri, ticket = challenge
    say(f"challenged: 401 from the gateway, ticket {ticket[:20]}…, AS {as_uri}")

    # Corroborate the (unauthenticated) challenge header against the
    # resource's TLS-anchored published metadata before negotiating.
    if resource_metadata is not None:
        try:
            validate_resource_metadata(resource_metadata, resource_url, as_uri)
            say("challenge corroborated: as_uri is among the resource's "
                "published authorization servers")
        except DiscoveryMismatch as exc:
            raise RuntimeError(f"refusing to negotiate: {exc}")

    # First contact pends as a connection request regardless of tier (the
    # day-1 handshake); ask-me tiers pend per operation. The simulated Alice
    # approves whatever lands, standing in for her portal tap.
    if simulate_alice:
        import threading

        def approve_when_pending():
            import time
            headers = {"Authorization": f"Bearer {owner_token()}"}
            for _ in range(40):
                time.sleep(1.5)
                pending = client.get(
                    f"{as_internal}/owner/pending", headers=headers,
                ).json()
                if pending:
                    p = pending[0]
                    say(f"[simulated-alice] approving {p['kind']} request "
                        f"{p['family']} from the couch")
                    client.post(
                        f"{as_internal}/owner/pending/{p['family']}/decision",
                        json={"decision": "approved"},
                        headers=headers,
                    )
                    return

        threading.Thread(target=approve_when_pending, daemon=True).start()

    def hold_receipt(receipt_jws: str) -> None:
        import base64 as _b64
        payload = json.loads(_b64.urlsafe_b64decode(receipt_jws.split(".")[1] + "=="))
        say(f"receipt held (both sides now have the record): terms {payload['terms_uri']}"
            f" · agreement {payload['agreement'][:20]}…")

    rpt = run_grant(client, as_uri, ticket, keys, approve_terms,
                    operation=operation, reason=reason, mission=mission,
                    on_status=say, on_receipt=hold_receipt)

    if on_grant is not None:
        on_grant(rpt)

    headers = signed_headers("POST", GATEWAY_AUTHORITY, MCP_PATH, rpt, keys)
    r, payload = session.request("tools/call", params, headers=headers)
    if r.status_code != 200:
        raise RuntimeError(f"authorized call failed: {r.status_code} {r.text[:300]}")
    return {"payload": payload, "rpt": rpt}


def show_result(payload: dict) -> None:
    try:
        content = payload["result"]["content"][0]["text"]
        data = json.loads(content)
        say("data received: " + json.dumps(data)[:140] + "…")
    except (KeyError, IndexError, ValueError):
        say("result: " + json.dumps(payload)[:200])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--act", default="all",
                    choices=["tier1", "tier2", "tier3", "revocation", "all"])
    ap.add_argument("--gateway", default="https://gateway.uma.lab/mcp")
    ap.add_argument("--as-internal", default="https://alice-as.uma.lab")
    ap.add_argument("--cacert", default="certs/rootCA.pem")
    ap.add_argument("--keystore", default="keys/agent-stable-key.pem")
    ap.add_argument("--simulate-alice", action="store_true",
                    help="approve pending requests via the owner API (headless runs)")
    ap.add_argument("--oidc-issuer",
                    default="https://keycloak.uma.lab/realms/alice")
    ap.add_argument("--alice-username", default=os.environ.get("ALICE_USERNAME", "alice"))
    ap.add_argument("--alice-password", default=os.environ.get("ALICE_PASSWORD", "alice-demo"))
    ap.add_argument("--agent-issuer", default="https://ps.uma.lab",
                    help="Bob's agent server; pass --pseudonymous to skip enrollment")
    ap.add_argument("--pseudonymous", action="store_true",
                    help="run with a bare key instead of an enrolled agent token")
    ap.add_argument("--alice-operator",
                    default=os.environ.get("UMA4A_ALICE_OPERATOR",
                                           "https://alice-agent.uma.lab"),
                    help="Alice's own operator presence, for the first-party act")
    ap.add_argument("--agent-operator",
                    default=os.environ.get("UMA4A_AGENT_OPERATOR",
                                           "https://agent.uma.lab"),
                    help="the operator's public presence: CIMD document and "
                         "Web Bot Auth key directory (empty to run without)")
    ap.add_argument("--person-token",
                    default=os.environ.get("PS_ADMIN_TOKEN", "uma4agents-ps-admin"),
                    help="person API bearer standing in for Bob's approval tap")
    args = ap.parse_args()

    client = httpx.Client(verify=args.cacert, timeout=15.0)
    if args.pseudonymous:
        keys = AgentKeys.load_or_create(args.keystore)
        say("running pseudonymously: the bare agent key is the identity")
    else:
        # The identified AAuth level: enroll with Bob's agent server. The
        # stable key persists across runs; the session key the aa-agent+jwt
        # binds is fresh each run — identity continuity lives in the token.
        print("\n== Prologue: Bob's agent enrolls with his agent server ==")
        keys = AgentKeys.load_or_create_identified(args.keystore)
        try:
            keys.agent_token = enroll(
                client, args.agent_issuer, keys.stable, keys.key,
                agent_name="Bob's advisory agent (Sterling & Vance)",
                person_token=args.person_token, on_status=say,
            )
            say(f"aa-agent+jwt in hand from {args.agent_issuer}; "
                "contracts will carry it")
        except EnrollmentDenied as exc:
            print(f"enrollment failed: {exc}")
            return 1
    # Who operates this agent, and where its keys are published. Both are
    # additive: the connection is still keyed by the agent's key (or its
    # verified issuer subject), and the RPT's cnf key is still what verifies
    # a request. These only let a party that has never met this agent say
    # something true about it — the RqP != RO cold-start problem.
    if args.agent_operator:
        keys.client_id = f"{args.agent_operator}/agent.json"
        keys.signature_agent = keys.publish(client, args.agent_operator)
        say(f"operator metadata: {keys.client_id}")
        say(f"key published for discovery: {keys.signature_agent or 'unavailable'}")

    acts = (["tier1", "tier2", "tier3", "first-party", "revocation"]
            if args.act == "all" else [args.act])

    # The simulated Alice authenticates like the real one: a direct-access
    # grant at her IdP yields the OIDC token her AS's owner API requires.
    _alice: dict = {}

    def owner_token() -> str:
        if not _alice or _alice["expires"] < __import__("time").time() + 15:
            r = client.post(
                f"{args.oidc_issuer}/protocol/openid-connect/token",
                data={"grant_type": "password", "client_id": "meridian-portal",
                      "username": args.alice_username,
                      "password": args.alice_password},
            )
            r.raise_for_status()
            body = r.json()
            _alice.update(token=body["access_token"],
                          expires=__import__("time").time() + body.get("expires_in", 60))
            say("[simulated-alice] logged in at her IdP (direct-access grant)")
        return _alice["token"]

    # Beat 0 — declarative discovery (RFC 9728). Before touching a tool, the
    # agent reads the resource's published metadata: who the authorization
    # server is, and which tool surfaces are protected under which scopes.
    print("\n== Beat 0: the agent discovers the resource's shape (RFC 9728) ==")
    prm_url = well_known_prm_url(args.gateway)
    prm = validate_resource_metadata(
        client.get(prm_url).json(), args.gateway)
    say(f"resource metadata at {prm_url} (signed: "
        f"{'yes' if prm.get('signed_metadata') else 'no'})")
    say(f"authorization server(s): {', '.join(prm['authorization_servers'])}")
    for ts in prm.get("tool_surfaces", []):
        say(f"tool surface: {ts['tool']} (scopes {', '.join(ts['resource_scopes'])})")
    say("note: which resources belong to whom is not in the public document —"
        " owner instances live behind the protected owner-resources endpoint")

    session = McpSession(client, args.gateway)
    session.initialize()
    say("MCP session established through the gateway (discovery is open)")

    try:
        if "tier1" in acts:
            print("\n== Act 1 (midday): Bob's agent requests Alice's holdings summary ==")
            print("   (first contact: an unconnected agent pends until Alice connects it)")
            out = call_tool(session, keys, "get_positions", {}, client,
                            reason="Suitability review for a new advisory "
                                   "engagement, at the client's request.",
                            simulate_alice=args.simulate_alice,
                            owner_token=owner_token, as_internal=args.as_internal,
                            resource_metadata=prm, resource_url=args.gateway)
            show_result(out["payload"])

        if "tier2" in acts:
            print("\n== Act 2 (midday): transaction history — watch the terms tighten ==")
            out = call_tool(session, keys, "get_transactions",
                            {"account": "brokerage-main"}, client,
                            reason="Cost-basis check before proposing a "
                                   "rebalance in this account.",
                            simulate_alice=args.simulate_alice,
                            owner_token=owner_token, as_internal=args.as_internal,
                            resource_metadata=prm, resource_url=args.gateway)
            show_result(out["payload"])

        if "tier3" in acts:
            print("\n== Act 3 (afternoon): the market moves — Bob's agent proposes a trade ==")
            order = {"symbol": "VTI", "side": "sell", "quantity": 40}
            operation = {"tool": "execute_trade", "params": order}

            # Between the grant and its one legitimate use, someone who has
            # seen the token replays it without the agent's key. A single-use
            # grant must survive that: if the resource spends the token before
            # checking the signature, anyone who can observe it can destroy
            # the approval Alice just gave.
            replay_ok = {"held": False}

            def replay_with_a_stolen_token(rpt: str) -> None:
                print("\n== Act 3 interlude: someone replays the grant unsigned ==")
                stolen = signed_headers("POST", GATEWAY_AUTHORITY, MCP_PATH, rpt, keys)
                # Must match sign()'s exact key casing — a lowercase "signature"
                # is a second header, not an override, and the forgery silently
                # never happens.
                stolen["Signature"] = "sig1=:" + "A" * 86 + ":"
                r, _ = session.request(
                    "tools/call", {"name": "execute_trade", "arguments": order},
                    headers=stolen)
                say(f"{r.status_code}: replay rejected — proof-of-possession failed")
                replay_ok["held"] = r.status_code == 401

            out = call_tool(session, keys, "execute_trade", order, client,
                            operation=operation,
                            reason="Trimming an overweight equity position "
                                   "the client approved by phone this morning.",
                            simulate_alice=args.simulate_alice,
                            owner_token=owner_token, as_internal=args.as_internal,
                            resource_metadata=prm, resource_url=args.gateway,
                            on_grant=replay_with_a_stolen_token)
            if not replay_ok["held"]:
                print("FAIL: a forged signature was not rejected with 401")
                return 1
            say("Alice's approval survived the replay — the honest call went through")
            show_result(out["payload"])

            print("\n== Act 3 epilogue: the same RPT, tried again ==")
            headers = signed_headers("POST", GATEWAY_AUTHORITY, MCP_PATH, out["rpt"], keys)
            r, _ = session.request("tools/call",
                                   {"name": "execute_trade", "arguments": order},
                                   headers=headers)
            say(f"{r.status_code}: single-use grant is consumed — approval permitted "
                "one walk through the door")
            if r.status_code == 200:
                print("FAIL: single-use RPT was accepted twice")
                return 1

        if "first-party" in acts:
            print("\n== Act 4 (evening): Alice's own agent, and the same tier ==")
            say("RO == RqP. She activated this one; it is still not her.")

            # Her agent is a separate key with a separate operator presence.
            # Nothing about the grant differs — same four beats, same terms,
            # same enforcement — which is the claim this act exists to test.
            hers = AgentKeys.load_or_create(f"{args.keystore.rsplit('/', 1)[0]}"
                                            f"/alice-agent-key.pem")
            if args.alice_operator:
                hers.client_id = f"{args.alice_operator}/agent.json"
                hers.signature_agent = hers.publish(client, args.alice_operator)
                say(f"her operator: {hers.client_id}")

            def owner_post(path: str, body: dict) -> dict:
                r = client.post(f"{args.as_internal}{path}", json=body,
                                headers={"Authorization": f"Bearer {owner_token()}"})
                r.raise_for_status()
                return r.json()

            def set_tier3_rules(rules: list) -> None:
                r = client.put(f"{args.as_internal}/owner/policies/tier3",
                               json={"rules": rules},
                               headers={"Authorization": f"Bearer {owner_token()}"})
                r.raise_for_status()

            origin = (args.alice_operator or "").rstrip("/")
            owner_post("/owner/operators/claim", {"origin": origin})
            say(f"she claims {origin} as her own")

            trade = {"symbol": "VTI", "side": "buy", "quantity": 5}
            op = {"tool": "execute_trade", "params": trade}

            try:
                # 1. Before she writes anything, being hers buys nothing. Tier 3
                #    asks, and it asks her about her own agent too.
                say("no rule yet — tier 3 asks her, about her own agent as well")
                call_tool(session, hers, "execute_trade", trade, client,
                          operation=op,
                          reason="Reinvesting this month's dividend.",
                          simulate_alice=args.simulate_alice,
                          owner_token=owner_token, as_internal=args.as_internal,
                          resource_metadata=prm, resource_url=args.gateway)

                # 2. Now she says so, in a rule that names no agent.
                set_tier3_rules([{"when": ["standing.first_party"], "then": "auto"}])
                say('rule added: {"when": ["standing.first_party"], "then": "auto"}')

                out = call_tool(session, hers, "execute_trade", trade, client,
                                operation=op,
                                reason="Reinvesting this month's dividend.",
                                simulate_alice=args.simulate_alice,
                                owner_token=owner_token,
                                as_internal=args.as_internal,
                                resource_metadata=prm, resource_url=args.gateway)
                say("granted without asking her — she had already decided")
                show_result(out["payload"])

                # 3. The same rule, the same tier, Bob's agent. Still asked,
                #    because the rule reads a fact about who she activated and
                #    Bob's agent is not one of them.
                say("the same rule, the same tier — now Bob's agent tries it")
                call_tool(session, keys, "execute_trade", trade, client,
                          operation=op,
                          reason="Following the same dividend reinvestment.",
                          simulate_alice=args.simulate_alice,
                          owner_token=owner_token, as_internal=args.as_internal,
                          resource_metadata=prm, resource_url=args.gateway)
                say("still asked — the relaxation is about whose agent it is")
            finally:
                # Leave her policy as it was found, so `demo-all` is repeatable.
                set_tier3_rules([])
                say("tier 3 restored to its shipped rules")

        if "revocation" in acts:
            print("\n== Act 4 (evening): Alice revokes the agent ==")
            out = call_tool(session, keys, "get_positions", {}, client,
                            simulate_alice=args.simulate_alice,
                            owner_token=owner_token, as_internal=args.as_internal,
                            resource_metadata=prm, resource_url=args.gateway)
            say("agent holds a live grant for the holdings summary")

            # This agent's own connection, not whichever happens to be first.
            # Revocation is per agent, so an act that picks an arbitrary active
            # one proves nothing — and quietly stops proving anything at all as
            # soon as another act leaves a second connection behind, which is
            # exactly what happened when the first-party act was added.
            headers = {"Authorization": f"Bearer {owner_token()}"}
            conns = client.get(f"{args.as_internal}/owner/connections",
                               headers=headers).json()
            mine = keys.connection_handle()
            handle = next((c["handle"] for c in conns
                           if c["status"] == "active" and c["handle"] == mine), None)
            if handle is None:
                print(f"FAIL: this agent has no active connection to revoke ({mine})")
                return 1
            revoked = client.post(
                f"{args.as_internal}/owner/connections/{handle}/revoke",
                headers=headers).json()
            say(f"[alice] revoked {handle[:24]}… — "
                f"{revoked['rpts_deactivated']} live grant(s) deactivated")

            # A revoked relationship is a decision the owner already made.
            # Answering 401 would invite the agent to negotiate again for an
            # outcome that is settled, so enforcement has to say so terminally.
            sig = signed_headers("POST", GATEWAY_AUTHORITY, MCP_PATH, out["rpt"], keys)
            r, _ = session.request("tools/call",
                                   {"name": "get_positions", "arguments": {}},
                                   headers=sig)
            say(f"{r.status_code}: {r.text[:80]}")
            if r.status_code != 403:
                print(f"FAIL: revoked agent got {r.status_code}, expected a terminal 403")
                return 1
            say("revocation is terminal — not an invitation to re-negotiate")
    except GrantDenied as exc:
        print(f"grant denied: {exc}")
        return 1

    print("\nPASS: the requested acts completed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
