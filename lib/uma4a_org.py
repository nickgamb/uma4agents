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
"""

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
