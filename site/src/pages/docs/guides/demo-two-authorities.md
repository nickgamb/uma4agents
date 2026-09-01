---
templateKey: doc
title: "Demo: two owners, two authorities"
seoTitle: "Demo two owners answering the same agent differently"
description: One agent, one key, two owners — opposite answers, and nothing anywhere reconciling them.
next:
  - title: "Demo: the firm's book"
    to: /docs/guides/demo-the-firms-book/
    blurb: What happens when the resource is not hers at all.
  - title: Many owners, one resource server
    to: /docs/overview/multi-owner/
    blurb: Why there is no privileged owner and no special case.
---

Meridian holds Alice's account and Carol's. Each owner has her own
authorization server, her own signing key, her own identity provider. The same
agent negotiates with both and gets a separate answer from each.

**Answer the two requests differently.** The disagreement is the demo, and it
is the part no hub-shaped model of this can do.

## The run-through

**0 · Terminal — `make k8s-status`**
`alice` and `carol` are separate namespaces with a `uma-as` each. Two
authorities, not one server with two rows in a table.

**1 · Terminal — `make kagent RESOURCE=carol`**
Carol is not a tenant of Alice's. She runs her own everything.

**2 · Terminal**

```bash
make kagent-ask RESOURCE=carol Q="What is in Carol's portfolio?" SIM=0
```

Read the challenge line out loud: it names `carol-as.uma.lab`. Nothing in the
agent picked that — **the resource published which authority speaks for it**,
which is the only reason an owner gets to choose one at all.

**3 · Carol's portal — Approve**
SCHD, IEFA, TLT. Her holdings, from her vault, under terms she wrote. Alice has
no part in this and never hears about it.

**4 · Terminal**

```bash
make kagent-ask Q="What is in Alice's portfolio?" SIM=0
```

Same agent, same key, same tool — different owner. This time the challenge
names `alice-as.uma.lab`.

**5 · Alice's portal — Deny**
**They disagreed, and nothing had to reconcile them.** No owner sits above
them, neither authority was told what the other decided, and no component had
to hold both answers at once.

**6 · Both portals — Settings → Security → Agent Authorization**
Carol's ledger records a grant she allowed. Alice's records a refusal she made.
Same agent in both, and each account of it belongs only to its own owner.

## What it establishes

Add a third owner, or a thousandth, the same way. What varies between
deployments is how many owners live in one process — one each here, many in one
elsewhere — and that is a packaging choice the grant loop cannot observe.

An authorization server holding one owner refuses everyone else at the door
rather than serving them and filtering, and each authority trusts only its own
owner's identity provider. One that accepted somebody else's tokens for its
owner would be only partly hers.
