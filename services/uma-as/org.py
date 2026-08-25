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

import copy
import os
import time

from uma4a_org import claims_match as _claims_match

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


# Shared with the organization's own service and the enforcement point —
# see `lib/uma4a_org.py`. Re-exported here because everything else in this
# module is written in terms of it.
claims_match = _claims_match

def governs(tier: dict, envelope: dict) -> bool:
    """Whether the organization's charter reaches this tier at all.

    Any resource is enough. A tier is one terms document over a set of
    resources, so a tier that mixes a claimed resource with an unclaimed one
    cannot be half-governed — and of the two directions available, applying
    the ceiling to the whole tier is the one that cannot leak. Her portal
    says so plainly rather than leaving her to work it out.
    """
    claims = envelope.get("claims") or []
    return any(claims_match(rid, claims) for rid in tier.get("resources") or [])


def _duration(seconds) -> str:
    if not seconds:
        return "—"
    for unit, size in (("day", 86400), ("hour", 3600), ("minute", 60)):
        if seconds >= size and seconds % size == 0:
            n = seconds // size
            return f"{n} {unit}{'' if n == 1 else 's'}"
    return f"{seconds}s"


def clamp(tier: dict, envelope: dict) -> tuple[dict, list[dict]]:
    """This tier, narrowed to the organization's ceiling, and what changed.

    Pure, and every field moves in one direction only. There is no envelope
    field that can lengthen an expiry, add a scope, remove a prohibition or
    turn off an ask — which is what makes it safe to run this on every write
    and every publish without checking first whether it would help or hurt.

    The changes are returned rather than logged because two surfaces need
    them in words: her portal, which shows her what joining did to terms she
    had already written, and the compliance report, which tells the
    organization *which of its fields* bit without telling it what hers said.
    """
    if not governs(tier, envelope):
        return copy.deepcopy(tier), []

    tier = copy.deepcopy(tier)
    terms = tier["terms"]
    changes: list[dict] = []

    ceiling = envelope.get("max_expires_in")
    if ceiling and terms.get("expires_in", 0) > ceiling:
        changes.append({
            "field": "max_expires_in",
            "was": terms["expires_in"], "now": ceiling,
            "text": f"Access expires after {_duration(terms['expires_in'])} "
                    f"→ {_duration(ceiling)}",
        })
        terms["expires_in"] = ceiling

    allowed = envelope.get("allowed_scopes")
    if allowed is not None:
        dropped = [s for s in terms.get("scope") or [] if s not in allowed]
        if dropped:
            changes.append({
                "field": "allowed_scopes",
                "was": list(terms.get("scope") or []),
                "now": [s for s in terms.get("scope") or [] if s in allowed],
                "text": f"No longer offers {', '.join(dropped)} — the "
                        f"organization does not allow it",
            })
            terms["scope"] = [s for s in terms.get("scope") or [] if s in allowed]

    required = envelope.get("require_prohibited") or []
    missing = [p for p in required if p not in (terms.get("prohibited") or [])]
    if missing:
        changes.append({
            "field": "require_prohibited",
            "was": list(terms.get("prohibited") or []),
            "now": list(terms.get("prohibited") or []) + missing,
            "text": f"Always forbids {', '.join(missing)}",
        })
        terms["prohibited"] = list(terms.get("prohibited") or []) + missing

    always_ask = envelope.get("always_ask") or []
    if not tier.get("ask_me") and any(
            claims_match(rid, always_ask) for rid in tier.get("resources") or []):
        changes.append({
            "field": "always_ask", "was": False, "now": True,
            "text": "Asks you every time — the organization requires it here",
        })
        tier["ask_me"] = True

    return tier, changes


def patch_for(tier: dict, envelope: dict) -> tuple[dict | None, list[dict]]:
    """The edit that would bring a tier inside the envelope, or None.

    Returned as a patch rather than a tier so the store applies it through
    the same path as one of her own edits — which bumps the terms version and
    republishes the document. A clamp that wrote the tier directly would
    change what an agent is held to without changing the id it cites, and
    every signed agreement pointing at that id would quietly stop describing
    what it agreed to.
    """
    clamped, changes = clamp(tier, envelope)
    if not changes:
        return None, []
    terms = {
        "expires_in": clamped["terms"]["expires_in"],
        "prohibited": clamped["terms"]["prohibited"],
    }
    # Only when she had one. A tier with no `scope` should not acquire an
    # empty one because a ceiling passed over it — the patch is meant to
    # narrow what is there, not to add fields to her document.
    if "scope" in clamped["terms"]:
        terms["scope"] = clamped["terms"]["scope"]
    return {"ask_me": clamped["ask_me"], "terms": terms}, changes


def would_exceed(spec: dict, resources: list[str], envelope: dict) -> list[str]:
    """What is wrong with terms she is about to write, in her words.

    Used on the create path, where refusing is better than silently
    narrowing: a tier she asked for and did not get is something she should
    be told about at the moment she asks, not discover later in a document
    she thought she had written. Editing an existing tier clamps instead —
    there the alternative is refusing to store a policy the organization
    changed under her, which would be blaming her for someone else's edit.
    """
    if not any(claims_match(rid, envelope.get("claims") or []) for rid in resources):
        return []
    problems = []
    terms = spec.get("terms") or {}
    ceiling = envelope.get("max_expires_in")
    if ceiling and int(terms.get("expires_in") or 0) > ceiling:
        problems.append(
            f"{envelope.get('name')} caps access to these resources at "
            f"{_duration(ceiling)}; these terms ask for "
            f"{_duration(int(terms['expires_in']))}")
    allowed = envelope.get("allowed_scopes")
    if allowed is not None:
        extra = [s for s in terms.get("scope") or [] if s not in allowed]
        if extra:
            problems.append(
                f"{envelope.get('name')} does not allow {', '.join(extra)} "
                f"over these resources")
    return problems


def compliance(tiers: dict, envelope: dict, resources,
               clamped_fields=None) -> dict:
    """What her authority tells the organization, and the shape of it is the
    point: counts and field names, never a value out of her policy.

    An organization is entitled to know its ceiling is being applied to the
    resources it claims. It is not entitled to read the arrangements she
    made underneath it — if it were, the member layer would have been
    replaced rather than governed.
    """
    claims = envelope.get("claims") or []
    governed_tiers = {tid: t for tid, t in tiers.items() if governs(t, envelope)}
    # Two different questions, and conflating them was a bug worth naming.
    #
    # `within` is a property of the tiers as they stand *now* — recomputed
    # here, so it can only be false in the window between an organization's
    # edit and this server's next clamp. `clamped_fields` is a property of
    # what the clamp just did, which the caller has to hand in because by the
    # time this runs the evidence has been applied and is gone. Deriving it
    # here produced an empty list every time and told the organization that
    # its ceiling had never bitten anyone.
    outstanding = set()
    within = True
    for tier in governed_tiers.values():
        _, changes = clamp(tier, envelope)
        if changes:
            within = False
            outstanding |= {c["field"] for c in changes}
    return {
        "charter_version": envelope.get("charter_version"),
        "resources_governed": sum(1 for rid in resources if claims_match(rid, claims)),
        "tiers_governed": len(governed_tiers),
        "clamped_fields": sorted(set(clamped_fields or []) | outstanding),
        "within": within,
    }


def tier_view(tier: dict, envelope: dict | None) -> dict | None:
    """What her portal shows above a tier's own terms, when there is an
    organization above it. `None` when this tier is hers alone."""
    if not envelope or not governs(tier, envelope):
        return None
    _, changes = clamp(tier, envelope)
    return {
        "org": envelope.get("org"),
        "name": envelope.get("name"),
        "charter_version": envelope.get("charter_version"),
        "max_expires_in": envelope.get("max_expires_in"),
        "require_prohibited": list(envelope.get("require_prohibited") or []),
        "allowed_scopes": envelope.get("allowed_scopes"),
        "always_ask": any(claims_match(rid, envelope.get("always_ask") or [])
                          for rid in tier.get("resources") or []),
        # Non-empty means her stored terms are outside the ceiling right now,
        # which happens between an organization's edit and this server's next
        # clamp. Showing it is better than hiding it: the pending narrowing is
        # about to change what her agents are held to.
        "pending": [c["text"] for c in changes],
    }


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
