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
                    recognisable next time? 0 until the agreement's signature
                    has actually verified against a key this server can name.
                    In the four-beat grant that happens before anything reaches
                    here — but it is *read* from the verification result rather
                    than assumed from the call path, which is the difference
                    between a level and a comment.

``provenance``      Can her authority check where the agent's credential came
                    from? A bare key is self-minted (0). A key carried in an
                    ``aa-agent+jwt`` whose signature verified against its
                    issuer's published keys came from somewhere checkable (1).

``accountability``  Is there a named party standing behind it that she could
                    reach? No client_id at all (0). A Client ID Metadata
                    Document that resolved and claims the URL it was fetched
                    from (1). The named operator having *published this
                    agent's signing key* in its own key directory, checked by
                    this server against a document the agent does not control
                    (2).

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

The step from 1 to 2 is the whole of accountability
---------------------------------------------------
Level 1 is a self-assertion: an operator publishes a document about itself, and
the only thing checked is that the document claims the URL it was fetched from.
That rules out third parties publishing metadata about someone else's agent. It
does not make the contents true, and in particular it says nothing about *this*
agent — any agent can point at any operator's public CIMD.

Level 2 closes exactly that gap, and needs no accreditation scheme to do it.
The agent names the operator's Web Bot Auth key directory; this server fetches
it and looks for the RFC 7638 thumbprint of the key that signed the contract.
If it is there, the operator has published this agent's key — a claim the
operator made, about a key the agent cannot add itself, checked by the party
relying on it.

Two constraints keep that honest, both in `operator_published_key`:

* the directory must be **same-origin with the client_id**, or an agent points
  at a directory it runs and attests to itself;
* a directory that will not resolve leaves the claim at level 1 rather than
  counting against the agent. An operator's outage is not evidence about an
  agent, and treating it as such makes every outage look like an attack.

What is still missing at level 2 is anyone *outside* the operator. Attestation
by an accreditation body, a chamber of commerce, a regulator — that would be a
level 3, it needs a trust framework that does not exist, and this deliberately
does not invent one. See FINDINGS.

Zero trust, meaning zero
------------------------
Every axis starts at 0 and is raised only by a check that **ran and passed** in
this negotiation. Nothing is granted by construction, by the shape of the call
path, or by "we could not have got here otherwise".

An earlier version of this file set ``binding`` to 1 unconditionally, with a
comment explaining that the grant loop could not reach it without a verified
signature. The comment was true. It was still wrong: a level that records an
assumption rather than an observation keeps reporting the assumption after
somebody refactors the thing that made it true, and it reports it in the one
direction that costs the owner something. So every value here now comes from a
field that a verification step wrote.

Nothing is ever self-asserted by the agent either. An agent cannot claim a
level. That was already the rule for client metadata in `app.py` ("resolved and
shown, never trusted") — this generalises it.
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
        0: "not bound to any key this server verified",
        1: "bound to a key, recognisable next time",
    },
    "provenance": {
        0: "self-minted key — nothing to check it against",
        1: "credential issued by {issuer}, signature verified",
    },
    "accountability": {
        0: "no operator named",
        1: "{operator} says it operates this agent (self-asserted)",
        2: "{operator} published this agent's signing key as its own",
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

    # Set by verify_contract when the agreement's signature verified against a
    # key this server can name. Absent means the check did not run, and an
    # unrun check is worth exactly what a failed one is worth.
    binding = BINDING_KEY if identity.get("key_bound") else BINDING_NONE

    provenance = PROVENANCE_ISSUER if level == "identified" else PROVENANCE_SELF

    if not meta:
        accountability = ACCOUNTABILITY_NONE
    elif meta.get("verified") and identity.get("operator_attested"):
        # The named operator published the key that signed this contract. Not
        # a third party vouching for the operator — the operator vouching for
        # this agent, which is the claim that was missing at level 1.
        accountability = ACCOUNTABILITY_ATTESTED
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
        "binding": binding,
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
