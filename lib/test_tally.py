"""The tally's own code: what it issues, from the answers it collected.

The tally is the party the enforcement point does not trust, so most of what
keeps it honest is checked at the door (`make pep-test`). What is pinned here
is what an honest tally must do so that an honest grant passes that door:
a grant built from verdicts never outlives the first of them.

Run with `make tally-test`.
"""

import importlib.util
import os
import sys
import tempfile
import time
from pathlib import Path

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "lib"), str(ROOT / "services" / "joint-tally")]
os.environ["TALLY_SIGNING_KEY"] = str(Path(tempfile.mkdtemp(prefix="u4a-tally-")) / "k.pem")

spec = importlib.util.spec_from_file_location("tally_app", ROOT / "services/joint-tally/app.py")
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


HOLDER = Ed25519PrivateKey.generate()
AGENT = {"kty": "OKP", "crv": "Ed25519", "x": "A" * 43}


def verdict(lasts: int) -> str:
    return jwt.encode({"holder": "h", "effect": "allow", "exp": int(time.time()) + lasts},
                      HOLDER, algorithm="EdDSA")


def negotiation(verdicts: dict, agreed: int = 3600) -> dict:
    return {"family": "jnt_test", "account": "acct", "resource_id": "acct/read",
            "template": {"expires_in": 3600, "scope": ["read"]},
            "contract": {"expires_in": agreed, "scope": ["read"]},
            "contract_hash": "s256:x", "signer": AGENT,
            "signed": verdicts, "verdicts": {o: "allow" for o in verdicts}}


def issued_exp(rec: dict) -> int:
    token = app.issue(rec, {"holders": [], "rule": {}, "resources": []}, {})["access_token"]
    return jwt.decode(token, options={"verify_signature": False})["exp"]


print("\n== how long a grant built from verdicts lasts ==")
now = int(time.time())
exp = issued_exp(negotiation({"alice": verdict(3600), "carol": verdict(3600)}, agreed=900))
check("as long as the agreement, when every verdict outlasts it",
      abs(exp - (now + 900)) <= 2, f"{exp - now}")
exp = issued_exp(negotiation({"alice": verdict(3600), "carol": verdict(600)}))
check("and no longer than the first verdict it carries",
      exp <= now + 600 + 2, f"{exp - now}")

print(f"\n{PASSED} passed, {FAILED} failed")
sys.exit(1 if FAILED else 0)
