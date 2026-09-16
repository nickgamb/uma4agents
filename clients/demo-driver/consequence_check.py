"""What an operation leaves behind, and who gets to say so.

Alice can write "ask me about anything that cannot be undone" only if
something says which operations those are. Every deployment knows — this lab
has always treated `execute_trade` as an act you cannot take back — and until
now it knew it in two hardcoded sets that no other party could read, for a
reason that appeared in no document at all.

The class is Nat Sakimura's vocabulary: reversible, compensatable,
forward-recoverable, irreversible. What this check is really about is who
declares it, because a self-asserted capability claim is advertising rather
than governance:

  * the **resource** declares it, in the metadata it already signs. It is the
    party that would have to undo the act, so it is the only one in a
    position to say. A requesting agent's own description of itself stays
    display-only for exactly the opposite reason (see docs/PROTOCOL.md,
    extension 11);
  * her authority **pulls** it into her registry with everything else the
    resource publishes, so what her rules read is what the resource said
    rather than what this deployment was configured with;
  * reading it can only ever **tighten**. The condition is unwritable as a
    relaxation — her editor refuses to save it — which is the same asymmetry
    assurance already has;
  * **absent is unknown**, and unknown is neither benign nor severe. MCP's
    tool annotations default to assuming the worst of an unannotated tool,
    which is right for a client deciding whether to show a confirmation box
    and wrong here, where it would make every undescribed operation in every
    existing deployment look irreversible on the day this shipped. She has a
    separate condition for "nobody has said", and it is hers to use.

The rule she ends up with names no tool. That is the whole point: it holds for
tools she has never seen, at resource servers she has never heard of, on the
day they are added.

Run against the full stack with `make consequence-check`, or in the cluster
with `make k8s-consequence-check`. Unit tests, needing nothing running:
`make rules-test` and `make pep-test`.
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import threading
import uuid

import httpx

sys.path.insert(0, "/driver/lib")
from uma4a_grant import (  # noqa: E402
    AgentKeys, mcp_call, mcp_json, mcp_meta, parse_challenge, run_grant,
    signed_headers,
)

GATEWAY = os.environ.get("UMA4A_GATEWAY", "https://gateway.uma.lab/mcp")
GATEWAY_AUTHORITY = os.environ.get("UMA4A_GATEWAY_AUTHORITY", "gateway.uma.lab")
MCP_PATH = "/mcp"
AS_PUBLIC = os.environ.get("UMA4A_AS", "https://alice-as.uma.lab")
KEYCLOAK = os.environ.get("UMA4A_OIDC", "https://keycloak.uma.lab")
CA = os.environ.get("UMA4A_CACERT", "/driver/rootCA.pem")
KEYS = "/driver/keys"
RUN = uuid.uuid4().hex[:8]
META = mcp_meta("u4a-consequence-check")

# The rule under test. It names a property of the act, never a tool.
ASK_ON_IRREVERSIBLE = {"when": ["request.consequence_at_or_above:irreversible"],
                       "then": "ask"}

PASS, FAIL = [], []


def say(msg: str) -> None:
    print(f"   {msg}", flush=True)


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"   {'ok  ' if ok else 'FAIL'} {name}"
          + (f" — {detail}" if detail and not ok else ""), flush=True)


def owner_hdrs(client: httpx.Client) -> dict:
    r = client.post(f"{KEYCLOAK}/realms/alice/protocol/openid-connect/token",
                    data={"grant_type": "password", "client_id": "meridian-portal",
                          "username": "alice",
                          "password": os.environ.get("ALICE_PASSWORD", "alice-demo")},
                    timeout=15.0)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def tiers(client: httpx.Client) -> dict:
    return client.get(f"{AS_PUBLIC}/owner/policies", headers=owner_hdrs(client),
                      timeout=15.0).json()


def put_tier(client: httpx.Client, tier_id: str, patch: dict) -> httpx.Response:
    return client.put(f"{AS_PUBLIC}/owner/policies/{tier_id}", json=patch,
                      headers=owner_hdrs(client), timeout=15.0)


def pending(client: httpx.Client) -> list:
    return client.get(f"{AS_PUBLIC}/owner/pending", headers=owner_hdrs(client),
                      timeout=15.0).json()


def decide(client: httpx.Client, family: str, decision: str) -> None:
    client.post(f"{AS_PUBLIC}/owner/pending/{family}/decision",
                json={"decision": decision}, headers=owner_hdrs(client),
                timeout=15.0)


def ledger(client: httpx.Client) -> list:
    return client.get(f"{AS_PUBLIC}/owner/ledger", headers=owner_hdrs(client),
                      timeout=15.0).json()


def challenge_for(client: httpx.Client, tool: str, args: dict | None = None):
    """Beat 1, and the header it comes back with."""
    r = mcp_call(client, GATEWAY, "tools/call",
                 {"name": tool, "arguments": args or {}}, META)
    return r, parse_challenge(r.headers.get("www-authenticate", ""))


def remediation_of(www_authenticate: str) -> dict:
    """The `authorization_remediation` object, decoded from the challenge.

    Base64url JSON in a header parameter — the same object the JSON-RPC
    encoding carries, which is why the class an agent reads does not depend on
    which binding refused it.
    """
    m = re.search(r'authorization_remediation="([^"]+)"', www_authenticate or "")
    if not m:
        return {}
    blob = m.group(1)
    return json.loads(base64.urlsafe_b64decode(blob + "=" * (-len(blob) % 4)))


def grant_in_background(client, ch, keys, operation=None):
    """run_grant, off the main thread, so a pend can be inspected while it waits.

    A pended negotiation is the interesting state here: the whole claim is
    that it pended *because of the class*, and that is only readable while the
    request is still in front of her.
    """
    out = {}

    def go() -> None:
        try:
            out["rpt"] = run_grant(client, ch.as_uri, ch.ticket, keys,
                                   lambda t: True, operation=operation,
                                   max_wait_s=90)
        except Exception as exc:                                   # noqa: BLE001
            out["error"] = exc

    t = threading.Thread(target=go, daemon=True)
    t.start()
    return out, t


def await_pend(client, seconds: float = 45.0) -> dict | None:
    import time as _t

    deadline = _t.time() + seconds
    while _t.time() < deadline:
        for p in pending(client):
            return p
        _t.sleep(1.0)
    return None


def main() -> int:
    client = httpx.Client(verify=CA, timeout=30.0, follow_redirects=True)
    keys = AgentKeys.load_or_create(f"{KEYS}/consequence-{RUN}.json")
    original: dict[str, dict] = {}

    print("\n== 1 · the resource says what its own operations leave behind ==")
    doc = client.get(
        f"https://{GATEWAY_AUTHORITY}/.well-known/oauth-protected-resource/mcp"
    ).json()
    declared = {s["tool"]: s.get("consequence")
                for s in doc.get("tool_surfaces") or []}
    say(f"published: {', '.join(f'{t}={c}' for t, c in sorted(declared.items()))}")
    check("the trade declares that it cannot be undone",
          declared.get("execute_trade") == "irreversible", str(declared))
    check("and the two reads declare that there is nothing to put back",
          declared.get("get_positions") == "reversible"
          and declared.get("get_transactions") == "reversible", str(declared))

    # Inside the signature, not appended to the document afterwards: a relayed
    # copy carries the claim and stays attributable to the resource.
    signed = doc.get("signed_metadata") or ""
    payload = json.loads(base64.urlsafe_b64decode(
        signed.split(".")[1] + "=" * (-len(signed.split(".")[1]) % 4)))
    check("the class is covered by the resource's own signature",
          {s["tool"]: s.get("consequence")
           for s in payload.get("tool_surfaces") or []} == declared)

    # One registry, two encodings. A client that reads either learns the same
    # thing about the same operation.
    aauth = client.get(
        f"https://{GATEWAY_AUTHORITY}/.well-known/aauth-resource.json").json()
    ops = (aauth.get("r3_vocabularies") or [{}])[0].get("operations") or []
    check("the AAuth encoding of the same registry agrees, operation for operation",
          {(o.get("tool") or o.get("operation")): o.get("consequence")
           for o in ops} == declared, json.dumps(ops))

    print("\n== 2 · her authority holds what the resource published ==")
    resources = {r["_id"]: r for r in client.get(
        f"{AS_PUBLIC}/owner/resources", headers=owner_hdrs(client),
        timeout=20.0).json()}
    check("the class arrives in her registry by the pull, not by configuration",
          (resources.get("alice-vault/execute_trade") or {}).get("consequence")
          == "irreversible")
    check("and it is there for every operation the resource described",
          all((resources.get(f"alice-vault/{t}") or {}).get("consequence") == c
              for t, c in declared.items() if c))

    print("\n== 3 · what her policy is allowed to do with it ==")
    vocab = {v["condition"]: v for v in client.get(
        f"{AS_PUBLIC}/owner/policy-vocabulary", headers=owner_hdrs(client),
        timeout=15.0).json()}
    offered = [c for c in vocab if c.startswith("request.consequence")]
    check("her editor offers the classes as conditions", len(offered) >= 3,
          str(sorted(vocab)))
    check("and says that none of them may relax a requirement",
          all(not vocab[c]["may_relax"] for c in offered))

    r = put_tier(client, "tier1", {"rules": [{"when": [ASK_ON_IRREVERSIBLE["when"][0]],
                                             "then": "auto"}]})
    check("a rule that would grant automatically because an act is "
          "irreversible cannot be saved at all", r.status_code == 400,
          f"HTTP {r.status_code}")
    r = put_tier(client, "tier1", {"rules": [
        {"when": ["request.consequence_at_or_above:catastrophic"], "then": "ask"}]})
    check("nor one naming a class nobody defined", r.status_code == 400,
          f"HTTP {r.status_code}")

    print("\n== 4 · the rule she writes names no tool ==")
    try:
        original = {t: dict(v) for t, v in tiers(client).items()}
        # Her holdings tier normally asks about an agent nobody is accountable
        # for; replaced here so the only rule in play is the one under test.
        put_tier(client, "tier1", {"rules": [ASK_ON_IRREVERSIBLE]})
        # And her trade tier stops asking about everything, so that when it
        # asks it is the class doing it and not the blanket switch.
        put_tier(client, "tier3", {"ask_me": False, "rules": [ASK_ON_IRREVERSIBLE]})
        say("tier 1 and tier 3 now carry one rule: ask about what cannot be undone")

        # First contact still pends — being unknown is not the same as being
        # irreversible, and this is the day-1 handshake rather than the rule.
        r, ch = challenge_for(client, "get_positions")
        check("an unauthorized call is challenged", ch is not None,
              f"HTTP {r.status_code}")
        out, thread = grant_in_background(client, ch, keys)
        first = await_pend(client)
        check("a stranger is asked about, because she has never met it",
              first is not None and first["tier"] == "tier1")
        if first:
            decide(client, first["family"], "approved")
        thread.join(timeout=90)
        check("and the grant completes once she says yes", bool(out.get("rpt")),
              str(out.get("error")))

        # Now the agent is standing, and the rule is the only thing left that
        # could ask. A reversible operation does not trip it.
        r, ch = challenge_for(client, "get_positions")
        rpt = run_grant(client, ch.as_uri, ch.ticket, keys, lambda t: True,
                        max_wait_s=30)
        check("a standing agent reading her holdings is not asked about again,"
              " because that operation can be undone", bool(rpt))
        check("and nothing is waiting on her", pending(client) == [])

        # The same rule, the same agent, an operation the resource declares
        # cannot be undone. Her trade tier no longer asks about everything.
        args = {"symbol": "VTI", "side": "buy", "quantity": 5}
        r, ch = challenge_for(client, "execute_trade", args)
        rem = remediation_of(r.headers.get("www-authenticate", ""))
        detail = (rem.get("authorization_details") or [{}])[0]
        check("the challenge tells the agent what the act would leave behind, "
              "before it negotiates for it",
              detail.get("consequence") == "irreversible", json.dumps(detail))

        out, thread = grant_in_background(
            client, ch, keys,
            operation={"tool": "execute_trade", "params": args})
        pend = await_pend(client)
        check("she is asked about the trade", pend is not None)
        because = (pend or {}).get("because") or []
        check("and the reason she is being asked is the class, not the tool",
              any("consequence" in str(b) for b in because), json.dumps(because))
        say(f"because: {json.dumps(because)}")
        if pend:
            decide(client, pend["family"], "approved")
        thread.join(timeout=120)
        rpt = out.get("rpt")
        check("the grant arrives after she answers", bool(rpt),
              str(out.get("error")))

        if rpt:
            hdrs = signed_headers("POST", GATEWAY_AUTHORITY, MCP_PATH, rpt, keys)
            resp = mcp_call(client, GATEWAY, "tools/call",
                            {"name": "execute_trade", "arguments": args}, META,
                            headers=hdrs)
            body = mcp_json(resp)
            check("and the call she approved goes through",
                  resp.status_code == 200 and "error" not in body,
                  json.dumps(body)[:200])

        # Both stores flatten `entry` into the row and return it oldest
        # first, so these are matched by negotiation rather than by position.
        rows = ledger(client)

        def promised_for(family: str) -> dict:
            hit = [e for e in rows if e.get("kind") == "promised"
                   and e.get("family") == family]
            return hit[-1] if hit else {}

        trade_row = promised_for((pend or {}).get("family"))
        check("her record of what was promised says what was at stake",
              trade_row.get("consequence") == "irreversible",
              json.dumps(trade_row)[:200])
        read_row = promised_for((first or {}).get("family"))
        check("and the record of the read says what that was, which is not "
              "the same thing",
              read_row.get("consequence") == "reversible",
              json.dumps(read_row)[:200])
    finally:
        # Her policy is not this check's to leave edited.
        for tier_id, tier in original.items():
            put_tier(client, tier_id, {"ask_me": tier.get("ask_me", False),
                                       "rules": tier.get("rules") or []})
        if original:
            say("her tiers are back as they were")
        for p in pending(client):
            decide(client, p["family"], "denied")

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
