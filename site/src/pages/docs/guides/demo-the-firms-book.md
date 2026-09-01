---
templateKey: doc
title: "Demo: the firm's book"
seoTitle: "Demo an organization sharing a resource a member administers"
description: Northwind shares part of its book with a member under a role — she administers it at her own authority, and only while she is a member.
next:
  - title: "Demo: two owners, one account"
    to: /docs/guides/demo-joint-account/
    blurb: A person beside her, rather than a firm above her.
  - title: Shared ownership
    to: /docs/overview/shared-ownership/
    blurb: Roles, charters, and what an organization may not do.
---

Everything else in these demos is Alice's own account. This is the other case:
Meridian also holds Northwind Capital's book, the firm shares part of it with
her under a role, and **she administers it under her own authority and her own
terms**.

Her portal and the firm's console, side by side. Step 1 is what brings the
resource into existence, so it cannot be skipped or pre-baked.

## The run-through

**0 · Terminal — `make k8s-status`**
`northwind` is the firm: an authority and a console of its own. It is not above
her authority in `alice` — by the end you will have shown that it cannot answer
for her.

**1 · Her portal — Agent Access → Organization**

```
Enrolment code:  NW-7K2F-QX
```

The preview shows what the role would give her and what the firm would require.
Her authority **refuses a join without the tick** and records what she agreed
to, because this changes the bargain rather than a setting.

**2 · Her portal — the same page**
The firm's book is now in her authority, marked shared. It was not there a
minute ago. **She administers it; she does not own it** — and her portal says
which, because the difference decides what happens when she leaves.

**3 · Terminal — `make kagent RESOURCE=shared`**
**That resource did not exist until step 1.** Its published metadata names
*her* authority, not Northwind's: the firm holds the book and enforces the
charter, and still cannot answer a request about it.

**4 · Terminal**

```bash
make kagent-ask RESOURCE=shared Q="What is in the firm's book?" SIM=0
```

It stops — and it stops at her portal. A request about the firm's asset,
waiting on a member's decision, at the member's own authorization server.

**5 · Her portal — Approve**
NWCF, NWEQ, TLT, VNQ. The firm's book — **not her portfolio**. Her own account
was never in scope for this agent, and the role is what drew that line.

**6 · The console — Groups · Charter → Rules**
The charter's two halves, on two pages. **Groups** is what a member gets and
agrees to; saving one publishes a charter version, because it changes the
bargain. **Charter → Rules** is what the firm enforces operationally, in Rego,
and it can only refuse or interrupt — never grant, and never answer for her.

The test for which page a rule belongs on: *would a member have to agree to it
again?*

**7 · Her portal — Organization → Leave**
Run step 4 again: refused, and the resource is gone. **Leaving takes back
exactly what joining gave**, and nothing of hers goes with it — her own
account, her tiers and her ledger are untouched.

## What it establishes

Whose agent it is decides the answer. Under the analyst role's
`first-party-only`, an agent she operates reads the book and Bob's agent is
refused — with the same terms, the same key strength and the same request.

And an administrator answering on her behalf is not her: his decision never
becomes evidence that *she* decided, because that fact is one of the few
allowed to relax her own rules.
