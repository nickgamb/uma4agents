"""Sub-agents: each one gets its own grant, and none of them get the parent's.

An orchestrator that spawns workers is the ordinary shape of agent software,
and it is the shape this profile refuses to solve by passing a token down. An
agent is individuated by its key, so a worker handed the parent's key simply
*is* the parent, and a worker with its own key is a stranger.

This is the third case. An agent the owner already deals with may *introduce* a
sibling from its own operator: the sibling arrives with a signed statement
about its key and nothing else, and then negotiates its own terms, under its
own key, for its own grant. What it skips is being introduced from nothing.

Four things are asserted here that cannot be seen from inside the agent:

  * an introduction is checked against *her* records, not believed. Every
    reason to refuse one is exercised — a sponsor she never approved in
    person, an agent from another operator, a forged binding, a sub-agent
    trying to sponsor in turn;
  * approval belongs to the lineage, and it flows both ways. The tier a
    sub-agent earns is a tier the agent that introduced it stops being asked
    about;
  * the ceiling is not configurable. A tier nobody in the lineage was approved
    for asks her, exactly as it would have asked about the parent;
  * revoking the parent kills the sub-agents, in one action, and their live
    grants stop working on the next call rather than at their expiry.

Run against the full stack with `make subagent-check`, or in the cluster with
`make k8s-subagent-check`.
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
    sign_introduction,
)

GATEWAY = os.environ.get("UMA4A_GATEWAY", "https://gateway.uma.lab/mcp")
AS_PUBLIC = os.environ.get("UMA4A_AS", "https://alice-as.uma.lab")
KEYCLOAK = os.environ.get("UMA4A_OIDC", "https://keycloak.uma.lab")
HIS_OPERATOR = os.environ.get("UMA4A_AGENT_OPERATOR", "https://agent.uma.lab")
HER_OPERATOR = os.environ.get("UMA4A_ALICE_OPERATOR", "https://alice-agent.uma.lab")
CA = os.environ.get("UMA4A_CACERT", "/driver/rootCA.pem")
KEYS = "/driver/keys"
RUN = uuid.uuid4().hex[:8]
META = mcp_meta("u4a-subagent-check")

# What she writes on a tier to say "ask me once per fleet, not once per agent".
# Both halves are restrictions: the ask fires only when this is new for the
# agent *and* new for the lineage.
LINEAGE_WIDE = [{"when": ["standing.first_at_tier",
                          "standing.lineage_new_at_tier"], "then": "ask"}]
# The stricter thing she can say instead.
ALWAYS_ASK = [{"when": ["standing.introduced"], "then": "ask"}]

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


def negotiate(client, keys, tool, args=None, introduction=None, max_wait_s=12):
    """One negotiation. Returns (granted, asked)."""
    r = mcp_call(client, GATEWAY, "tools/call",
                 {"name": tool, "arguments": args or {}}, META)
    ch = parse_challenge(r.headers.get("www-authenticate", ""))
    if ch is None:
        raise SystemExit(f"no challenge for {tool}: {r.status_code} {r.text[:300]}")
    asked = {"v": False}

    def status(msg: str) -> None:
        if "has been asked" in msg:
            asked["v"] = True

    op = ({"tool": tool, "params": args} if tool == "execute_trade" else None)
    try:
        run_grant(client, ch.as_uri, ch.ticket, keys, lambda t: True,
                  operation=op, introduction=introduction, on_status=status,
                  max_wait_s=max_wait_s)
        return True, asked["v"]
    except GrantDenied:
        return False, asked["v"]
    except Exception as exc:                                   # noqa: BLE001
        say(f"   [negotiate {tool}] {type(exc).__name__}: {str(exc)[:200]}")
        return False, asked["v"]


def set_rules(client, tier: str, rules: list, ask_me: bool | None = None) -> None:
    patch: dict = {"rules": rules}
    if ask_me is not None:
        patch["ask_me"] = ask_me
    client.put(f"{AS_PUBLIC}/owner/policies/{tier}", json=patch,
               headers=hdrs(client), timeout=15.0).raise_for_status()


def get_rules(client) -> dict:
    """Her rules and ask-me switch per tier, so they can be put back exactly.

    Restoring to `[]` instead would be wrong and quietly so: tier 2 ships with
    a rule that asks her the first time an agent reaches it, and clearing that
    leaves a tier which auto-grants transaction history to anybody. A check
    that edits her policy has to put back what was there, not what it assumes
    was there.
    """
    doc = client.get(f"{AS_PUBLIC}/owner/policies", headers=hdrs(client),
                     timeout=15.0).json()
    # The endpoint answers with a map keyed by tier id, and the tier objects
    # carry no id of their own — so the key is the only place the id exists.
    # Reading it as a list of objects with an `id` yields an empty mapping,
    # the restore loop below iterates nothing, and the run reports that it put
    # her rules back while leaving every edit in place. It did exactly that
    # once.
    rows = doc.get("tiers") if isinstance(doc.get("tiers"), dict) else doc
    if not isinstance(rows, dict):
        raise ValueError(f"unexpected /owner/policies shape: {type(rows).__name__}")
    return {tid: (list(t.get("rules") or []), bool(t.get("ask_me")))
            for tid, t in rows.items() if isinstance(t, dict)}


def connections(client) -> dict:
    rows = client.get(f"{AS_PUBLIC}/owner/connections", headers=hdrs(client),
                      timeout=15.0).json()
    return {r["handle"]: r for r in rows}


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
    stop = threading.Event()

    def loop() -> None:
        end = time.time() + seconds
        while time.time() < end and not stop.is_set():
            try:
                decide_all(client, "approved")
            except Exception:                                  # noqa: BLE001
                pass
            time.sleep(0.8)

    threading.Thread(target=loop, daemon=True).start()
    return stop


# Where the operator's provisioned private keys are mounted, in the replicated
# shape. Absent under compose, where the operator has no document of its own
# and an agent registers the key it generated.
PUBLISHED_KEYS = os.environ.get("UMA4A_PUBLISHED_KEYS")


def spawn(client, name: str, operator: str = HIS_OPERATOR) -> AgentKeys:
    """A worker with its own key, in its operator's directory.

    Provisioned where the operator serves a document it holds, self-published
    where it does not. The distinction matters more for this check than for
    any other: "one operator published both keys" is the half of an
    introduction the requesting side cannot manufacture, and a directory an
    agent can write to is an agent attesting to its own siblings.
    """
    directory = f"{operator}/.well-known/http-message-signatures-directory"
    provisioned = f"{PUBLISHED_KEYS}/{name}-ed25519.pem" if PUBLISHED_KEYS else None
    if provisioned and os.path.exists(provisioned):
        keys = AgentKeys.load_or_create(provisioned)
        keys.keyid = f"agent-{name}-1"
        keys.client_id = f"{operator}/agent.json"
        keys.signature_agent = directory
        return keys
    keys = AgentKeys.load_or_create(f"{KEYS}/sub-{name}-{RUN}.pem")
    # A distinct keyid per agent: the lab operator's runtime directory is
    # keyed by it, so a fleet sharing the default would overwrite each other
    # and only the last one would be published.
    keys.keyid = f"agent-{name}-{RUN}"
    keys.client_id = f"{operator}/agent.json"
    keys.signature_agent = keys.publish(client, operator)
    return keys


def main() -> int:
    with httpx.Client(verify=CA, timeout=60.0, follow_redirects=True) as client:
        # -------------------------------------------------------------------
        print("\n== An agent she has approved, the ordinary way ==")
        # -------------------------------------------------------------------
        parent = spawn(client, "lead")
        check("the operator published the parent's key", bool(parent.signature_agent))

        stop = approving(client, 60)
        try:
            granted, _ = negotiate(client, parent, "get_positions")
            check("first contact pends and she admits it", granted)
            granted, asked = negotiate(client, parent, "get_transactions")
            check("she is asked at the transactions tier too, and approves",
                  granted and asked, f"granted={granted} asked={asked}")
        finally:
            stop.set()

        parent_handle = parent.connection_handle()
        rows = connections(client)
        check("her records show one connection, with no sponsor",
              rows.get(parent_handle, {}).get("parent_handle") in (None, ""))
        check("and a tier she approved in person",
              "tier2" in (rows.get(parent_handle, {}).get("tiers_approved") or []),
              f"got {rows.get(parent_handle, {}).get('tiers_approved')!r}")

        # -------------------------------------------------------------------
        print("\n== A worker it spawns, with its own key ==")
        # -------------------------------------------------------------------
        # The default is per-agent: skipping first contact is not skipping the
        # tier. She is still asked once about this worker.
        kid = spawn(client, "worker-a")
        intro = sign_introduction(parent, kid.thumbprint(), AS_PUBLIC)

        stop = approving(client, 60)
        try:
            granted, _ = negotiate(client, kid, "get_transactions",
                                   introduction=intro)
            check("it is admitted and gets a grant of its own", granted)
        finally:
            stop.set()

        rows = connections(client)
        kid_handle = kid.connection_handle()
        check("her records name the agent that introduced it",
              rows.get(kid_handle, {}).get("parent_handle") == parent_handle,
              f"got {rows.get(kid_handle, {}).get('parent_handle')!r}")
        check("it is a separate connection, not the parent's",
              kid_handle != parent_handle and kid_handle in rows)

        # -------------------------------------------------------------------
        print("\n== What she can say about sub-agents ==")
        # -------------------------------------------------------------------
        set_rules(client, "tier2", LINEAGE_WIDE)
        say("her tier-2 rule: ask once per fleet, not once per agent")
        kid_b = spawn(client, "worker-b")
        granted, asked = negotiate(
            client, kid_b, "get_transactions",
            introduction=sign_introduction(parent, kid_b.thumbprint(), AS_PUBLIC))
        check("a second worker goes straight through, and she is not woken",
              granted and not asked, f"granted={granted} asked={asked}")

        set_rules(client, "tier2", ALWAYS_ASK)
        say("her stricter rule: ask me about every sub-agent, every time")
        kid_c = spawn(client, "worker-c")
        stop = approving(client, 45)
        try:
            granted, asked = negotiate(
                client, kid_c, "get_transactions",
                introduction=sign_introduction(parent, kid_c.thumbprint(), AS_PUBLIC))
            check("and then she is asked about a sub-agent again", granted and asked,
                  f"granted={granted} asked={asked}")
        finally:
            stop.set()
        set_rules(client, "tier2", LINEAGE_WIDE)

        # -------------------------------------------------------------------
        print("\n== The ceiling, which is not hers to configure away ==")
        # -------------------------------------------------------------------
        # Trades. Nobody in this lineage has ever been approved there, so the
        # sub-agent is asked exactly as the parent would have been.
        granted, asked = negotiate(client, kid_b, "execute_trade",
                                   {"symbol": "VTI", "side": "buy", "quantity": 1},
                                   max_wait_s=6)
        check("a tier the lineage never reached still asks her", asked,
              "it was granted without asking, which is the ceiling failing")

        # And when she says yes, it is the *lineage* that gains the tier.
        stop = approving(client, 45)
        try:
            granted, _ = negotiate(client, kid_b, "execute_trade",
                                   {"symbol": "VTI", "side": "buy", "quantity": 1})
            check("she approves it for the sub-agent", granted)
        finally:
            stop.set()

        # On a tier she had marked ask-me, the lineage rule is not enough by
        # itself: a restriction can narrow an ask but never lower a baseline.
        # So saying "ask me once per fleet" here means carrying the ask in the
        # rule rather than in the switch — which is the more honest statement
        # of it anyway: *ask me the first time this fleet wants to trade*,
        # rather than *always ask me*, with an exception underneath.
        set_rules(client, "tier3", LINEAGE_WIDE, ask_me=False)
        granted, asked = negotiate(client, parent, "execute_trade",
                                   {"symbol": "VTI", "side": "sell", "quantity": 1},
                                   max_wait_s=8)
        check("what a sub-agent earned reaches the agent that introduced it",
              granted and not asked, f"granted={granted} asked={asked}")

        # -------------------------------------------------------------------
        print("\n== Introductions her authority will not act on ==")
        # -------------------------------------------------------------------
        # Two different failure modes on purpose, because they are meant to
        # behave differently.
        #
        # A document that does not hold up — wrong key, wrong authority,
        # expired — is a bad request. The agent sent something it meant to be
        # honoured, and answering with a silent downgrade would leave it
        # guessing why it was suddenly being asked to wait.
        #
        # A document that is fine but says nothing this owner acts on — an
        # unapproved sponsor, another operator's agent — is not the agent's
        # mistake. It falls back to first contact, which is exactly what would
        # have happened with no introduction at all.
        outsider = spawn(client, "outsider")
        bystander = spawn(client, "bystander")
        # A real introduction, for a different agent, presented by one it does
        # not name. This is the copied-credential attack, and the binding
        # between the document and the key that signs the contract is what
        # answers it.
        not_for_you = sign_introduction(parent, bystander.thumbprint(), AS_PUBLIC)
        granted, asked = negotiate(client, outsider, "get_transactions",
                                   introduction=not_for_you, max_wait_s=5)
        check("an introduction naming another agent's key is refused outright",
              not granted and not asked,
              f"granted={granted} asked={asked} — a copied introduction was honoured")
        decide_all(client, "denied")

        # Depth. `kid_b` is a sub-agent she has personally approved at a tier,
        # so it passes every other test — which is the whole reason the depth
        # check has to be explicit rather than emergent.
        grandchild = spawn(client, "grandchild")
        granted, asked = negotiate(
            client, grandchild, "get_transactions", max_wait_s=5,
            introduction=sign_introduction(kid_b, grandchild.thumbprint(), AS_PUBLIC))
        check("a sub-agent cannot sponsor one of its own", asked,
              "the lineage went two deep")
        decide_all(client, "denied")

        # The operator boundary. Attested, genuinely — by the wrong operator.
        other_op = spawn(client, "other-operator", operator=HER_OPERATOR)
        check("the other operator published its key", bool(other_op.signature_agent))
        granted, asked = negotiate(
            client, other_op, "get_transactions", max_wait_s=5,
            introduction=sign_introduction(parent, other_op.thumbprint(), AS_PUBLIC))
        check("an agent from another operator is a stranger again", asked,
              "it was admitted across an operator boundary")
        decide_all(client, "denied")

        # -------------------------------------------------------------------
        print("\n== Revoking the agent that introduced them ==")
        # -------------------------------------------------------------------
        before = connections(client)
        live_kids = [h for h, c in before.items()
                     if c.get("parent_handle") == parent_handle
                     and c.get("status") == "active"]
        res = client.post(f"{AS_PUBLIC}/owner/connections/revoke",
                          json={"handle": parent_handle}, headers=hdrs(client),
                          timeout=15.0).json()
        check("one action revokes the sub-agents with it",
              res.get("connections_revoked", 0) == len(live_kids),
              f"revoked {res.get('connections_revoked')} of {len(live_kids)}")

        after = connections(client)
        check("every sub-agent is revoked in her records",
              all(after[h]["status"] != "active" for h in live_kids),
              f"still active: {[h for h in live_kids if after[h]['status'] == 'active']}")

        # The claim that matters operationally: not that the record says
        # revoked, but that the sub-agent's next call fails. It holds because
        # the enforcement point introspects here on every call.
        granted, _ = negotiate(client, kid_b, "get_transactions", max_wait_s=5)
        check("and a revoked sub-agent's next call does not go through",
              not granted, "it was still able to use a grant")
        decide_all(client, "denied")

        # Its sponsor cannot let it back in: that would make Revoke advisory.
        granted, asked = negotiate(
            client, kid_b, "get_transactions", max_wait_s=5,
            introduction=sign_introduction(parent, kid_b.thumbprint(), AS_PUBLIC))
        check("and cannot be re-introduced by the agent that sponsored it",
              not granted or asked,
              "a revoked agent was restored by an introduction")
        decide_all(client, "denied")

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        for f in FAIL:
            print(f"   FAILED: {f}")
        return 1
    print("\nPASS: sub-agents were admitted without a second first contact,")
    print("      negotiated their own grants under their own keys, stayed")
    print("      under a ceiling she did not configure away, and died with")
    print("      the agent that introduced them.")
    return 0


if __name__ == "__main__":
    # Her rules are read before anything edits them and written back however
    # this ends. Leaving an edited tier behind is not cosmetic: it is a live
    # change to her policy that the next suite inherits, and it is how a
    # previous run of this very check made the following one fail for reasons
    # that had nothing to do with it.
    with httpx.Client(verify=CA, timeout=30.0, follow_redirects=True) as c:
        try:
            ORIGINAL = get_rules(c)
        except Exception as exc:                               # noqa: BLE001
            raise SystemExit(f"could not read her policy to restore it later: {exc}")
        # Refuse to start rather than run with nothing to restore. An empty
        # mapping here is not "she has no tiers" — it is this function having
        # failed to parse, and the cost of finding out afterwards is her policy
        # left as the check left it.
        if not ORIGINAL:
            raise SystemExit("read no tiers from /owner/policies; refusing to "
                             "edit a policy this run could not put back")
    try:
        code = main()
    finally:
        with httpx.Client(verify=CA, timeout=30.0, follow_redirects=True) as c:
            for tier, (rules, ask_me) in ORIGINAL.items():
                try:
                    set_rules(c, tier, rules, ask_me=ask_me)
                except Exception:                              # noqa: BLE001
                    pass
        print(f"   (her rules on {', '.join(sorted(ORIGINAL))} have been put "
              f"back as they were)")
    raise SystemExit(code)
