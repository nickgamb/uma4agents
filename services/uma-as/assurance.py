"""Agent assurance, and why it is not one number.

Alice's tiers say what may be asked of *her resources*. This module is the
other axis: what her authority can establish about the *asking agent*, so her
policy can say "an agent like this must ask me" without ever naming an agent.

Naming it assurance rather than inventing a euphemism, because that is what it
is. But it is deliberately not an assurance *level*, and the reason is the
history of the term.

Why not a single ladder
-----------------------
Identity assurance spent a decade on one ordinal scale (LOA 1-4) before
NIST SP 800-63-3 pulled it apart into three independent axes — IAL for how
well a real-world identity was proofed, AAL for how strongly the credential is
presented, FAL for how the assertion travels. The decomposition happened
because the single scale forced unrelated evidence into one order, so a
deployment that needed strong credentials was pushed into identity proofing it
did not want, and a strong showing on one axis silently compensated for a weak
one on another.

An "Agent Assurance Level 1-4" would repeat that mistake, in a domain where
the axes are even less correlated: an agent can be trivially recognisable and
completely unaccountable, or backed by a named firm and holding a key nobody
has ever bound to anything. So this keeps them apart, and offers **no composite
score** — there is deliberately no function here that adds them up. A composite
is the mechanism by which strong binding excuses an unknown operator, which is
exactly the trade nobody would make if they were asked directly.

The axes
--------
``binding``         Can this request be tied to a key, and will that key be
                    recognisable next time? This is the one U4A never
                    compromises on: the four-beat grant requires an RFC 9421
                    signature and a proof-of-possession key, so it is never 0
                    in practice. It is on the list because a profile that
                    relaxed it should have to say so out loud.

``provenance``      Can her authority check where the agent's credential came
                    from? A bare key is self-minted (0). A key carried in an
                    ``aa-agent+jwt`` whose signature verified against its
                    issuer's published keys came from somewhere checkable (1).

``accountability``  Is there a named party standing behind it that she could
                    reach? No client_id at all (0). A Client ID Metadata
                    Document that resolved and claims the URL it was fetched
                    from (1). A document whose claims are attested by someone
                    other than its subject (2) — see below.

Each axis is ordinal *within itself*, because the levels genuinely nest: an
issuer-verified credential is everything a bare key is and more. Across axes
there is no order at all, and none is implied.

Standing is not assurance
-------------------------
Alice's own record of an agent — has she met it, how long ago, has she ever
revoked it — is kept separate and called ``standing``, in this module and in
her policy vocabulary. The distinction is the safety rule, made memorable:

    **assurance is what they can show; standing is what she has seen.**

Only standing may relax a requirement. Assurance may only tighten one. That
falls out of who produced the evidence rather than being a rule bolted on:
axes 1-3 are attested by the requesting side or by an issuer she did not
choose, and a signal the counterparty influences must never be able to widen
access. Standing was produced by her own authority, and is the only evidence
here she has any reason to believe unconditionally.

The consequence is worth stating plainly, because it is what makes the whole
thing safe to build: **a lie can only cost the liar friction.** Which is why
this can afford to read self-asserted metadata at all.

What this lab can actually produce
----------------------------------
``accountability`` level 2 is defined and never emitted. A CIMD is fetched
over TLS and checked for self-consistency, and that is the whole of it — there
is no signature over the document and no attestation by a third party, so
"this firm says it operates this agent" is as far as the evidence goes. Level 2
is in the vocabulary so a deployment that *does* have an attestation has
somewhere to put it, and so this file does not quietly imply the lab checked
something it did not. See FINDINGS.

Nothing here is ever self-asserted by the agent. An agent cannot claim a level;
levels are derived from what this server verified. That was already the rule
for client metadata in `app.py` ("resolved and shown, never trusted") — this
generalises it.
"""

from __future__ import annotations

# Levels are small on purpose. A scale with room for gradations invites
# gradations nobody can evidence.
BINDING_NONE, BINDING_KEY = 0, 1
PROVENANCE_SELF, PROVENANCE_ISSUER = 0, 1
ACCOUNTABILITY_NONE, ACCOUNTABILITY_SELF_ASSERTED, ACCOUNTABILITY_ATTESTED = 0, 1, 2

AXES = ("binding", "provenance", "accountability")

# Human-readable, for the pending dialog Alice actually reads. Her portal
# should never show her a bare integer.
DESCRIPTIONS: dict[str, dict[int, str]] = {
    "binding": {
        0: "not bound to any key",
        1: "bound to a key, recognisable next time",
    },
    "provenance": {
        0: "self-minted key — nothing to check it against",
        1: "credential issued by {issuer}, signature verified",
    },
    "accountability": {
        0: "no operator named",
        1: "{operator} says it operates this agent (self-asserted)",
        2: "{operator}, attested by a third party",
    },
}


def assess(identity: dict) -> dict:
    """Derive the assurance axes from what this server verified.

    ``identity`` is the record `verify_contract` built: it is already the
    output of verification rather than a set of claims, which is the reason
    this function cannot be fooled by a contract that asserts a level.
    """
    level = identity.get("level")
    meta = identity.get("client_metadata") or {}

    provenance = PROVENANCE_ISSUER if level == "identified" else PROVENANCE_SELF

    if not meta:
        accountability = ACCOUNTABILITY_NONE
    elif meta.get("verified"):
        # Resolved, and the document claims the URL it was fetched from. That
        # rules out third parties publishing metadata about someone else's
        # agent; it does not make the contents true.
        accountability = ACCOUNTABILITY_SELF_ASSERTED
    else:
        # Offered and did not resolve. Deliberately not distinguished from
        # "none offered" in the level, because a claim that cannot be checked
        # is worth what no claim is worth.
        accountability = ACCOUNTABILITY_NONE

    return {
        # The grant loop cannot reach this code without a verified signature
        # over a key it can name, so this is 1 by construction. Kept explicit
        # so a profile that changes it has to change it here, visibly.
        "binding": BINDING_KEY,
        "provenance": provenance,
        "accountability": accountability,
    }


def describe(axes: dict, identity: dict) -> list[str]:
    """One sentence per axis, for the dialog she reads before deciding."""
    meta = identity.get("client_metadata") or {}
    operator = meta.get("client_name") or meta.get("client_id") or "an operator"
    issuer = identity.get("iss") or "an issuer"
    out = []
    for axis in AXES:
        text = DESCRIPTIONS[axis].get(axes.get(axis, 0), "")
        out.append(text.format(operator=operator, issuer=issuer))
    return out
