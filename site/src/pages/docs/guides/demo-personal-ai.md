---
templateKey: doc
title: "Demo: her personal AI"
seoTitle: "Demo standing consent answering for an owner who is asleep"
description: Kwaai's pAI-OS holding her key and answering from standing consent — and refusing the one thing it has no way to ask her about.
next:
  - title: "Demo: the firm's book"
    to: /docs/guides/demo-the-firms-book/
    blurb: A resource that is not hers at all.
  - title: Put the authority on her device
    to: /docs/guides/personal-authority/
    blurb: Build the surface this demo uses.
---

The same lab with [Kwaai's pAI-OS](/docs/overview/) added, running our ability.
It holds her key and answers from standing consent she gave ahead of time.

Her portal stays on screen throughout, and for most of this demo **nothing
lands in it**. Point at the empty queue — that is the result.

## The run-through

**0 · Terminal — `make k8s-status`**
`paios` sits in *her* namespace, beside her authority and her portal — not in
Bob's, and not in Meridian's. It is another way of reaching her, not another
way around her.

**1 · Terminal**

```bash
make kagent-ask Q="What is in Alice's portfolio?" SIM=0
```

Start with the ordinary shape: she is asked, and you approve it in her portal.
Do this first so the room has seen a normal request land before it stops
landing.

**2 · Terminal — `make k8s-paios`**
Her personal AI starts answering. It authenticates to her authority with an RFC
9421 signature rather than a browser session — **it is her, arriving a different
way** — and her policy still decides.

**3 · Terminal**

```bash
make kagent-ask Q="Show me her transaction history and cost basis." SIM=0
```

Answered in seconds, and her portal never moves. The log still prints *Alice has
been asked* — she was — and the answer came from standing consent. She is
asleep, and this is what "she is not woken" looks like from the other side.

**4 · Terminal**

```bash
make kagent-ask Q="Sell 200 shares of her AAPL position." SIM=0
```

Refused, not answered and not held. Her AI has no channel to wake her, so it
will not guess on her behalf: it records *no channel to her* and stops.
**Standing consent is not a stand-in for her.** The surface that cannot ask her
is the surface that says no.

**5 · Terminal — `make k8s-paios-down`**
Nothing is rebuilt and nothing is lost. Her portal is the surface again.

**6 · Portal — Approve or Deny**
Run step 4 again; now it waits for her. Same protocol, same tier, same request.
A different surface is answering, and the one that can reach her is the one
allowed to decide this.

**7 · Portal — Settings → Security → Agent Authorization**
The grant her AI made and the one she made herself sit in the same record,
against the same agent, correlated to the same negotiation. **Her ledger does
not distinguish them, and it should not** — both were her.

## What it establishes

The two surfaces do not run against each other well, and that is the point.
While her personal AI is up it answers everything she has given it standing
consent for, so those requests never appear in her portal — there is nothing
left to tap. That is not a conflict to fix; it is what delegation looks like
when it works.

**Both surfaces doing the part each can do**, and neither pretending to be the
other.
