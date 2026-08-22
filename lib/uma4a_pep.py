"""The UMA enforcement core, with no transport of its own.

Two shapes, one implementation:

  1. a gateway, with plain MCP servers behind it that know nothing about UMA;
  2. no gateway at all, with the MCP server handling the grant itself.

UMA 2.0's Federated Authorization gives the resource server a job list — hold
a PAT (§1.5), keep the authorization server's view of its resources current
(§3), ask for a permission ticket (§4), introspect a token before allowing a
call (§5) — and never says which piece of software does that work. §1.4,
"Separation of Responsibility and Authority", divides the work between the
*parties*, not between processes. So a gateway in front of the resource and
the resource itself are equally conformant; the job list is the same either
way.

That is why the decision logic lives here, written in terms of request *facts*
rather than any particular server's request object, with thin adapters on top:

  - `services/uma-pep` runs it as an HTTP ext_authz service behind a gateway,
    which is what lets a stock MCP server participate untouched.
  - `mcp/alice-vault/uma_extension.py` runs the same code in-process as an MCP
    SDK 2.x `Extension`, where the resource protects itself.

Both talk to the same AS over the same wire contract and reach the same
verdicts. The only thing that differs is how a verdict becomes a response,
because an in-process interceptor has no HTTP hop of its own to decorate.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from jwt.algorithms import OKPAlgorithm

from urllib.parse import urlencode

from uma4a_http_sig import VerifyError, verify
from uma4a_http_sig import sign as http_sign


class Pending(Exception):
    """The authority knows this resource server and the owner has not yet
    said yes. Not an error in the relationship — a stage of it."""


def _error_of(r: httpx.Response) -> str:
    try:
        return r.json().get("error", "")
    except ValueError:
        return ""


def s256(data: bytes) -> str:
    return "s256:" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()


# --- What the core needs to know about one request ---------------------------


@dataclass
class AuthzFacts:
    """One inbound tool call, reduced to what a verdict depends on.

    Deliberately not an HTTP request or an MCP context: an adapter fills this
    in from whatever it has.
    """

    tool: str | None
    args: dict | None
    mcp_method: str | None
    http_method: str = "POST"
    # No `authority` here on purpose: the RFC 9421 base is reconstructed from
    # the enforcer's *configured* expected_authority, never from the request,
    # because an ext_authz hop rewrites Host and a forwarded value would let a
    # caller choose what it signed over.
    path: str = "/mcp"
    authorization: str | None = None
    signature: str = ""
    signature_input: str = ""
    origin: str | None = None
    header_mcp_method: str | None = None
    header_mcp_name: str | None = None
    protocol_version: str | None = None
    # Web Bot Auth: where this agent publishes its keys. Covered by the
    # signature when present, so it cannot be swapped in transit.
    signature_agent: str | None = None
    # W3C Trace Context. The negotiation family correlates everything *inside*
    # this system; traceparent is what joins it to the caller's trace, which
    # matters because a grant spans two organizations and an offline human.
    traceparent: str | None = None


@dataclass
class Decision:
    """A verdict, plus everything a host needs to render it.

    `outcome` is what happened; how it reaches the client is the adapter's
    business. A gateway turns `challenge` into 401 + WWW-Authenticate; an
    in-process extension turns it into a JSON-RPC error carrying the same
    ticket and as_uri, because it has no status line to set.
    """

    outcome: Literal["allow", "challenge", "deny"]
    status: int = 200
    error: str = ""
    description: str = ""
    ticket: str | None = None
    as_uri: str | None = None
    resource_metadata: str | None = None
    scopes: list[str] | None = None
    # draft-zehavi-oauth-rar-metadata: what authority was missing, in RAR
    # terms, plus its content-addressed id.
    authorization_details: list[dict] | None = None
    authorization_reference: str | None = None
    family: str | None = None
    contract: str | None = None


ALLOW = Decision(outcome="allow")


# --- The enforcer ------------------------------------------------------------


class Enforcer:
    """Carries the FedAuthz obligations against one authorization server, for
    one owner.

    Both halves of that matter. A resource server holding many people's
    accounts holds one of these per owner, and nothing is shared between them
    — not the PAT, not the tool namespace, not the authorization server. That
    last one is what lets two owners of the same resource server name two
    different authorities.
    """

    def __init__(
        self,
        *,
        owner: str = "alice",
        as_internal: str,
        as_public: str,
        client_id: str,
        client_secret: str = "",
        signing_key: Any = None,
        key_id: str = "",
        resource_uri: str = "",
        rs_name: str = "",
        establish_backoff_s: float = 30.0,
        realm: str,
        tools: dict[str, tuple[str, list[str]]],
        single_use_tools: set[str],
        protected_methods: set[str],
        open_methods: set[str],
        expected_authority: str,
        allowed_origins: set[str],
        resource_metadata_url: str,
        event=None,
    ) -> None:
        self.owner = owner
        self.as_internal = as_internal
        self.as_public = as_public
        self.client_id = client_id
        self.client_secret = client_secret
        # The other way to be this resource server: a key published at the
        # origin of the resource it serves. Used when there is no secret,
        # which is every authority nobody provisioned this side against.
        self.signing_key = signing_key
        self.key_id = key_id
        self.resource_uri = resource_uri
        self.rs_name = rs_name
        self.establish_backoff_s = establish_backoff_s
        # When it is worth introducing ourselves again. A withdrawn resource
        # server that re-registered on every request would put the same
        # question in front of the owner as fast as traffic arrives, which is
        # a way of pestering her into a yes.
        self._establish_after = 0.0
        self.realm = realm
        self.tools = tools
        self.single_use_tools = single_use_tools
        self.protected_methods = protected_methods
        self.open_methods = open_methods
        self.expected_authority = expected_authority
        self.allowed_origins = allowed_origins
        self.resource_metadata_url = resource_metadata_url
        self.event = event or (lambda *a, **k: None)
        self._pat: dict[str, Any] = {"token": None, "expires": 0}

    # --- Protection API client ------------------------------------------

    @property
    def as_authority(self) -> str:
        """The host a signature to this authority has to cover. The public
        one, not the address dialled — a service mesh routes by an internal
        name the authority has never heard of, and signing that would make
        the signature unverifiable at the far end for no gain."""
        return self.as_public.split("://", 1)[-1].rstrip("/")

    async def _token_request(self, client: httpx.AsyncClient,
                             form: dict) -> httpx.Response:
        """POST /token, authenticated the way this relationship works."""
        if self.client_secret:
            return await client.post(f"{self.as_internal}/token",
                                     data={**form,
                                           "client_secret": self.client_secret},
                                     timeout=5.0)
        body = urlencode(form).encode()
        headers = http_sign(
            method="POST", authority=self.as_authority, path="/token",
            authorization="", key=self.signing_key, keyid=self.key_id,
            body=body)
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        return await client.post(f"{self.as_internal}/token", content=body,
                                 headers=headers, timeout=5.0)

    async def establish(self, client: httpx.AsyncClient) -> str:
        """Introduce this resource server to an authority that has never seen
        it, and report what came back: `active`, `pending`, or `refused`.

        Nothing is sent that the authority has to be configured to recognise.
        The signature is made with a key published in the RFC 9728 document
        this resource already serves, so verifying it is a fetch the authority
        performs against the origin it is being asked to trust.
        """
        body = json.dumps({"owner": self.owner,
                           "resource_uri": self.resource_uri,
                           "name": self.rs_name or self.client_id}).encode()
        headers = http_sign(
            method="POST", authority=self.as_authority, path="/rs/register",
            authorization="", key=self.signing_key, keyid=self.key_id,
            body=body)
        headers["Content-Type"] = "application/json"
        r = await client.post(f"{self.as_internal}/rs/register", content=body,
                              headers=headers, timeout=10.0)
        status = "refused"
        if r.status_code in (200, 202):
            status = r.json().get("status", "pending")
        self.event("resource_server.establish", owner=self.owner,
                   authority=self.as_public, status=status,
                   code=r.status_code)
        return status

    async def pat(self, client: httpx.AsyncClient, force: bool = False) -> str:
        """The PAT, refreshed 60s early. An OAuth token, not a shared string.

        Where there is no secret this may be the first thing that ever passes
        between the two, so an unrecognised client is not an error to raise
        but a introduction to make: register, then ask again. The second 401
        is real.
        """
        if not force and self._pat["token"] and time.time() < self._pat["expires"] - 60:
            return self._pat["token"]
        form = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "scope": "uma_protection",
            # One PAT per owner. Without this the authorization server
            # cannot tell which of its owners this resource server is
            # asking on behalf of.
            "owner": self.owner,
        }
        r = await self._token_request(client, form)
        # Unrecognised, or known and withdrawn. Neither is a credential this
        # side got wrong — there is no secret to get wrong — so the move is to
        # introduce ourselves again and let her decide, not to retry harder.
        # Asking again cannot undo her withdrawal; it can only put the
        # question back in front of her, which is what re-registering does.
        refused = r.status_code == 401 or (
            r.status_code == 403 and _error_of(r) == "access_denied")
        if refused and self.signing_key is not None:
            if time.time() >= self._establish_after:
                self._establish_after = time.time() + self.establish_backoff_s
                await self.establish(client)
                # Ask again either way: the second answer separates "she has
                # been asked" from "that origin does not check out", and only
                # the first is worth waiting through.
                r = await self._token_request(client, form)
        if r.status_code == 403 and _error_of(r) == "authorization_pending":
            # She has been asked and has not answered. Distinct from a
            # refusal, and the difference matters: this side should keep
            # serving challenges and try again, not treat itself as revoked.
            raise Pending(f"{self.owner} has not yet authorized this "
                          f"resource server at {self.as_public}")
        r.raise_for_status()
        body = r.json()
        # A working relationship clears the throttle, so the next time this
        # one stops working the question reaches her at once. The throttle is
        # there to stop the same unanswered question repeating, not to sit
        # between her and a change she just made.
        self._establish_after = 0.0
        self._pat = {"token": body["access_token"],
                     "expires": time.time() + body.get("expires_in", 3600)}
        return self._pat["token"]

    async def pat_headers(self, client: httpx.AsyncClient) -> dict[str, str]:
        return {"Authorization": f"Bearer {await self.pat(client)}"}

    async def mint_ticket(self, resource_id: str, scopes: list[str]) -> str | None:
        """Register the attempted permission and get a ticket (beat 1).

        A 401 means the PAT expired mid-flight, or the AS restarted with new
        keys; retry once with a fresh one. An unknown resource id is *not*
        this side's problem to repair under declarative registration — the AS
        re-reads what we publish when it meets one, which is the whole point
        of the trade.
        """
        body = {"resource_id": resource_id, "resource_scopes": scopes}
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(f"{self.as_internal}/perm", json=body,
                                      headers=await self.pat_headers(client), timeout=5.0)
                if r.status_code == 401:
                    await self.pat(client, force=True)
                    r = await client.post(f"{self.as_internal}/perm", json=body,
                                          headers=await self.pat_headers(client),
                                          timeout=5.0)
                r.raise_for_status()
                return r.json()["ticket"]
        except httpx.HTTPError as exc:
            self.event("permission.mint_failed", error=str(exc)[:200])
            return None

    async def introspect(self, token: str) -> dict:
        """Ask the AS about an RPT. Never consumes — see `consume`.

        A resource server still waiting on her cannot introspect either, and
        an inactive answer is the right one: it holds no PAT, so it has no
        way to be told this token is good.
        """
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    f"{self.as_internal}/introspect",
                    data={"token": token, "consume": "false"},
                    headers=await self.pat_headers(client),
                    timeout=5.0,
                )
                r.raise_for_status()
                return r.json()
        except Pending:
            return {"active": False}

    async def consume(self, token: str) -> bool:
        """Burn a single-use RPT, once everything else has verified."""
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    f"{self.as_internal}/consume",
                    data={"token": token},
                    headers=await self.pat_headers(client),
                    timeout=5.0,
                )
                r.raise_for_status()
                return bool(r.json().get("consumed"))
        except (httpx.HTTPError, Pending):
            return False

    async def report_access(self, family: str, tool: str, summary: str) -> None:
        """Ground the ledger's "touched" column in enforcement, not claims."""
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{self.as_internal}/audit/access",
                    json={"family": family, "tool": tool, "summary": summary},
                    headers=await self.pat_headers(client),
                    timeout=5.0,
                )
        except (httpx.HTTPError, Pending):
            pass

    # --- The verdict ----------------------------------------------------

    async def authorize(self, f: AuthzFacts) -> Decision:
        """Decide one request. The ordering below is normative — see PROTOCOL.md."""
        # MCP 2026-07-28 makes Origin validation a MUST.
        if f.origin and f.origin not in self.allowed_origins:
            self.event("access.denied", reason="bad-origin", origin=f.origin)
            return Decision(outcome="deny", status=403, error="invalid_origin")

        # SEP-2243 mirrors the method and target into headers so a proxy can
        # route without parsing a body. Two parsers over one message is the
        # request-smuggling shape, so they have to be reconciled.
        if f.header_mcp_method and f.mcp_method and f.header_mcp_method != f.mcp_method:
            self.event("access.denied", reason="header-body-mismatch",
                       header_method=f.header_mcp_method, body_method=f.mcp_method)
            return Decision(outcome="deny", status=400, error="header_body_mismatch",
                            description="Mcp-Method disagrees with the JSON-RPC body")
        if f.header_mcp_name and f.tool and f.header_mcp_name != f.tool:
            self.event("access.denied", reason="header-body-mismatch",
                       header_name=f.header_mcp_name, body_name=f.tool)
            return Decision(outcome="deny", status=400, error="header_body_mismatch",
                            description="Mcp-Name disagrees with the JSON-RPC body")

        # Deny by default: named-open passes, named-protected is enforced,
        # anything a future revision invents is neither.
        if f.mcp_method in self.open_methods:
            return ALLOW
        if f.mcp_method not in self.protected_methods:
            self.event("access.denied", reason="unknown-method", mcp_method=f.mcp_method)
            return Decision(outcome="deny", status=403, error="unknown_method",
                            description=f"{f.mcp_method} is not enforceable by this PEP")
        # On a protected method the routing headers are REQUIRED, not merely
        # reconciled if supplied. Absent, an enforcement point that routes on
        # them can be steered by omission — and the reference SDK rejects a
        # missing mcp-name on tools/call for the same reason. Only checked for
        # callers that already speak 2026-07-28, so an older client still gets
        # a challenge rather than a confusing 400.
        if f.protocol_version and f.protocol_version >= "2026-07-28":
            if not f.header_mcp_method or not f.header_mcp_name:
                self.event("access.denied", reason="missing-routing-headers",
                           tool=f.tool)
                return Decision(
                    outcome="deny", status=400, error="missing_routing_headers",
                    description="Mcp-Method and Mcp-Name are required on tools/call")
        if f.tool not in self.tools:
            self.event("access.denied", reason="unknown-tool", tool=f.tool)
            return Decision(outcome="deny", status=403, error="unknown_tool")

        rid, scopes = self.tools[f.tool]

        if not f.authorization:
            return await self.challenge(f.tool, rid, scopes)
        if not f.authorization.startswith("PoP "):
            return Decision(outcome="deny", status=401, error="invalid_token",
                            description="RPTs are PoP tokens here, not Bearer")
        rpt = f.authorization[4:]

        # 1. Is the token live, and does the relationship behind it stand?
        #    Non-consuming: nothing is spent before every check has passed.
        info = await self.introspect(rpt)
        if not info.get("active"):
            reason = info.get("error", "inactive")
            self.event("access.denied", reason=f"inactive-rpt: {reason}", tool=f.tool)
            # A revoked connection is a decision the owner already made.
            # Re-challenging invites a negotiation whose outcome is settled.
            if reason == "connection_revoked":
                return Decision(outcome="deny", status=403, error="access_revoked",
                                description="the resource owner revoked this agent")
            return await self.challenge(f.tool, rid, scopes)

        # 2. Does the grant cover this resource?
        perms = {p["resource_id"] for p in info.get("permissions", [])}
        if rid not in perms:
            self.event("access.denied", reason="permission-scope", tool=f.tool,
                       granted=sorted(perms))
            return await self.challenge(f.tool, rid, scopes)

        # 3. Proof of possession. Covering the Authorization header is what
        #    makes the RPT sender-constrained rather than bearer.
        try:
            # The verifying key is the one bound into the grant, always. A
            # Signature-Agent directory is discovery, not authority: it is
            # covered by the signature so it cannot be swapped, but it is
            # never consulted to decide *which* key to trust.
            pub = OKPAlgorithm.from_jwk(json.dumps(info["cnf"]["jwk"]))
            verify(
                method=f.http_method,
                authority=self.expected_authority,
                path=f.path,
                authorization=f.authorization,
                signature_input=f.signature_input,
                signature=f.signature,
                public_key=pub,
                signature_agent=f.signature_agent,
            )
        except (KeyError, VerifyError) as exc:
            self.event("access.denied", reason=f"pop: {exc}", tool=f.tool,
                       path=f.path, signature_input=f.signature_input)
            return Decision(outcome="deny", status=401, error="invalid_token",
                            description=f"proof-of-possession failed: {exc}")

        # 4. Operation binding: this trade, not trading authority.
        if f.tool in self.single_use_tools:
            op = info.get("operation") or {}
            actual = s256(json.dumps(f.args or {}, sort_keys=True).encode())
            if op.get("tool") != f.tool or op.get("params_s256") != actual:
                self.event("access.denied", reason="operation-binding", tool=f.tool,
                           expected=op.get("params_s256"), actual=actual)
                return Decision(outcome="deny", status=403, error="operation_mismatch",
                                description="RPT authorizes a different operation")
            # 5. Only now spend it. Check-then-act, so the burn is last and
            #    atomic; losing the race means someone else got there first.
            if not await self.consume(rpt):
                self.event("access.denied", reason="consume-lost-race", tool=f.tool)
                return Decision(outcome="deny", status=403, error="already_consumed",
                                description="this single-use grant was already spent")

        family = info.get("family", "?")
        self.event("access.allowed", corr=family, tool=f.tool,
                   contract=info.get("contract"),
                   single_use=info.get("single_use", False),
                   traceparent=f.traceparent)
        await self.report_access(family, f.tool,
                                 summary=json.dumps(f.args or {}, sort_keys=True))
        return Decision(outcome="allow", family=family, contract=info.get("contract"))

    def authorization_details(self, rid: str, tool: str,
                              scopes: list[str]) -> list[dict]:
        """What authority was missing, as an RFC 9396 authorization_details
        array, built from the failed request.

        Same vocabulary draft-zehavi-oauth-rar-metadata uses for step-up
        remediation. Emitting it costs nothing — the resource id and scopes
        are already known — and it means a client that implements that draft
        can read most of a UMA challenge without knowing UMA. It also gives a
        downstream policy engine typed fields instead of only a digest.
        """
        return [{
            "type": "urn:uma4agents:authorization-details:tool-call",
            "locations": [self.resource_metadata_url.rsplit("/.well-known/", 1)[0]],
            "identifier": rid,
            "actions": [tool],
            "datatypes": scopes,
        }]

    async def challenge(self, tool: str, rid: str, scopes: list[str]) -> Decision:
        """Beat 1: a real ticket from the AS, and where to take it."""
        try:
            ticket = await self.mint_ticket(rid, scopes)
        except Pending as exc:
            # Not "her authority is down" — her authority answered, and said
            # it does not yet work for this resource server on her behalf.
            # Reporting that as unreachable would send the caller looking in
            # the wrong place for something only she can fix.
            self.event("challenge.awaiting_owner", tool=tool, resource_id=rid,
                       error=str(exc)[:200])
            return Decision(
                outcome="deny", status=503, error="authorization_pending",
                description=("this resource server has registered with the "
                             "owner's authorization server and is waiting for "
                             "her to authorize it"),
                as_uri=self.as_public,
                resource_metadata=self.resource_metadata_url)
        if ticket is None:
            return Decision(outcome="deny", status=503, error="as_unreachable")
        details = self.authorization_details(rid, tool, scopes)
        self.event("challenge.issued", corr=None, tool=tool, resource_id=rid,
                   scopes=scopes)
        return Decision(
            outcome="challenge",
            status=401,
            error="uma_challenge",
            ticket=ticket,
            as_uri=self.as_public,
            resource_metadata=self.resource_metadata_url,
            scopes=scopes,
            authorization_details=details,
            authorization_reference=s256(
                json.dumps(details, sort_keys=True, separators=(",", ":")).encode()),
        )

    @staticmethod
    def remediation(d: Decision) -> dict:
        """The `authorization_remediation` object, shared by both encodings.

        Deliberately the same JSON whether it rides a WWW-Authenticate header
        or a JSON-RPC error: the payload is portable, only the envelope is
        binding-specific. `as_uri` is the U4A addition — it names *whose*
        authorization server decides, which is what the RAR-metadata flow has
        no slot for, because it assumes the client's own AS can grant.
        """
        return {
            "authorization_details": d.authorization_details or [],
            "authorization_reference": d.authorization_reference,
            "authorization_server": d.as_uri,
            "ticket": d.ticket,
        }

    def www_authenticate(self, d: Decision) -> str:
        """The UMA challenge header, for hosts that have a status line.

        A superset of the RAR-metadata step-up challenge rather than a rival
        to it: `error` and `authorization_remediation` are that draft's
        parameters, carrying the same base64url JSON; `as_uri` and `ticket`
        are the two additions that let a party who is not the caller decide.
        `scope` is RFC 6750 §3, which MCP 2026-07-28 says a resource SHOULD
        include.
        """
        blob = base64.urlsafe_b64encode(
            json.dumps(self.remediation(d), separators=(",", ":")).encode()
        ).rstrip(b"=").decode()
        parts = [f'realm="{self.realm}"',
                 'error="insufficient_authorization"',
                 f'as_uri="{d.as_uri}"',
                 f'ticket="{d.ticket}"',
                 f'resource_metadata="{d.resource_metadata}"']
        if d.scopes:
            parts.append(f'scope="{" ".join(d.scopes)}"')
        parts.append(f'authorization_remediation="{blob}"')
        return "UMA " + ", ".join(parts)


def parse_mcp(body: bytes) -> tuple[str | None, str | None, dict | None]:
    """(jsonrpc_method, tool_name, tool_args) from an MCP POST body."""
    try:
        msg = json.loads(body)
    except (ValueError, TypeError):
        return None, None, None
    if not isinstance(msg, dict):
        return None, None, None
    method = msg.get("method")
    params = msg.get("params") or {}
    if method == "tools/call":
        return method, params.get("name"), params.get("arguments") or {}
    return method, None, None
