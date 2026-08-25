"""The joint-ownership algebra, checked in a bare interpreter.

Same argument as `test_org.py`: everything here is a pure function over
dictionaries, so it can be checked with nothing running and nothing
installed. The mandate validator and the tally are where a mistake is
expensive and silent — a threshold off by one releases a jointly held
resource on one person's say-so — so they are checked here rather than only
end to end.

    python lib/test_joint.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import uma4a_joint as j  # noqa: E402

PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"   {'ok  ' if ok else 'FAIL'} {name}"
          + (f" — {detail}" if detail and not ok else ""))


def refuses(name: str, doc, floor=0) -> None:
    try:
        j.validate_mandate(doc, floor=floor)
    except j.MandateError as exc:
        check(name, True, str(exc))
        return
    check(name, False, "it was accepted")


RESOURCE = ["meridian-joint/*"]


def mandate(**over):
    doc = {"resources": RESOURCE,
           "holders": [{"owner": "alice", "issuer": "https://alice-as.uma.lab"},
                       {"owner": "carol", "issuer": "https://carol-as.uma.lab"}],
           "rule": {"kind": "all"}}
    doc.update(over)
    return j.validate_mandate(doc)


def tier(expires=3600, scope=("positions:read", "transactions:read"),
         prohibited=("model-training",), ask=False):
    return {"name": "Joint account", "resources": list(RESOURCE), "ask_me": ask,
            "terms": {"expires_in": expires, "scope": list(scope),
                      "prohibited": list(prohibited)}}


print("\n-- the mandate names the electorate --")
m = mandate()
check("two holders of equal weight, unanimity", m["rule"]["threshold"] == 2
      and m["total_weight"] == 2, f"{m['rule']}")
check("`any` is satisfied by the lightest holder alone",
      mandate(rule={"kind": "any"})["rule"]["threshold"] == 1)
weighted = mandate(holders=[
    {"owner": "alice", "issuer": "https://alice-as.uma.lab", "weight": 3},
    {"owner": "carol", "issuer": "https://carol-as.uma.lab", "weight": 1}],
    rule={"kind": "threshold", "threshold": 3})
check("holders can carry different weight", weighted["total_weight"] == 4
      and weighted["rule"]["threshold"] == 3)
check("and `any` with weights still means the lightest can act alone",
      mandate(holders=weighted["holders"], rule={"kind": "any"})
      ["rule"]["threshold"] == 1)

refuses("one holder is not a mandate",
        {"resources": RESOURCE,
         "holders": [{"owner": "alice", "issuer": "https://alice-as.uma.lab"}]})
refuses("the same holder listed twice is refused",
        {"resources": RESOURCE,
         "holders": [{"owner": "alice", "issuer": "https://alice-as.uma.lab"},
                     {"owner": "alice", "issuer": "https://alice-as.uma.lab"}]})
refuses("a holder whose verdicts could not be verified is refused",
        {"resources": RESOURCE,
         "holders": [{"owner": "alice", "issuer": "http://alice-as.uma.lab"},
                     {"owner": "carol", "issuer": "https://carol-as.uma.lab"}]})
refuses("a mandate over nothing is refused",
        {"resources": [], "holders": [
            {"owner": "alice", "issuer": "https://alice-as.uma.lab"},
            {"owner": "carol", "issuer": "https://carol-as.uma.lab"}]})
refuses("a threshold nobody could ever reach is refused",
        {"resources": RESOURCE, "rule": {"kind": "threshold", "threshold": 5},
         "holders": [{"owner": "alice", "issuer": "https://alice-as.uma.lab"},
                     {"owner": "carol", "issuer": "https://carol-as.uma.lab"}]})

print("\n-- a floor the holders did not set, and may not lower --")
check("a mandate at or above the floor stands",
      j.validate_mandate({"resources": RESOURCE, "rule": {"kind": "all"},
                          "holders": mandate()["holders"]}, floor=2)
      ["rule"]["threshold"] == 2)
refuses("one below it is refused, in the holders' words",
        {"resources": RESOURCE, "rule": {"kind": "any"},
         "holders": mandate()["holders"]}, floor=2)

print("\n-- folding every holder's terms into one document --")
strict = tier(expires=900, scope=("positions:read",),
              prohibited=("resale",), ask=True)
folded, changes = j.fold([("alice", tier()), ("carol", strict)], RESOURCE)
t = folded["terms"]
check("the shortest expiry any holder set", t["expires_in"] == 900,
      f"{t['expires_in']}")
check("only the scopes every holder offers", t["scope"] == ["positions:read"],
      f"{t['scope']}")
check("every prohibition any holder wrote",
      set(t["prohibited"]) == {"model-training", "resale"}, f"{t['prohibited']}")
check("and if one holder wants asking, everybody is asked",
      folded["ask_me"] is True)
check("each holder is told what her co-owners' terms did to hers",
      [c["field"] for c in changes["alice"]] == [] and
      {c["field"] for c in changes["carol"]}
      >= {"max_expires_in", "allowed_scopes"},
      f"{ {k: [c['field'] for c in v] for k, v in changes.items()} }")

again, _ = j.fold([("alice", folded), ("carol", strict)], RESOURCE)
check("folding an already-folded document changes nothing further",
      again["terms"] == folded["terms"] and again["ask_me"] == folded["ask_me"])
alone, _ = j.fold([("alice", tier()), ("carol", tier())], RESOURCE)
check("two holders who agree lose nothing", alone["terms"] == tier()["terms"])

print("\n-- the count --")
check("nobody has answered yet",
      j.tally(m, {})["effect"] == "pending")
check("one of two, under unanimity, is still pending",
      j.tally(m, {"alice": "allow"})["effect"] == "pending")
check("both allow and it is granted",
      j.tally(m, {"alice": "allow", "carol": "allow"})["effect"] == "allow")
early = j.tally(m, {"carol": "refuse"})
check("one refusal ends it without waiting for the other",
      early["effect"] == "refuse" and early["outstanding"] == ["alice"],
      f"{early}")
any_m = mandate(rule={"kind": "any"})
check("under `any`, one holder is enough",
      j.tally(any_m, {"alice": "allow"})["effect"] == "allow")
check("and one refusal there is not — the other can still release it",
      j.tally(any_m, {"alice": "refuse"})["effect"] == "pending")
check("until nobody is left who could",
      j.tally(any_m, {"alice": "refuse", "carol": "refuse"})["effect"] == "refuse")
check("a heavier holder can carry a threshold alone",
      j.tally(weighted, {"alice": "allow"})["effect"] == "allow")
check("and the lighter one cannot",
      j.tally(weighted, {"carol": "allow"})["effect"] == "pending")
check("a verdict from somebody who is not a holder is not counted",
      j.tally(m, {"dana": "allow"})["for"] == 0)

print("\n-- what the holders are shown --")
lines = j.describe(m)
check("the sentences name the rule and the reach",
      any("Any one of you can stop it" in x for x in lines)
      and any("meridian-joint/*" in x for x in lines), f"{lines}")
check("and say that the terms are everybody's at once",
      any("every prohibition any of you wrote" in x for x in lines), f"{lines}")
check("a resource outside the mandate is not governed by it",
      j.governs(m, "meridian-joint/get_positions")
      and not j.governs(m, "alice-vault/get_positions"))

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
for f in FAIL:
    print(f"  - {f}")
raise SystemExit(1 if FAIL else 0)
