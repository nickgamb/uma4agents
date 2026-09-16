"""The authorization server's own handlers, over the in-memory store.

`store-test` proves the store keeps its promises and `pep-test` proves the
enforcement point does. Neither reaches the code in between: the handlers
that decide what a grant is issued for, how long it lasts, who may ask about
it, whose approval may later relax her rules, and what one holder of a jointly
held resource puts her name to. Those are checked here, by calling the
handlers directly, with no server, no network and no database.

Run: make as-test
"""
import asyncio
import base64
import importlib.util
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "lib"), str(ROOT / "services/uma-as")]
os.environ.setdefault("UMA_AS_SIGNING_KEY",
                      str(Path(tempfile.mkdtemp(prefix="u4a-as-test-")) / "key.pem"))

import jwt  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from jwt.algorithms import OKPAlgorithm  # noqa: E402

import joint as holder_joint  # noqa: E402
from store_memory import MemoryStore  # noqa: E402
from uma4a_joint import mandate_digest  # noqa: E402

spec = importlib.util.spec_from_file_location("uma_as_app", ROOT / "services/uma-as/app.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASSED if ok else FAILED).append(name)
    print(("ok   " if ok else "FAIL ") + name + (f" — {detail}" if detail and not ok else ""))


def refuses(name: str, attempt, because: str) -> None:
    try:
        attempt()
    except ValueError as exc:
        check(name, because in str(exc), str(exc))
        return
    check(name, False, "it was accepted")


KEY = Ed25519PrivateKey.generate()
JWK = json.loads(OKPAlgorithm.to_jwk(KEY.public_key()))


def unverified(token: str) -> dict:
    return jwt.decode(token, options={"verify_signature": False})


def identities() -> None:
    print("\n== a connection's name ==")
    handle = app.connection_handle
    a = handle({"level": "identified", "sub": "agent",
                "iss": "https://login.example/tenant-a/v2.0"}, {})
    b = handle({"level": "identified", "sub": "agent",
                "iss": "https://login.example/tenant-b/v2.0"}, {})
    check("two tenants of one provider are two connections", a != b, f"{a} == {b}")
    check("a subject already qualified by its issuer keeps its name",
          handle({"level": "identified", "sub": a,
                  "iss": "https://login.example/tenant-a/v2.0"}, {}) == a)
    check("an issuer with no path names connections as it always has",
          handle({"level": "identified", "sub": "agent",
                  "iss": "https://ps.uma.lab"}, {}) == "agent@ps.uma.lab")


TEMPLATE = {"nonce": "n-1", "family": "fam_terms", "template_id": "alice/tier1/v1",
            "terms_uri": "https://alice-as.example/terms/alice/tier1/v1",
            "purpose": "portfolio review", "scope": ["positions:read"],
            "prohibited": ["resale"], "expires_in": 3600}


def agreement(**over) -> tuple[str, str]:
    raw = jwt.encode({**TEMPLATE, "aud": app.ISSUER, **over}, KEY,
                     algorithm="EdDSA", headers={"jwk": JWK})
    return raw, base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def negotiating() -> dict:
    return {"owner": "alice", "family": "fam_terms", "template": dict(TEMPLATE),
            "tier": "tier1", "resource_id": "alice-vault/get_positions",
            "resource_scopes": ["positions:read"]}


async def agreements_and_grants() -> None:
    print("\n== what an agreement may say, and what the grant then is ==")
    _, widened = agreement(scope=["positions:read", "trades:execute"])
    refuses("an agreement that adds a scope to the terms is refused",
            lambda: app.verify_contract(widened, negotiating()), "scope was widened")
    _, endless = agreement(expires_in=0)
    refuses("an agreement with no lifetime is refused",
            lambda: app.verify_contract(endless, negotiating()), "positive number")

    raw, short = agreement(expires_in=60)
    rec = negotiating()
    contract, signer = app.verify_contract(short, rec)
    rec.update(contract=contract, agreement_jws=raw)
    issued = await app.issue_rpt(rec, app.s256(raw.encode()), signer, None)
    claims = unverified(issued["access_token"])
    check("a grant lasts no longer than the agent agreed to",
          claims["exp"] - time.time() <= 61, f"{claims['exp'] - time.time():.0f}s")
    check("and neither does its permission",
          claims["permissions"][0]["exp"] - time.time() <= 61)

    handle = app.connection_handle(contract["_identity"], signer)
    store = app.st("alice")
    await store.put_connection({"handle": handle, "status": "active",
                                "first_seen": app.utcstamp()})
    token = issued["access_token"]

    print("\n== who may ask about a grant ==")
    with patch.object(app, "require_pat", AsyncMock(return_value="alice")):
        mine = await app.introspect(None, token=token, consume=None)
    check("the owner's own resource server is told the grant is live",
          mine.get("active") is True, str(mine))
    with patch.object(app, "require_pat", AsyncMock(return_value="carol")):
        theirs = await app.introspect(None, token=token, consume=None)
    check("a resource server holding another owner's PAT is told nothing",
          theirs == {"active": False, "error": "unknown_token"}, str(theirs))

    print("\n== a revoked grant stays revoked ==")
    await store.revoke_connection(handle)
    await store.put_connection({"handle": handle, "status": "active",
                                "first_seen": app.utcstamp()})
    _, _, error = await app._decode_rpt(token)
    check("admitting the same agent again does not revive what revocation ended",
          error == "revoked", f"error was {error!r}")


async def whose_approval() -> None:
    print("\n== whose approval may relax her rules ==")
    store = app.st("alice")
    for label, actor, relaxes in (
            ("an administrator's", {"admin": "dana", "organization": "meridian"}, False),
            ("her own", None, True)):
        family, handle = f"fam_{'admin' if actor else 'hers'}", f"jkt:{label[:5]}"
        await store.put_connection({"handle": handle, "status": "active",
                                    "first_seen": app.utcstamp(),
                                    "tiers_granted": [], "tiers_approved": []})
        await store.mint_ticket({
            "owner": "alice", "family": family, "state": "awaiting-owner",
            "decision": None, "pending_kind": "operation", "tier": "tier2",
            "handle": handle, "resource_id": "alice-vault/get_transactions",
            "resource_scopes": ["transactions:read"], "contract_hash": "s256:x",
            "signer_jwk": JWK, "contract": {"purpose": "x", "prohibited": [],
                                            "_identity": {}}}, 300)
        await app.decide_pending("alice", family, "approved", actor=actor)
        with patch.object(app, "issue_rpt", AsyncMock(return_value={"access_token": "t"})):
            await app.pending_poll(await store.negotiation(family))
        approved = (await store.connection(handle)).get("tiers_approved") or []
        if relaxes:
            check("her own approval is recorded as hers", "tier2" in approved,
                  f"tiers_approved={approved}")
        else:
            check("an administrator's approval is not recorded as hers",
                  "tier2" not in approved, f"tiers_approved={approved}")


MANDATE = {"account": "joint", "resources": ["joint/*"], "rule": {"kind": "all"},
           "holders": [{"owner": "alice", "issuer": "https://alice.example", "weight": 1},
                       {"owner": "carol", "issuer": "https://carol.example", "weight": 1}]}


async def a_holders_verdict() -> None:
    print("\n== what one holder puts her name to ==")
    store = app.st("alice")
    record = holder_joint.record_of("joint", "https://tally.example", MANDATE)
    contract = {"purpose": "joint review", "scope": ["read"], "expires_in": 300,
                "prohibited": [], "_identity": {"level": "pseudonymous"}}
    await store.save_negotiation({
        "owner": "alice", "family": "fam_joint", "state": "awaiting-owner",
        "decision": None, "expires": time.time() + 60, "pending_kind": "joint",
        "tier": "tier1", "resource_id": "joint/read", "resource_scopes": ["read"],
        "handle": "jkt:joint", "contract": contract,
        "contract_hash": "s256:the-one-she-saw", "signer_jwk": JWK,
        "template": {"enforced": {}}})
    await store.decide("fam_joint", "approved", {"kind": "owner", "owner": "alice"})

    async def asked_about(digest: str) -> dict:
        request = ("alice", record, {"negotiation": "fam_joint",
                                     "resource_id": "joint/read", "contract": digest})
        with patch.object(app, "tally_request", AsyncMock(return_value=request)):
            return unverified((await app.joint_verdict(None))["verdict"])

    swapped = await asked_about("s256:a-different-agreement")
    check("her approval is not signed over an agreement she did not see",
          swapped["effect"] == "refuse", str(swapped))
    honest = await asked_about("s256:the-one-she-saw")
    check("and is signed over the one she did", honest["effect"] == "allow", str(honest))
    check("the verdict names the key that agreed",
          honest.get("cnf_jkt") == app.jwk_thumbprint(JWK), str(honest.get("cnf_jkt")))
    check("and the scope and lifetime agreed",
          honest.get("scope") == ["read"] and honest.get("expires_in") == 300)
    check("and the mandate she is counting under",
          honest.get("mandate_s256") == mandate_digest(MANDATE))

    print("\n== a mandate that moved ==")
    reissued = {**MANDATE, "holders": [dict(MANDATE["holders"][0], issuer="https://elsewhere.example"),
                                       MANDATE["holders"][1]]}
    check("a holder answering from a different authority is a change she is shown",
          bool(holder_joint.moved(record, reissued)))
    reweighted = {**MANDATE, "holders": [MANDATE["holders"][0],
                                         dict(MANDATE["holders"][1], weight=3)]}
    check("so is a holder's weight", bool(holder_joint.moved(record, reweighted)))
    check("and an unchanged mandate is not", holder_joint.moved(record, dict(MANDATE)) == [])

    print("\n== a folded agreement, against her own terms ==")
    hers = {"resources": ["joint/*"],
            "terms": {"expires_in": 600, "scope": ["read"], "prohibited": ["resale"]}}
    fair = {"expires_in": 300, "scope": ["read"], "prohibited": ["resale"]}
    check("a fold inside her terms passes",
          holder_joint.verdict_problems(fair, hers, "joint/read") == [])
    check("a fold that widens her terms is refused",
          bool(holder_joint.verdict_problems({**fair, "scope": ["read", "write"]},
                                             hers, "joint/read")))


async def an_unreachable_organization() -> None:
    print("\n== an organization that cannot be reached ==")
    import org as org_mod
    # Nothing listens on port 9, so the call fails as an outage would.
    gone = org_mod.OrgClient("https://127.0.0.1:9", "membership-token", {})
    decision = await gone.decide({"resource_id": "northwind/book/get_positions"})
    check("an organization that cannot be reached refuses the request",
          decision.get("effect") == "refuse" and decision.get("governed") is True,
          str(decision))


def a_clearance() -> None:
    """An attestation about the member, from a party that is not the agent.

    A licence is adverse-capable: its holder has every reason to say it is
    current, so the fact travels from the organization to her authority and
    never through the agent. What is checked here is that every way of
    presenting somebody else's attestation, or a stale one, is refused.
    """
    import uma4a_clearance as clearance

    key = Ed25519PrivateKey.generate()
    jwk = json.loads(OKPAlgorithm.to_jwk(key.public_key()))
    jwk.update({"kid": "org-1", "use": "sig", "alg": "EdDSA"})
    other = Ed25519PrivateKey.generate()

    def mint(signer=key, typ=clearance.TYP, **over):
        claims = {"iss": "https://org.example", "sub": "alice",
                  "aud": "https://alice-as.example", "iat": int(time.time()),
                  "exp": int(time.time()) + 300, "jti": "notice-1",
                  clearance.CLAIM: {"licence_active": True,
                                    "jurisdiction": "US-NY"}}
        claims.update(over)
        return jwt.encode(claims, signer, algorithm="EdDSA",
                          headers={"typ": typ, "kid": "org-1"})

    def verified(token, **over):
        args = {"keys": [jwk], "issuer": "https://org.example",
                "audience": "https://alice-as.example", "subject": "alice",
                "now": time.time()}
        args.update(over)
        return clearance.verify(token, **args)

    def refused(name, token, **over):
        try:
            verified(token, **over)
            check(name, False, "it verified")
        except clearance.ClearanceError as exc:
            check(name, True, str(exc))

    check("an attestation from the organization verifies",
          verified(mint()) == {"licence_active": True, "jurisdiction": "US-NY"})
    refused("a membership token is not a clearance, whatever it carries",
            mint(typ="u4a-membership+jwt"))
    refused("an attestation about somebody else is refused",
            mint(sub="carol"))
    refused("an attestation audienced at another authority is refused",
            mint(aud="https://carol-as.example"))
    refused("an expired attestation is refused — a licence lapses",
            mint(exp=int(time.time()) - 3600, iat=int(time.time()) - 7200))
    refused("one signed by a key the organization does not publish is refused",
            mint(signer=other))
    refused("and one carrying no facts at all is refused",
            jwt.encode({"iss": "https://org.example", "sub": "alice",
                        "aud": "https://alice-as.example",
                        "iat": int(time.time()), "exp": int(time.time()) + 300,
                        "jti": "n2"}, key, algorithm="EdDSA",
                       headers={"typ": clearance.TYP, "kid": "org-1"}))


async def main() -> int:
    app.STORE = MemoryStore()
    await app.st("alice").seed()
    identities()
    a_clearance()
    await agreements_and_grants()
    await whose_approval()
    await a_holders_verdict()
    await an_unreachable_organization()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
