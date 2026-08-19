"""Two intents, and what the grant does with each.

Alice states what she will accept, in advance, in her tiers. An agent states
what it wants and — optionally — why it is asking and under whose mandate. The
grant is the only place both are in hand at once, and what it does there is
narrow on purpose.

**Her terms cannot be signed weaker than she wrote them.** The echo is compared
field by field. A valid signature over a dropped prohibition or a stretched
expiry is exactly what an adversarial agent would send, so it ends the
negotiation. Binding itself to *more* than she asked is allowed, because that
direction costs her nothing.

**What the agent says it is for is carried, not judged.** Her authority never
reads the reason and never compares it to her purpose — that would put a
judgement about natural language inside an authorization decision. It is
bounded, stored, and put in front of her. The one thing her policy may do with
it is notice it is missing:

    a lie can only cost the liar friction; silence costs it the same

**A cited mandate is a claim, not an axis.** An AAuth mission reference travels
in AAuth's own shape and is recorded, never dereferenced — missions are served
to administrators, so from here an agent citing a real one and an agent
inventing a hash are the same agent.

**Drift is read from her side.** Nothing asks the requesting side whether its
agent is behaving; she cannot inspect that infrastructure and has nothing to
check a report against. What she has is every request that arrived at hers,
filed under the agent that made it and the tier it was made against. Breadth
and volume are shapes in her own record.

**Some of her prohibitions are refused and some are only promised.** The line
is whether the forbidden thing has to cross her boundary to happen. Placing an
order beyond approved parameters means calling her tool; retaining the data
afterwards happens where she cannot see. Her published terms mark which is
which.

**The record answers a question about an agent, not only about a request.**
One exception is real and worth seeing: a decline arrives before anything is
signed, so there is nobody to name.

Run against the full stack with `make intent-check`.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import uuid

import httpx

sys.path.insert(0, "/driver/lib")
from uma4a_grant import (  # noqa: E402
    AGREEMENT_FORMAT, GRANT_TYPE, AgentKeys, GrantDenied, mcp_call, mcp_meta,
    parse_challenge, run_grant, sign_contract, signed_headers,
)

GATEWAY_AUTHORITY = os.environ.get("UMA4A_GATEWAY_AUTHORITY", "gateway.uma.lab")
MCP_PATH = "/mcp"

GATEWAY = os.environ.get("UMA4A_GATEWAY", "https://gateway.uma.lab/mcp")
AS_PUBLIC = os.environ.get("UMA4A_AS", "https://alice-as.uma.lab")
KEYCLOAK = os.environ.get("UMA4A_OIDC", "https://keycloak.uma.lab")
OPERATOR = os.environ.get("UMA4A_AGENT_OPERATOR", "https://agent.uma.lab")
CA = os.environ.get("UMA4A_CACERT", "/driver/rootCA.pem")
KEYS = "/driver/keys"
MAX_REASON = int(os.environ.get("UMA_AS_MAX_REASON", "512"))
RUN = uuid.uuid4().hex[:8]
META = mcp_meta("u4a-intent-check")

PASS, FAIL = [], []


def say(msg: str) -> None:
    print(f"   {msg}", flush=True)


def check(name: str, ok: bool, detail: str = "") -> None:
    """`detail` is the diagnostic for a failure and is printed only then —
    beside `ok` it reads as a contradiction. Anything worth seeing on a pass
    goes through `say`."""
    (PASS if ok else FAIL).append(name)
    print(f"   {'ok  ' if ok else 'FAIL'} {name}"
          + (f" — {detail}" if detail and not ok else ""), flush=True)


def owner_hdrs(client: httpx.Client) -> dict:
    r = client.post(f"{KEYCLOAK}/realms/alice/protocol/openid-connect/token",
                    data={"grant_type": "password", "client_id": "alice-portal",
                          "username": "alice",
                          "password": os.environ.get("ALICE_PASSWORD", "alice-demo")},
                    timeout=15.0)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def pending(client: httpx.Client) -> list:
    return client.get(f"{AS_PUBLIC}/owner/pending", headers=owner_hdrs(client),
                      timeout=15.0).json()


def decide_all(client: httpx.Client, decision: str) -> int:
    hdrs, n = owner_hdrs(client), 0
    for p in pending(client):
        client.post(f"{AS_PUBLIC}/owner/pending/{p['family']}/decision",
                    json={"decision": decision}, headers=hdrs, timeout=15.0)
        n += 1
    return n


def ledger(client: httpx.Client, handle: str | None = None) -> list:
    params = {"handle": handle} if handle else None
    return client.get(f"{AS_PUBLIC}/owner/ledger", params=params,
                      headers=owner_hdrs(client), timeout=15.0).json()


def approve_in_background(client: httpx.Client, seconds: float):
    """Alice, answering promptly, and blind to who is asking.

    A connection is created when she approves *while the agent is still
    polling* — that is the day-1 handshake, one tap doing two things. An agent
    that gave up before she answered has no connection and no trajectory, which
    is correct and is why this check cannot just approve afterwards.
    """
    import threading
    import time as _t

    stop = threading.Event()

    def loop() -> None:
        deadline = _t.time() + seconds
        while _t.time() < deadline and not stop.is_set():
            try:
                decide_all(client, "approved")
            except Exception:                                      # noqa: BLE001
                pass
            _t.sleep(0.8)

    threading.Thread(target=loop, daemon=True).start()
    return stop


def refused_by_as(client, hdrs, tier_id: str, rules: list) -> bool:
    """Whether her authorization server declines to *store* this rule.

    The guarantee lives at save time, so this is the assertion that matters:
    a rule that could widen access on evidence the counterparty supplies has
    to fail to save, not fail quietly at evaluation."""
    r = client.post(f"{AS_PUBLIC}/owner/policies", headers=hdrs, timeout=15.0,
                    json={"id": tier_id, "name": "should not save",
                          "resources": [], "ask_me": True, "rules": rules,
                          "terms": {"purpose": "unstorable", "expires_in": 3600}})
    if r.status_code < 300:
        client.delete(f"{AS_PUBLIC}/owner/policies/{tier_id}", headers=hdrs,
                      timeout=15.0)
        return False
    return True


def thumbprint(keys: AgentKeys) -> str:
    """The handle a pseudonymous agent is filed under — RFC 7638, computed
    here rather than read back, so the check knows which rows are its own."""
    jwk = keys.public_jwk()
    canonical = json.dumps({"crv": jwk["crv"], "kty": jwk["kty"], "x": jwk["x"]},
                           separators=(",", ":"), sort_keys=True)
    return "jkt:" + base64.urlsafe_b64encode(
        hashlib.sha256(canonical.encode()).digest()).rstrip(b"=").decode()


def terms_doc(client: httpx.Client, template_id: str) -> dict:
    """Her published terms, as an agent or an auditor would fetch them."""
    r = client.get(f"{AS_PUBLIC}/terms/{template_id}",
                   headers={"accept": "application/json"}, timeout=15.0)
    r.raise_for_status()
    return r.json()


def challenge_for(client: httpx.Client, tool: str, args: dict):
    r = mcp_call(client, GATEWAY, "tools/call",
                 {"name": tool, "arguments": args}, META)
    ch = parse_challenge(r.headers.get("www-authenticate", ""))
    if ch is None:
        raise SystemExit(f"no challenge for {tool}: {r.status_code}")
    return ch


def negotiate(client, keys, tool, args=None, reason=None, max_wait_s=25):
    """One negotiation. Returns (granted, asked, error)."""
    args = args or {}
    ch = challenge_for(client, tool, args)
    asked = {"v": False}

    def status(msg: str) -> None:
        if "has been asked" in msg:
            asked["v"] = True

    try:
        rpt = run_grant(client, ch.as_uri, ch.ticket, keys, lambda t: True,
                        operation=({"tool": tool, "params": args} if args else None),
                        reason=reason, on_status=status, max_wait_s=max_wait_s)
    except GrantDenied as exc:
        return False, asked["v"], str(exc)
    # Spend it. A grant nobody uses leaves no record of anything being touched,
    # and half of what a trajectory shows is the distance between what was
    # promised and what the agent actually did.
    mcp_call(client, GATEWAY, "tools/call", {"name": tool, "arguments": args},
             META, headers=signed_headers("POST", GATEWAY_AUTHORITY, MCP_PATH,
                                          rpt, keys))
    return True, asked["v"], None


def commit_raw(client, keys, tool, mutate, reason=None, mission=None):
    """Present a contract built from a template we have altered by hand.

    The client in uma4a_grant never weakens anything, so the only way to check
    that the authority would catch it is to build the bad echo here.

    Returns the authority's refusal as one string, or None if the contract was
    accepted. `request_submitted` counts as accepted: the echo verified, and
    the request went on to Alice. Reporting only `error_description` would read
    a malformed request as a passing test, which is how the first draft of this
    check convinced itself the authority was broken.
    """
    ch = challenge_for(client, tool, {})
    r = client.post(f"{ch.as_uri}/token",
                    data={"grant_type": GRANT_TYPE, "ticket": ch.ticket},
                    timeout=15.0)
    body = r.json()
    if body.get("error") != "need_info":
        raise SystemExit(f"expected need_info at beat 2, got {body}")
    template = dict(body["required_claims"][0]["terms_template"])
    mutate(template)
    claim = sign_contract(template, keys, ch.as_uri, None, reason, mission)
    r = client.post(f"{ch.as_uri}/token",
                    data={"grant_type": GRANT_TYPE, "ticket": body["ticket"],
                          "claim_token": claim,
                          "claim_token_format": AGREEMENT_FORMAT},
                    timeout=15.0)
    out = r.json()
    err = out.get("error")
    if not err or err == "request_submitted":
        return None
    return f"{err}: {out.get('error_description', '')}".strip(": ")


def main() -> int:
    ca = CA if os.path.exists(CA) else True
    with httpx.Client(verify=ca, timeout=30.0) as client:
        decide_all(client, "denied")          # start from an empty queue
        hdrs = owner_hdrs(client)

        # ---------------------------------------------------------------
        print("\n== The echo is checked field by field ==")
        # ---------------------------------------------------------------
        tamper = AgentKeys.load_or_create(f"{KEYS}/intent-tamper-{RUN}.pem")

        err = commit_raw(client, tamper, "get_positions",
                         lambda t: t.update(purpose="whatever I like"))
        check("a rewritten purpose ends the negotiation",
              err is not None and "purpose" in err, err or "it was accepted")

        err = commit_raw(client, tamper, "get_positions",
                         lambda t: t.update(prohibited=t["prohibited"][:-1]))
        check("so does dropping one of her prohibitions",
              err is not None and "weakened" in err, err or "it was accepted")

        err = commit_raw(client, tamper, "get_positions",
                         lambda t: t.update(expires_in=t["expires_in"] * 10))
        check("and so does helping itself to a longer expiry",
              err is not None and "expiry" in err, err or "it was accepted")

        err = commit_raw(client, tamper, "get_positions",
                         lambda t: t.update(prohibited=t["prohibited"] + ["resale"]))
        check("binding itself to more than she asked is allowed",
              err is None, err or "")

        # ---------------------------------------------------------------
        print("\n== What it says it is for is carried, never judged ==")
        # ---------------------------------------------------------------
        stated = AgentKeys.load_or_create(f"{KEYS}/intent-stated-{RUN}.pem")
        # Named operator, so tier 1's own `assurance.accountability_below:1`
        # rule is satisfied and the only thing left that could disturb her is
        # the one this check is about.
        stated.client_id = f"{OPERATOR}/agent.json"
        errand = "Suitability review before Thursday's client meeting."

        # Read her queue before answering it, so the dialog can be inspected.
        seen = {"reason": None}

        def watch_then_approve() -> None:
            import threading
            import time as _t

            def loop() -> None:
                for _ in range(40):
                    for p in pending(client):
                        if p.get("reason"):
                            seen["reason"] = p["reason"]
                    if decide_all(client, "approved"):
                        return
                    _t.sleep(0.5)

            threading.Thread(target=loop, daemon=True).start()

        watch_then_approve()
        ok, asked, err = negotiate(client, stated, "get_positions", reason=errand)
        check("first contact pends until she answers", ok and asked, err or "")
        check("her approval dialog shows the agent's own words",
              seen["reason"] == errand, f"saw {seen['reason']!r}")
        say(f'she is shown: "{errand}"')

        ok, asked, err = negotiate(client, stated, "get_positions", reason=errand)
        check("and afterwards it negotiates without disturbing her",
              ok and not asked, err or "")

        promised = [e for e in ledger(client) if e["kind"] == "promised"]
        check("and the record keeps it beside what she dictated",
              any(e.get("reason") == errand for e in promised))
        check("her purpose is still hers, not the agent's",
              all(e.get("purpose") != errand for e in promised))

        err = commit_raw(client, tamper, "get_positions", lambda t: None,
                         reason="x" * (MAX_REASON + 1))
        check("a reason past the cap is refused rather than stored",
              err is not None and "length" in err, err or "it was accepted")

        payload = "<script>alert(document.cookie)</script>"
        ok, _, _ = negotiate(client, stated, "get_positions", reason=payload)
        stored = [e for e in ledger(client) if e.get("reason") == payload]
        check("markup in a reason is stored verbatim, to be escaped on render",
              bool(stored), "the authority must not sanitise what it records")

        # ---------------------------------------------------------------
        print("\n== A mandate, cited in the shape AAuth already uses ==")
        # ---------------------------------------------------------------
        # Bob's mission is Bob's: approved at his person server, evaluated
        # there, named here by content hash. Alice's authority records the
        # citation and can require her to look when there is none. What it
        # deliberately does not do is read the mandate and rule on whether
        # this request is inside it — that is the approver's question.
        mandated = AgentKeys.load_or_create(f"{KEYS}/intent-mandate-{RUN}.pem")
        mission = {"approver": "https://ps.uma.lab", "s256": "a" * 43}

        err = commit_raw(client, mandated, "get_positions",
                         lambda t: None, mission=mission)
        check("a well-formed citation is accepted", err is None, err or "")

        for bad, why in ((({"approver": "http://ps.uma.lab", "s256": "a" * 43}),
                          "an approver that is not https"),
                         (({"s256": "a" * 43}), "a citation with no approver"),
                         (({"approver": "https://ps.uma.lab", "s256": "x"}),
                          "a hash too short to be one"),
                         ("just-a-string", "a citation that is not an object")):
            err = commit_raw(client, mandated, "get_positions",
                             lambda t: None, mission=bad)
            check(f"refused: {why}", err is not None, "it was accepted")

        cited = [e for e in ledger(client)
                 if (e.get("mission") or {}).get("s256") == mission["s256"]]
        check("the citation is on the record beside her terms", bool(cited))
        check("and it is kept as a reference, not as text she has to trust",
              bool(cited) and set(cited[0]["mission"]) == {"approver", "s256"},
              f"got {cited[0]['mission'] if cited else None}")

        vocab_now = client.get(f"{AS_PUBLIC}/owner/policy-vocabulary",
                               headers=hdrs, timeout=15.0).json()
        check("she can ask to be told when nothing set the agent this task",
              any(v["condition"] == "request.mission_absent" for v in vocab_now))
        check("but citing one can never widen access",
              refused_by_as(client, hdrs, f"mandate{RUN}",
                            [{"when": ["request.mission_absent"],
                              "then": "auto"}]))
        check("and it is not an assurance axis, because nothing verified it",
              not any("mandate" in v["condition"] for v in vocab_now),
              "a level this authority cannot reach is not one it should award")

        # ---------------------------------------------------------------
        print("\n== The record answers questions about an agent ==")
        # ---------------------------------------------------------------
        other = AgentKeys.load_or_create(f"{KEYS}/intent-other-{RUN}.pem")
        approving = approve_in_background(client, 60)
        negotiate(client, other, "get_positions", reason="An unrelated errand.")
        negotiate(client, other, "get_positions", reason="An unrelated errand.")
        approving.set()

        conns = client.get(f"{AS_PUBLIC}/owner/connections", headers=hdrs,
                           timeout=15.0).json()
        active = [c["handle"] for c in conns if c["status"] == "active"]
        check("both agents hold a standing connection", len(active) >= 2,
              f"{len(active)} active")
        say(f"{len(active)} standing connections, each with its own trail")

        mine, theirs = ledger(client, handle=active[0]), ledger(client, handle=active[1])
        check("one agent's trajectory is one agent's",
              bool(mine) and all(e["handle"] == active[0] for e in mine))
        check("and holds none of the other's",
              not ({e["family"] for e in mine} & {e["family"] for e in theirs}))
        check("it holds what was promised and what was touched",
              {"promised", "touched"} <= {e["kind"] for e in mine},
              f"kinds: {sorted({e['kind'] for e in mine})}")
        say(f"one agent's trajectory: {sorted({e['kind'] for e in mine})}")
        check("an unknown agent has an empty trajectory",
              ledger(client, handle="jkt:nobody") == [])

        declined = AgentKeys.load_or_create(f"{KEYS}/intent-declined-{RUN}.pem")
        ch = challenge_for(client, "get_positions", {})
        r = client.post(f"{ch.as_uri}/token",
                        data={"grant_type":
                              "urn:ietf:params:oauth:grant-type:uma-ticket",
                              "ticket": ch.ticket}, timeout=15.0)
        client.post(f"{ch.as_uri}/token",
                    data={"grant_type":
                          "urn:ietf:params:oauth:grant-type:uma-ticket",
                          "ticket": r.json()["ticket"], "decline": "true"},
                    timeout=15.0)
        refusals = [e for e in ledger(client) if e["kind"] == "refused"]
        check("a decline is recorded with nobody to name",
              any(e.get("handle") is None for e in refusals),
              "there is no signature at beat 2, so there is no agent yet")

        # ---------------------------------------------------------------
        print("\n== Drift, seen from the side that can actually see it ==")
        # ---------------------------------------------------------------
        # Nothing here asks Bob's side whether its agent is behaving. She
        # cannot see his infrastructure and has no reason to believe a report
        # from it. What she can see is every request that arrived at hers, and
        # that is enough: an agent admitted for one thing and then reaching
        # across her resources looks different in her own record.
        drifter = AgentKeys.load_or_create(f"{KEYS}/intent-drift-{RUN}.pem")
        drifting = approve_in_background(client, 90)
        try:
            negotiate(client, drifter, "get_positions", {},
                      reason="Quarterly review for the client.")
            for _ in range(2):
                negotiate(client, drifter, "get_positions", {})
            negotiate(client, drifter, "get_transactions",
                      {"account": "brokerage-main"},
                      reason="Still the quarterly review.")
        finally:
            drifting.set()

        traj = ledger(client, handle=thumbprint(drifter))
        touched = [e for e in traj if e["kind"] == "touched"]
        tiers = sorted({e.get("tier") for e in traj if e.get("tier")})
        check("her record holds what it did, not only what it asked",
              len(touched) >= 3, f"{len(touched)} calls recorded")
        check("every call is filed under the tier it was made against",
              all(e.get("tier") for e in touched),
              f"{[e.get('tier') for e in touched]}")
        check("and the widening is visible as more than one tier",
              len(tiers) >= 2, f"reached {tiers}")
        say(f"one agent, {len(touched)} calls across {len(tiers)} of her tiers")

        # A rule reading exactly that. It names no agent, and it is written
        # against her own record rather than against anything the agent said.
        r = client.post(f"{AS_PUBLIC}/owner/policies", headers=hdrs, timeout=15.0,
                        json={"id": f"drift{RUN}", "name": "Watch the trajectory",
                              "resources": [], "ask_me": False,
                              "rules": [{"when": ["standing.tiers_above:1"],
                                         "then": "ask"},
                                        {"when": ["standing.calls_above:2"],
                                         "then": "ask"}],
                              "terms": {"purpose": "drift", "expires_in": 900}})
        check("she can write a rule about the trajectory itself",
              r.status_code < 300, r.text[:160])
        check("and it cannot be turned into a reason to grant",
              refused_by_as(client, hdrs, f"driftauto{RUN}",
                            [{"when": ["standing.calls_above:2"], "then": "auto"}]))
        if r.status_code < 300:
            client.delete(f"{AS_PUBLIC}/owner/policies/drift{RUN}",
                          headers=hdrs, timeout=15.0)

        # ---------------------------------------------------------------
        print("\n== Which of her terms are refused, and which are only promised ==")
        # ---------------------------------------------------------------
        # The line worth drawing is not terms-versus-enforcement. It is
        # whether the thing forbidden has to cross her boundary to happen.
        # Placing an order beyond the approved parameters means calling her
        # tool, and the enforcement point is holding a grant that names those
        # parameters. Retaining the data afterwards happens on the requester's
        # own disks, and no protocol reaches it.
        t1 = terms_doc(client, "alice/advisor-tier1/v2")
        t3 = terms_doc(client, "alice/advisor-tier3/v2")
        check("her trade tier marks the prohibitions it actually refuses",
              set(t3.get("enforced") or {})
              == {"orders-beyond-approved-parameters",
                  "discretionary-reuse-of-authority"},
              f"got {sorted((t3.get('enforced') or {}))}")
        check("and names the mechanism that refuses each",
              (t3["enforced"]["orders-beyond-approved-parameters"]
               == "operation-binding")
              and (t3["enforced"]["discretionary-reuse-of-authority"]
                   == "single-use"))
        check("her holdings tier claims none, because none of them cross her door",
              not (t1.get("enforced") or {}),
              f"got {sorted((t1.get('enforced') or {}))}")
        check("the enforced ones are a subset of what she actually prohibits",
              set(t3["enforced"]) <= set(t3["prohibited"]))
        say("two of her trade prohibitions are refused; the rest are undertakings")

        # ---------------------------------------------------------------
        print("\n== And policy can read it, naming no agent ==")
        # ---------------------------------------------------------------
        tier_id = f"intentcheck{RUN}"
        r = client.post(
            f"{AS_PUBLIC}/owner/policies", headers=hdrs, timeout=15.0,
            json={"id": tier_id, "name": "Intent check",
                  "resources": [], "ask_me": False,
                  "rules": [{"when": ["request.reason_absent"], "then": "ask"},
                            {"when": ["standing.denials_above:1"], "then": "ask"}],
                  "terms": {"purpose": "Checking that intent rules save",
                            "expires_in": 3600}})
        check("a tier reading the reason and the record saves", r.status_code < 300,
              r.text[:160])

        r = client.post(
            f"{AS_PUBLIC}/owner/policies", headers=hdrs, timeout=15.0,
            json={"id": f"{tier_id}bad", "name": "Should not save",
                  "resources": [], "ask_me": True,
                  "rules": [{"when": ["standing.denials_above:1"], "then": "auto"}],
                  "terms": {"purpose": "Trying to relax on her own refusals",
                            "expires_in": 3600}})
        check("a rule relaxing on her own refusals does not", r.status_code >= 400,
              "it saved, which would let a denial argue for a grant")

        vocab = client.get(f"{AS_PUBLIC}/owner/policy-vocabulary", headers=hdrs,
                           timeout=15.0).json()
        offered = {v["condition"].split(":")[0] for v in vocab}
        check("all four are offered to her policy editor",
              {"request.reason_absent", "request.mission_absent",
               "standing.denials_above", "standing.tiers_above"} <= offered)

        client.delete(f"{AS_PUBLIC}/owner/policies/{tier_id}", headers=hdrs,
                      timeout=15.0)

        # A queue left full makes the next thing anyone runs look broken.
        drained = decide_all(client, "denied")
        say(f"queue left empty ({drained} of this check's requests dismissed)")

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        return 1
    print("\nPASS: her terms could not be signed weaker than she wrote them, the")
    print("      ones her enforcement point actually refuses are marked as such,")
    print("      what the agent said it wanted was recorded and never judged,")
    print("      and drift was read from her own record rather than reported by")
    print("      the side being watched — tightening only, and naming no agent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
