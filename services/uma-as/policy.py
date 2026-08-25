"""Alice's tier policy — the owner-side configuration uma-as evaluates.

This is deliberately a small, legible document (not a policy language):
each tier names the resources it covers, the terms template the AS dictates
for them, and whether granting requires asking Alice. The portal edits it
through the owner API.

The tiers themselves live in the store, not here — Alice edits them at
runtime, so at more than one replica a module-level dict would let two
authorization servers disagree about her policy. What stays here is the part
that is genuinely policy and not state: the default she starts from, and the
rules for how an owner edit is applied.
"""

import copy
import os

# Default policy — the state Alice's "morning scene" produces. The store seeds
# itself from this once; every later read comes from the store.
DEFAULT_TIERS: dict[str, dict] = {
    "tier1": {
        "name": "Holdings summary",
        "resources": ["alice-vault/get_positions"],
        "ask_me": False,
        # Nobody named behind it, nobody to complain to. She still lets it
        # negotiate — it just does not get to do so quietly.
        "rules": [
            {"when": ["assurance.accountability_below:1"], "then": "ask"},
        ],
        "terms": {
            "template_id": "alice/advisor-tier1/v2",
            "purpose": "Suitability review for advisory onboarding",
            "scope": ["positions:read"],
            "expires_in": 172800,
            "prohibited": [
                "retention-after-review",
                "marketing",
                "model-training",
            ],
        },
    },
    "tier2": {
        "name": "Transaction history and cost basis",
        "resources": ["alice-vault/get_transactions"],
        "ask_me": False,
        # Approving a first contact used to admit an agent to everything below
        # the ask-me line, so an agent she let in to see her holdings could
        # read her transaction history without asking. Being admitted is not
        # the same as being admitted *here*.
        "rules": [
            {"when": ["standing.first_at_tier"], "then": "ask"},
        ],
        "terms": {
            "template_id": "alice/advisor-tier2/v2",
            "purpose": "Portfolio analysis for the current advisory engagement",
            "scope": ["transactions:read"],
            "expires_in": 86400,
            "prohibited": [
                "client-benchmarking",
                "sharing-outside-engagement-team",
                "retention-after-engagement",
            ],
            "constraints": {"accounts": ["brokerage-main"]},
        },
    },
    "tier3": {
        "name": "Trade execution",
        "resources": ["alice-vault/execute_trade"],
        "ask_me": True,
        # Deliberately empty. This is the only tier where a relaxation could
        # do anything — the other two already grant without asking — and
        # "we have known each other a while" is not a reason to stop asking
        # about money. The mechanism exists; her default policy declines to
        # use it. A deployment that disagrees would write:
        #
        #   {"when": ["standing.approved_at_tier", "standing.age_above:90d",
        #             "standing.never_revoked"], "then": "auto"}
        #
        # and should have to write it deliberately.
        #
        # Going the other way is always available and never needs an argument
        # from anyone. An agent whose requests have started to widen, or that
        # she keeps saying no to, can be made to face her every time:
        #
        #   {"when": ["standing.tiers_above:1"], "then": "ask"}
        #   {"when": ["standing.denials_above:2"], "then": "refuse"}
        #
        # Both read the ledger her own decisions wrote, over
        # UMA_AS_TRAJECTORY_WINDOW. Left out of the default because tier 3
        # already asks; they earn their keep on a tier that does not.
        "rules": [],
        "terms": {
            "template_id": "alice/advisor-tier3/v2",
            "purpose": "Execution of one client-approved order",
            "scope": ["trades:execute"],
            "expires_in": 900,
            "prohibited": [
                "orders-beyond-approved-parameters",
                "discretionary-reuse-of-authority",
            ],
            "per_operation": True,
        },
    },
}


# Which prohibitions the enforcement point can actually refuse, and what
# refuses them.
#
# A prohibition is enforceable exactly when the thing it forbids has to cross
# the owner's boundary to happen. "Do not retain this after the review" is a
# promise about the requester's own storage: she hands the bytes over and can
# never see what becomes of them. "Do not place orders beyond the approved
# parameters" is different in kind -- placing one means calling her tool, and
# the enforcement point is holding a grant that names the exact parameters.
#
# Both were already true before this map existed. Two of the three tiers ship
# prohibitions the PEP has always refused (`operation_mismatch`,
# `already_consumed`) without anything saying so, which left her terms reading
# as though every line were equally a matter of trust. Naming the mechanism
# does not add enforcement; it stops understating it.
#
# Keyed on the prohibition string and gated on the tier switch that turns the
# mechanism on, so a tier that forbids reuse without setting `per_operation`
# is honestly reported as undertaken rather than enforced.
ENFORCED_PROHIBITIONS = {
    "orders-beyond-approved-parameters": ("per_operation", "operation-binding"),
    "discretionary-reuse-of-authority": ("per_operation", "single-use"),
}


def enforced_prohibitions(tier: dict) -> dict:
    """Which of this tier's prohibitions are refused at the door, and by what.

    Derived on every read rather than stored: the answer follows from the
    tier's own switches, and a copy would be one owner edit away from lying.
    """
    terms = tier.get("terms") or {}
    out = {}
    for name in terms.get("prohibited") or []:
        gate, mechanism = ENFORCED_PROHIBITIONS.get(name, (None, None))
        if gate and terms.get(gate):
            out[name] = mechanism
    return out


def defaults(owner: str = "alice") -> dict[str, dict]:
    """Starting tiers for an owner.

    The resource ids and the terms template ids are both namespaced by owner.
    That is not cosmetic: a resource server holding a thousand people's
    accounts holds a thousand distinct collections, and a terms document is
    dereferenced by agents holding no token, so its id is the only thing that
    can say whose terms it is.
    """
    tiers = copy.deepcopy(DEFAULT_TIERS)
    if owner == "alice":
        return tiers
    for tier in tiers.values():
        tier["resources"] = [r.replace("alice-vault/", f"{owner}-vault/", 1)
                             for r in tier["resources"]]
        t = tier["terms"]
        t["template_id"] = t["template_id"].replace("alice/", f"{owner}/", 1)
    return tiers


def tier_for_resource(tiers: dict[str, dict],
                      resource_id: str) -> tuple[str, dict] | tuple[None, None]:
    """Which tier governs a resource. Pure: the caller supplies the tiers it
    read, so the lookup can never see a different policy than the one the
    caller is acting on."""
    for tid, t in tiers.items():
        if resource_id in t["resources"]:
            return tid, copy.deepcopy(t)
    return None, None


# --- Rules: policy that faces the agent, without naming one ------------------
#
# A tier says what may be asked of a resource. A rule says what a *request*
# has to look like before that tier's answer applies. Together they let Alice
# write "an agent I cannot check must ask me" — which names no agent, and so
# holds for the ten-thousandth stranger exactly as written.
#
# The shape is one list per tier:
#
#     "rules": [
#         {"when": ["assurance.accountability_below:1"], "then": "ask"},
#         {"when": ["standing.age_above:90d", "standing.never_revoked"],
#          "then": "auto"}
#     ]
#
# Conjunction inside a rule, disjunction across rules, and nothing else. No
# negation, no nesting, no expressions. That is the whole grammar, and keeping
# it that small is the point: `policy.py` is a legible document, not a policy
# language, and the moment it can express anything it needs a debugger.
#
# Two properties do the safety work:
#
#   1. **Restrictions beat relaxations.** Relaxations are applied first and
#      restrictions last, so no combination of matched rules can end up more
#      permissive than the strictest thing that matched.
#   2. **Only an owner decision may relax.** `then: "auto"` is the only
#      requirement that can loosen, and `validate_rules` refuses one whose
#      conditions are not in RELAXING_CONDITIONS. Assurance is evidence the
#      requesting side supplied, so it is out. So is anything recording what
#      this *server* did — relaxing on "we granted here before" would let one
#      automatic grant justify the next. What is left is what Alice herself
#      decided: she admitted this agent, she approved something at this tier,
#      she has never revoked it. See `assurance.py` for the wider line.
#
# The consequence is the thing that makes reading self-asserted metadata safe
# at all: a lie can only cost the liar friction.

AUTO, ASK, REFUSE = "auto", "ask", "refuse"
RANK = {AUTO: 0, ASK: 1, REFUSE: 2}

# --- Her attention is the scarcest resource here -----------------------------
#
# Nothing above stops someone generating ten thousand keys and putting ten
# thousand first-contact requests in front of Alice. Keys are free, so a rate
# limit per key is theatre and one per source address is the wrong layer. The
# property that actually matters is not "how fast" but "how much of her queue
# can strangers occupy at once", so this is a *depth* limit rather than a rate:
# past the cap, a request is refused with a reason instead of queued.
#
# The first version of this had one queue, and it was wrong in the way that
# mattered most. An agent she already knows was never counted — but **an agent
# she does not know yet is exactly what Bob's is on first contact**, so a flood
# of anonymous bots filled the only lane there was and Bob could never become
# one of the agents she knows. It protected continuity and left onboarding
# undefended, which is the half that decides whether any of this is adoptable.
#
# So the queue is split, and the split is the same asymmetry as everywhere
# else: better evidence buys *less friction*, never more access. A lane is not
# permission — every request in it still faces her policy unchanged.
#
#   unattributable   nobody checkable stands behind it. Cheap to mint by the
#                    thousand, so it gets a deliberately small lane.
#   attributable     a named operator published *this agent's key* in its own
#                    directory (accountability 2). Faking that means standing
#                    up a domain, serving a metadata document that claims its
#                    own URL, and publishing a key per agent.
#
# The point is not that the second is expensive. It is that it is
# **attributable**: every agent minted that way is tied to one operator, so a
# flood in that lane has a name on it and can be shut out in one action, while
# a flood in the first lane cannot reach the second at all.
#
# What this does not claim: if she accepts anonymous strangers at all, they can
# fill the anonymous lane. Nothing here prevents that, and no scheme does
# without charging the requester something. What it guarantees is that the
# damage stays in that lane.
#
# Three properties, all of which survive the split:
#
#   * It is self-healing. Every request she answers frees a slot, so the cap is
#     on the backlog and not on the relationship.
#   * **A flood cannot crowd out an agent she knows, nor one that can be
#     named.** The failure mode of an attack is that anonymous strangers are
#     turned away.
#   * It needs no new state. The counts are a read of the pending queue her
#     portal already lists.
#
# The refusal is honest rather than silent: the agent is told the owner is not
# accepting new requests right now, which is true, and can come back. Silence
# would be indistinguishable from a broken server, and would push a legitimate
# agent into retrying — which is the behaviour the cap exists to prevent.
#
# Setting the unattributable lane to 0 turns her authority into
# introduce-yourself-first: an agent with nobody behind it cannot reach her at
# all. That is a legitimate posture and it is one environment variable. It is
# not the default, because the whole argument of this profile is that a
# stranger can negotiate.
PEND_BUDGET = int(os.environ.get("UMA_AS_PEND_BUDGET", "5"))
PEND_BUDGET_ATTRIBUTED = int(
    os.environ.get("UMA_AS_PEND_BUDGET_ATTRIBUTED", "40"))

# The line between the lanes. Accountability 2 is the only level an agent
# cannot reach on its own say-so: it requires the operator it names to have
# published this agent's key, in a directory this authority fetched itself.
ATTRIBUTABLE_AT = 2


def pend_lane(axes: dict) -> str:
    return ("attributable" if axes.get("accountability", 0) >= ATTRIBUTABLE_AT
            else "unattributable")


def pend_budget(lane: str) -> int:
    return PEND_BUDGET_ATTRIBUTED if lane == "attributable" else PEND_BUDGET

# Facts her own authority produced, rather than the requesting side.
#
# Split again, and the second line is the sharper one. Relaxing on "we have
# granted here before" is circular: that grant may itself have been automatic,
# so a relaxation would be resting on evidence a relaxation produced. Only
# facts traceable to a decision **Alice personally made** may lower a
# requirement — she approved this connection, she approved something at this
# tier, she has never revoked it. Everything else about her own records may
# still raise one.
RELAXING_CONDITIONS = {
    "standing.approved_at_tier",  # she personally approved something here
    "standing.never_revoked",
    "standing.age_above",         # :<duration>, since she admitted it
    # An agent she activated herself. Admissible here, and it is worth being
    # explicit about why, because it is the only relaxing condition that is
    # not a fact about *this agent's* history with her.
    #
    # It holds when the operator the agent names is an origin she claimed AND
    # her authority checked that operator's own key directory and found this
    # agent's signing key in it. The first half is her decision. The second is
    # a check she ran. Neither is anything the requesting side can assert, and
    # dropping the second would be fatal: any agent can point at a metadata
    # document she publishes, but only she can put a key in her directory.
    "standing.first_party",
}

OBSERVED_CONDITIONS = {
    "standing.none",            # she has no active connection with this agent
    "standing.first_at_tier",   # never *granted* at this tier before
    "standing.revoked_before",
    "standing.age_below",       # :<duration>
    # What the agent has been doing lately, read from her own ledger over
    # UMA_AS_TRAJECTORY_WINDOW. Her decisions, so they belong on this side of
    # the line — but observed rather than relaxing, because "she has denied you
    # repeatedly, so grant automatically" is not a sentence anyone should be
    # able to save.
    "standing.denials_above",   # :<n>, denials in the window
    "standing.tiers_above",     # :<n>, distinct tiers reached in the window
    "standing.calls_above",     # :<n>, calls actually made in the window
}

STANDING_CONDITIONS = RELAXING_CONDITIONS | OBSERVED_CONDITIONS

# Evidence the requesting side supplied, or facts about what it asked for.
# These may only tighten.
ASSURANCE_CONDITIONS = {
    "assurance.binding_below",         # :<level>
    "assurance.provenance_below",      # :<level>
    "assurance.accountability_below",  # :<level>
    "request.max_expiry",              # it asked for the tier's ceiling
    "request.reason_absent",           # it did not say what it wanted this for
    "request.mission_absent",          # it cited no mandate for the errand
}

CONDITIONS = STANDING_CONDITIONS | ASSURANCE_CONDITIONS

# Conditions that take an argument, and what kind. Validation checks these,
# because the alternative is a rule that saves cleanly and then raises inside
# the grant loop — a 500 on the token endpoint, from a policy edit that looked
# accepted. Worse, a bad argument on a *relaxing* rule stays latent until the
# first ask-me tier evaluates it, so the failure surfaces on trades and
# nowhere else.
DURATION_ARGS = {"standing.age_above", "standing.age_below"}
LEVEL_ARGS = {"assurance.binding_below", "assurance.provenance_below",
              "assurance.accountability_below"}
COUNT_ARGS = {"standing.denials_above", "standing.tiers_above",
              "standing.calls_above"}
TAKES_ARG = DURATION_ARGS | LEVEL_ARGS | COUNT_ARGS

_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


# What a policy editor needs in order to offer these as choices rather than
# make the owner remember them. Published rather than duplicated in the portal,
# so the surface she edits through cannot drift from what this will accept —
# including *which* conditions may relax, which is the rule she should be shown
# rather than discover by having a save rejected.
#
# Each entry is a **complete condition**, not a name plus a box to type into.
# The level-taking ones are enumerated per level because each level is a
# different sentence: `accountability_below:1` is "nobody is named", and
# `accountability_below:2` is "the named operator has not vouched for this
# key". Only durations are genuinely open-ended, and only those ask for a
# value.
VOCABULARY = [
    {"condition": "assurance.binding_below:1", "takes": None,
     "label": "the request is not bound to a key this authority verified"},
    {"condition": "assurance.provenance_below:1", "takes": None,
     "label": "the agent's credential cannot be traced to an issuer"},
    {"condition": "assurance.accountability_below:1", "takes": None,
     "label": "nobody named and reachable is standing behind the agent"},
    {"condition": "assurance.accountability_below:2", "takes": None,
     "label": "the named operator has not published this agent's key"},
    {"condition": "request.max_expiry", "takes": None,
     "label": "it asked for the longest access this tier allows"},
    {"condition": "request.reason_absent", "takes": None,
     "label": "it did not say what it wants the access for"},
    {"condition": "request.mission_absent", "takes": None,
     "label": "it cited no mandate for what it is doing"},
    {"condition": "standing.none", "takes": None,
     "label": "I have no standing connection with this agent"},
    {"condition": "standing.first_at_tier", "takes": None,
     "label": "it has never been granted at this tier before"},
    {"condition": "standing.revoked_before", "takes": None,
     "label": "I have revoked this agent before"},
    {"condition": "standing.age_below", "takes": "duration",
     "label": "I have known this agent for less than"},
    {"condition": "standing.first_party", "takes": None,
     "label": "it is an agent I activated myself"},
    {"condition": "standing.never_revoked", "takes": None,
     "label": "I have never revoked this agent"},
    {"condition": "standing.approved_at_tier", "takes": None,
     "label": "I have personally approved something at this tier"},
    {"condition": "standing.age_above", "takes": "duration",
     "label": "I have known this agent for more than"},
    {"condition": "standing.denials_above", "takes": "count",
     "label": "I have recently denied this agent more times than"},
    {"condition": "standing.tiers_above", "takes": "count",
     "label": "it has recently asked at more tiers than"},
    {"condition": "standing.calls_above", "takes": "count",
     "label": "it has recently made more calls than"},
]


def vocabulary() -> list[dict]:
    """The conditions an owner may write, and what each may do.

    `may_relax` is the interesting field: a surface that shows which options
    cannot lower a requirement teaches the rule at the moment it matters,
    instead of letting her compose something and then refusing to save it.
    """
    out = []
    for entry in VOCABULARY:
        name = entry["condition"].split(":", 1)[0]
        out.append({**entry, "may_relax": name in RELAXING_CONDITIONS})
    return out


def parse_duration(text: str) -> int:
    """`90d`, `12h`, `45m`, or plain seconds."""
    text = str(text).strip()
    if text and text[-1] in _UNITS:
        return int(float(text[:-1]) * _UNITS[text[-1]])
    return int(text)


def _split(condition: str) -> tuple[str, str | None]:
    name, _, value = condition.partition(":")
    return name, (value or None)


def validate_rules(rules) -> None:
    """Reject a rule set before it is ever stored.

    This runs on the owner API's edit path rather than at evaluation time, so
    a policy that could widen access on evidence the agent controls cannot be
    saved at all — as opposed to being saved and quietly ignored, which is how
    a deployment ends up believing it has a control it does not have.
    """
    if not isinstance(rules, list):
        raise ValueError("rules must be a list")
    for rule in rules:
        then = rule.get("then")
        if then not in RANK:
            raise ValueError(f"rule `then` must be one of {sorted(RANK)}, got {then!r}")
        when = rule.get("when")
        if isinstance(when, str):
            when = [when]
        if not when or not isinstance(when, list):
            raise ValueError("rule `when` must be a non-empty condition or list")
        for condition in when:
            name, value = _split(condition)
            if name not in CONDITIONS:
                raise ValueError(f"unknown condition {name!r}")
            if name in TAKES_ARG:
                if value is None:
                    raise ValueError(
                        f"{name!r} needs an argument, as {name}:<value>")
                try:
                    if name in DURATION_ARGS:
                        parse_duration(value)
                    elif int(value) < 0:
                        # A negative count would make the condition always true
                        # and the rule always fire, which reads as a working
                        # restriction and is really a stuck one.
                        raise ValueError("negative")
                except (TypeError, ValueError):
                    kind = ("duration" if name in DURATION_ARGS
                            else "count" if name in COUNT_ARGS else "level")
                    raise ValueError(
                        f"{name!r} takes a {kind}, got {value!r}") from None
            elif value is not None:
                raise ValueError(f"{name!r} takes no argument, got {value!r}")
            if then == AUTO and name not in RELAXING_CONDITIONS:
                why = ("assurance is supplied by the requesting side, and a "
                       "signal the counterparty influences must never widen "
                       "access") if name not in STANDING_CONDITIONS else (
                    "it records what this server did, not what Alice decided; "
                    "relaxing on it would let one automatic grant justify the "
                    "next")
                raise ValueError(
                    f"{name!r} cannot relax a requirement — {why}. Only "
                    f"{sorted(RELAXING_CONDITIONS)} may lower one.")


def _matches(condition: str, facts: dict) -> bool:
    name, value = _split(condition)
    standing, assurance = facts["standing"], facts["assurance"]
    tier_id = facts.get("tier")

    if name == "standing.none":
        return not standing["active"]
    if name == "standing.first_party":
        return bool(standing.get("first_party"))
    if name == "standing.first_at_tier":
        return standing["first_at_tier"]
    if name == "standing.approved_at_tier":
        return tier_id in (standing.get("approved_tiers") or [])
    if name == "standing.never_revoked":
        return standing["revocations"] == 0
    if name == "standing.revoked_before":
        return standing["revocations"] > 0
    if name in ("standing.age_above", "standing.age_below"):
        age = standing["age_seconds"]
        if age is None:          # never met: it is not older than anything,
            return name == "standing.age_below"   # and it is younger than all
        return (age > parse_duration(value) if name == "standing.age_above"
                else age < parse_duration(value))

    # Read from her own ledger before evaluation and handed in with the rest of
    # her standing facts, so nothing here needs a store and this stays a pure
    # function of the dict. `trajectory` is absent when she has never met this
    # agent, and both conditions read that as nothing having happened.
    if name == "standing.denials_above":
        return standing.get("trajectory", {}).get("denials", 0) > int(value)
    if name == "standing.tiers_above":
        return len(standing.get("trajectory", {}).get("tiers", [])) > int(value)
    if name == "standing.calls_above":
        return standing.get("trajectory", {}).get("calls", 0) > int(value)

    if name.startswith("assurance."):
        axis = name[len("assurance."):-len("_below")]
        return assurance.get(axis, 0) < int(value)
    if name == "request.max_expiry":
        return facts["request"]["expires_in"] >= facts["request"]["max_expires_in"]
    if name == "request.reason_absent":
        return not (facts["request"].get("reason") or "").strip()
    if name == "request.mission_absent":
        return not facts["request"].get("mission")
    return False


def _rule_matches(rule: dict, when: list, facts: dict) -> bool:
    """Whether every condition in a rule holds.

    `validate_rules` makes a malformed rule unstorable, so this should never
    see one. It can still happen — a policy stored before validation existed, a
    store edited directly — and the answer must not be a 500 inside the grant
    loop. So a rule that cannot be evaluated **fails towards the owner**: an
    unusable restriction is treated as matching, an unusable relaxation as not
    matching. Both directions land on more friction rather than less.
    """
    try:
        return all(_matches(c, facts) for c in when)
    except (TypeError, ValueError, KeyError):
        return rule["then"] != AUTO


def evaluate(tier: dict, facts: dict) -> tuple[str, list[str]]:
    """What this request needs before it may be granted, and why.

    Returns one of ``auto`` / ``ask`` / ``refuse``, plus the conditions that
    decided it — which the pending dialog shows Alice and the ledger keeps, so
    a decision is explicable after the fact rather than only reproducible.
    """
    baseline = ASK if tier.get("ask_me") else AUTO
    rules = tier.get("rules") or []

    relaxed, reasons = baseline, []
    for rule in rules:                       # relaxations first
        when = rule["when"] if isinstance(rule["when"], list) else [rule["when"]]
        if rule["then"] != AUTO or RANK[AUTO] >= RANK[relaxed]:
            continue
        if _rule_matches(rule, when, facts):
            relaxed, reasons = AUTO, list(when)

    result = relaxed
    for rule in rules:                       # restrictions last, and they win
        when = rule["when"] if isinstance(rule["when"], list) else [rule["when"]]
        if RANK[rule["then"]] <= RANK[result]:
            continue
        if _rule_matches(rule, when, facts):
            result, reasons = rule["then"], list(when)
    return result, reasons


def new_tier(tier_id: str, spec: dict, existing: dict[str, dict],
             registered: set[str]) -> dict:
    """Build a tier Alice is adding, or raise ValueError saying why not.

    Three checks, and the middle one is the one with teeth:

    * the id is hers to choose but has to be new, and has to be a plain slug —
      it ends up in a terms `template_id` that agents will cite for years;
    * every resource must be **registered and ungoverned**. Registered because
      a tier over something her authority does not protect is a rule that can
      never fire; ungoverned because `tier_for_resource` returns the first
      match, so two tiers over one resource would make her policy depend on
      dict ordering — which is not a policy;
    * the rules follow the same asymmetry as everywhere else.

    A tier with no resources is allowed. She may well write the terms first
    and attach them when the resource shows up.
    """
    if not tier_id or not all(c.isalnum() or c in "-_" for c in tier_id):
        raise ValueError("a tier id may contain letters, digits, - and _ only")
    if tier_id in existing:
        raise ValueError(f"there is already a tier called {tier_id!r}")

    resources = list(spec.get("resources") or [])
    governed = {r: tid for tid, t in existing.items() for r in t["resources"]}
    for rid in resources:
        if rid not in registered:
            raise ValueError(f"{rid!r} is not a resource this authority protects")
        if rid in governed:
            raise ValueError(
                f"{rid!r} is already governed by {governed[rid]!r} — a resource "
                "belongs to one tier, or which terms apply would depend on the "
                "order they happen to be stored in")

    terms = dict(spec.get("terms") or {})
    for field in ("purpose", "expires_in"):
        if not terms.get(field):
            raise ValueError(f"terms need a {field}")
    rules = spec.get("rules") or []
    validate_rules(rules)

    return {
        "name": spec.get("name") or tier_id,
        "resources": resources,
        "ask_me": bool(spec.get("ask_me")),
        "rules": copy.deepcopy(rules),
        "terms": {
            # v1 because this document has never been served before. Every
            # later edit bumps it, and every version stays dereferenceable.
            "template_id": f"alice/{tier_id}/v1",
            "purpose": terms["purpose"],
            "scope": list(terms.get("scope") or []),
            "expires_in": int(terms["expires_in"]),
            "prohibited": list(terms.get("prohibited") or []),
            **({"per_operation": True} if terms.get("per_operation") else {}),
        },
    }


def apply_patch(tier: dict, patch: dict) -> dict:
    """Owner edits: terms fields, the ask_me switch, and her agent rules.
    Resources are fixed by registration, not editable here.

    Pure — it returns the edited tier rather than mutating shared state, so
    the store can apply it inside whatever transaction keeps the version bump
    atomic.
    """
    tier = copy.deepcopy(tier)
    if "ask_me" in patch:
        tier["ask_me"] = bool(patch["ask_me"])
    if "rules" in patch:
        validate_rules(patch["rules"])       # raises rather than storing
        tier["rules"] = copy.deepcopy(patch["rules"])
    terms_patch = patch.get("terms", {})
    # `scope` is in this list and is not something her portal offers her: the
    # scopes a tier covers follow from the resources it governs, so editing
    # them by hand would only ever produce terms that describe access the
    # resource cannot give. It is patchable because the layer above her can
    # narrow it — an organization whose charter does not allow a scope makes
    # her terms stop offering it, and the terms document has to say so.
    for field in ("purpose", "expires_in", "prohibited", "scope"):
        if field in terms_patch:
            tier["terms"][field] = terms_patch[field]
    # Any owner edit produces a new template version so contracts are
    # verifiably tied to the terms in force when they were signed.
    base = tier["terms"]["template_id"].rsplit("/v", 1)[0]
    version = int(tier["terms"]["template_id"].rsplit("/v", 1)[1]) + 1
    tier["terms"]["template_id"] = f"{base}/v{version}"
    return tier
