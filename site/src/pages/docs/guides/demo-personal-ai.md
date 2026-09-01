---
templateKey: doc
title: "Demo: Her personal AI"
seoTitle: "Demo standing consent answering for an owner who is asleep"
description: pAI-OS answering from standing consent, and refusing what it cannot ask her about.
next:
  - title: The firm's book
    to: /docs/guides/demo-the-firms-book/
  - title: Put the authority on her device
    to: /docs/guides/personal-authority/
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
| 0 | **Terminal**<br>`make k8s-status` | Show the whole lab first. `paios` sits in **her** namespace, beside her authority and her portal — not in Bob's, and not in Meridian's. It is another way of reaching her, not another way around her. |
| 1 | **Terminal**<br>`make kagent-ask Q="What is in Alice's portfolio?" SIM=0` | Held for her Start with the ordinary shape: she is asked. Approve it in her portal. Do this first so the room has seen a normal request land before it stops landing. |
| 2 | **Terminal**<br>`make k8s-paios` | Her personal AI starts answering. Kwaai's pAI-OS, running our ability, holding her key. It authenticates to her authority with an RFC 9421 signature rather than a browser session — **it is her, arriving a different way**, and her policy still decides. |
| 3 | **Terminal**<br>`make kagent-ask Q="Show me her transaction history and cost basis." SIM=0` | Through · no approval Answered in seconds, and her portal never moves. **Point at the empty queue on the right.** The log still prints *Alice has been asked* — she was — and the answer came back from standing consent she gave ahead of time. She is asleep, and this is what "she is not woken" looks like from the other side. |
| 4 | **Terminal**<br>`make kagent-ask Q="Sell 200 shares of her AAPL position." SIM=0` | Refused The trade is refused, not answered and not held. Her AI has no channel to wake her, so it will not guess on her behalf: it records *no channel to her* and stops. **Standing consent is not a stand-in for her.** The surface that cannot ask her is the surface that says no. |
| 5 | **Terminal**<br>`make k8s-paios-down` | Hand the decisions back. Nothing is rebuilt and nothing is lost. Her portal is the surface again. |
| 6 | **Portal**<br>Approve | Held for her Run step 4 again — now it waits for her. Same protocol, same tier, same request. A different surface is answering, and the one that can reach her is the one allowed to decide this. **Both surfaces doing the part each can do**, and neither pretending to be the other. |
| 7 | **Portal**<br>Settings → Security → Agent Authorization | One ledger, both surfaces. The grant her AI made and the one she made herself sit in the same record, against the same agent, correlated to the same negotiation. **Her ledger does not distinguish them, and it should not** — both were her. |
