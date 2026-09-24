"""uma4a_aauth — an AAuth agent token, accepted as an agent's identity.

AAuth is one of the ways an agent may say who it is. Its agent token is a JWT
an agent provider signs, binding an identifier to the key in `cnf`. This
module verifies one, and nothing more: none of AAuth's access modes, tokens or
flows are used here, only the credential.

It accepts the token as draft-hardt-oauth-aauth-protocol-10 defines it and as
the earlier revisions defined it, because agents built on either are in use.
The two differ in what they name, not in what they prove:

  current   `alg: Ed25519` in the header, on the issuer's key and on
            `cnf.jwk` (RFC 9864), and `dwk`, `jti` and `iat` required
  earlier   `alg: EdDSA`, keys that may name no algorithm, and `dwk`, `jti`
            and `iat` optional

Either way the key is an Ed25519 key, checked by its type and curve, and the
signature is verified with the algorithm that key names — never the one the
token asks for. Verification, in order:

  1. the header says `typ: aa-agent+jwt`, and an `alg` of `Ed25519` or `EdDSA`;
  2. `iss` is an https origin, and `dwk`, if present, is `aauth-agent.json`;
  3. the document at `{iss}/.well-known/aauth-agent.json`, if it names an
     `issuer`, names `iss` exactly;
  4. the key at its `jwks_uri` — the one with the header's `kid`, or with no
     `kid` the only one there — is an Ed25519 key, names the header's `alg`
     or no algorithm, and verifies the signature;
  5. `sub` and `exp` are present and `exp` is in the future; a `sub` in
     AAuth's `aauth:local@domain` form is under the issuer's own host;
  6. `cnf.jwk` is an Ed25519 key;
  7. `parent_agent`, where present, names another agent of the same issuer —
     AAuth's mark of a sub-agent.

Any failure raises `Refused` with the step that failed.
"""

from __future__ import annotations

import re
import threading
import time
from typing import Callable
from urllib.parse import urlsplit

import jwt
from jwt.algorithms import OKPAlgorithm

import uma4a_jose
from uma4a_jose import ED25519

AGENT_TYP = "aa-agent+jwt"
AGENT_DWK = "aauth-agent.json"
ALGS = (ED25519, "EdDSA")

# `aauth:local@domain`. The local part may carry `+`, which AAuth reserves for
# a sub-agent's discriminator; it is never parsed for decisions here.
_AGENT_ID = re.compile(r"aauth:([A-Za-z0-9_.+-]{1,255})@([a-z0-9.-]+)")

# AAuth: fetch an issuer's keys at most once a minute. What was fetched is
# kept for five minutes; a kid not in the cached set is the one case that asks
# again sooner — it is how an issuer's key rotation is noticed.
REFETCH_FLOOR_S = 60
CACHE_TTL_S = 300


class Refused(ValueError):
    pass


def issuer_origin(value: object) -> str:
    """An https issuer with a lowercase host, and no credentials, query or
    fragment. AAuth's current text narrows this to scheme and host; earlier
    issuers are not held to that."""
    if not isinstance(value, str):
        raise Refused("issuer is not a string")
    parts = urlsplit(value)
    if (parts.scheme != "https" or not parts.hostname or parts.query
            or parts.fragment or parts.username or parts.password
            or parts.netloc.split(":")[0] != parts.hostname):
        raise Refused(f"{value!r} is not an https issuer")
    return value.rstrip("/")


def agent_identifier(value: object, host: str) -> str:
    """A subject, held to AAuth's `aauth:local@domain` form when it uses it."""
    if not isinstance(value, str) or not value:
        raise Refused("the token names no subject")
    if value.startswith("aauth:"):
        match = _AGENT_ID.fullmatch(value)
        if not match:
            raise Refused(f"{value!r} is not an AAuth agent identifier")
        if match.group(2) != host:
            raise Refused(f"{value!r} is not an agent of {host}")
    return value


class AgentTokens:
    """Verifies agent tokens against the keys their issuers publish.

    `fetch(url)` returns a URL's parsed JSON body and raises on anything else;
    it is where TLS policy lives, so it is supplied rather than built here.
    """

    def __init__(self, fetch: Callable[[str], dict],
                 clock: Callable[[], float] = time.time):
        self._fetch = fetch
        self._clock = clock
        self._lock = threading.Lock()
        self._keys: dict[str, tuple[float, float, list]] = {}

    def _issuer_keys(self, iss: str, kid: str | None) -> list:
        now = self._clock()
        with self._lock:
            cached = self._keys.get(iss)
        if cached:
            fetched, expires, keys = cached
            known = kid is None or any(k.get("kid") == kid for k in keys)
            if (known and now < expires) or now - fetched < REFETCH_FLOOR_S:
                return keys
        try:
            meta = self._fetch(f"{iss}/.well-known/{AGENT_DWK}")
        except Exception as exc:
            raise Refused(f"the issuer's {AGENT_DWK} could not be read: {exc}")
        named = meta.get("issuer")
        if named is not None and str(named).rstrip("/") != iss:
            raise Refused(f"the issuer's {AGENT_DWK} names {named!r}, not {iss!r}")
        try:
            keys = [k for k in self._fetch(meta["jwks_uri"])["keys"]
                    if isinstance(k, dict)]
        except Exception as exc:
            raise Refused(f"the issuer's keys could not be read: {exc}")
        with self._lock:
            self._keys[iss] = (now, now + CACHE_TTL_S, keys)
        return keys

    def verify(self, token: str) -> dict:
        try:
            header = jwt.get_unverified_header(token)
            unverified = jwt.decode(token, options={"verify_signature": False})
        except jwt.InvalidTokenError as exc:
            raise Refused(f"not a JWT: {exc}")
        if header.get("typ") != AGENT_TYP:
            raise Refused(f"typ must be {AGENT_TYP!r}, not {header.get('typ')!r}")
        alg = header.get("alg")
        if alg not in ALGS:
            raise Refused(f"alg must be {ED25519!r} or 'EdDSA', not {alg!r}")
        kid = header.get("kid")
        iss = issuer_origin(unverified.get("iss"))
        if "dwk" in unverified and unverified["dwk"] != AGENT_DWK:
            raise Refused(f"dwk must be {AGENT_DWK!r}, not {unverified['dwk']!r}")

        keys = self._issuer_keys(iss, kid)
        chosen = ([k for k in keys if k.get("kid") == kid] if kid
                  else keys if len(keys) == 1 else [])
        if not chosen:
            raise Refused(f"{iss} publishes no key {kid!r}" if kid else
                          f"the token names no kid and {iss} publishes "
                          f"{len(keys)} keys")
        jwk = chosen[0]
        try:
            if "alg" in jwk and uma4a_jose.alg_of(jwk) != alg:
                raise ValueError(f"it names {jwk['alg']!r} and the token {alg!r}")
            uma4a_jose.alg_of({k: v for k, v in jwk.items() if k != "alg"})
            key = OKPAlgorithm.from_jwk({k: jwk[k] for k in ("kty", "crv", "x")})
        except (KeyError, ValueError, jwt.InvalidKeyError) as exc:
            raise Refused(f"{iss}'s key {kid!r}: {exc}")
        try:
            claims = jwt.decode(token, key, algorithms=[alg],
                                options={"require": ["sub", "exp"],
                                         "verify_aud": False, "verify_iat": False})
        except jwt.InvalidTokenError as exc:
            raise Refused(f"did not verify against {iss}'s key {kid!r}: {exc}")
        if alg == ED25519:
            # A token in the current text's algorithm is held to the rest of
            # that text's shape: its claims, and keys that name their algorithm.
            missing = [c for c in ("dwk", "jti", "iat") if c not in claims]
            if missing:
                raise Refused(f"an {ED25519} agent token must carry {', '.join(missing)}")
            if jwk.get("alg") != ED25519:
                raise Refused(f"{iss}'s key {kid!r} must name {ED25519!r}")
            if (claims.get("cnf") or {}).get("jwk", {}).get("alg") != ED25519:
                raise Refused(f"cnf.jwk must name {ED25519!r} in an {ED25519} agent token")

        host = urlsplit(iss).hostname
        agent_identifier(claims["sub"], host)
        cnf = claims.get("cnf")
        if not isinstance(cnf, dict) or not isinstance(cnf.get("jwk"), dict):
            raise Refused("no cnf.jwk binds the token to a key")
        try:
            uma4a_jose.alg_of(cnf["jwk"])
        except ValueError as exc:
            raise Refused(f"cnf.jwk: {exc}")
        if "parent_agent" in claims:
            agent_identifier(claims["parent_agent"], host)
            if claims["parent_agent"] == claims["sub"]:
                raise Refused("an agent cannot be its own parent")
        return claims
