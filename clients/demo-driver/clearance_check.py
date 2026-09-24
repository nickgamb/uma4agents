"""Clearance: an authorization that is nobody's in this negotiation to give.

Alice's terms decide whether an agent may touch her things. They cannot decide
whether the act is *permitted at all* — whether the desk behind it holds a
current licence, whether it is registered where the trade would be placed.
Those are facts about the world, and the party asking is the last party who
should be asked for them.

So the requirement is hers, or her organization's, and the answer comes from
the organization over her authority's own membership credential. Never from
the agent. This is the same rule the joint-ownership work arrived at from the
other direction:

    a claim works when the requesting party is the only one who holds the
    fact, and fails when the fact may be adverse to it.

A licence is adverse-capable — its holder has every reason to say it is
current — so it travels authority to authority, signed, audienced at one
authority, about one member, and short-lived because a licence lapses.

What this check follows, end to end:

  * an administrator writes the requirement into the charter, and a
    requirement that would not evaluate is refused in front of him;
  * her authority takes it into terms she had already written, and she cannot
    edit it back out — the ceiling narrows, as every other ceiling field does;
  * an agent that would otherwise be granted is refused, before it signs
    anything, and told which claim is missing;
  * the organization attests, and the same request goes through;
  * the organization withdraws it, and access stops without anybody editing a
    policy.

Run against the full stack with `make clearance-check`, or in the cluster with
`make k8s-clearance-check`. Unit tests, needing nothing running:
`make org-test`.
"""

from __future__ import annotations

from collections.abc import Mapping
import base64
import json
import os
import sys
import time
import uuid

import httpx

sys.path.insert(0, "/driver/lib")
from uma4a_grant import (  # noqa: E402
    AgentKeys, GrantDenied, mcp_call, mcp_json, mcp_meta, parse_challenge,
    run_grant, signed_headers,
)

GATEWAY = os.environ.get("UMA4A_GATEWAY", "https://gateway.uma.lab/mcp")
KEYCLOAK = os.environ.get("UMA4A_OIDC", "https://keycloak.uma.lab")
AS_PUBLIC = os.environ.get("UMA4A_AS", "https://alice-as.uma.lab")
ORG = os.environ.get("UMA4A_ORG", "https://northwind-org.uma.lab")
class _OrgAdmin(Mapping):
    """Dana, signed in at Northwind's administration realm, as request headers.

    The credential the console holds, not a static token beside it. Fetched
    on first use and again a minute before it lapses, so a long run never
    sends an expired one."""

    def __init__(self) -> None:
        self._token, self._expires = "", 0.0

    def _headers(self) -> dict:
        if time.time() > self._expires - 60:
            r = httpx.post(
                f"{KEYCLOAK}/realms/northwind/protocol/openid-connect/token",
                data={"grant_type": "password", "client_id": "meridian-org-console",
                      "username": os.environ.get("ORG_ADMIN_USER", "dana"),
                      "password": os.environ.get("ORG_ADMIN_PASSWORD", "dana-demo")},
                verify=CA, timeout=15.0)
            r.raise_for_status()
            self._token = r.json()["access_token"]
            self._expires = time.time() + r.json().get("expires_in", 300)
        return {"Authorization": f"Bearer {self._token}"}

    def __getitem__(self, key: str) -> str:
        return self._headers()[key]

    def __iter__(self):
        return iter(self._headers())

    def __len__(self) -> int:
        return 1


ADMIN = _OrgAdmin()
JOIN_CODE = os.environ.get("ORG_JOIN_CODE", "NW-7K2F-QX")
OPERATOR = os.environ.get("UMA4A_AGENT_OPERATOR", "https://agent.uma.lab")
PUBLISHED_KEYS = os.environ.get("UMA4A_PUBLISHED_KEYS")
CA = os.environ.get("UMA4A_CACERT", "/driver/rootCA.pem")
BOOK = "northwind-vault"
SHARED = "/shared/alice"
RUN = uuid.uuid4().hex[:8]
META = mcp_meta("u4a-clearance-check")
# How long her authority may hold a copy of what the organization attests.
# Read from the variable the server is configured with, so a wait here cannot
# drift into a flaky one.
ORG_TTL = float(os.environ.get("UMA_AS_ORG_TTL_S", "30")) + 3
# How long the firm's book may take to reach her registry after she joins.
# Three bounded staleness windows in series, each read from the variable the
# server it belongs to is configured with: the gateway's view of her
# membership, her authority's copy of the ceiling, and her authority's copy of
# what the resource server publishes. Guessing a constant here is how a check
# passes on a warm stack and fails on a cold one.
BOOK_WAIT = (float(os.environ.get("UMA_PEP_MEMBERSHIP_TTL_S", "10"))
             + float(os.environ.get("UMA_AS_ORG_TTL_S", "30"))
             + float(os.environ.get("UMA_AS_RESOURCE_REFRESH_S", "15")) + 20)

# What this organization requires before its book may be reached at all.
REQUIREMENT = {"licence_active": [True], "jurisdiction": ["US-NY", "US-NJ"]}
ATTESTED = {"licence_active": True, "jurisdiction": "US-NY", "desk": "equities"}

PASS, FAIL = [], []


def say(msg: str) -> None:
    print(f"   {msg}", flush=True)


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"   {'ok  ' if ok else 'FAIL'} {name}"
          + (f" — {detail}" if detail and not ok else ""), flush=True)


def hdrs(c: httpx.Client) -> dict:
    r = c.post(f"{KEYCLOAK}/realms/alice/protocol/openid-connect/token",
               data={"grant_type": "password", "client_id": "meridian-portal",
                     "username": "alice",
                     "password": os.environ.get("ALICE_PASSWORD", "alice-demo")},
               timeout=15.0)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def attested_agent(c: httpx.Client, name: str) -> AgentKeys:
    """An agent whose operator publishes its key — the posture a firm's
    charter asks for over its own book."""
    directory = f"{OPERATOR}/.well-known/http-message-signatures-directory"
    provisioned = f"{PUBLISHED_KEYS}/{name}-ed25519.pem" if PUBLISHED_KEYS else None
    if provisioned and os.path.exists(provisioned):
        keys = AgentKeys.load_or_create(provisioned)
        keys.client_id = f"{OPERATOR}/agent.json"
        keys.signature_agent = directory
        return keys
    keys = AgentKeys()
    keys.keyid = f"{name}-{RUN}"
    keys.client_id = f"{OPERATOR}/agent.json"
    keys.signature_agent = keys.publish(c, OPERATOR)
    return keys


def charter_doc(c: httpx.Client) -> dict:
    base = c.get(f"{ORG}/admin/charter/versions/1", headers=ADMIN,
                 timeout=20.0).json()
    return dict(base.get("charter") or base)


def publish(c: httpx.Client, doc: dict) -> httpx.Response:
    return c.put(f"{ORG}/admin/charter", json=doc, headers=ADMIN, timeout=20.0)


def set_clearance(c: httpx.Client, facts: dict) -> httpx.Response:
    return c.put(f"{ORG}/admin/members/alice/clearance",
                 json={"clearance": facts}, headers=ADMIN, timeout=15.0)


def tiers(c: httpx.Client) -> dict:
    return c.get(f"{AS_PUBLIC}/owner/policies", headers=hdrs(c), timeout=15.0).json()


def ledger(c: httpx.Client) -> list:
    return c.get(f"{AS_PUBLIC}/owner/ledger", headers=hdrs(c), timeout=15.0).json()


def poke(c: httpx.Client) -> None:
    """One unauthenticated call, so the gateway publishes and her authority
    pulls. Ordinary discovery, not a back door."""
    mcp_call(c, f"{GATEWAY}{SHARED}", "tools/call",
             {"name": "get_positions", "arguments": {}}, META)


def ensure_resource_server(c: httpx.Client) -> None:
    """Her authority has to be protecting this resource server before any of
    this means anything.

    The gateway introduces itself on first contact and waits for her; nothing
    is registered until she approves it. Under compose that approval has
    usually happened in an earlier run, which is exactly why it has to be
    made to happen here rather than assumed.
    """
    for _ in range(8):
        registry = {r["client_id"]: r for r in c.get(
            f"{AS_PUBLIC}/owner/resource-servers", headers=hdrs(c),
            timeout=15.0).json()}
        if any(r.get("status") == "active" for r in registry.values()):
            return
        pending = [cid for cid, r in registry.items()
                   if r.get("status") == "pending"]
        for cid in pending:
            c.post(f"{AS_PUBLIC}/owner/resource-servers/decision",
                   json={"client_id": cid, "decision": "approved"},
                   headers=hdrs(c), timeout=15.0)
        if not pending:
            mcp_call(c, GATEWAY, "tools/call",
                     {"name": "get_positions", "arguments": {}}, META)
            time.sleep(1.0)


def wait_for_book(c: httpx.Client, seconds: float = BOOK_WAIT) -> bool:
    """Joining is what makes the firm's book exist at her authority.

    It arrives by a pull, so it appears when her authority next reads what the
    resource server publishes — polled rather than slept on, so this cannot
    drift into a flaky wait on a slower machine.
    """
    deadline = time.time() + seconds
    while time.time() < deadline:
        poke(c)
        held = {r["_id"] for r in c.get(f"{AS_PUBLIC}/owner/resources",
                                        headers=hdrs(c), timeout=15.0).json()}
        if f"{BOOK}/get_positions" in held:
            return True
        time.sleep(2.0)
    return False


def negotiate(c: httpx.Client, keys: AgentKeys) -> tuple[str | None, str]:
    """The ordinary four beats at the firm's book, answering as her."""
    r = mcp_call(c, f"{GATEWAY}{SHARED}", "tools/call",
                 {"name": "get_positions", "arguments": {}}, META)
    ch = parse_challenge(r.headers.get("www-authenticate", ""))
    if ch is None:
        return None, f"no challenge: {r.status_code} {r.text[:150]}"
    answered = {"v": False}

    def be_her(msg: str) -> None:
        if "has been asked" not in msg or answered["v"]:
            return
        answered["v"] = True
        for p in c.get(f"{AS_PUBLIC}/owner/pending", headers=hdrs(c),
                       timeout=15.0).json():
            c.post(f"{AS_PUBLIC}/owner/pending/{p['family']}/decision",
                   json={"decision": "approved"}, headers=hdrs(c), timeout=15.0)

    try:
        return run_grant(c, ch.as_uri, ch.ticket, keys, lambda t: True,
                         reason="Desk research", on_status=be_her,
                         max_wait_s=60), ""
    except GrantDenied as exc:
        return None, str(exc)[:240]


def setup(c: httpx.Client) -> None:
    """A clean slate: not a member, no terms over the book, charter at v1."""
    if c.get(f"{AS_PUBLIC}/owner/organization", headers=hdrs(c),
             timeout=15.0).json().get("enrolled"):
        c.request("DELETE", f"{AS_PUBLIC}/owner/organization",
                  headers=hdrs(c), timeout=15.0)
    for tid, t in tiers(c).items():
        if any(r.startswith(f"{BOOK}/") for r in t.get("resources") or []):
            c.request("DELETE", f"{AS_PUBLIC}/owner/policies/{tid}",
                      headers=hdrs(c), timeout=15.0)
    c.request("DELETE", f"{ORG}/admin/members/alice", headers=ADMIN, timeout=15.0)
    publish(c, charter_doc(c))


def main() -> int:                                             # noqa: C901
    c = httpx.Client(verify=CA, timeout=30.0, follow_redirects=True)
    try:
        setup(c)
        ensure_resource_server(c)

        print("\n== 1 · an organization states what it must be able to attest ==")
        bad = charter_doc(c)
        bad["envelope"]["require_clearance"] = {"licence_active": True}
        r = publish(c, bad)
        check("a requirement that would not evaluate is refused when it is "
              "written, not inside every member's grant",
              r.status_code == 400, f"HTTP {r.status_code}")

        doc = charter_doc(c)
        doc["envelope"]["require_clearance"] = REQUIREMENT
        r = publish(c, doc)
        check("a well-formed requirement is published", r.status_code == 200,
              f"HTTP {r.status_code} {r.text[:160]}")
        summary = " ".join(r.json().get("summary") or [])
        check("and a member is told, in words, that it is asserted about her "
              "rather than by her", "attest" in summary, summary[:200])

        print("\n== 2 · her terms carry it, and she cannot edit it out ==")
        r = c.post(f"{AS_PUBLIC}/owner/organization",
                   json={"code": JOIN_CODE, "agreed": True},
                   headers=hdrs(c), timeout=20.0)
        check("she joins", r.status_code == 200, f"HTTP {r.status_code} {r.text[:160]}")
        # A trader, because the analyst role this charter hands out on
        # joining is first-party-only: somebody else's agent may not act on
        # the book at all, and this check is about an agent that otherwise
        # would have been granted.
        c.post(f"{ORG}/admin/members/alice/role", json={"role": "trader"},
               headers=ADMIN, timeout=15.0)
        state = c.get(f"{AS_PUBLIC}/owner/organization", headers=hdrs(c),
                      timeout=15.0).json()
        member = [m for m in c.get(f"{ORG}/admin/members", headers=ADMIN,
                                   timeout=15.0).json() if m["owner"] == "alice"]
        say(f"enrolled={state.get('enrolled')} role="
            f"{(member or [{}])[0].get('role')} grants="
            f"{(member or [{}])[0].get('grants')}; waiting up to "
            f"{BOOK_WAIT:.0f}s for it to reach her registry")
        check("the firm's book reaches her authority, because she joined",
              wait_for_book(c), "it never appeared in her registry")

        r = c.post(f"{AS_PUBLIC}/owner/policies", headers=hdrs(c), timeout=15.0,
                   json={"id": f"firmbook{RUN}", "name": "Northwind book",
                         "ask_me": False,
                         "resources": [f"{BOOK}/get_positions",
                                       f"{BOOK}/get_transactions"],
                         "terms": {"purpose": "Desk research on the firm book",
                                   "expires_in": 3600,
                                   "scope": ["positions:read",
                                             "transactions:read"],
                                   "prohibited": ["client-benchmarking"]}})
        check("she writes her own terms over the firm's book",
              r.status_code == 200, f"HTTP {r.status_code} {r.text[:200]}")
        tier_id = f"firmbook{RUN}"
        written = tiers(c).get(tier_id) or {}
        check("and the organization's requirement is in them, though she "
              "never typed it", written.get("clearance") == REQUIREMENT,
              json.dumps(written.get("clearance")))

        c.put(f"{AS_PUBLIC}/owner/policies/{tier_id}", json={"clearance": {}},
              headers=hdrs(c), timeout=15.0)
        check("editing it away does not take — the ceiling puts it back",
              (tiers(c).get(tier_id) or {}).get("clearance") == REQUIREMENT,
              json.dumps((tiers(c).get(tier_id) or {}).get("clearance")))

        print("\n== 3 · nothing attested, so nothing is granted ==")
        set_clearance(c, {})
        # `attested`, not a per-run name: where the operator provisions its
        # directory (the cluster) the key has to be one it already publishes,
        # or the agent never reaches the accountability the firm's charter
        # requires and is refused before the clearance is reached at all.
        # Under compose there is no provisioned directory and this registers
        # at runtime, as every other check there does.
        keys = attested_agent(c, "attested")
        rpt, why = negotiate(c, keys)
        check("an agent that would otherwise be granted is refused",
              rpt is None, "it was granted")
        check("and told which claim is missing, rather than 'denied'",
              "licence_active" in why or "clearance" in why, why[:200])
        say(f"refusal: {why[:160]}")
        refusals = [e for e in ledger(c) if e.get("kind") == "refused"
                    and any("clearance" in str(b) or "licence" in str(b)
                            for b in e.get("because") or [])]
        check("her record says why, in the same words she would be shown",
              bool(refusals), json.dumps(refusals[-1] if refusals else {})[:200])

        print("\n== 4 · the organization vouches, and the same request goes through ==")
        r = set_clearance(c, ATTESTED)
        check("an administrator records what the organization will attest",
              r.status_code == 200, f"HTTP {r.status_code} {r.text[:160]}")
        rpt, why = negotiate(c, keys)
        check("the agent is granted, with nothing about it changed",
              bool(rpt), why[:200])

        if rpt:
            resp = mcp_call(c, f"{GATEWAY}{SHARED}", "tools/call",
                            {"name": "get_positions", "arguments": {}}, META,
                            headers=signed_headers("POST", "gateway.uma.lab",
                                                   f"/mcp{SHARED}", rpt, keys))
            body = mcp_json(resp)
            check("and the call goes through at the resource",
                  resp.status_code == 200 and "error" not in body,
                  json.dumps(body)[:200])

        # The grant says the check happened; it does not say what was found.
        # The facts are about her — her licence, where she is registered — and
        # the party that would read them here is the agent that asked.
        if rpt:
            body64 = rpt.split(".")[1]
            claims = json.loads(base64.urlsafe_b64decode(
                body64 + "=" * (-len(body64) % 4)))
            carried = claims.get("clearance")
            check("the grant carries that a clearance was checked, as a digest",
                  isinstance(carried, str) and carried.startswith("s256:"),
                  json.dumps(carried))
            check("and does not hand the agent what was attested about her",
                  "US-NY" not in json.dumps(claims)
                  and "licence_active" not in json.dumps(claims),
                  json.dumps(claims)[:200])

        # There is no wire path by which the agent could supply one. Asked
        # here, where the requirement is *satisfied*, so the negotiation gets
        # as far as claims at all: while a clearance is outstanding the
        # negotiation is refused before terms are dictated, which is the
        # ordering the profile requires and a different refusal entirely.
        r = mcp_call(c, f"{GATEWAY}{SHARED}", "tools/call",
                     {"name": "get_positions", "arguments": {}}, META)
        ticket = parse_challenge(r.headers.get("www-authenticate", ""))
        if ticket is not None:
            offered = c.post(f"{ticket.as_uri}/token", data={
                "grant_type": "urn:ietf:params:oauth:grant-type:uma-ticket",
                "ticket": ticket.ticket,
                "claim_token": "eyJhbGciOiJub25lIn0.e30.",
                "claim_token_format": "https://u4a.ai/spec/policy/1.0#clearance+jwt"},
                timeout=15.0)
            check("a clearance the agent offers is not a claim this authority takes",
                  offered.status_code == 400
                  and "invalid_claim_token_format" in offered.text,
                  f"HTTP {offered.status_code} {offered.text[:160]}")

        promised = [e for e in ledger(c) if e.get("kind") == "promised"
                    and e.get("clearance")]
        check("her record keeps what was vouched for",
              bool(promised) and promised[-1]["clearance"].get("jurisdiction")
              == "US-NY", json.dumps(promised[-1] if promised else {})[:200])

        print("\n== 5 · withdrawn, and access stops without a policy edit ==")
        set_clearance(c, {})
        say(f"waiting {ORG_TTL:.0f}s — her authority holds an attestation only "
            f"briefly, because a licence lapses")
        time.sleep(ORG_TTL)
        rpt, why = negotiate(c, keys)
        check("the next request is refused, and nobody edited a policy",
              rpt is None, "it was granted")
        check("her terms are exactly as she left them",
              (tiers(c).get(tier_id) or {}).get("clearance") == REQUIREMENT)
    finally:
        try:
            set_clearance(c, {})
            for tid, t in tiers(c).items():
                if any(r.startswith(f"{BOOK}/") for r in t.get("resources") or []):
                    c.request("DELETE", f"{AS_PUBLIC}/owner/policies/{tid}",
                              headers=hdrs(c), timeout=15.0)
            c.request("DELETE", f"{AS_PUBLIC}/owner/organization",
                      headers=hdrs(c), timeout=15.0)
            c.request("DELETE", f"{ORG}/admin/members/alice", headers=ADMIN,
                      timeout=15.0)
            publish(c, charter_doc(c))
            say("the charter is back at its first version and she has left")
        except Exception as exc:                               # noqa: BLE001
            say(f"cleanup: {exc}")

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
