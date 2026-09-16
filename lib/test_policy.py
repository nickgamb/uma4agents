"""Alice's agent rules: what may tighten, what may relax, and what wins.

Run it with no dependencies:

    python3 lib/test_policy.py

The suite is mostly about one property, because one property is what makes
reading self-asserted evidence safe at all:

    **nothing the requesting side controls can widen access.**

Everything else here — the lattice, the ordering, the budget arithmetic — is
in service of that. The refusals matter more than the allows: a rule engine
that only proves its permits would pass with the restrictions deleted.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "uma-as"))

import assurance  # noqa: E402
import policy  # noqa: E402

PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"{'ok  ' if ok else 'FAIL'} {name}{'  — ' + detail if detail and not ok else ''}")


def facts(*, binding=1, provenance=0, accountability=0,
          active=False, age=None, first_at_tier=True, approved_tiers=(),
          revocations=0, denials=0, tiers_seen=(), expires_in=0,
          max_expires_in=3600, reason=None, mission=None,
          introduced=False, lineage_new_at_tier=True,
          consequence=None, tier_id="tier1") -> dict:
    return {
        "assurance": {"binding": binding, "provenance": provenance,
                      "accountability": accountability},
        "standing": {"active": active, "age_seconds": age,
                     "first_at_tier": first_at_tier,
                     "approved_tiers": list(approved_tiers),
                     "revocations": revocations,
                     "introduced": introduced,
                     "lineage_new_at_tier": lineage_new_at_tier,
                     # Read from her ledger by the caller and handed in, which
                     # is what keeps `evaluate` testable with no store at all.
                     "trajectory": {"denials": denials,
                                    "tiers": list(tiers_seen)}},
        "request": {"expires_in": expires_in, "max_expires_in": max_expires_in,
                    "reason": reason, "mission": mission,
                    # The resource server's statement about its own operation,
                    # read from her registry by the caller. None is what an
                    # undeclared operation looks like here, and it is a case
                    # the rules below are mostly about.
                    "consequence": consequence},
        "tier": tier_id,
    }


def refused(rules) -> bool:
    """Whether `validate_rules` declines to store this. The guarantee lives at
    save time, so this is the assertion that matters for anything that must
    never be writable."""
    try:
        policy.validate_rules(rules)
        return False
    except ValueError:
        return True


def tier(ask_me=False, rules=None) -> dict:
    return {"ask_me": ask_me, "rules": rules or [],
            "terms": {"expires_in": 3600}}


# --- the lattice --------------------------------------------------------------

check("a tier with no rules keeps its own answer",
      policy.evaluate(tier(), facts())[0] == policy.AUTO)
check("an ask-me tier with no rules still asks",
      policy.evaluate(tier(ask_me=True), facts())[0] == policy.ASK)

t = tier(rules=[{"when": ["assurance.accountability_below:1"], "then": "ask"}])
check("an unaccountable agent is asked about",
      policy.evaluate(t, facts(accountability=0))[0] == policy.ASK)
check("a named operator passes the same rule",
      policy.evaluate(t, facts(accountability=1))[0] == policy.AUTO)

t = tier(rules=[{"when": ["standing.first_at_tier"], "then": "ask"}])
check("the first request at a tier asks, even with a standing connection",
      policy.evaluate(t, facts(active=True, first_at_tier=True))[0] == policy.ASK)
check("the second request at that tier does not",
      policy.evaluate(t, facts(active=True, first_at_tier=False))[0] == policy.AUTO)

# --- conjunction and disjunction, and nothing else ----------------------------

t = tier(ask_me=True, rules=[
    {"when": ["standing.age_above:90d", "standing.never_revoked"], "then": "auto"}])
check("a relaxation needs every condition in its rule",
      policy.evaluate(t, facts(active=True, age=91 * 86400, revocations=1))[0]
      == policy.ASK)
check("and applies when they all hold",
      policy.evaluate(t, facts(active=True, age=91 * 86400))[0] == policy.AUTO)
check("an agent she has never met is younger than any window",
      policy.evaluate(t, facts(active=False, age=None))[0] == policy.ASK)

t = tier(ask_me=True, rules=[
    {"when": ["standing.approved_at_tier"], "then": "auto"}])
check("a tier she personally approved at may relax",
      policy.evaluate(t, facts(active=True, approved_tiers=["tier1"]))[0]
      == policy.AUTO)
check("and a different tier she approved at does not",
      policy.evaluate(t, facts(active=True, approved_tiers=["tier2"]))[0]
      == policy.ASK)

t = tier(rules=[{"when": ["assurance.provenance_below:1"], "then": "ask"},
                {"when": ["request.max_expiry"], "then": "ask"}])
check("separate rules are alternatives",
      policy.evaluate(t, facts(provenance=1, expires_in=3600))[0] == policy.ASK)

# --- the property this exists for ---------------------------------------------

t = tier(ask_me=True, rules=[
    {"when": ["standing.age_above:1d", "standing.never_revoked"], "then": "auto"},
    {"when": ["assurance.provenance_below:1"], "then": "ask"}])
check("a restriction beats a relaxation that also matched",
      policy.evaluate(t, facts(active=True, age=99 * 86400, provenance=0))[0]
      == policy.ASK)

t = tier(rules=[{"when": ["assurance.accountability_below:1"], "then": "ask"},
                {"when": ["assurance.provenance_below:1"], "then": "refuse"}])
check("the strictest match wins, whatever order the rules are in",
      policy.evaluate(t, facts())[0] == policy.REFUSE)

for condition in ("assurance.accountability_below:1", "assurance.provenance_below:1",
                  "request.max_expiry",
                  # her own records, but a record of what this *server* did.
                  # Relaxing on it lets one automatic grant justify the next.
                  "standing.first_at_tier", "standing.none",
                  # Which agents join a lineage is the operator's choice, so
                  # neither of these may ever widen access — they exist to
                  # narrow an ask she already has, or to add one.
                  "standing.introduced", "standing.lineage_new_at_tier",
                  "standing.revoked_before", "standing.age_below:30d"):
    try:
        policy.validate_rules([{"when": [condition], "then": "auto"}])
        ok = False
    except ValueError:
        ok = True
    check(f"{condition} cannot be used to relax", ok)

try:
    policy.validate_rules([
        {"when": ["standing.age_above:90d", "assurance.provenance_below:1"],
         "then": "auto"}])
    ok = False
except ValueError:
    ok = True
check("nor smuggled in beside a standing condition", ok)

for condition in ("standing.never_revoked", "standing.approved_at_tier",
                  "standing.age_above:90d"):
    policy.validate_rules([{"when": [condition], "then": "auto"}])
check("only decisions Alice made herself may relax", True)
check("and every one of those is in RELAXING_CONDITIONS",
      policy.RELAXING_CONDITIONS < policy.STANDING_CONDITIONS
      and not (policy.RELAXING_CONDITIONS & policy.ASSURANCE_CONDITIONS))

for bad in ([{"when": ["standing.never_revoked"], "then": "maybe"}],
            [{"when": ["agent.is_nice"], "then": "ask"}],
            [{"when": [], "then": "ask"}],
            "not a list"):
    try:
        policy.validate_rules(bad)
        ok = False
    except ValueError:
        ok = True
    check(f"invalid rule set is refused: {str(bad)[:44]}", ok)

# --- a rule that saves must not be able to break the grant loop ---------------

for bad in ("assurance.provenance_below", "standing.age_above",
            "standing.age_above:soon", "assurance.provenance_below:x",
            "standing.never_revoked:1"):
    try:
        policy.validate_rules([{"when": [bad], "then": "ask"}])
        ok = False
    except ValueError:
        ok = True
    check(f"a malformed argument is refused at save time: {bad}", ok)

# And if one ever gets in another way, it must fail towards her rather than
# raising inside the token endpoint.
broken = [{"when": ["assurance.provenance_below:x"], "then": "refuse"}]
check("an unusable restriction is treated as matching",
      policy.evaluate(tier(rules=broken), facts())[0] == policy.REFUSE)
broken = [{"when": ["standing.age_above:soon"], "then": "auto"}]
check("an unusable relaxation is treated as not matching",
      policy.evaluate(tier(ask_me=True, rules=broken), facts(active=True))[0]
      == policy.ASK)

# --- assurance is derived, never claimed --------------------------------------

check("nothing is granted by construction — binding starts at 0",
      assurance.assess({"level": "identified", "iss": "https://ps.uma.lab",
                        "client_metadata": {"verified": True}})["binding"] == 0)
check("and is raised only by a signature this server verified",
      assurance.assess({"level": "pseudonymous", "key_bound": True})
      ["binding"] == 1)
check("a bare key is self-minted provenance",
      assurance.assess({"level": "pseudonymous"})["provenance"] == 0)
check("a verified issuer raises provenance",
      assurance.assess({"level": "identified", "iss": "https://ps.uma.lab"})
      ["provenance"] == 1)
check("no client metadata means no accountability",
      assurance.assess({"level": "pseudonymous"})["accountability"] == 0)
check("resolved client metadata is self-asserted accountability",
      assurance.assess({"level": "pseudonymous",
                        "client_metadata": {"verified": True,
                                            "client_name": "Sterling Vance"}})
      ["accountability"] == 1)
check("metadata that did not resolve is worth what none is worth",
      assurance.assess({"level": "pseudonymous",
                        "client_metadata": {"verified": False,
                                            "error": "timeout"}})
      ["accountability"] == 0)
check("the operator publishing this agent's key is worth more than saying so",
      assurance.assess({"level": "pseudonymous", "operator_attested": True,
                        "client_metadata": {"verified": True,
                                            "client_name": "Sterling Vance"}})
      ["accountability"] == 2)
check("a directory that did not check out leaves the claim self-asserted",
      assurance.assess({"level": "pseudonymous", "operator_attested": False,
                        "client_metadata": {"verified": True}})
      ["accountability"] == 1)
check("and attestation without a resolved operator is worth nothing",
      assurance.assess({"level": "pseudonymous",
                        "operator_attested": True})["accountability"] == 0)
check("an agent cannot assert its own level",
      assurance.assess({"level": "pseudonymous", "assurance": {"provenance": 1},
                        "accountability": 2})["provenance"] == 0)
check("there is no composite score to game",
      not any(n in dir(assurance) for n in ("score", "total", "overall", "level_of")))

# --- durations ----------------------------------------------------------------

check("durations parse", [policy.parse_duration(x) for x in ("90d", "12h", "45m", "30")]
      == [7776000, 43200, 2700, 30])

# --- terms she writes herself --------------------------------------------------

REGISTERED = {"alice-vault/get_positions", "alice-vault/get_transactions",
              "alice-vault/execute_trade", "alice-vault/get_statements"}
shipped = policy.defaults()

t = policy.new_tier("statements", {
    "name": "Statements", "ask_me": True,
    "resources": ["alice-vault/get_statements"],
    "terms": {"purpose": "Preparing my annual return", "expires_in": 86400,
              "prohibited": ["model-training"]}}, shipped, REGISTERED)
check("she can write a tier of her own", t["terms"]["purpose"].startswith("Preparing"))
check("its terms document starts at v1", t["terms"]["template_id"] == "alice/statements/v1")
check("and it carries her ask-me choice", t["ask_me"] is True)

for spec, why in (
    ({"id": "x", "resources": ["alice-vault/get_positions"],
      "terms": {"purpose": "p", "expires_in": 60}}, "a resource another tier governs"),
    ({"id": "x", "resources": ["alice-vault/nope"],
      "terms": {"purpose": "p", "expires_in": 60}}, "a resource nobody protects"),
    ({"id": "x", "terms": {"expires_in": 60}}, "terms with no purpose"),
    ({"id": "x", "terms": {"purpose": "p"}}, "terms that never expire"),
    ({"id": "x", "resources": [], "rules": [{"when": ["standing.none"], "then": "auto"}],
      "terms": {"purpose": "p", "expires_in": 60}}, "a rule that cannot relax"),
):
    try:
        policy.new_tier(spec["id"], spec, shipped, REGISTERED)
        ok = False
    except ValueError:
        ok = True
    check(f"she cannot write a tier over {why}", ok)

for bad in ("tier1", "", "has spaces", "../etc"):
    try:
        policy.new_tier(bad, {"terms": {"purpose": "p", "expires_in": 60}},
                        shipped, REGISTERED)
        ok = False
    except ValueError:
        ok = True
    check(f"a tier id must be new and a plain slug: {bad!r}", ok)

check("a tier with no resources yet is allowed",
      policy.new_tier("later", {"terms": {"purpose": "p", "expires_in": 60}},
                      shipped, REGISTERED)["resources"] == [])

# --- the shipped defaults ------------------------------------------------------

# --- what the agent said it wants the access for -------------------------------
#
# The reason is the one claim the requesting side authors, so the only thing
# her policy may do with it is notice that it is missing.

ask_no_reason = tier(rules=[{"when": ["request.reason_absent"], "then": "ask"}])
check("no stated reason routes the request to her",
      policy.evaluate(ask_no_reason, facts(reason=None))[0] == policy.ASK)
check("an empty reason is no reason",
      policy.evaluate(ask_no_reason, facts(reason="   "))[0] == policy.ASK)
check("a stated reason costs nothing",
      policy.evaluate(ask_no_reason, facts(reason="cost basis check"))[0]
      == policy.AUTO)
check("but it cannot buy anything either",
      refused([{"when": ["request.reason_absent"], "then": "auto"}]))

# A cited mandate is a request fact and not an assurance axis, because nothing
# dereferenced it. From here, an agent that cites a mission and one that
# invents a hash are the same agent.
mandate = tier(rules=[{"when": ["request.mission_absent"], "then": "ask"}])
check("citing no mandate routes the request to her",
      policy.evaluate(mandate, facts())[0] == policy.ASK)
check("citing one costs nothing",
      policy.evaluate(mandate, facts(mission={"approver": "https://ps",
                                              "s256": "x" * 43}))[0]
      == policy.AUTO)
check("and buys nothing",
      refused([{"when": ["request.mission_absent"], "then": "auto"}]))

# --- what it has been doing lately ---------------------------------------------

repeat = tier(rules=[{"when": ["standing.denials_above:1"], "then": "ask"}])
check("two denials is not more than one... ",
      policy.evaluate(repeat, facts(active=True, denials=1))[0] == policy.AUTO)
check("...and three is",
      policy.evaluate(repeat, facts(active=True, denials=3))[0] == policy.ASK)
check("an agent she has never met has no history to hold against it",
      policy.evaluate(repeat, facts())[0] == policy.AUTO)

breadth = tier(rules=[{"when": ["standing.tiers_above:1"], "then": "ask"}])
check("reaching at one tier is not spreading",
      policy.evaluate(breadth, facts(active=True, tiers_seen=["tier1"]))[0]
      == policy.AUTO)
check("reaching at three is",
      policy.evaluate(breadth, facts(active=True,
                                     tiers_seen=["tier1", "tier2", "tier3"]))[0]
      == policy.ASK)

check("a denial record cannot be turned into a reason to grant",
      refused([{"when": ["standing.denials_above:1"], "then": "auto"}]))
check("nor can the number of tiers it has reached",
      refused([{"when": ["standing.tiers_above:1"], "then": "auto"}]))
check("a count has to be a count",
      refused([{"when": ["standing.denials_above:soon"], "then": "ask"}]))
check("and it cannot be negative, which would fire always",
      refused([{"when": ["standing.tiers_above:-1"], "then": "ask"}]))
check("a count condition without its argument is unstorable",
      refused([{"when": ["standing.denials_above"], "then": "ask"}]))

# A rule that cannot be evaluated must land on more friction, not less. This is
# the shape a stored-before-validation rule would have.
check("an unevaluable restriction still asks",
      policy.evaluate(tier(rules=[{"when": ["standing.age_above:1d"],
                                   "then": "ask"}]),
                      {"assurance": {}, "standing": {}, "request": {},
                       "tier": "tier1"})[0] == policy.ASK)


d = policy.defaults()
for tid, t in d.items():
    policy.validate_rules(t.get("rules", []))
check("every shipped tier's rules are valid", True)
check("trades ship with no relaxation",
      not any(r["then"] == policy.AUTO for r in d["tier3"]["rules"]))
check("transactions ask on first use at that tier",
      policy.evaluate(d["tier2"], facts(active=True, accountability=1,
                                        first_at_tier=True))[0] == policy.ASK)
check("holdings stay quiet for an accountable, established agent",
      policy.evaluate(d["tier1"], facts(active=True, accountability=1,
                                        first_at_tier=False))[0] == policy.AUTO)

# --- sub-agents: the three things she can say ---------------------------------
#
# Approval belongs to the lineage rather than to one connection, and which of
# those three sentences applies is hers to write per tier. These assert the
# verdicts each one actually produces, because the postures are expressed in
# rule combinations rather than in a setting — if `evaluate`'s precedence ever
# changed, two of these would silently invert.

per_agent = {"ask_me": False,
             "rules": [{"when": ["standing.first_at_tier"], "then": "ask"}]}
lineage = {"ask_me": False,
           "rules": [{"when": ["standing.first_at_tier",
                               "standing.lineage_new_at_tier"], "then": "ask"}]}
always_ask = {"ask_me": False,
              "rules": [{"when": ["standing.first_at_tier"], "then": "ask"},
                        {"when": ["standing.introduced"], "then": "ask"}]}

for name, tier in (("per-agent", per_agent), ("lineage-wide", lineage),
                   ("always-ask", always_ask)):
    policy.validate_rules(tier["rules"])
check("all three sub-agent postures are storable", True)

# 1 · Per-agent. The default, and it does not care about lineage at all.
check("per-agent: a sub-agent is asked about even when its lineage was approved",
      policy.evaluate(per_agent, facts(active=True, accountability=2,
                                       introduced=True, first_at_tier=True,
                                       lineage_new_at_tier=False))[0] == policy.ASK)

# 2 · Lineage-wide. The ask narrows to fleets she has not yet said yes to.
check("lineage-wide: a sub-agent of an approved lineage goes through",
      policy.evaluate(lineage, facts(active=True, accountability=2,
                                     introduced=True, first_at_tier=True,
                                     lineage_new_at_tier=False))[0] == policy.AUTO)
check("lineage-wide: a tier the lineage never reached still asks",
      policy.evaluate(lineage, facts(active=True, accountability=2,
                                     introduced=True, first_at_tier=True,
                                     lineage_new_at_tier=True))[0] == policy.ASK)
# The direction that inverts the usual model: the parent benefits from what
# its sub-agent earned, and it is the same rule doing it.
check("lineage-wide: the introducing agent inherits what a sub-agent earned",
      policy.evaluate(lineage, facts(active=True, accountability=2,
                                     introduced=False, first_at_tier=True,
                                     lineage_new_at_tier=False))[0] == policy.AUTO)

# 3 · Always ask. Restrictions win, so this outranks the narrowing above.
check("always-ask: a sub-agent is asked about however established its lineage",
      policy.evaluate(always_ask, facts(active=True, accountability=2,
                                        introduced=True, first_at_tier=False,
                                        lineage_new_at_tier=False))[0] == policy.ASK)
check("always-ask: an agent she met directly is unaffected",
      policy.evaluate(always_ask, facts(active=True, accountability=2,
                                        introduced=False, first_at_tier=False,
                                        lineage_new_at_tier=False))[0] == policy.AUTO)

# The ceiling, which is not configurable: an ask-me tier still asks. A lineage
# rule cannot lower a baseline, only narrow a rule.
check("no sub-agent rule lowers an ask-me tier",
      policy.evaluate({"ask_me": True, "rules": lineage["rules"]},
                      facts(active=True, accountability=2, introduced=True,
                            lineage_new_at_tier=False))[0] == policy.ASK)


# --- what the act leaves behind -----------------------------------------------
#
# The class is published by the party that performs the operation, so unlike
# every other fact the requesting side supplies, reading it is not reading the
# counterparty's own account of itself. It still may only tighten: the rule she
# gets out of it is "ask me about anything that cannot be undone", which names
# no tool and so holds for tools she has never seen.

def _over(rules) -> dict:
    return {"ask_me": False, "rules": rules, "terms": {"expires_in": 3600}}


undoable = _over([{"when": ["request.consequence_at_or_above:irreversible"],
                   "then": "ask"}])
check("a tier that grants automatically still asks about what cannot be undone",
      policy.evaluate(undoable, facts(consequence="irreversible"))[0] == policy.ASK)
check("and goes on granting what can be",
      policy.evaluate(undoable, facts(consequence="reversible"))[0] == policy.AUTO)
check("the order is by remedy, so forward-recoverable is not yet irreversible",
      policy.evaluate(undoable, facts(consequence="forward_recoverable"))[0] == policy.AUTO)

costly = _over([{"when": ["request.consequence_at_or_above:compensatable"],
                 "then": "ask"}])
check("a lower floor catches everything at or past it",
      all(policy.evaluate(costly, facts(consequence=c))[0] == policy.ASK
          for c in ("compensatable", "forward_recoverable", "irreversible")))
check("and nothing below it",
      policy.evaluate(costly, facts(consequence="reversible"))[0] == policy.AUTO)

# Absent is unknown. Not benign — she may refuse it — and not severe, because
# an operation nobody has described is not evidence about anything.
check("an undeclared operation does not fire a rule about severity",
      policy.evaluate(undoable, facts(consequence=None))[0] == policy.AUTO)
undescribed = _over([{"when": ["request.consequence_unknown"], "then": "ask"}])
check("but she can ask about anything nobody has described",
      policy.evaluate(undescribed, facts(consequence=None))[0] == policy.ASK)
check("and that rule leaves described operations alone",
      policy.evaluate(undescribed, facts(consequence="irreversible"))[0] == policy.AUTO)
check("a word this vocabulary does not know is no declaration, not a fifth class",
      policy.evaluate(undescribed, facts(consequence="catastrophic"))[0] == policy.ASK)

# The asymmetry, at save time rather than at evaluation time.
check("a consequence class cannot be made to grant automatically",
      refused([{"when": ["request.consequence_at_or_above:irreversible"],
                "then": "auto"}]))
check("nor can nobody-has-said",
      refused([{"when": ["request.consequence_unknown"], "then": "auto"}]))
check("a class the vocabulary does not know cannot be saved at all",
      refused([{"when": ["request.consequence_at_or_above:catastrophic"],
                "then": "ask"}]))
check("and the condition is not writable without one",
      refused([{"when": ["request.consequence_at_or_above"], "then": "ask"}]))

_vocab = {v["condition"]: v for v in policy.vocabulary()}
check("her policy surface offers the classes, none of them able to relax",
      any(c.startswith("request.consequence") for c in _vocab)
      and not any(_vocab[c]["may_relax"] for c in _vocab
                  if c.startswith("request.consequence")))


# --- her attention has a floor and a ceiling -----------------------------------

check("the pend budget is a small positive default", 0 < policy.PEND_BUDGET <= 20)

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
