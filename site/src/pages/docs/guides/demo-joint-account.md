---
templateKey: doc
title: "Demo: Two owners, one account"
seoTitle: "Demo a jointly held account neither owner can release alone"
description: A joint account where both holders are asked and either can stop it.
next:
  - title: Two owners, two authorities
    to: /docs/guides/demo-two-authorities/
  - title: Joint ownership
    to: /docs/overview/joint-ownership/
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
| 0 | **Terminal**<br>`make k8s-status` | Show the whole lab first. Every party in its own namespace. Point out `tally`: it is its own party, it owns nothing, and it is about to be the thing neither owner has to trust. |
| 1 | **Alice's portal**<br>Agent Access → Joint accounts<br>`Where it is counted:  https://joint-tally.uma.lab`<br>`Account:              meridian-joint`<br>→ See what this commits you to | She reads the deal before she agrees to it. It names **Carol** as the other holder and says *"Every holder has to allow a request. Any one of you can stop it."* Tick the box and **Join**. Her authority refuses a join without that tick, and records what she agreed to. |
| 2 | **Carol's portal**<br>Agent Access → Joint accounts<br>`Where it is counted:  https://joint-tally.uma.lab`<br>`Account:              meridian-joint` | Carol does the same at her own authority. Two people, two authorities, one account. **Neither was enrolled by the other naming her** — being a co-owner is something you agree to, not something done to you. |
| 3 | **Both portals**<br>My Terms → new tier<br>`ALICE                              CAROL`<br>`Name it:      Joint - Alice        Joint - Carol`<br>`Governs:      meridian-joint       meridian-joint`<br>`Expires after: 3600                900`<br>`Prohibited:   model-training       resale-to-third-parties` | Each writes her own terms, at her own authority. Alice is looser on every field on purpose, so that **every narrowing you see in step 7 came from Carol**. Terms over something held jointly get a tier of their own — one edit here would change what the other holder's agents are held to. |
| 4 | **Terminal**<br>`make kagent RESOURCE=joint` | Point Bob's agent at the joint account. Nothing about the agent is joint-aware. The resource publishes its own authority, so **it finds out it needs two people by asking**, not by being configured. |
| 5 | **Terminal**<br>`make kagent-ask RESOURCE=joint Q="What is in the joint account?" SIM=0` | Held jointly · all of 2 It stops, and two portals light up. One question, asked of one agent, has become a decision waiting on two different people at two different authorities. |
| 6 | **Alice's portal**<br>Approve | One of two Alice says yes and nothing happens. Let it sit for a beat. The terminal is still waiting. **One holder is not a decision**, and there is no majority to round up to. |
| 7 | **Carol's portal**<br>Approve | Both · granted Now it completes: VTSAX, VBTLX, MMDA. Read the folded document out of the log — **900 seconds** (Carol's, the shorter), **positions:read only** (all they both offer), and **both prohibitions**. One agreement, made of two people's terms. The grant carries a signed verdict from each, and the gateway re-ran the count itself before letting it through — so a tally that invented a yes dies at the door. |
| 8 | **Terminal**<br>`make kagent-ask RESOURCE=joint Q="Sell 400 shares of VTSAX from the joint account." SIM=0` | Now ask it to move their money. Both are asked again. Nothing was carried over from last time — the previous grant was spent. |
| 9 | **Carol's portal**<br>Deny | Refused Carol refuses, and it is over immediately. **Alice is never asked.** Under a mandate that needs everybody, one refusal settles it and nobody waits for the rest — which is also why the tally cannot stall a decision by sitting on it. |
