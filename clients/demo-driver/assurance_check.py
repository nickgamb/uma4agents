"""Agent assurance, and the limit on how much of Alice's attention a stranger
can spend.

Two things are demonstrated here, both against the running stack.

**Assurance is policy she can write, without naming an agent.** Her authority
derives what it can establish about a requesting agent — is the request bound
to a key it will recognise, can it check where the credential came from, is
anyone named and reachable behind it — and keeps those apart from *standing*,
which is what she has herself seen of that agent. Her rules read those facts.
Nothing in them names an agent, so they hold for the next stranger too.

The asymmetry is the safety property, and it is what this checks hardest:

    assurance may only tighten a requirement; only standing may relax one.

So a lie can only cost the liar friction. That is what makes it safe for her
policy to read a self-asserted operator name at all.

**Her attention has a depth limit.** Nothing above stops someone minting ten
thousand keys and putting ten thousand first-contact requests in front of her.
Keys are free. So there is a cap on how many requests from agents she has no
standing with may be waiting at once, and an agent she already knows is never
counted against it.

That alone was not enough, and the gap is the interesting part: **Bob's agent
is a stranger too, the first time.** One queue meant a flood of anonymous bots
could keep him out of the relationship he still had to form — the cap protected
continuity and left onboarding undefended. So strangers queue by lane. An agent
whose named operator published its key contends only with other agents somebody
can be held to; the anonymous flood cannot reach that lane at all.

Run against the full stack with `make assurance-check`.
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
OPERATOR = os.environ.get("UMA4A_AGENT_OPERATOR", "https://agent.uma.lab")
CA = os.environ.get("UMA4A_CACERT", "/driver/rootCA.pem")
KEYS = "/driver/keys"
BUDGET = int(os.environ.get("UMA_AS_PEND_BUDGET", "5"))
RUN = uuid.uuid4().hex[:8]
META = mcp_meta("u4a-assurance-check")

PASS, FAIL = [], []


def say(msg: str) -> None:
    print(f"   {msg}", flush=True)


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"   {'ok  ' if ok else 'FAIL'} {name}" + (f" — {detail}" if detail else ""),
          flush=True)


def owner_token(client: httpx.Client) -> str:
    r = client.post(f"{KEYCLOAK}/realms/alice/protocol/openid-connect/token",
                    data={"grant_type": "password", "client_id": "meridian-portal",
                          "username": "alice",
                          "password": os.environ.get("ALICE_PASSWORD", "alice-demo")},
                    timeout=15.0)
    r.raise_for_status()
    return r.json()["access_token"]


def owner_hdrs(client: httpx.Client) -> dict:
    return {"Authorization": f"Bearer {owner_token(client)}"}


def pending(client: httpx.Client) -> list:
    return client.get(f"{AS_PUBLIC}/owner/pending", headers=owner_hdrs(client),
                      timeout=15.0).json()


def forget_agents(client: httpx.Client) -> int:
    """Revoke every standing connection, so each run starts having met nobody.

    Needed once the requesting side's keys are provisioned rather than
    generated per run. A stable key is the realistic case — an operator issues
    its agents keys and they keep them — but it also means an agent that
    negotiated yesterday still has standing today, and half of what is
    asserted below is about what happens on a *first* contact.

    Revoking is the owner action that restores that, and it is the same one
    the check exercises later: she withdraws an agent, and the next thing it
    asks pends like a stranger's. Nothing here reaches past the owner API.
    """
    hdrs, n = owner_hdrs(client), 0
    for conn in client.get(f"{AS_PUBLIC}/owner/connections", headers=hdrs,
                           timeout=15.0).json():
        if conn.get("status") == "active":
            client.post(
                f"{AS_PUBLIC}/owner/connections/{conn['handle']}/revoke",
                headers=hdrs, timeout=15.0)
            n += 1
    return n


def decide_all(client: httpx.Client, decision: str) -> int:
    hdrs, n = owner_hdrs(client), 0
    for p in pending(client):
        client.post(f"{AS_PUBLIC}/owner/pending/{p['family']}/decision",
                    json={"decision": decision}, headers=hdrs, timeout=15.0)
        n += 1
    return n


# Where this operator's agent keys come from. Two shapes, and which one
# applies is a property of the deployment rather than of the protocol.
#
#   provisioned  the operator was handed a published directory and serves only
#                that, so the agent is given the private half of a key already
#                in it. This is the replicated shape and the honest one: an
#                operator publishes keys it issued.
#   self-published  the single-process stack generates a key per run and the
#                agent registers it. Convenient, and impossible to run behind
#                more than one replica — the operator refuses it outright once
#                it has a document of its own.
PUBLISHED_KEYS = os.environ.get("UMA4A_PUBLISHED_KEYS")


def operator_agent(client: httpx.Client, name: str) -> AgentKeys:
    """An agent whose key its operator's directory actually carries."""
    directory = f"{OPERATOR}/.well-known/http-message-signatures-directory"
    provisioned = f"{PUBLISHED_KEYS}/{name}-ed25519.pem" if PUBLISHED_KEYS else None
    if provisioned and os.path.exists(provisioned):
        keys = AgentKeys.load_or_create(provisioned)
        keys.client_id = f"{OPERATOR}/agent.json"
        keys.signature_agent = directory
        return keys
    keys = AgentKeys.load_or_create(f"{KEYS}/assurance-{name}-{RUN}.pem")
    keys.client_id = f"{OPERATOR}/agent.json"
    keys.signature_agent = keys.publish(client, OPERATOR)
    return keys


def negotiate(client: httpx.Client, keys: AgentKeys, tool: str,
              arguments: dict | None = None, quiet: bool = True,
              max_wait_s: int = 25):
    """One negotiation. Returns (granted, asked, reason) — whether the grant
    was issued, whether it had to go past Alice to get there, and what the
    authorization server said if it did not."""
    args = arguments or {}
    r = mcp_call(client, GATEWAY, "tools/call",
                 {"name": tool, "arguments": args}, META)
    ch = parse_challenge(r.headers.get("www-authenticate", ""))
    if ch is None:
        raise SystemExit(f"no challenge for {tool}: {r.status_code}")
    asked = {"v": False}

    def status(msg: str) -> None:
        if "has been asked" in msg:
            asked["v"] = True
        if not quiet:
            say(f"[agent] {msg}")

    try:
        run_grant(client, ch.as_uri, ch.ticket, keys, lambda t: True,
                  operation=({"tool": tool, "params": args} if args else None),
                  on_status=status, max_wait_s=max_wait_s)
        return True, asked["v"], None
    except GrantDenied as exc:
        return False, asked["v"], str(exc)


def approve_in_background(client: httpx.Client, seconds: float):
    """Alice, answering promptly. Deliberately blind to who is asking.

    Returns the stop switch: the attention-budget section below has to be able
    to turn her off, because a cap on the *queue* is only observable while
    nobody is draining it.
    """
    import threading

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


def main() -> int:
    ca = CA if os.path.exists(CA) else True
    with httpx.Client(verify=ca, timeout=30.0) as client:
        decide_all(client, "denied")          # start from an empty queue
        forget_agents(client)                 # ...and having met nobody

        # An agent with a named operator, and one with nobody behind it.
        # Same code, same key type, same terms — the only difference is
        # whether a CIMD document says who runs it.
        accountable = AgentKeys.load_or_create(f"{KEYS}/assurance-named-{RUN}.pem")
        accountable.client_id = f"{OPERATOR}/agent.json"
        anonymous = AgentKeys.load_or_create(f"{KEYS}/assurance-nameless-{RUN}.pem")

        print("\n== First contact: both are strangers, so both ask ==")
        approving = approve_in_background(client, 90)
        a_ok, a_asked, _ = negotiate(client, accountable, "get_positions")
        n_ok, n_asked, _ = negotiate(client, anonymous, "get_positions")
        check("the accountable agent was admitted, after asking", a_ok and a_asked)
        check("the nameless agent was admitted too — assurance is not a gate",
              n_ok and n_asked)

        print("\n== Second request, same tier: assurance decides who is quiet ==")
        a_ok, a_asked, _ = negotiate(client, accountable, "get_positions")
        check("an agent with a named operator does not disturb her again",
              a_ok and not a_asked)
        n_ok, n_asked, _ = negotiate(client, anonymous, "get_positions")
        check("an agent with nobody behind it asks every time",
              n_ok and n_asked)
        say("her rule reads `assurance.accountability_below:1` and names no agent")

        print("\n== Standing is per tier, not per agent ==")
        a_ok, a_asked, _ = negotiate(client, accountable, "get_transactions")
        check("being admitted is not being admitted everywhere", a_ok and a_asked)
        a_ok, a_asked, _ = negotiate(client, accountable, "get_transactions")
        check("and the second request at that tier is quiet",
              a_ok and not a_asked)

        print("\n== Saying so, and having published the key ==")
        # Same operator, same CIMD. The difference is that this one's signing
        # key is in the operator's own key directory, which Alice's authority
        # fetches and checks for itself.
        #
        # Two ways for it to get there, and which one applies is a property of
        # the deployment. Where the operator was provisioned with a published
        # directory — the replicated shape, and the real one — the agent is
        # given the private half of a key that directory already holds, and
        # publishes nothing. Where it was not, the single-process stack lets
        # the agent register the key it just generated. The second cannot be
        # made to work behind more than one replica, which is why the operator
        # refuses it as soon as it has a document of its own.
        attested = operator_agent(client, "attested")
        check("the operator's key directory carries this agent's key",
              attested.signature_agent is not None)
        # Read what her authority established, from the dialog she would see.
        approving.set()
        time.sleep(1.5)
        decide_all(client, "denied")
        negotiate(client, attested, "get_positions", max_wait_s=2)
        seen = pending(client)
        axes = seen[0]["assurance"] if seen else {}
        check("the operator's own directory raised accountability to 2",
              axes.get("accountability") == 2, str(axes))
        for note in (seen[0]["assurance_notes"] if seen else []):
            say(note)
        decide_all(client, "denied")
        approving = approve_in_background(client, 60)
        t_ok, t_asked, _ = negotiate(client, attested, "get_positions")
        check("and it is still admitted like any other stranger — assurance "
              "buys quiet, never access", t_ok and t_asked)

        print("\n== A lie can only cost the liar friction ==")
        liar = AgentKeys.load_or_create(f"{KEYS}/assurance-liar-{RUN}.pem")
        liar.client_id = "https://not-a-real-operator.invalid/agent.json"
        # And pointing at somebody else's real directory does not help: the
        # directory has to be same-origin with the operator being claimed,
        # or an agent could attest to itself with a server it runs.
        liar.signature_agent = f"{OPERATOR}/.well-known/http-message-signatures-directory"
        l_ok, l_asked, _ = negotiate(client, liar, "get_positions")
        check("metadata that does not resolve buys nothing", l_ok and l_asked)
        l_ok, l_asked, _ = negotiate(client, liar, "get_positions")
        check("and is still worth nothing on the second try", l_ok and l_asked)

        print("\n== Her attention has a depth limit ==")
        # She stops answering. A cap on the queue is only observable while
        # nobody is draining it — which is also the situation it exists for.
        approving.set()
        time.sleep(1.5)
        decide_all(client, "denied")

        refused = None
        for i in range(BUDGET + 2):
            stranger = AgentKeys.load_or_create(f"{KEYS}/assurance-flood-{RUN}-{i}.pem")
            # A short wait: each of these is meant to *stay* in her queue, not
            # to be answered. Giving up on the poll leaves the pend standing,
            # which is exactly what an attacker's request would do.
            ok, _, why = negotiate(client, stranger, "get_positions", max_wait_s=2)
            if not ok and "not accepting new agent requests" in (why or "") \
                    and refused is None:
                refused = i
        waiting = len(pending(client))
        check(f"a flood of strangers is capped at {BUDGET} waiting for her",
              waiting <= BUDGET, f"{waiting} waiting")
        check("and the ones past the cap are refused with a reason, not queued",
              refused is not None, f"first refusal at stranger {refused}")

        # Her queue is still full of anonymous strangers, and nobody is
        # answering it. This is the case the single-queue version got wrong:
        # Bob's agent is a stranger too the first time, so a flood used to shut
        # the door on the relationship he still had to form.
        print("\n== And a newcomer that can be named still gets in ==")
        newcomer = operator_agent(client, "newcomer")
        n_ok, _, n_why = negotiate(client, newcomer, "get_positions", max_wait_s=2)
        check("a first contact she could name is not refused for budget",
              "not accepting new agent requests" not in (n_why or ""),
              n_why or "")
        lanes = [p["assurance"].get("accountability", 0) for p in pending(client)]
        check("and it is waiting for her, in its own lane",
              any(a >= 2 for a in lanes),
              f"accountability of what is waiting: {sorted(lanes)}")

        # Her queue is still full of strangers, and nobody is answering it.
        print("\n== And the flood does not reach the agent she knows ==")
        a_ok, a_asked, _ = negotiate(client, accountable, "get_positions",
                                     max_wait_s=4)
        check("an established agent is unaffected by the queue being full",
              a_ok and not a_asked)
        decide_all(client, "denied")

        print("\n== One action shuts out an operator, not one agent ==")
        hdrs = owner_hdrs(client)
        before = client.get(f"{AS_PUBLIC}/owner/operators", headers=hdrs,
                            timeout=15.0).json()
        mine = [o for o in before if o["origin"] == OPERATOR]
        check("her authority lists the operator behind those agents",
              bool(mine) and mine[0]["active"] >= 2,
              f"{mine[0]['active'] if mine else 0} active")
        res = client.post(f"{AS_PUBLIC}/owner/operators/block", headers=hdrs,
                          json={"origin": OPERATOR}, timeout=20.0).json()
        check("blocking it revokes every agent it runs, in one step",
              res.get("connections_revoked", 0) >= 2, str(res))
        blocked_ok, _, why = negotiate(client, accountable, "get_positions",
                                       max_wait_s=2)
        check("and an agent of that operator is refused by name",
              not blocked_ok and OPERATOR in (why or ""), why or "")
        # It does not remove them from the internet: the same key, without the
        # claim, is a stranger again — which is the honest limit.
        anon_again = AgentKeys.load_or_create(f"{KEYS}/assurance-named-{RUN}.pem")
        anon_again.client_id = None
        again_ok, again_asked, _ = negotiate(client, anon_again, "get_positions",
                                             max_wait_s=2)
        check("but the same party may return anonymously, as a stranger",
              again_asked or not again_ok)
        client.post(f"{AS_PUBLIC}/owner/operators/unblock", headers=owner_hdrs(client),
                    json={"origin": OPERATOR}, timeout=20.0)
        say("unblocked — she may deal with them again, but what the block")
        say("revoked stays revoked: it restores the right to ask, not the access")

        # Leave her queue as we found it. A check that fills the pend queue and
        # walks away makes the *next* thing anyone runs look broken — which is
        # exactly what it did the first time.
        drained = decide_all(client, "denied")
        say(f"queue left empty ({drained} of this check's requests dismissed)")


    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        return 1
    print("\nPASS: assurance tightened and never widened, standing was per tier,")
    print("      a flood of anonymous strangers could crowd out neither the agent")
    print("      she knows nor a newcomer she could put a name to, and one action")
    print("      shut out an operator rather than one agent at a time.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
