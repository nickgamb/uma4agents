---
templateKey: doc
title: "Demo: what an operation leaves behind"
seoTitle: "Demo a policy rule that names the act rather than the tool"
description: Alice replaces a rule that names one tool with a rule about what an act leaves behind, and an agent that has never heard of UMA runs into it.
next:
  - title: What an operation leaves behind
    to: /docs/overview/consequence/
  - title: Alice to Bob
    to: /docs/guides/demo-alice-to-bob/
---

Alice has a rule that names a tool. She replaces it with a rule about the act,
and nothing else changes.

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

Then open `https://portal.uma.lab` on the right screen and log in as **alice** /
**alice-demo**.

**Running it again.** Rewinds her ledger and her connections.

```bash
make k8s-reset
```

## The run-through

The agent is stock kagent. It has never heard of UMA, and it never learns what
her rule says — it only ever sees a tool call that is slow, or one that fails.
Everything that changes in this demo happens on the right screen.

**0 · Portal — Settings → Security → Agent Authorization.** Open **Trade
execution** and look at *Ask me every time*. It is on because somebody once
decided that this tool was the dangerous one. It is a list of tool names,
maintained by hand, and it says nothing about *why* that tool is on it.

**1 · Terminal** — *tier 1 · holdings.* Let the agent in first, so that later
beats are about her rule and not about first contact.

```bash
make kagent-ask Q="What is in Alice's portfolio?" SIM=0
```

**2 · Portal — badge shows 1 → Approve.** *Held for her.* She has never met this
agent, so nothing happens until she says yes. The holdings come back on the
left.

**3 · Terminal** — *tier 3 · trade execution.* Now ask it to sell something.

```bash
make kagent-ask Q="Sell 200 shares of her AAPL position." SIM=0
```

**4 · Portal — Deny.** *Refused.* It stopped because that toggle is on. **Read
the pending card before you deny it.** It tells her which tier the request is
for and what the agent promised. It does not tell her what the act would do,
because nothing in her policy knows.

**5 · Portal — turn the toggle off, add a rule, Save changes.** The rule is *if
it cannot be undone at all — ask me first*. Trade execution now has **no rule
naming it**. Nothing about the vault changed, and the agent was never told.

**6 · Terminal** — *tier 1 again · straight through.* Ask for the holdings once
more. Nothing stops, and **the portal never moves**. Reading holdings is
published as `reversible`, so a rule about what cannot be undone has nothing to
say about it.

```bash
make kagent-ask Q="What is in Alice's portfolio?" SIM=0
```

**7 · Terminal** — *tier 3 again · held.* Ask it to sell again.

```bash
make kagent-ask Q="Sell 200 shares of her AAPL position." SIM=0
```

**8 · Portal — read the reason, then Approve.** *Held for her.* Under **Why
you** the card now says *it cannot be undone at all*. Nobody put the trade
endpoint on a list. The vault publishes that executing a trade is
`irreversible`, her authority pulled that in with everything else the vault
publishes, and the rule she wrote in step 5 read it.

**9 · Portal — try to write the opposite.** Add the same condition with *grant
without asking* and save. Her authority refuses it. What an act costs can raise
what a request needs and can never lower it, so the one rule she cannot write is
the one that waves an irreversible act through.

**10 · Terminal.** Her record carries the class next to the tier and the
operation, so *what was at stake* is answerable later without looking up what
`execute_trade` does.

```bash
make k8s-audit
```

## What to point at

The rule she wrote in step 5 names no tool, no agent and no operator. The vault
could add a fourth endpoint tomorrow and, if it publishes that the endpoint
cannot be undone, her rule covers it the first time an agent asks — with no
edit on her side.

## FAQs

**Who decides the class?** The resource server, in the metadata it signs. It is
the party that would have to undo the act. An agent's description of itself
stays display-only for the opposite reason.

**What about a tool nobody has described?** Undeclared is unknown. A rule about
remedy does not fire on it, and she has a separate condition — *nobody has said
whether it can be undone* — if she wants those refused too.

**Is this a risk score?** No. The classes order by how much remedy remains, not
by how bad the outcome is. A reversible act can still be catastrophic while it
stands, and nothing here adds the classes up.

**Can a resource lie?** Claiming an act is worse than it is costs it friction.
Claiming it is better buys nothing: the class is published in metadata the
resource signs, and the grant records the class it was issued against, so a
later re-declaration cannot spend a grant given under the old one.

**Does the agent see it?** Yes, in the refusal. The challenge carries the class,
so an agent learns what it is asking for before it negotiates rather than after.

**Does this need changes to the agent?** No. The lab runs stock kagent. It sees
a tool call that is slow or one that fails, exactly as it did before her rule
changed.
