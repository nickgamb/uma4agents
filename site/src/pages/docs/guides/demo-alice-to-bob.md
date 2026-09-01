---
templateKey: doc
title: "Demo: Alice to Bob"
seoTitle: "Demo an unmodified agent framework held to an owner's policy"
description: Three questions to an agent nobody modified, and an owner deciding each one from her own portal.
next:
  - title: "Demo: two owners, one account"
    to: /docs/guides/demo-joint-account/
    blurb: The same shape, with two people who must both agree.
  - title: "Demo: her own agent"
    to: /docs/guides/demo-her-own-agent/
    blurb: What changes when the agent asking is hers.
---

The reference demonstration. [kagent](https://kagent.dev) is not ours, has not
been modified, and has never heard of UMA. It sees three ordinary MCP tools.
Her policy governs it anyway.

**Terminal on the left, her portal on the right.** Watch her side, not the
agent's.

## Before the room arrives

```bash
make kagent
make k8s-reset
```

Open `https://portal.uma.lab` and sign in as `alice` / `alice-demo`. The reset
matters: without it she has already met this agent, and the first beat of the
demo is that she has not.

## The run-through

**0 · Terminal — `make k8s-status`**
Show the whole lab. Every party in its own namespace: her authority, the firm
holding her assets, and Bob's agent, with no path between them except the edge.

**1 · Terminal**

```bash
make kagent-ask Q="What is in Alice's portfolio?" SIM=0
```

Tier 1, her holdings. Stock kagent — nobody changed it, and all it can see is
three MCP tools.

**2 · Portal — Approve**
It stopped. She has never met this agent, so first contact is held for her.
Nothing happens until she says yes. Approve, and the holdings arrive: what she
granted covers that one call and nothing else.

**3 · Terminal**

```bash
make kagent-ask Q="Show me her transaction history and cost basis." SIM=0
```

A different tier. Letting it see her holdings gave it no access to this.

**4 · Portal — Approve**
She is asked once per tier, not once per agent. Tell the room to watch what
happens when it asks for the same thing again.

**5 · Terminal — the same command again**
Nothing stops. Nobody approved this one. Her standing terms already covered it,
so it went straight through while she was away, and the portal never moved.
**This is the point of the tier system**, and it only lands because they
watched step 4.

**6 · Terminal**

```bash
make kagent-ask Q="Sell 200 shares of her AAPL position." SIM=0
```

She marked this tier ask-me, so it stops and waits for her. From the agent's
side an ask-me tier is simply a slow tool call.

**7 · Portal — Deny**
She says no, and the trade does not happen. The agent stops there with no
leftover token to retry with.

**8 · Portal — Settings → Security → Agent Authorization**
Everything is recorded on her side: each agent, what it promised, what it
touched, and what she approved or refused. Click **Revoke** if they ask what
happens next.

## What it establishes

The requesting side needed an adapter, not a rewrite. Everything that makes
those three tools reachable — the challenge, the terms, the signed agreement,
the proof-of-possession key, the single-use grant — happens in the U4A adapter
beside the agent, in Bob's namespace, holding Bob's key. The framework above it
is untouched, and her authority has never heard of it.

That claim is checkable without a model in the way:

```bash
make k8s-adapter-check
```

An MCP client with no U4A code in it, reaching her resources.
