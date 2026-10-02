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
    except (ValueError, jwt.InvalidTokenError) as exc:
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
    _, unscoped = agreement(scope=None)
    refuses("an agreement with no scope array is refused",
            lambda: app.verify_contract(unscoped, negotiating()), "array of strings")
    per_op = negotiating()
    per_op["template"]["per_operation"] = True
    _, toolless = agreement(operation={"params": {"qty": 1}})
    refuses("a per-operation agreement naming no tool is refused before she is asked",
            lambda: app.verify_contract(toolless, per_op), "naming a tool")

    def signed(alg: str, jwk: dict) -> str:
        raw = jwt.encode({**TEMPLATE, "aud": app.ISSUER}, KEY, algorithm=alg,
                         headers={"jwk": jwk})
        return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")

    named = {**JWK, "alg": "Ed25519"}
    check("an agreement is verified with the algorithm its key names",
          app.verify_contract(signed("Ed25519", named), negotiating())[1] == named)
    refuses("and not with one its header asks for instead",
            lambda: app.verify_contract(signed("EdDSA", named), negotiating()),
            "not allowed")
    refuses("a bare key names no algorithm, so it is held to the one it always signed",
            lambda: app.verify_contract(signed("Ed25519", JWK), negotiating()),
            "not allowed")
    refuses("an algorithm it does not advertise is refused, by name",
            lambda: app.verify_contract(signed("EdDSA", {**JWK, "alg": "ES256"}),
                                        negotiating()),
            "ES256")
    refuses("a reason past the ceiling is refused wherever an agreement is accepted",
            lambda: app.requester_claims({"reason": "x" * (app.MAX_REASON + 1)}),
            "permitted length")

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

    raw_other, other_res = agreement(resource_id="alice-vault/execute_trade")
    rec_other = negotiating()
    contract_o, signer_o = app.verify_contract(other_res, rec_other)
    rec_other.update(contract=contract_o, agreement_jws=raw_other)
    granted_for = unverified((await app.issue_rpt(
        rec_other, app.s256(raw_other.encode()), signer_o, None))["access_token"])
    check("the resource a grant covers is the negotiation's, whatever the agreement names",
          [p["resource_id"] for p in granted_for["permissions"]]
          == ["alice-vault/get_positions"], str(granted_for["permissions"]))

    raw_long, long_ = agreement(expires_in=86400)
    rec_long = negotiating()
    rec_long["template"] = {**rec_long["template"], "expires_in": 172800}
    contract_long, signer_long = app.verify_contract(long_, rec_long)
    rec_long.update(contract=contract_long, agreement_jws=raw_long)
    lasting = unverified((await app.issue_rpt(
        rec_long, app.s256(raw_long.encode()), signer_long, None))["access_token"])
    check("and as long as it agreed to, when her terms allow it, past any hour",
          abs(lasting["exp"] - time.time() - 86400) <= 5,
          f"{lasting['exp'] - time.time():.0f}s")

    handle = app.connection_handle(contract["_identity"], signer)
    store = app.st("alice")
    await store.put_connection({"handle": handle, "status": "active",
                                "first_seen": app.utcstamp()})
    token = issued["access_token"]

    raw_c, cleared = agreement()
    rec_c = negotiating()
    contract_c, signer_c = app.verify_contract(cleared, rec_c)
    rec_c.update(contract=contract_c, agreement_jws=raw_c, clearance={"licence": "series-7"})
    cleared_token = (await app.issue_rpt(rec_c, app.s256(raw_c.encode()), signer_c,
                                         None))["access_token"]

    print("\n== who may ask about a grant ==")
    with patch.object(app, "require_pat", AsyncMock(return_value="alice")):
        mine = await app.introspect(None, token=token, consume=None)
        cleared_answer = await app.introspect(None, token=cleared_token, consume=None)
    check("a grant issued under a clearance says so when introspected, as the same digest",
          cleared_answer.get("clearance") == unverified(cleared_token).get("clearance")
          == app.s256(json.dumps({"licence": "series-7"}, sort_keys=True,
                                 separators=(",", ":"), ensure_ascii=False).encode()),
          str(cleared_answer.get("clearance")))
    check("the owner's own resource server is told the grant is live",
          mine.get("active") is True, str(mine))
    check("and is given what enforcement reads, from the answer rather than the token",
          mine.get("cnf") == claims["cnf"] and mine.get("permissions") == claims["permissions"]
          and mine.get("contract") == claims["contract"], str(mine))
    check("the grant carries iss, aud, jti and exp",
          all(claims.get(k) for k in ("iss", "aud", "jti", "exp")), str(sorted(claims)))
    check("and is an RFC 9068 access token, whose subject and client are her handle",
          jwt.get_unverified_header(token).get("typ") == "at+jwt"
          and claims.get("iat") and claims.get("sub") == claims.get("client_id") == handle,
          f"{jwt.get_unverified_header(token)} {claims.get('sub')} {handle}")
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
    with patch.object(app, "require_pat", AsyncMock(return_value="carol")):
        theirs = await app.introspect(None, token=token, consume=None)
        spend = await app.consume_rpt(None, token=token)
    check("another owner's resource server is not told it was revoked",
          theirs == {"active": False, "error": "unknown_token"}, str(theirs))
    check("nor told so when it tries to spend it",
          spend == {"consumed": False, "error": "unknown_token"}, str(spend))


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


async def an_owner_nobody_set_up() -> None:
    print("\n== a name nobody set up is not an owner ==")
    from fastapi import HTTPException

    for label, attempt in (
            ("her terms index", lambda: app.terms_index("mallory")),
            ("a terms document", lambda: app.terms_document("mallory/x/v1", None))):
        try:
            await attempt()
            check(f"{label} for an unknown owner is refused", False, "answered")
        except HTTPException as exc:
            check(f"{label} for an unknown owner is refused", exc.status_code == 404,
                  str(exc.status_code))
    check("and asking made no owner of her", "mallory" not in await app.STORE.owners(),
          str(await app.STORE.owners()))


async def a_mandate_over_the_firms_own_resource() -> None:
    print("\n== a jointly held account cannot take the firm's resource out of its reach ==")
    from types import SimpleNamespace

    from fastapi import HTTPException

    class Req:
        async def json(self):
            return {"tally": "https://tally.example", "account": "a", "agreed": True}

    REFUSED = "her authority refuses to agree to a mandate over what her organization claims"
    firm = {"claims": ["northwind-vault/*"]}
    mandate = {"resources": ["northwind-vault/*"],
               "holders": [{"owner": "alice"}, {"owner": "carol"}]}
    with patch.object(app, "require_owner", AsyncMock(return_value="alice")), \
            patch.object(app, "fetch_mandate", AsyncMock(return_value=mandate)), \
            patch.object(app, "org_envelope", AsyncMock(return_value=firm)):
        try:
            await app.owner_joint_join(Req())
            check(REFUSED, False, "agreed")
        except HTTPException as exc:
            check(REFUSED, exc.status_code == 409, str(exc.detail))
    client = SimpleNamespace(envelope={**firm, "grants": ["northwind-vault/*"]})
    with patch.object(app, "org_client", AsyncMock(return_value=client)), \
            patch.object(app, "jointly_held",
                         AsyncMock(return_value={"northwind-vault/*", "meridian-joint/*"})):
        env = await app.org_envelope("alice")
    check("and one she holds anyway does not lift the firm's ceiling off it",
          env["excluded"] == ["meridian-joint/*"], str(env["excluded"]))
    greedy = SimpleNamespace(envelope={"claims": ["northwind-vault/*", "meridian-joint/*"],
                                       "grants": ["northwind-vault/*"]})
    with patch.object(app, "org_client", AsyncMock(return_value=greedy)), \
            patch.object(app, "jointly_held",
                         AsyncMock(return_value={"meridian-joint/*"})):
        env = await app.org_envelope("alice")
    check("but a charter claiming her joint account does not bring it into reach",
          env["excluded"] == ["meridian-joint/*"], str(env["excluded"]))


async def a_tier_written_again() -> None:
    print("\n== a tier deleted and written again ==")

    class Req:
        def __init__(self, body):
            self.body = body

        async def json(self):
            return self.body

    spec = {"id": "drafts", "name": "Drafts", "resources": [],
            "terms": {"purpose": "drafting", "expires_in": 600}}
    with patch.object(app, "require_owner", AsyncMock(return_value="alice")), \
            patch.object(app, "org_envelope", AsyncMock(return_value=None)):
        first = await app.owner_create_policy(Req(spec))
        await app.owner_delete_policy("drafts", Req({}))
        second = await app.owner_create_policy(Req({**spec, "terms": {
            "purpose": "something else entirely", "expires_in": 600}}))
    check("continues its numbering, so one id never names two documents",
          first["terms"]["template_id"] == "alice/drafts/v1"
          and second["terms"]["template_id"] == "alice/drafts/v2",
          f"{first['terms']['template_id']} then {second['terms']['template_id']}")


def pulled_registrations() -> None:
    print("\n== what a pull believes about a resource server ==")
    RU = "https://rs.example/mcp"
    rs_key, other_key = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    rs_jwk = json.loads(OKPAlgorithm.to_jwk(rs_key.public_key()))

    def documents(signer=rs_key, iss=RU, owner="alice", rid="x/get") -> dict:
        signed = jwt.encode({"iss": iss, "owner_resources_endpoint":
                             "https://rs.example/owner-resources/alice"}, signer,
                            algorithm="EdDSA")
        return {
            app.well_known_prm_url(RU): {"resource": RU, "authorization_servers":
                                         [app.ISSUER], "jwks_uri": "https://rs.example/jwks",
                                         "signed_metadata": signed},
            "https://rs.example/jwks": {"keys": [rs_jwk]},
            "https://rs.example/owner-resources/alice": {
                "owner": owner, "resources": [{"_id": rid, "resource_scopes": ["s"]}]},
        }

    class Client:
        docs: dict = {}

        def __init__(self, **_):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def stream(self, method, url, **_):
            body = json.dumps(Client.docs[url]).encode()

            class Resp:
                def __enter__(self):
                    return self

                def __exit__(self, *_):
                    return False

                def raise_for_status(self):
                    pass

                def iter_bytes(self):
                    yield body
            return Resp()

    def pull(client_id="rs-a", **over):
        Client.docs = documents(**over)
        with patch("httpx.Client", Client):
            return app.pull_registrations(client_id, {"resource_uri": RU}, "alice")

    app.RESOURCES.clear()
    check("a resource server's own signed listing is registered for her",
          pull() == 1 and ("alice", "x/get") in app.RESOURCES, str(list(app.RESOURCES)))
    for label, over in (
            ("metadata signed by a key the resource does not publish is refused",
             {"signer": other_key}),
            ("metadata naming another resource as its issuer is refused",
             {"iss": "https://other.example/mcp"}),
            ("a listing that names another owner is refused", {"owner": "carol"})):
        try:
            pull(**over)
            check(label, False, "accepted")
        except ValueError:
            check(label, True)
    pull(client_id="rs-b")
    check("a second resource server she approved may serve the same resource",
          app.RESOURCES[("alice", "x/get")]["sources"] == ["rs-a", "rs-b"],
          str(app.RESOURCES[("alice", "x/get")].get("sources")))

    Client.docs = documents(rid="y/get")
    with patch("httpx.Client", Client):
        app.pull_registrations("rs-a", {"resource_uri": RU}, "alice")
    check("and when one stops publishing it, it stays registered for the other",
          app.RESOURCES[("alice", "x/get")]["sources"] == ["rs-b"],
          str(app.RESOURCES.get(("alice", "x/get"))))
    app.RESOURCES.clear()


async def who_may_ask_about_a_resource() -> None:
    print("\n== who may ask for a ticket over a resource ==")
    from types import SimpleNamespace
    app.RESOURCES[("alice", "x/get")] = {"resource_scopes": ["s"], "owner": "alice",
                                         "sources": ["rs-a", "rs-b"]}

    async def perm(as_client: str):
        class Req:
            state = SimpleNamespace(pat_client=as_client)

            async def json(self):
                return {"resource_id": "x/get", "resource_scopes": ["s"]}
        with patch.object(app, "require_pat", AsyncMock(return_value="alice")), \
                patch.object(app, "pull_registrations_now", AsyncMock()):
            return await app.register_permission(Req())

    check("a resource server that serves it may",
          (await perm("rs-b")).status_code == 201, str((await perm("rs-b")).status_code))
    with patch.object(app, "pull_registrations", lambda *a: None):
        refused = await perm("rs-c")
    check("one she approved for something else may not",
          refused.status_code == 400 and b"invalid_resource_id" in refused.body,
          str(refused.status_code))

    def now_lists_it(client_id, rs, owner):
        app.RESOURCES[("alice", "x/get")]["sources"] = ["rs-a", "rs-b", "rs-c"]
    with patch.object(app, "pull_registrations", now_lists_it):
        late = await perm("rs-c")
    check("but one this replica had not yet read it from is read again, then answered",
          late.status_code == 201, str(late.status_code))
    app.RESOURCES.clear()


async def an_introduction_by_token() -> None:
    print("\n== an introducing agent's token ==")
    other = json.loads(OKPAlgorithm.to_jwk(Ed25519PrivateKey.generate().public_key()))
    claims = {"iss": "https://ps.example", "sub": "aauth:parent@ps.example",
              "cnf": {"jwk": other}}
    with patch.object(app, "verify_agent_token", lambda token: claims):
        handle, why = await app.introduction_ok(
            "alice", {"parent_jwk": JWK, "agent_token": "t"},
            {"level": "pseudonymous"}, None)
    check("is refused when it binds a key other than the one that introduced",
          handle is None and "different key" in why, why)


async def an_operator_let_back_in() -> None:
    print("\n== an operator she blocks, and then lets back in ==")
    store = app.st("alice")

    class Req:
        def __init__(self, body):
            self.body = body

        async def json(self):
            return self.body

    origin = "https://op.example"
    await store.put_connection({
        "handle": "jkt:op-agent", "status": "active", "first_seen": app.utcstamp(),
        "identity": {"client_metadata": {"client_id": f"{origin}/agent.json",
                                         "verified": True}},
        "tiers_granted": [], "tiers_approved": []})
    with patch.object(app, "require_owner", AsyncMock(return_value="alice")), \
            patch.object(app, "operator_origin", lambda identity: origin):
        await app.owner_block_operator(Req({"origin": origin}))
        blocked = (await store.connection("jkt:op-agent"))["status"]
        await app.owner_unblock_operator(Req({"origin": origin}))
    after = (await store.connection("jkt:op-agent"))["status"]
    check("blocking ends the connections it runs",
          blocked != "active", blocked)
    check("and unblocking restores the right to ask, not the connections",
          after != "active", after)


async def what_a_terms_document_says_about_her() -> None:
    print("\n== what a published terms document says about her ==")
    tiers = await app.st("alice").tiers()
    for tier_id, tier in tiers.items():
        await app.publish_terms("alice", tier_id, tier)
    docs = await app.st("alice").terms_docs()
    allowed = {"template_id", "terms_uri", "proffered_by", "name", "tier", "purpose",
               "scope", "expires_in", "prohibited", "per_operation", "constraints",
               "organization", "family", "published_at"}
    extra = sorted({k for d in docs for k in d} - allowed)
    check("it carries her terms and nothing that names her beyond the resource id",
          docs and not extra, f"extra fields: {extra}")


async def what_her_dialog_is_told() -> None:
    print("\n== what her decision surface is told about a request ==")
    store = app.st("alice")
    for family, kind in (("fam_kind_c", "connection"), ("fam_kind_o", "operation")):
        await store.mint_ticket({
            "owner": "alice", "family": family, "state": "awaiting-owner",
            "decision": None, "pending_kind": kind, "tier": "tier2",
            "handle": f"jkt:{family}", "resource_id": "alice-vault/get_transactions",
            "resource_scopes": ["transactions:read"], "contract_hash": "s256:x",
            "signer_jwk": JWK, "contract": {"purpose": "x", "prohibited": [],
                                            "_identity": {}}}, 300)
    kinds = {p["family"]: p["kind"] for p in await app.pending_view("alice")}
    check("which kind of request is waiting: meeting an agent, or one operation",
          kinds.get("fam_kind_c") == "connection" and kinds.get("fam_kind_o") == "operation",
          str(kinds))
    for family in ("fam_kind_c", "fam_kind_o"):
        await app.decide_pending("alice", family, "denied", actor=None)


async def an_approval_she_has_since_overtaken() -> None:
    print("\n== an approval does not outlive what she withdrew after it ==")
    store = app.st("alice")
    issued = AsyncMock(return_value={"access_token": "t"})

    async def pend(family: str, handle: str, kind: str, seen: int = 0) -> None:
        await store.mint_ticket({
            "owner": "alice", "family": family, "state": "awaiting-owner",
            "decision": None, "pending_kind": kind, "tier": "tier2",
            "handle": handle, "revocations_seen": seen,
            "resource_id": "alice-vault/get_transactions",
            "resource_scopes": ["transactions:read"], "contract_hash": "s256:x",
            "signer_jwk": JWK, "contract": {"purpose": "x", "prohibited": [],
                                            "_identity": {}}}, 300)
        await app.decide_pending("alice", family, "approved", actor=None)

    async def collect(family: str):
        issued.reset_mock()
        with patch.object(app, "issue_rpt", issued):
            return await app.pending_poll(await store.negotiation(family))

    await store.put_connection({"handle": "jkt:later", "status": "active",
                                "first_seen": app.utcstamp(),
                                "tiers_granted": [], "tiers_approved": []})
    await pend("fam_later", "jkt:later", "operation")
    await store.revoke_connection("jkt:later")
    r = await collect("fam_later")
    check("an approval collected after she revoked the agent issues nothing",
          r.status_code == 403 and not issued.called, f"{r.status_code}")

    await pend("fam_again", "jkt:later", "connection", seen=1)
    r = await collect("fam_again")
    check("but admitting it again, knowing it was revoked, still works",
          r.status_code == 200 and issued.called, f"{r.status_code}")

    await pend("fam_twice", "jkt:later", "connection", seen=1)
    await store.revoke_connection("jkt:later")
    r = await collect("fam_twice")
    check("and a revocation between its asking and its collecting is not undone",
          r.status_code == 403 and not issued.called, f"{r.status_code}")

    await store.put_connection({"handle": "jkt:cleared", "status": "active",
                                "first_seen": app.utcstamp(),
                                "tiers_granted": [], "tiers_approved": []})
    await pend("fam_cleared", "jkt:cleared", "operation")
    with patch.object(app, "clearance_unmet",
                      AsyncMock(return_value=(["the licence is no longer attested"], {}))):
        r = await collect("fam_cleared")
    check("a clearance lost while she was deciding is read again before the grant",
          r.status_code == 403 and not issued.called, f"{r.status_code}")


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

    async def asked_about(digest: str, published: dict = MANDATE) -> dict:
        request = ("alice", record, {"negotiation": "fam_joint",
                                     "resource_id": "joint/read", "contract": digest})
        with patch.object(app, "tally_request", AsyncMock(return_value=request)), \
                patch.object(app, "fetch_mandate", AsyncMock(return_value=published)):
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
    await store.set_mandate("joint", record)
    with patch.object(app, "owner_notify", AsyncMock()) as told:
        moved = await asked_about("s256:the-one-she-saw", published=reweighted)
        await asked_about("s256:the-one-she-saw", published=reweighted)
    check("a holder does not sign under a mandate she has not agreed to",
          moved["effect"] == "refuse", str(moved))
    kept = await store.mandate("joint")
    check("and her authority keeps what changed, for her to agree to again",
          bool(kept.get("moved")), str(kept.get("moved")))
    check("she is told once, not at every verdict", told.await_count == 1,
          f"told {told.await_count} times")

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


async def her_signed_request_sent_twice() -> None:
    print("\n== her signed request, sent a second time ==")
    from starlette.requests import Request
    from uma4a_http_sig import sign
    key = Ed25519PrivateKey.generate()
    body = b'{"decision":"approved"}'
    path = "/owner/pending/fam_x/decision"
    headers = sign("POST", app.OWNER_EXPECTED_AUTHORITY, path, "", key, "her-device", body=body)

    def request(method: str = "POST"):
        raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
        sent = {"done": False}

        async def receive():
            if sent["done"]:
                return {"type": "http.disconnect"}
            sent["done"] = True
            return {"type": "http.request", "body": body, "more_body": False}
        return Request({"type": "http", "method": method, "path": path, "query_string": b"",
                        "headers": raw, "server": ("as", 80), "scheme": "http"}, receive)

    with patch.object(app, "owner_device_key", return_value=key.public_key()):
        first = await app.require_owner_signature(request())
        check("the first is hers", first == app.OWNER_KEY_OWNER)
        try:
            await app.require_owner_signature(request())
            check("the same signed change sent again is refused", False, "accepted")
        except app.HTTPException as exc:
            check("the same signed change sent again is refused",
                  exc.status_code == 401 and "already" in exc.detail, exc.detail)


async def what_it_says_it_verifies() -> None:
    print("\n== the algorithms it says it verifies ==")
    meta = await app.discovery()
    check("it advertises Ed25519 for signed claim tokens",
          {"EdDSA", "Ed25519"} <= set(meta.get("signing_alg_values_supported", [])))
    check("and ed25519 for signed requests",
          "ed25519" in meta.get("http_message_signature_alg_values_supported", []))
    check("it advertises where the parties beside her reach it",
          all(meta.get(k) for k in ("rs_registration_endpoint", "org_notice_endpoint",
                                    "org_admin_endpoint", "joint_quote_endpoint",
                                    "joint_verdict_endpoint")))
    forged = jwt.encode({"owner": "alice", "account": "x", "iss": "https://tally.example",
                         "exp": int(time.time()) + 60}, KEY, algorithm="EdDSA",
                        headers={"typ": "u4a-verdict+jwt"})
    try:
        app.tally_claims(forged, "https://tally.example")
        check("a tally request must be typed as one", False, "accepted")
    except app.HTTPException as exc:
        check("a tally request must be typed as one", exc.status_code == 401, exc.detail)


def _request(method: str, path: str, body: bytes, ctype: str):
    from starlette.requests import Request
    sent = {"done": False}

    async def receive():
        if sent["done"]:
            return {"type": "http.disconnect"}
        sent["done"] = True
        return {"type": "http.request", "body": body, "more_body": False}
    return Request({"type": "http", "method": method, "path": path, "query_string": b"",
                    "headers": [(b"content-type", ctype.encode())],
                    "server": ("as", 443), "scheme": "https"}, receive)


async def the_wire_from_her_organization() -> None:
    print("\n== what the parties beside her send ==")
    org_key = Ed25519PrivateKey.generate()
    org_jwk = json.loads(OKPAlgorithm.to_jwk(org_key.public_key()))

    def notice(kind: str, typ: str = "u4a-org-notice+jwt", jti: str = "n-1") -> object:
        token = jwt.encode({"iss": "https://org.example", "sub": "alice", "org": "nw",
                            "kind": kind, "iat": int(time.time()),
                            "exp": int(time.time()) + 300, "jti": jti},
                           org_key, algorithm="EdDSA", headers={"typ": typ})
        return _request("POST", "/org/notice", json.dumps({"notice": token}).encode(),
                        "application/json")

    with patch.object(app, "org_record",
                      AsyncMock(return_value={"issuer": "https://org.example", "envelope": {}})), \
            patch.object(app, "issuer_keys", lambda issuer, fresh=False: [org_jwk]):
        try:
            await app.org_notice(notice("charter_changed", typ="u4a-org-admin+jwt", jti="n-0"))
            check("a notice must be typed as one", False, "accepted")
        except app.HTTPException as exc:
            check("a notice must be typed as one", exc.status_code == 401, exc.detail)
        answer = await app.org_notice(notice("something_added_later"))
        check("a kind it does not know is accepted and nothing is done",
              answer == {"received": "something_added_later"}, str(answer))
        try:
            await app.org_notice(notice("something_added_later"))
            check("the same notice is acted on once", False, "accepted twice")
        except app.HTTPException as exc:
            check("the same notice is acted on once", exc.status_code == 409, exc.detail)

    tally_key, elsewhere = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    asked = jwt.encode({"owner": "alice", "account": "joint", "iss": "https://tally.example",
                        "iat": int(time.time()), "exp": int(time.time()) + 60},
                       elsewhere, algorithm="EdDSA", headers={"typ": "u4a-tally-req+jwt"})
    with patch.object(app, "issuer_keys", lambda issuer, fresh=False: [
            json.loads(OKPAlgorithm.to_jwk(tally_key.public_key()))]):
        try:
            app.tally_claims(asked, "https://tally.example")
            check("a question not signed by the tally her mandate names is refused",
                  False, "answered")
        except app.HTTPException as exc:
            check("a question not signed by the tally her mandate names is refused",
                  exc.status_code == 401, exc.detail)

    store = app.st("alice")
    seeded = await store.resource_server("meridian-gateway")
    await store.put_resource_server("meridian-gateway", {**seeded, "secret": "old-secret"})
    with patch.dict(os.environ, {"UMA_AS_RS_CLIENT_SECRET": "rotated-secret"}):
        rotated = await app.token(_request(
            "POST", "/token",
            b"grant_type=client_credentials&scope=uma_protection&owner=alice"
            b"&client_id=meridian-gateway&client_secret=rotated-secret",
            "application/x-www-form-urlencoded"))
        stale = await app.token(_request(
            "POST", "/token",
            b"grant_type=client_credentials&scope=uma_protection&owner=alice"
            b"&client_id=meridian-gateway&client_secret=old-secret",
            "application/x-www-form-urlencoded"))
    check("a provisioned secret the deployment rotated is the one that works",
          rotated.status_code == 200 and stale.status_code == 401,
          f"{rotated.status_code} {stale.status_code}")
    await store.put_resource_server("meridian-gateway", {**seeded, "secret": "old-secret",
                                                         "status": "revoked"})
    with patch.dict(os.environ, {"UMA_AS_RS_CLIENT_SECRET": "rotated-secret"}):
        revoked = await app.token(_request(
            "POST", "/token",
            b"grant_type=client_credentials&scope=uma_protection&owner=alice"
            b"&client_id=meridian-gateway&client_secret=rotated-secret",
            "application/x-www-form-urlencoded"))
    check("and one she revoked stays revoked", revoked.status_code == 403,
          str(revoked.status_code))
    await store.put_resource_server("meridian-gateway", seeded)

    pat = await app.token(_request(
        "POST", "/token",
        b"grant_type=client_credentials&scope=uma_protection&owner=mallory&client_id=rs",
        "application/x-www-form-urlencoded"))
    check("a PAT for an owner it does not serve is refused, and creates no owner",
          pat.status_code == 401 and "mallory" not in await app.STORE.owners(),
          str(pat.status_code))


async def main() -> int:
    app.STORE = MemoryStore()
    await app.st("alice").seed()
    identities()
    a_clearance()
    await agreements_and_grants()
    await an_owner_nobody_set_up()
    await an_operator_let_back_in()
    await what_her_dialog_is_told()
    await what_a_terms_document_says_about_her()
    await an_introduction_by_token()
    pulled_registrations()
    await who_may_ask_about_a_resource()
    await a_tier_written_again()
    await a_mandate_over_the_firms_own_resource()
    await whose_approval()
    await an_approval_she_has_since_overtaken()
    await a_holders_verdict()
    await an_unreachable_organization()
    await her_signed_request_sent_twice()
    await what_it_says_it_verifies()
    await the_wire_from_her_organization()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
