"""A resource server meeting an authority nobody configured it against.

FedAuthz begins with a resource server that already holds a PAT. Where one
operator runs both sides, a provisioned client secret is a fair account of how
it got one — Alice's authority and Meridian's gateway were stood up together,
and that is how they still authenticate here.

It stops being an account of anything once the authority is the owner's.
Carol's server has never heard of Meridian, and Meridian was never given a
secret for Carol; there was no moment at which anyone could have configured
both ends, because the two ends belong to different people. So the gateway
introduces itself: it signs a registration with the key it publishes at its
own origin, in the RFC 9728 document that origin already serves, and Carol's
authority fetches that document and checks the signature against it.

What that buys is an authority Carol can put anywhere — her own hardware, a
hosted instance, an edge isolate — without anyone at Meridian doing anything.
What it does not buy is access. A verified signature settles who is asking.
Whether they may is hers, and this check is mostly about the ways of not
getting an answer:

  * an origin that does not publish the key that signed gets nothing;
  * a claim to a resource whose own metadata names something else gets
    nothing;
  * a stale signature gets nothing, however valid it once was;
  * a verified registration gets nothing until she says so;
  * and when she withdraws it, the next call stops — asking again puts it
    back in front of her rather than back to work.

Run with `make establishment-check`.
"""

from __future__ import annotations

import json
import os
import sys
import time
import types
import uuid

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, "/driver/lib")
import uma4a_http_sig as hs  # noqa: E402
from uma4a_grant import (  # noqa: E402
    AgentKeys, GrantDenied, mcp_call, mcp_json, mcp_meta, parse_challenge,
    run_grant, signed_headers,
)

GATEWAY = os.environ.get("UMA4A_GATEWAY", "https://gateway.uma.lab/mcp")
KEYCLOAK = os.environ.get("UMA4A_OIDC", "https://keycloak.uma.lab")
CA = os.environ.get("UMA4A_CACERT", "/driver/rootCA.pem")
KEYS = "/driver/keys"
RUN = uuid.uuid4().hex[:8]
META = mcp_meta("u4a-establishment-check")

OWNER = "carol"
AS = os.environ.get("UMA4A_CAROL_AS", "https://carol-as.uma.lab")
AS_AUTHORITY = AS.split("://", 1)[-1]
PASSWORD = os.environ.get("CAROL_PASSWORD", "carol-demo")
RS = "https://gateway.uma.lab"
RESOURCE = f"{RS}/mcp/{OWNER}"

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"   {'ok  ' if ok else 'FAIL'} {name}"
          + (f" — {detail}" if detail and not ok else ""), flush=True)


def hdrs(c: httpx.Client) -> dict:
    r = c.post(f"{KEYCLOAK}/realms/{OWNER}/protocol/openid-connect/token",
               data={"grant_type": "password", "client_id": "meridian-portal",
                     "username": OWNER, "password": PASSWORD}, timeout=15.0)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def register(c: httpx.Client, *, key: Ed25519PrivateKey, resource_uri: str,
             age_s: int = 0) -> httpx.Response:
    """A registration attempt, as a resource server would make it.

    `age_s` backdates the signature. Nothing but a clock separates a replayed
    request from the original, so the only way to test the freshness window
    is to sign as though the request were made that long ago.
    """
    body = json.dumps({"owner": OWNER, "resource_uri": resource_uri,
                       "name": "establishment-check"}).encode()
    real = hs.time
    if age_s:
        hs.time = types.SimpleNamespace(time=lambda: real.time() - age_s)
    try:
        headers = hs.sign(method="POST", authority=AS_AUTHORITY,
                          path="/rs/register", authorization="",
                          key=key, keyid="uma-pep-1", body=body)
    finally:
        hs.time = real
    headers["Content-Type"] = "application/json"
    return c.post(f"{AS}/rs/register", content=body, headers=headers,
                  timeout=15.0)


def registry(c: httpx.Client) -> dict:
    return {r["client_id"]: r for r in
            c.get(f"{AS}/owner/resource-servers", headers=hdrs(c),
                  timeout=15.0).json()}


def decide(c: httpx.Client, decision: str) -> httpx.Response:
    return c.post(f"{AS}/owner/resource-servers/decision",
                  json={"client_id": RS, "decision": decision},
                  headers=hdrs(c), timeout=15.0)


def call(c: httpx.Client, headers: dict | None = None) -> httpx.Response:
    return mcp_call(c, f"{GATEWAY}/{OWNER}", "tools/call",
                    {"name": "get_positions", "arguments": {}}, META,
                    headers=headers)


def error_of(r: httpx.Response) -> str:
    try:
        return r.json().get("error", "")
    except ValueError:
        return ""


def ensure_active(c: httpx.Client) -> dict:
    """Drive the gateway's relationship with her to active, from wherever it
    is. The lab may have been left mid-negotiation by an earlier run, and a
    check that only works from one starting state is testing the state.

    Everything here is a real move: a call provokes the introduction, and she
    answers it. Nothing is written to her registry from out here.
    """
    for _ in range(6):
        rec = registry(c).get(RS, {})
        if rec.get("status") == "active":
            return rec
        if rec.get("status") == "pending":
            decide(c, "approved")
            continue
        call(c)                        # provoke the introduction, or a re-ask
        time.sleep(1.0)
    return registry(c).get(RS, {})


def main() -> int:
    stranger = Ed25519PrivateKey.generate()
    with httpx.Client(verify=CA, timeout=30.0) as c:
        print(f"\n== a resource server introduces itself to {OWNER}'s "
              f"authority ==", flush=True)

        # --- who may even ask -------------------------------------------
        # Four registrations that must not work, described by what is wrong
        # with each rather than by which check caught it. From out here they
        # are one status code: this side holds no key any origin publishes, so
        # every one of these fails on the signature as well as on the thing it
        # is named for, and only the authorization server's own event log
        # separates the reasons. Each cause is isolated where it can be —
        # the freshness window in `make sig-test`, the metadata rules in the
        # AS's `resource_server.metadata_rejected` events.
        r = register(c, key=stranger, resource_uri=RESOURCE)
        check("signed by a key that origin does not publish: refused",
              r.status_code == 401 and error_of(r) == "invalid_client",
              f"{r.status_code} {r.text[:120]}")

        r = register(c, key=stranger, resource_uri=f"{AS}/mcp/{OWNER}")
        check("claiming a resource at an origin that publishes none: refused",
              r.status_code == 401, f"{r.status_code} {r.text[:120]}")

        r = register(c, key=stranger, resource_uri=f"{RS}/mcp/nobody")
        check("claiming a resource whose metadata names another: refused",
              r.status_code == 401, f"{r.status_code} {r.text[:120]}")

        r = register(c, key=stranger, resource_uri=RESOURCE, age_s=600)
        check("signed long enough ago to have been captured: refused",
              r.status_code == 401, f"{r.status_code} {r.text[:120]}")

        before = registry(c)
        # Named, not counted. Two of the attempts above claim a resource at
        # the gateway's own origin, so they share a client_id with the real
        # relationship and "nothing new is pending" cannot tell them apart
        # from a run that left it pending. The third names an origin nothing
        # legitimate registers under, and its absence is unambiguous.
        check("none of that put anything in her registry",
              AS not in before, f"{sorted(before)}")

        # --- the gateway's own registration, which she has already seen ---
        # It registered itself the first time anything asked for Carol's
        # resource; there was no other way for it to hold a PAT here. If this
        # lab has been up before, she has already approved it.
        rec = ensure_active(c)
        check("the gateway did register itself, by signature and not secret",
              rec.get("auth") == "origin_signature", f"{rec}")
        check("naming the resource it actually serves for her",
              rec.get("resource_uri") == RESOURCE, f"{rec.get('resource_uri')}")

        # --- and it works, which is the point of all of the above ---------
        agent = AgentKeys.load_or_create(f"{KEYS}/est-{RUN}")
        answered = {"v": False}

        def be_her(msg: str) -> None:
            if "has been asked" in msg and not answered["v"]:
                answered["v"] = True
                for p in c.get(f"{AS}/owner/pending", headers=hdrs(c),
                               timeout=15.0).json():
                    c.post(f"{AS}/owner/pending/{p['family']}/decision",
                           json={"decision": "approved"}, headers=hdrs(c),
                           timeout=15.0)

        ch = parse_challenge(call(c).headers.get("www-authenticate", ""))
        check("her resource challenges, on a relationship nobody provisioned",
              ch is not None and ch.as_uri == AS,
              "no challenge" if ch is None else ch.as_uri)
        granted = False
        symbols: list = []
        if ch is not None:
            try:
                rpt = run_grant(c, ch.as_uri, ch.ticket, agent, lambda t: True,
                                on_status=be_her, max_wait_s=90)
                granted = True
            except GrantDenied as exc:
                check("Bob's agent is granted", False, str(exc)[:160])
        if granted:
            hdr = signed_headers("POST", "gateway.uma.lab", f"/mcp/{OWNER}",
                                 rpt, agent)
            try:
                data = json.loads(mcp_json(call(c, hdr))
                                  ["result"]["content"][0]["text"])
                symbols = sorted(p["symbol"] for p in data["positions"])
            except (KeyError, IndexError, ValueError, TypeError):
                symbols = []
            check("Bob's agent is granted, and served her holdings",
                  bool(symbols), f"{symbols}")

        # --- and she can end it -------------------------------------------
        check("she can withdraw the resource server",
              decide(c, "revoked").status_code == 200)
        r = call(c)
        # The gateway's PAT is refused on its next use, it re-registers, and
        # lands back in front of her. A withdrawal that could be undone by
        # asking again would not be a withdrawal.
        check("the next call stops, and asking again only re-asks her",
              r.status_code == 503 and error_of(r) == "authorization_pending",
              f"{r.status_code} {r.text[:120]}")
        check("her registry shows it pending again, not active",
              registry(c).get(RS, {}).get("status") == "pending",
              f"{registry(c).get(RS, {}).get('status')}")

        check("and she can let it back in", decide(c, "approved").status_code == 200)
        for _ in range(10):
            if parse_challenge(call(c).headers.get("www-authenticate", "")):
                break
            time.sleep(1.0)
        check("after which her resource challenges again",
              parse_challenge(call(c).headers.get("www-authenticate", "")) is not None)

    print()
    print(f"{len(PASS)} passed, {len(FAIL)} failed", flush=True)
    if FAIL:
        for f in FAIL:
            print(f"  - {f}")
        return 1
    print("\nPASS: a resource server and an authority that were never")
    print("      configured against each other established a relationship,")
    print("      on nothing but a key published at an origin and Carol's")
    print("      answer — and she ended it and let it back in, over the same")
    print("      owner API her portal calls.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
