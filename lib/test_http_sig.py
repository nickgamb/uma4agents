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

must_fail("verifier that cannot resolve a covered component refuses",
          lambda: verify(**A, signature_input=h2["Signature-Input"],
                         signature=h2["Signature"], public_key=pub))

stripped = h["Signature-Input"].replace('"authorization" ', "").replace(' "authorization"', "")
must_fail("dropping a required component is rejected",
          lambda: verify(**A, signature_input=stripped,
                         signature=h["Signature"], public_key=pub))

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

must_fail("a tampered body-bound header is rejected",
          lambda: verify(method="POST", authority="gateway.uma.lab", path="/mcp",
                         authorization="PoP DIFFERENT",
                         signature_input=h["Signature-Input"],
                         signature=h["Signature"], public_key=pub))

if FAILED:
    print(f"\nhttp-sig: {PASSED} passed, {FAILED} failed")
    sys.exit(1)
print(f"\nhttp-sig: {PASSED} passed, 0 failed")
