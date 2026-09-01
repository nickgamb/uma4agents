---
templateKey: doc
title: "Demo: two owners, one account"
seoTitle: "Demo a jointly held account neither owner can release alone"
description: Two people join a mandate, write their own terms, and watch an agent be unable to get past either of them.
next:
  - title: "Demo: two owners, two authorities"
    to: /docs/guides/demo-two-authorities/
    blurb: Two owners who are not sharing anything.
  - title: Joint ownership
    to: /docs/overview/joint-ownership/
    blurb: The mandate, the verdict and the tally, explained.
---

A joint account is the ordinary case of a problem with no mechanism anywhere:
**a resource with two owners of equal standing, where neither can decide
alone.** No party sits above them to arbitrate.

**Terminal on the left, two portals on the right** — hers and Carol's, side by
side. Steps 1 to 3 are the two of them agreeing to hold something together, and
they are half the point. Do them live.

## The run-through

**0 · Terminal — `make k8s-status`**
Point at `tally`. It is its own party, it owns nothing, and it is about to be
the thing neither owner has to trust.

**1 · Alice's portal — Agent Access → Joint accounts**

```
Where it is counted:  https://joint-tally.uma.lab
Account:              meridian-joint
```

Then **See what this commits you to**. It names Carol as the other holder and
says *"Every holder has to allow a request. Any one of you can stop it."* Tick
the box and **Join** — her authority refuses a join without that tick, and
records what she agreed to.

**2 · Carol's portal — the same two values**
Two people, two authorities, one account. Neither was enrolled by the other
naming her; being a co-owner is something you agree to, not something done to
you.

**3 · Both portals — My Terms → new tier**

| | Alice | Carol |
|---|---|---|
| Name it | Joint - Alice | Joint - Carol |
| Governs | meridian-joint | meridian-joint |
| Expires after | 3600 | 900 |
| Prohibited | model-training | resale-to-third-parties |

Alice is looser on every field on purpose, so that every narrowing in step 7
visibly came from Carol.

**4 · Terminal — `make kagent RESOURCE=joint`**
Nothing about the agent is joint-aware. The resource publishes its own
authority, so it finds out it needs two people by asking.

**5 · Terminal**

```bash
make kagent-ask RESOURCE=joint Q="What is in the joint account?" SIM=0
```

It stops, and two portals light up. One question, asked of one agent, is now a
decision waiting on two people at two authorities.

**6 · Alice's portal — Approve**
Let it sit for a beat. The terminal is still waiting. **One holder is not a
decision**, and there is no majority to round up to.

**7 · Carol's portal — Approve**
Now it completes: VTSAX, VBTLX, MMDA. Read the folded document out of the log —
**900 seconds** (Carol's, the shorter), **positions:read only** (all they both
offer), and **both prohibitions**. One agreement, made of two people's terms.

The grant carries a signed verdict from each holder, and the enforcement point
re-runs the count itself against the keys their authorities publish. A tally
that invented a yes dies at the door.

**8 · Terminal**

```bash
make kagent-ask RESOURCE=joint Q="Sell 400 shares of VTSAX from the joint account." SIM=0
```

Both are asked again. Nothing carried over — the previous grant was spent.

**9 · Carol's portal — Deny**
It ends immediately and **Alice is never asked**. Under a mandate that needs
everybody, one refusal settles it and nobody waits for the rest — which is also
why the tally cannot stall a decision by sitting on it.

## What it establishes

This is not consensus and it is not a ledger. There is no ordering to agree on,
no long-lived state to fork, and the coordinator does not have to be trusted —
because it was made **unable to fabricate a yes** rather than merely watched.

`meridian-either` is the same machinery with the rule set to `any`, which is
the "either or survivor" half of how joint accounts actually work.
