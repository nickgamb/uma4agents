---
templateKey: doc
title: "Demo: Alice to Bob"
seoTitle: "Demo an unmodified agent framework held to an owner's policy"
description: Three questions to an agent nobody modified, and an owner deciding each one from her own portal.
next:
  - title: Two owners, one account
    to: /docs/guides/demo-joint-account/
  - title: Her own agent
    to: /docs/guides/demo-her-own-agent/
---

Three questions to Bob's agent. Watch Alice's side, not the agent's.

**Left screen** — Terminal, `~/uma4agents`
**Right screen** — Alice's portal, `https://portal.uma.lab`

## Pre-demo setup

From cold to ready. Four commands on a Mac, two in a Codespace, about 20
minutes.

**1 · Once per machine.** Points your OS resolver at the lab's DNS so
`*.uma.lab` works in a browser. One sudo. Skip both in a Codespace — it uses
`/etc/hosts` instead.

```bash
brew install kind helm
make dns-setup
```

**2 · Build the lab.** Three-node kind cluster, Istio ambient, kgateway,
cert-manager, CloudNativePG, and every party in its own namespace. ~13 minutes
cold. If the compose stack is running it will stop you — both want :443 and
:53, so run `make down` and try again.

```bash
make kind-up
```

**3 · Trust the CA.** cert-manager issues the lab CA inside the cluster; this
trusts it locally so her portal loads with no warning. Re-run after every
`kind-up` — a new cluster means a new CA. In a Codespace run
`make codespaces-web` instead.

```bash
make k8s-trust-ca
sudo security add-trusted-cert -d -r trustRoot \
  -k /Library/Keychains/System.keychain /tmp/u4a-k8s-ca.pem
```

**4 · Bring up the agent.** kagent's controller, the U4A adapter in Bob's
namespace, and a model for the agent to think with. Your key goes into a
Kubernetes Secret and nowhere else.

```bash
export ANTHROPIC_API_KEY=sk-ant-...
make kagent
```

Then open `https://portal.uma.lab` on the right screen, log in as **alice** /
**alice-demo**, and start the run-through. A cluster this fresh already has
zero connections, so there is nothing to clear.

To ask Bob's agent from a browser instead of the terminal, open
`https://kagent.uma.lab`, sign in as **bob** / **bob-demo**, choose
`sterling-vance/advisory-agent`, and put the same questions to it in a new
chat.

**In a Codespace.** Only steps 2 and 4. No resolver to edit, no CA to trust —
`kind-up` publishes the portal for you. To republish it later:

```bash
make codespaces-web
```

**Running it again.** Rewinds her ledger. The demos use a fresh agent key each
run, so most of them repeat without it.

```bash
make k8s-reset
```

### Switching the model

Another provider key:

```bash
export OPENAI_API_KEY=sk-...
make kagent MODEL=openai
```

Another model:

```bash
ANTHROPIC_MODEL=claude-opus-4-5 make kagent
OPENAI_MODEL=gpt-4o make kagent MODEL=openai
```

A model in the cluster instead:

```bash
make kagent MODEL=ollama
```

## The run-through

Terminal on the left, her portal on the right. One question gets asked twice,
on purpose.

**0 · Terminal.** Display the status of the entire lab. Every container's
status.

```bash
make k8s-status
```

**1 · Terminal** — *tier 1 · holdings summary.* Bob's agent is about to ask for
Alice's holdings. This is stock kagent. Nobody changed it, and it has never
heard of UMA. All it sees is three MCP tools.

```bash
make kagent-ask Q="What is in Alice's portfolio?" SIM=0
```

**2 · Portal — badge shows 1 → Approve.** *Held for her.* It stopped. Alice has
never met this agent. Nothing happens until she says yes. Approve, and the
holdings come back on the left. **What she granted covers that one call and
nothing else.**

**3 · Terminal** — *tier 2 · transactions.* Now it wants her transaction
history. That is a different tier. Letting it see her holdings gave it no
access to this.

```bash
make kagent-ask Q="Show me her transaction history and cost basis." SIM=0
```

**4 · Portal — Approve.** *Held for her.* It stops again, and this is the last
time. She approves each tier once. **Now lets watch what happens when it
asks for the same thing again.**

```bash
make kagent-ask Q="Show me her transaction history and cost basis." SIM=0
```

**5 · Terminal** — *through · no approval.* Nothing stopped. Nobody approved
this one. Same question as before. Her terms already covered it, so it went
straight through while she was away. **The portal never moved.**

```bash
make kagent-ask Q="Show me her transaction history and cost basis." SIM=0
```

**6 · Terminal** — *tier 3 · trade execution.* Now it wants to sell her shares.
She marked this tier ask-me, so it stops and waits for her. The agent just sees
a slow tool call.

```bash
make kagent-ask Q="Sell 100 shares of her AAPL position." SIM=0
```

**7 · Portal — Deny.** *Refused.* She says no, and the trade does not happen.
The agent stops there. It has no leftover token to retry with.

**8 · Portal — Settings → Security → Agent Authorization.** Everything is
recorded on her side. Each agent, what it promised, what it touched, and what
she approved or refused. **Click Revoke** if they ask what happens next.
