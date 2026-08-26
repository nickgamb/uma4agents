"""The whole negotiation, against a real Okta tenant.

Not a check — a single run of the thing the lab does with its own provider,
with the provider swapped for somebody else's implementation. What it proves
is the only thing the lab's own provider cannot: that nothing here depends on
the provider having been written alongside it.

Needs a refresh token from a real sign-in, which is the one part of Cross App
Access nobody can automate away — the subject token is an employee having
authenticated.
"""
from __future__ import annotations

import json
import os
import sys

import httpx

sys.path.insert(0, "/driver/lib")
from uma4a_grant import (  # noqa: E402
    AgentKeys, Enterprise, GrantDenied, mcp_call, mcp_json, mcp_meta,
    parse_challenge, run_grant, signed_headers,
)

GATEWAY = os.environ.get("UMA4A_GATEWAY", "https://gateway.uma.lab/mcp")
KEYCLOAK = os.environ.get("UMA4A_OIDC", "https://keycloak.uma.lab")
ORG = os.environ.get("UMA4A_ORG", "https://northwind-org.uma.lab")
AS = os.environ.get("UMA4A_AS", "https://alice-as.uma.lab")
ADMIN = {"Authorization": f"Bearer {os.environ.get('ORG_ADMIN_TOKEN', 'org-admin-dev-token')}"}
CA = os.environ.get("UMA4A_CACERT", "/driver/rootCA.pem")
OPERATOR = os.environ.get("UMA4A_ALICE_OPERATOR", "https://alice-agent.uma.lab")
BOOK, BOOK_PATH = "northwind-vault", "/shared/alice"
META = mcp_meta("u4a-okta-live")

OKTA = os.environ["OKTA_ORG"]
OKTA_CLIENT = os.environ["OKTA_CLIENT_ID"]
OKTA_SECRET = os.environ["OKTA_CLIENT_SECRET"]
OKTA_REFRESH = os.environ["OKTA_REFRESH_TOKEN"]
OKTA_SUBJECT = os.environ["OKTA_SUBJECT"]      # what the tenant asserts
MEMBER = "alice"                               # who that is here

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"   {'ok  ' if ok else 'FAIL'} {name}" + (f" — {detail}" if detail and not ok else ""),
          flush=True)


def portal(c):
    r = c.post(f"{KEYCLOAK}/realms/alice/protocol/openid-connect/token",
               data={"grant_type": "password", "client_id": "meridian-portal",
                     "username": "alice",
                     "password": os.environ.get("ALICE_PASSWORD", "alice-demo")},
               timeout=15.0)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def main() -> int:
    c = httpx.Client(verify=CA, timeout=45.0)
    alice = portal(c)

    print(f"\n1. point Northwind's charter at {OKTA}")
    base = c.get(f"{ORG}/admin/charter/versions/1", headers=ADMIN, timeout=15.0
                 ).json()["charter"]
    charter = {**base, "identity_provider": {
        "enabled": True, "issuer": OKTA, "assertion": "id-jag",
        "directory": "", "enrol": False,
        # The tenant asserts an identifier of its own; the organization says
        # who that is here.
        "subject_map": {OKTA_SUBJECT: MEMBER},
    }}
    r = c.put(f"{ORG}/admin/charter", json=charter, headers=ADMIN, timeout=20.0)
    check("the charter federates to the tenant", r.status_code == 200,
          f"{r.status_code} {r.text[:160]}")

    print("\n2. she is a member, and the book is hers to administer")
    if not c.get(f"{AS}/owner/organization", headers=alice, timeout=15.0
                 ).json().get("enrolled"):
        c.post(f"{AS}/owner/organization", headers=alice, timeout=20.0,
               json={"code": os.environ.get("ORG_JOIN_CODE", "NW-7K2F-QX"),
                     "agreed": True})
    check("enrolled", c.get(f"{AS}/owner/organization", headers=alice,
                            timeout=15.0).json().get("enrolled"))
    c.post(f"{AS}/owner/operators/claim", json={"origin": OPERATOR},
           headers=alice, timeout=15.0)
    c.post(f"{AS}/owner/policies", headers=alice, timeout=15.0,
           json={"id": "firmbook", "name": "Northwind book", "ask_me": False,
                 "resources": [f"{BOOK}/get_positions", f"{BOOK}/get_transactions"],
                 "terms": {"purpose": "Desk research on the firm book",
                           "expires_in": 600,
                           "scope": ["positions:read", "transactions:read"],
                           "prohibited": ["client-benchmarking"]}})
    check("her terms over the book are written",
          "firmbook" in c.get(f"{AS}/owner/policies", headers=alice,
                              timeout=15.0).json())

    print("\n3. the whole negotiation, end to end")
    keys = AgentKeys()
    keys.keyid = f"okta-live-{os.getpid()}"
    keys.client_id = f"{OPERATOR}/agent.json"
    keys.signature_agent = keys.publish(c, OPERATOR)
    ent = Enterprise(subject_token=OKTA_REFRESH, client_id=OKTA_CLIENT,
                     client_secret=OKTA_SECRET,
                     subject_token_type="urn:ietf:params:oauth:token-type:refresh_token")

    r = mcp_call(c, f"{GATEWAY}{BOOK_PATH}", "tools/call",
                 {"name": "get_positions", "arguments": {}}, META)
    ch = parse_challenge(r.headers.get("www-authenticate", ""))
    check("the resource refuses and names her authority",
          ch is not None and "alice-as" in (ch.as_uri if ch else ""),
          f"{r.status_code} {r.text[:140]}")
    if ch is None:
        return 1

    said, answered = [], {"v": False}

    def watch(msg):
        """Alice, answering. The organization's own rules can require she be
        asked even where her tier does not, so the run has to be able to
        answer as her — the point here is the protocol, not her being away."""
        said.append(msg)
        if "has been asked" not in msg or answered["v"]:
            return
        answered["v"] = True
        for p in c.get(f"{AS}/owner/pending", headers=alice, timeout=15.0).json():
            c.post(f"{AS}/owner/pending/{p['family']}/decision",
                   json={"decision": "approved"}, headers=alice, timeout=15.0)

    try:
        rpt = run_grant(c, ch.as_uri, ch.ticket, keys, lambda t: True,
                        reason="Desk research", on_status=watch,
                        max_wait_s=90, enterprise=ent)
    except GrantDenied as exc:
        check("the grant is issued", False, str(exc)[:240])
        print("\n   what happened:")
        for m in said:
            print("     ·", m)
        return 1

    check("the agent was sent to the tenant, not configured with it",
          any(OKTA in m for m in said), str(said)[:200])
    check("identity was settled before terms",
          next((i for i, m in enumerate(said) if "identity required" in m), 99)
          < next((i for i, m in enumerate(said) if "terms proffered" in m), 99),
          str(said)[:240])
    check("the grant is issued", bool(rpt))

    r = mcp_call(c, f"{GATEWAY}{BOOK_PATH}", "tools/call",
                 {"name": "get_positions", "arguments": {}}, META,
                 headers=signed_headers("POST", "gateway.uma.lab",
                                        f"/mcp{BOOK_PATH}", rpt, keys))
    try:
        got = sorted(p["symbol"] for p in json.loads(
            mcp_json(r)["result"]["content"][0]["text"])["positions"])
    except (KeyError, IndexError, ValueError, TypeError):
        got = []
    check("and it spends at the resource", bool(got), f"{r.status_code}")
    if got:
        print(f"        {', '.join(got)}")

    print("\n4. put the charter back")
    c.put(f"{ORG}/admin/charter", json=base, headers=ADMIN, timeout=20.0)

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print("   FAIL", f)
    if not FAIL:
        print("\nPASS: an agent negotiated with an authority that is not Okta's,\n"
              "      for a resource Okta does not own, on terms Okta never saw —\n"
              "      and Okta's assertion was what got it through the door.")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
