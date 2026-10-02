---
templateKey: doc
title: "Demo: the firm's book"
seoTitle: "Demo an organization sharing a resource a member administers"
description: Northwind shares part of its book with a member under a role — she administers it at her own authority, and only while she is a member.
next:
  - title: Two owners, one account
    to: /docs/guides/demo-joint-account/
  - title: Shared ownership
    to: /docs/overview/shared-ownership/
---

Northwind shares part of its book with Alice under a role. She administers it at
her own authority, and only for as long as she is a member.

**Left screen** — Terminal, `~/uma4agents`
**Right screen** — her portal and the firm's console, `portal.uma.lab` and
`org-console.uma.lab`

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

Open her portal at `https://portal.uma.lab` (**alice** / **alice-demo**) and the
administrator's console at `https://org-console.uma.lab` (**dana** /
**dana-demo**).

**In a Codespace.** Only steps 2 and 4. No resolver to edit, no CA to trust —
`kind-up` publishes the portal for you. To republish it later:

```bash
make codespaces-web
```

**Running it again.** Rewinds her ledger; her membership is what step 1
re-establishes.

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
ANTHROPIC_MODEL=claude-sonnet-5 make kagent
OPENAI_MODEL=gpt-4o make kagent MODEL=openai
```

A model in the cluster instead:

```bash
make kagent MODEL=ollama
```

## The run-through

Her portal and the firm's console, side by side. Step 1 is what brings the
resource into existence, so it cannot be skipped or pre-baked.

**0 · Terminal.** Show the whole lab first. `northwind` is the firm: an
authority and a console of its own, in its own namespace. It is not above her
authority in `alice` — by the end you will have shown that it cannot answer for
her.

```bash
make k8s-status
```

**1 · Her portal — Agent Access → Organization.** Alice joins Northwind, and has
to agree to do it. The preview shows what the role would give her and what the
firm would require. Her authority **refuses a join without the tick** and records
what she agreed to, because this changes the bargain rather than a setting.

```
Enrolment code:  NW-7K2F-QX
```

**2 · Her portal — the same page.** *Joining grants something.* The firm's book
is now in her authority, marked shared. It was not there a minute ago. **She
administers it; she does not own it** — and her portal says which, because the
difference decides what happens when she leaves.

**3 · Terminal.** Point an agent at the firm's book. **That resource did not
exist until step 1.** Its published metadata names *her* authority, not
Northwind's: the firm holds the book and enforces the charter, and still cannot
answer a request about it.

```bash
make kagent RESOURCE=shared
```

**4 · Terminal** — *shared · analyst role.* It stops — and it stops at her
portal. A request about the firm's asset, waiting on a member's decision, at the
member's own authorization server.

```bash
make kagent-ask RESOURCE=shared Q="What is in the firm's book?" SIM=0
```

**5 · Her portal — Approve.** *Held for her.* She allows it: NWCF, NWEQ, TLT,
VNQ. The firm's book — **not her portfolio**. Her own account was never in scope
for this agent, and the role is what drew that line.

**6 · The console — Groups · Charter → Rules.** The charter's two halves, on two
pages. **Groups** is what a member gets and agrees to; saving one publishes a
charter version, because it changes the bargain. **Charter → Rules** is what the
firm enforces operationally, in Rego, and it can only refuse or interrupt —
never grant, and never answer for her. The test for which page a rule belongs
on: *is it part of what a member is shown, and agrees to, when she joins?* A
new charter version applies to existing members when it is published; her
authority re-applies the ceiling and records the version.

**7 · Her portal — Organization → Leave.** *Taken back.* Run step 4 again:
refused, and the resource is gone. **Leaving takes back exactly what joining
gave**, and nothing of hers goes with it — her own account, her tiers and her
ledger are untouched. What the firm shared was never hers to keep, which is the
whole difference between a resource of hers and a resource of theirs.
