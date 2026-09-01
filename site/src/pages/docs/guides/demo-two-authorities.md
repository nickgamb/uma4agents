---
templateKey: doc
title: "Demo: Two owners, two authorities"
seoTitle: "Demo two owners answering the same agent differently"
description: One agent and one key against two owners, who answer differently.
next:
  - title: The firm's book
    to: /docs/guides/demo-the-firms-book/
  - title: Many owners, one resource server
    to: /docs/overview/multi-owner/
---

**Left screen** — Terminal, `~/Documents/Github/uma4agents`  
**Right screen** — Two portals, `portal.uma.lab · carol-portal.uma.lab`

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
| 0 | **Terminal**<br>`make k8s-status` | Show the whole lab first. Two things to point at: `alice` and `carol` are separate namespaces with a `uma-as` each. Two authorities, not one server with two rows in a table. |
| 1 | **Terminal**<br>`make kagent RESOURCE=carol` | Point an agent at Carol's account. Meridian holds her account and Alice's. Carol runs her own authorization server, her own signing key, her own identity provider — **she is not a tenant of Alice's**. |
| 2 | **Terminal**<br>`make kagent-ask RESOURCE=carol Q="What is in Carol's portfolio?" SIM=0` | Tier 1 · Holdings Read the challenge line out loud. It names `carol-as.uma.lab`. Nothing in the agent picked that — **the resource published which authority speaks for it**, which is the only reason an owner gets to choose one at all. |
| 3 | **Carol's portal**<br>Approve | Held for her Carol allows it: SCHD, IEFA, TLT. Her holdings, from her vault, under terms she wrote. Alice has no part in this and never hears about it. |
| 4 | **Terminal**<br>`make kagent-ask Q="What is in Alice's portfolio?" SIM=0` | Same agent, same key, same tool — different owner. The only thing that changed is whose resource is being asked about. This time the challenge names `alice-as.uma.lab`. |
| 5 | **Alice's portal**<br>Deny | Refused Alice refuses the identical request. **They disagreed, and nothing had to reconcile them.** No owner sits above them, neither authority was told what the other decided, and no part of the system had to hold both answers at once. Add a third owner, or a thousandth, the same way. |
| 6 | **Both portals**<br>Settings → Security → Agent Authorization | Two ledgers, and neither mentions the other. Carol's records a grant she allowed. Alice's records a refusal she made. **Same agent in both, and each account of it is only its own owner's.** |
