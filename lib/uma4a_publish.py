"""What a resource server publishes about itself, in one implementation.

Discovery has two audiences and three documents:

  RFC 9728 metadata      public, structural — the tools, the scopes, which
                         authorization servers speak for this resource, and
                         the key its metadata is signed under
  AAuth resource meta    the same structural facts in the other binding's
                         encoding
  owner-resources        protected — the owner-bound instances, served only
                         to a querier that proves possession of the owner's
                         authorization server key

Whoever hosts the enforcement obligations also hosts these, and there are two
such hosts in this lab: the ext_authz service ahead of the resource, and the
resource itself when it protects itself. That is the same "one core, two
hosts" split `uma4a_pep.py` exists for, applied to publication — so these
builders live beside it rather than inside either host.

None of this depends on how the request arrived, so the functions take plain
values and return plain dicts. The host adds routes.
"""

from __future__ import annotations

import json
import time


def prm_document(public_base: str, as_public: str,
                 tools: dict[str, tuple[str, list[str]]],
                 leaf: str = "mcp") -> dict:
    """RFC 9728 Protected Resource Metadata — *structural* only.

    It says what shape the resource has and where authority lives. It does not
    say whose instances sit behind it: publishing which resources a named
    person owns at an unauthenticated well-known URI would be a privacy leak
    the older push registration never had. Owner-bound ids live behind the
    protected listing below.

    `leaf` is the path this document is served for. RFC 9728 §3.3 has the
    client refuse a document whose `resource` is not the resource it is
    accessing, so a resource reachable at both /mcp and /mcp/<owner> has to
    answer each with its own identifier rather than one canonical answer.
    """
    scopes = sorted({s for _, (rid, ss) in tools.items() for s in ss})
    return {
        "resource": f"{public_base}/{leaf}",
        "authorization_servers": [as_public],
        "jwks_uri": f"{public_base}/jwks",
        "scopes_supported": scopes,
        "bearer_methods_supported": ["header"],
        "resource_signing_alg_values_supported": ["EdDSA"],
        "tool_surfaces": [
            {"tool": tool, "resource_scopes": ss}
            for tool, (rid, ss) in tools.items()
        ],
        "owner_resources_endpoint": f"{public_base}/owner-resources",
    }


def sign_metadata(doc: dict, key, kid: str) -> dict:
    """Add RFC 9728 `signed_metadata`.

    The same claims as a JWT under the resource's own key, so a relayed or
    cached copy of the document stays attributable to the resource that
    published it rather than to whoever handed it over.
    """
    import jwt

    signed = dict(doc)
    signed["signed_metadata"] = jwt.encode(
        {**doc, "iss": doc["resource"], "iat": int(time.time())},
        key, algorithm="EdDSA",
        headers={"typ": "oauth-protected-resource+jwt", "kid": kid},
    )
    return signed


def aauth_document(public_base: str, as_public: str,
                   tools: dict[str, tuple[str, list[str]]]) -> dict:
    """The AAuth binding's encoding of the same structural facts.

    `access_mode` names the topology — four-party, the federated shape where
    the resource, the owner's authority and the requesting side are all
    different parties. The R3 vocabulary is content-addressed, so the
    operation list has a stable id independent of any owner.
    """
    import base64
    import hashlib

    ops = [
        {"operation": tool, "resource_scopes": ss}
        for tool, (rid, ss) in sorted(tools.items())
    ]
    digest = base64.urlsafe_b64encode(
        hashlib.sha256(
            json.dumps(ops, separators=(",", ":"), sort_keys=True).encode()
        ).digest()
    ).rstrip(b"=").decode()
    return {
        "resource": f"{public_base}/mcp",
        "access_mode": "four-party",
        "authorization_servers": [as_public],
        "jwks_uri": f"{public_base}/jwks",
        "r3_vocabularies": [
            {"id": f"s256:{digest}", "operations": ops},
        ],
        "owner_resources_endpoint": f"{public_base}/owner-resources",
    }


def owner_resources_document(public_base: str, owner: str,
                             tools: dict[str, tuple[str, list[str]]]) -> dict:
    """The protected half: whose instances sit behind this resource."""
    return {
        "owner": owner,
        "resource": f"{public_base}/mcp",
        "resources": [
            {"_id": rid, "tool": tool, "resource_scopes": ss,
             "name": f"Alice's vault: {tool}", "type": "mcp-tool"}
            for tool, (rid, ss) in tools.items()
        ],
    }


def verify_owner_as_query(method: str, authority: str, path: str,
                          signature_input: str, signature: str,
                          as_jwks: list) -> str | None:
    """Is this query really from the owner's authorization server?

    RFC 9421 over the same covered components the agent signs, verified
    against the AS's published keys. Returns None when it verifies, or the
    reason it did not.
    """
    import json as _json

    from jwt.algorithms import OKPAlgorithm

    from uma4a_http_sig import VerifyError
    from uma4a_http_sig import verify as verify_sig

    last = "no signature"
    for jwk_dict in as_jwks:
        try:
            verify_sig(
                method=method,
                authority=authority,
                path=path,
                authorization="",
                signature_input=signature_input,
                signature=signature,
                public_key=OKPAlgorithm.from_jwk(_json.dumps(jwk_dict)),
            )
            return None
        except VerifyError as exc:
            last = str(exc)
    return last
