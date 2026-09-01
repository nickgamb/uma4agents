---
templateKey: doc
title: "Demo: The firm's book"
seoTitle: "Demo an organization sharing a resource a member administers"
description: A resource that exists in a member's authority only while she is a member.
next:
  - title: Two owners, one account
    to: /docs/guides/demo-joint-account/
  - title: Shared ownership
    to: /docs/overview/shared-ownership/
---

**Left screen** — Terminal, `~/Documents/Github/uma4agents`  
**Right screen** — Her portal + the console, `portal.uma.lab · org-console.uma.lab`

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
| 0 | **Terminal**<br>`make k8s-status` | Show the whole lab first. `northwind` is the firm: an authority and a console of its own, in its own namespace. It is not above her authority in `alice` — by the end you will have shown that it cannot answer for her. |
| 1 | **Her portal**<br>Agent Access → Organization<br>`Enrolment code:  NW-7K2F-QX` | Alice joins Northwind, and has to agree to do it. The preview shows what the role would give her and what the firm would require. Her authority **refuses a join without the tick** and records what she agreed to, because this changes the bargain rather than a setting. |
| 2 | **Her portal**<br>Agent Access → Organization | Joining grants something The firm's book is now in her authority, marked shared. It was not there a minute ago. **She administers it; she does not own it** — and her portal says which, because the difference decides what happens when she leaves. |
| 3 | **Terminal**<br>`make kagent RESOURCE=shared` | Point an agent at the firm's book. **That resource did not exist until step 1.** Its published metadata names *her* authority, not Northwind's: the firm holds the book and enforces the charter, and still cannot answer a request about it. |
| 4 | **Terminal**<br>`make kagent-ask RESOURCE=shared Q="What is in the firm's book?" SIM=0` | Shared · analyst role It stops — and it stops at her portal. A request about the firm's asset, waiting on a member's decision, at the member's own authorization server. |
| 5 | **Her portal**<br>Approve | Held for her She allows it: NWCF, NWEQ, TLT, VNQ. The firm's book — **not her portfolio**. Her own account was never in scope for this agent, and the role is what drew that line. |
| 6 | **The console**<br>Groups · Charter → Rules | The charter's two halves, on two pages. **Groups** is what a member gets and agrees to; saving one publishes a charter version, because it changes the bargain. **Charter → Rules** is what the firm enforces operationally, in Rego, and it can only refuse or interrupt — never grant, and never answer for her. The test for which page a rule belongs on: *would a member have to agree to it again?* |
| 7 | **Her portal**<br>Organization → Leave | Taken back Run step 4 again: refused, and the resource is gone. **Leaving takes back exactly what joining gave**, and nothing of hers goes with it — her own account, her tiers and her ledger are untouched. What the firm shared was never hers to keep, which is the whole difference between a resource of hers and a resource of theirs. |
