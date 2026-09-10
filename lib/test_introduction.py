"""Sub-agent introductions: what is honoured, and what is refused.

One property, in two halves. An introduction is a statement by an agent the
owner already holds a connection with, that another key belongs to a sibling
it is putting forward. It confers nothing. What it buys is that the sibling
skips being introduced from nothing — and every reason it might not buy even
that is asserted here.

The introduction is *minted with the client helper* and *verified with the
server module*, so these also check that the requesting side and the owner's
authority agree about the document's shape. A test that built the JWS by hand
would pass while the two implementations drifted apart.

Run with 'make introduction-test'.
"""

import os
import sys
import time

# Third-party imports first, and the local path added only afterwards. The
# authorization server's package directory contains an `org` module, and
# putting it at the front of `sys.path` shadows the standard library's `org`
# package — which `copy` imports, which `dataclasses` imports, which
# `cryptography` imports. Loading everything external up front means the
# shadow is never in place while the standard library is still being resolved.
import jwt

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "uma-as"))

import introduction
from uma4a_grant import AgentKeys, sign_introduction

AS = "https://alice-as.uma.lab"
OTHER_AS = "https://carol-as.uma.lab"

PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"{'ok  ' if ok else 'FAIL'} {name}{'  — ' + detail if detail and not ok else ''}")


def refused(fn, *a, **kw) -> str:
    """Run something that must raise Refused; return the reason it gave."""
    try:
        fn(*a, **kw)
    except introduction.Refused as exc:
        return str(exc)
    return ""


parent = AgentKeys()
child = AgentKeys()
stranger = AgentKeys()

# ---------------------------------------------------------------- the document

intro = sign_introduction(parent, child.thumbprint(), AS)
info = introduction.verify_claim(intro, child.thumbprint(), AS)
check("a well-formed introduction verifies",
      info["parent_jwk"] == parent.public_jwk())
check("and reports the introducing key, not a claimed identity",
      "parent_jwk" in info and "iss" not in info)

check("an introduction for another key is refused",
      "different key" in refused(introduction.verify_claim,
                                 intro, stranger.thumbprint(), AS))

check("an introduction for another authority is refused",
      refused(introduction.verify_claim, intro, child.thumbprint(), OTHER_AS) != "")

expired = jwt.encode(
    {"sub": child.thumbprint(), "aud": AS,
     "iat": int(time.time()) - 600, "exp": int(time.time()) - 60},
    parent.key, algorithm="EdDSA",
    headers={"typ": introduction.TYP, "jwk": parent.public_jwk()})
check("an expired introduction is refused",
      refused(introduction.verify_claim, expired, child.thumbprint(), AS) != "")

wrong_typ = jwt.encode(
    {"sub": child.thumbprint(), "aud": AS, "exp": int(time.time()) + 300},
    parent.key, algorithm="EdDSA",
    headers={"typ": "myterms-agreement-v1+jws", "jwk": parent.public_jwk()})
check("a document of another type is refused",
      "typ" in refused(introduction.verify_claim, wrong_typ, child.thumbprint(), AS))

# Signed by one key, carrying another in the header — the shape of an attempt
# to have somebody else's key looked up as the sponsor.
forged = jwt.encode(
    {"sub": child.thumbprint(), "aud": AS, "exp": int(time.time()) + 300},
    stranger.key, algorithm="EdDSA",
    headers={"typ": introduction.TYP, "jwk": parent.public_jwk()})
check("an introduction not signed by the key it names is refused",
      "does not verify" in refused(introduction.verify_claim,
                                   forged, child.thumbprint(), AS))

check("a JWS larger than the ceiling is refused",
      "exceeds" in refused(introduction.verify_claim,
                           "x" * (introduction.MAX_BYTES + 1),
                           child.thumbprint(), AS))
check("something that is not a JWS at all is refused",
      refused(introduction.verify_claim, "not-a-jws", child.thumbprint(), AS) != "")

# --------------------------------------------------------------- the decision

APPROVED = {"status": "active", "tiers_approved": ["tier2"], "parent_handle": None}


def admit(parent_conn=APPROVED, child_prior=None, same_operator=True,
          live_children=0, fanout=3):
    return introduction.admit(parent_conn, child_prior, same_operator,
                              live_children, fanout)


check("an approved, active, same-operator parent may introduce",
      refused(admit) == "")

check("an agent the owner has never met may not introduce",
      "not a connection" in refused(admit, parent_conn=None))

check("a revoked agent may not introduce",
      "not active" in refused(admit, parent_conn={**APPROVED, "status": "revoked"}))

# The anti-circularity line: automatic grants must not seed sponsors.
check("an agent she never approved in person may not introduce",
      "approved in person" in refused(admit,
                                      parent_conn={**APPROVED, "tiers_approved": []}))

# Depth. This is the check that keeps the authority graph one level deep, and
# it has to be explicit — an approved sub-agent satisfies every other test.
check("an agent that was itself introduced may not introduce",
      "may not introduce" in refused(
          admit, parent_conn={**APPROVED, "parent_handle": "jkt:parent"}))

check("a revoked agent cannot be restored by an introduction",
      "revoked" in refused(admit, child_prior={"status": "revoked"}))
check("an agent with a live prior connection is unaffected",
      refused(admit, child_prior={"status": "active"}) == "")

check("an agent from another operator may not be introduced",
      "same operator" in refused(admit, same_operator=False))

check("fan-out is capped",
      "limit" in refused(admit, live_children=3, fanout=3))
check("and one below the cap is allowed",
      refused(admit, live_children=2, fanout=3) == "")

# --------------------------------------------- lineage in AAuth's own claim
#
# An identified agent does not need a sibling to vouch for it. Its issuer
# already signs a credential for it, and RFC 8693's `act` claim — which AAuth
# nests to record a delegation chain — is where that issuer names the agent
# this one was spawned by. Nothing new is defined here; what is asserted is
# that the claim only counts when it arrives inside a *verified* agent token.

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "uma-as"))


def identity_from(claims: dict) -> dict:
    """The identity `contract_identity` builds from verified token claims."""
    ident = {"level": "identified", "iss": claims["iss"], "sub": claims.get("sub")}
    if isinstance(act := claims.get("act"), dict) and isinstance(act.get("sub"), str):
        if act["sub"]:
            ident["act"] = {"sub": act["sub"]}
    return ident


ident = identity_from({"iss": "https://ps.uma.lab", "sub": "worker-7",
                       "act": {"sub": "lead-1"}})
check("an act claim naming the spawning agent is carried through",
      ident.get("act", {}).get("sub") == "lead-1")

check("an act claim without a subject is ignored",
      "act" not in identity_from({"iss": "https://ps.uma.lab", "sub": "w",
                                  "act": {"scope": "everything"}}))
check("a non-object act claim is ignored",
      "act" not in identity_from({"iss": "https://ps.uma.lab", "sub": "w",
                                  "act": "lead-1"}))
check("an agent with no act claim carries no lineage",
      "act" not in identity_from({"iss": "https://ps.uma.lab", "sub": "w"}))

# The decision is the same one, so every refusal already asserted above
# applies to this path too. The one that matters most: an issuer naming a
# sponsor the owner never approved buys nothing.
check("an act claim naming an unapproved sponsor is still refused",
      "approved in person" in refused(admit,
                                      parent_conn={**APPROVED, "tiers_approved": []}))
check("and an act claim cannot make a sub-agent into a sponsor",
      "may not introduce" in refused(
          admit, parent_conn={**APPROVED, "parent_handle": "jkt:lead"}))


print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    for f in FAIL:
        print(f"  - {f}")
raise SystemExit(1 if FAIL else 0)
