---
templateKey: doc
title: "Demo: Her own agent"
seoTitle: "Demo a first-party agent held to the same ceiling as a stranger"
description: One rule and one tier, with an agent she operates and one she does not.
next:
  - title: Her personal AI
    to: /docs/guides/demo-personal-ai/
  - title: Her own agent
    to: /docs/overview/first-party/
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
| 0 | **Terminal**<br>`make k8s-status` | Show the whole lab first. Note that `sterling-vance` is Bob's namespace and `alice` is hers. By the end, an agent in each will have asked her authority for the same thing. |
| 1 | **Her portal**<br>Settings → Security → Agent Authorization → Operators<br>`https://alice-agent.uma.lab` | Alice claims an origin as hers. This is half a decision and the portal treats it as half. **Anybody may point an agent at her origin** — a metadata document only proves it came from the URL it names. The other half is that **only she can put a key in her directory**, and her authority checks for both. |
| 2 | **Her portal**<br>My Terms → Trade execution → add rule<br>`When:  the agent is one of mine`<br>`Then:  allow without asking me` | One rule, on the tier she cares most about. **The rule names no agent.** It does not list a key, a vendor or a product — only that the thing asking is hers. She is describing a relationship, and anything that enters or leaves it is covered without her editing this again. |
| 3 | **Terminal**<br>`make kagent RESOURCE=hers` | Bring up an agent she operates. As it starts, the adapter publishes its signing key in her directory and names her origin as its client id — the second half from step 1, done the only way it can be done. |
| 4 | **Terminal**<br>`make kagent-ask RESOURCE=hers Q="Sell 200 shares of my AAPL position." SIM=0` | Through · no approval The trade goes through and she is never asked. **Watch the right screen while this runs and say what is not happening.** Her portal does not move. No badge, no queue, no tap. The next step is the same rule and the same tier, so make them notice this one. |
| 5 | **Terminal**<br>`make kagent-ask Q="Sell 200 shares of her AAPL position." SIM=0` | Tier 3 · Trade execution Now Bob's agent asks for exactly the same thing. It is attested too — a real operator, a published key, a signed request. It is simply **not hers**, so her rule does not reach it and the request stops. |
| 6 | **Her portal**<br>Approve | Held for her She is asked, exactly like anybody else. Either answer makes the point, so take whichever the room wants. **Being hers bought less friction and no more access.** Her tier is the ceiling in both directions; the only thing that moved was whether she had to be woken. |
| 7 | **Her portal**<br>Operators → Disclaim | Taken back She un-claims the origin, then re-run step 4. Her own agent is asked now, like a stranger, with no change to the agent at all. **What made it hers was her say-so, and it was hers to withdraw** — which is the difference between a relationship and a credential. |
