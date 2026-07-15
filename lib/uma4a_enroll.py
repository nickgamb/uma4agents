"""uma4a_enroll — enroll a requesting agent with its AAuth agent server.

The identified half of the AAuth identity model: the agent holds a persisted
*stable* key (its long-term identity) and a per-session *ephemeral* key. It
registers with its principal's agent server by POSTing its stable public key
in a request signed by the ephemeral key (`hwk` scheme — bare key in
Signature-Key). First contact pends until the principal (Bob) approves; a
known stable key re-registers immediately. The issued `aa-agent+jwt` binds
`cnf.jwk` to the ephemeral key, so the same key that signs intent contracts
and proof-of-possession requests is the one the token vouches for.

Shared by the demo-driver (headless, person-approval via the PS admin API)
and the agent-shim (Bob approves in his person server's UI).
"""

import json
import time
from typing import Callable

import aauth
import httpx


class EnrollmentDenied(Exception):
    pass


def _signed(method: str, url: str, body: bytes | None, ephemeral_priv) -> dict:
    headers = {}
    if body is not None:
        headers["Content-Type"] = "application/json"
    sig = aauth.sign_request(
        method=method,
        target_uri=url,
        headers=headers,
        body=body,
        private_key=ephemeral_priv,
        sig_scheme="hwk",
    )
    return {**headers, **sig}


def enroll(
    client: httpx.Client,
    issuer: str,
    stable_key,
    ephemeral_key,
    agent_name: str,
    person_token: str | None = None,
    on_status: Callable[[str], None] = lambda s: None,
    max_wait_s: int = 300,
    poll_interval: int = 3,
) -> str:
    """Runs the AAuth registration ceremony. Returns the aa-agent+jwt.

    With `person_token` the pending approval is granted through the person
    API (the headless stand-in for Bob's tap in his person server portal);
    without it the caller waits for Bob to approve in the PS UI.
    """
    issuer = issuer.rstrip("/")
    meta = client.get(f"{issuer}/.well-known/aauth-agent.json").json()
    reg_url = meta["registration_endpoint"]

    stable_pub_jwk = aauth.public_key_to_jwk(stable_key.public_key())
    body = json.dumps({"stable_pub": stable_pub_jwk, "agent_name": agent_name}).encode()
    r = client.post(reg_url, content=body,
                    headers=_signed("POST", reg_url, body, ephemeral_key))

    if r.status_code == 200:
        # Known stable key: re-registration issues a token for this session's
        # ephemeral key with no new approval.
        on_status("agent server recognized this agent — token issued")
        return r.json()["agent_token"]
    if r.status_code != 202:
        raise EnrollmentDenied(f"register failed: {r.status_code} {r.text[:300]}")

    location = r.headers.get("location", "")
    pending_id = location.rstrip("/").split("/")[-1]
    poll_url = f"{issuer}{location}" if location.startswith("/") else location
    on_status(f"registration pending {pending_id} — awaiting the principal's approval")

    if person_token is not None:
        ar = client.post(
            f"{issuer}/person/registrations/{pending_id}/approve",
            headers={"Authorization": f"Bearer {person_token}"},
        )
        if ar.status_code != 200:
            raise EnrollmentDenied(
                f"person approval failed: {ar.status_code} {ar.text[:300]}")
        on_status("[simulated-bob] approved his agent at his person server")
    else:
        on_status(f"approve this agent in the person server UI: {issuer}/ui")

    deadline = time.time() + max_wait_s
    while time.time() < deadline:
        pr = client.get(poll_url,
                        headers=_signed("GET", poll_url, None, ephemeral_key))
        if pr.status_code == 200:
            return pr.json()["agent_token"]
        if pr.status_code == 202:
            time.sleep(poll_interval)
            continue
        raise EnrollmentDenied(
            f"registration {pending_id}: {pr.status_code} {pr.text[:300]}")
    raise EnrollmentDenied("timed out waiting for the principal's approval")
