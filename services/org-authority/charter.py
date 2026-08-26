"""The charter — an organization's policy document, and what may be said in it.

Two layers of policy meet in this system and they are not the same kind of
thing, which is why they are not written in the same language.

Alice's tiers are a small legible document because *she* is the one reading
and writing them, and a person editing her own sharing rules should never
need a debugger. An organization is the other case entirely: the operator of
the service **is** the party with authority to decide, there is a compliance
team, and the policy outlives whoever wrote it. That is exactly the workload
policy engines were built for, so the org layer gets one — Rego, evaluated by
OPA, in `org.rego` beside this file.

What stays here is the part an engine cannot do for you: the **envelope**.
A ceiling on what a member's terms may say is an algebra over two documents,
not a judgement about one request, so it has to be comparable at the moment
a member edits her policy — long before any agent has asked for anything.
An engine answers questions about requests; this answers a question about
policy. See `services/uma-as/org.py`, which is the other half.

    charter
      claims        which resources fall under the organization at all
      envelope      the ceiling on a member's terms      -> clamped, in Python
      conditions    what a request must look like        -> decided, in Rego
      break_glass   when the organization may reach past a member's refusal
      rego          the admin's own rules, which may only tighten

`conditions` is a declarative front end onto the shipped Rego module: an
admin who never opens the code editor still gets an engine-evaluated policy,
and one who does can express anything Rego can — but only ever `deny` and
`ask`, never a grant. That asymmetry is the same one Alice's rules live
under, one layer up.
"""

import copy
import re

from uma4a_org import claims_match as _claims_match

# One month. Not a policy — a bound on what any policy may say, so a typo in
# a units field cannot mint a year-long grant across every member at once.
MAX_EXPIRES_CEILING = 30 * 86400
# Break-glass is an exception, and an exception that lasts a working day is a
# standing permission with a dramatic name.
BREAK_GLASS_CEILING = 3600

ASSURANCE_FLOORS = ("min_binding", "min_provenance", "min_accountability")

# What a member may let an agent do with the organization's resources. The
# middle value is the one that does not exist anywhere else, and it is the
# reason this profile has anything to say about organizations at all: it
# distinguishes an agent the member operates from an agent somebody else
# operates, which is a distinction about *parties* rather than permissions.
DELEGATION = {"none", "first-party-only", "any-agent"}


def _covered(pattern: str, claims) -> bool:
    """Whether a grant pattern is inside what the charter claims.

    Deliberately not a general "is pattern A subsumed by pattern B". That is a
    decision procedure, and a validator is the wrong place to hide one — the
    failure mode is a charter that hands out access to a resource the
    validator's cleverness talked itself into. Three syntactic cases and
    nothing else:

      * the same pattern is claimed;
      * the pattern names one concrete resource, and a claim matches it;
      * the pattern is `X/*`, and `X/*` is itself claimed.

    Anything an administrator wants that these cannot express, he expresses by
    claiming it explicitly. That is a worse day for him and a better one for
    everybody whose resources are not his.
    """
    claims = list(claims or [])
    if pattern in claims:
        return True
    if "*" not in pattern:
        return claims_match(pattern, claims)
    return pattern.endswith("/*") and f"{pattern.rsplit('/', 1)[0]}/*" in claims


# The charter an organization starts with, and the one the lab demonstrates.
#
# It is deliberately not empty. A governance layer that ships neutral teaches
# nothing about what a governance layer is *for*, and an admin staring at a
# blank Rego buffer will write nothing at all. These are the four things a
# firm actually cares about when someone else's agent asks for its data:
# how long access lasts, what may never be done with it, what a person has to
# sign off on, and who is standing behind the agent.
DEFAULT_CHARTER: dict = {
    "name": "Agent access policy",
    # The organization's own resources — the book its people work on. Not a
    # pattern over everyone's accounts, and the distinction is the whole
    # model: these belong to the organization and are *shared with* members,
    # which is why it may set policy over them.
    #
    # A member's own accounts match nothing here and are untouched by every
    # line of this charter. She is not handing over her portfolio by joining;
    # she is being given access to the firm's.
    "claims": [
        "northwind-vault/*",
    ],
    # What joining is *for*.
    #
    # A governance layer that only ever narrowed would be a strange thing to
    # volunteer for. Membership is an exchange: the organization gets policy
    # over its own data, and the member gets access to it — under a role,
    # which is the ordinary way an organization says who may see what.
    #
    # `delegation` is the field that matters most, and it is the one nobody
    # else has anywhere to put:
    #
    #   none              she may reach the firm's book herself; no agent may
    #   first-party-only  an agent she operates may; somebody else's may not
    #   any-agent         any agent may, subject to her terms and this charter
    #
    # That is the sentence a firm actually wants to write and cannot write in
    # any authorization system built around one party — because it is not
    # about *what* is accessed, it is about *whose agent* is doing the
    # accessing on behalf of *which* person.
    "roles": {
        "analyst": {
            "name": "Analyst",
            "grants": [
                "northwind-vault/get_positions",
                "northwind-vault/get_transactions",
            ],
            "delegation": "first-party-only",
        },
        "trader": {
            "name": "Trader",
            "grants": ["northwind-vault/*"],
            "delegation": "any-agent",
        },
    },
    # What a member gets on joining, before an administrator has decided
    # anything about her. The read-only role, because the alternative is that
    # enrolment either does nothing at all or hands out trade authority.
    "default_role": "analyst",
    # The ceiling. Every field here can only ever narrow a member's terms.
    "envelope": {
        # Firm data may be held for an hour, whatever a member's own terms say.
        "max_expires_in": 3600,
        # Absent means unrestricted. `[]` means nothing may be granted, which
        # is a legitimate and very loud thing to write.
        "allowed_scopes": ["positions:read", "transactions:read", "trades:execute"],
        # Added to every member's terms whether she wrote them or not. These
        # are undertakings rather than mechanisms — see ENFORCED_PROHIBITIONS
        # in the AS — and the charter is where a firm states them once instead
        # of hoping each member remembers.
        "require_prohibited": [
            "model-training",
            "sharing-outside-engagement-team",
            "retention-after-engagement",
        ],
        # Resources where a member's "grant without asking" does not apply.
        # She may still ask on more than this; she may not ask on less.
        "always_ask": ["northwind-vault/execute_trade"],
    },
    # Evaluated per request, by the engine, against the facts of that request.
    "conditions": {
        "min_binding": 1,
        "min_provenance": 0,
        # The one level an agent cannot reach on its own say-so: the operator
        # it names has to have published this agent's key.
        "min_accountability": 2,
        "require_reason": True,
        "require_mission": False,
    },
    "break_glass": {
        "enabled": True,
        # Never the whole claim set by default. Reading the firm's book in an
        # emergency is a different act from trading it.
        "resources": ["northwind-vault/get_positions",
                      "northwind-vault/get_transactions"],
        "max_expires_in": 900,
        "require_reason": True,
        # Operator origins that may invoke it. Empty means the admin console
        # only — which is the safe default, because it means a human at the
        # organization has to be the one who does this.
        "invokers": [],
    },
    # The escape hatch, and the reason OPA is here rather than another
    # hand-rolled evaluator. Ships empty: a firm that needs nothing beyond the
    # conditions above should not have to read Rego to understand its own
    # policy.
    "rego": "",
}

CUSTOM_PACKAGE = "package u4a.custom"


# The pattern language lives in `lib/uma4a_org.py`: an organization's
# charter is evaluated by three services and one Rego module, and a matcher
# per copy is a matcher per interpretation.
claims_match = _claims_match

def _ints(mapping: dict, fields, *, low=0, high=None, label="") -> None:
    for field in fields:
        if field not in mapping:
            continue
        value = mapping[field]
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{label}{field} must be a whole number")
        if value < low or (high is not None and value > high):
            raise ValueError(
                f"{label}{field} must be between {low} and {high}, got {value}")


def _strings(mapping: dict, fields, *, label="") -> None:
    for field in fields:
        value = mapping.get(field)
        if value is None:
            continue
        if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
            raise ValueError(f"{label}{field} must be a list of strings")


def validate(charter: dict) -> dict:
    """Reject a charter before it is ever a version, or return it normalised.

    Every check here has the same shape as `policy.validate_rules` on the
    member side and exists for the same reason: an edit that is going to fail
    should fail in front of the person who made it, not inside somebody
    else's grant loop an hour later. A charter reaches thousands of requests
    across every member at once, so the argument is stronger, not weaker.
    """
    if not isinstance(charter, dict):
        raise ValueError("a charter is a JSON object")
    out = copy.deepcopy(charter)

    name = (out.get("name") or "").strip()
    if not name:
        raise ValueError("the charter needs a name — members are shown it")
    out["name"] = name

    claims = out.get("claims")
    if not isinstance(claims, list) or not claims or any(
            not isinstance(c, str) or not c.strip() for c in claims):
        raise ValueError(
            "claims must be a non-empty list of resource patterns — a charter "
            "that claims nothing governs nothing, and a member joining it "
            "would be agreeing to a document with no subject")
    out["claims"] = [c.strip() for c in claims]
    # A charter says what the organization owns. It may not say it with a
    # wildcard in the first segment.
    #
    # `*/get_positions` is a well-formed pattern and it reads as "this kind of
    # resource, wherever it lives" — which is precisely the reach an
    # organization must not have. It matches `alice-vault/get_positions`, so a
    # firm would be governing a member's own brokerage account; and it matches
    # `meridian-joint/get_positions`, so it would be governing an account she
    # holds with somebody who never enrolled here and cannot leave.
    #
    # Both of those were reachable, and demonstrated, before this check
    # existed. A namespace is how "the organization's own resources" is said
    # in this system, so a claim has to name one.
    for pattern in out["claims"]:
        head = pattern.split("/", 1)[0]
        if "*" in head or "?" in head or not head:
            raise ValueError(
                f"claims must name the organization's own namespace — "
                f"{pattern!r} has a wildcard where the namespace goes, and "
                f"would reach resources belonging to members and to people "
                f"who have never heard of this organization. Claim "
                f"`{head or '<namespace>'}…` as a concrete namespace instead.")

    envelope = out.setdefault("envelope", {})
    if not isinstance(envelope, dict):
        raise ValueError("envelope must be an object")
    if not envelope.get("max_expires_in"):
        raise ValueError("envelope.max_expires_in is required — the ceiling on "
                         "how long any member's grant may last")
    _ints(envelope, ["max_expires_in"], low=1, high=MAX_EXPIRES_CEILING,
          label="envelope.")
    _strings(envelope, ["allowed_scopes", "require_prohibited", "always_ask"],
             label="envelope.")

    roles = out.setdefault("roles", {})
    if not isinstance(roles, dict):
        raise ValueError("roles must be an object of role id -> definition")
    for role_id, role in roles.items():
        if not isinstance(role, dict):
            raise ValueError(f"role {role_id!r} must be an object")
        _strings(role, ["grants"], label=f"roles.{role_id}.")
        for pattern in role.get("grants") or []:
            # A role granting something the charter does not claim would be
            # the organization handing out access to resources it never said
            # were its own — and, worse, to resources that may be somebody's
            # personal accounts.
            if not _covered(pattern, out["claims"]):
                raise ValueError(
                    f"role {role_id!r} grants {pattern!r}, which this charter "
                    f"does not claim. A role may only hand out access to the "
                    f"organization's own resources.")
        delegation = role.setdefault("delegation", "none")
        if delegation not in DELEGATION:
            raise ValueError(
                f"roles.{role_id}.delegation must be one of {sorted(DELEGATION)}, "
                f"got {delegation!r}")
        role.setdefault("name", role_id)
    default_role = out.get("default_role")
    if default_role and default_role not in roles:
        raise ValueError(f"default_role {default_role!r} is not a role here")

    conditions = out.setdefault("conditions", {})
    if not isinstance(conditions, dict):
        raise ValueError("conditions must be an object")
    _ints(conditions, ASSURANCE_FLOORS, low=0, high=3, label="conditions.")
    for flag in ("require_reason", "require_mission"):
        if flag in conditions and not isinstance(conditions[flag], bool):
            raise ValueError(f"conditions.{flag} is true or false")

    glass = out.setdefault("break_glass", {"enabled": False})
    if not isinstance(glass, dict):
        raise ValueError("break_glass must be an object")
    glass["enabled"] = bool(glass.get("enabled"))
    _strings(glass, ["resources", "invokers"], label="break_glass.")
    if glass["enabled"]:
        if not glass.get("resources"):
            raise ValueError(
                "break_glass.resources is required when break-glass is enabled "
                "— an override with no stated subject is not an exception, it "
                "is a second way in")
        _ints(glass, ["max_expires_in"], low=1, high=BREAK_GLASS_CEILING,
              label="break_glass.")
        glass.setdefault("max_expires_in", 900)
        # Break-glass may reach past a member's refusal. It may not reach past
        # the organization's own claim: the charter is what a member agreed
        # to, and an override outside it was never disclosed to her.
        for pattern in glass["resources"]:
            if not _covered(pattern, out["claims"]):
                raise ValueError(
                    f"break_glass.resources names {pattern!r}, which the "
                    "charter does not claim — an override may only reach what "
                    "members were told the organization governs")

    idp = out.get("identity_provider")
    if idp is not None:
        if not isinstance(idp, dict):
            raise ValueError("identity_provider must be an object")
        issuer = (idp.get("issuer") or "").strip()
        enabled = bool(idp.get("enabled", True))
        if not enabled and not issuer:
            # Switched off and nothing typed in. That is the same charter as
            # one that never mentioned a provider, and storing an empty shell
            # would make every reader test two things instead of one.
            out.pop("identity_provider", None)
            idp = None
        # The issuer is a trust root: a member's authority will accept
        # assertions about who her agents act for on the strength of this one
        # string. Plain http would put that decision on the network.
        elif not issuer.startswith("https://"):
            raise ValueError(
                "identity_provider.issuer must be an https issuer — a "
                "member's authority trusts assertions signed by it")
    if idp is not None:
        assertion = (idp.get("assertion") or "id-jag").strip()
        if assertion != "id-jag":
            raise ValueError(
                "identity_provider.assertion: this profile understands "
                "`id-jag` and nothing else")
        directory = (idp.get("directory") or "").strip()
        if directory and not directory.startswith("https://"):
            raise ValueError(
                "identity_provider.directory must be an https issuer")
        # Who the provider's identifiers belong to here. A real tenant asserts
        # a `sub` that means something only inside it, so somebody has to say
        # which member that is — and the organization is the party that knows,
        # since they are its people and it enrolled them.
        subject_map = idp.get("subject_map") or {}
        if not isinstance(subject_map, dict) or not all(
                isinstance(k, str) and isinstance(v, str)
                for k, v in subject_map.items()):
            raise ValueError(
                "identity_provider.subject_map maps what the provider asserts "
                "to the member it means here — strings to strings")
        out["identity_provider"] = {
            # Configured but switched off is a real state, and a different one
            # from never configured: an administrator turning federation off
            # should not lose the provider she typed in.
            "enabled": bool(idp.get("enabled", True)),
            "issuer": issuer,
            "assertion": assertion,
            # Where employees actually sign in. Discovered from the provider's
            # own metadata when blank, which is the normal case — an
            # administrator should not have to type the same company's two
            # endpoints and keep them agreeing.
            "directory": directory,
            "subject_map": subject_map,
            # Whether the provider vouching for her is enough to enrol,
            # instead of an enrolment code.
            "enrol": bool(idp.get("enrol", True)),
        }

    rego = out.get("rego") or ""
    if not isinstance(rego, str):
        raise ValueError("rego must be a string — the module text")
    rego = rego.strip()
    if rego and not rego.startswith(CUSTOM_PACKAGE):
        raise ValueError(
            f"custom rules must begin with `{CUSTOM_PACKAGE}` — the shipped "
            "module reads `deny` and `ask` from that package, and a module "
            "declaring any other package would load cleanly and never be "
            "consulted. It is a sibling of `u4a.org` rather than a child of "
            "it so that the shipped rules can read it without the engine "
            "seeing a package that depends on itself.")
    # A rule this package cannot express, refused rather than ignored.
    #
    # The shipped module reads exactly two things out of `u4a.custom`: `deny`
    # and `ask`. An administrator who writes `allow` has written something
    # that will load cleanly, evaluate correctly, and change nothing — and
    # will reasonably believe he has granted access. Saying so at the moment
    # he saves it is the difference between a limitation and a trap.
    if re.search(r"^\s*(default\s+)?allow\b", rego, re.M):
        raise ValueError(
            "custom rules can contribute `deny` and `ask` and nothing else. "
            "An `allow` here would load, evaluate, and be ignored: this layer "
            "sits above the member's policy and can only ever make a request "
            "harder. What she permits is hers to decide.")
    out["rego"] = rego
    return out


def powers(charter: dict, role: dict | None = None) -> dict:
    """What joining gives this organization the right to do, what it gives
    *her*, and what it still may not touch.

    Kept apart from `summarize`, which describes the ceiling. This describes
    the **relationship** — and it is the more important of the two to put in
    front of somebody, because a ceiling only narrows what she was going to
    do anyway, while these are things another party may do to her agents.

    The boundary in `cannot` is the load-bearing half and every line of it is
    enforced somewhere you can point at. The organization shares resources
    with her; it does not acquire hers. An administrator sees the agents that
    touch the firm's book and cannot see the ones that touch her brokerage
    account — not "is discouraged from", cannot: her authority filters by
    what the charter claims before anything is returned.

    Generated from the charter, so that if one of those endpoints changed its
    scope this list would have to change with it.
    """
    glass = charter.get("break_glass") or {}
    envelope = charter.get("envelope") or {}
    claims = ", ".join(charter.get("claims") or [])
    role = role or (charter.get("roles") or {}).get(charter.get("default_role")) or {}
    delegation = role.get("delegation", "none")
    gets = [
        {"what": f"Access to {', '.join(role.get('grants') or []) or 'nothing yet'}",
         "detail": f"As {role.get('name') or 'a member'}. These are the "
                   f"organization's resources, shared with you — they appear "
                   f"in your own authorization server, and you write the terms "
                   f"agents must accept to touch them."},
        {"what": {
            "none": "No agent may act on them — only you",
            "first-party-only": "Agents you operate yourself may act on them",
            "any-agent": "Any agent may act on them, if your terms allow it",
         }[delegation],
         "detail": {
            "none": "You can reach the firm's book yourself. Nothing you "
                    "delegate to an agent reaches it.",
            "first-party-only": "An agent whose operator you claimed, and "
                                "whose key that operator published, may be "
                                "granted access under your terms. Somebody "
                                "else's agent may not — however much you "
                                "trust it, and whatever your own terms say.",
            "any-agent": "Including agents other people operate. Your terms "
                         "still decide what they may do, and this charter "
                         "still caps it.",
         }[delegation]},
    ]
    can = [
        {"what": f"Set a ceiling on the terms you write over {claims}",
         "detail": f"No grant over them may last longer than "
                   f"{_human_duration(envelope.get('max_expires_in'))}, and "
                   f"prohibitions this charter requires are added to your "
                   f"terms whether you wrote them or not."},
        {"what": "See the agents that touch its resources, and shut them out",
         "detail": "An administrator can stop an agent reaching the firm's "
                   "book without asking you. It does not end your "
                   "relationship with that agent: whatever it does with your "
                   "own accounts carries on untouched."},
        {"what": "See requests waiting on you about its resources, and answer them",
         "detail": "Approve or deny, in your place. Only requests about the "
                   "organization's resources — it cannot see, or answer, a "
                   "request about your own accounts."},
        {"what": "Refuse a request your own terms would have allowed",
         "detail": "Every request over its resources is judged by this "
                   "organization's policy as well as yours. Either of you can "
                   "stop it; neither can widen the other."},
        {"what": "Change what you may reach, or end your membership",
         "detail": "Your role here is theirs to set. Ending it takes back the "
                   "access it gave you; what their ceiling narrowed in your "
                   "own terms stays narrowed."},
    ]
    if glass.get("enabled"):
        can.append({
            "what": "Break glass — reach its own resources without your approval",
            "detail": f"On {', '.join(glass.get('resources') or [])}, for up "
                      f"to {_human_duration(glass.get('max_expires_in'))} at "
                      f"a time, without going through your authorization "
                      f"server at all. You cannot stop it, and it cannot be "
                      f"done quietly: you are told the moment it is opened, "
                      f"before any data moves, and every use is written into "
                      f"your own record."})
    cannot = [
        {"what": "Touch anything of yours",
         "detail": f"This charter reaches {claims} and nothing else. Your own "
                   f"accounts, the terms you write over them, and the agents "
                   f"that use them are outside it entirely — an administrator "
                   f"cannot see them, cannot answer for them, and cannot "
                   f"revoke them."},
        {"what": "Read your policy",
         "detail": "Not even for its own resources. What crosses to this "
                   "organization is that its ceiling was applied and which of "
                   "its own fields narrowed you — never what you wrote."},
        {"what": "Make your terms wider",
         "detail": "Nothing in this charter can lengthen an expiry, add a "
                   "scope or remove a prohibition. It can only narrow."},
        {"what": "Act as you",
         "detail": "Everything an administrator does is written into your "
                   "record under their name, not yours, and you are told as "
                   "it happens."},
    ]
    if not glass.get("enabled"):
        cannot.insert(1, {
            "what": "Reach its resources without going through your policy",
            "detail": "This charter has no break-glass clause. An agent "
                      "acting for this organization negotiates with your "
                      "authorization server like anyone else's."})
    return {"gets": gets, "can": can, "cannot": cannot}


def envelope_of(charter: dict, role: dict | None = None) -> dict:
    """What leaves the organization and reaches a member's authority.

    Not the whole charter, and the line is worth stating. A member's
    authorization server needs the ceiling, because it has to clamp her terms
    to it and it has to be able to show her what it did. It does not need the
    organization's conditions or its Rego, because those are evaluated at the
    organization's own decision point — the same party boundary that keeps
    the firm from reading Alice's policy, pointed the other way.

    What crosses instead is `summary`: the organization's own account of what
    it enforces, in sentences, so a member is told what she is agreeing to
    without the policy text being exported to her.
    """
    envelope = charter.get("envelope") or {}
    glass = charter.get("break_glass") or {}
    return {
        # The charter's own title, under a key of its own. It used to be
        # `name`, which quietly shadowed the *organization's* name wherever
        # an envelope was spread over one — so a member's portal, and the
        # terms document her agents read, both announced "Agent access
        # policy" as the party above her. Two different things called the
        # same thing is how that happens.
        "charter_name": charter["name"],
        "claims": list(charter.get("claims") or []),
        # Which provider's assertions a member's authority should accept
        # about who her agents act for. It crosses because she cannot check a
        # signature against an issuer she was never told about — and because
        # she should be able to see, in her own portal, whose word about her
        # colleagues her server is taking.
        # Only when it is on. A member's authority should not be asking for
        # assertions on the strength of a provider an administrator disabled.
        "identity_provider": (charter.get("identity_provider")
                              if (charter.get("identity_provider") or {}).get("enabled")
                              else None),
        "max_expires_in": envelope.get("max_expires_in"),
        "allowed_scopes": envelope.get("allowed_scopes"),
        "require_prohibited": list(envelope.get("require_prohibited") or []),
        "always_ask": list(envelope.get("always_ask") or []),
        "break_glass": {
            "enabled": bool(glass.get("enabled")),
            "resources": list(glass.get("resources") or []),
            "max_expires_in": glass.get("max_expires_in"),
        },
        "summary": summarize(charter, role),
        # What joining lets this organization *do*, what it gives her, and
        # what it may never touch. She has to agree to this, not merely be
        # shown it.
        "powers": powers(charter, role),
    }


def _human_duration(seconds) -> str:
    if not seconds:
        return "—"
    for unit, size in (("day", 86400), ("hour", 3600), ("minute", 60)):
        if seconds >= size and seconds % size == 0:
            n = seconds // size
            return f"{n} {unit}{'' if n == 1 else 's'}"
    return f"{seconds} seconds"


def summarize(charter: dict, role: dict | None = None) -> list[str]:
    """The charter as sentences a member reads before she joins.

    Generated from the document rather than typed beside it, for the obvious
    reason: a summary an admin maintains by hand is one edit away from
    describing a policy that is no longer in force.

    It leads with what she gets, because that is what she is being offered.
    A governance layer described only by its constraints reads as a demand,
    and this is an exchange — the organization shares its resources with her
    and sets policy over them.
    """
    envelope = charter.get("envelope") or {}
    conditions = charter.get("conditions") or {}
    glass = charter.get("break_glass") or {}
    role = role or (charter.get("roles") or {}).get(
        charter.get("default_role")) or {}
    delegation = role.get("delegation", "none")
    out = [
        f"Shares {', '.join(role.get('grants') or []) or 'nothing'} with you"
        + (f", as {role.get('name')}." if role.get("name") else "."),
        {"none": "No agent may act on them on your behalf — only you.",
         "first-party-only": "Only agents you operate yourself may act on "
                             "them. Somebody else's agent may not, whatever "
                             "your own terms say.",
         "any-agent": "Any agent may act on them, if your own terms allow "
                      "it.",
         }[delegation],
        f"Governs {', '.join(charter.get('claims') or [])} — your own "
        f"accounts are outside this entirely.",
        f"No grant over its resources may last longer than "
        f"{_human_duration(envelope.get('max_expires_in'))}, whatever your own "
        f"terms say.",
    ]
    scopes = envelope.get("allowed_scopes")
    if scopes is not None:
        out.append(
            f"Only these may ever be granted: {', '.join(scopes) or 'nothing'}."
            if scopes else
            "No access at all may be granted while this is in force.")
    if envelope.get("require_prohibited"):
        out.append("Your terms over its resources will always forbid: "
                   f"{', '.join(envelope['require_prohibited'])}.")
    if envelope.get("always_ask"):
        out.append("You will be asked every time for: "
                   f"{', '.join(envelope['always_ask'])} — even if your own "
                   "terms would have granted automatically.")
    floors = {
        "min_binding": "the request is bound to a key the authority verified",
        "min_provenance": "the agent's credential traces to an issuer",
        "min_accountability": "someone named is standing behind the agent",
    }
    for field, sentence in floors.items():
        if conditions.get(field):
            out.append(f"Requests are refused unless {sentence} "
                       f"(level {conditions[field]}).")
    if conditions.get("require_reason"):
        out.append("An agent that does not say what it wants the access for "
                   "is refused.")
    if conditions.get("require_mission"):
        out.append("An agent that cites no mandate for its errand is refused.")
    if charter.get("rego"):
        out.append("The organization applies operating rules of its own, "
                   "evaluated by its policy engine — things like a close "
                   "period or trading hours, which change without this "
                   "agreement changing. They can only make a request harder, "
                   "never easier, and whenever one of them stops you it is "
                   "named in your own record.")
    if glass.get("enabled"):
        out.append(
            "Break-glass: the organization can reach "
            f"{', '.join(glass.get('resources') or [])} for up to "
            f"{_human_duration(glass.get('max_expires_in'))} without your "
            "approval, and every time it does you are told immediately and it "
            "is written into your own record.")
    else:
        out.append("The organization cannot reach your resources without going "
                   "through your policy like anyone else.")
    return out
