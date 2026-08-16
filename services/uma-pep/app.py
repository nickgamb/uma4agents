"""uma-pep — the UMA enforcement core hosted as an HTTP ext_authz service.

The verdicts are not decided here. `lib/uma4a_pep.py` holds the enforcement
core in terms of request facts, so the same code can protect a resource from
in-process (see `mcp/alice-vault/uma_extension.py`). This module is the
gateway-shaped host for that role: it turns an ext_authz callback into
`AuthzFacts`, and a `Decision` back into an HTTP response — which is the one
thing that genuinely differs between hosts, since only a host with a status
line can answer beat 1 with `401 + WWW-Authenticate: UMA`.

What is specific to this host:

- Registering Alice's vault tool surfaces at her AS on startup, and re-pushing
  when the AS reports an unknown resource id (push mode's RS-side obligation).
- Publishing the resource's discovery layer: the RFC 9728 document, the AAuth
  R3 encoding of the same structural facts, `jwks`, and the protected
  owner-resources listing that only the owner's AS may query.
- Rendering verdicts as HTTP.
"""

import json
import logging
import os
import sys
import time

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI, Request, Response
from jwt.algorithms import OKPAlgorithm

from uma4a_http_sig import VerifyError, verify
from uma4a_pep import AuthzFacts, Enforcer, parse_mcp, s256

AS_PUBLIC = os.environ.get("UMA_AS_PUBLIC", "https://alice-as.uma.lab")
AS_INTERNAL = os.environ.get("UMA_AS_INTERNAL", "http://uma-as:9000")
# The gateway's standing as a resource server: client credentials it
# exchanges at the AS for a PAT (scope uma_protection) — the FedAuthz
# obligation, done as OAuth rather than a shared string.
RS_CLIENT_ID = os.environ.get("UMA_AS_RS_CLIENT_ID", "meridian-gateway")
RS_CLIENT_SECRET = os.environ.get("UMA_AS_RS_CLIENT_SECRET", "gateway-dev-secret")
REALM = os.environ.get("UMA_REALM", "alice-vault")
# Registration is declarative: this RS only *publishes* — public structure in
# the RFC 9728 document, owner-bound instances behind the protected
# owner-resources endpoint — and the AS comes and reads. Classic FedAuthz
# push registration is gone from this line; see `legacy/rreg-baseline`.
# The owner whose instances this (single-owner) gateway fronts.
OWNER = os.environ.get("UMA_OWNER", "alice")
PEP_KEY_PATH = os.environ.get("UMA_PEP_SIGNING_KEY", "/keys/uma-pep-ed25519.pem")
PEP_KID = "uma-pep-1"
# The authority Alice's vault is served under. Signature verification
# reconstructs the signed components from configuration rather than trusting
# forwarded headers (the ext_authz hop rewrites Host).
EXPECTED_AUTHORITY = os.environ.get("UMA_EXPECTED_AUTHORITY", "gateway.uma.lab")
# The base every published URL is built from. The scheme is configuration
# rather than a constant for the same reason the authority is: a resource
# server reachable over plain http — a personal deployment on a laptop, with
# no certificate authority in the picture — publishes http URLs, and an
# authorization server pulling from it has to be able to fetch what it reads.
# The deployed shape leaves this alone and stays https.
PUBLIC_SCHEME = os.environ.get("UMA_PEP_SCHEME", "https")
PUBLIC_BASE = f"{PUBLIC_SCHEME}://{EXPECTED_AUTHORITY}"
# Origins allowed to drive the gateway from a browser context. Agents are not
# browsers and send no Origin; the check only bites when one is present.
ALLOWED_ORIGINS = {
    o for o in os.environ.get(
        "UMA_ALLOWED_ORIGINS",
        f"https://{os.environ.get('UMA_EXPECTED_AUTHORITY', 'gateway.uma.lab')},"
        "https://portal.uma.lab",
    ).split(",") if o
}

# Alice's vault tool surface: tool -> (resource_id, scopes). This is what the
# gateway registers at her AS on startup.
TOOLS = {
    "get_positions": ("alice-vault/get_positions", ["positions:read"]),
    "get_transactions": ("alice-vault/get_transactions", ["transactions:read"]),
    "execute_trade": ("alice-vault/execute_trade", ["trades:execute"]),
}
SINGLE_USE_TOOLS = {"execute_trade"}
# Deny by default. An allow-list of open methods silently admits every method
# a future protocol revision invents — 2026-07-28 alone added tasks/*,
# server/discover and subscriptions/listen — so the protected set is named
# instead, and anything unrecognised is refused rather than forwarded.
PROTECTED_METHODS = {"tools/call"}
OPEN_METHODS = {
    "initialize", "notifications/initialized", "ping",
    "tools/list", "prompts/list", "resources/list", "resources/templates/list",
    "completion/complete", "logging/setLevel",
    "server/discover",          # 2026-07-28 replacement for initialize
}

log = logging.getLogger("uma-pep")
logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")

app = FastAPI(title="uma-pep")


def load_or_create_key(path: str) -> Ed25519PrivateKey:
    if os.path.exists(path):
        with open(path, "rb") as f:
            return serialization.load_pem_private_key(f.read(), password=None)
    key = Ed25519PrivateKey.generate()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
    return key


PEP_KEY = load_or_create_key(PEP_KEY_PATH)


def event(name: str, corr: str | None = None, **details) -> None:
    log.info(
        json.dumps(
            {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "event": name,
                "corr": corr,
                "actor": "uma-pep",
                "details": details,
            }
        )
    )


def deny(status: int, body: dict, headers: dict | None = None) -> Response:
    return Response(
        status_code=status,
        content=json.dumps(body),
        media_type="application/json",
        headers=headers or {},
    )


# The enforcement core, shared with the in-process extension.
ENFORCER = Enforcer(
    as_internal=AS_INTERNAL,
    as_public=AS_PUBLIC,
    client_id=RS_CLIENT_ID,
    client_secret=RS_CLIENT_SECRET,
    realm=REALM,
    tools=TOOLS,
    single_use_tools=SINGLE_USE_TOOLS,
    protected_methods=PROTECTED_METHODS,
    open_methods=OPEN_METHODS,
    expected_authority=EXPECTED_AUTHORITY,
    allowed_origins=ALLOWED_ORIGINS,
    resource_metadata_url=(
        f"{PUBLIC_BASE}/.well-known/oauth-protected-resource/mcp"),
    event=event,
)


@app.on_event("startup")
async def announce_registration() -> None:
    event("registration.declarative",
          note="publishing only; the AS pulls what it needs")


@app.api_route("/check{rest:path}", methods=["GET", "POST", "HEAD", "DELETE"])
async def check(request: Request, rest: str = "") -> Response:
    """agentgateway's ext_authz callback: HTTP facts in, HTTP verdict out.

    Everything that decides the verdict lives in lib/uma4a_pep.py, so the
    in-process extension reaches the same conclusions from the same code. All
    this adapter does is read the HTTP request and render a Decision — which
    for this host means a status line and, on a challenge, the UMA header.
    """
    original_path = rest or "/"
    body = await request.body()
    h = request.headers

    # The gateway buffers the body up to a configured ceiling and, past it,
    # forwards a prefix with this header set rather than refusing the call.
    # A cut-off JSON-RPC body does not parse, so the tool name disappears —
    # which is a bypass shape: pad a call past the ceiling and the
    # enforcement point can no longer see what is being invoked.
    #
    # Deny-by-default already catches it (an unparseable body yields no
    # method, and no method is not a protected method), but it reports
    # "unknown_method" and says nothing about a body cut in half. Fail closed
    # on purpose, and name the reason: the signal is right here in the
    # request.
    if h.get("x-envoy-auth-partial-body") == "true":
        event("access.denied", reason="truncated-body", path=original_path)
        return deny(413, {
            "error": "request_body_too_large",
            "error_description": "the call exceeded the gateway's authorization "
                                 "body limit, so the tool being invoked could "
                                 "not be determined",
        })

    method, tool, args = parse_mcp(body) if body else (None, None, None)

    # Nothing to authorize: no body, or a method that carries no invocation.
    if request.method != "POST" or (method is None and tool is None and not body):
        return Response(status_code=200)

    facts = AuthzFacts(
        tool=tool,
        args=args,
        mcp_method=method,
        http_method=request.method,
        path=original_path,
        authorization=h.get("authorization"),
        signature=h.get("signature", ""),
        signature_input=h.get("signature-input", ""),
        origin=h.get("origin"),
        header_mcp_method=h.get("mcp-method"),
        header_mcp_name=h.get("mcp-name"),
        protocol_version=h.get("mcp-protocol-version"),
        signature_agent=h.get("signature-agent"),
        traceparent=h.get("traceparent"),
    )
    d = await ENFORCER.authorize(facts)

    if d.outcome == "allow":
        return Response(status_code=200,
                        headers={"x-uma-contract": d.contract or ""})
    if d.outcome == "challenge":
        # Beat 1 at an HTTP hop: 401 plus the UMA challenge, naming the
        # metadata document so the client can corroborate as_uri (RFC 9728
        # 5.1) instead of trusting this header.
        return deny(d.status, {"error": d.error},
                    {"WWW-Authenticate": ENFORCER.www_authenticate(d)})
    body_out = {"error": d.error}
    if d.description:
        body_out["error_description"] = d.description
    return deny(d.status, body_out)


def prm_document() -> dict:
    """RFC 9728 Protected Resource Metadata — *structural* only. It says
    what shape the resource has (tools, scopes) and where authority lives
    (authorization_servers, the owner-resources query endpoint); it does
    not say whose instances sit behind it. Publishing which resources Alice
    owns at an unauthenticated well-known URI would be a privacy leak the
    old push registration never had — owner-bound ids live behind
    /owner-resources ("protected webfinger" for Alice's stuff)."""
    scopes = sorted({s for _, (rid, ss) in TOOLS.items() for s in ss})
    return {
        "resource": f"{PUBLIC_BASE}/mcp",
        "authorization_servers": [AS_PUBLIC],
        "jwks_uri": f"{PUBLIC_BASE}/jwks",
        "scopes_supported": scopes,
        "bearer_methods_supported": ["header"],
        "resource_signing_alg_values_supported": ["EdDSA"],
        "tool_surfaces": [
            {"tool": tool, "resource_scopes": ss}
            for tool, (rid, ss) in TOOLS.items()
        ],
        "owner_resources_endpoint": f"{PUBLIC_BASE}/owner-resources",
    }


@app.get("/.well-known/oauth-protected-resource")
@app.get("/.well-known/oauth-protected-resource/mcp")
async def protected_resource_metadata() -> dict:
    doc = prm_document()
    # RFC 9728 signed_metadata: the same claims as a JWT under the
    # resource's key (jwks_uri above), so a relayed or cached copy of this
    # document stays attributable to the resource that published it.
    doc["signed_metadata"] = jwt.encode(
        {**doc, "iss": doc["resource"], "iat": int(time.time())},
        PEP_KEY, algorithm="EdDSA",
        headers={"typ": "oauth-protected-resource+jwt", "kid": PEP_KID},
    )
    return doc


def r3_vocabulary() -> dict:
    """An AAuth Rich Resource Requests (R3) vocabulary describing this
    resource's operations in a format the agent already speaks (MCP), so a
    caller that knows only the hostname can learn the API. Content-addressed:
    the digest is over the canonical operation list, which gives the
    *universal type layer* (operations + their scopes) a stable identifier —
    the same facts, referenceable independent of any one owner."""
    operations = [
        {"tool": tool, "resource_scopes": ss}
        for tool, (rid, ss) in TOOLS.items()
    ]
    digest = s256(json.dumps(operations, sort_keys=True).encode())
    return {"format": "mcp", "operations": operations, "digest": digest}


def aauth_resource_document() -> dict:
    """The AAuth-binding encoding of the *same public structural layer* the
    PRM document carries — AAuth's `/.well-known/aauth-resource.json`. Same
    tool surfaces, expressed as an R3 vocabulary; `access_mode` names the
    four-party (federated) topology this gateway already runs (PS federates
    with the owner's AS). Crucially it points at the *same*
    owner_resources_endpoint: the protected instance layer ("protected
    webfinger") is binding-independent — only the public encoding changes."""
    return {
        "resource": f"{PUBLIC_BASE}/mcp",
        "access_mode": "four-party",
        "access_servers": [AS_PUBLIC],
        "jwks_uri": f"{PUBLIC_BASE}/jwks",
        "r3_vocabularies": [r3_vocabulary()],
        "owner_resources_endpoint": f"{PUBLIC_BASE}/owner-resources",
    }


@app.get("/.well-known/aauth-resource.json")
async def aauth_resource_metadata() -> dict:
    doc = aauth_resource_document()
    doc["signed_metadata"] = jwt.encode(
        {**doc, "iss": doc["resource"], "iat": int(time.time())},
        PEP_KEY, algorithm="EdDSA",
        headers={"typ": "aauth-resource+jwt", "kid": PEP_KID},
    )
    return doc


@app.get("/jwks")
async def pep_jwks() -> dict:
    jwk = json.loads(OKPAlgorithm.to_jwk(PEP_KEY.public_key()))
    jwk.update({"kid": PEP_KID, "use": "sig"})
    return {"keys": [jwk]}


_AS_KEYS_CACHE: dict = {"expires": 0.0, "keys": []}


async def as_verification_keys() -> list:
    if _AS_KEYS_CACHE["expires"] < time.time():
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{AS_INTERNAL}/jwks", timeout=5.0)
            r.raise_for_status()
        _AS_KEYS_CACHE.update(expires=time.time() + 300, keys=r.json()["keys"])
    return _AS_KEYS_CACHE["keys"]


@app.get("/owner-resources")
async def owner_resources(request: Request) -> Response:
    """The protected half of discovery — a "protected webfinger" for the
    owner's stuff. Serves the owner-bound resource instances only to a
    querier that proves possession of the owner's AS signing key (RFC 9421
    over @method/@authority/@path — the same message-signature mechanics
    the agent uses for proof-of-possession, pointed the other way). The
    trust was established at onboarding: this gateway holds a PAT from
    exactly that AS."""
    verified = False
    last_error = "no signature"
    for jwk_dict in await as_verification_keys():
        try:
            pub = OKPAlgorithm.from_jwk(json.dumps(jwk_dict))
            verify(
                method=request.method,
                authority=EXPECTED_AUTHORITY,
                path="/owner-resources",
                authorization="",
                signature_input=request.headers.get("signature-input", ""),
                signature=request.headers.get("signature", ""),
                public_key=pub,
            )
            verified = True
            break
        except VerifyError as exc:
            last_error = str(exc)
    if not verified:
        event("owner_resources.denied", reason=last_error)
        return deny(401, {"error": "invalid_signature",
                          "error_description": "this listing is served only to "
                          f"the owner's authorization server: {last_error}"})
    event("owner_resources.served", owner=OWNER, count=len(TOOLS))
    return Response(
        content=json.dumps({
            "owner": OWNER,
            "resource": f"{PUBLIC_BASE}/mcp",
            "resources": [
                {"_id": rid, "tool": tool, "resource_scopes": ss,
                 "name": f"Alice's vault: {tool}", "type": "mcp-tool"}
                for tool, (rid, ss) in TOOLS.items()
            ],
        }),
        media_type="application/json",
    )


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
