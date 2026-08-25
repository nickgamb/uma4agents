"""The organization above the owner, from the owner's side.

Alice can be the person whose sharing this is without being the party that
owns what is shared. A firm holds the account; she administers access to it;
the firm has obligations she cannot waive on its behalf. UMA has always had
a name for that role — resource rights administrator — and this is the layer
it implies.

Two halves, and they are different kinds of thing:

**The envelope is clamped.** A ceiling on what her terms may say is an
algebra over two documents, so it is computed here, in Python, at the moment
she edits — and the result is written into her tiers. That last part is the
design decision worth defending. The obvious alternative is to leave her
tiers alone and apply the ceiling at grant time, which is less code and is
wrong: the terms document is what an agent dereferences, reads and signs, and
a document that says 24 hours while the grant lasts one is a document that
lies to both of them. Clamping on write means what the organization requires
is *in* what the agent agreed to.

**The decision is asked for.** Whether one particular request is acceptable
to the organization is a judgement about that request, and it is made at the
organization's own decision point against policy this server never sees. Her
authority asks and folds the answer into its own.

The composition rule is one sentence: **both layers must allow, and either
may refuse.** Her policy is what permits — the organization's `allow` means
only that it has no objection. Nothing the organization returns can make a
request easier than her own tiers already make it.

And one thing that is not policy at all: **what the organization shares with
her.** The envelope carries the grants her role gives her, and the firm's
resources appear in her registry because of them. That is the half she joined
for, and it is why the ceiling is not simply an imposition — it arrives
attached to something.

The exception, and it is a real one rather than a hedge, is break-glass:
grants the organization signs itself, which do not pass through here at all.
What arrives here is the notice, and what this module does with it is put it
in front of her. See `/org/notice` in app.py.
"""

import os
import time

from uma4a_org import (claims_match as _claims_match, clamp as _clamp,
                       compliance as _compliance, governs as _governs,
                       patch_for as _patch_for, reaches as _reaches,
                       tier_view as _tier_view, would_exceed as _would_exceed)

# Where the envelope is re-read from, and how long a copy may be trusted.
#
# The second number is the interesting one. An organization that changes its
# charter should not have to wait on a member's cache to have said so — but a
# member's grant loop should not stop because the organization's service is
# restarting either. So: a short refresh, and a longer window in which a copy
# that could not be refreshed still stands. Past that window the answer is a
# refusal, because a ceiling nobody can read is not a ceiling.
ENVELOPE_TTL_S = float(os.environ.get("UMA_AS_ORG_TTL_S", "30"))
ENVELOPE_STALE_MAX_S = float(os.environ.get("UMA_AS_ORG_STALE_MAX_S", "600"))
HTTP_TIMEOUT_S = float(os.environ.get("UMA_AS_ORG_TIMEOUT_S", "5"))
CA_BUNDLE = os.environ.get("UMA4A_CA_BUNDLE")


# The pattern language and the clamp algebra both live in `lib/uma4a_org.py`
# and are re-exported here, because everything below is written in terms of
# them and because three services now need the same answers: this one, the
# organization's own, and the tally that folds several owners' terms over one
# jointly held resource. A second implementation of "narrow this document by
# that one" is a second implementation to disagree with the first.
claims_match = _claims_match
reaches = _reaches
governs = _governs
clamp = _clamp
patch_for = _patch_for
would_exceed = _would_exceed
compliance = _compliance
tier_view = _tier_view

# --- Talking to the organization ---------------------------------------------


def _httpx():
    """Imported where it is used, not at the top.

    Everything above this line is a pure function over two documents, and
    keeping it importable with nothing installed is what lets the clamp be
    unit-tested in a bare interpreter — the same way `policy.py` is. The
    client half needs a network stack; the algebra does not.
    """
    import httpx

    return httpx


class OrgClient:
    """This owner's side of the relationship with one organization.

    Holds the membership token her authority was given at enrolment, a copy
    of the envelope, and nothing else. There is no long-lived connection and
    no callback the organization can rely on: everything either party needs
    is re-read.
    """

    def __init__(self, issuer: str, token: str, envelope: dict) -> None:
        self.issuer = issuer.rstrip("/")
        self.token = token
        self.envelope = envelope
        self.fetched = time.time()
        self.failing: str | None = None

    @property
    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def stale(self) -> bool:
        return time.time() - self.fetched > ENVELOPE_TTL_S

    def unusable(self) -> bool:
        """Past the point where a copy that could not be refreshed still
        stands. A ceiling this old is not evidence of anything."""
        return time.time() - self.fetched > ENVELOPE_STALE_MAX_S

    async def refresh(self) -> tuple[dict | None, str | None]:
        """(envelope, error). A changed charter version is the caller's cue
        to re-clamp; an error is its cue to decide how long it will go on
        without one."""
        httpx = _httpx()
        try:
            async with httpx.AsyncClient(verify=CA_BUNDLE or True,
                                         timeout=HTTP_TIMEOUT_S) as c:
                r = await c.get(f"{self.issuer}/member/envelope",
                                headers=self.headers)
            if r.status_code == 403:
                # Membership ended at the organization — she was removed, or
                # this token belongs to an enrolment that no longer exists.
                return None, "membership_ended"
            r.raise_for_status()
        except httpx.HTTPError as exc:
            self.failing = str(exc)
            return None, str(exc)
        self.envelope = r.json()
        self.fetched = time.time()
        self.failing = None
        return self.envelope, None

    async def decide(self, facts: dict) -> dict:
        """Ask the organization about one request.

        Failure is a refusal, not an allow — the same direction the
        organization's own engine fails in, for the same reason. A request
        that proceeded because the layer above could not be consulted would
        be precisely the access that layer exists to prevent, and it would
        happen exactly when something is already wrong.
        """
        httpx = _httpx()
        try:
            async with httpx.AsyncClient(verify=CA_BUNDLE or True,
                                         timeout=HTTP_TIMEOUT_S) as c:
                r = await c.post(f"{self.issuer}/decision", json=facts,
                                 headers=self.headers)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as exc:
            return {"effect": "refuse", "governed": True,
                    "because": [f"your organization's authority could not be "
                                f"reached ({exc.__class__.__name__}), and its "
                                f"policy is not something a request over its "
                                f"resources may proceed without"]}

    async def report(self, summary: dict) -> None:
        httpx = _httpx()
        try:
            async with httpx.AsyncClient(verify=CA_BUNDLE or True,
                                         timeout=HTTP_TIMEOUT_S) as c:
                await c.post(f"{self.issuer}/member/compliance", json=summary,
                             headers=self.headers)
        except httpx.HTTPError:
            # Nothing depends on this landing. The organization's console
            # shows "not reported" rather than a wrong answer, and the next
            # clamp reports again.
            pass

    async def leave(self) -> None:
        httpx = _httpx()
        try:
            async with httpx.AsyncClient(verify=CA_BUNDLE or True,
                                         timeout=HTTP_TIMEOUT_S) as c:
                await c.post(f"{self.issuer}/member/leave", headers=self.headers)
        except httpx.HTTPError:
            pass


async def preview(issuer: str, code: str) -> dict:
    """What she is being asked to agree to, before she agrees to it."""
    async with _httpx().AsyncClient(verify=CA_BUNDLE or True,
                                 timeout=HTTP_TIMEOUT_S) as c:
        r = await c.post(f"{issuer.rstrip('/')}/member/preview",
                         json={"code": code})
    r.raise_for_status()
    return r.json()


async def invitation(issuer: str, owner: str) -> dict:
    """Whether the organization this authority knows about has asked for her.

    Polled rather than delivered, and it has to be: before she accepts, this
    organization has never heard of her authorization server and has nowhere
    to deliver anything. Her authority knows where to ask because she — or
    whoever set it up for her — pointed it at one.

    Unreachable is not "no invitation". It is "unknown", and the surface says
    so rather than showing her nothing.
    """
    async with _httpx().AsyncClient(verify=CA_BUNDLE or True,
                                    timeout=HTTP_TIMEOUT_S) as c:
        r = await c.get(f"{issuer.rstrip('/')}/member/invitation",
                        params={"owner": owner})
    r.raise_for_status()
    return r.json()


async def decline(issuer: str, owner: str, code: str) -> None:
    async with _httpx().AsyncClient(verify=CA_BUNDLE or True,
                                    timeout=HTTP_TIMEOUT_S) as c:
        r = await c.post(f"{issuer.rstrip('/')}/member/invitation/decline",
                         json={"owner": owner, "code": code})
    r.raise_for_status()


async def join(issuer: str, code: str, owner: str, as_uri: str) -> dict:
    async with _httpx().AsyncClient(verify=CA_BUNDLE or True,
                                 timeout=HTTP_TIMEOUT_S) as c:
        r = await c.post(f"{issuer.rstrip('/')}/member/join",
                         json={"code": code, "owner": owner, "as_uri": as_uri})
    r.raise_for_status()
    return r.json()
