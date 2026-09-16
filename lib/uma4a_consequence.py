"""What an operation leaves behind, as a declared fact.

An owner's policy can say "ask me about anything that cannot be undone" only
if something says which operations those are. Today that knowledge exists in
every deployment and is written down nowhere: this lab treats `execute_trade`
as irreversible by listing it in two hardcoded sets, and the reason it is in
those sets appears in no document any other party can read.

The vocabulary is Nat Sakimura's, from his agentic-AI governance work: an
action is reversible, compensatable, forward-recoverable, or irreversible.

Three rules make it safe to read, and they are the whole design:

**The resource declares it, not the agent.** The party that owns the
operation is the only one that knows whether it can be undone. It publishes
the class in the metadata it already signs, so a relayed copy stays
attributable to the resource rather than to whoever handed it over. A client
ID metadata document is display only for exactly the opposite reason
(`docs/PROTOCOL.md`, extension 11): a requesting party describing itself is
advertising. A resource describing its own tools is not — it is the party that
will have to perform the act.

**It may only tighten.** A declared class can raise what a request needs and
can never lower it, which is the same asymmetry assurance already has. So a
requesting side that declares its own class — an agent narrowing itself — can
bind itself to more and never to less.

**Absent is unknown, not benign, and not severe.** MCP's tool annotations
default to the pessimistic reading: an unannotated tool is assumed
destructive. That is right for a host deciding whether to show a confirmation
dialog and wrong here, where an undeclared operation would otherwise make
every existing deployment look irreversible on the day this shipped. An
undeclared operation is `None`: `at_or_above` never fires for it, and an owner
who wants to refuse what nobody will describe writes that rule herself.

The order is about **remedy, not severity**. It says how much of the world can
still be put back, not how bad it would be — a reversible action can still be
catastrophic while it stands. Nothing here adds the classes up or scores them,
for the reason `assurance.py` gives at more length: a composite is the
mechanism by which one axis quietly excuses another.
"""

from __future__ import annotations

# Ordered by how much remedy remains, most to least.
CLASSES: tuple[str, ...] = (
    # Undone completely, by the party that did it. An internal draft.
    "reversible",
    # Offset by a counter-action, which leaves a trace. A cancelled booking.
    "compensatable",
    # Not undone, but recovered by going on. A repaired workflow.
    "forward_recoverable",
    # Neither undone nor offset. A disclosure.
    "irreversible",
)

_RANK = {name: i for i, name in enumerate(CLASSES)}


def normalise(value) -> str | None:
    """A declared class, or None for anything this does not recognise.

    An unrecognised string is treated as no declaration rather than as an
    error: the class arrives from another party's published document, and a
    resource server that invents a fifth word should lose the benefit of the
    declaration, not take the authorization server down with it.
    """
    if not isinstance(value, str):
        return None
    return value if (value := value.strip().lower()) in _RANK else None


def rank(value) -> int | None:
    """Position in the order, or None when nothing was declared."""
    return _RANK.get(normalise(value) or "")


def at_or_above(actual, floor) -> bool:
    """Does `actual` leave at most as much remedy as `floor`?

    False when either is undeclared. An undeclared operation is not evidence
    of anything, and a rule written against a word this does not know would
    otherwise fire on everything.
    """
    a, f = rank(actual), rank(floor)
    return a is not None and f is not None and a >= f


def from_mcp_annotations(annotations) -> str | None:
    """The nearest class MCP's tool annotations can express.

    Read only from hints that are *explicitly present*. MCP's own defaults
    (`destructiveHint` true, `idempotentHint` false, `openWorldHint` true when
    absent) are a pessimistic posture for a host deciding whether to prompt;
    inheriting them here would turn "this server publishes no annotations at
    all" into "every one of its tools is irreversible", which is a claim
    nobody made.

    `reversibleHint` is proposed rather than shipped (SEP-1984). It is read
    where it appears because it is the one hint that means this directly, and
    it is not required for the rest of the mapping to work.
    """
    if not isinstance(annotations, dict):
        return None
    if isinstance(rev := annotations.get("reversibleHint"), bool):
        return "reversible" if rev else "irreversible"
    if annotations.get("readOnlyHint") is True:
        # Nothing changed, so there is nothing to put back.
        return "reversible"
    if annotations.get("destructiveHint") is True:
        return "irreversible"
    if annotations.get("destructiveHint") is False:
        # Additive rather than destructive: a created or appended thing can be
        # removed, which is a counter-action and not an undo.
        return "compensatable"
    return None


def single_use(consequence) -> bool:
    """Whether a tool of this class takes a grant bound to one operation.

    Irreversible is the case the operation binding exists for: authority over
    one act, spent by that act. The two facts were separate lists in every
    deployment that had them, and one fact stated twice is one fact that can
    disagree with itself.
    """
    return normalise(consequence) == "irreversible"


def surface_of(consequence: dict[str, str] | None, tool: str) -> str | None:
    """The class declared for one tool, normalised."""
    return normalise((consequence or {}).get(tool))
