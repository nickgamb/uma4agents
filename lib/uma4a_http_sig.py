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
import hashlib
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

# The components this profile *requires*. A signer may cover more — Web Bot
# Auth adds "signature-agent" — and a verifier must accept that rather than
# demanding an exact list, or the two conventions cannot coexist on one
# request. Requiring a minimum is the security property; requiring an exact
# set was only ever an implementation shortcut.
REQUIRED_COMPONENTS = ('"@method"', '"@authority"', '"@path"', '"authorization"')
LABEL = "sig1"


def content_digest(body: bytes) -> str:
    """RFC 9530 Content-Digest over a request body.

    A signature that covers the method, the authority and the path says who is
    asking and what they are asking of. It says nothing about the bytes. That
    is adequate for a GET and unsafe for anything that carries a decision in
    its body: without this, an intermediary can leave the signature untouched
    and change what the request says.
    """
    return "sha-256=:" + base64.b64encode(hashlib.sha256(body).digest()).decode() + ":"


def _params_str(covered: tuple[str, ...], created: int, keyid: str,
                expires: int | None = None, nonce: str | None = None,
                tag: str | None = None) -> str:
    s = f'({" ".join(covered)});created={created}'
    if expires is not None:
        s += f";expires={expires}"
    s += f';keyid="{keyid}";alg="ed25519"'
    if nonce is not None:
        s += f';nonce="{nonce}"'
    if tag is not None:
        s += f';tag="{tag}"'
    return s


def _base(covered: tuple[str, ...], values: dict[str, str], params: str) -> bytes:
    """RFC 9421 signature base: the covered components in order, then the
    params line verbatim — on verify the params string is echoed exactly as
    received, since re-serializing it would change the bytes that were signed.
    """
    lines = [f"{c}: {values[c]}" for c in covered]
    lines.append(f'"@signature-params": {params}')
    return "\n".join(lines).encode()


def _values(method: str, authority: str, path: str, authorization: str,
            signature_agent: str | None = None,
            digest: str | None = None) -> dict[str, str]:
    v = {
        '"@method"': method.upper(),
        '"@authority"': authority,
        '"@path"': path,
        '"authorization"': authorization,
    }
    if signature_agent is not None:
        v['"signature-agent"'] = signature_agent
    if digest is not None:
        v['"content-digest"'] = digest
    return v


def sign(method: str, authority: str, path: str, authorization: str,
         key: Ed25519PrivateKey, keyid: str,
         signature_agent: str | None = None,
         expires_in: int | None = None,
         nonce: str | None = None,
         tag: str | None = None,
         body: bytes | None = None) -> dict[str, str]:
    """Returns the Signature-Input and Signature headers for the request.

    Passing `signature_agent` covers a Web Bot Auth `Signature-Agent` header
    (the URL of the directory the verifying side can fetch this key from) and
    emits the header alongside the signature.

    Passing `body` covers an RFC 9530 `Content-Digest` over it and emits that
    header too. Any request that carries meaning in its body should pass it;
    the verifier can then refuse a request whose bytes were changed after
    signing.
    """
    created = int(time.time())
    covered = REQUIRED_COMPONENTS
    if signature_agent is not None:
        covered = covered + ('"signature-agent"',)
    digest = content_digest(body) if body is not None else None
    if digest is not None:
        covered = covered + ('"content-digest"',)
    params = _params_str(covered, created, keyid,
                         expires=created + expires_in if expires_in else None,
                         nonce=nonce, tag=tag)
    values = _values(method, authority, path, authorization, signature_agent,
                     digest)
    sig = key.sign(_base(covered, values, params))
    headers = {
        "Signature-Input": f"{LABEL}={params}",
        "Signature": f"{LABEL}=:{base64.b64encode(sig).decode()}:",
    }
    if signature_agent is not None:
        headers["Signature-Agent"] = signature_agent
    if digest is not None:
        headers["Content-Digest"] = digest
    return headers


class VerifyError(Exception):
    pass


def verify(method: str, authority: str, path: str, authorization: str,
           signature_input: str, signature: str, public_key: Ed25519PublicKey,
           max_age_s: int = 60, signature_agent: str | None = None,
           body: bytes | None = None, require_digest: bool = False,
           digest_header: str | None = None) -> str:
    """Verifies the signature headers against the reconstructed request.

    Accepts any covered-component list that *includes* REQUIRED_COMPONENTS, so
    a signer may also cover `signature-agent` (Web Bot Auth) without this
    profile rejecting it. Returns the keyid; raises VerifyError on any
    mismatch.
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
    # An explicit expiry is the signer's own bound and is honoured whenever
    # present, independently of the verifier's freshness window.
    if "expires=" in params:
        try:
            expires = int(params.split("expires=", 1)[1].split(";", 1)[0])
        except ValueError as exc:
            raise VerifyError(f"malformed expires: {exc}") from exc
        if time.time() > expires:
            raise VerifyError("signature expired")

    covered_str = params.split(");", 1)[0].lstrip("(")
    covered = tuple(c for c in covered_str.split(" ") if c)
    missing = [c for c in REQUIRED_COMPONENTS if c not in covered]
    if missing:
        raise VerifyError(f"signature does not cover {', '.join(missing)}")

    # The body, if the caller cares about it.
    #
    # Two separate obligations, and conflating them is the classic way to get
    # this wrong. RFC 9421 builds the base from the *header field value*, so
    # that is what goes into the base — recomputing it from the body instead
    # would verify our own clients and reject a conforming third-party signer
    # whose encoding differs. And RFC 9530 says nothing about whether the
    # header is true, so the header is separately checked against the bytes
    # that actually arrived. A verifier that does only the first trusts an
    # attacker's arithmetic; one that does only the second is not verifying
    # what was signed.
    #
    # `require_digest` is how an endpoint whose body carries meaning refuses a
    # signature that does not reach it. Covering it optionally is not coverage:
    # a signer that omits it still produces a signature that verifies.
    digest = None
    if require_digest and '"content-digest"' not in covered:
        raise VerifyError("signature does not cover content-digest")
    if '"content-digest"' in covered:
        if not digest_header:
            raise VerifyError("signature covers content-digest but none was sent")
        if body is None:
            raise VerifyError("signature covers content-digest but no body was read")
        if digest_header.strip() != content_digest(body):
            raise VerifyError("content-digest does not match the body")
        digest = digest_header.strip()

    values = _values(method, authority, path, authorization, signature_agent,
                     digest)
    unknown = [c for c in covered if c not in values]
    if unknown:
        raise VerifyError(f"cannot reconstruct covered components: {', '.join(unknown)}")

    try:
        sig_label, sig_val = signature.split("=", 1)
        if sig_label != LABEL or not (sig_val.startswith(":") and sig_val.endswith(":")):
            raise VerifyError("malformed Signature header")
        raw = base64.b64decode(sig_val[1:-1])
    except Exception as exc:
        raise VerifyError(f"malformed Signature header: {exc}") from exc

    try:
        public_key.verify(raw, _base(covered, values, params))
    except Exception as exc:
        raise VerifyError("signature verification failed") from exc
    return keyid
