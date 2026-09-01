---
templateKey: doc
title: "Demo: Alice to Bob"
seoTitle: "Demo an unmodified agent framework held to an owner's policy"
description: An agent framework nobody modified, asking for an owner's holdings, and her deciding each request from her own portal.
next:
  - title: Two owners, one account
    to: /docs/guides/demo-joint-account/
  - title: Her own agent
    to: /docs/guides/demo-her-own-agent/
---

**Left screen** — Terminal, `~/Documents/Github/uma4agents`  
**Right screen** — Alice's portal, `https://portal.uma.lab`

## Pre-demo setup

| # | Run this | What it does |
|---|---|---|
| 1 | **Once per machine**<br>`brew install kind helm`<br>`make dns-setup` | Points your OS resolver at the lab's DNS so ***.uma.lab** works in a browser. One sudo. **Skip both in a Codespace** — it uses `/etc/hosts` instead. |
| 2 | **Build the lab**<br>`make kind-up` | Three-node kind cluster, Istio ambient, kgateway, cert-manager, CloudNativePG, and every party in its own namespace. **~13 minutes cold.** If the compose stack is running it will stop you — both want :443 and :53, so run `make down` and try again. |
| 3 | **Trust the CA**<br>`make k8s-trust-ca`<br>`sudo security add-trusted-cert -d -r trustRoot \`<br>`-k /Library/Keychains/System.keychain /tmp/u4a-k8s-ca.pem` | cert-manager issues the lab CA inside the cluster; this trusts it locally so the portals load with no warning. **Re-run after every `kind-up`** — a new cluster means a new CA. In a Codespace run `make codespaces-web` instead. |
| 4 | **Bring up the agent**<br>`export ANTHROPIC_API_KEY=sk-ant-...`<br>`make kagent` | kagent's controller, the U4A adapter in Bob's namespace, and a model for the agent to think with. Your key goes into a Kubernetes Secret and nowhere else. See **Switching the model** below for the other providers. |

## The run-through

| # | Do this | Say this |
|---|---|---|
| 0 | **Terminal**<br>`make k8s-status` | Display the status of the entire lab Every containers status |
| 1 | **Terminal**<br>`make kagent-ask Q="What is in Alice's portfolio?" SIM=0` | Tier 1 · Holdings summary Bob's agent is about to ask for Alice's holdings. This is stock kagent. Nobody changed it, and it has never heard of UMA. All it sees is three MCP tools. |
| 2 | **Portal**<br>Badge shows 1 → Approve | Held for her It stopped. Alice has never met this agent. Nothing happens until she says yes. Approve, and the holdings come back on the left. **What she granted covers that one call and nothing else.** |
| 3 | **Terminal**<br>`make kagent-ask Q="Show me her transaction history and cost basis." SIM=0` | Tier 2 · Transactions Now it wants her transaction history. That is a different tier. Letting it see her holdings gave it no access to this. |
| 4 | **Portal**<br>Approve | Held for her It stops again, and this is the last time. She approves each tier once. **Tell them to watch what happens when it asks for the same thing again.** |
| 5 | **Terminal — same question again**<br>`make kagent-ask Q="Show me her transaction history and cost basis." SIM=0` | Through · no approval Nothing stopped. Nobody approved this one. Same question as before. Her terms already covered it, so it went straight through while she was away. **The portal never moved.** |
| 6 | **Terminal**<br>`make kagent-ask Q="Sell 200 shares of her AAPL position." SIM=0` | Tier 3 · Trade execution Now it wants to sell her shares. She marked this tier ask-me, so it stops and waits for her. The agent just sees a slow tool call. |
| 7 | **Portal**<br>Deny | Refused She says no, and the trade does not happen. The agent stops there. It has no leftover token to retry with. |
| 8 | **Portal**<br>Settings → Security → Agent Authorization | Everything is recorded on her side. Each agent, what it promised, what it touched, and what she approved or refused. **Click Revoke** if they ask what happens next. |
