"""The gateway's reading of a path: which authority a tool call is judged under.

agentgateway routes by leading prefix and forwards everything under a prefix
to that prefix's backend. The enforcement point has to name the same owner,
member or account the gateway forwards to, for every path the gateway accepts,
or a grant from one authority is spent at another's resource. These cases are
the paths that have fooled it, and the names that must never become part of a
URL it fetches.

Run with `make gateway-test`.
"""

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "lib"), str(ROOT / "services" / "uma-pep")]
os.environ.update({
    "UMA_OWNER": "alice",
    "UMA_EXTRA_OWNERS": "carol",
    "UMA_PEP_SIGNING_KEY": str(Path(tempfile.mkdtemp(prefix="u4a-pep-")) / "key.pem"),
    "UMA_PEP_ORG_ISSUER": "https://org.example",
    "UMA_PEP_JOINT_TALLY": "https://tally.example",
    "UMA_PEP_JOINT_ACCOUNTS": "meridian-joint",
})

spec = importlib.util.spec_from_file_location("pep_app", ROOT / "services/uma-pep/app.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

PASSED = FAILED = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if ok:
        PASSED += 1
        print(f"ok   {name}")
    else:
        FAILED += 1
        print(f"FAIL {name}  {detail}")


def route(path: str) -> tuple[str, str]:
    return app.route_of(path)


print("\n== the paths the gateway serves ==")
for path, want in (
    ("/mcp", ("alice", "own")),
    ("/mcp/", ("alice", "own")),
    ("/mcp/alice", ("alice", "own")),
    ("/mcp/carol", ("carol", "own")),
    ("/mcp/shared/bob", ("bob", "shared")),
    ("/mcp/joint/meridian-joint", ("meridian-joint", "joint")),
):
    check(f"{path} is {want}", route(path) == want, str(route(path)))

print("\n== a suffix stays with the prefix the gateway routed on ==")
for path, want in (
    ("/mcp/carol/mcp", ("carol", "own")),
    ("/mcp/shared/bob/mcp", ("bob", "shared")),
    ("/mcp/joint/meridian-joint/mcp", ("meridian-joint", "joint")),
    ("/mcp/carol/mcp/shared/alice", ("carol", "own")),
    ("/mcp/carol?x=/mcp", ("carol", "own")),
):
    check(f"{path} is {want}", route(path) == want, str(route(path)))
check("/mcp/mcp/carol is not Carol's: the gateway sends it to the catch-all",
      route("/mcp/mcp/carol")[1] == "unknown", str(route("/mcp/mcp/carol")))

print("\n== nobody the gateway serves ==")
for path in ("/mcp/mallory", "/mcp/shared", "/mcp/joint", "/other", "/"):
    check(f"{path} is judged under nobody", route(path)[1] == "unknown", str(route(path)))

print("\n== names that would change a URL ==")
for path in ("/mcp/shared/a%2F..%2Fbob", "/mcp/shared/..", "/mcp/joint/a%2Fb",
             "/mcp/shared/" + "x" * 65):
    check(f"{path[:40]} is refused, not looked up", route(path)[1] == "unknown",
          str(route(path)))

print("\n== an owner with no listing here ==")
import asyncio  # noqa: E402

resp = asyncio.run(app.owner_resources_for("mallory", None))
check("is a 404, not the primary owner's listing", resp.status_code == 404,
      str(resp.status_code))

print("\n== her listing, and whose signature reads it ==")
import json  # noqa: E402
from unittest.mock import AsyncMock, patch  # noqa: E402

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from jwt.algorithms import OKPAlgorithm  # noqa: E402
from starlette.requests import Request  # noqa: E402
from uma4a_http_sig import sign  # noqa: E402

HER_AS, OTHER = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()


class Keys:
    """Alice's authority's published keys, as this resource's configuration
    names them."""
    async def get(self, refresh=False):
        return [json.loads(OKPAlgorithm.to_jwk(HER_AS.public_key()))]

    def may_refresh(self):
        return False


def listing(signer):
    hdrs = sign("GET", app.EXPECTED_AUTHORITY, "/owner-resources/alice", "", signer, "k")
    req = Request({"type": "http", "method": "GET", "path": "/owner-resources/alice",
                   "query_string": b"", "server": ("rs", 443), "scheme": "https",
                   "headers": [(k.lower().encode(), v.encode()) for k, v in hdrs.items()]})
    with patch.object(app, "authority_keys", lambda who: Keys()), \
            patch.object(app, "shared_enforcer", AsyncMock(return_value=None)), \
            patch.object(app, "joint_held_by", AsyncMock(return_value={})):
        return asyncio.run(app.owner_resources_for("alice", req))


check("her authority's signature reads her listing", listing(HER_AS).status_code == 200,
      str(listing(HER_AS).status_code))
check("a signature by any other key does not, whoever sent it",
      listing(OTHER).status_code == 401, str(listing(OTHER).status_code))

print(f"\n{PASSED} passed, {FAILED} failed")
sys.exit(1 if FAILED else 0)
