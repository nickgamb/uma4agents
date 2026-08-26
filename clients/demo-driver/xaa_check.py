"""Cross App Access beside UMA: an enterprise says who, an owner says what.

Two protocols meet here, and the point of the check is that they do not
overlap. Northwind runs an identity provider. Alice runs an authorization
server. Each answers a question the other cannot, and a single request needs
both answers.

    Cross App Access (ID-JAG)   which employee is this agent acting for,
                                and did an administrator approve this
                                application reaching that resource at all

    UMA / this profile          and therefore what may it do to the
                                resource, on whose terms, for how long,
                                and at what depth of delegation

What can only be seen from out here:

  * **the resource side starts it.** The agent knows nothing about Northwind
    when it begins. It calls the tool, is refused, is told which provider to
    go to and what to ask for, and only then goes. Nobody pushed an assertion
    at it and nothing was pre-arranged with it;
  * **two questions, two beats.** The server asks who the agent acts for
    before it will say anything about terms — because which terms apply
    follows from which member it is. Ordinary UMA claims-gathering, one claim
    per beat;
  * **three ceilings, one for each party.** The provider's connection scope,
    the charter's grants, and her terms. Each is set by a different party and
    none of them can widen another;
  * **an assertion is not an entitlement.** A perfectly good ID-JAG still
    negotiates for terms, and can still be refused by the owner;
  * **the enterprise half stops at the organization's own resources.** Alice's
    personal account is never governed by it, and neither is anything she
    holds jointly with Carol. No assertion is asked for, and none would help.

Run with `make xaa-check`.
"""

from __future__ import annotations

import json
import os
import sys
import time

import httpx

sys.path.insert(0, "/driver/lib")
from uma4a_grant import (  # noqa: E402
    AgentKeys, Enterprise, GrantDenied, ID_JAG_FORMAT, mcp_call, mcp_json,
    mcp_meta, parse_challenge, run_grant, signed_headers,
)

GATEWAY = os.environ.get("UMA4A_GATEWAY", "https://gateway.uma.lab/mcp")
# Meridian's identity provider. It authenticates people into Meridian's own
# surfaces — her portal, Dana's console — and it is not Northwind's.
KEYCLOAK = os.environ.get("UMA4A_OIDC", "https://keycloak.uma.lab")
# Northwind's, which is a different company's infrastructure. Its employee
# directory, and the issuer the charter federates to.
NORTHWIND_IDP = os.environ.get("UMA4A_NORTHWIND_IDP",
                               "https://northwind-idp.uma.lab/realms/employees")
ORG = os.environ.get("UMA4A_ORG", "https://northwind-org.uma.lab")
XAA = os.environ.get("UMA4A_XAA", "https://northwind-xaa.uma.lab")
AS = os.environ.get("UMA4A_AS", "https://alice-as.uma.lab")
CAROL_AS = os.environ.get("UMA4A_CAROL_AS", "https://carol-as.uma.lab")
ADMIN = {"Authorization": f"Bearer {os.environ.get('ORG_ADMIN_TOKEN', 'org-admin-dev-token')}"}
JOIN_CODE = os.environ.get("ORG_JOIN_CODE", "NW-7K2F-QX")
CA = os.environ.get("UMA4A_CACERT", "/driver/rootCA.pem")
AGENT_CLIENT = "northwind-research-agent"
AGENT_SECRET = os.environ.get("XAA_AGENT_SECRET", "northwind-agent-secret")
# Two operators, because the charter distinguishes them. Her role is
# `first-party-only`, so an agent she runs may act on the firm's book and
# somebody else's may not — whatever the identity provider says about it.
HER_OPERATOR = os.environ.get("UMA4A_ALICE_OPERATOR", "https://alice-agent.uma.lab")
HIS_OPERATOR = os.environ.get("UMA4A_AGENT_OPERATOR", "https://agent.uma.lab")
BOOK = "northwind-vault"
# Where the firm's book is served, for this member. Her own account is the
# bare path — the same gateway, a different resource.
BOOK_PATH = "/shared/alice"
# How long the enforcement point may word a refusal from a cached description
# of the organization. Read from the same variable the service is configured
# with, so a wait here cannot drift into a flaky failure.
ORG_DISCOVERY_TTL = float(os.environ.get("UMA_PEP_ORG_DISCOVERY_TTL_S", "15")) + 2
META = mcp_meta("u4a-xaa-check")

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"   {'ok  ' if ok else 'FAIL'} {name}"
          + (f" — {detail}" if detail and not ok else ""), flush=True)


def portal(c: httpx.Client, owner: str, realm: str, password: str) -> dict:
    r = c.post(f"{KEYCLOAK}/realms/{realm}/protocol/openid-connect/token",
               data={"grant_type": "password", "client_id": "meridian-portal",
                     "username": owner, "password": password}, timeout=15.0)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def employee_id_token(c: httpx.Client, who: str) -> str:
    """An employee signing into the application, at Northwind's own provider."""
    r = c.post(f"{NORTHWIND_IDP}/protocol/openid-connect/token",
               data={"grant_type": "password", "client_id": AGENT_CLIENT,
                     "username": who, "password": f"{who}-northwind",
                     "scope": "openid"}, timeout=15.0)
    r.raise_for_status()
    return r.json()["id_token"]


def meridian_token(c: httpx.Client, who: str, realm: str, password: str,
                   client: str = "meridian-org-console") -> str:
    """Somebody signing into a *Meridian* surface. A different company."""
    r = c.post(f"{KEYCLOAK}/realms/{realm}/protocol/openid-connect/token",
               data={"grant_type": "password", "client_id": client,
                     "username": who, "password": password, "scope": "openid"},
               timeout=15.0)
    r.raise_for_status()
    return r.json()["id_token"]


def leave_org(c: httpx.Client, hdrs: dict) -> None:
    if c.get(f"{AS}/owner/organization", headers=hdrs, timeout=15.0
             ).json().get("enrolled"):
        c.request("DELETE", f"{AS}/owner/organization", headers=hdrs, timeout=15.0)


def federated(base: dict, **over) -> dict:
    doc = {**base, "identity_provider": {"enabled": True, "issuer": XAA,
                                         "assertion": "id-jag", "directory": "",
                                         "enrol": True, "jit_invite": True}}
    doc["identity_provider"].update(over)
    return doc


def exchange(c: httpx.Client, subject: str, audience: str, scope: str,
             resource: str = f"{GATEWAY}") -> httpx.Response:
    return c.post(f"{XAA}/token", timeout=15.0, data={
        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
        "requested_token_type": ID_JAG_FORMAT,
        "subject_token": subject,
        "subject_token_type": "urn:ietf:params:oauth:token-type:id_token",
        "audience": audience, "resource": resource, "scope": scope,
        "client_id": AGENT_CLIENT, "client_secret": AGENT_SECRET})


def negotiate(c: httpx.Client, path: str, keys: AgentKeys,
              enterprise: Enterprise | None, tool: str = "get_positions",
              hdrs: dict | None = None) -> tuple[str | None, str, list[str]]:
    """The ordinary beats at one surface. Returns (rpt, why-not, statuses)."""
    r = mcp_call(c, f"{GATEWAY}{path}", "tools/call",
                 {"name": tool, "arguments": {}}, META)
    ch = parse_challenge(r.headers.get("www-authenticate", ""))
    if ch is None:
        return None, f"no challenge: {r.status_code} {r.text[:120]}", []
    said: list[str] = []

    def approve(msg: str) -> None:
        said.append(msg)
        if "has been asked" not in msg or hdrs is None:
            return
        for p in c.get(f"{ch.as_uri}/owner/pending", headers=hdrs,
                       timeout=15.0).json():
            c.post(f"{ch.as_uri}/owner/pending/{p['family']}/decision",
                   json={"decision": "approved"}, headers=hdrs, timeout=15.0)

    try:
        rpt = run_grant(c, ch.as_uri, ch.ticket, keys, lambda t: True,
                        reason="Desk research", on_status=approve,
                        max_wait_s=60, enterprise=enterprise)
        return rpt, "", said
    except GrantDenied as exc:
        return None, str(exc)[:200], said


def main() -> int:                                            # noqa: C901
    c = httpx.Client(verify=CA, timeout=30.0)
    alice = portal(c, "alice", "alice", os.environ.get("ALICE_PASSWORD", "alice-demo"))

    print("\n1. Northwind federates identity in its charter")
    base = c.get(f"{ORG}/admin/charter/versions/1", headers=ADMIN,
                 timeout=15.0).json()["charter"]
    r = c.put(f"{ORG}/admin/charter", json=federated(base), headers=ADMIN, timeout=20.0)
    check("a charter may name the provider its people are asserted by",
          r.status_code == 200, f"{r.status_code} {r.text[:140]}")
    r = c.put(f"{ORG}/admin/charter",
              json={**base, "identity_provider": {"issuer": "http://xaa.example"}},
              headers=ADMIN, timeout=20.0)
    check("and it has to be an https issuer — it is a trust root",
          r.status_code >= 400, f"accepted {r.status_code}")
    r = c.put(f"{ORG}/admin/charter",
              json={**base, "identity_provider": {"enabled": False, "issuer": ""}},
              headers=ADMIN, timeout=20.0)
    check("switched off with nothing typed in is a charter that never had one",
          r.status_code == 200 and not (c.get(f"{ORG}/.well-known/u4a-organization",
                                              timeout=15.0).json()
                                        .get("identity_provider")),
          f"{r.status_code} {r.text[:120]}")
    c.put(f"{ORG}/admin/charter", json=federated(base), headers=ADMIN, timeout=20.0)

    print("\n1b. the provider is the enterprise's, not Meridian's")
    r = c.post(f"{XAA}/token", timeout=15.0, data={
        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
        "requested_token_type": ID_JAG_FORMAT,
        "subject_token": meridian_token(c, "dana", "northwind", "dana-demo"),
        "subject_token_type": "urn:ietf:params:oauth:token-type:id_token",
        "audience": AS, "resource": GATEWAY, "scope": "get_positions",
        "client_id": AGENT_CLIENT, "client_secret": AGENT_SECRET})
    check("a token from Meridian's own identity provider is not an employee "
          "assertion", r.status_code >= 400, f"accepted {r.status_code}")

    print("\n2. an employee enrols because the provider says she is one")
    leave_org(c, alice)
    r = c.post(f"{AS}/owner/organization", headers=alice, timeout=20.0,
               json={"assertion": employee_id_token(c, "alice"), "agreed": True})
    check("no enrolment code — her employer's directory is the entitlement",
          r.status_code == 200, f"{r.status_code} {r.text[:160]}")
    r2 = c.post(f"{AS}/owner/organization", headers=alice, timeout=20.0,
                json={"assertion": employee_id_token(c, "carol"), "agreed": True})
    check("and one employee's token does not enrol another",
          r2.status_code >= 400, f"accepted {r2.status_code}")
    leave_org(c, alice)
    r3 = c.post(f"{AS}/owner/organization", headers=alice, timeout=20.0,
                json={"assertion": meridian_token(c, "alice", "alice", "alice-demo",
                                                 "meridian-portal"),
                      "agreed": True})
    check("and Meridian's word about who Northwind employs is worth nothing",
          r3.status_code >= 400, f"accepted {r3.status_code}")
    c.post(f"{AS}/owner/organization", headers=alice, timeout=20.0,
           json={"assertion": employee_id_token(c, "alice"), "agreed": True})

    print("\n3. the terms over the firm's book are still hers to write")
    c.post(f"{AS}/owner/policies", headers=alice, timeout=15.0,
           json={"id": "firmbook", "name": "Northwind book", "ask_me": False,
                 "resources": [f"{BOOK}/get_positions", f"{BOOK}/get_transactions"],
                 "terms": {"purpose": "Desk research on the firm book",
                           "expires_in": 600,
                           "scope": ["positions:read", "transactions:read"],
                           "prohibited": ["client-benchmarking"]}})
    tiers = c.get(f"{AS}/owner/policies", headers=alice, timeout=15.0).json()
    check("she writes them; the charter still only narrows",
          "firmbook" in tiers, str(list(tiers))[:120])

    def agent_of(operator: str, name: str) -> AgentKeys:
        k = AgentKeys()
        k.keyid = f"{name}-{int(time.time())}"
        k.client_id = f"{operator}/agent.json"
        k.signature_agent = k.publish(c, operator)
        return k

    # Whose agent is *hers* to say. The identity provider asserts which
    # employee is behind an application; it has no standing to say which
    # operator she runs, and the charter's first-party rule turns on that.
    c.post(f"{AS}/owner/operators/claim", json={"origin": HER_OPERATOR},
           headers=alice, timeout=15.0)
    keys = agent_of(HER_OPERATOR, "hers")

    print("\n4. an agent with no enterprise credentials gets nowhere")
    rpt, why, said = negotiate(c, BOOK_PATH, keys, None, hdrs=alice)
    check("the server asks who it acts for, and it cannot say",
          rpt is None and "enterprise credentials" in why, why or "granted anyway")

    print("\n5. the resource side names the provider; the agent goes and asks")
    ent = Enterprise(subject_token=employee_id_token(c, "alice"),
                     client_id=AGENT_CLIENT, client_secret=AGENT_SECRET)
    rpt, why, said = negotiate(c, BOOK_PATH, keys, ent, hdrs=alice)
    check("an assertion is obtained and the grant is issued", rpt is not None, why)
    check("the agent was told where to go rather than knowing in advance",
          any("exchanging at" in m and XAA in m for m in said), str(said)[:160])
    check("identity was asked for before terms were dictated",
          next((i for i, m in enumerate(said) if "identity required" in m), 99)
          < next((i for i, m in enumerate(said) if "terms proffered" in m), 99),
          str(said)[:200])
    if rpt:
        r = mcp_call(c, f"{GATEWAY}{BOOK_PATH}", "tools/call",
                     {"name": "get_positions", "arguments": {}}, META,
                     headers=signed_headers("POST", "gateway.uma.lab",
                                            f"/mcp{BOOK_PATH}", rpt, keys))
        try:
            got = sorted(p["symbol"] for p in json.loads(
                mcp_json(r)["result"]["content"][0]["text"])["positions"])
        except (KeyError, IndexError, ValueError, TypeError):
            got = []
        check("and the grant spends at the resource", bool(got), str(r.status_code))

    print("\n6. three ceilings, and each party owns exactly one")
    idt = employee_id_token(c, "alice")
    r = exchange(c, idt, AS, "place_order")
    check("the provider will not assert a scope no administrator approved",
          r.status_code >= 400 and r.json().get("error") == "invalid_scope",
          f"{r.status_code} {r.text[:120]}")
    rpt2, why2, _ = negotiate(c, BOOK_PATH, keys, ent, tool="place_order", hdrs=alice)
    check("and an operation outside the connection never becomes a grant",
          rpt2 is None, why2 or "granted anyway")

    print("\n6b. a perfect assertion does not override the charter")
    his = agent_of(HIS_OPERATOR, "his")
    rpt4, why4, _ = negotiate(c, BOOK_PATH, his, ent, hdrs=alice)
    check("somebody else's agent is refused under a first-party-only role",
          rpt4 is None and "operates herself" in why4, why4 or "granted anyway")
    check("and the refusal comes from the charter, not the provider",
          rpt4 is None and "provider" not in why4 and "assert" not in why4, why4)

    print("\n7. an assertion is not an entitlement")
    r = exchange(c, idt, AS, "get_positions")
    check("a well-formed ID-JAG is issued", r.status_code == 200, r.text[:120])
    if r.status_code == 200:
        jag = r.json()["access_token"]
        spend = c.post(f"{AS}/token", timeout=15.0, data={
            "grant_type": "urn:ietf:params:oauth:grant-type:uma-ticket",
            "claim_token": jag, "claim_token_format": ID_JAG_FORMAT,
            "ticket": "not-a-ticket"})
        check("but it is worth nothing without a ticket of her issuing",
              spend.status_code >= 400, f"{spend.status_code} {spend.text[:120]}")

    print("\n7b. and it is spent once")
    r = exchange(c, employee_id_token(c, "alice"), AS, "get_positions")
    if r.status_code == 200:
        once = r.json()["access_token"]
        codes = []
        for _ in range(2):
            rr = mcp_call(c, f"{GATEWAY}{BOOK_PATH}", "tools/call",
                          {"name": "get_positions", "arguments": {}}, META)
            ch = parse_challenge(rr.headers.get("www-authenticate", ""))
            # The ticket rotates on every beat, so the identity claim has to
            # be presented against the one the challenge beat handed back.
            asked = c.post(f"{ch.as_uri}/token", timeout=15.0,
                           data={"grant_type": "urn:ietf:params:oauth:grant-type:uma-ticket",
                                 "ticket": ch.ticket}).json()
            # `need_info` is itself a 403, so what separates accepted from
            # refused here is the error, not the status.
            codes.append(c.post(f"{ch.as_uri}/token", timeout=15.0, data={
                "grant_type": "urn:ietf:params:oauth:grant-type:uma-ticket",
                "ticket": asked.get("ticket") or ch.ticket, "claim_token": once,
                "claim_token_format": ID_JAG_FORMAT}).json().get("error"))
        check("the same assertion cannot open a second negotiation",
              codes[0] == "need_info" and codes[1] == "request_denied",
              str(codes))

    print("\n8. the assertion is bound to one authority and one person")
    r = exchange(c, idt, CAROL_AS, "get_positions")
    check("an assertion audienced at Carol's authority is issued for Carol's",
          r.status_code == 200, r.text[:120])
    if r.status_code == 200:
        elsewhere = r.json()["access_token"]
        rr = c.post(f"{AS}/token", timeout=15.0, data={
            "grant_type": "urn:ietf:params:oauth:grant-type:uma-ticket",
            "claim_token": elsewhere, "claim_token_format": ID_JAG_FORMAT,
            "ticket": "x"})
        check("and it is refused at Alice's", rr.status_code >= 400,
              f"{rr.status_code} {rr.text[:120]}")

    print("\n8b. an employee who has not joined yet")
    # The direction-of-mastering case. Her employer vouches for her; she has
    # not joined. What must not happen is that the assertion enrols her —
    # joining hands the organization powers over her agents, and those are
    # acquired by agreeing to a charter, not by being on a payroll.
    leave_org(c, alice)
    # The charter started federating at the top of this run, and the refusal
    # below quotes what the organization publishes about itself.
    time.sleep(ORG_DISCOVERY_TTL)
    r = mcp_call(c, f"{GATEWAY}{BOOK_PATH}", "tools/call",
                 {"name": "get_positions", "arguments": {}}, META)
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    check("the firm's book is refused outright — she is not a member of it",
          r.status_code == 403 and body.get("error") == "not_shared",
          f"{r.status_code} {r.text[:120]}")
    check("and no assertion is asked for, because there is nothing to negotiate",
          not r.headers.get("www-authenticate"),
          r.headers.get("www-authenticate", "")[:100])
    check("the refusal names the organization rather than being a dead end",
          "Northwind" in (body.get("error_description") or ""),
          str(body)[:160])
    check("and says how membership is come by",
          "enrol" in (body.get("how_to_join") or "").lower(), str(body)[:200])
    check("an ID-JAG for a non-member enrols nobody",
          not c.get(f"{AS}/owner/organization", headers=alice,
                    timeout=15.0).json().get("enrolled"),
          "she was enrolled without agreeing to anything")

    print("\n8c. she joins, and the same agent then works")
    r = c.post(f"{AS}/owner/organization", headers=alice, timeout=20.0,
               json={"assertion": employee_id_token(c, "alice"), "agreed": True})
    check("signing in at her employer is the whole of the enrolment",
          r.status_code == 200, f"{r.status_code} {r.text[:140]}")
    c.post(f"{AS}/owner/policies", headers=alice, timeout=15.0,
           json={"id": "firmbook", "name": "Northwind book", "ask_me": False,
                 "resources": [f"{BOOK}/get_positions", f"{BOOK}/get_transactions"],
                 "terms": {"purpose": "Desk research on the firm book",
                           "expires_in": 600,
                           "scope": ["positions:read", "transactions:read"],
                           "prohibited": ["client-benchmarking"]}})
    rpt6, why6, _ = negotiate(c, BOOK_PATH, keys, ent, hdrs=alice)
    check("and only then does the same agent get a grant", rpt6 is not None, why6)

    print("\n9. the enterprise half stops at the organization's resources")
    rpt3, why3, said3 = negotiate(c, "", keys, None, hdrs=alice)
    check("her own account never asks for an assertion",
          not any("identity required" in m for m in said3), str(said3)[:160])

    # Put the charter back. This check is the only one that federates
    # identity, and a charter left federated changes what every other check
    # in the lab negotiates against.
    c.put(f"{ORG}/admin/charter", json=base, headers=ADMIN, timeout=20.0)
    if c.get(f"{AS}/owner/organization", headers=alice, timeout=15.0
             ).json().get("enrolled"):
        c.request("DELETE", f"{AS}/owner/organization", headers=alice, timeout=15.0)

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print(f"   FAIL {f}")
    if not FAIL:
        print("\nPASS: two protocols, one request. Northwind's provider said "
              "which\n      employee and which application; Alice's authority "
              "said what\n      could be done on whose terms. Neither could "
              "answer the other's\n      question, and neither had to.")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
