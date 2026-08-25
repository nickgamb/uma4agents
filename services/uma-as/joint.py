"""Resources this owner holds jointly with somebody else, from her side.

The organization layer above her is asymmetric on purpose: a firm sets a
ceiling and she decides underneath it. This is the other arrangement — a
resource with two or more owners of equal standing, where none of them can
decide alone and none of them is above the rest.

Three things are different because of that, and they are what this module
exists for.

**She agrees to a mandate before her authority will answer anybody about it.**
The tally is a party she has never met, asking her authorization server to
adjudicate. It gets an answer only for a resource she joined, from the tally
named in the mandate she saw. Everything else is a stranger asking about a
stranger's account.

**Her terms are quoted, not surrendered.** What leaves here is her tier over
the jointly held resource: the longest she would allow, the scopes she
offers, what she forbids, whether she wants asking. That is the same document
she publishes to agents, and it goes no further than the co-owners she shares
this one resource with. Nothing about her other resources is quotable at all.

**She re-checks what was folded.** The party that intersects everybody's
terms is not trusted to have done it faithfully — see `verdict_problems`. If
the folded document an agent signed offers more than her own terms do, her
authority refuses, whatever the fold said. That is what lets the folding be
done by something that holds no policy.
"""

import os

from uma4a_joint import claims_match

TALLY_TTL_S = float(os.environ.get("UMA_AS_JOINT_TTL_S", "30"))
CA_BUNDLE = os.environ.get("UMA4A_CA_BUNDLE")


def quote_of(tier: dict, resources: list) -> dict:
    """Her terms over the joint resource, in the shape the fold consumes.

    A tier and nothing else. Her tier id, her rule set, the connections she
    has and every other tier she has written stay here — the co-owners of one
    account are entitled to know what she offers over *that account*, because
    an agent has to be told one set of terms and hers are half of it. They are
    entitled to nothing else, and this is where that line is drawn.
    """
    terms = tier.get("terms") or {}
    return {
        "name": tier.get("name"),
        "resources": list(resources),
        "ask_me": bool(tier.get("ask_me")),
        "terms": {
            "expires_in": terms.get("expires_in"),
            "scope": list(terms.get("scope") or []),
            "prohibited": list(terms.get("prohibited") or []),
        },
    }


def verdict_problems(contract: dict, tier: dict, resource_id: str) -> list[str]:
    """Whether the document the agent signed is inside *her* terms.

    The load-bearing check in the whole arrangement, and the reason the
    folding party can be untrusted. An agent negotiating over a jointly held
    resource signs one folded document, addressed to whoever folded it. If
    that party quietly lengthened an expiry, added a scope or dropped a
    prohibition, the fold would look fine to the agent and to everyone
    reading it — and it dies here, because each co-owner's authority compares
    it against what she herself published and refuses on any difference in
    the direction of more.

    Differences in the direction of *less* are expected and fine: the fold is
    the intersection, so it is normally shorter and narrower than any one
    holder's terms. Only widening is a problem.
    """
    problems: list[str] = []
    terms = tier.get("terms") or {}
    if not claims_match(resource_id, tier.get("resources") or []):
        return [f"her terms do not cover {resource_id}"]

    ceiling = terms.get("expires_in")
    if ceiling is not None and contract.get("expires_in", 0) > ceiling:
        problems.append(
            f"the agreed access lasts {contract.get('expires_in')}s, longer "
            f"than the {ceiling}s this holder's own terms allow")

    offered = terms.get("scope")
    if offered is not None:
        extra = [s for s in contract.get("scope") or [] if s not in offered]
        if extra:
            problems.append(
                f"the agreed terms carry {', '.join(extra)}, which this "
                f"holder does not offer over this resource")

    required = set(terms.get("prohibited") or [])
    missing = sorted(required - set(contract.get("prohibited") or []))
    if missing:
        problems.append(
            f"the agreed terms drop {', '.join(missing)}, which this holder "
            f"forbids over this resource")
    return problems


def record_of(account: str, tally: str, mandate: dict) -> dict:
    """What her authority stores about one mandate.

    The mandate itself is kept rather than a pointer to it. A tally that
    could change the electorate under her — add a holder, lower a threshold —
    without her authority noticing would make agreeing to one meaningless,
    so the copy she agreed to is what her side answers against, and a
    mandate that has moved is something she is asked about again.
    """
    return {"account": account, "tally": tally.rstrip("/"), "mandate": mandate}


def moved(record: dict, fresh: dict) -> list[str]:
    """What changed in a mandate since she agreed to it, in her words."""
    was, now = record.get("mandate") or {}, fresh or {}
    out = []
    old_holders = {h["owner"] for h in was.get("holders") or []}
    new_holders = {h["owner"] for h in now.get("holders") or []}
    if added := sorted(new_holders - old_holders):
        out.append(f"{', '.join(added)} would join the holders of this account")
    if gone := sorted(old_holders - new_holders):
        out.append(f"{', '.join(gone)} would no longer be a holder")
    old_rule = (was.get("rule") or {}).get("threshold")
    new_rule = (now.get("rule") or {}).get("threshold")
    if old_rule != new_rule:
        out.append(f"it would take {new_rule} of the holders' weight to "
                   f"release this rather than {old_rule}")
    if sorted(was.get("resources") or []) != sorted(now.get("resources") or []):
        out.append("the resources it covers would change")
    return out
