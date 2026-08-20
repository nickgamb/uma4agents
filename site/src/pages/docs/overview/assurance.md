---
templateKey: doc
seoTitle: "Agent assurance: verifying an AI agent without trusting its claims"
title: Agent assurance
description: What the owner's own authority can verify about an agent asking for her things — and why nothing an agent says about itself can widen access.
next:
  - title: The owner's attention
    to: /docs/overview/attention/
    blurb: The other thing a stranger can spend.
  - title: Let the owner write her own policy
    to: /docs/guides/owner-policy/
    blurb: Turning what she can verify into rules she can hold in her head.
---

The owner's tiers say what may be asked of her resources, and name no agent.
That is what lets one policy hold for an unbounded number of strangers.

Underneath sits a second question: what does her authority actually *know*
about the agent asking? Most answers reach for what the agent attests about
itself — and end at "can you trust the issuer?"

This one does not ask that. **Assurance here is what her own authority
verified**: checks it ran, against documents it fetched. An agent cannot claim
it, and no third party is asked to have done the checking on her behalf.

![Agent assurance starts at zero. Five steps, left to right, each one a check the owner's authority performed itself: nothing yet, with all three axes at zero, for an agent she has never seen; the agreement's signature verified against a key she can name; the credential's issuer verified against its published keys; an operator metadata document resolved and self-consistent; and that operator's own key directory holding this very key, which the agent could not have added. Below, one rule from her holdings tier — when accountability is below 1, ask — read against each step: it fires at the first three and is silent at the last two.](/img/docs/assurance.svg)

## Three things she can check

Each is a question her authority answers for itself, by doing something.

| | The question | How it is answered |
|---|---|---|
| `binding` | Will she recognise this key next time? | The agreement's signature verified against a key this server can name. |
| `provenance` | Can she check where the credential came from? | The credential carrying that key was signed by an issuer whose published keys verify it. |
| `accountability` | Is anyone named and reachable behind it? | A metadata document resolved and claims the URL it was fetched from — and, one step further, that operator's own key directory holds this very key. |

The last step is where a claim stops being a claim. An operator publishing a document that says "we run agents" is
telling you about itself. An operator publishing *this agent's key* is telling
you about this agent — and it is a thing the agent cannot do on its own behalf.
Her authority fetches that directory itself and looks for the key that signed
the contract in front of it.

## It starts at nothing

Every check starts at zero and is raised only by one that **ran and passed** in
this negotiation. Nothing is granted by construction, by the shape of the call
path, or by "we could not have got here otherwise".

> An unresolvable claim scores what no claim scores, and a check that did not
> run counts as one that failed.

The three are also kept apart and never added up. There is no total, because a
total is precisely the mechanism by which strong key binding comes to excuse an
unknown operator — a trade nobody would make if they were asked directly. An
agent can be perfectly recognisable and completely unaccountable, and her policy
should be able to say so.

## What verification is allowed to do

Verified facts about the agent may only make a request **stricter**. Only the
owner's own decisions — she admitted this agent, she approved at this tier, she
has never revoked it — may make one easier.

That is not a rule bolted on. It follows from who produced the evidence: the
three checks above are performed on material the requesting side supplied, or on
documents belonging to an issuer she never chose. Her own decisions are the one
kind of evidence the requesting side had no hand in producing.

The direction is easy to read backwards, so plainly: **showing more never makes
a request stricter.** What adds friction is a *gap* — no operator named, a key
with nothing to check it against. An agent that can show more is not penalised
for it; it avoids friction that showing less would have cost. And at the top it
still gains no access it would not otherwise have had, because the ceiling is
whatever the owner said about her own resources.

Which leaves the consequence that makes any of this safe to build:

> **A lie can only cost the liar friction.**

That is why her policy can afford to read a self-asserted operator name at all,
and why none of this needs a registry, an accreditation scheme, or a trust
framework that does not exist yet. An agent presenting metadata that does not
resolve is admitted exactly like any other stranger, and gains nothing on the
second request either.

## What it is not

**It is not an assurance level.** There is no ladder to climb and no rung that
entitles an agent to anything. The numbers exist so a rule can say "below this",
and they mean nothing beyond it.

**It is not identity.** Her policy vocabulary contains no issuer, no metadata
URL, no key thumbprint — the conditions name properties of evidence, so swapping
the mechanism underneath leaves her policy unchanged. That is
[the flow property](/docs/overview/flow/) surviving contact with policy that
faces the agent.

**It is not an accreditation.** Nobody outside the operator has vouched for
anything. An attestation by a regulator or a trade body would be a further step,
it needs a trust framework that does not exist, and this deliberately does not
invent one.

Turning any of it into rules she can write is
[the owner's policy guide](/docs/guides/owner-policy/).
