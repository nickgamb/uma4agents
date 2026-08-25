"""The charter's pattern language, in one place.

An organization writes `*/get_positions` once and three different pieces of
software have to agree on what it matches: the organization's own service,
which decides whether a resource is claimed at all; a member's authorization
server, which clamps her terms to the ceiling; and the enforcement point in
front of the resource, which checks independently that the ceiling held.

Two of those are Python and one is Rego, so exact agreement cannot be had by
sharing code alone — `glob.match(pattern, ["/"], resource_id)` in `org.rego`
is the fourth evaluator and the one this has to match. Hence the deliberate
shape below: a segment at a time, `*` stopping at the separator, no
alternatives and no recursive wildcard. A pattern language small enough that
two implementations of it can be checked against each other by reading them.

Kept in `lib/` rather than beside any one service for the same reason
`uma4a_http_sig` is: every party to this arrangement needs it, and a copy in
each is a copy that drifts.

The same argument brought the clamp algebra here. Narrowing one terms
document by another started as an organization applying a ceiling to a
member, and it turned out to be the same operation as folding several
co-owners' terms over one jointly held resource: take the shorter expiry,
the smaller set of scopes, the union of the prohibitions, and ask if either
side asks. Written twice it would be two chances to disagree about what
"narrower" means, in the two places where disagreeing is worst.

Everything here is a pure function over dictionaries and imports nothing
that needs installing, which is what lets `lib/test_org.py` and
`lib/test_joint.py` check it in a bare interpreter.
"""

import copy
import fnmatch

# Belt-and-braces slack when an enforcement point compares a grant's
# remaining life against the organization's ceiling. The authority computed
# the expiry from its own clock; the enforcement point is reading it on
# another. Seconds, and small: this exists so that clock skew is not read as
# a policy breach, not to give anything room.
CLOCK_SLACK_S = 5


def claims_match(resource_id: str, patterns) -> bool:
    """Whether a resource id falls under any of these charter patterns.

    Segment-wise, so `*` stops at the `/`: `*/get_positions` matches
    `alice-vault/get_positions` and `carol-vault/get_positions` — which is
    the point of the globs, since a firm's charter is written once and every
    member's resources live in a namespace of her own — and does not match
    `alice-vault/nested/get_positions`.
    """
    segments = resource_id.split("/")
    for pattern in patterns or []:
        parts = pattern.split("/")
        if len(parts) == len(segments) and all(
                fnmatch.fnmatchcase(s, p) for s, p in zip(segments, parts)):
            return True
    return False


def envelope_breach(permission: dict, envelope: dict, remaining_s: float) -> str | None:
    """Whether a grant sits outside the organization's ceiling, and how.

    The half of the envelope that is checkable from a token alone, which is
    less than the whole of it and worth being exact about. How long access
    lasts and what it reaches are in the grant; the prohibitions a charter
    requires and the approvals it insists on are in the *terms*, and a token
    carries only a hash of those. So an enforcement point can prove the
    ceiling held on expiry and scope, and cannot prove it held on the rest.

    That is not a gap so much as the division of labour: the member's
    authority writes the whole ceiling into the terms document, where the
    agent reads and signs it, and this catches the part that would still be
    visible if that authority had never applied it at all.
    """
    ceiling = envelope.get("max_expires_in")
    if ceiling and remaining_s > ceiling + CLOCK_SLACK_S:
        return (f"the grant has {int(remaining_s)}s left, past the "
                f"{ceiling}s ceiling {envelope.get('name')} sets for this "
                f"resource")
    allowed = envelope.get("allowed_scopes")
    if allowed is not None:
        extra = [s for s in permission.get("resource_scopes") or []
                 if s not in allowed]
        if extra:
            return (f"the grant carries {', '.join(extra)}, which "
                    f"{envelope.get('name')} does not allow for this resource")
    return None


def reaches(resource_id: str, envelope: dict) -> bool:
    """Whether an organization may touch this resource, for this owner.

    Its claims say what it owns. This says what it may reach *here*, which is
    less by one rule: **a resource the owner holds jointly with somebody else
    is outside every organization's reach**, whatever any charter claims.

    Her co-owner never enrolled with that organization, was never shown its
    charter, and cannot leave it — so she cannot enrol, on her own, something
    that is half his. Without this an organization's administrator could see
    and answer requests over a jointly held account, and its ceiling narrowed
    the terms an agent was held to there. Both were reachable and both were
    demonstrated.

    The charter side is guarded too — a claim has to name a concrete
    namespace — but that only stops the accident. This stops the deliberate
    one, and it is the check the co-owner's safety actually rests on, because
    it lives at the authority of the person being asked rather than in the
    document of the party doing the asking.
    """
    if resource_id in (envelope.get("excluded") or ()):
        return False
    return claims_match(resource_id, envelope.get("claims") or [])


def governs(tier: dict, envelope: dict) -> bool:
    """Whether the organization's charter reaches this tier at all.

    Any resource is enough. A tier is one terms document over a set of
    resources, so a tier that mixes a claimed resource with an unclaimed one
    cannot be half-governed — and of the two directions available, applying
    the ceiling to the whole tier is the one that cannot leak. Her portal
    says so plainly rather than leaving her to work it out.
    """
    return any(reaches(rid, envelope) for rid in tier.get("resources") or [])


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
    if not any(reaches(rid, envelope) for rid in resources):
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
        "resources_governed": sum(1 for rid in resources
                                  if reaches(rid, envelope)),
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
