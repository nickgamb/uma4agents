"""The organization's ceiling: what it may do to a member's terms.

Run it with no dependencies:

    python3 lib/test_org.py

One property carries most of the weight here, and it is the mirror of the one
`test_policy.py` is about:

    **a ceiling can only ever narrow.**

Everything else — the pattern language, the compliance report, the
enforcement point's independent check — is in service of that. The refusals
matter more than the allows again: an envelope that only proved it clamps
would pass with every widening path left in.

The second property is subtler and is the one that makes the arrangement
honest rather than merely safe: **what the organization learns is a fact
about its own ceiling, not a fact about her policy.**
"""

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT / "services" / "uma-as"))
sys.path.insert(0, str(ROOT / "services" / "org-authority"))

import charter  # noqa: E402
import org  # noqa: E402
import uma4a_org  # noqa: E402

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"{'ok  ' if ok else 'FAIL'} {name}" + (f" — {detail}" if detail and not ok else ""))


BOOK = "northwind-vault"


def envelope(**over):
    """A charter over the organization's *own* resources.

    Not a pattern across everybody's accounts, and that is the model rather
    than a detail of the fixture: the organization owns a book and shares it
    with its members. A member's own vault matches nothing here, and every
    test below that says "her own accounts are untouched" is testing that
    this is structurally true rather than politely observed.
    """
    base = {
        "org": "northwind", "name": "Northwind Capital", "charter_version": 3,
        "claims": [f"{BOOK}/*"],
        "grants": [f"{BOOK}/get_positions", f"{BOOK}/get_transactions"],
        "delegation": "first-party-only",
        "role": "analyst", "role_name": "Analyst",
        "max_expires_in": 3600,
        "allowed_scopes": ["positions:read", "transactions:read"],
        "require_prohibited": ["model-training"],
        "always_ask": [f"{BOOK}/execute_trade"],
    }
    base.update(over)
    return base


def tier(**over):
    """Her terms over a resource the organization shares with her."""
    base = {
        "name": "Northwind book", "resources": [f"{BOOK}/get_positions"],
        "ask_me": False, "rules": [],
        "terms": {"template_id": "alice/firmbook/v2", "purpose": "review",
                  "scope": ["positions:read"], "expires_in": 172800,
                  "prohibited": ["marketing"]},
    }
    base.update(over)
    return base


def own(**over):
    """Her terms over her own brokerage account. Nothing here is the
    organization's business, and the tests say so."""
    base = {
        "name": "Holdings", "resources": ["alice-vault/get_positions"],
        "ask_me": False, "rules": [],
        "terms": {"template_id": "alice/tier1/v2", "purpose": "suitability",
                  "scope": ["positions:read"], "expires_in": 172800,
                  "prohibited": ["marketing"]},
    }
    base.update(over)
    return base


# --- The pattern language ----------------------------------------------------
#
# Four evaluators have to agree on it: this one, the organization's, the
# enforcement point's, and `glob.match` in org.rego. Only the first three can
# be tested from here; the fourth is exercised by `make org-check`, which is
# the reason that check asserts on an always-ask resource.

check("a charter pattern covers the organization's own resources",
      uma4a_org.claims_match(f"{BOOK}/get_positions", [f"{BOOK}/*"]))
check("and reaches nobody's personal accounts",
      not uma4a_org.claims_match("alice-vault/get_positions", [f"{BOOK}/*"])
      and not uma4a_org.claims_match("carol-vault/get_positions", [f"{BOOK}/*"]))
check("a wildcard stops at the separator",
      not uma4a_org.claims_match(f"{BOOK}/sub/get_positions", [f"{BOOK}/*"]))
check("an unrelated resource matches nothing",
      not uma4a_org.claims_match("alice-vault/get_statements", [f"{BOOK}/*"]))
check("and the organization's copy of the matcher is the same object",
      charter.claims_match is uma4a_org.claims_match
      and org.claims_match is uma4a_org.claims_match)


# --- What the ceiling does ---------------------------------------------------

clamped, changes = org.clamp(tier(), envelope())
check("an expiry above the ceiling comes down to it",
      clamped["terms"]["expires_in"] == 3600)
check("a prohibition the charter requires is added",
      "model-training" in clamped["terms"]["prohibited"])
check("and one she wrote herself survives",
      "marketing" in clamped["terms"]["prohibited"])
check("every change is reported in words, for two surfaces that need them",
      len(changes) == 2 and all(c["text"] and c["field"] for c in changes))

t3 = tier(resources=[f"{BOOK}/execute_trade"], ask_me=False)
t3["terms"]["scope"] = ["trades:execute", "transactions:read"]
clamped3, changes3 = org.clamp(t3, envelope())
check("a resource the charter names always-ask starts asking",
      clamped3["ask_me"] is True)
check("a scope the charter does not allow is dropped from her terms",
      clamped3["terms"]["scope"] == ["transactions:read"],
      f"{clamped3['terms']['scope']}")

untouched, none = org.clamp(own(), envelope())
check("her own account is left entirely alone by the charter",
      none == [] and untouched["terms"]["expires_in"] == 172800,
      "the organization reached a resource of hers")
check("and `governs` says so before anything is computed",
      not org.governs(own(), envelope()))

mixed = tier(resources=[f"{BOOK}/get_positions", "alice-vault/get_statements"])
check("a tier mixing claimed and unclaimed resources is governed as a whole",
      org.governs(mixed, envelope()),
      "one terms document cannot be half-clamped, and of the two available "
      "directions only this one fails safe")


# --- The property that matters -----------------------------------------------
#
# Enumerated rather than asserted once, because the interesting failures are
# the combinations: a charter with no scope restriction, a ceiling above her
# expiry, a tier that already asks. None of them may produce something wider
# than what went in.

def wider(before, after):
    """Whether `after` permits anything `before` did not."""
    b, a = before["terms"], after["terms"]
    if a["expires_in"] > b["expires_in"]:
        return "expiry grew"
    if set(a.get("scope") or []) - set(b.get("scope") or []):
        return "a scope appeared"
    if set(b.get("prohibited") or []) - set(a.get("prohibited") or []):
        return "a prohibition vanished"
    if before.get("ask_me") and not after.get("ask_me"):
        return "an ask-me tier stopped asking"
    return None

widened = []
for ceiling in (60, 3600, 999999):
    for scopes in (None, [], ["positions:read"], ["positions:read", "trades:execute"]):
        for required in ([], ["model-training"], ["marketing"]):
            for ask in ([], [f"{BOOK}/get_positions"], [f"{BOOK}/execute_trade"]):
                for start_ask in (True, False):
                    env = envelope(max_expires_in=ceiling, allowed_scopes=scopes,
                                   require_prohibited=required, always_ask=ask)
                    original = tier(ask_me=start_ask)
                    out, _ = org.clamp(original, env)
                    if why := wider(original, out):
                        widened.append((ceiling, scopes, required, ask, start_ask, why))
check("no combination of envelope and tier produces wider terms than it started with",
      not widened, f"{widened[:3]}")

twice, again = org.clamp(clamped, envelope())
check("clamping an already-clamped tier changes nothing further",
      again == [] and twice["terms"] == clamped["terms"])

before = copy.deepcopy(tier())
org.clamp(before, envelope())
check("and the input is never mutated", before == tier())


# --- Writing terms while enrolled -------------------------------------------

problems = org.would_exceed(
    {"terms": {"expires_in": 864000, "scope": ["positions:read"]}},
    [f"{BOOK}/get_positions"], envelope())
check("new terms above the ceiling are refused with the reason", len(problems) == 1
      and "Northwind Capital" in problems[0], f"{problems}")
check("new terms over her own accounts are not its business",
      org.would_exceed({"terms": {"expires_in": 864000}},
                       ["alice-vault/get_positions"], envelope()) == [])

patch, _ = org.patch_for(tier(), envelope())
check("the clamp is expressed as a patch, so the store bumps the terms version",
      patch is not None and set(patch) == {"ask_me", "terms"})
scopeless = tier()
del scopeless["terms"]["scope"]
patch_s, _ = org.patch_for(scopeless, envelope())
check("and a tier with no scope does not acquire an empty one",
      "scope" not in (patch_s or {}).get("terms", {}), f"{patch_s}")
check("and there is no patch when there is nothing to do",
      org.patch_for(clamped, envelope())[0] is None)


# --- What the organization learns -------------------------------------------

report = org.compliance({"firmbook": clamped, "firmtrade": clamped3}, envelope(),
                        [f"{BOOK}/get_positions", f"{BOOK}/execute_trade",
                         "alice-vault/get_positions"],
                        clamped_fields=["max_expires_in"])
check("it is told how many of its own resources she governs",
      report["resources_governed"] == 2)
check("it is told which of its fields bit", report["clamped_fields"] == ["max_expires_in"])
check("and that her terms are inside the ceiling", report["within"] is True)
blob = repr(report)
check("and nothing else — no purpose, no template id, no prohibition of hers",
      not any(x in blob for x in ("review", "alice/firmbook", "marketing")), blob)

outstanding = org.compliance({"firmbook": tier()}, envelope(),
                             [f"{BOOK}/get_positions"])
check("a member who has not been re-clamped yet is reported as outside, not inside",
      outstanding["within"] is False and "max_expires_in" in outstanding["clamped_fields"])


# --- What her portal shows above her own terms ------------------------------

view = org.tier_view(tier(), envelope())
check("her portal is told the organization's name, not the charter's title",
      view["name"] == "Northwind Capital")
check("and what is pending against her stored terms",
      len(view["pending"]) == 2, f"{view}")
check("a tier over her own accounts has no band at all",
      org.tier_view(own(), envelope()) is None)
check("and neither does one belonging to a member of nothing",
      org.tier_view(tier(), None) is None)


# --- The enforcement point's independent check -------------------------------
#
# The half of the ceiling that is checkable from a token alone. Less than the
# whole of it, and the tests say so explicitly rather than leaving the gap to
# be discovered.

env = envelope()
check("a grant longer than the ceiling is a breach the resource side can see",
      uma4a_org.envelope_breach({"resource_scopes": ["positions:read"]}, env, 7200))
check("a grant inside it is not",
      uma4a_org.envelope_breach({"resource_scopes": ["positions:read"]}, env, 3500) is None)
check("clock skew is not read as a policy breach",
      uma4a_org.envelope_breach({"resource_scopes": []}, env,
                                3600 + uma4a_org.CLOCK_SLACK_S - 1) is None)
check("a scope the charter does not allow is a breach",
      uma4a_org.envelope_breach({"resource_scopes": ["trades:execute"]}, env, 60))
check("an unrestricted charter allows any scope",
      uma4a_org.envelope_breach({"resource_scopes": ["anything:at-all"]},
                                envelope(allowed_scopes=None), 60) is None)


# --- What may be written in a charter ---------------------------------------

def refuses(doc, because):
    try:
        charter.validate(doc)
    except ValueError as exc:
        return because in str(exc)
    return False


ok = charter.validate(charter.DEFAULT_CHARTER)
check("the charter this lab ships is valid", ok["name"])
check("a charter that claims nothing is refused",
      refuses({**charter.DEFAULT_CHARTER, "claims": []}, "claims must be"))
check("a charter with no ceiling on expiry is refused",
      refuses({**charter.DEFAULT_CHARTER, "envelope": {}}, "max_expires_in"))
check("an absurd ceiling is refused before it reaches every member at once",
      refuses({**charter.DEFAULT_CHARTER,
               "envelope": {"max_expires_in": 99 * 86400}}, "between"))
check("break-glass over a resource the charter does not claim is refused",
      refuses({**charter.DEFAULT_CHARTER,
               "break_glass": {"enabled": True,
                               "resources": ["alice-vault/get_positions"]}},
              "does not claim"),
      "an override outside what members were shown is a second front door")
check("break-glass with no stated subject is refused",
      refuses({**charter.DEFAULT_CHARTER, "break_glass": {"enabled": True}},
              "resources is required"))
check("a custom rule that tries to *allow* is refused, not ignored",
      refuses({**charter.DEFAULT_CHARTER,
               "rego": "package u4a.custom\n\ndefault allow := true\n"},
              "can only ever make a request harder"),
      "an administrator would believe he had granted something")
check("custom rules in the wrong package are refused rather than silently ignored",
      refuses({**charter.DEFAULT_CHARTER, "rego": "package somewhere.else\n"},
              "u4a.custom"))

envelope_out = charter.envelope_of(ok)
check("the envelope that leaves carries the ceiling and the disclosure",
      envelope_out["max_expires_in"] and envelope_out["summary"]
      and envelope_out["powers"])
check("and not the organization's conditions or its rules",
      "conditions" not in envelope_out and "rego" not in envelope_out,
      "those are evaluated at the organization's own decision point")
check("the charter's own title does not shadow the organization's name",
      "name" not in envelope_out and envelope_out["charter_name"])

powers = charter.powers(ok)
check("what she is offered leads with what she gets",
      len(powers["gets"]) >= 2
      and any("northwind-vault" in p["what"] for p in powers["gets"]),
      f"{[p['what'] for p in powers['gets']]}")
check("and names whose agents may act on it for her",
      any("agent" in p["what"].lower() for p in powers["gets"]))
check("what she agrees to names every standing authority she is granting",
      len(powers["can"]) >= 6 and len(powers["cannot"]) >= 4,
      f"{len(powers['can'])} / {len(powers['cannot'])}")
check("and the boundary is stated as plainly as the authority",
      any(p["what"] == "Touch anything of yours" for p in powers["cannot"]),
      f"{[p['what'] for p in powers['cannot']]}")
check("including break-glass, when the charter has it",
      any("Break glass" in p["what"] for p in powers["can"]))
off = charter.powers({**ok, "break_glass": {"enabled": False}})
check("and saying so plainly when it does not",
      not any("Break glass" in p["what"] for p in off["can"])
      and any("without going through your policy" in p["what"] for p in off["cannot"]))


# --- Roles: what membership is *for* -----------------------------------------
#
# The half that makes joining an exchange rather than a submission. A charter
# that only narrowed would be a strange thing to volunteer for.

roles = ok["roles"]
check("a role grants resources the charter claims",
      all(uma4a_org.claims_match(g.replace("/*", "/get_positions"), ok["claims"])
          for r in roles.values() for g in r["grants"]))
check("and says whose agents may act on them",
      {r["delegation"] for r in roles.values()} <= charter.DELEGATION)
check("a role that hands out somebody's personal account is refused",
      refuses({**charter.DEFAULT_CHARTER,
               "roles": {"x": {"grants": ["alice-vault/get_positions"],
                               "delegation": "none"}}}, "does not claim"),
      "an organization may only share what it owns")
check("a delegation setting nobody defined is refused",
      refuses({**charter.DEFAULT_CHARTER,
               "roles": {"x": {"grants": [f"{BOOK}/*"], "delegation": "sure"}}},
              "delegation must be one of"))
check("and a default role that does not exist is refused",
      refuses({**charter.DEFAULT_CHARTER, "default_role": "nobody"},
              "is not a role here"))
check("the shipped charter starts a member on the read-only role",
      ok["default_role"] == "analyst"
      and roles["analyst"]["delegation"] == "first-party-only",
      "enrolment should neither do nothing nor hand out trade authority")


print()
print("\n-- what no organization reaches, whatever its charter says --")
joint = "meridian-joint/get_positions"
wide = {**envelope(), "claims": ["*/get_positions"]}
check("a pattern can reach an account she holds with somebody else",
      uma4a_org.claims_match(joint, wide["claims"]))
check("but the ceiling does not, once it is excluded",
      not uma4a_org.reaches(joint, {**wide, "excluded": [joint]}))
check("and her own resources are still reached",
      uma4a_org.reaches("alice-vault/get_positions",
                        {**wide, "excluded": [joint]}))
jt = {"name": "joint", "resources": [joint], "ask_me": False,
      "terms": {"expires_in": 86400, "scope": ["positions:read"],
                "prohibited": []}}
check("a tier over it is not governed, so it is never clamped",
      not org.governs(jt, {**wide, "excluded": [joint]}))
clamped_j, changes_j = org.clamp(jt, {**wide, "excluded": [joint]})
check("and its terms come back exactly as she wrote them",
      clamped_j["terms"]["expires_in"] == 86400 and not changes_j,
      f"{clamped_j['terms']['expires_in']} {changes_j}")
check("with no exclusion, the same charter would have clamped it",
      org.clamp(jt, wide)[0]["terms"]["expires_in"] == 3600)

print("\n-- a charter may only claim a namespace it names --")
for bad in ("*/get_positions", "*/*", "*"):
    try:
        charter.validate({"name": "t", "claims": [bad],
                          "envelope": {"max_expires_in": 3600}})
        check(f"a claim of {bad!r} is refused", False, "it was accepted")
    except ValueError as exc:
        check(f"a claim of {bad!r} is refused", True, str(exc))
check("a concrete namespace is accepted",
      charter.validate({"name": "t", "claims": ["northwind-vault/*"],
                        "envelope": {"max_expires_in": 3600}})["claims"]
      == ["northwind-vault/*"])

print(f"{len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    for f in FAIL:
        print(f"  - {f}")
raise SystemExit(1 if FAIL else 0)
