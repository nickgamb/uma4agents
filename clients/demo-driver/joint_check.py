"""Joint ownership: one resource, two owners, neither of them above the other.

The organization demo answers "some of this stuff is the firm's". This
answers a different question, and it is the one with no mechanism anywhere:
what if a resource has *two* owners of equal standing, and neither can decide
alone.

The arrangement. Meridian holds an account jointly for Alice and Carol. Each
of them administers it through her own authorization server, under her own
terms, exactly as she administers her own brokerage account — and there is no
party above them. What decides is a **mandate**: who is entitled to be
counted, at what weight, and how many it takes. What does the counting is a
**tally**, which owns nothing, holds no policy, and is not trusted.

What can only be seen from out here, across six processes:

  * **one document, everybody's terms.** The agent signs one folded
    agreement: the shortest expiry either holder set, only the scopes both
    offer, every prohibition either wrote;
  * **each holder re-checks the fold.** A tally that quietly widened the
    terms is caught by the holders' own authorities, not by anybody trusting
    it;
  * **the tally cannot manufacture a yes.** The grant carries the holders'
    signed verdicts and the enforcement point re-runs the count against their
    published keys. A grant with a forged verdict inside it dies at the door;
  * **one refusal is enough**, under a mandate that needs everybody — and
    nobody waits for the rest once the outcome cannot change;
  * **either is enough** under a mandate that says so, with the same code;
  * **being a co-owner of one account gives neither of them anything
    anywhere else.**

Run with `make joint-check`.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, "/driver/lib")
from uma4a_grant import (  # noqa: E402
    AgentKeys, GrantDenied, mcp_call, mcp_json, mcp_meta, parse_challenge,
    run_grant, signed_headers,
)

GATEWAY = os.environ.get("UMA4A_GATEWAY", "https://gateway.uma.lab/mcp")
KEYCLOAK = os.environ.get("UMA4A_OIDC", "https://keycloak.uma.lab")
TALLY = os.environ.get("UMA4A_TALLY", "https://joint-tally.uma.lab")
BOTH = os.environ.get("UMA4A_JOINT_ACCOUNT", "meridian-joint")
EITHER = os.environ.get("UMA4A_EITHER_ACCOUNT", "meridian-either")
VERIFY = os.environ.get("UMA4A_CA_BUNDLE", "/driver/rootCA.pem")
ORG = os.environ.get("UMA4A_ORG", "https://northwind-org.uma.lab")
ORG_ADMIN = {"Authorization":
             f"Bearer {os.environ.get('ORG_ADMIN_TOKEN', 'org-admin-dev-token')}"}
ORG_CODE = os.environ.get("ORG_JOIN_CODE", "NW-7K2F-QX")
META = mcp_meta("joint-check")

OWNERS = {
    "alice": {"as": os.environ.get("UMA4A_AS", "https://alice-as.uma.lab"),
              "realm": "alice", "password": "alice-demo"},
    "carol": {"as": os.environ.get("UMA4A_CAROL_AS", "https://carol-as.uma.lab"),
              "realm": "carol", "password": "carol-demo"},
}

PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"   {'ok  ' if ok else 'FAIL'} {name}"
          + (f" — {detail}" if detail and not ok else ""), flush=True)


def hdrs(c: httpx.Client, owner: str) -> dict:
    o = OWNERS[owner]
    r = c.post(f"{KEYCLOAK}/realms/{o['realm']}/protocol/openid-connect/token",
               data={"grant_type": "password", "client_id": "meridian-portal",
                     "username": owner, "password": o["password"]}, timeout=15.0)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def ensure_resource_server(c: httpx.Client, owner: str) -> None:
    """Make sure this owner's authority has met the gateway.

    A resource has to be registered at her authority before she can write a
    word of terms over it, and registration is something the resource server
    initiates when an agent turns up. In a lab whose authorities can be
    restarted between runs that is not a given, so it is made one.
    """
    o = OWNERS[owner]
    own = "" if owner == "alice" else f"/{owner}"
    for _ in range(8):
        registry = {r["client_id"]: r for r in c.get(
            f"{o['as']}/owner/resource-servers", headers=hdrs(c, owner),
            timeout=15.0).json()}
        if any(r.get("status") == "active" for r in registry.values()):
            return
        pending = [cid for cid, r in registry.items() if r.get("status") == "pending"]
        for cid in pending:
            c.post(f"{o['as']}/owner/resource-servers/decision",
                   json={"client_id": cid, "decision": "approved"},
                   headers=hdrs(c, owner), timeout=15.0)
        if not pending:
            mcp_call(c, f"{GATEWAY}{own}", "tools/call",
                     {"name": "get_positions", "arguments": {}}, META)
            time.sleep(1.0)


def join(c: httpx.Client, owner: str, account: str, agreed: bool = True):
    return c.post(f"{OWNERS[owner]['as']}/owner/joint",
                  json={"tally": TALLY, "account": account, "agreed": agreed},
                  headers=hdrs(c, owner), timeout=20.0)


def leave(c: httpx.Client, owner: str, account: str) -> None:
    c.request("DELETE", f"{OWNERS[owner]['as']}/owner/joint/{account}",
              headers=hdrs(c, owner), timeout=15.0)


def write_terms(c: httpx.Client, owner: str, account: str, *, expires: int,
                scope: list, prohibited: list, ask_me: bool = False):
    """Her own terms over the joint account, in her own authority."""
    tier = f"{account.replace('-', '')}{owner}"
    c.request("DELETE", f"{OWNERS[owner]['as']}/owner/policies/{tier}",
              headers=hdrs(c, owner), timeout=15.0)
    return c.post(f"{OWNERS[owner]['as']}/owner/policies", json={
        "id": tier, "name": f"{owner.title()}'s terms for {account}",
        "resources": [f"{account}/get_positions", f"{account}/get_transactions"],
        "ask_me": ask_me,
        "terms": {"expires_in": expires, "scope": scope,
                  "prohibited": prohibited,
                  "purpose": f"Access to {account}"},
    }, headers=hdrs(c, owner), timeout=15.0)


def drop_terms(c: httpx.Client, owner: str, account: str) -> None:
    tier = f"{account.replace('-', '')}{owner}"
    c.request("DELETE", f"{OWNERS[owner]['as']}/owner/policies/{tier}",
              headers=hdrs(c, owner), timeout=15.0)


def answer_pending(c: httpx.Client, owner: str, decision: str) -> int:
    """Answer everything waiting on this holder, as her."""
    n = 0
    for p in c.get(f"{OWNERS[owner]['as']}/owner/pending",
                   headers=hdrs(c, owner), timeout=15.0).json():
        c.post(f"{OWNERS[owner]['as']}/owner/pending/{p['family']}/decision",
               json={"decision": decision}, headers=hdrs(c, owner), timeout=15.0)
        n += 1
    return n


def negotiate(c: httpx.Client, account: str, keys: AgentKeys,
              tool: str = "get_positions", answers: dict | None = None,
              reason: str | None = "Reviewing the joint account",
              capture: dict | None = None):
    """The ordinary four beats, at a jointly held account.

    Nothing about the agent's side of this is joint-aware: same challenge,
    same `need_info`, same signed agreement, same polling while somebody is
    asked. It never learns that the authority it negotiated with owns
    nothing.
    """
    url = f"{GATEWAY}/joint/{account}"
    r = mcp_call(c, url, "tools/call", {"name": tool, "arguments": {}}, META)
    ch = parse_challenge(r.headers.get("www-authenticate", ""))
    if ch is None:
        return None, f"no challenge: {r.status_code} {r.text[:150]}"
    done = {"v": False}

    def be_them(msg: str) -> None:
        if "has been asked" not in msg or done["v"] or not answers:
            return
        done["v"] = True
        for owner, decision in answers.items():
            answer_pending(c, owner, decision)

    def accept(template: dict) -> bool:
        if capture is not None:
            capture.update(template)
        return True

    try:
        return run_grant(c, ch.as_uri, ch.ticket, keys, accept, reason=reason,
                         on_status=be_them, max_wait_s=60), ""
    except GrantDenied as exc:
        return None, str(exc)[:240]


def spend(c: httpx.Client, account: str, keys: AgentKeys, rpt: str) -> list:
    path = f"/mcp/joint/{account}"
    r = mcp_call(c, f"{GATEWAY}/joint/{account}", "tools/call",
                 {"name": "get_positions", "arguments": {}}, META,
                 headers=signed_headers("POST", "gateway.uma.lab", path, rpt, keys))
    try:
        return sorted(p["symbol"] for p in json.loads(
            mcp_json(r)["result"]["content"][0]["text"])["positions"])
    except (KeyError, IndexError, ValueError, TypeError):
        return []


def main() -> int:                                            # noqa: C901
    with httpx.Client(verify=VERIFY, timeout=30.0) as c:
        print("\n-- 1. the mandate is published, and says what it takes --")
        doc = c.get(f"{TALLY}/mandate/{BOTH}", timeout=15.0).json()
        check("the tally publishes who is entitled to be counted",
              {h["owner"] for h in doc["holders"]} == {"alice", "carol"},
              f"{doc.get('holders')}")
        check("and how many of them it takes",
              doc["rule"]["threshold"] == 2 and doc["rule"]["kind"] == "all",
              f"{doc.get('rule')}")
        check("in sentences a holder is shown before she agrees",
              any("Any one of you can stop it" in s for s in doc["summary"]),
              f"{doc.get('summary')}")
        check("the tally says it is not an ordinary authority",
              c.get(f"{TALLY}/.well-known/uma4agents-configuration",
                    timeout=15.0).json().get("u4a_tally") is True)

        print("\n-- 2. joining is agreed to, and nobody is enrolled by naming her --")
        for owner in ("alice", "carol"):
            ensure_resource_server(c, owner)
        r = join(c, "alice", BOTH, agreed=False)
        check("joining without agreeing is refused", r.status_code == 400,
              f"{r.status_code} {r.text[:140]}")
        for owner in ("alice", "carol"):
            r = join(c, owner, BOTH)
            check(f"{owner} agrees to the mandate", r.status_code == 200,
                  f"{r.status_code} {r.text[:160]}")
            join(c, owner, EITHER)

        print("\n-- 3. one document, and it is everybody's terms at once --")
        # Deliberately different. Alice is the looser of the two on every
        # field, so every narrowing in the folded document came from Carol —
        # which is what makes it visible that the fold is an intersection and
        # not a copy of whoever was asked first.
        wa = write_terms(c, "alice", BOTH, expires=3600,
                         scope=["positions:read", "transactions:read"],
                         prohibited=["model-training"])
        wc = write_terms(c, "carol", BOTH, expires=900,
                         scope=["positions:read"],
                         prohibited=["resale-to-third-parties"])
        check("each holder writes her own terms, at her own authority",
              wa.status_code == 200 and wc.status_code == 200,
              f"alice {wa.status_code} {wa.text[:90]} / "
              f"carol {wc.status_code} {wc.text[:90]}")
        time.sleep(1.0)
        hers = AgentKeys(keyid="joint-1")
        seen: dict = {}
        rpt, why = negotiate(c, BOTH, hers, answers={"alice": "approved",
                                                     "carol": "approved"},
                             capture=seen)
        check("the agent is offered one folded document", bool(seen), f"{why}")
        check("with the shortest expiry either holder set",
              seen.get("expires_in") == 900, f"{seen.get('expires_in')}")
        check("only the scopes both of them offer",
              seen.get("scope") == ["positions:read"], f"{seen.get('scope')}")
        check("and every prohibition either of them wrote",
              {"model-training", "resale-to-third-parties"}
              <= set(seen.get("prohibited") or []), f"{seen.get('prohibited')}")
        check("the document says who is behind it and what it takes",
              (seen.get("joint") or {}).get("threshold") == 2
              and sorted((seen.get("joint") or {}).get("holders") or [])
              == ["alice", "carol"], f"{seen.get('joint')}")
        check("both holders allowed, so the grant issues", rpt is not None, why)
        check("and it works", spend(c, BOTH, hers, rpt) if rpt else [],
              "nothing came back")

        print("\n-- 4. the grant carries the evidence it rests on --")
        claims = jwt.decode(rpt, options={"verify_signature": False}) if rpt else {}
        joint = claims.get("joint") or {}
        check("the grant names the mandate it was issued under",
              sorted(h["owner"] for h in (joint.get("mandate") or {})
                     .get("holders") or []) == ["alice", "carol"])
        check("and carries a signed verdict from each holder",
              len(joint.get("verdicts") or []) == 2,
              f"{len(joint.get('verdicts') or [])}")
        holders = sorted(jwt.decode(v, options={"verify_signature": False})["holder"]
                         for v in joint.get("verdicts") or [])
        check("each signed by that holder's own authority, not the tally's",
              holders == ["alice", "carol"] and all(
                  jwt.decode(v, options={"verify_signature": False})["iss"]
                  != TALLY for v in joint["verdicts"]), f"{holders}")

        print("\n-- 5. a tally that manufactures a yes is caught at the door --")
        # The same grant with one holder's verdict replaced by one this
        # script signed itself. Nothing about it is malformed; it is simply
        # not signed by the authority the mandate names.
        forger = Ed25519PrivateKey.generate()
        joint.setdefault("verdicts", [""])
        forged = jwt.encode(
            {"iss": OWNERS["carol"]["as"], "holder": "carol",
             "negotiation": claims.get("jti"),
             "resource_id": f"{BOTH}/get_positions",
             "contract": claims.get("contract"), "effect": "allow",
             "exp": int(time.time()) + 300},
            forger, algorithm="EdDSA")
        tampered = dict(claims)
        tampered["joint"] = {**joint, "verdicts": [joint["verdicts"][0], forged]}
        bad = jwt.encode(tampered, forger, algorithm="EdDSA",
                         headers={"typ": "aa-auth+jwt"})
        r = mcp_call(c, f"{GATEWAY}/joint/{BOTH}", "tools/call",
                     {"name": "get_positions", "arguments": {}}, META,
                     headers=signed_headers("POST", "gateway.uma.lab",
                                            f"/mcp/joint/{BOTH}", bad, hers))
        check("a grant nobody's authority signed is refused",
              r.status_code in (401, 403), f"{r.status_code} {r.text[:160]}")

        # And the subtler forgery: every verdict genuine, but the electorate
        # rewritten. A tally that shipped one real verdict beside a mandate
        # saying one is enough would pass any check that counted against the
        # copy inside the token — so the enforcement point counts against the
        # mandate the tally *publishes*, which is the one the holders saw.
        lowered = dict(claims)
        lowered["joint"] = {**joint,
                            "mandate": {**(joint.get("mandate") or {}),
                                        "holders": [h for h in
                                                    (joint.get("mandate") or {}).get("holders") or []
                                                    if h["owner"] == "alice"],
                                        "rule": {"kind": "all", "threshold": 1}},
                            "verdicts": [joint["verdicts"][0]]}
        cooked = jwt.encode(lowered, forger, algorithm="EdDSA",
                            headers={"typ": "aa-auth+jwt"})
        r = mcp_call(c, f"{GATEWAY}/joint/{BOTH}", "tools/call",
                     {"name": "get_positions", "arguments": {}}, META,
                     headers=signed_headers("POST", "gateway.uma.lab",
                                            f"/mcp/joint/{BOTH}", cooked, hers))
        check("nor one that rewrites who was entitled to be counted",
              r.status_code in (401, 403), f"{r.status_code} {r.text[:160]}")

        print("\n-- 6. one refusal is enough, and nobody waits for the rest --")
        other = AgentKeys(keyid="joint-2")
        rpt2, why2 = negotiate(c, BOTH, other,
                               answers={"alice": "approved", "carol": "denied"})
        check("a holder who declines stops the request", rpt2 is None, f"{rpt2}")
        check("and the agent is told, rather than left polling",
              "declined" in why2 or "did not agree" in why2, f"{why2}")

        print("\n-- 7. silence is not consent --")
        drop_terms(c, "carol", BOTH)
        time.sleep(1.0)
        quiet = AgentKeys(keyid="joint-3")
        rpt3, why3 = negotiate(c, BOTH, quiet,
                               answers={"alice": "approved", "carol": "approved"})
        check("a holder who has written no terms cannot be counted",
              rpt3 is None, f"{rpt3}")
        write_terms(c, "carol", BOTH, expires=900, scope=["positions:read"],
                    prohibited=["resale-to-third-parties"])

        print("\n-- 8. either, when the mandate says either --")
        for owner in ("alice", "carol"):
            write_terms(c, owner, EITHER, expires=1800,
                        scope=["positions:read"], prohibited=["model-training"])
        time.sleep(1.0)
        solo = AgentKeys(keyid="joint-4")
        rpt4, why4 = negotiate(c, EITHER, solo,
                               answers={"alice": "approved", "carol": "denied"})
        check("one holder's refusal does not stop what either may release",
              rpt4 is not None, f"{why4}")
        left = jwt.decode(rpt4, options={"verify_signature": False}) if rpt4 else {}
        check("and the grant rests on the holder who did allow it",
              len((left.get("joint") or {}).get("verdicts") or []) == 1,
              f"{(left.get('joint') or {}).get('verdicts')}")

        print("\n-- 9. holding one account together is not standing anywhere else --")
        r = c.get(f"{OWNERS['alice']['as']}/owner/pending",
                  headers=hdrs(c, "carol"), timeout=15.0)
        check("a holder cannot read her co-owner's queue",
              r.status_code in (401, 403), f"{r.status_code}")
        mine = c.get(f"{OWNERS['alice']['as']}/owner/joint",
                     headers=hdrs(c, "alice"), timeout=15.0).json()
        check("her own view names the accounts and who holds them",
              {m["account"] for m in mine} >= {BOTH, EITHER}
              and all({"alice", "carol"} == {h["owner"] for h in m["holders"]}
                      for m in mine if m["account"] in (BOTH, EITHER)),
              f"{[m['account'] for m in mine]}")
        check("and carries none of her co-owner's terms",
              all("expires_in" not in json.dumps(m) for m in mine),
              "a holder's terms leaked into another holder's view")

        print("\n-- 10. no organization reaches what she holds with somebody else --")
        # The charter here names the joint namespace outright, which is legal:
        # a claim has to be a concrete namespace, and this is one. What stops
        # it is not the charter's shape but her own authority — Carol never
        # enrolled with this organization, was never shown its charter, and
        # cannot leave it, so Alice cannot enrol a resource that is half his.
        base = c.get(f"{ORG}/admin/charter", headers=ORG_ADMIN,
                     timeout=15.0).json()["charter"]
        greedy = {**base, "claims": list(base["claims"]) + [f"{BOTH}/*"]}
        r = c.put(f"{ORG}/admin/charter", json=greedy, headers=ORG_ADMIN,
                  timeout=20.0)
        check("a charter may claim a namespace it does not own",
              r.status_code == 200, f"{r.status_code} {r.text[:140]}")
        r = c.put(f"{ORG}/admin/charter",
                  json={**base, "claims": ["*/get_positions"]},
                  headers=ORG_ADMIN, timeout=20.0)
        check("but not one written as a wildcard, which would reach anybody's",
              r.status_code == 400 and "namespace" in r.text,
              f"{r.status_code} {r.text[:140]}")
        alice = OWNERS["alice"]["as"]
        c.post(f"{alice}/owner/organization",
               json={"code": ORG_CODE, "agreed": True},
               headers=hdrs(c, "alice"), timeout=20.0)
        time.sleep(1.0)

        # Her terms over the joint account, well above the charter's ceiling.
        drop_terms(c, "alice", BOTH)
        w = write_terms(c, "alice", BOTH, expires=86400,
                        scope=["positions:read"], prohibited=["model-training"])
        stored = c.get(f"{alice}/owner/policies", headers=hdrs(c, "alice"),
                       timeout=15.0).json().get(f"{BOTH.replace('-', '')}alice", {})
        check("its ceiling does not clamp terms over the joint account",
              (stored.get("terms") or {}).get("expires_in") == 86400,
              f"{w.status_code} {(stored.get('terms') or {}).get('expires_in')}")

        # And a request waiting on her about it is none of its business.
        write_terms(c, "carol", BOTH, expires=900, scope=["positions:read"],
                    prohibited=["resale-to-third-parties"], ask_me=True)
        drop_terms(c, "alice", BOTH)
        write_terms(c, "alice", BOTH, expires=86400, scope=["positions:read"],
                    prohibited=["model-training"], ask_me=True)
        time.sleep(1.0)
        waiting = AgentKeys(keyid="joint-6")
        held = threading.Thread(target=negotiate, args=(c, BOTH, waiting),
                                kwargs={"answers": None})
        held.start()
        time.sleep(7.0)
        mine = c.get(f"{alice}/owner/pending", headers=hdrs(c, "alice"),
                     timeout=15.0).json()
        check("it is waiting on her",
              any((p.get("resource_id") or "").startswith(f"{BOTH}/") for p in mine),
              f"{[p.get('resource_id') for p in mine]}")
        raw = c.get(f"{ORG}/admin/members/alice/pending", headers=ORG_ADMIN,
                    timeout=15.0)
        theirs = raw.json() if raw.status_code == 200 else []
        check("and the organization cannot see it",
              isinstance(theirs, list) and not any(
                  (p.get("resource_id") or "").startswith(f"{BOTH}/")
                  for p in theirs),
              f"{raw.status_code} {raw.text[:180]}")
        family = next((p["family"] for p in mine
                       if (p.get("resource_id") or "").startswith(f"{BOTH}/")), None)
        d = c.post(f"{ORG}/admin/members/alice/pending/{family}/decision",
                   json={"decision": "approved"}, headers=ORG_ADMIN, timeout=15.0)
        check("nor answer it", d.status_code == 403,
              f"{d.status_code} {d.text[:140]}")
        answer_pending(c, "alice", "denied")
        answer_pending(c, "carol", "denied")
        held.join()

        # And she cannot put it in a tier with anything else, which would be
        # the way round all of the above.
        drop_terms(c, "alice", BOTH)
        r = c.post(f"{alice}/owner/policies", json={
            "id": "mixedtier", "name": "mixed", "ask_me": False,
            "resources": [f"{BOTH}/get_positions", "alice-vault/get_positions"],
            "terms": {"expires_in": 900, "scope": ["positions:read"],
                      "prohibited": [], "purpose": "mixed"},
        }, headers=hdrs(c, "alice"), timeout=15.0)
        check("a tier cannot mix it with anything else",
              r.status_code == 400 and "held jointly" in r.text,
              f"{r.status_code} {r.text[:160]}")
        c.put(f"{ORG}/admin/charter", json=base, headers=ORG_ADMIN, timeout=20.0)
        c.request("DELETE", f"{alice}/owner/organization",
                  headers=hdrs(c, "alice"), timeout=15.0)

        print("\n-- 11. leaving --")
        leave(c, "carol", BOTH)
        gone = AgentKeys(keyid="joint-5")
        rpt5, why5 = negotiate(c, BOTH, gone, answers={"alice": "approved"})
        check("a holder who has left is not asked, and cannot be counted",
              rpt5 is None, f"{rpt5}")
        check("her own terms survive leaving",
              f"{BOTH.replace('-', '')}carol" in
              c.get(f"{OWNERS['carol']['as']}/owner/policies",
                    headers=hdrs(c, "carol"), timeout=15.0).json())

        # Leave the lab as it was found.
        for owner in ("alice", "carol"):
            for account in (BOTH, EITHER):
                leave(c, owner, account)
                drop_terms(c, owner, account)

    print()
    print(f"{len(PASS)} passed, {len(FAIL)} failed", flush=True)
    if FAIL:
        for f in FAIL:
            print(f"  - {f}")
        return 1
    print("\nPASS: one resource, two owners, neither above the other. The terms")
    print("      an agent signed were both of theirs at once, the count was run")
    print("      again at the door from signatures the counting party could not")
    print("      forge, and either of them could stop it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
