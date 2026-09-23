"""U4A as an ability of a personal AI.

The ability is small, and that is the finding rather than a shortcut. U4A
already puts the deciding authority on the owner's side and already lets her
authenticate to it with a key she holds, so a personal AI does not need to
implement any of the protocol to become her consent surface. It needs to do
two things: hold her key, and ask her.

Everything below is those two things. The grant, the terms, the ticket, the
proof-of-possession and the ledger are the authority's job and are untouched.

    Host                    Ability                    Her authority
    ----                    -------                    -------------
    holds her key    -->    signs owner-API      -->   verifies one
                            requests (RFC 9421)        public key
    asks her         <--    "this agent wants
                             to sell 40 VTI"
                     -->    approve / deny       -->   grant, or refusal

The `Host` protocol below is what this needs from a personal AI. It is
deliberately four methods: anything larger would be this project's opinion
leaking into someone else's runtime.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol

sys.path.insert(0, "lib")

import httpx  # noqa: E402

from uma4a_http_sig import sign as http_sign  # noqa: E402


class Host(Protocol):
    """What this ability needs from the personal AI running it.

    A host that can do these four things can host the owner's authority. Any
    of them may be backed by whatever the platform already has — a secure
    enclave for the key, a chat turn for the question, the OS keychain for
    storage.
    """

    def sign(self, payload: bytes) -> bytes:
        """Sign with her key. The key does not leave the host."""

    def public_key_pem(self) -> bytes:
        """Her public key, to enrol with an authority once."""

    def ask(self, question: "Request") -> bool:
        """Put a decision in front of her and wait. True approves.

        May block for as long as it takes. The negotiation on the other side
        is holding a ticket, not a connection, so an answer tomorrow is still
        an answer.
        """

    def log(self, event: str, detail: dict[str, Any]) -> None:
        """Whatever the platform does with a record."""


@dataclass
class Request:
    """One thing waiting on her, as a person would need it described."""

    family: str
    kind: str                  # "connection" (first contact) or "operation"
    tier: str
    purpose: str
    agent: str
    operation: dict | None     # tool + the exact arguments, for ask-me tiers
    prohibited: list[str]

    @classmethod
    def from_pending(cls, p: dict) -> "Request":
        return cls(
            family=p["family"],
            kind=p.get("kind", "operation"),
            tier=p.get("tier", ""),
            purpose=p.get("purpose", ""),
            agent=str(p.get("identity", "")),
            operation=p.get("operation"),
            prohibited=p.get("prohibited", []) or [],
        )

    def summary(self) -> str:
        """One line a person can act on, without knowing any of the protocol."""
        if self.kind == "connection":
            return f"An agent you have not met wants access: {self.purpose}"
        if self.operation:
            args = json.dumps(self.operation.get("params", {}))
            return f"{self.operation.get('tool')}({args}) — {self.purpose}"
        return self.purpose


class OwnerAuthority:
    """The ability itself."""

    def __init__(self, host: Host, authority_url: str, authority_name: str,
                 auto_approve_tiers: tuple[str, ...] = ()) -> None:
        self.host = host
        self.url = authority_url.rstrip("/")
        # Taken from configuration, never from a response. An authority read
        # off the wire is an authority whoever is on the wire chooses.
        self.name = authority_name
        self.auto = set(auto_approve_tiers)

    # -- talking to her authority ------------------------------------------

    def _call(self, client: httpx.Client, method: str, path: str,
              body: dict | None = None) -> httpx.Response:
        # Sign the bytes that are sent, not an equivalent serialisation of
        # them. A decision endpoint's meaning is in its body, so the body is
        # covered by a Content-Digest — without it an intermediary can leave
        # the signature intact and change the answer.
        raw = json.dumps(body).encode() if body is not None else None
        headers = http_sign(
            method=method, authority=self.name, path=path, authorization="",
            key=_HostKey(self.host), keyid="owner", body=raw,
        )
        if raw is not None:
            headers["Content-Type"] = "application/json"
        return client.request(method, f"{self.url}{path}", headers=headers,
                              content=raw, timeout=15.0)

    def pending(self, client: httpx.Client) -> list[Request]:
        r = self._call(client, "GET", "/owner/pending")
        r.raise_for_status()
        return [Request.from_pending(p) for p in r.json()]

    def decide(self, client: httpx.Client, family: str, approved: bool) -> str:
        """Send her answer. "sent", "moot", "refused" or "retry".

        Moot is her authority saying nothing is pending under that family any
        more — somebody else answered, or it expired — and there is nothing
        left to send. Retry is her authority unreachable or failing: the
        answer is hers and it is kept, so it is sent again rather than asked
        again. Refused is her authority declining this request — a key it does
        not recognise, a body it will not take — which sending again every
        two seconds will not change.
        """
        try:
            r = self._call(client, "POST", f"/owner/pending/{family}/decision",
                           {"decision": "approved" if approved else "denied"})
        except httpx.HTTPError as exc:
            self.host.log("decision.unsent", {"family": family, "error": str(exc)})
            return "retry"
        if r.status_code == 404:
            self.host.log("decision.moot", {"family": family})
            return "moot"
        if r.status_code >= 500:
            self.host.log("decision.unsent", {"family": family,
                                              "status": r.status_code})
            return "retry"
        if r.status_code >= 300:
            self.host.log("decision.refused", {"family": family,
                                               "status": r.status_code,
                                               "detail": r.text[:200]})
            return "refused"
        return "sent"

    def enrol(self) -> bytes:
        """Her public key, for the one-time enrolment with an authority."""
        return self.host.public_key_pem()

    # -- the loop ----------------------------------------------------------

    def run(self, poll_seconds: float = 2.0,
            should_stop: Callable[[], bool] | None = None,
            client: httpx.Client | None = None) -> None:
        """Answer requests as they arrive, for as long as the host runs it.

        A poll, because it is the smallest thing that works and it makes no
        demand of the host's event model. Her authority also publishes a
        stream at /owner/events, which a host with a socket to spare should
        prefer.

        `client` is the host's, when it has one. Making our own here was a
        bug worth keeping a note about: a fresh httpx client trusts only the
        system roots, so against an authority behind a private CA every poll
        failed, and the ability sat quietly doing nothing. The host knows how
        to reach the network; it should be the one that says so.
        """
        seen: set[str] = set()
        # Answers she gave that her authority has not yet recorded, with the
        # record to write once it has. A family is marked seen when she is
        # asked, so without this an answer lost to one failed request was
        # never sent again — and was logged as decided while the request
        # went on waiting for her.
        unsent: dict[str, tuple[bool, str, dict]] = {}
        owned = client is None
        client = client or httpx.Client()

        def send(family: str, approved: bool, record: str, detail: dict) -> None:
            outcome = self.decide(client, family, approved)
            if outcome == "retry":
                unsent[family] = (approved, record, detail)
                return
            unsent.pop(family, None)
            if outcome == "sent":
                self.host.log(record, detail)

        try:
            while not (should_stop and should_stop()):
                for family, (approved, record, detail) in list(unsent.items()):
                    send(family, approved, record, detail)
                try:
                    waiting = self.pending(client)
                except httpx.HTTPStatusError as exc:
                    # Reached, and refused. Almost always configuration — an
                    # authority name or an enrolled key that does not match —
                    # and it has to say so, not that the network is down.
                    self.host.log("authority.refused", {
                        "status": exc.response.status_code,
                        "detail": exc.response.text[:200]})
                    time.sleep(poll_seconds)
                    continue
                except Exception as exc:                       # noqa: BLE001
                    self.host.log("authority.unreachable", {"error": str(exc)})
                    time.sleep(poll_seconds)
                    continue

                for req in waiting:
                    if req.family in seen:
                        continue
                    seen.add(req.family)
                    # A standing answer covers operations at a tier, never an
                    # agent's first contact: meeting a stranger is hers to
                    # decide, whatever the tier would otherwise allow.
                    if req.tier in self.auto and req.kind != "connection":
                        send(req.family, True, "decided.standing",
                             {"family": req.family, "tier": req.tier})
                        continue
                    self.host.log("asking", {"family": req.family,
                                             "summary": req.summary()})
                    approved = self.host.ask(req)
                    send(req.family, approved, "decided",
                         {"family": req.family, "approved": approved})

                time.sleep(poll_seconds)
        finally:
            if owned:
                client.close()


class _HostKey:
    """Adapts a `Host` to the signing interface `uma4a_http_sig` expects.

    The signer only ever calls `.sign(bytes)`, which is the whole reason this
    works against a key the host will not hand over: an enclave, a passkey, a
    hardware token. Nothing here ever sees private key material.
    """

    def __init__(self, host: Host) -> None:
        self._host = host

    def sign(self, data: bytes) -> bytes:
        return self._host.sign(data)
