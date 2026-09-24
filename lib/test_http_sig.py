"""Unit tests for the RFC 9421 profile.

The profile has to hold two properties at once: it must *require* the
components that make an RPT sender-constrained, and it must *tolerate* a
signer covering more — otherwise Web Bot Auth's `signature-agent` and this
profile cannot coexist on one request. The negative cases are the point.

    make sig-test
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from uma4a_http_sig import sign, verify, VerifyError

k = Ed25519PrivateKey.generate()
pub = k.public_key()
A = dict(method="POST", authority="gateway.uma.lab", path="/mcp",
         authorization="PoP abc")


PASSED = 0
FAILED = 0


def ok(label, fn):
    global PASSED, FAILED
    try:
        fn()
        PASSED += 1
        print("  OK   ", label)
    except Exception as e:
        FAILED += 1
        print("  FAIL ", label, "->", type(e).__name__, str(e)[:70])


def must_fail(label, fn):
    global PASSED, FAILED
    try:
        fn()
        FAILED += 1
        print("  FAIL ", label, "-> verified when it should not have")
    except VerifyError as e:
        PASSED += 1
        print("  OK   ", label, f"(rejected: {str(e)[:45]})")
    except Exception as e:
        FAILED += 1
        print("  FAIL ", label, "-> wrong error", type(e).__name__)


h = sign(**A, key=k, keyid="agent-1")
ok("baseline round trip",
   lambda: verify(**A, signature_input=h["Signature-Input"],
                  signature=h["Signature"], public_key=pub))

h2 = sign(**A, key=k, keyid="agent-1",
          signature_agent="https://ps.uma.lab", tag="web-bot-auth",
          expires_in=300)
print("  Signature-Agent header:", h2.get("Signature-Agent"))
print("  Signature-Input:", h2["Signature-Input"][:110])
ok("covers signature-agent, with tag + expires",
   lambda: verify(**A, signature_input=h2["Signature-Input"],
                  signature=h2["Signature"], public_key=pub,
                  signature_agent="https://ps.uma.lab"))

must_fail("a swapped Signature-Agent must not verify",
          lambda: verify(**A, signature_input=h2["Signature-Input"],
                         signature=h2["Signature"], public_key=pub,
                         signature_agent="https://evil.example"))

must_fail("a Signature-Agent the signature does not cover is refused",
          lambda: verify(**A, signature_input=h["Signature-Input"],
                         signature=h["Signature"], public_key=pub,
                         signature_agent="https://evil.example"))

must_fail("verifier that cannot resolve a covered component refuses",
          lambda: verify(**A, signature_input=h2["Signature-Input"],
                         signature=h2["Signature"], public_key=pub))

stripped = h["Signature-Input"].replace('"authorization" ', "").replace(' "authorization"', "")
must_fail("dropping a required component is rejected",
          lambda: verify(**A, signature_input=stripped,
                         signature=h["Signature"], public_key=pub))

_covered = ('"@method"', '"@authority"', '"@path"', '"authorization"')
_params = (f'({" ".join(_covered)});created={int(__import__("time").time())}'
           ';keyid="agent-1";alg="rsa-pss-sha512"')
_values = {'"@method"': A["method"], '"@authority"': A["authority"],
           '"@path"': A["path"], '"authorization"': A["authorization"]}
_lines = "\n".join([f"{c}: {_values[c]}" for c in _covered]
                   + [f'"@signature-params": {_params}'])
_sig = __import__("base64").b64encode(k.sign(_lines.encode())).decode()
must_fail("a signature claiming another algorithm is refused",
          lambda: verify(**A, signature_input=f"sig1={_params}",
                         signature=f"sig1=:{_sig}:", public_key=pub))

h3 = sign(**A, key=k, keyid="agent-1", expires_in=-10)
must_fail("an expired signature is rejected",
          lambda: verify(**A, signature_input=h3["Signature-Input"],
                         signature=h3["Signature"], public_key=pub))

# The freshness window, on its own. Distinct from `expires` above: that is a
# lifetime the *signer* set, and this is the ceiling the verifier imposes on
# how old a signature it will accept whatever the signer asked for. It is the
# only thing standing between a captured request and a replay of it, so it is
# worth a case where nothing else about the request is wrong — a valid key, a
# valid body, and the clock as the sole reason.
import time as _time                                             # noqa: E402
import uma4a_http_sig as _hs                                     # noqa: E402


def _signed_at(offset_s):
    real = _hs.time
    _hs.time = type("clock", (), {"time": staticmethod(lambda: real.time() + offset_s)})
    try:
        return sign(**A, key=k, keyid="agent-1")
    finally:
        _hs.time = real


ok("a signature made just now verifies",
   lambda: verify(**A, public_key=pub,
                  **{"signature_input": _signed_at(-5)["Signature-Input"],
                     "signature": _signed_at(-5)["Signature"]}))

_stale = _signed_at(-3600)
must_fail("a signature older than the freshness window is rejected",
          lambda: verify(**A, signature_input=_stale["Signature-Input"],
                         signature=_stale["Signature"], public_key=pub))

_future = _signed_at(3600)
must_fail("and one dated far in the future is too",
          lambda: verify(**A, signature_input=_future["Signature-Input"],
                         signature=_future["Signature"], public_key=pub))

# The authority is the verifier's, from configuration. A signature over the
# same request against a different authority is a signature over a different
# request, and a verifier that read the authority off the wire could be
# handed one that matches.
must_fail("a signature over another authority is rejected",
          lambda: verify(**{**A, "authority": "other.example"},
                         signature_input=h["Signature-Input"],
                         signature=h["Signature"], public_key=pub))

# Covering the body is two obligations: the header in the base, and the header
# recomputed from the bytes. A verifier told to require the digest refuses a
# request that carries none, or the signer that omits it escapes the check.
_body = b'{"decision": "approved"}'
hb = sign(**A, key=k, keyid="agent-1", body=_body)
ok("a body-bound signature verifies with its digest",
   lambda: verify(**A, signature_input=hb["Signature-Input"],
                  signature=hb["Signature"], public_key=pub, body=_body,
                  require_digest=True, digest_header=hb["Content-Digest"]))
must_fail("a body without its digest is refused where one is required",
          lambda: verify(**A, signature_input=h["Signature-Input"],
                         signature=h["Signature"], public_key=pub, body=_body,
                         require_digest=True, digest_header=None))

must_fail("another signature label is rejected",
          lambda: verify(**A, signature_input=h["Signature-Input"].replace("sig1=", "sig2=", 1),
                         signature=h["Signature"].replace("sig1=", "sig2=", 1),
                         public_key=pub))

must_fail("a tampered body-bound header is rejected",
          lambda: verify(method="POST", authority="gateway.uma.lab", path="/mcp",
                         authorization="PoP DIFFERENT",
                         signature_input=h["Signature-Input"],
                         signature=h["Signature"], public_key=pub))

# The owner's authority's keys, as a resource verifies its queries. A forced
# refetch is rate-limited so an unsigned request cannot make the resource call
# the authority on its behalf — but the limit is between forced refetches, so
# the first failure after a rotation always gets a fresh look.
import asyncio                                                   # noqa: E402
import types                                                     # noqa: E402

from uma4a_publish import AuthorityKeys                          # noqa: E402

_FETCHES: list = []


class _Client:                                   # the network, counted
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, timeout=None):
        _FETCHES.append(url)
        return types.SimpleNamespace(raise_for_status=lambda: None,
                                     json=lambda: {"keys": []})


sys.modules["httpx"] = types.SimpleNamespace(AsyncClient=_Client)
_keys = AuthorityKeys("https://as.example/jwks")
asyncio.run(_keys.get())                         # filled on schedule
asyncio.run(_keys.get(refresh=True))             # a rotation: looked at again


def _fetched(n):
    if len(_FETCHES) != n:
        raise VerifyError(f"{len(_FETCHES)} fetches")


ok("a signature that fails right after the cache filled still forces a fresh look",
   lambda: _fetched(2))
for _ in range(50):
    asyncio.run(_keys.get(refresh=True))         # a flood of bad signatures
ok("and a flood of bad signatures forces no more than that one", lambda: _fetched(2))

# An operator's key directory. A hit may come from cache; a miss is always
# looked at again, so a key the operator has just published is recognised at
# once rather than after the cache expires.
from uma4a_http_sig import KeyDirectories, jwk_thumbprint      # noqa: E402

_published = [pub_jwk_a := {"kty": "OKP", "crv": "Ed25519", "x": "A" * 43}]


def _dir_get(url, timeout=None, follow_redirects=None, verify=None):
    _FETCHES.append(url)
    return types.SimpleNamespace(raise_for_status=lambda: None,
                                 json=lambda: {"keys": list(_published)})


sys.modules["httpx"] = types.SimpleNamespace(get=_dir_get)
_FETCHES.clear()
_dirs = KeyDirectories()
_where = "https://operator.example/.well-known/http-message-signatures-directory"
_new = {"kty": "OKP", "crv": "Ed25519", "x": "B" * 43}
_dirs.publishes(_where, jwk_thumbprint(pub_jwk_a))
_dirs.publishes(_where, jwk_thumbprint(pub_jwk_a))
ok("a key the directory holds is answered from cache the second time",
   lambda: _fetched(1))
_published.append(_new)
ok("and a key it has just published is recognised at once, not after the TTL",
   lambda: _dirs.publishes(_where, jwk_thumbprint(_new))[0]
   or (_ for _ in ()).throw(VerifyError("not recognised")))
ok("a directory that is not https is not consulted",
   lambda: not _dirs.publishes("http://operator.example/d", jwk_thumbprint(_new))[0]
   or (_ for _ in ()).throw(VerifyError("consulted")))

if FAILED:
    print(f"\nhttp-sig: {PASSED} passed, {FAILED} failed")
    sys.exit(1)
print(f"\nhttp-sig: {PASSED} passed, 0 failed")
