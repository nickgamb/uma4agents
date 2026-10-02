"""An AAuth agent token, accepted as an agent's identity — in the shape
AAuth's current text defines, and in the shape earlier revisions did — and
every reason one is refused.

Mints agent tokens the way an agent provider does, including with the `aauth`
package Christian Posta's person server uses, and verifies them with the
module the authorization server uses, against a provider served from a dict.
Needs nothing running.

Run with `make aauth-test`.
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))

import jwt  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

import uma4a_aauth  # noqa: E402
import uma4a_jose  # noqa: E402

PASSED = FAILED = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if ok:
        PASSED += 1
        print(f"ok   {name}")
    else:
        FAILED += 1
        print(f"FAIL {name}  {detail}")


ISS = "https://ap.example"
AP = Ed25519PrivateKey.generate()
AGENT = Ed25519PrivateKey.generate()
DOCS: dict[str, dict] = {}
FETCHES: list[str] = []


def jwk(key, alg: str | None = "Ed25519", **extra) -> dict:
    out = {k: v for k, v in uma4a_jose.ed25519_jwk(key).items() if k != "alg"}
    return {**out, **({"alg": alg} if alg else {}), **extra}


def publish(issuer: str | None = ISS, keys: list[dict] | None = None) -> None:
    meta = {"jwks_uri": f"{ISS}/jwks.json"}
    if issuer is not None:
        meta["issuer"] = issuer
    DOCS[f"{ISS}/.well-known/aauth-agent.json"] = meta
    DOCS[f"{ISS}/jwks.json"] = {"keys": keys if keys is not None else [jwk(AP, kid="ap-1")]}


def fetch(url: str) -> dict:
    FETCHES.append(url)
    if url not in DOCS:
        raise LookupError(f"404 {url}")
    return DOCS[url]


def mint(key=AP, alg: str = "Ed25519", kid: str | None = "ap-1",
         typ: str = "aa-agent+jwt", drop: tuple[str, ...] = (), **over) -> str:
    now = int(time.time())
    claims = {"iss": ISS, "dwk": "aauth-agent.json", "sub": "aauth:planner@ap.example",
              "jti": "at-1", "iat": now, "exp": now + 3600,
              "cnf": {"jwk": jwk(AGENT, "Ed25519" if alg == "Ed25519" else None)}, **over}
    for name in drop:
        claims.pop(name, None)
    header = {"typ": typ, **({"kid": kid} if kid else {})}
    return jwt.encode(claims, key, algorithm=alg, headers=header)


def older(**over) -> str:
    """An agent token as the earlier revisions shaped it."""
    return mint(alg="EdDSA", **over)


def refused(token: str, tokens: uma4a_aauth.AgentTokens | None = None) -> str:
    try:
        (tokens or uma4a_aauth.AgentTokens(fetch, [ISS])).verify(token)
    except uma4a_aauth.Refused as exc:
        return str(exc)
    return ""


publish()

print("\n== the current shape (draft-hardt-oauth-aauth-protocol-10) ==")
claims = uma4a_aauth.AgentTokens(fetch, [ISS]).verify(mint())
check("is accepted, and says who the agent is",
      claims["sub"] == "aauth:planner@ap.example", str(claims))
check("and binds the key the agent signs with",
      claims["cnf"]["jwk"]["x"] == uma4a_jose.ed25519_jwk(AGENT)["x"])
for name in ("dwk", "jti", "iat"):
    check(f"an Ed25519 token without {name} is refused",
          "must carry" in refused(mint(drop=(name,))))
bare_cnf = {"jwk": jwk(AGENT, None)}
check("an Ed25519 token whose cnf.jwk names no algorithm is refused",
      "cnf.jwk must name" in refused(mint(cnf=bare_cnf)))
publish(keys=[jwk(AP, None, kid="ap-1")])
check("an Ed25519 token under a key that names no algorithm is refused",
      "must name 'Ed25519'" in refused(mint()))
publish(keys=[jwk(AP, "EdDSA", kid="ap-1")])
check("an Ed25519 token under a key that names EdDSA is refused",
      "names 'EdDSA' and the token 'Ed25519'" in refused(mint()))
publish()

print("\n== the earlier shape ==")
publish(keys=[jwk(AP, "EdDSA", kid="ap-1")])
check("an EdDSA token under a key naming EdDSA is accepted", refused(older()) == "")
publish(keys=[jwk(AP, None, kid="ap-1")])
check("and under a key that names no algorithm", refused(older()) == "")
check("without dwk, jti or iat, which earlier revisions did not all require",
      refused(older(drop=("dwk", "jti", "iat"))) == "")
publish(keys=[jwk(AP, "Ed25519", kid="ap-1")])
check("an EdDSA token under a key that names Ed25519 is refused",
      "names 'Ed25519' and the token 'EdDSA'" in refused(older()))
try:
    import aauth

    publish(keys=[{**aauth.public_key_to_jwk(AP.public_key()), "kid": "ap-1",
                   "alg": "EdDSA", "use": "sig"}])
    posta = aauth.create_agent_token(
        iss=ISS, sub="aauth:3f1c2e7a@ap.example",
        cnf_jwk=aauth.public_key_to_jwk(AGENT.public_key()),
        private_key=AP, kid="ap-1", ps="https://ps.example")
    check("a token minted by the aauth package Posta's person server uses is accepted",
          refused(posta) == "", refused(posta))
except ImportError:
    check("a token minted by the aauth package Posta's person server uses is accepted",
          False, "the aauth package is not installed")
publish()

print("\n== what neither shape allows ==")
check("another typ is refused", "typ must be" in refused(mint(typ="aa-auth+jwt")))
check("another algorithm is refused",
      "alg must be" in refused(jwt.encode({"iss": ISS}, "k" * 32, algorithm="HS256",
                                          headers={"typ": "aa-agent+jwt"})))
check("an http issuer is refused", "not an https issuer" in refused(mint(iss="http://ap.example")))
check("a dwk other than aauth-agent.json is refused",
      "dwk must be" in refused(mint(dwk="aauth-person.json")))
publish(issuer="https://elsewhere.example")
check("a metadata document naming another issuer is refused",
      "names 'https://elsewhere.example'" in refused(mint()))
publish(issuer=None, keys=[jwk(AP, "EdDSA", kid="ap-1")])
check("one naming none, as earlier providers' did, is not held against the token",
      refused(older()) == "")
publish()
check("a kid the issuer does not publish is refused",
      "publishes no key 'ap-2'" in refused(mint(kid="ap-2")))
publish(keys=[jwk(AP, "EdDSA")])
check("a token with no kid is verified against an issuer's only key",
      refused(older(kid=None)) == "")
publish(keys=[jwk(AP, "EdDSA"), jwk(Ed25519PrivateKey.generate(), "EdDSA")])
check("but not guessed among several", "names no kid" in refused(older(kid=None)))
publish(keys=[{**jwk(AP, "EdDSA", kid="ap-1"), "crv": "Ed448"}])
check("a key that is not an Ed25519 key is refused",
      "not an Ed25519 key" in refused(older()))
publish()
check("a signature by another key is refused",
      "did not verify" in refused(mint(key=Ed25519PrivateKey.generate())))
check("a token with no sub is refused", "did not verify" in refused(mint(drop=("sub",))))
check("an expired token is refused", "expired" in refused(mint(exp=int(time.time()) - 1)))
check("an aauth: subject under another provider's domain is refused",
      "not an agent of ap.example" in refused(mint(sub="aauth:planner@other.example")))
check("a malformed aauth: subject is refused",
      "not an AAuth agent identifier" in refused(mint(sub="aauth:planner")))
check("identifiers are compared exactly, so case is kept",
      refused(mint(sub="aauth:Planner@ap.example")) == "")
publish(keys=[jwk(AP, "EdDSA", kid="ap-1")])
check("a subject in another form is the issuer's to choose",
      refused(older(sub="delegate-7")) == "")
check("a token with no cnf.jwk is refused", "no cnf.jwk" in refused(older(drop=("cnf",))))
check("a cnf.jwk that is not an Ed25519 key is refused",
      "cnf.jwk" in refused(older(cnf={"jwk": {**jwk(AGENT, None), "crv": "Ed448"}})))
publish()

print("\n== a sub-agent ==")
child = uma4a_aauth.AgentTokens(fetch, [ISS]).verify(
    mint(sub="aauth:planner+search1@ap.example", parent_agent="aauth:planner@ap.example"))
check("parent_agent names the agent that spawned it, and is carried through",
      child.get("parent_agent") == "aauth:planner@ap.example")
check("a parent under another provider is refused",
      "not an agent of ap.example" in refused(mint(parent_agent="aauth:planner@other.example")))
check("an agent cannot name itself its parent",
      "own parent" in refused(mint(parent_agent="aauth:planner@ap.example")))

print("\n== how often the issuer is asked ==")
clock = [1000.0]
FETCHES.clear()
tokens = uma4a_aauth.AgentTokens(fetch, [ISS], clock=lambda: clock[0])
tokens.verify(mint())
tokens.verify(mint())
check("its keys are fetched once and then cached", len(FETCHES) == 2, str(FETCHES))
refused(mint(kid="ap-2"), tokens)
check("an unknown kid does not refetch inside a minute", len(FETCHES) == 2)
clock[0] += uma4a_aauth.REFETCH_FLOOR_S
DOCS[f"{ISS}/jwks.json"]["keys"].append(jwk(AP, kid="ap-2"))
check("and after a minute it does, which is how a rotation is noticed",
      refused(mint(kid="ap-2"), tokens) == "" and len(FETCHES) == 4)

print("\n== which issuers are believed ==")
FETCHES.clear()
check("an issuer the deployment did not name is refused, and never fetched",
      "not an agent-token issuer this server" in refused(
          mint(), uma4a_aauth.AgentTokens(fetch, ["https://other.example"]))
      and FETCHES == [], str(FETCHES))
check("and with no issuers named, none is believed",
      "not an agent-token issuer" in refused(mint(), uma4a_aauth.AgentTokens(fetch)))

print("\n== an issuer that cannot be read ==")
clock = [5000.0]
FETCHES.clear()
saved = dict(DOCS)
DOCS.clear()
tokens = uma4a_aauth.AgentTokens(fetch, [ISS], clock=lambda: clock[0])
first = refused(mint(), tokens)
refused(mint(), tokens)
refused(mint(), tokens)
check("is asked once, however many tokens name it inside a minute",
      "could not be read" in first and len(FETCHES) == 1, str(FETCHES))
check("and each refusal says why", "could not be read" in refused(mint(), tokens))
DOCS.update(saved)
clock[0] += uma4a_aauth.REFETCH_FLOOR_S
check("and once the minute is up it is asked again, and believed",
      refused(mint(), tokens) == "" and len(FETCHES) == 3, str(FETCHES))

print(f"\n{PASSED} passed, {FAILED} failed")
sys.exit(1 if FAILED else 0)
