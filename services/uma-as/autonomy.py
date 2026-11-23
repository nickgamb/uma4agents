"""Earned autonomy, and why every agent has two ladders.

`assurance.py` answers what her authority can establish about an agent it has
never met. This module answers the question that comes after: once she has
met it, **how much may it do without asking her?** The vocabulary is the
Cloud Security Alliance's Agentic Trust Framework (ATF) maturity model, used
as written:

    1  intern     observe and report       nothing it does changes anything
    2  junior     recommend and approve    every act waits for a human
    3  senior     act and notify           it acts, and someone is told
    4  principal  autonomous in a domain   it acts, and escalates the edge

ATF describes one ladder, held by the organisation that deploys the agent. It
had no reason to describe two: inside one enterprise the party governing the
agent and the party whose systems it touches are the same party. UMA's whole
contribution is that they are not. The requesting party's operator runs the
agent; the resource owner holds what it asks for. So under U4A **every agent
stands on two ladders at once**, and this module keeps them apart.

The operator's ladder
---------------------
ATF as Josh Woodruff wrote it, run by the operator over its own agents. The
operator publishes where an agent stands — in its Client ID Metadata
Document, beside the rest of what it says about itself — and her authority
reads it. Under U4A it may only **tighten**: an operator that says its own
agent is an intern is telling her something she should hear, and an operator
that says its agent is a principal is telling her nothing she has to act on.

That is the same asymmetry assurance has, and for the same reason. The level
is the requesting side's statement about itself. A lie upwards gains nothing,
because nothing reads the level as a reason to widen; a lie downwards costs
the liar. So it needs no verification to be *safe*, and is shown to her with
whatever her authority could verify about who said it.

The resource owner's ladder
---------------------------
The same four rungs, held by her authority, about this agent, with her. Every
agent starts on the bottom rung, because ATF says so ("Initial maturity level
set (always Intern)") and because U4A says so independently: standing starts
at zero, and a level another party granted is not standing with her.

**Only she may raise it**, one rung at a time, and the level is therefore one
of the very few facts allowed to relax one of her rules. She may lower it any
distance, and so does revoking the agent: a revoked agent she later readmits
is an intern again. Lowering is a restriction, and a restriction never needs
an argument — `change` would accept one from a party acting for her. This
deployment gives no such party an endpoint for it, though, and the reason is
scope rather than trust: her ladder covers her own accounts as well as any
organization's, and an organization's administrator already has the narrower
tool, shutting an agent out of the organization's resources.

That gives the invariant everything else leans on, stated once:

    **the owner's level can rise only by her hand, so whatever it reads now
    is at or below a level she personally granted.**

Which is why `standing.autonomy_at_least` may sit on the relaxing side of the
line in `policy.py` without breaking the rule that only her own decisions
relax anything.

How they compose
----------------
Neither ladder is read through the other, and there is no function here that
combines them — the same refusal `assurance.py` makes, for the same reason. A
composite is how an operator's "principal" would come to excuse a stranger.
The owner's policy reads both, as separate conditions, and the profile below
writes the composition out as rules a person can read: **whichever ladder
stands lower governs.** An operator's demotion reaches every owner on the
agent's next request without any of them doing anything. Nobody's promotion
reaches anybody.

What ATF asks for and this does not decide
------------------------------------------
ATF's five promotion gates are performance, security validation, business
value, incident record and governance sign-off. Two of those are visible from
her side — time at the current level, and how often she has said yes to what
it asked — and `eligibility` reports them. The rest are evidence about the
operator's programme rather than about this agent with her, and are the
operator's to show. None of it promotes anything. The fifth gate *is* her
decision, and the only thing that can make it.

Third-party attestation (ATF Certified) is the evidence that would let an
outsider stand behind the operator's ladder. It is read here as a claim and
displayed as one, and is deliberately not credited: there is not yet a
registry a relying party can fetch an attestation from. See docs/AUTONOMY.md.
"""

from __future__ import annotations

import time

# ATF's numbering, kept so a level reads the same in both documents.
LEVELS: tuple[str, ...] = ("intern", "junior", "senior", "principal")
INTERN, JUNIOR, SENIOR, PRINCIPAL = 1, 2, 3, 4
_RANK = {name: i + 1 for i, name in enumerate(LEVELS)}

# What each rung means, in the words her portal shows her. ATF's own column
# headings ("Observe + Report" and so on), restated as what her authority
# will do about a request from an agent at that rung under the profile below.
MEANS = {
    INTERN: "observes only — anything that would change something is refused",
    JUNIOR: "may act, but every act waits for your approval",
    SENIOR: "acts without asking and you are told; what cannot be undone "
            "still waits for you",
    PRINCIPAL: "acts without asking within what your terms allow, including "
               "what cannot be undone",
}

# ATF's illustrative minimum time at a level before promotion is considered,
# and its acceptance threshold for leaving Junior. Reported, never enforced:
# ATF calls them illustrative, and the decision they inform is hers.
MIN_DAYS_AT = {INTERN: 14, JUNIOR: 28, SENIOR: 56}
ACCEPTANCE_TO_LEAVE = {JUNIOR: 0.95}

# How much of a connection's promotion history is kept on the record itself.
# The ledger holds all of it; this is what the portal shows at a glance.
HISTORY_KEPT = 20


def normalise(value) -> int | None:
    """A level as its rank, from a name or a number, or None.

    An unrecognised value is no level rather than an error, for the reason
    `uma4a_consequence.normalise` gives: it may arrive from another party's
    published document, and an operator that invents a fifth rung should lose
    the benefit of declaring one, not take this server down.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if INTERN <= value <= PRINCIPAL else None
    if isinstance(value, str):
        text = value.strip().lower()
        if text.isdigit():
            return normalise(int(text))
        return _RANK.get(text)
    return None


def name(rank: int | None) -> str | None:
    return LEVELS[rank - 1] if rank in (INTERN, JUNIOR, SENIOR, PRINCIPAL) else None


# --- the owner's ladder ------------------------------------------------------


def owner_level(conn: dict | None) -> int:
    """Where this agent stands with her. An intern unless she said otherwise.

    An inactive connection is an intern whatever it once was. Revocation is
    the strongest demotion there is, and an agent she readmits starts a new
    relationship — the record written on readmission carries no level, so this
    reading is belt and braces rather than the mechanism.
    """
    if not conn or conn.get("status") != "active":
        return INTERN
    return normalise((conn.get("autonomy") or {}).get("level")) or INTERN


def change(conn: dict | None, to, by: dict, when: str,
           note: str | None = None) -> dict:
    """The connection's next autonomy record, or ValueError saying why not.

    `by` is who is changing it, in the shape `decide_pending` writes:
    ``{"kind": "owner", "owner": …}`` for her own tap, anything else for
    someone acting for her. Three rules:

    * **only she raises it.** A promotion by anyone else would be a decision
      of theirs relaxing her rules for every request afterwards — the exact
      thing the multiparty draft forbids an administrator's approval to do;
    * **one rung at a time.** ATF's gates are per rung, and the time an agent
      spends at each is the only evidence of behaviour at that rung she will
      ever have. Skipping one discards it;
    * **lowering needs no particular author**, to any rung. A restriction
      never needs an argument. (No party acting for her is given an endpoint
      for it here — see the module docstring — but the rule does not depend
      on that.)

    Pure: the caller writes the result, with the expected current level, so a
    stale view cannot overwrite a change it never saw.
    """
    if not conn or conn.get("status") != "active":
        raise ValueError("only an agent you are connected to has a level with "
                         "you — one you have revoked starts again as an intern")
    target = normalise(to)
    if target is None:
        raise ValueError(f"a level is one of {', '.join(LEVELS)}, not {to!r}")
    current = owner_level(conn)
    if target == current:
        raise ValueError(f"this agent is already {name(current)} with you")
    if target > current:
        if by.get("kind") != "owner":
            raise ValueError(
                "only the owner may promote an agent. Someone acting for her "
                "may demote one — a restriction needs no argument — but a "
                "promotion relaxes her rules, and only her own decisions may "
                "do that")
        if target != current + 1:
            raise ValueError(
                f"promotion is one rung at a time: {name(current)} to "
                f"{name(current + 1)}. Time at each rung is the only evidence "
                f"of how an agent behaves there")
    record = dict(conn.get("autonomy") or {})
    history = list(record.get("history") or [])
    history.append({"from": name(current), "to": name(target), "by": by,
                    "at": when, **({"note": note} if note else {})})
    return {"level": name(target), "since": when, "by": by,
            "history": history[-HISTORY_KEPT:]}


def _parse_ts(stamp: str | None) -> float | None:
    if not stamp:
        return None
    try:
        import calendar
        return float(calendar.timegm(time.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")))
    except (TypeError, ValueError):
        return None


def eligibility(conn: dict | None, ledger: list[dict],
                now: float | None = None) -> dict:
    """What her own record says about promoting this agent one rung.

    The two of ATF's five gates that are observable from her side, read from
    the ledger her decisions already wrote, and the three that are not, named
    as the operator's to show. **Advisory**: nothing here promotes anything,
    and the answer is shown beside the button rather than instead of it.
    """
    now = time.time() if now is None else now
    level = owner_level(conn)
    if level >= PRINCIPAL:
        return {"level": name(level), "next": None, "gates": []}
    record = (conn or {}).get("autonomy") or {}
    since = record.get("since") or (conn or {}).get("first_seen")
    since_ts = _parse_ts(since)

    at_level = [r for r in ledger
                if since is None or (r.get("ts") or "") >= since]
    approved = sum(1 for r in at_level if r.get("kind") == "approved")
    denied = sum(1 for r in at_level if r.get("kind") == "denied")
    refused = sum(1 for r in at_level if r.get("kind") == "refused")

    gates = []
    days = None if since_ts is None else (now - since_ts) / 86400
    need_days = MIN_DAYS_AT.get(level)
    gates.append({
        "gate": "performance: time at level",
        "met": None if days is None else days >= need_days,
        "detail": (f"{days:.1f} days as {name(level)}; ATF suggests "
                   f"{need_days} before {name(level + 1)}"
                   if days is not None else "no record of when this level began"),
    })
    if (threshold := ACCEPTANCE_TO_LEAVE.get(level)) is not None:
        asked = approved + denied
        rate = approved / asked if asked else None
        gates.append({
            "gate": "performance: your acceptance of what it asked",
            "met": None if rate is None else rate >= threshold,
            "detail": (f"you approved {approved} of {asked} "
                       f"({rate:.0%}); ATF suggests above {threshold:.0%}"
                       if asked else "it has asked you nothing at this level yet"),
        })
    gates.append({
        "gate": "incident record: refused by your policy",
        "met": refused == 0,
        "detail": (f"{refused} request(s) refused since it became "
                   f"{name(level)}" if refused else
                   f"nothing refused since it became {name(level)}"),
    })
    for gate in ("security validation", "business value"):
        gates.append({"gate": gate, "met": None,
                      "detail": "evidence about the operator's programme, not "
                                "about this agent with you — the operator's to "
                                "show"})
    gates.append({"gate": "governance sign-off", "met": None,
                  "detail": "yours: promoting it is the sign-off"})
    return {"level": name(level), "next": name(level + 1), "gates": gates}


# --- the operator's ladder ---------------------------------------------------

# Where an operator says it in its Client ID Metadata Document. One member,
# shaped after ATF's own conformance statement so an operator that has
# written one can publish it here unchanged:
#
#   "atf": {"version": "0.9.0", "maturity_level": "senior",
#           "conformance": "compatible",
#           "statement_uri": "https://operator.example/atf"}
CIMD_MEMBER = "atf"
CONFORMANCE = ("compatible", "certified")


def operator_declaration(identity: dict) -> dict:
    """What the agent's operator says about where it stands on its own ladder.

    Read only from a metadata document her authority resolved and found to
    claim its own URL — never from the agent's own request. An unresolved
    document declares nothing. `published_key` records whether that operator
    also published this agent's key, which is what lets her dialog say *who*
    made the declaration: an operator that vouched for this agent, or a
    document any agent could have pointed at.

    `level` is None when nothing was declared, and the conditions that read
    it treat that as unknown rather than as low: an operator that has never
    heard of ATF is not saying its agent is an intern.
    """
    meta = identity.get("client_metadata") or {}
    out = {"level": None, "conformance": None, "version": None,
           "statement_uri": None,
           "published_key": bool(identity.get("operator_attested"))}
    if not meta.get("verified"):
        return out
    atf = meta.get(CIMD_MEMBER)
    if not isinstance(atf, dict):
        return out
    level = normalise(atf.get("maturity_level"))
    out["level"] = name(level)
    if (conf := str(atf.get("conformance") or "").strip().lower()) in CONFORMANCE:
        out["conformance"] = conf
    if isinstance(atf.get("version"), str):
        out["version"] = atf["version"][:32]
    uri = atf.get("statement_uri")
    if isinstance(uri, str) and uri.startswith("https://"):
        out["statement_uri"] = uri[:512]
    return out


def describe(owner_rank: int, declared: dict) -> list[str]:
    """Two sentences for her dialog: where it stands with her, and where its
    operator says it stands. Never one number."""
    out = [f"with you: {name(owner_rank)} — {MEANS[owner_rank]}"]
    if declared.get("level") is None:
        out.append("its operator declares no ATF maturity level")
    else:
        who = ("an operator that published this agent's key"
               if declared.get("published_key")
               else "a metadata document it named (self-asserted)")
        extra = ""
        if declared.get("conformance") == "certified":
            extra = (" — it claims ATF Certified; nobody this authority can "
                     "ask has confirmed that")
        out.append(f"its operator says: {declared['level']}, per {who}{extra}")
    return out


# --- the profile -------------------------------------------------------------
#
# ATF's levels, written as an owner's rules. Nothing here is new machinery:
# every condition already exists, and the profile is the composition written
# out where she can read it. Applied to a tier, it means:
#
#   with her       the request is ...
#   ---------      ------------------------------------------------------
#   intern         refused if it would change anything; reads as the tier says
#   junior         asked about if it would change anything
#   senior         granted without asking, except what cannot be undone
#   principal      granted without asking
#
# and then the operator's ladder, read the same way, can only make each line
# stricter. The tier's own `ask_me` stays the baseline for reads, so a tier
# that asks before anything is read keeps asking, whoever is reading.
#
# What "changes anything" means comes from the resource, not the agent: the
# consequence class the resource server declares for the operation
# (`uma4a_consequence`). A read is `reversible`; an act is `compensatable` or
# worse. An operation nobody has described is put to her when an intern asks
# for it, rather than refused, because an undescribed read is common and
# refusing it would make the profile unusable on most of the web.

EARNED_AUTONOMY: list[dict] = [
    # Her ladder. The only relaxation, and the only condition in it that may
    # relax anything is her own decision about this agent.
    {"when": ["standing.autonomy_at_least:senior"], "then": "auto"},
    {"when": ["standing.autonomy_below:principal",
              "request.consequence_at_or_above:irreversible"], "then": "ask"},
    {"when": ["standing.autonomy_below:senior",
              "request.consequence_at_or_above:compensatable"], "then": "ask"},
    {"when": ["standing.autonomy_below:junior",
              "request.consequence_at_or_above:compensatable"], "then": "refuse"},
    {"when": ["standing.autonomy_below:junior",
              "request.consequence_unknown"], "then": "ask"},
    # The operator's ladder. Tightening only, and silent for an operator that
    # declared nothing.
    {"when": ["operator.autonomy_below:junior",
              "request.consequence_at_or_above:compensatable"], "then": "refuse"},
    {"when": ["operator.autonomy_below:senior",
              "request.consequence_at_or_above:compensatable"], "then": "ask"},
    {"when": ["operator.autonomy_below:principal",
              "request.consequence_at_or_above:irreversible"], "then": "ask"},
]

PRESETS = [{
    "id": "earned-autonomy",
    "label": "Earned autonomy (CSA Agentic Trust Framework)",
    "summary": ("Agents start as interns with you and you promote them one "
                "rung at a time. Whichever stands lower — the level you gave "
                "it or the level its own operator declares — decides."),
    "levels": {name(r): MEANS[r] for r in (INTERN, JUNIOR, SENIOR, PRINCIPAL)},
    "rules": EARNED_AUTONOMY,
}]


def with_preset(rules: list[dict], preset: list[dict]) -> list[dict]:
    """Her rules with a preset's added, once. Hers come first and none are
    removed: a preset is something she adds to what she wrote, not a
    replacement for it."""
    out = [dict(r) for r in rules or []]
    seen = [(r.get("then"), tuple(r.get("when") or [])) for r in out]
    for rule in preset:
        key = (rule["then"], tuple(rule["when"]))
        if key not in seen:
            out.append({"when": list(rule["when"]), "then": rule["then"]})
            seen.append(key)
    return out
