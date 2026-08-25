"""Joint ownership: one resource, several owners, none of them above the rest.

The organization layer answers "some of this is the firm's". This answers a
different question: what if a resource has *two* owners of equal standing and
neither can decide alone. A joint account is the ordinary case; the awkward
ones are worse, because the parties may have interests that genuinely
conflict and there is no party above them to arbitrate.

Three things follow, and they are what this module is:

**A mandate names the electorate.** Who is entitled to be counted, at what
weight, and how many it takes. It is signed by the holders and published
beside the resource, so "who gets a say" is not something any single party
can decide later.

**A verdict is a document, not a return value.** Each owner's authorization
server signs its answer to one negotiation. That is what makes it possible
for something other than an authority to do the counting: whoever tallies
cannot manufacture a yes, because it cannot sign one.

**The counting is not consensus.** Not in the distributed-systems sense, and
the word does real damage here. There is no ordered history to agree on —
verdicts about one negotiation are a set — no long-lived state to protect,
and no requirement that the counting party be trusted. So the machinery is a
fold and a comparison, and the thing that makes it safe is signatures rather
than replication.

Nothing here imports anything that needs installing, so `lib/test_joint.py`
runs it in a bare interpreter. The narrowing algebra is `uma4a_org.clamp`,
reused rather than rewritten: folding two co-owners' terms is the same
operation as an organization applying a ceiling, pointed sideways instead of
down.
"""

import copy

from uma4a_org import claims_match, clamp

RULES = {"all", "any", "threshold"}


class MandateError(ValueError):
    """A co-ownership record that must not become the one in force."""


def validate_mandate(doc: dict, floor: int = 0) -> dict:
    """Reject a mandate, or return it normalised with an explicit threshold.

    `floor` is a minimum number of holders that this mandate may not go
    below — a threshold set by somebody other than the holders. It exists
    because the interesting real-world version of this is not a group
    choosing its own quorum: it is a regulator, or an account agreement,
    fixing one. That also answers the question a self-chosen quorum cannot,
    which is what quorum decides the quorum.
    """
    if not isinstance(doc, dict):
        raise MandateError("a mandate is a JSON object")
    out = copy.deepcopy(doc)

    resource = out.get("resources")
    if isinstance(resource, str):
        resource = [resource]
    if not isinstance(resource, list) or not resource or any(
            not isinstance(r, str) or not r.strip() for r in resource):
        raise MandateError(
            "resources must name at least one id or pattern — a mandate over nothing "
            "governs nothing, and the holders would be agreeing to a document "
            "with no subject")
    out["resources"] = [r.strip() for r in resource]

    holders = out.get("holders")
    if not isinstance(holders, list) or len(holders) < 2:
        raise MandateError(
            "a mandate needs at least two holders — one holder is ownership, "
            "and it already has a mechanism")
    seen = set()
    total = 0
    for h in holders:
        if not isinstance(h, dict):
            raise MandateError("each holder is an object")
        owner = (h.get("owner") or "").strip()
        issuer = (h.get("issuer") or "").strip().rstrip("/")
        if not owner:
            raise MandateError("a holder needs an owner id")
        if owner in seen:
            raise MandateError(
                f"{owner!r} appears twice — a holder counted twice is a holder "
                f"who outvotes the others by being listed again")
        seen.add(owner)
        if not issuer.startswith("https://"):
            raise MandateError(
                f"holder {owner!r} needs an https issuer: her verdicts are "
                f"verified against the keys it publishes, and a plaintext "
                f"origin has nothing to verify against")
        weight = h.get("weight", 1)
        if not isinstance(weight, int) or isinstance(weight, bool) or weight < 1:
            raise MandateError(f"holder {owner!r} needs an integer weight of 1 or more")
        h["owner"], h["issuer"], h["weight"] = owner, issuer, weight
        total += weight
    out["holders"] = holders

    rule = out.setdefault("rule", {"kind": "all"})
    if not isinstance(rule, dict):
        raise MandateError("rule must be an object")
    kind = rule.get("kind") or "all"
    if kind not in RULES:
        raise MandateError(f"rule.kind must be one of {sorted(RULES)}, got {kind!r}")
    rule["kind"] = kind
    # Normalised to a number, because everything downstream compares weights
    # and a rule that stayed a word would be re-interpreted at each place
    # that read it. `any` is the smallest weight rather than 1: with weights
    # in play, "any one holder" has to mean the least of them can act alone,
    # or the word would quietly exclude somebody.
    if kind == "all":
        rule["threshold"] = total
    elif kind == "any":
        rule["threshold"] = min(h["weight"] for h in holders)
    else:
        threshold = rule.get("threshold")
        if not isinstance(threshold, int) or isinstance(threshold, bool) \
                or not 1 <= threshold <= total:
            raise MandateError(
                f"rule.threshold must be between 1 and {total}, the total "
                f"weight of the holders")
    if floor and rule["threshold"] < floor:
        raise MandateError(
            f"this resource requires at least {floor} of the holders' weight "
            f"to release it, and this mandate asks for {rule['threshold']}. "
            f"That floor is not the holders' to lower.")
    out["rule"] = rule
    out["total_weight"] = total
    return out


def governs(mandate: dict, resource_id: str) -> bool:
    return claims_match(resource_id, mandate.get("resources") or [])


def holder(mandate: dict, owner: str) -> dict | None:
    for h in mandate.get("holders") or []:
        if h["owner"] == owner:
            return h
    return None


# --- Folding the holders' terms ---------------------------------------------


def as_ceiling(tier: dict, resources: list[str]) -> dict:
    """One holder's terms, expressed as a ceiling over the joint resource.

    This is the trick that lets the fold reuse the organization's clamp
    instead of being a second implementation of "narrower". An organization's
    envelope and a co-owner's terms are the same kind of object seen from
    different angles: both say the longest this may last, the most it may
    reach, what it must forbid, and when a person has to be asked. Turning
    hers into an envelope and clamping by it gives the intersection, with the
    one-directional guarantee `lib/test_org.py` already proves.
    """
    terms = tier.get("terms") or {}
    return {
        "claims": list(resources),
        "max_expires_in": terms.get("expires_in"),
        "allowed_scopes": terms.get("scope"),
        "require_prohibited": list(terms.get("prohibited") or []),
        "always_ask": list(resources) if tier.get("ask_me") else [],
    }


def fold(quotes: list[tuple[str, dict]], resources: list[str]) -> tuple[dict, dict]:
    """Every holder's terms over this resource, intersected into one document.

    Returns the folded tier and, per holder, what her co-owners' terms did to
    what she would have offered alone.

    One document rather than several is the whole point. The alternative is
    to publish each holder's terms and let the requesting side work out the
    intersection, which fails for the reason it fails one layer up: it hands
    the computation to the party with every incentive to compute it
    generously, and leaves two documents that can disagree with nothing
    saying which wins. Here the agent reads one document, signs it once, and
    each holder's authority independently re-checks that what was signed is
    inside what she published — so the folding party cannot weaken anybody's
    terms, only state them.
    """
    if not quotes:
        raise MandateError("nothing to fold")
    (_, first), *rest = quotes
    folded = copy.deepcopy(first)
    changes: dict[str, list[dict]] = {}
    for owner, tier in rest:
        folded, made = clamp(folded, as_ceiling(tier, resources))
        changes[owner] = made
    # What the first holder's own terms lost to everybody else's. Computed by
    # folding her in last rather than by tracking it above, because she is the
    # one holder the loop never clamps by.
    first_owner = quotes[0][0]
    _, against_first = clamp(folded, as_ceiling(first, resources))
    changes[first_owner] = against_first
    return folded, changes


# --- Counting ----------------------------------------------------------------


def tally(mandate: dict, verdicts: dict) -> dict:
    """Where this negotiation stands: allowed, refused, or still waiting.

    `verdicts` is {owner: "allow" | "refuse"}. Anyone not in it has not
    answered yet.

    The refusal test is the interesting half. It does not wait for everybody:
    a request is refused the moment the weight still outstanding cannot carry
    it over the threshold, which under `all` means the first refusal ends it.
    Waiting for the rest would leave people answering a question that has
    already been settled, and would tell a requesting agent to keep polling
    for an outcome that cannot change.
    """
    holders = mandate.get("holders") or []
    threshold = (mandate.get("rule") or {}).get("threshold") or 0
    weights = {h["owner"]: h["weight"] for h in holders}
    for_ = sum(w for o, w in weights.items() if verdicts.get(o) == "allow")
    against = sum(w for o, w in weights.items() if verdicts.get(o) == "refuse")
    outstanding = sorted(o for o in weights if o not in verdicts)
    possible = for_ + sum(weights[o] for o in outstanding)
    if for_ >= threshold:
        effect = "allow"
    elif possible < threshold:
        effect = "refuse"
    else:
        effect = "pending"
    return {
        "effect": effect,
        "for": for_,
        "against": against,
        "threshold": threshold,
        "total_weight": sum(weights.values()),
        "outstanding": outstanding,
        "rule": (mandate.get("rule") or {}).get("kind"),
    }


def describe(mandate: dict) -> list[str]:
    """The mandate in sentences, for whoever has to agree to it."""
    holders = mandate.get("holders") or []
    rule = mandate.get("rule") or {}
    names = ", ".join(h["owner"] for h in holders)
    weighted = any(h["weight"] != 1 for h in holders)
    lines = [f"Held jointly by {names}, over "
             f"{', '.join(mandate.get('resources') or [])}."]
    if rule.get("kind") == "all":
        lines.append("Every holder has to allow a request before it is granted. "
                     "Any one of you can stop it.")
    elif rule.get("kind") == "any":
        lines.append("Any one holder can release it alone. You are trusting "
                     "each other's judgement, not only your own.")
    else:
        lines.append(f"It takes {rule.get('threshold')} of "
                     f"{mandate.get('total_weight')} to release it"
                     + (", and the holders do not carry equal weight."
                        if weighted else "."))
    lines.append("The terms an agent must accept are every holder's terms at "
                 "once: the shortest expiry any of you set, only the scopes "
                 "all of you offer, and every prohibition any of you wrote.")
    lines.append("No holder can see another's terms over anything else, or "
                 "act for her anywhere but here.")
    return lines
