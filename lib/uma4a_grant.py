"""uma4a_grant — the requesting-agent side of the four-beat grant loop.

Shared by the agent-shim (live Claude sessions) and the demo-driver
(headless acts). Handles: parsing the UMA challenge, presenting tickets,
receiving Alice's dictated terms, signing the intent contract with the
agent's Ed25519 key, waiting out request_submitted holds, and signing
resource requests for proof-of-possession.

Terms approval is a callback so the shim can elicit Bob inside his agent
while the driver applies his standing config.
"""

import base64
import hashlib
import json
import re
import time
from urllib.parse import urlparse
from dataclasses import dataclass, field
from typing import Callable

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from jwt.algorithms import OKPAlgorithm

from uma4a_http_sig import sign

# MyTerms-shaped agreement: the owner proffers the terms; this side signs them.
AGREEMENT_FORMAT = "urn:uma4agents:format:myterms-agreement-v1+jws"
GRANT_TYPE = "urn:ietf:params:oauth:grant-type:uma-ticket"
# The enterprise half, asked for by an authorization server whose owner is a
# member of an organization that federates identity. See `Enterprise`.
ID_JAG_FORMAT = "urn:ietf:params:oauth:token-type:id-jag"
ID_JAG_CLAIM = "urn:ietf:params:oauth:token-type:id-jag"
TOKEN_EXCHANGE = "urn:ietf:params:oauth:grant-type:token-exchange"
ID_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:id_token"
REFRESH_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:refresh_token"


@dataclass
class Enterprise:
    """What an agent running inside an enterprise application already holds.

    Nothing here is arranged with any particular authorization server, and
    that is the point: these are the credentials the application has because
    an employee signed into it and because an administrator registered it.
    An agent carrying them can satisfy an identity challenge from a server it
    has never heard of, which is what makes the exchange resource-initiated.

    `subject_token` is the employee's OpenID Connect ID token. The client
    credentials are the application's own, at the identity provider — not at
    the authorization server, which never sees them.
    """
    subject_token: str
    client_id: str
    client_secret: str = ""
    # What the subject token *is*. A real tenant exchanges the refresh token
    # from the employee's sign-in; the provider shipped beside this lab
    # exchanges an ID token. Left unset, the challenge decides — the provider
    # advertises what it will take, and an agent should not have to be
    # configured with a fact its identity provider publishes.
    subject_token_type: str = ""
    # The deployment's own CA, where an agent knows it and would rather not
    # have it discovered. Public roots are added to it either way.
    ca_bundle: str = ""


class GrantDenied(Exception):
    pass


class TermsRejected(Exception):
    pass


@dataclass
class AgentKeys:
    """The requesting agent's signing identity.

    Pseudonymous (AAuth level 0): `key` is the persisted long-term key and
    its bare public JWK rides the contract's JWS header — the key *is* the
    identity, so it must be stable across runs for the owner's standing
    connection to recognize the agent.

    Identified: `stable` is the persisted long-term key enrolled at the
    agent server; `key` is a fresh per-session ephemeral key that the issued
    aa-agent+jwt (`agent_token`) binds via cnf.jwk. Contracts and PoP
    requests are signed with the ephemeral key; identity continuity lives in
    the token's issuer+subject, not the key.
    """

    key: Ed25519PrivateKey = field(default_factory=Ed25519PrivateKey.generate)
    keyid: str = "agent-req-1"
    agent_token: str | None = None  # aa-agent+jwt when enrolled
    stable: Ed25519PrivateKey | None = None  # long-term key (identified mode)
    # Optional CIMD URL describing who operates this agent. Display metadata
    # for the owner's approval dialog, never an authorization input.
    client_id: str | None = None
    # Optional Web Bot Auth directory URL, covered by the request signature.
    signature_agent: str | None = None

    def publish(self, client, operator_origin: str) -> str | None:
        """Publish the signing key to the operator's Web Bot Auth directory.

        Returns the `Signature-Agent` value to send, or None if the directory
        is unreachable — discovery is additive, so a resource that cannot
        resolve it still verifies against the key in the RPT's `cnf`. The
        directory never becomes the authority; it only lets a stranger's
        authorization server attribute a key it has never seen before.
        """
        try:
            r = client.post(f"{operator_origin}/register",
                            json={"keyid": self.keyid, "jwk": self.public_jwk()},
                            timeout=5.0)
            r.raise_for_status()
            return f"{operator_origin}/.well-known/http-message-signatures-directory"
        except Exception:
            return None

    @staticmethod
    def _load_or_create_key(path: str) -> Ed25519PrivateKey:
        import os

        if os.path.exists(path):
            with open(path, "rb") as f:
                return serialization.load_pem_private_key(f.read(), password=None)
        key = Ed25519PrivateKey.generate()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "wb") as f:
            f.write(
                key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                )
            )
        return key

    @classmethod
    def load_or_create(cls, path: str) -> "AgentKeys":
        """Pseudonymous identity: one persisted signing key."""
        return cls(key=cls._load_or_create_key(path))

    @classmethod
    def load_or_create_identified(cls, path: str) -> "AgentKeys":
        """Identified identity: persisted stable key + fresh session key.
        Enroll with uma4a_enroll.enroll() to obtain the agent_token."""
        return cls(key=Ed25519PrivateKey.generate(),
                   stable=cls._load_or_create_key(path))

    def public_jwk(self) -> dict:
        return json.loads(OKPAlgorithm.to_jwk(self.key.public_key()))

    def connection_handle(self) -> str:
        """The handle the owner's authority will file this agent under.

        Mirrors `connection_handle` on the authorization server, and the
        requesting side can compute it because both halves are things it
        already holds. Worth having here rather than open-coded by every
        caller that wants to find its own row: two copies of an RFC 7638
        thumbprint is two chances to disagree with the server about who this
        agent is.

        An identified agent is its issuer-qualified subject, because its
        session key rotates. A pseudonymous one *is* its key.
        """
        if self.agent_token:
            claims = jwt.decode(self.agent_token, options={"verify_signature": False})
            sub, host = claims.get("sub", ""), urlparse(claims.get("iss", "")).netloc
            return sub if sub.endswith(f"@{host}") else f"{sub}@{host}"
        jwk = self.public_jwk()
        canonical = json.dumps({"crv": jwk["crv"], "kty": jwk["kty"], "x": jwk["x"]},
                               separators=(",", ":"), sort_keys=True)
        return "jkt:" + base64.urlsafe_b64encode(
            hashlib.sha256(canonical.encode()).digest()).rstrip(b"=").decode()


@dataclass
class Challenge:
    """A parsed WWW-Authenticate: UMA challenge. `resource_metadata` is the
    RFC 9728 pointer the resource may add so the client can corroborate
    `as_uri` against the resource's own published metadata."""

    as_uri: str
    ticket: str
    resource_metadata: str | None = None

    def __iter__(self):  # (as_uri, ticket) unpacking still works
        return iter((self.as_uri, self.ticket))


def parse_challenge(www_authenticate: str) -> Challenge | None:
    """Parses a WWW-Authenticate: UMA header."""
    if not www_authenticate or "UMA" not in www_authenticate:
        return None
    m_as = re.search(r'as_uri="([^"]+)"', www_authenticate)
    m_t = re.search(r'ticket="([^"]+)"', www_authenticate)
    if not (m_as and m_t):
        return None
    m_rm = re.search(r'resource_metadata="([^"]+)"', www_authenticate)
    return Challenge(m_as.group(1), m_t.group(1),
                     m_rm.group(1) if m_rm else None)


def well_known_prm_url(resource_url: str) -> str:
    """RFC 9728 §3: the metadata URL is formed by inserting the well-known
    path between host and any resource path component."""
    u = httpx.URL(resource_url)
    port = f":{u.port}" if u.port else ""
    path = u.path.rstrip("/")
    return (f"{u.scheme}://{u.host}{port}"
            f"/.well-known/oauth-protected-resource{path}")


class DiscoveryMismatch(Exception):
    """The resource's published metadata contradicts what the client was
    told — wrong `resource` value, or a challenge naming an AS the resource
    never published."""


def validate_resource_metadata(doc: dict, resource_url: str,
                               as_uri: str | None = None) -> dict:
    """RFC 9728 §3.3 client validation: the `resource` value must identify
    the resource being accessed. When a challenge is in hand, its as_uri
    must be among the published authorization_servers — the TLS-anchored
    metadata corroborates the (unauthenticated) challenge header."""
    if doc.get("resource") != resource_url:
        raise DiscoveryMismatch(
            f"metadata is for {doc.get('resource')!r}, not {resource_url!r}")
    if as_uri is not None and as_uri not in doc.get("authorization_servers", []):
        raise DiscoveryMismatch(
            f"challenge names AS {as_uri}, which the resource's metadata "
            f"does not publish ({doc.get('authorization_servers')})")
    return doc


def sign_contract(template: dict, keys: AgentKeys, as_uri: str,
                  operation: dict | None = None,
                  reason: str | None = None,
                  mission: dict | None = None) -> str:
    """Echo the proffered template, signed — the agreement half of the
    MyTerms exchange. Weakening any field is caught by the AS; this client
    doesn't try.

    Everything above `operation` is the owner's, repeated. `operation` and
    `reason` are the only things the requesting side contributes: what it
    proposes to do, and why it says it is asking. The owner's authority never
    compares `reason` to anything — it is carried so a person can read it and
    so the agent has signed it."""
    contract = {
        "iss": f"aauth:agent:{keys.keyid}",
        "aud": as_uri,
        "iat": int(time.time()),
        "template_id": template["template_id"],
        "terms_uri": template["terms_uri"],
        "purpose": template["purpose"],
        "scope": template["scope"],
        "expires_in": template["expires_in"],
        "prohibited": template["prohibited"],
        "nonce": template["nonce"],
        "family": template["family"],
    }
    if operation is not None:
        contract["operation"] = operation
    if reason:
        contract["reason"] = reason
    # An AAuth mission reference, in AAuth's own shape: the person server that
    # approved it, and the content hash of what was approved. Carried rather
    # than invented — `approver` and `s256` are the fields the
    # `AAuth-Mission` request header already uses.
    if mission:
        contract["mission"] = mission
    headers = {"typ": "myterms-agreement-v1+jws", "kid": keys.keyid}
    if keys.agent_token:
        headers["agent_token"] = keys.agent_token
    else:
        headers["jwk"] = keys.public_jwk()
    # Client ID Metadata Document (draft-ietf-oauth-client-id-metadata-document),
    # the mechanism MCP now prefers over Dynamic Client Registration. Here it
    # is applied to the requesting *agent*: a URL the owner's AS can resolve to
    # a human-readable operator, name and policy. Purely descriptive — the
    # connection is still keyed by the agent's key or its verified issuer, so
    # this never becomes an authorization input.
    if keys.client_id:
        headers["client_id"] = keys.client_id
    # Where the operator publishes the keys its agents sign with. Naming the
    # directory here lets the owner's authorization server check, for itself,
    # that the operator has published *this* key — turning "a firm says it
    # operates this agent" into "that firm published this agent's key". It is
    # still not an authorization input on its own: the connection is keyed by
    # the agent's key or its verified issuer, and a directory the AS cannot
    # resolve simply leaves the claim where it was.
    if keys.signature_agent:
        headers["signature_agent"] = keys.signature_agent
    jws = jwt.encode(contract, keys.key, algorithm="EdDSA", headers=headers)
    return base64.urlsafe_b64encode(jws.encode()).rstrip(b"=").decode()


_PROVIDER_TRUST: dict = {}

# Where a deployment's own CA is conventionally mounted. Consulted only after
# the caller and the environment have both been asked.
_LAB_CA_PATHS = ("/driver/rootCA.pem", "/certs/rootCA.pem")


def provider_trust(ca_bundle: str = ""):
    """What to verify an identity provider's TLS against.

    An agent's own client is configured for the resource server it came to
    talk to, which in a private deployment means a private CA and *only* that
    CA. An identity provider is the one party in this exchange that may
    legitimately be somewhere else, with an ordinary public certificate — so
    the exchange gets a trust store with the public roots *and* whatever
    private CA the agent was given.

    Both halves matter, and dropping either breaks a different deployment.
    Public roots alone cannot verify a provider inside the lab; a private CA
    alone cannot verify a real tenant, and fails as `CERTIFICATE_VERIFY_FAILED`
    at the moment the agent leaves the deployment — which reads like the
    provider being unreachable rather than like a trust store that was never
    going to work.
    """
    import os

    private = (ca_bundle
               or os.environ.get("UMA4A_CA_BUNDLE")
               or os.environ.get("UMA4A_CACERT") or "")
    if not private or not os.path.exists(private):
        private = next((p for p in _LAB_CA_PATHS if os.path.exists(p)), "")
    if private in _PROVIDER_TRUST:
        return _PROVIDER_TRUST[private]

    if not private:
        _PROVIDER_TRUST[private] = True          # public roots only
        return True
    try:
        import certifi
        combined = "/tmp/u4a-agent-provider-trust.pem"
        with open(combined, "w") as out:
            out.write(open(certifi.where()).read())
            out.write("\n")
            out.write(open(private).read())
        _PROVIDER_TRUST[private] = combined
    except Exception:                                           # noqa: BLE001
        # No public roots to be had; a provider inside the deployment still
        # verifies, which is the shipped arrangement.
        _PROVIDER_TRUST[private] = private
    return _PROVIDER_TRUST[private]


def identity_ask(body: dict) -> dict | None:
    """The identity requirement in a `need_info`, if that is what it is."""
    for claim in body.get("required_claims") or []:
        if claim.get("claim_type") == ID_JAG_CLAIM:
            return claim
    return None


def id_jag_request(ask: dict, enterprise: "Enterprise") -> tuple[str, dict]:
    """Where to go and what to ask for, taken from what the server said.

    Every field but the credentials comes out of the challenge. The agent
    contributes who it is; the resource side contributes everything about
    where it will be honoured.
    """
    idp = ask.get("identity_provider") or {}
    endpoint = idp.get("token_endpoint") or f"{idp.get('issuer', '').rstrip('/')}/token"
    return endpoint, {
        "grant_type": idp.get("grant_type") or TOKEN_EXCHANGE,
        "requested_token_type": idp.get("requested_token_type") or ID_JAG_FORMAT,
        "subject_token": enterprise.subject_token,
        "subject_token_type": (
            enterprise.subject_token_type
            or (ask.get("identity_provider") or {}).get(
                "subject_token_types_supported", [ID_TOKEN_TYPE])[0]),
        "audience": ask.get("audience") or "",
        "resource": ask.get("resource") or "",
        "scope": " ".join(ask.get("scope") or []),
        "client_id": enterprise.client_id,
        "client_secret": enterprise.client_secret,
    }


def id_jag_from(response) -> str:
    body = response.json()
    if response.status_code != 200:
        raise GrantDenied(
            "the identity provider would not assert this: "
            + (body.get("error_description") or body.get("error", "unknown")))
    if body.get("issued_token_type") != ID_JAG_FORMAT:
        raise GrantDenied(
            f"the identity provider issued {body.get('issued_token_type')!r}, "
            f"not an identity assertion")
    return body["access_token"]


def run_grant(
    client: httpx.Client,
    as_uri: str,
    ticket: str,
    keys: AgentKeys,
    approve_terms: Callable[[dict], bool],
    operation: dict | None = None,
    reason: str | None = None,
    mission: dict | None = None,
    on_status: Callable[[str], None] = lambda s: None,
    on_receipt: Callable[[str], None] = lambda r: None,
    max_wait_s: int = 120,
    enterprise: "Enterprise | None" = None,
) -> str:
    """Walks beats 2-4. Returns the RPT; the counter-signed MyTerms receipt
    (the agent's half of the dual record) is delivered via on_receipt.
    Raises GrantDenied / TermsRejected."""
    token_url = f"{as_uri}/token"

    on_status("presenting ticket at Alice's AS")
    r = client.post(token_url, data={"grant_type": GRANT_TYPE, "ticket": ticket})
    body = r.json()

    # Beat 1a: the server wants to know whose agent this is before it will
    # say anything about terms. Nothing was arranged in advance — where to go
    # and what to ask for are both in what it just said.
    if (ask := identity_ask(body)) is not None:
        if enterprise is None:
            raise GrantDenied(
                "this resource is governed by an organization that federates "
                "identity, and this agent carries no enterprise credentials")
        endpoint, payload = id_jag_request(ask, enterprise)
        on_status(f"identity required — exchanging at {endpoint}")
        # A client of its own, trusting the provider's world as well as this
        # deployment's — see `provider_trust`.
        with httpx.Client(verify=provider_trust(enterprise.ca_bundle),
                          timeout=30.0) as idp:
            assertion = id_jag_from(idp.post(endpoint, data=payload))
        on_status("assertion obtained, presenting it")
        r = client.post(token_url, data={"grant_type": GRANT_TYPE,
                                         "ticket": body["ticket"],
                                         "claim_token": assertion,
                                         "claim_token_format": ID_JAG_FORMAT})
        body = r.json()

    if body.get("error") == "need_info":
        template = body["required_claims"][0]["terms_template"]
        on_status(f"terms proffered: {template['purpose']} "
                  f"(expires {template['expires_in']}s, "
                  f"prohibited: {', '.join(template['prohibited'])})")
        if not approve_terms(template):
            # Refusals are records too (the owner's ledger notes the decline).
            client.post(token_url, data={"grant_type": GRANT_TYPE,
                                         "ticket": body["ticket"],
                                         "decline": "true"})
            raise TermsRejected(template["template_id"])
        claim = sign_contract(template, keys, as_uri, operation, reason, mission)
        on_status("agreement signed, committing")
        r = client.post(
            token_url,
            data={
                "grant_type": GRANT_TYPE,
                "ticket": body["ticket"],
                "claim_token": claim,
                "claim_token_format": AGREEMENT_FORMAT,
            },
        )
        body = r.json()

    deadline = time.time() + max_wait_s
    while body.get("error") == "request_submitted":
        on_status("Alice has been asked — holding the ticket")
        if time.time() > deadline:
            raise GrantDenied("timed out waiting for the owner")
        time.sleep(body.get("interval", 3))
        r = client.post(
            token_url, data={"grant_type": GRANT_TYPE, "ticket": body["ticket"]}
        )
        body = r.json()

    if "access_token" in body:
        on_status("grant issued")
        if body.get("receipt"):
            on_receipt(body["receipt"])
        return body["access_token"]
    raise GrantDenied(body.get("error_description") or body.get("error", "unknown"))


def traceparent() -> str | None:
    """A W3C Trace Context header for this call, if tracing is on.

    Correlation inside this system is the negotiation family; traceparent is
    what lets that join a trace spanning the requesting org, the resource, and
    the owner's authorization server — three parties who share no other id.
    """
    import os
    import secrets

    if os.environ.get("UMA4A_TRACING", "1") in ("0", "false", "no"):
        return None
    return f"00-{secrets.token_hex(16)}-{secrets.token_hex(8)}-01"


def signed_headers(method: str, authority: str, path: str, rpt: str,
                   keys: AgentKeys) -> dict[str, str]:
    """Authorization + RFC 9421 signature headers for a resource request.

    When the agent has published its key, the signature also covers a Web Bot
    Auth `Signature-Agent` header naming the directory. That composes with
    proof-of-possession rather than competing with it: the key that *verifies*
    is still the one bound into the RPT's `cnf`, and the directory only says
    where that key was published.
    """
    authorization = f"PoP {rpt}"
    sig = sign(method, authority, path, authorization, keys.key, keys.keyid,
               signature_agent=keys.signature_agent, tag="web-bot-auth")
    headers = {"Authorization": authorization, **sig}
    # W3C Trace Context: deliberately *not* covered by the signature. It is
    # diagnostic metadata a proxy may legitimately rewrite, and binding it
    # into the signature base would make ordinary tracing look like tampering.
    if tp := traceparent():
        headers["traceparent"] = tp
    return headers


async def run_grant_async(
    client,  # httpx.AsyncClient
    as_uri: str,
    ticket: str,
    keys: AgentKeys,
    approve_terms,  # async Callable[[dict], bool]
    operation: dict | None = None,
    reason: str | None = None,
    mission: dict | None = None,
    on_status: Callable[[str], None] = lambda s: None,
    on_receipt: Callable[[str], None] = lambda r: None,
    max_wait_s: int = 120,
    enterprise: "Enterprise | None" = None,
    on_pending=None,   # async Callable[[dict], bool] | None
) -> str:
    """Async twin of run_grant — the shim awaits elicitation mid-dance.

    `on_pending` is called each time the owner's decision is still outstanding,
    with the pend's details, and returns whether to keep waiting. It exists so
    the requesting side does not have to *block* through someone else's
    decision: a caller that can express waiting to its own user (MCP's
    input_required) hands the question up instead of holding the call open.
    Omit it and the loop polls to `max_wait_s`, which is what a headless
    driver wants.
    """
    import asyncio

    token_url = f"{as_uri}/token"

    on_status("presenting ticket at Alice's AS")
    r = await client.post(token_url, data={"grant_type": GRANT_TYPE, "ticket": ticket})
    body = r.json()

    if (ask := identity_ask(body)) is not None:
        if enterprise is None:
            raise GrantDenied(
                "this resource is governed by an organization that federates "
                "identity, and this agent carries no enterprise credentials")
        endpoint, payload = id_jag_request(ask, enterprise)
        on_status(f"identity required — exchanging at {endpoint}")
        async with httpx.AsyncClient(verify=provider_trust(enterprise.ca_bundle),
                                     timeout=30.0) as idp:
            assertion = id_jag_from(await idp.post(endpoint, data=payload))
        on_status("assertion obtained, presenting it")
        r = await client.post(token_url, data={"grant_type": GRANT_TYPE,
                                               "ticket": body["ticket"],
                                               "claim_token": assertion,
                                               "claim_token_format": ID_JAG_FORMAT})
        body = r.json()

    if body.get("error") == "need_info":
        template = body["required_claims"][0]["terms_template"]
        on_status(f"terms proffered: {template['purpose']}")
        if not await approve_terms(template):
            # Refusals are records too (the owner's ledger notes the decline).
            await client.post(token_url, data={"grant_type": GRANT_TYPE,
                                               "ticket": body["ticket"],
                                               "decline": "true"})
            raise TermsRejected(template["template_id"])
        claim = sign_contract(template, keys, as_uri, operation, reason, mission)
        r = await client.post(
            token_url,
            data={
                "grant_type": GRANT_TYPE,
                "ticket": body["ticket"],
                "claim_token": claim,
                "claim_token_format": AGREEMENT_FORMAT,
            },
        )
        body = r.json()

    deadline = time.time() + max_wait_s
    while body.get("error") == "request_submitted":
        on_status("Alice has been asked — holding the ticket")
        if time.time() > deadline:
            if on_pending is None:
                raise GrantDenied("timed out waiting for the owner")
            # Hand the wait up rather than deciding to abandon it here: only
            # the requesting human knows whether this is still worth waiting
            # for. Answering resets the window.
            if not await on_pending({
                "as_uri": as_uri,
                "interval": body.get("interval", 3),
                "waited_s": max_wait_s,
                # The live ticket, so a caller that hands the wait back to its
                # own client can come back to *this* pend later instead of
                # starting a second one. Without it the only way to retry is a
                # fresh negotiation, which asks the owner the same question
                # twice and leaves the first one orphaned in her queue.
                "ticket": body["ticket"],
            }):
                raise GrantDenied("the requesting side stopped waiting for the owner")
            deadline = time.time() + max_wait_s
        await asyncio.sleep(body.get("interval", 3))
        r = await client.post(
            token_url, data={"grant_type": GRANT_TYPE, "ticket": body["ticket"]}
        )
        body = r.json()

    if "access_token" in body:
        on_status("grant issued")
        if body.get("receipt"):
            on_receipt(body["receipt"])
        return body["access_token"]
    raise GrantDenied(body.get("error_description") or body.get("error", "unknown"))


# --- The MCP envelope --------------------------------------------------------
#
# Every driver in this repo was carrying its own copy of the 2026-07-28 framing:
# the protocol version, the two routing headers, the Accept that admits an SSE
# body, and the unwrapping of `data:` frames. Six copies of the one thing the
# spec revision most recently changed, and the one thing a future revision will
# change again.

MCP_PROTOCOL_VERSION = "2026-07-28"


def mcp_meta(client_name: str, version: str = "0.1") -> dict:
    return {
        "io.modelcontextprotocol/protocolVersion": MCP_PROTOCOL_VERSION,
        "io.modelcontextprotocol/clientCapabilities": {},
        "io.modelcontextprotocol/clientInfo": {"name": client_name, "version": version},
    }


def mcp_call(client, url: str, method: str, params: dict, meta: dict,
             headers: dict | None = None, timeout: float = 30.0):
    """One JSON-RPC call over MCP streamable-http. Returns the parsed response.

    `Mcp-Method` and `Mcp-Name` are sent because SEP-2243 requires them on
    2026-07-28, and because an enforcement point is entitled to route on them —
    it must also reconcile them against the body, which is why they are set
    from the same values rather than passed in separately.
    """
    p = dict(params)
    p["_meta"] = meta
    h = {
        "content-type": "application/json",
        "accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
        "Mcp-Method": method,
    }
    if method == "tools/call":
        h["Mcp-Name"] = params.get("name", "")
    h.update(headers or {})
    r = client.post(url, json={"jsonrpc": "2.0", "method": method, "id": 1,
                               "params": p}, headers=h, timeout=timeout)
    return r


def mcp_json(response) -> dict:
    """The JSON body, whether it arrived plain or as a single SSE frame."""
    body = response.text
    for line in body.splitlines():
        if line.startswith("data:"):
            body = line[5:].strip()
    return json.loads(body)
