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
import os
import time
from dataclasses import dataclass
from typing import Any, Literal

import httpx
import jwt
from jwt.algorithms import OKPAlgorithm

from urllib.parse import urlencode

from uma4a_http_sig import VerifyError, verify
from uma4a_http_sig import sign as http_sign
from uma4a_joint import tally as joint_tally
from uma4a_org import claims_match, envelope_breach


# How long this side may act on a cached answer about who is a member.
#
# The window matters in one direction only: a membership that has *ended* is
# still honoured here until it expires. Ten seconds rather than thirty because
# that window is somebody's access to a firm's book after the firm withdrew
# it, and it is the sort of number a deployment should be able to set.
# Nothing here can extend a grant beyond it — the member's authority stops
# issuing at once, and this only affects whether a challenge is offered.
MEMBERSHIP_TTL_S = float(os.environ.get("UMA_PEP_MEMBERSHIP_TTL_S", "10"))


# The trust anchor for fetching a co-owner's published keys. Every other
# call this library makes is to a service it was configured with, over the
# internal network; verifying a holder's verdict means reaching her authority
# at its public name, which is the one place here that needs a bundle.
CA_BUNDLE = os.environ.get("UMA4A_CA_BUNDLE")
# How long the electorate of a jointly held resource may be reused.
# Short: a holder leaving should stop counting in seconds, not at a
# restart.
MANDATE_TTL_S = float(os.environ.get("UMA_PEP_MANDATE_TTL_S", "30"))


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
        org_issuer: str = "",
        org_internal: str = "",
        org_token: str = "",
        joint_issuer: str = "",
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
        # The organization above this owner, if the firm running this
        # resource server knows of one. Two distinct jobs, and neither is a
        # favour to the member's authority:
        #
        #   * check that a grant her authority issued is inside the
        #     organization's ceiling. She may name any authorization server
        #     she likes — that is BYOAS and it is the point — but the
        #     resource belongs to the organization, so *something* on this
        #     side has to be able to tell whether her authority applied the
        #     ceiling. This is that something.
        #   * accept grants the organization signed itself. Break-glass does
        #     not pass through her authority at all, which is the only way
        #     "the organization owns this data" can be a technical fact
        #     rather than a request.
        self.org_issuer = org_issuer.rstrip("/")
        self.org_internal = (org_internal or org_issuer).rstrip("/")
        self.org_token = org_token
        # A tally this resource server accepts grants from, for resources
        # held jointly. Named rather than inferred: a grant is checked
        # against the mandate inside it, and accepting one from any issuer
        # that happened to embed a plausible mandate would be accepting the
        # electorate from the party that assembled it.
        self.joint_issuer = joint_issuer.rstrip("/")
        self.event = event or (lambda *a, **k: None)
        self._pat: dict[str, Any] = {"token": None, "expires": 0}
        self._membership: tuple[float, dict] = (0.0, {})
        self._holder_jwks: dict[str, tuple[float, list]] = {}
        self._mandates: dict[str, tuple[float, dict]] = {}

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

    # --- The organization above this owner ------------------------------

    async def membership(self, fresh: bool = False) -> dict:
        """Whether this owner administers these resources for an
        organization, and what that organization's ceiling is.

        Read from the organization, never from the member's authority. The
        whole value of this check is that it does not go through the party
        it is checking.
        """
        if not self.org_issuer:
            return {}
        cached_at, cached = self._membership
        # The cache is for the hot path — one lookup per authorized call.
        # Anything that *publishes* what a member may reach asks for a fresh
        # answer instead: those are rare, they are read by her authorization
        # server rather than by an agent, and a listing served from a stale
        # cache is how a role change appears to have been ignored.
        if not fresh and cached_at > time.time() - MEMBERSHIP_TTL_S:
            return cached
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"{self.org_internal}/membership/{self.owner}",
                    headers={"Authorization": f"Bearer {self.org_token}"},
                    timeout=5.0)
                r.raise_for_status()
                doc = r.json()
        except httpx.HTTPError as exc:
            self.event("org.membership_unreadable", owner=self.owner,
                       error=str(exc))
            # The previous answer stands rather than either extreme. Treating
            # an unreachable organization as "no organization" would drop the
            # ceiling exactly when something is wrong; treating it as a denial
            # would make the organization's uptime a precondition for every
            # owner's grant loop, including owners who are not members.
            return cached
        self._membership = (time.time(), doc)
        return doc

    async def org_introspect(self, token: str) -> dict:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    f"{self.org_internal}/introspect", data={"token": token},
                    headers={"Authorization": f"Bearer {self.org_token}"},
                    timeout=5.0)
                r.raise_for_status()
                return r.json()
        except httpx.HTTPError:
            return {"active": False, "error": "organization_unreachable"}

    async def org_consume(self, token: str) -> bool:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    f"{self.org_internal}/consume", data={"token": token},
                    headers={"Authorization": f"Bearer {self.org_token}"},
                    timeout=5.0)
                r.raise_for_status()
                return bool(r.json().get("consumed"))
        except httpx.HTTPError:
            return False

    async def org_report(self, family: str, tool: str, summary: str) -> None:
        """Report a call allowed under an override.

        Reported to the organization, which forwards it to the member. Not
        posted to her authority directly: this grant was never hers, her
        authority has no record to attach it to, and an enforcement point
        that could write into her ledger on behalf of a third party would be
        a way to forge entries in it.
        """
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{self.org_internal}/audit/access",
                    json={"family": family, "tool": tool, "summary": summary,
                          "owner": self.owner},
                    headers={"Authorization": f"Bearer {self.org_token}"},
                    timeout=5.0)
        except httpx.HTTPError:
            pass

    async def joint_breach(self, info: dict, rid: str) -> str | None:
        """Whether a grant over a jointly held resource is actually backed by
        its holders.

        This is the check that makes the tally an untrusted party rather than
        one more thing to believe. Each verdict is verified against the keys
        *that holder's own authorization server* publishes, checked to be
        about this negotiation and this exact agreement, and the count is run
        again. A tally that fabricated a yes, or replayed an old one, fails
        at this line.

        The mandate is read from where the tally **publishes** it, never from
        the grant. Counting against the copy inside the token would leave the
        electorate in the gift of the party being checked: a tally could ship
        one genuine verdict beside a mandate saying one is enough, and the
        arithmetic here would agree with it. The published document is the one
        the holders saw and can check, so it is the one the count runs on, and
        an unreadable one is a refusal rather than a fallback to the token's.

        What this deliberately does not do is decide anything. It re-derives
        the same arithmetic from the same signed inputs, and if it disagrees
        with the issuer, the issuer is wrong.
        """
        joint = info.get("joint")
        if not joint:
            return None
        mandate = await self.published_mandate(joint.get("account") or "")
        if mandate is None:
            return ("this resource is held jointly and its mandate could not "
                    "be read, so who was entitled to a say is not known here")
        if not mandate.get("holders"):
            return "that mandate names no holders to have agreed to it"
        by_owner = {h["owner"]: h for h in mandate["holders"]}
        verdicts: dict[str, str] = {}
        for jws in joint.get("verdicts") or []:
            try:
                unverified = jwt.decode(jws, options={"verify_signature": False})
            except jwt.InvalidTokenError:
                return "a verdict in this grant is not a token"
            holder = by_owner.get(unverified.get("holder") or "")
            if holder is None:
                return (f"a verdict is signed for {unverified.get('holder')!r}, "
                        f"who is not a holder of this resource")
            claims = await self._verified_verdict(jws, holder)
            if claims is None:
                return (f"the verdict attributed to {holder['owner']} is not "
                        f"signed by the authority that holder names")
            if claims.get("contract") != info.get("contract"):
                return (f"{holder['owner']}'s verdict is about a different "
                        f"agreement than this grant was issued for")
            if claims.get("resource_id") != rid:
                return (f"{holder['owner']}'s verdict is about a different "
                        f"resource")
            if claims.get("effect") == "allow":
                verdicts[holder["owner"]] = "allow"
        result = joint_tally(mandate, verdicts)
        if result["effect"] != "allow":
            return (f"this grant claims the holders agreed, and the verdicts "
                    f"inside it carry {result['for']} of the "
                    f"{result['threshold']} it takes")
        return None

    async def published_mandate(self, account: str) -> dict | None:
        """Who is entitled to be counted over this account, from the tally's
        published document rather than from a grant.

        Cached briefly for the hot path. Unreachable returns None, and the
        caller refuses — a jointly held resource whose electorate cannot be
        established is not one this side can let through.
        """
        if not account or not self.joint_issuer:
            return None
        cached = self._mandates.get(account)
        if cached and cached[0] > time.time():
            return cached[1]
        try:
            async with httpx.AsyncClient(verify=CA_BUNDLE or True,
                                         timeout=5.0) as client:
                r = await client.get(f"{self.joint_issuer}/mandate/{account}")
                r.raise_for_status()
                doc = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            self.event("joint.mandate_unreadable", account=account,
                       error=str(exc)[:160])
            return cached[1] if cached else None
        self._mandates[account] = (time.time() + MANDATE_TTL_S, doc)
        return doc

    async def _verified_verdict(self, jws: str, holder: dict) -> dict | None:
        """One verdict, against the issuing holder's published keys."""
        issuer = (holder.get("issuer") or "").rstrip("/")
        cached = self._holder_jwks.get(issuer)
        if not cached or cached[0] < time.time():
            try:
                async with httpx.AsyncClient(verify=CA_BUNDLE or True,
                                             timeout=5.0) as client:
                    r = await client.get(f"{issuer}/jwks")
                    r.raise_for_status()
                cached = (time.time() + 300, r.json()["keys"])
                self._holder_jwks[issuer] = cached
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                self.event("joint.jwks_unreachable", issuer=issuer,
                           error=str(exc)[:160])
                return None
        for jwk_dict in cached[1]:
            try:
                return jwt.decode(jws, OKPAlgorithm.from_jwk(json.dumps(jwk_dict)),
                                  algorithms=["EdDSA"], issuer=issuer,
                                  options={"verify_aud": False})
            except jwt.InvalidTokenError:
                continue
        return None

    def issued_by_organization(self, rpt: str) -> bool:
        """Whose grant this is, from the token itself.

        Unverified — it only selects which authority to ask, and both answers
        verify what they are given. Reading an unverified claim to decide
        where to send something is safe; reading one to decide anything else
        is not.
        """
        if not self.org_issuer:
            return False
        try:
            claims = jwt.decode(rpt, options={"verify_signature": False})
        except jwt.InvalidTokenError:
            return False
        return (claims.get("iss") or "").rstrip("/") == self.org_issuer

    async def ceiling_breach(self, info: dict, rid: str) -> str | None:
        """Whether a grant from the member's authority sits outside the
        organization's ceiling.

        This is the check that does not trust the authority that minted the
        token. It catches the case that matters — a member's authorization
        server, which she chose and may run herself, issuing more than the
        organization's charter allows over the organization's own resources.
        """
        doc = await self.membership()
        if not doc.get("member") or not claims_match(rid, doc.get("claims")):
            return None
        for permission in info.get("permissions", []):
            if permission.get("resource_id") != rid:
                continue
            remaining = float(permission.get("exp", 0)) - time.time()
            if breach := envelope_breach(permission, doc, remaining):
                return breach
        return None

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

        # Which authority to ask. Almost always the owner's; the exception is
        # a grant the organization above her signed itself, which never went
        # through her authority and cannot be introspected there. Everything
        # after this point is the same sequence of checks either way — the
        # override is a different *issuer*, not a shortcut past enforcement.
        override = self.issued_by_organization(rpt)

        # 1. Is the token live, and does the relationship behind it stand?
        #    Non-consuming: nothing is spent before every check has passed.
        info = await (self.org_introspect(rpt) if override else self.introspect(rpt))
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

        # 2a. If an organization governs this resource, does the grant sit
        #     inside its ceiling? Only for grants the *member's* authority
        #     issued: an override is the organization exceeding its own
        #     envelope on purpose, under a clause its members were shown.
        #
        #     Re-challenging would be wrong here and the distinction is worth
        #     the branch. A challenge says "negotiate again and you may
        #     succeed"; this says the authority that answered is issuing more
        #     than the organization permits, which negotiating again will
        #     reproduce exactly.
        if not override and (breach := await self.ceiling_breach(info, rid)):
            self.event("access.denied", reason="org-envelope", tool=f.tool,
                       detail=breach)
            return Decision(outcome="deny", status=403,
                            error="organization_envelope_exceeded",
                            description=breach)

        # 2b. If this resource is held jointly, do the holders' own signed
        #     verdicts actually add up to what the grant claims? Re-derived
        #     here from the mandate and the signatures rather than taken from
        #     the party that issued the token, which is the whole reason that
        #     party does not have to be trusted.
        #
        #     Not a re-challenge, for the same reason the ceiling above is
        #     not: negotiating again reproduces it exactly.
        if breach := await self.joint_breach(info, rid):
            self.event("access.denied", reason="joint-verdicts", tool=f.tool,
                       detail=breach)
            return Decision(outcome="deny", status=403,
                            error="joint_mandate_unsatisfied",
                            description=breach)

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
        #    An override is always single-use, whatever tool it names — the
        #    organization's clause is an exception for one act, and one act
        #    is what it gets.
        if f.tool in self.single_use_tools or (override and info.get("single_use")):
            op = info.get("operation") or {}
            actual = s256(json.dumps(f.args or {}, sort_keys=True).encode())
            if op and (op.get("tool") != f.tool or op.get("params_s256") != actual):
                self.event("access.denied", reason="operation-binding", tool=f.tool,
                           expected=op.get("params_s256"), actual=actual)
                return Decision(outcome="deny", status=403, error="operation_mismatch",
                                description="RPT authorizes a different operation")
            # 5. Only now spend it. Check-then-act, so the burn is last and
            #    atomic; losing the race means someone else got there first.
            spent = await (self.org_consume(rpt) if override else self.consume(rpt))
            if not spent:
                self.event("access.denied", reason="consume-lost-race", tool=f.tool)
                return Decision(outcome="deny", status=403, error="already_consumed",
                                description="this single-use grant was already spent")

        family = info.get("family", "?")
        self.event("access.allowed", corr=family, tool=f.tool,
                   contract=info.get("contract"),
                   single_use=info.get("single_use", False),
                   break_glass=bool(info.get("break_glass")),
                   traceparent=f.traceparent)
        summary = json.dumps(f.args or {}, sort_keys=True)
        if override:
            await self.org_report(family, f.tool, summary)
        else:
            await self.report_access(family, f.tool, summary)
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
