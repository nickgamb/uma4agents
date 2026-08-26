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
from fastapi.responses import JSONResponse
from jwt.algorithms import OKPAlgorithm

from uma4a_http_sig import VerifyError, verify
from uma4a_pep import (MANDATE_TTL_S, AuthzFacts, Enforcer, parse_mcp,
                       s256)

AS_PUBLIC = os.environ.get("UMA_AS_PUBLIC", "https://alice-as.uma.lab")
AS_INTERNAL = os.environ.get("UMA_AS_INTERNAL", "http://uma-as:9000")
# The gateway's standing as a resource server: client credentials it
# exchanges at the AS for a PAT (scope uma_protection) — the FedAuthz
# obligation, done as OAuth rather than a shared string.
RS_CLIENT_ID = os.environ.get("UMA_AS_RS_CLIENT_ID", "meridian-gateway")
RS_CLIENT_SECRET = os.environ.get("UMA_AS_RS_CLIENT_SECRET", "gateway-dev-secret")
# What an owner sees in her registry when this gateway introduces itself.
RS_DISPLAY_NAME = os.environ.get("UMA_PEP_RS_NAME", "Meridian Wealth API gateway")
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
# Owners besides the primary one that this gateway fronts, each at its own
# path. A resource server holding many people's accounts holds a distinct
# protected resource for each: `/mcp` is Alice's, `/mcp/carol` is Carol's,
# and RFC 9728 metadata hangs off each separately — which is what will let one
# owner's challenge name a different authorization server from the next.
EXTRA_OWNERS = [o for o in os.environ.get("UMA_EXTRA_OWNERS", "").split(",") if o]

# Which authority governs which owner — the resource server's side of BYOAS.
#
# FedAuthz assumes one: the resource server is a registered client of *the*
# authorization server. A resource server holding many people's accounts has
# no such thing, because the choice of authority is the owner's and she may
# not have chosen the operator's. So it is a map, defaulting to the operator's
# AS for anyone who has not named one.
OWNER_AUTHORITIES = json.loads(os.environ.get("UMA_OWNER_AUTHORITIES", "{}"))

# The shared secrets this resource server was provisioned with, per owner.
# An authority stood up alongside this gateway is in here; an authority that
# is the owner's own is not, and cannot be — nobody was there to configure
# both ends. Those are introduced at runtime instead: see Enforcer.establish.
RS_SECRETS = json.loads(os.environ.get("UMA_PEP_RS_SECRETS", "null") or "null")
if RS_SECRETS is None:
    RS_SECRETS = {OWNER: RS_CLIENT_SECRET}

# The organization above the owners this gateway fronts, when the firm
# running it knows of one.
#
# Configured on this side rather than discovered from an owner's authority,
# and that is the entire point of it being here. An owner may name any
# authorization server she likes; the resource still belongs to the
# organization, so the check that the organization's ceiling was applied has
# to come from somewhere she does not control. Unset, none of this exists and
# the enforcement point behaves exactly as it did.
ORG_ISSUER = os.environ.get("UMA_PEP_ORG_ISSUER", "")
ORG_INTERNAL = os.environ.get("UMA_PEP_ORG_INTERNAL", "") or ORG_ISSUER
ORG_TOKEN = os.environ.get("UMA_PEP_ORG_TOKEN", "")
# The organization's own resources, and the path its members reach them by.
#
# `/mcp/shared/<member>` is one resource with many administrators: the same
# process, the same resource ids, and a different authorization server
# depending on which member is named. That is the whole of shared ownership
# on this side — the resource belongs to the organization, and each member
# administers access to it under her own authority.
SHARED_PREFIX = os.environ.get("UMA_PEP_SHARED_PREFIX", "mcp/shared")
SHARED_NAMESPACE = os.environ.get("UMA_PEP_SHARED_NAMESPACE", "northwind-vault")
SHARED_RS_NAME = os.environ.get("UMA_PEP_SHARED_RS_NAME",
                                "Meridian Wealth shared-book gateway")

# A jointly held account: one resource, several owners of equal standing, and
# an authority that is nobody's. `/mcp/joint/<account>` reaches it, and the
# party at the other end of the challenge is the tally rather than any
# owner's authorization server — which is why this needs no per-owner
# enforcer and no membership lookup. Who is entitled to a say is in the
# mandate, and the grant is checked against it here.
JOINT_PREFIX = os.environ.get("UMA_PEP_JOINT_PREFIX", "mcp/joint")
JOINT_TALLY = os.environ.get("UMA_PEP_JOINT_TALLY", "")
JOINT_TALLY_INTERNAL = os.environ.get("UMA_PEP_JOINT_TALLY_INTERNAL", "") or JOINT_TALLY
JOINT_SECRET = os.environ.get("UMA_PEP_JOINT_SECRET", "")
JOINT_ACCOUNTS = [a for a in os.environ.get("UMA_PEP_JOINT_ACCOUNTS", "").split(",") if a]
JOINT_RS_NAME = os.environ.get("UMA_PEP_JOINT_RS_NAME",
                               "Meridian Wealth joint-account gateway")


def authority_for(owner: str) -> tuple[str, str]:
    """(public, internal) for the authority that governs this owner."""
    a = OWNER_AUTHORITIES.get(owner) or {}
    return a.get("public", AS_PUBLIC), a.get("internal", AS_INTERNAL)


ALL_OWNERS = [OWNER, *EXTRA_OWNERS]


def tools_for(owner: str) -> dict:
    """The same tool surface, in that owner's namespace."""
    if owner == OWNER:
        return TOOLS
    return {tool: (rid.replace("alice-vault/", f"{owner}-vault/", 1), ss)
            for tool, (rid, ss) in TOOLS.items()}


def shared_tools(grants) -> dict:
    """The organization's tool surface, narrowed to what this member's role
    grants her.

    Narrowed here rather than only refused later, because this table is what
    the published listing is built from — and a listing that advertised the
    firm's trade endpoint to an analyst would have her write terms over
    something she was never given.
    """
    from uma4a_org import claims_match

    return {tool: (f"{SHARED_NAMESPACE}/{tool}", ss)
            for tool, (_, ss) in TOOLS.items()
            if claims_match(f"{SHARED_NAMESPACE}/{tool}", grants)}


def route_of(path: str) -> tuple[str, str]:
    """(name, kind) for a request path, where kind is own|shared|joint.

    On an unauthenticated tool call the path is the only thing that can say
    which authority governs, and the three kinds are three different answers
    to that. `own` is an owner's own authorization server. `shared` is a
    resource the organization owns, administered by the member named — one
    path per person, because each of them administers it under her own
    authority. `joint` is one resource with several owners of equal standing,
    and there the path names the *account* rather than a person: no single
    holder's authority governs it, which is the whole difference.
    """
    tail = path.rstrip("/").rsplit("/mcp", 1)[-1].strip("/")
    shared_leaf = SHARED_PREFIX.rsplit("/", 1)[-1]
    joint_leaf = JOINT_PREFIX.rsplit("/", 1)[-1]
    if tail.startswith(f"{shared_leaf}/"):
        return tail.split("/", 1)[1], "shared"
    if tail.startswith(f"{joint_leaf}/"):
        return tail.split("/", 1)[1], "joint"
    return (tail if tail in ALL_OWNERS else OWNER), "own"


def owner_for_path(path: str) -> str:
    return route_of(path)[0]


def joint_tools(account: str) -> dict:
    """The tool surface over one jointly held account.

    The account is the namespace. Two accounts held by different people are
    two sets of resources, and sharing a namespace between them would make
    "which mandate covers this request" ambiguous at the one place it has to
    be exact.
    """
    return {tool: (f"{account}/{tool}", ss) for tool, (_, ss) in TOOLS.items()}
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


def _enforcer_for(owner: str) -> Enforcer:
    """One per owner. Nothing is shared between them — not the PAT, not the
    tool namespace, and (from here on) not necessarily the authorization
    server either."""
    leaf = f"mcp/{owner}"
    as_public, as_internal = authority_for(owner)
    secret = RS_SECRETS.get(owner, "")
    return Enforcer(
        owner=owner,
        as_internal=as_internal,
        as_public=as_public,
        # Which identity this resource server has here follows from whether
        # anyone provisioned the pair. With a secret it is the name it was
        # given; without one it is its own origin, which is the only thing
        # about itself an authority can check without being told anything
        # first.
        client_id=RS_CLIENT_ID if secret else PUBLIC_BASE,
        client_secret=secret,
        signing_key=None if secret else PEP_KEY,
        key_id=PEP_KID,
        resource_uri=f"{PUBLIC_BASE}/{leaf}",
        rs_name=RS_DISPLAY_NAME,
        realm=REALM,
        tools=tools_for(owner),
        single_use_tools=SINGLE_USE_TOOLS,
        protected_methods=PROTECTED_METHODS,
        open_methods=OPEN_METHODS,
        expected_authority=EXPECTED_AUTHORITY,
        allowed_origins=ALLOWED_ORIGINS,
        resource_metadata_url=(
            f"{PUBLIC_BASE}/.well-known/oauth-protected-resource/{leaf}"),
        org_issuer=ORG_ISSUER,
        org_internal=ORG_INTERNAL,
        org_token=ORG_TOKEN,
        event=event,
    )


# The enforcement core, shared with the in-process extension.
ENFORCERS = {o: _enforcer_for(o) for o in [OWNER, *EXTRA_OWNERS]}
ENFORCER = ENFORCERS[OWNER]

# One per member the organization has shared its book with. Built on demand
# rather than at startup, because membership is not a deployment fact: someone
# joins from her own portal at eleven o'clock and this has to be able to
# enforce for her at one minute past.
SHARED: dict[str, Enforcer] = {}


def _shared_enforcer_for(owner: str) -> Enforcer:
    as_public, as_internal = authority_for(owner)
    leaf = f"{SHARED_PREFIX}/{owner}"
    base = ENFORCERS.get(owner) or ENFORCER
    return Enforcer(
        owner=owner,
        as_internal=as_internal,
        as_public=as_public,
        # The same client of her authority as the surface protecting her own
        # vault, deliberately. It is the same gateway, holding the same PAT,
        # under the same relationship she already authorized — a second
        # registration would ask her to consent again to a party she has
        # already consented to, and (since a resource server is identified by
        # its origin) the two records would be the same record fighting over
        # one resource URI.
        #
        # What she can withdraw separately is the *membership*, which is the
        # thing that actually granted anything.
        client_id=base.client_id,
        client_secret=base.client_secret,
        signing_key=base.signing_key,
        key_id=PEP_KID,
        resource_uri=f"{PUBLIC_BASE}/{leaf}",
        rs_name=SHARED_RS_NAME,
        realm=REALM,
        # Filled in from her membership before every use: what she may reach
        # follows from the role the organization gave her, and that changes
        # without anything here restarting.
        tools={},
        single_use_tools=SINGLE_USE_TOOLS,
        protected_methods=PROTECTED_METHODS,
        open_methods=OPEN_METHODS,
        expected_authority=EXPECTED_AUTHORITY,
        allowed_origins=ALLOWED_ORIGINS,
        resource_metadata_url=(
            f"{PUBLIC_BASE}/.well-known/oauth-protected-resource/{leaf}"),
        org_issuer=ORG_ISSUER,
        org_internal=ORG_INTERNAL,
        org_token=ORG_TOKEN,
        event=event,
    )


_MANDATES: dict[str, tuple[float, dict]] = {}


async def mandate_of(account: str) -> dict | None:
    """The mandate for one jointly held account, from the tally that publishes
    it. Cached briefly: it names who is entitled to a say, and a holder
    leaving should stop being listed here in seconds rather than at a
    restart."""
    if not JOINT_TALLY_INTERNAL:
        return None
    cached = _MANDATES.get(account)
    if cached and cached[0] > time.time():
        return cached[1]
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{JOINT_TALLY_INTERNAL}/mandate/{account}")
            r.raise_for_status()
            doc = r.json()
    except httpx.HTTPError as exc:
        event("mandate.unreachable", account=account, error=str(exc)[:160])
        return cached[1] if cached else None
    _MANDATES[account] = (time.time() + MANDATE_TTL_S, doc)
    return doc


async def joint_held_by(owner: str) -> dict[str, dict]:
    """The jointly held accounts this owner is a holder of, with their tools.

    Used to put those resources in the listing her authorization server
    reads, which is how they come to exist at her authority at all — the same
    route the organization's shared resources take. Without it she has
    nothing to write terms over, and a holder with no terms is a holder who
    has consented to nothing.
    """
    out = {}
    for account in JOINT_ACCOUNTS:
        doc = await mandate_of(account)
        if doc and any(h.get("owner") == owner for h in doc.get("holders") or []):
            out[account] = joint_tools(account)
    return out


JOINT: dict[str, Enforcer] = {}


def joint_enforcer(account: str) -> Enforcer | None:
    """One per jointly held account, pointed at the tally rather than at any
    owner.

    Everything else about it is an ordinary enforcement point, and that is
    the useful part: the tally speaks the same authorization-server surface,
    so nothing here needs to know that the party it is negotiating with owns
    nothing. What it does know — because it is named in configuration rather
    than read off a token — is which tally it will accept a grant from.
    """
    if not JOINT_TALLY or (JOINT_ACCOUNTS and account not in JOINT_ACCOUNTS):
        return None
    if account not in JOINT:
        leaf = f"{JOINT_PREFIX}/{account}"
        JOINT[account] = Enforcer(
            owner=account,
            as_internal=JOINT_TALLY_INTERNAL,
            as_public=JOINT_TALLY,
            client_id=RS_CLIENT_ID,
            client_secret=JOINT_SECRET,
            key_id=PEP_KID,
            resource_uri=f"{PUBLIC_BASE}/{leaf}",
            rs_name=JOINT_RS_NAME,
            # The protection space is the account, not the primary owner's
            # vault. A challenge from a jointly held resource that announced
            # `realm="alice-vault"` would be naming one holder as the party
            # behind a resource that is equally the other's.
            realm=account,
            tools=joint_tools(account),
            single_use_tools=SINGLE_USE_TOOLS,
            protected_methods=PROTECTED_METHODS,
            open_methods=OPEN_METHODS,
            expected_authority=EXPECTED_AUTHORITY,
            allowed_origins=ALLOWED_ORIGINS,
            resource_metadata_url=(
                f"{PUBLIC_BASE}/.well-known/oauth-protected-resource/{leaf}"),
            joint_issuer=JOINT_TALLY,
            event=event,
        )
    return JOINT[account]


async def shared_enforcer(owner: str, fresh: bool = False) -> Enforcer | None:
    """The enforcer for the organization's book as administered by `owner`,
    or None if the organization has not shared it with her.

    The tool surface is re-derived from her membership on every use. That is
    the mechanism by which an administrator changing her role in the console
    changes what this gateway will serve her a minute later, with nothing
    deployed and nothing restarted.
    """
    if not ORG_ISSUER:
        return None
    enforcer = SHARED.get(owner)
    if enforcer is None:
        enforcer = SHARED[owner] = _shared_enforcer_for(owner)
    doc = await enforcer.membership(fresh=fresh)
    if not doc.get("member"):
        return None
    enforcer.tools = shared_tools(doc.get("grants") or [])
    return enforcer


_ORG_DISCOVERY: tuple[float, dict] = (0.0, {})
# How long this may serve a cached description of the organization. Only ever
# affects the wording of a refusal, never a decision — but a charter that has
# just started or stopped federating identity should be reflected in what an
# agent is told within a sensible time, and a checker has to be able to read
# the same number rather than guess it.
ORG_DISCOVERY_TTL_S = float(os.environ.get("UMA_PEP_ORG_DISCOVERY_TTL_S", "120"))


async def org_discovery() -> dict:
    """The organization's public description of itself, cached.

    Read for one purpose: to say something useful in a refusal. None of it
    decides anything here — the sharing decision above is unchanged, and a
    discovery document that failed to load only costs a less helpful message.
    """
    global _ORG_DISCOVERY
    if not ORG_ISSUER:
        return {}
    age, doc = _ORG_DISCOVERY
    if doc and age > time.time():
        return doc
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(f"{ORG_INTERNAL.rstrip('/')}/.well-known/u4a-organization")
            r.raise_for_status()
            doc = r.json()
    except Exception:                                           # noqa: BLE001
        return {}
    _ORG_DISCOVERY = (time.time() + ORG_DISCOVERY_TTL_S, doc)
    return doc


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
    owner, kind = route_of(original_path)
    if kind == "joint":
        enforcer = joint_enforcer(owner)
        if enforcer is None:
            event("access.denied", reason="no-mandate", account=owner,
                  path=original_path)
            return deny(404, {"error": "no_mandate",
                              "error_description": "this gateway serves no "
                              "jointly held account by that name"})
    elif kind == "shared":
        enforcer = await shared_enforcer(owner)
        if enforcer is None:
            # Not a member, or the organization stopped sharing. Not a
            # challenge: there is no authority to negotiate with about a
            # resource nobody has shared, and sending an agent to one would
            # have it argue with a server that has never heard of this.
            event("access.denied", reason="not-shared", owner=owner,
                  path=original_path)
            # Still not a challenge, for the reason above. But a refusal that
            # names the organization and says how membership is come by is the
            # difference between a dead end and something the person acting
            # for can actually do — and none of it is privileged: the
            # organization publishes all of it.
            doc = await org_discovery()
            org_name = (doc.get("organization") or {}).get("name")
            idp = doc.get("identity_provider") or {}
            body = {"error": "not_shared",
                    "error_description":
                        (f"this resource belongs to {org_name} and is not "
                         f"shared with that member" if org_name else
                         "this resource is not shared with that member")}
            if org_name:
                body["organization"] = {"name": org_name,
                                        "issuer": doc.get("issuer")}
            if idp.get("enrol"):
                body["how_to_join"] = (
                    f"{org_name} federates identity to {idp['issuer']}. "
                    f"Whoever this authority belongs to can enrol from their "
                    f"own portal by signing in there — no enrolment code.")
            return deny(403, body)
    else:
        enforcer = ENFORCERS.get(owner, ENFORCER)
    d = await enforcer.authorize(facts)

    if d.outcome == "allow":
        return Response(status_code=200,
                        headers={"x-uma-contract": d.contract or ""})
    if d.outcome == "challenge":
        # Beat 1 at an HTTP hop: 401 plus the UMA challenge, naming the
        # metadata document so the client can corroborate as_uri (RFC 9728
        # 5.1) instead of trusting this header.
        return deny(d.status, {"error": d.error},
                    {"WWW-Authenticate": enforcer.www_authenticate(d)})
    body_out = {"error": d.error}
    if d.description:
        body_out["error_description"] = d.description
    return deny(d.status, body_out)


def prm_document(owner: str = None, leaf: str = None, enforcer=None,
                 tools: dict = None, owner_resources_tail: str = None) -> dict:
    """RFC 9728 Protected Resource Metadata — *structural* only. It says
    what shape the resource has (tools, scopes) and where authority lives
    (authorization_servers, the owner-resources query endpoint); it does
    not say whose instances sit behind it. Publishing which resources an
    owner has at an unauthenticated well-known URI would be a privacy leak
    the old push registration never had — owner-bound ids live behind
    /owner-resources ("protected webfinger" for her stuff).

    `leaf` is the path this document is *served for*, and it is separate from
    the owner on purpose. RFC 9728 §3.3 has the client refuse a document
    whose `resource` is not the resource it is accessing, and `lib/
    uma4a_grant.py` implements that refusal. So the alias at /mcp has to
    claim /mcp — naming the owner's canonical path there would hand every
    client at the alias a document it is required to reject, which is what
    it did until `make shim-test` said so.
    """
    owner = owner or OWNER
    tools = tools if tools is not None else tools_for(owner)
    leaf = leaf or f"mcp/{owner}"
    tail = owner_resources_tail or f"/{owner}"
    enforcer = enforcer or ENFORCERS.get(owner)
    scopes = sorted({s for _, (rid, ss) in tools.items() for s in ss})
    return {
        "resource": f"{PUBLIC_BASE}/{leaf}",
        # Per owner, because this is the document an agent reads to find out
        # whose authority governs what it just got refused by. Two owners of
        # the same resource server can name two different authorization
        # servers, and this is where that becomes visible.
        "authorization_servers": [enforcer.as_public if enforcer else AS_PUBLIC],
        "jwks_uri": f"{PUBLIC_BASE}/jwks",
        "scopes_supported": scopes,
        "bearer_methods_supported": ["header"],
        "resource_signing_alg_values_supported": ["EdDSA"],
        "tool_surfaces": [
            {"tool": tool, "resource_scopes": ss}
            for tool, (rid, ss) in tools.items()
        ],
        "owner_resources_endpoint": f"{PUBLIC_BASE}/owner-resources{tail}",
    }


@app.get("/.well-known/oauth-protected-resource/mcp/shared/{owner}")
async def shared_resource_metadata(owner: str) -> Response:
    """The organization's book, as a resource administered by one member.

    Its `authorization_servers` names *her* authority, which is the whole
    point: the resource is Northwind's, and the party who decides whether an
    agent may touch it on her behalf is her. A second member reaches the same
    process at her own path and that document names a different authority.

    404 when the organization has not shared it with her — publishing a
    document for a resource nobody has been given would send an agent to
    negotiate with an authority that has never heard of it.
    """
    enforcer = await shared_enforcer(owner, fresh=True)
    if enforcer is None:
        return JSONResponse({"error": "no such resource"}, status_code=404)
    # One listing, the owner's. These resources are hers to administer even
    # though they are not hers to own, and her authority reads everything it
    # protects for her from one place.
    doc = prm_document(owner, f"{SHARED_PREFIX}/{owner}", enforcer=enforcer,
                       tools=enforcer.tools)
    return JSONResponse(_sign_prm(doc))


@app.get("/.well-known/oauth-protected-resource/mcp/joint/{account}")
async def joint_resource_metadata(account: str) -> Response:
    """A jointly held account, as a protected resource.

    Its `authorization_servers` names the **tally**, and that is the only
    document in this gateway of which that is true. Every other resource here
    points an agent at some owner's authority; this one points it at a party
    that owns nothing and decides nothing, because no single holder's
    authority governs a resource all of them hold.
    """
    enforcer = joint_enforcer(account)
    if enforcer is None:
        return JSONResponse({"error": "no such resource"}, status_code=404)
    doc = prm_document(account, f"{JOINT_PREFIX}/{account}", enforcer=enforcer,
                       tools=enforcer.tools)
    return JSONResponse(_sign_prm(doc))


@app.get("/.well-known/oauth-protected-resource/mcp/{owner}")
async def protected_resource_metadata_for(owner: str) -> Response:
    """One owner's resource, at her own path.

    An owner this resource server does not serve gets a 404 rather than the
    primary owner's document. Answering for somebody who is not here would
    publish a document claiming a resource nobody governs, and an agent that
    followed it would negotiate with an authority that has never heard of the
    resource it named.
    """
    if owner not in ALL_OWNERS:
        return JSONResponse({"error": "no such resource"}, status_code=404)
    return JSONResponse(_signed_prm(owner, f"mcp/{owner}"))


@app.get("/.well-known/oauth-protected-resource")
@app.get("/.well-known/oauth-protected-resource/mcp")
async def protected_resource_metadata() -> dict:
    """The alias, for a client configured against the bare /mcp path.

    Self-references /mcp, because that is the resource being accessed. It is
    the primary owner's resource reached by a second name, not an ownerless
    one: the authority it names is hers.
    """
    return _signed_prm(OWNER, "mcp")


def _sign_prm(doc: dict) -> dict:
    doc["signed_metadata"] = jwt.encode(
        {**doc, "iss": doc["resource"], "iat": int(time.time())},
        PEP_KEY, algorithm="EdDSA",
        headers={"typ": "oauth-protected-resource+jwt", "kid": PEP_KID},
    )
    return doc


def _signed_prm(owner: str, leaf: str) -> dict:
    doc = prm_document(owner, leaf)
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


# Per authority, not per resource server. The owner-resources listing is
# served only to the authority that governs that owner, and with BYOAS that is
# a different key per owner — Carol's server signs with Carol's key, which is
# not in Alice's JWKS and never will be. A single cache here would authorise
# one authority to read every owner's listing, which is the exact confusion
# this whole partition exists to prevent.
_AS_KEYS_CACHE: dict[str, dict] = {}


async def as_verification_keys(owner: str = None) -> list:
    _, as_internal = authority_for(owner or OWNER)
    entry = _AS_KEYS_CACHE.setdefault(as_internal, {"expires": 0.0, "keys": []})
    if entry["expires"] < time.time():
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{as_internal}/jwks", timeout=5.0)
            r.raise_for_status()
        entry.update(expires=time.time() + 300, keys=r.json()["keys"])
    return entry["keys"]


async def _require_as_signature(request: Request, who: str,
                                path: str) -> Response | None:
    """RFC 9421 over @method/@authority/@path, against the owner's AS keys.

    The same mechanics the agent uses for proof-of-possession, pointed the
    other way: this listing is served only to a caller that proves possession
    of her authorization server's signing key.
    """
    last_error = "no signature"
    for jwk_dict in await as_verification_keys(who):
        try:
            verify(method=request.method, authority=EXPECTED_AUTHORITY,
                   path=path, authorization="",
                   signature_input=request.headers.get("signature-input", ""),
                   signature=request.headers.get("signature", ""),
                   public_key=OKPAlgorithm.from_jwk(json.dumps(jwk_dict)))
            return None
        except VerifyError as exc:
            last_error = str(exc)
    event("owner_resources.denied", reason=last_error, owner=who)
    return deny(401, {"error": "invalid_signature",
                      "error_description": "this listing is served only to "
                      f"the owner's authorization server: {last_error}"})


@app.get("/owner-resources/{owner}")
async def owner_resources_for(owner: str, request: Request) -> Response:
    return await owner_resources(request, owner if owner in ALL_OWNERS else None)


@app.get("/owner-resources")
async def owner_resources(request: Request, owner: str = None) -> Response:
    """The protected half of discovery — a "protected webfinger" for the
    owner's stuff. Serves the owner-bound resource instances only to a
    querier that proves possession of the owner's AS signing key (RFC 9421
    over @method/@authority/@path — the same message-signature mechanics
    the agent uses for proof-of-possession, pointed the other way). The
    trust was established at onboarding: this gateway holds a PAT from
    exactly that AS."""
    who = owner or OWNER
    if (denial := await _require_as_signature(request, who,
                                              f"/owner-resources/{who}")):
        return denial
    tools = dict(tools_for(who))
    # Everything this owner administers, hers and shared alike, in one
    # listing. An organization's resource appears here only while she holds a
    # role that grants it — which is what makes membership the thing that
    # brings it into existence at her authority, and leaving the thing that
    # removes it.
    shared = await shared_enforcer(who, fresh=True)
    shared_ids = set()
    if shared is not None:
        for tool, (rid, ss) in shared.tools.items():
            tools[f"shared:{tool}"] = (rid, ss)
            shared_ids.add(rid)
    # And the accounts she holds jointly with somebody else. They arrive by
    # the same route as the organization's, and for the same reason: a
    # resource has to exist at her authority before she can write terms over
    # it, and her terms are half of what an agent will be held to here.
    joint_ids = set()
    for account, jtools in (await joint_held_by(who)).items():
        for tool, (rid, ss) in jtools.items():
            tools[f"joint:{account}:{tool}"] = (rid, ss)
            joint_ids.add(rid)
    leaf = f"mcp/{who}"
    event("owner_resources.served", owner=who, count=len(tools),
          shared=len(shared_ids), joint=len(joint_ids))
    return Response(
        content=json.dumps({
            "owner": who,
            "resource": f"{PUBLIC_BASE}/{leaf}",
            "resources": [
                {"_id": rid, "tool": tool.rsplit(":", 1)[-1],
                 "resource_scopes": ss, "type": "mcp-tool",
                 "name": (f"Shared: {tool.rsplit(':', 1)[-1]}" if rid in shared_ids
                          else f"Joint: {tool.rsplit(':', 1)[-1]}" if rid in joint_ids
                          else f"{who.title()}'s vault: {tool}")}
                for tool, (rid, ss) in tools.items()
            ],
        }),
        media_type="application/json",
    )


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
