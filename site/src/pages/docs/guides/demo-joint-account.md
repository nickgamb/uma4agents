---
templateKey: doc
title: "Demo: two owners, one account"
seoTitle: "Demo a jointly held account neither owner can release alone"
description: An account Alice and Carol hold together, where an agent cannot get past either of them alone.
next:
  - title: Two owners, two authorities
    to: /docs/guides/demo-two-authorities/
  - title: Joint ownership
    to: /docs/overview/joint-ownership/
---

An account Alice and Carol hold together. Ask its agent a question and watch
neither of them be able to answer it alone.

**Left screen** — Terminal, `~/uma4agents`
**Right screen** — two portals, `portal.uma.lab` and `carol-portal.uma.lab`

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
trusts it locally so the portals load with no warning. Re-run after every
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

Open `https://portal.uma.lab` (**alice** / **alice-demo**) and
`https://carol-portal.uma.lab` (**carol** / **carol-demo**) side by side on the
right screen.

**In a Codespace.** Only steps 2 and 4. No resolver to edit, no CA to trust —
`kind-up` publishes the portal for you. To republish it later:

```bash
make codespaces-web
```

**Running it again.** No reset needed. A fresh agent key every run, so both
holders are always asked — and the demo puts the account back as it found it.

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

Two portals on the right, not one. Steps 1 to 3 are the two of them agreeing to
hold something together — do them live, they are half the point.

**0 · Terminal.** Show the whole lab first. Every party in its own namespace.
Point out `tally`: it is its own party, it owns nothing, and it is about to be
the thing neither owner has to trust.

```bash
make k8s-status
```

**1 · Alice's portal — Agent Access → Joint accounts.** She reads the deal
before she agrees to it. It names **Carol** as the other holder and says *"Every
holder has to allow a request. Any one of you can stop it."* Tick the box and
**Join**. Her authority refuses a join without that tick, and records what she
agreed to.

```
Where it is counted:  https://joint-tally.uma.lab
Account:              meridian-joint
```

Then **See what this commits you to**.

**2 · Carol's portal — Agent Access → Joint accounts.** Same two values. Two
people, two authorities, one account. **Neither was enrolled by the other naming
her** — being a co-owner is something you agree to, not something done to you.

**3 · Both portals — My Terms → new tier.** Each writes her own terms, at her
own authority. Alice is looser on every field on purpose, so that **every
narrowing you see in step 7 came from Carol**. Terms over something held jointly
get a tier of their own — one edit here would change what the other holder's
agents are held to.

```
              ALICE                 CAROL
Name it:      Joint - Alice         Joint - Carol
Governs:      meridian-joint        meridian-joint
Expires after: 3600                 900
Prohibited:   model-training        resale-to-third-parties
```

**4 · Terminal.** Point Bob's agent at the joint account. Nothing about the
agent is joint-aware. The resource publishes its own authority, so **it finds
out it needs two people by asking**, not by being configured.

```bash
make kagent RESOURCE=joint
```

**5 · Terminal** — *held jointly · all of 2.* It stops, and two portals light
up. One question, asked of one agent, has become a decision waiting on two
different people at two different authorities.

```bash
make kagent-ask RESOURCE=joint Q="What is in the joint account?" SIM=0
```

**6 · Alice's portal — Approve.** *One of two.* Alice says yes and nothing
happens. Let it sit for a beat. The terminal is still waiting. **One holder is
not a decision**, and there is no majority to round up to.

**7 · Carol's portal — Approve.** *Both · granted.* Now it completes: VTSAX,
VBTLX, MMDA. Read the folded document out of the log — **900 seconds** (Carol's,
the shorter), **positions:read only** (all they both offer), and **both
prohibitions**. One agreement, made of two people's terms. The grant carries a
signed verdict from each holder, and the enforcement point re-ran the count
itself before letting it through — so a tally that invented a yes dies at the
door.

**8 · Terminal.** Now ask it to move their money. Both are asked again. Nothing
was carried over from last time — the previous grant was spent.

```bash
make kagent-ask RESOURCE=joint Q="Sell 400 shares of VTSAX from the joint account." SIM=0
```

**9 · Carol's portal — Deny.** *Refused.* Carol refuses, and it is over
immediately. **Alice is never asked.** Under a mandate that needs everybody, one
refusal settles it and nobody waits for the rest — which is also why the tally
cannot stall a decision by sitting on it.
