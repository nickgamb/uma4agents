"""The same UMA enforcement, hosted inside the resource instead of ahead of it.

An MCP SDK 2.x `Extension` that carries the FedAuthz obligations in-process:
`intercept_tool_call` is a short-circuiting hook at exactly the boundary the
gateway deployment protects from outside, and it reaches its verdicts by
calling the same `lib/uma4a_pep.Enforcer` the ext_authz service uses. Nothing
about the grant, the ticket, the terms, or the token changes.

One thing does change, and it is a finding rather than a limitation. A host
with an HTTP hop of its own answers beat 1 with `401 + WWW-Authenticate: UMA`.
An in-process interceptor has no status line to set — `intercept_tool_call`
returns a domain result — so the challenge has to be JSON-RPC-shaped instead:
a `-32001` error carrying the same `as_uri`, `ticket`, and `resource_metadata`.
That is the same binding-shaped / binding-independent split the discovery work
found: the *challenge encoding* follows the deployment; the ticket, the
authorization server, and the owner's terms do not.

Enabled with ENFORCEMENT_MODE=embedded. In gateway mode this module is not
loaded and the vault holds no auth code at all.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Any

from mcp.server.extension import CallNext, Extension, HandlerResult, ServerRequestContext
from mcp.shared.exceptions import MCPError
from mcp.types import CallToolRequestParams

from uma4a_pep import AuthzFacts, Enforcer

log = logging.getLogger("alice-vault.uma")
logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")

# JSON-RPC application error range. The challenge is a protocol outcome, not a
# transport failure, so it travels as an error with structured data.
UMA_CHALLENGE = -32001
UMA_DENIED = -32002


def event(name: str, corr: str | None = None, **details: Any) -> None:
    log.info(json.dumps({
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event": name,
        "corr": corr,
        "actor": "alice-vault-uma",
        "details": details,
    }))


class UmaEnforcement(Extension):
    """UMA protection applied by the resource to itself."""

    # MCP requires a reverse-DNS-prefixed extension identifier. It is
    # advertised under capabilities.extensions, so a client can see that this
    # resource enforces a UMA grant without being told out of band.
    identifier = "dev.uma4agents/uma-enforcement"

    def settings(self) -> dict[str, Any]:
        return {
            "grant_type": "urn:ietf:params:oauth:grant-type:uma-ticket",
            "authorization_servers": [self.enforcer.as_public],
            "challenge": {"jsonrpc_error_code": UMA_CHALLENGE},
        }

    def __init__(self, enforcer: Enforcer, *, authority: str, path: str = "/mcp") -> None:
        self.enforcer = enforcer
        self.authority = authority
        self.path = path

    async def intercept_tool_call(
        self,
        params: CallToolRequestParams,
        ctx: ServerRequestContext[Any, Any],
        call_next: CallNext,
    ) -> HandlerResult:
        req = getattr(ctx, "request", None)
        headers = getattr(req, "headers", {}) or {}

        facts = AuthzFacts(
            tool=params.name,
            args=dict(params.arguments or {}),
            mcp_method="tools/call",
            # The path is the resource's public one, not whatever this
            # process happens to be bound to; the authority comes from the
            # enforcer's configuration for the same reason.
            http_method=getattr(req, "method", "POST") if req else "POST",
            path=self.path,
            authorization=headers.get("authorization"),
            signature=headers.get("signature", ""),
            signature_input=headers.get("signature-input", ""),
            origin=headers.get("origin"),
            header_mcp_method=headers.get("mcp-method"),
            header_mcp_name=headers.get("mcp-name"),
            protocol_version=headers.get("mcp-protocol-version"),
            signature_agent=headers.get("signature-agent"),
            traceparent=headers.get("traceparent"),
        )

        d = await self.enforcer.authorize(facts)

        if d.outcome == "allow":
            return await call_next(ctx)

        if d.outcome == "challenge":
            # Beat 1 without a status line. Same parameters the 401 would
            # carry, including the RAR-metadata remediation object byte for
            # byte — which is the point: that payload is portable, and only
            # the envelope is binding-specific.
            raise MCPError(
                UMA_CHALLENGE,
                "authorization required: present this ticket to the resource owner's AS",
                {
                    "error": "insufficient_authorization",
                    "as_uri": d.as_uri,
                    "ticket": d.ticket,
                    "resource_metadata": d.resource_metadata,
                    "realm": self.enforcer.realm,
                    "scope": " ".join(d.scopes or []),
                    "authorization_remediation": self.enforcer.remediation(d),
                },
            )

        raise MCPError(
            UMA_DENIED,
            d.description or d.error,
            {"error": d.error, "status": d.status},
        )


def origin_guard(app, enforcer: Enforcer, path: str = "/mcp"):
    """The Origin rule for every request to the MCP endpoint.

    The extension above sees tools/call and nothing else; initialize, the
    stream GET and the session DELETE never reach it. So the rule is applied
    at the transport, ahead of the SDK, with the same code the gateway uses.
    The discovery documents are left readable from any origin: they are
    public, and a browser client has to be able to fetch them.
    """
    from starlette.responses import JSONResponse

    async def guarded(scope, receive, send):
        if scope["type"] == "http" and scope["path"].startswith(path):
            origin = dict(scope["headers"]).get(b"origin")
            refused = enforcer.origin_refused(origin.decode() if origin else None)
            if refused:
                await JSONResponse({"error": refused.error},
                                   status_code=refused.status)(scope, receive, send)
                return
        await app(scope, receive, send)
    return guarded


def build(tools: dict[str, tuple[str, list[str]]],
          single_use: set[str],
          consequence: dict[str, str] | None = None) -> UmaEnforcement:
    """Wire an enforcer from the environment, mirroring the gateway host."""
    import uma_publish

    authority = os.environ.get("UMA_EXPECTED_AUTHORITY", "gateway.uma.lab")
    # The same origin `uma_publish` serves the metadata at, and built the same
    # way: the identifier this resource registers under has to be the one the
    # authority will dereference, or it authenticates as nobody.
    public_base = f"{os.environ.get('UMA_PEP_SCHEME', 'https')}://{authority}"
    secret = os.environ.get("UMA_AS_RS_CLIENT_SECRET", "gateway-dev-secret")
    enforcer = Enforcer(
        as_internal=os.environ.get("UMA_AS_INTERNAL", "http://uma-as:9000"),
        as_public=os.environ.get("UMA_AS_PUBLIC", "https://alice-as.uma.lab"),
        # Which identity this resource server has here follows from whether
        # anyone provisioned the pair — the same rule the gateway host
        # applies, because it is the same question. With a secret it is the
        # name it was given; without one it is its own origin, and it
        # introduces itself by signing with the key it publishes there.
        client_id=(os.environ.get("UMA_AS_RS_CLIENT_ID", "meridian-gateway")
                   if secret else public_base),
        client_secret=secret,
        # Loaded only on the branch that needs it. A deployment holding a
        # secret may have this file mounted read-only, or not at all, and
        # `key()` would create one.
        signing_key=None if secret else uma_publish.key(),
        key_id=uma_publish.KID,
        resource_uri=f"{public_base}/mcp",
        rs_name=os.environ.get("UMA_PEP_RS_NAME", f"{authority} (embedded)"),
        realm=os.environ.get("UMA_REALM", "alice-vault"),
        tools=tools,
        single_use_tools=single_use,
        consequence=consequence or {},
        protected_methods={"tools/call"},
        open_methods=set(),        # the interceptor only ever sees tools/call
        expected_authority=authority,
        allowed_origins={o for o in os.environ.get(
            "UMA_ALLOWED_ORIGINS",
            f"https://{authority},https://portal.uma.lab").split(",") if o},
        resource_metadata_url=(
            f"https://{authority}/.well-known/oauth-protected-resource/mcp"),
        event=event,
    )
    return UmaEnforcement(enforcer, authority=authority)
