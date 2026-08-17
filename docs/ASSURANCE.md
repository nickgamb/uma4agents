# Agent assurance

Alice's tiers name resources. This is the other axis: what her authority can
establish about the agent *asking* — without an allow-list, which is an ACL
wearing a new hat.

The distinction the whole thing turns on: **assurance here is what her own
authority verified, not what the agent attested.** Checks it ran, against
documents it fetched. An agent cannot claim a level, and no third party is
asked to have done the checking on her behalf.

Run it: `make assurance-check`, or `make k8s-assurance-check` in the cluster.
Unit tests, needing nothing running: `make rules-test`.

![Agent assurance starts at zero. Five steps, left to right, each one a check the owner's authority performed itself: nothing yet, with all three axes at zero, for an agent she has never seen; the agreement's signature verified against a key she can name; the credential's issuer verified against its published keys; an operator metadata document resolved and self-consistent; and that operator's own key directory holding this very key, which the agent could not have added. Below, one rule from her holdings tier — when accountability is below 1, ask — read against each step: it fires at the first three and is silent at the last two.](assurance.svg)

## What her authority checks

| Axis | The check it runs | What the lab produces |
|---|---|---|
| `binding` | Did the agreement's signature verify against a key this server can name? | 0 until it has. Read from the verification result, never assumed from the call path. |
| `provenance` | Was the credential carrying that key signed by an issuer whose published keys verify it? | 0 for a bare key, 1 for a verified `aa-agent+jwt`. |
| `accountability` | Is anyone named and reachable behind it? | 0 for none. 1 for a CIMD that resolved and claims the URL it was fetched from. 2 when that operator's own key directory holds *this agent's key*. |

Every axis starts at 0 and rises only on a check that **ran and passed** in this
negotiation. Nothing is granted by construction. Stated for the parts that can
fail: *an unresolvable claim scores what no claim scores, and a check that did
not run counts as one that failed.*

They are never added up. A composite is the mechanism by which strong key
binding comes to excuse an unknown operator, so there is deliberately no
function here that produces one — `make rules-test` asserts the absence.

### The step from 1 to 2 is the whole of accountability

Level 1 is self-assertion: an operator publishes a document about itself and the
only thing checked is that the document claims the URL it was fetched from. That
rules out third parties publishing metadata about someone else's agent. It says
nothing about *this* agent — any agent can point at any operator's public CIMD,
and `make assurance-check` includes one that does.

Level 2 closes that without an accreditation scheme. The agent names the
operator's Web Bot Auth key directory in its contract header; the authorization
server fetches it and looks for the RFC 7638 thumbprint of the key that signed
the contract. The operator published this agent's key — a claim by the operator,
about a key the agent cannot add itself, checked by the party relying on it.

Two constraints keep it honest, both in `operator_published_key`:

- the directory must be **same-origin with the `client_id`**, or an agent points
  at a directory it runs and attests to itself. The check demonstrates this: an
  agent claiming a fake operator while pointing at the *real* operator's
  directory is rejected, and the reason is logged;
- a directory that will not resolve leaves the claim at level 1 rather than
  counting against the agent. An operator's outage is not evidence about an
  agent.

Only a cache *hit* is served from cache, for the same asymmetry: a stale hit
keeps attesting a key the operator has disowned, while a stale miss merely fails
to recognise one just published — the common case, since an agent enrols and
then immediately negotiates.

What is still missing at level 2 is anyone *outside* the operator. Attestation
by an accreditation body or a regulator would be a further level; it needs a
trust framework that does not exist, and this does not invent one.

## The asymmetry

Her own record of an agent is kept separate and called **standing**: has she met
it, how long ago, has she ever revoked it, has she approved anything at this
tier.

> **What she verified about the agent may only tighten a requirement. Only what
> she decided herself may relax one.**

It follows from who produced the evidence. The three checks are performed on
material the requesting side supplied, or on documents belonging to an issuer
she never chose. Her own decisions are the one kind the requesting side had no
hand in producing.

The direction reads backwards easily, so plainly: **showing more never makes a
request stricter.** Friction comes from a *gap*. An agent that can show more
avoids friction that showing less would have cost, and gains no access it would
not otherwise have had — the ceiling is whatever she said about her own
resources.

Which leaves the consequence that makes it safe to read self-asserted metadata
at all, and the reason none of this needs a registry:

> **A lie can only cost the liar friction.**

## Where the rest of it lives

This document is about what her authority can verify. The things built on top
have their own homes:

| | |
|---|---|
| Writing rules over these facts, adding terms of her own, and the validation that has to happen where policy is *stored* | [u4a.ai/docs/guides/owner-policy](https://u4a.ai/docs/guides/owner-policy/) |
| Why relaxation may rest only on her own decisions, and not on what this server granted | same guide, step 3 |
| The cap on how much of her attention a stranger can spend, and why one queue defended the wrong half | [u4a.ai/docs/overview/attention](https://u4a.ai/docs/overview/attention/), and FINDINGS recommendation 14 |
| Blocking an operator rather than one agent at a time | [u4a.ai/docs/overview/revocation](https://u4a.ai/docs/overview/revocation/), and `POST /owner/operators/block` in [PROTOCOL.md](PROTOCOL.md) |

## See also

- [FLOW.md](FLOW.md) — why her policy still names no identity system
- [FINDINGS.md](../FINDINGS.md) — recommendations 13 and 14
- `services/uma-as/assurance.py`, `services/uma-as/policy.py`
