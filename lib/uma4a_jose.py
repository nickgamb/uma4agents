"""uma4a_jose — `Ed25519` as a JOSE algorithm, and choosing it from the key.

RFC 9864 registered `Ed25519` as the fully-specified replacement for the
polymorphic `EdDSA`, and AAuth's current text requires it: an agent token is
signed `Ed25519` and every key its issuer publishes says so. Earlier revisions
signed `EdDSA`, and tokens of both kinds are in use. PyJWT has no `Ed25519`
name yet. Importing this module registers one — PyJWT's own
EdDSA operation, refusing any key that is not an Ed25519 key, so the name
means what it says.

The rest of the stack still signs its own tokens `EdDSA`. What one signature
is verified with is decided by the key it is verified against, never by the
token's header: `alg_of` is that decision.
"""

from __future__ import annotations

import json

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from jwt.algorithms import OKPAlgorithm

ED25519 = "Ed25519"


class _Ed25519(OKPAlgorithm):
    def prepare_key(self, key):
        key = super().prepare_key(key)
        if not isinstance(key, (Ed25519PrivateKey, Ed25519PublicKey)):
            raise jwt.InvalidKeyError("Ed25519 is for Ed25519 keys only")
        return key


try:
    jwt.register_algorithm(ED25519, _Ed25519())
except ValueError:
    pass  # registered by an earlier import


def alg_of(jwk: dict) -> str:
    """The one algorithm a signature by this key may be verified with.

    A key that names its algorithm is held to it. A bare key that names none
    is U4A's pseudonymous agent, which has always signed `EdDSA`. Anything
    else — another algorithm, or a key type that disagrees with the one named
    — is refused, so a token cannot talk its verifier into a different
    operation than its key was published for.
    """
    alg = jwk.get("alg")
    if jwk.get("kty") != "OKP" or jwk.get("crv") != "Ed25519":
        raise ValueError("the key is not an Ed25519 key")
    if alg is None:
        return "EdDSA"
    if alg not in (ED25519, "EdDSA"):
        raise ValueError(f"the key names {alg!r}, which this server does not verify")
    return alg


def ed25519_jwk(key) -> dict:
    """The public JWK of an Ed25519 key, naming its algorithm."""
    public = key.public_key() if isinstance(key, Ed25519PrivateKey) else key
    return {**json.loads(OKPAlgorithm.to_jwk(public)), "alg": ED25519}
