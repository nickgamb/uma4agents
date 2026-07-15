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
import json
import re
import time
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
                  operation: dict | None = None) -> str:
    """Echo the proffered template, signed — the agreement half of the
    MyTerms exchange. Weakening any field is caught by the AS; this client
    doesn't try."""
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
    headers = {"typ": "myterms-agreement-v1+jws", "kid": keys.keyid}
    if keys.agent_token:
        headers["agent_token"] = keys.agent_token
    else:
        headers["jwk"] = keys.public_jwk()
    jws = jwt.encode(contract, keys.key, algorithm="EdDSA", headers=headers)
    return base64.urlsafe_b64encode(jws.encode()).rstrip(b"=").decode()


def run_grant(
    client: httpx.Client,
    as_uri: str,
    ticket: str,
    keys: AgentKeys,
    approve_terms: Callable[[dict], bool],
    operation: dict | None = None,
    on_status: Callable[[str], None] = lambda s: None,
    on_receipt: Callable[[str], None] = lambda r: None,
    max_wait_s: int = 120,
) -> str:
    """Walks beats 2-4. Returns the RPT; the counter-signed MyTerms receipt
    (the agent's half of the dual record) is delivered via on_receipt.
    Raises GrantDenied / TermsRejected."""
    token_url = f"{as_uri}/token"

    on_status("presenting ticket at Alice's AS")
    r = client.post(token_url, data={"grant_type": GRANT_TYPE, "ticket": ticket})
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
        claim = sign_contract(template, keys, as_uri, operation)
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


def signed_headers(method: str, authority: str, path: str, rpt: str,
                   keys: AgentKeys) -> dict[str, str]:
    """Authorization + RFC 9421 signature headers for a resource request."""
    authorization = f"PoP {rpt}"
    sig = sign(method, authority, path, authorization, keys.key, keys.keyid)
    return {"Authorization": authorization, **sig}


async def run_grant_async(
    client,  # httpx.AsyncClient
    as_uri: str,
    ticket: str,
    keys: AgentKeys,
    approve_terms,  # async Callable[[dict], bool]
    operation: dict | None = None,
    on_status: Callable[[str], None] = lambda s: None,
    on_receipt: Callable[[str], None] = lambda r: None,
    max_wait_s: int = 120,
) -> str:
    """Async twin of run_grant — the shim awaits elicitation mid-dance."""
    import asyncio

    token_url = f"{as_uri}/token"

    on_status("presenting ticket at Alice's AS")
    r = await client.post(token_url, data={"grant_type": GRANT_TYPE, "ticket": ticket})
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
        claim = sign_contract(template, keys, as_uri, operation)
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
            raise GrantDenied("timed out waiting for the owner")
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
