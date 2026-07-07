"""Minimal RFC 9421 HTTP message signatures for the uma4agents lab.

One implementation shared by the agent-shim (signing) and uma-pep
(verification), so the two ends cannot drift. Profile:

  covered components: "@method" "@authority" "@path" "authorization"
  params: created, keyid, alg="ed25519"

Covering the `authorization` header binds the signature to the presented RPT,
which is what makes the RPT proof-of-possession rather than bearer: replaying
the token without the agent's private key fails verification, and re-binding
the signature to a different token changes the base string.

Interop note (for FINDINGS): this is a spec-shaped subset, sufficient for the
lab's closed loop. Cross-implementation verification against the upstream
AAuth Go verifier is binding-document work.
"""

import base64
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

COMPONENTS = ('"@method"', '"@authority"', '"@path"', '"authorization"')
LABEL = "sig1"


def _signature_params(created: int, keyid: str) -> str:
    return f'({" ".join(COMPONENTS)});created={created};keyid="{keyid}";alg="ed25519"'


def _base(method: str, authority: str, path: str, authorization: str,
          created: int, keyid: str) -> bytes:
    lines = [
        f'"@method": {method.upper()}',
        f'"@authority": {authority}',
        f'"@path": {path}',
        f'"authorization": {authorization}',
        f'"@signature-params": {_signature_params(created, keyid)}',
    ]
    return "\n".join(lines).encode()


def sign(method: str, authority: str, path: str, authorization: str,
         key: Ed25519PrivateKey, keyid: str) -> dict[str, str]:
    """Returns the Signature-Input and Signature headers for the request."""
    created = int(time.time())
    sig = key.sign(_base(method, authority, path, authorization, created, keyid))
    return {
        "Signature-Input": f"{LABEL}={_signature_params(created, keyid)}",
        "Signature": f"{LABEL}=:{base64.b64encode(sig).decode()}:",
    }


class VerifyError(Exception):
    pass


def verify(method: str, authority: str, path: str, authorization: str,
           signature_input: str, signature: str, public_key: Ed25519PublicKey,
           max_age_s: int = 60) -> str:
    """Verifies the signature headers against the reconstructed request.

    Returns the keyid. Raises VerifyError on any mismatch.
    """
    try:
        label, params = signature_input.split("=", 1)
        if label != LABEL:
            raise VerifyError(f"unexpected signature label {label!r}")
        created = int(params.split("created=", 1)[1].split(";", 1)[0])
        keyid = params.split('keyid="', 1)[1].split('"', 1)[0]
    except (IndexError, ValueError) as exc:
        raise VerifyError(f"malformed Signature-Input: {exc}") from exc

    if abs(time.time() - created) > max_age_s:
        raise VerifyError("signature outside the freshness window")

    covered = params.split(");", 1)[0].lstrip("(")
    if covered != " ".join(COMPONENTS):
        raise VerifyError(f"unexpected covered components: {covered}")

    try:
        sig_label, sig_val = signature.split("=", 1)
        if sig_label != LABEL or not (sig_val.startswith(":") and sig_val.endswith(":")):
            raise VerifyError("malformed Signature header")
        raw = base64.b64decode(sig_val[1:-1])
    except Exception as exc:
        raise VerifyError(f"malformed Signature header: {exc}") from exc

    try:
        public_key.verify(raw, _base(method, authority, path, authorization, created, keyid))
    except Exception as exc:
        raise VerifyError("signature verification failed") from exc
    return keyid
