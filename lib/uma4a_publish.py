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

`tools` everywhere maps a key to `(resource_id, scopes)`. A host that serves
more than one kind of resource may qualify the key — `shared:get_book`,
`joint:acct:get_balance` — and the operation it names is the last segment.
"""

from __future__ import annotations

import json
import time


def _operation(key: str) -> str:
    return key.rsplit(":", 1)[-1]


def _declared(consequence: dict[str, str] | None, key: str) -> dict:
    """The operation's declared class, where the resource has declared one.
    An absent member is "undeclared", which is not the same claim as "nothing
    to put back" and must not be read as one."""
    cls = (consequence or {}).get(_operation(key))
    return {"consequence": cls} if cls else {}


def prm_document(public_base: str, as_public: str,
                 tools: dict[str, tuple[str, list[str]]],
                 leaf: str = "mcp",
                 consequence: dict[str, str] | None = None,
                 owner_resources_path: str = "/owner-resources") -> dict:
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

    `as_public` is per document, not per host: two owners of one resource
    server may name two different authorities, and this is the document an
    agent reads to learn which one governs what it was just refused.
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
            {"tool": _operation(key), "resource_scopes": ss, **_declared(consequence, key)}
            for key, (rid, ss) in tools.items()
        ],
        "owner_resources_endpoint": f"{public_base}{owner_resources_path}",
    }


def sign_metadata(doc: dict, key, kid: str,
                  typ: str = "oauth-protected-resource+jwt") -> dict:
    """Add `signed_metadata`: the same claims as a JWT under the resource's
    own key, so a relayed or cached copy of the document stays attributable to
    the resource that published it rather than to whoever handed it over.
    RFC 9728 for the protected-resource document; the AAuth binding's
    resource document takes the same member with its own `typ`.
    """
    import jwt

    signed = dict(doc)
    signed["signed_metadata"] = jwt.encode(
        {**doc, "iss": doc["resource"], "iat": int(time.time())},
        key, algorithm="EdDSA", headers={"typ": typ, "kid": kid},
    )
    return signed


def aauth_document(public_base: str, as_public: str,
                   tools: dict[str, tuple[str, list[str]]],
                   consequence: dict[str, str] | None = None) -> dict:
    """The AAuth binding's encoding of the same structural facts, as that
    binding's draft defines it. Sign it with `typ="aauth-resource+jwt"`.

    `access_mode` names the topology — four-party, the federated shape where
    the resource, the owner's authority and the requesting side are all
    different parties. The vocabulary is content-addressed: the digest is over
    the operation list, canonicalized as RFC 8785 would for these values, so
    the operation surface has an identifier no owner's instances appear in —
    and a resource that re-declares an operation gets a new one, which is the
    content-addressing working rather than a break.
    """
    import base64
    import hashlib

    ops = [{"tool": _operation(key), "resource_scopes": ss, **_declared(consequence, key)}
           for key, (rid, ss) in sorted(tools.items())]
    canonical = json.dumps(ops, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False).encode()
    digest = base64.urlsafe_b64encode(hashlib.sha256(canonical).digest())
    return {
        "resource": f"{public_base}/mcp",
        "access_mode": "four-party",
        "access_servers": [as_public],
        "jwks_uri": f"{public_base}/jwks",
        "r3_vocabularies": [{"format": "mcp", "operations": ops,
                             "digest": "s256:" + digest.rstrip(b"=").decode()}],
        "owner_resources_endpoint": f"{public_base}/owner-resources",
    }


def owner_resources_document(public_base: str, owner: str,
                             tools: dict[str, tuple[str, list[str]]],
                             consequence: dict[str, str] | None = None,
                             leaf: str = "mcp",
                             name=None) -> dict:
    """The protected half: whose instances sit behind this resource.

    The declared class rides here as well as in the public document, because
    this listing is what the owner's authorization server pulls into its
    registry — and the registry is what her policy reads. Carrying it only in
    the public document would leave her authority knowing the shape of the
    resource and nothing about what its operations cost.

    `name(key, resource_id)` is what she is shown for each; by default, the
    operation on her vault.
    """
    name = name or (lambda key, rid: f"{owner.title()}'s vault: {_operation(key)}")
    return {
        "owner": owner,
        "resource": f"{public_base}/{leaf}",
        "resources": [
            {"_id": rid, "tool": _operation(key), "resource_scopes": ss,
             "type": "mcp-tool", "name": name(key, rid), **_declared(consequence, key)}
            for key, (rid, ss) in tools.items()
        ],
    }


class AuthorityKeys:
    """One authorization server's published keys, as a resource verifies its
    queries against them.

    Cached for `ttl_s`. A signature that fails against the cached set may have
    been made with a key published since, which is what rotation looks like
    from here, so a failure may force a refetch — but not within
    `min_refresh_s` of the last forced one. Otherwise every unsigned request
    to a public route would be one request to the authority, sent on the
    caller's behalf. The floor is between forced refetches only: the first
    failure after a rotation always gets a fresh look, however recently the
    cache was filled on schedule. It is short because a replicated authority
    rotates by rolling restart, and a refetch that lands on a replica still
    publishing only the old key must be able to look again within seconds.
    """

    def __init__(self, jwks_url: str, ttl_s: float = 300, min_refresh_s: float = 5):
        self.jwks_url, self.ttl_s, self.min_refresh_s = jwks_url, ttl_s, min_refresh_s
        self._keys: list = []
        self._expires = self._forced = 0.0

    def may_refresh(self) -> bool:
        return time.time() - self._forced >= self.min_refresh_s

    async def get(self, refresh: bool = False) -> list:
        forced = refresh and self.may_refresh()
        if forced:
            self._forced = time.time()
        if forced or time.time() >= self._expires:
            import httpx

            async with httpx.AsyncClient() as client:
                r = await client.get(self.jwks_url, timeout=5.0)
                r.raise_for_status()
            self._keys = r.json()["keys"]
            self._expires = time.time() + self.ttl_s
        return self._keys


async def verify_owner_as_query(method: str, authority: str, path: str,
                                signature_input: str, signature: str,
                                keys: AuthorityKeys) -> str | None:
    """Is this query really from the owner's authorization server?

    RFC 9421 over the same covered components the agent signs, verified
    against the authority's published keys. Returns None when it verifies, or
    the reason it did not — including that the keys could not be read, which
    is a refusal like any other rather than an error.
    """
    from jwt.algorithms import OKPAlgorithm

    from uma4a_http_sig import VerifyError
    from uma4a_http_sig import verify as verify_sig

    if not signature_input or not signature:
        return "no signature"
    last = "no signature"
    for refresh in (False, True):
        if refresh and not keys.may_refresh():
            break
        try:
            jwks = await keys.get(refresh=refresh)
        except Exception as exc:                        # noqa: BLE001
            return f"the authorization server's keys could not be read ({type(exc).__name__})"
        for jwk_dict in jwks:
            try:
                verify_sig(method=method, authority=authority, path=path,
                           authorization="", signature_input=signature_input,
                           signature=signature,
                           public_key=OKPAlgorithm.from_jwk(json.dumps(jwk_dict)))
                return None
            except VerifyError as exc:
                last = str(exc)
    return last
