"""Sub-agent introductions — verification and admission, as pure functions.

An agent that already holds a connection may put a *sibling* forward: another
agent, with its own key, run by the same operator. The sibling arrives with an
introduction signed by the agent that vouches for it, and that is all it
arrives with. It is not a token, not a grant, and not a delegation. It carries
no tier, no scope and no expiry of the parent's authority, and presenting one
buys exactly one thing: the child does not have to be introduced to the owner
from nothing. Everything after that — the terms, the tier, the grant, the
single-use ceiling — the child negotiates for itself, under its own key.

Split from `app` on purpose, the way `policy` is. The two halves here are

  * `verify_claim` — everything settleable from the document alone, and
  * `admit`        — the decision, as a function of facts already fetched.

Neither reads a store, opens a socket or knows about FastAPI, so the whole
admission rule is testable with a dict and no lab running. The caller does the
I/O and hands the answers in, exactly as `policy.evaluate` is handed facts.
"""

import json

import jwt
from jwt.algorithms import OKPAlgorithm

TYP = "u4a-introduction-v1+jws"
# A compact JWS with an embedded public key. Bounded for the same reason the
# contract's `reason` is: it is parsed and stored, and a field with no ceiling
# is a place to put a megabyte.
MAX_BYTES = 4096


class Refused(ValueError):
    """An introduction that will not be honoured, and why.

    A refusal is never fatal to the request. The child falls back to being a
    stranger and is introduced to the owner the ordinary way, which is the
    behaviour with no introduction at all. That is why every message here
    reads as a reason the shortcut does not apply rather than as an error.
    """


def verify_claim(intro: str, child_jkt: str, issuer: str) -> dict:
    """What the document settles on its own.

    Returns the introducing key and the claim's own metadata. Raises `Refused`
    if the document is not a well-formed introduction *for this child, at this
    authority, right now*.

    Note what is absent: nothing here decides whose key the introducing key
    is. An `iss` naming the introducer would have to be either ignored or
    believed, and believing it would let any agent nominate another agent's
    handle as its sponsor. The introducing identity is carried only in the
    header key, which is checkable — the signature verifies against it, and
    the caller re-derives a handle from it and looks that up.
    """
    if not isinstance(intro, str) or not intro:
        raise Refused("introduction must be a compact JWS")
    if len(intro.encode()) > MAX_BYTES:
        raise Refused(f"introduction exceeds {MAX_BYTES} bytes")
    try:
        header = jwt.get_unverified_header(intro)
    except Exception as exc:
        raise Refused(f"introduction is not a JWS: {exc}")
    if header.get("typ") != TYP:
        raise Refused(f"introduction must be typ {TYP}")
    parent_jwk = header.get("jwk")
    if not isinstance(parent_jwk, dict):
        raise Refused("introduction must carry the introducing key in its header")

    # Verified against the key in its own header. On its own that proves only
    # that the document is internally consistent — anyone can mint one of
    # these. It becomes worth something when the caller finds that key already
    # filed as one of the owner's active connections.
    #
    # `aud` pins it to one authorization server, so an introduction obtained
    # for one owner's authority is not replayable at another's. Expiry is
    # enforced by decode.
    try:
        key = OKPAlgorithm.from_jwk(json.dumps(parent_jwk))
        claims = jwt.decode(intro, key, algorithms=["EdDSA"], audience=issuer)
    except Exception as exc:
        raise Refused(f"introduction does not verify: {exc}")

    # The binding that makes an introduction non-transferable: it names the
    # key it vouches for, and that key has to be the one that signed the
    # contract underneath. Without this, a copy of somebody else's
    # introduction would admit whoever presented it.
    if claims.get("sub") != child_jkt:
        raise Refused("introduction vouches for a different key than the one "
                      "that signed this contract")

    return {
        "parent_jwk": parent_jwk,
        # Present when the introducing agent is identified rather than
        # pseudonymous: it is filed under an issuer-qualified subject, so the
        # caller needs the token to work out which connection this is.
        "agent_token": header.get("agent_token"),
        "jti": claims.get("jti"),
        "exp": claims.get("exp"),
    }


def admit(parent_conn: dict | None, child_prior: dict | None,
          same_operator: bool, live_children: int,
          fanout: int) -> None:
    """Whether this introduction is honoured. Raises `Refused` saying why not.

    Every argument is a fact the caller has already fetched, so this is a
    decision and not a lookup. The order is deliberate: cheapest and most
    absolute first, so a refusal reads as the strongest reason it was refused
    rather than an incidental one.
    """
    # 1. The introducing key has to be an agent this owner currently holds a
    #    live connection with. A key she has never seen vouches for nothing,
    #    and neither does one she has cut off.
    if parent_conn is None:
        raise Refused("the introducing agent is not a connection of this owner")
    if parent_conn.get("status") != "active":
        raise Refused("the introducing agent's connection is not active")

    # 2. The owner has to have personally approved that agent for something.
    #    `tiers_approved` is written only when she answers a pend herself —
    #    never when an organization administrator answers on her behalf — so
    #    an agent that has only ever been granted things automatically cannot
    #    become a sponsor. Without this, one automatic grant could seed an
    #    unbounded population of agents from a decision she never made.
    if not (parent_conn.get("tiers_approved") or []):
        raise Refused("the introducing agent has nothing this owner approved "
                      "in person")

    # 3. Depth. An agent that was itself introduced may not introduce, so the
    #    authority graph is one level deep and stays there. This is an
    #    explicit check and not an emergent property: the moment she approves
    #    a sub-agent at any tier it gains a `tiers_approved` entry, and
    #    without this line it would satisfy (2) and could sponsor in turn.
    if parent_conn.get("parent_handle"):
        raise Refused("an agent that was itself introduced may not introduce "
                      "another")

    # 4. An agent whose connection was revoked goes back through first contact
    #    and cannot be let back in by its sponsor. Otherwise revoking an agent
    #    would be undone by re-introducing it seconds later, and the owner's
    #    Revoke button would be advisory.
    if child_prior is not None and child_prior.get("status") != "active":
        raise Refused("this agent's connection was revoked and cannot be "
                      "restored by an introduction")

    # 5. Both keys published by the same operator, in a directory that
    #    operator controls and the agents do not. This is the half the
    #    requesting side cannot manufacture: it bounds the set of agents that
    #    can ever be introduced to the ones the operator has put its name to,
    #    and it makes a misbehaving fleet answerable to a single block.
    if not same_operator:
        raise Refused("the two agents are not published by the same operator")

    # 6. A ceiling on how many live sub-agents one agent may have. Hard rather
    #    than a policy rule, because the rule governing sub-agents is hers to
    #    write and this has to hold whether or not she has written one.
    if live_children >= fanout:
        raise Refused(f"the introducing agent already has {live_children} "
                      f"sub-agents, which is the limit ({fanout})")


def act_of(agent_claims: dict) -> dict | None:
    """The spawning agent an issuer names in a verified agent token's `act`.

    Only a subject that is a non-empty string counts; anything else in the
    claim is ignored rather than guessed at.
    """
    act = agent_claims.get("act")
    if isinstance(act, dict) and isinstance(act.get("sub"), str) and act["sub"]:
        return {"sub": act["sub"]}
    return None
