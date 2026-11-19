---
templateKey: doc
title: "Demo: her own agent"
seoTitle: "Demo a first-party agent held to the same ceiling as a stranger"
description: One rule, one tier, two agents — hers goes through without waking her, and one that is not hers is asked anyway.
next:
  - title: Her personal AI
    to: /docs/guides/demo-personal-ai/
  - title: Her own agent
    to: /docs/overview/first-party/
---

One rule, one tier, two agents. Hers goes through without waking her; one that
is not hers is asked anyway.

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

Open `https://portal.uma.lab` on the right and log in as **alice** /
**alice-demo**.

**In a Codespace.** Only steps 2 and 4. No resolver to edit, no CA to trust —
`kind-up` publishes the portal for you. To republish it later:

```bash
make codespaces-web
```

**Running it again.** No reset needed. Fresh keys each run, and the demo claims
and publishes what it needs at the start — then puts her tier-3 rule back.

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

The whole card turns on a contrast. Steps 4 and 5 are the same tier under the
same rule, so run them back to back and let the room hear the difference.

**0 · Terminal.** Show the whole lab first. Note that `sterling-vance` is Bob's
namespace and `alice` is hers. By the end, an agent in each will have asked her
authority for the same thing.

```bash
make k8s-status
```

**1 · Her portal — Settings → Security → Agent Authorization → Operators.**
Alice claims an origin as hers. This is half a decision and the portal treats it
as half. **Anybody may point an agent at her origin** — a metadata document only
proves it came from the URL it names. The other half is that **only she can put
a key in her directory**, and her authority checks for both.

```
https://alice-agent.uma.lab
```

**2 · Her portal — My Terms → Trade execution → add rule.** One rule, on the
tier she cares most about. **The rule names no agent.** It does not list a key,
a vendor or a product — only that the thing asking is hers. She is describing a
relationship, and anything that enters or leaves it is covered without her
editing this again.

```
When:  the agent is one of mine
Then:  allow without asking me
```

**3 · Terminal.** Bring up an agent she operates. As it starts, the adapter
publishes its signing key in her directory and names her origin as its client
id — the second half from step 1, done the only way it can be done.

```bash
make kagent RESOURCE=hers
```

**4 · Terminal** — *through · no approval.* The trade goes through and she is
never asked. **Watch the right screen while this runs and say what is not
happening.** Her portal does not move. No badge, no queue, no tap. The next step
is the same rule and the same tier, so make them notice this one.

```bash
make kagent-ask RESOURCE=hers Q="Sell 100 shares of my AAPL position." SIM=0
```

**5 · Terminal** — *tier 3 · trade execution.* Now Bob's agent asks for exactly
the same thing. It is attested too — a real operator, a published key, a signed
request. It is simply **not hers**, so her rule does not reach it and the
request stops.

```bash
make kagent-ask Q="Sell 100 shares of her AAPL position." SIM=0
```

**6 · Her portal — Approve or Deny.** *Held for her.* She is asked, exactly like
anybody else. Either answer makes the point, so take whichever the room wants.
**Being hers bought less friction and no more access.** Her tier is the ceiling
in both directions; the only thing that moved was whether she had to be woken.

**7 · Her portal — Operators → Disclaim.** *Taken back.* She un-claims the
origin, then re-run step 4. Her own agent is asked now, like a stranger, with no
change to the agent at all. **What made it hers was her say-so, and it was hers
to withdraw** — which is the difference between a relationship and a credential.
