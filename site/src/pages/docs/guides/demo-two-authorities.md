---
templateKey: doc
title: "Demo: two owners, two authorities"
seoTitle: "Demo two owners answering the same agent differently"
description: One agent, one key, two owners — opposite answers, and nothing anywhere reconciling them.
next:
  - title: The firm's book
    to: /docs/guides/demo-the-firms-book/
  - title: Many owners, one resource server
    to: /docs/overview/multi-owner/
---

One agent, one key, two owners. They give opposite answers and nothing anywhere
has to reconcile them.

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
`https://carol-portal.uma.lab` (**carol** / **carol-demo**) side by side.

**In a Codespace.** Only steps 2 and 4. No resolver to edit, no CA to trust —
`kind-up` publishes the portal for you. To republish it later:

```bash
make codespaces-web
```

**Running it again.** No reset needed — a fresh agent key each run, so both
owners are always asked.

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

Two portals on the right. Answer the two requests differently — the
disagreement is the demo, and it is the part no other model of this can do.

**0 · Terminal.** Show the whole lab first. Two things to point at: `alice` and
`carol` are separate namespaces with a `uma-as` each. Two authorities, not one
server with two rows in a table.

```bash
make k8s-status
```

**1 · Terminal.** Point an agent at Carol's account. Meridian holds her account
and Alice's. Carol runs her own authorization server, her own signing key, her
own identity provider — **she is not a tenant of Alice's**.

```bash
make kagent RESOURCE=carol
```

**2 · Terminal** — *tier 1 · holdings.* Read the challenge line out loud. It
names `carol-as.uma.lab`. Nothing in the agent picked that — **the resource
published which authority speaks for it**, which is the only reason an owner
gets to choose one at all.

```bash
make kagent-ask RESOURCE=carol Q="What is in Carol's portfolio?" SIM=0
```

**3 · Carol's portal — Approve.** *Held for her.* Carol allows it: SCHD, IEFA,
TLT. Her holdings, from her vault, under terms she wrote. Alice has no part in
this and never hears about it.

**4 · Terminal.** Same agent, same key, same tool — different owner. The only
thing that changed is whose resource is being asked about. This time the
challenge names `alice-as.uma.lab`.

```bash
make kagent-ask Q="What is in Alice's portfolio?" SIM=0
```

**5 · Alice's portal — Deny.** *Refused.* Alice refuses the identical request.
**They disagreed, and nothing had to reconcile them.** No owner sits above them,
neither authority was told what the other decided, and no part of the system had
to hold both answers at once. Add a third owner, or a thousandth, the same way.

**6 · Both portals — Settings → Security → Agent Authorization.** Two ledgers,
and neither mentions the other. Carol's records a grant she allowed. Alice's
records a refusal she made. **Same agent in both, and each account of it is only
its own owner's.**
