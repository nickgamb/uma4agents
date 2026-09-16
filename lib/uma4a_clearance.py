"""Clearance: an authorization that is nobody's to grant here.

Her terms decide whether an agent may touch her things. They cannot decide
whether the act is *permitted at all* — whether the party behind it holds the
licence, sits in a jurisdiction where the act is lawful, is old enough. Those
are facts about the world, established by somebody else, and an authorization
server that let a requesting party assert them would be inventing a compliance
check rather than performing one.

This is the mechanism for requiring them, and the whole of its design is one
sentence the lab already discovered on a different problem:

    **A claim works when the requesting party is the only one who holds the
    fact, and fails when the fact may be adverse to it.**

That is why joint verdicts travel authority-to-authority rather than as claims
(FINDINGS rec 26), and a licence is the same shape: the party whose licence it
is has every reason to say it is current, and is the last party who should be
asked. So a clearance never rides on the agent. The organization that employs
the member attests to it, her authorization server fetches that attestation
over its own membership credential, and verifies it against the keys the
organization publishes — the same path an organization notice already takes.

What is checked, in order:

  * the media type, so a token minted for some other purpose cannot be spent
    as a clearance;
  * the signature, against the issuer's published keys;
  * the issuer, the subject and the audience, so an attestation about one
    member, meant for one authority, cannot be replayed about another or at
    another;
  * freshness, because a licence is exactly the kind of fact that lapses.

A requirement is a mapping of claim name to the values that satisfy it:

    {"jurisdiction": ["US-NY", "US-NJ"], "licence_active": [True]}

Two requirements combine by **intersection**, never union, so a layer above
can narrow what satisfies a claim and can never widen it. An empty list of
acceptable values is a requirement nothing satisfies, which is a legitimate
and very loud thing for an organization to write.
"""

from __future__ import annotations

TYP = "u4a-clearance+jwt"

# The attestation carries the facts under one claim rather than at the top
# level, so a clearance can never collide with a registered JWT claim or be
# confused for one.
CLAIM = "clearance"


class ClearanceError(Exception):
    """The attestation is not one this authority may act on."""


def validate_requirement(requirement, *, label: str = "clearance") -> dict:
    """A requirement, normalised, or ValueError saying what is wrong with it.

    Runs on every write — an owner's tier edit and a charter publication — for
    the same reason `validate_rules` does: a requirement that will not
    evaluate should fail in front of whoever wrote it, not inside a grant an
    hour later, where it would refuse every request and look like an outage.
    """
    if requirement is None:
        return {}
    if not isinstance(requirement, dict):
        raise ValueError(f"{label} must be an object of claim -> accepted values")
    out: dict[str, list] = {}
    for claim, accepted in requirement.items():
        if not isinstance(claim, str) or not claim.strip():
            raise ValueError(f"{label} has a claim name that is not a name")
        if not isinstance(accepted, list):
            raise ValueError(
                f"{label}.{claim} must be a list of acceptable values — one "
                f"value on its own is a list of one, and writing it bare is "
                f"how a requirement ends up matching a string character by "
                f"character")
        for value in accepted:
            if not isinstance(value, (str, bool, int, float)):
                raise ValueError(
                    f"{label}.{claim} may only accept strings, numbers or "
                    f"booleans — an attestation is a set of simple facts")
        out[claim.strip()] = list(accepted)
    return out


def tighten(base, addition) -> dict:
    """Two requirements as one, narrowed.

    A claim either party requires is required. A claim both require is
    satisfied only by values both accept, which is the intersection — so the
    layer above can say "and only in New York" and can never say "anywhere
    after all".
    """
    base = dict(base or {})
    out = {k: list(v) for k, v in base.items()}
    for claim, accepted in (addition or {}).items():
        if claim not in out:
            out[claim] = list(accepted)
            continue
        keep = [v for v in out[claim] if v in accepted]
        out[claim] = keep
    return out


def unmet(requirement, facts) -> list[str]:
    """Why this clearance does not satisfy this requirement, in her words.

    Returns an empty list when it does. The reasons are shown to the owner and
    written to her ledger, so they name the claim and what was wanted without
    quoting more of the attestation than the refusal needs.
    """
    facts = facts if isinstance(facts, dict) else {}
    reasons: list[str] = []
    for claim, accepted in (requirement or {}).items():
        if claim not in facts:
            reasons.append(f"the clearance says nothing about {claim}")
            continue
        if not accepted:
            reasons.append(
                f"no value of {claim} is accepted here, so nothing satisfies it")
            continue
        if facts[claim] not in accepted:
            reasons.append(
                f"{claim} is {facts[claim]!r}, and this requires "
                f"{' or '.join(repr(a) for a in accepted)}")
    return reasons


def verify(token: str, *, keys, issuer: str, audience: str, subject: str,
           now: float, leeway: int = 60) -> dict:
    """The facts in a clearance attestation, or ClearanceError saying why not.

    `keys` is the issuer's published JWKS, resolved by the caller — this
    module does no network of its own, so it stays testable and so the caller
    keeps one cache of what each peer signs with.
    """
    import json

    import jwt
    from jwt.algorithms import OKPAlgorithm

    try:
        head = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as exc:
        raise ClearanceError(f"that is not an attestation: {exc}") from exc
    # A membership token and a clearance are signed by the same key for
    # different purposes. Without this, either could be spent as the other.
    if head.get("typ") != TYP:
        raise ClearanceError(
            f"expected a clearance (typ {TYP}), got typ {head.get('typ')!r}")

    claims = None
    signature_error = None
    for jwk_dict in keys:
        if (kid := head.get("kid")) and jwk_dict.get("kid") != kid:
            continue
        try:
            claims = jwt.decode(
                token, OKPAlgorithm.from_jwk(json.dumps(jwk_dict)),
                algorithms=["EdDSA"], issuer=issuer,
                options={"verify_aud": False, "require": ["exp", "iat", "jti"]},
                leeway=leeway)
            break
        except jwt.InvalidTokenError as exc:
            signature_error = exc
            continue
    if claims is None:
        raise ClearanceError(
            f"the clearance does not verify against {issuer}"
            + (f": {signature_error}" if signature_error else ""))

    if claims.get("sub") != subject:
        raise ClearanceError(
            f"the clearance is about {claims.get('sub')!r}, and this "
            f"negotiation is about {subject!r}")
    aud = claims.get("aud")
    audiences = [aud] if isinstance(aud, str) else list(aud or [])
    if audience not in audiences:
        raise ClearanceError(
            f"the clearance is audienced at {audiences or ['nothing']} rather "
            f"than at {audience!r} — an attestation is issued to one authority")
    facts = claims.get(CLAIM)
    if not isinstance(facts, dict):
        raise ClearanceError("the clearance carries no facts")
    return facts
