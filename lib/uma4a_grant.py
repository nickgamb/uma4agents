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

CONTRACT_FORMAT = "urn:uma4agents:format:intent-contract-v1+jws"
GRANT_TYPE = "urn:ietf:params:oauth:grant-type:uma-ticket"


class GrantDenied(Exception):
    pass


class TermsRejected(Exception):
    pass


@dataclass
class AgentKeys:
    """The requesting agent's signing identity (pseudonymous AAuth level:
    the bare public key rides the contract's JWS header; identified level
    adds a PS-issued agent token)."""

    key: Ed25519PrivateKey = field(default_factory=Ed25519PrivateKey.generate)
    keyid: str = "agent-req-1"
    agent_token: str | None = None  # aa-agent+jwt when PS-bootstrapped

    @classmethod
    def load_or_create(cls, path: str) -> "AgentKeys":
        import os

        if os.path.exists(path):
            with open(path, "rb") as f:
                return cls(key=serialization.load_pem_private_key(f.read(), password=None))
        keys = cls()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "wb") as f:
            f.write(
                keys.key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                )
            )
        return keys

    def public_jwk(self) -> dict:
        return json.loads(OKPAlgorithm.to_jwk(self.key.public_key()))


def parse_challenge(www_authenticate: str) -> tuple[str, str] | None:
    """Extracts (as_uri, ticket) from a WWW-Authenticate: UMA header."""
    if not www_authenticate or "UMA" not in www_authenticate:
        return None
    m_as = re.search(r'as_uri="([^"]+)"', www_authenticate)
    m_t = re.search(r'ticket="([^"]+)"', www_authenticate)
    if not (m_as and m_t):
        return None
    return m_as.group(1), m_t.group(1)


def sign_contract(template: dict, keys: AgentKeys, as_uri: str,
                  operation: dict | None = None) -> str:
    """Echo the dictated template, signed. Weakening any field is caught by
    the AS; this client doesn't try."""
    contract = {
        "iss": f"aauth:agent:{keys.keyid}",
        "aud": as_uri,
        "iat": int(time.time()),
        "template_id": template["template_id"],
        "purpose": template["purpose"],
        "scope": template["scope"],
        "expires_in": template["expires_in"],
        "prohibited": template["prohibited"],
        "nonce": template["nonce"],
        "family": template["family"],
    }
    if operation is not None:
        contract["operation"] = operation
    headers = {"typ": "intent-contract-v1+jws", "kid": keys.keyid}
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
    max_wait_s: int = 120,
) -> str:
    """Walks beats 2-4. Returns the RPT. Raises GrantDenied / TermsRejected."""
    token_url = f"{as_uri}/token"

    on_status("presenting ticket at Alice's AS")
    r = client.post(token_url, data={"grant_type": GRANT_TYPE, "ticket": ticket})
    body = r.json()

    if body.get("error") == "need_info":
        template = body["required_claims"][0]["terms_template"]
        on_status(f"terms dictated: {template['purpose']} "
                  f"(expires {template['expires_in']}s, "
                  f"prohibited: {', '.join(template['prohibited'])})")
        if not approve_terms(template):
            raise TermsRejected(template["template_id"])
        claim = sign_contract(template, keys, as_uri, operation)
        on_status("intent contract signed, committing")
        r = client.post(
            token_url,
            data={
                "grant_type": GRANT_TYPE,
                "ticket": body["ticket"],
                "claim_token": claim,
                "claim_token_format": CONTRACT_FORMAT,
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
        on_status(f"terms dictated: {template['purpose']}")
        if not await approve_terms(template):
            raise TermsRejected(template["template_id"])
        claim = sign_contract(template, keys, as_uri, operation)
        r = await client.post(
            token_url,
            data={
                "grant_type": GRANT_TYPE,
                "ticket": body["ticket"],
                "claim_token": claim,
                "claim_token_format": CONTRACT_FORMAT,
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
        return body["access_token"]
    raise GrantDenied(body.get("error_description") or body.get("error", "unknown"))
