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
          revocations=0, expires_in=0, max_expires_in=3600,
          tier_id="tier1") -> dict:
    return {
        "assurance": {"binding": binding, "provenance": provenance,
                      "accountability": accountability},
        "standing": {"active": active, "age_seconds": age,
                     "first_at_tier": first_at_tier,
                     "approved_tiers": list(approved_tiers),
                     "revocations": revocations},
        "request": {"expires_in": expires_in, "max_expires_in": max_expires_in},
        "tier": tier_id,
    }


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

# --- her attention has a floor and a ceiling -----------------------------------

check("the pend budget is a small positive default", 0 < policy.PEND_BUDGET <= 20)

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
