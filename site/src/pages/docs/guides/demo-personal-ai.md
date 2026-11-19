---
templateKey: doc
title: "Demo: her personal AI"
seoTitle: "Demo standing consent answering for an owner who is asleep"
description: pAI-OS holding her key and answering from standing consent, until the one thing it has no way to ask her about.
next:
  - title: The firm's book
    to: /docs/guides/demo-the-firms-book/
  - title: Put the authority on her device
    to: /docs/guides/personal-authority/
---

Kwaai's pAI-OS, holding her key and answering from standing consent — until the
one thing it has no way to ask her about.

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
**alice-demo**. Leave it on her pending queue — half this demo is about what
never lands there.

**In a Codespace.** Only steps 2 and 4. No resolver to edit, no CA to trust —
`kind-up` publishes the portal for you. To republish it later:

```bash
make codespaces-web
```

**Put it back.** Hands every decision back to her portal. Run it before demoing
any of the other cards.

```bash
make k8s-paios-down
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

Her portal stays on screen throughout, and for most of this demo nothing lands
in it. Point at the empty queue — that is the result.

**0 · Terminal.** Show the whole lab first. `paios` sits in **her** namespace,
beside her authority and her portal — not in Bob's, and not in Meridian's. It is
another way of reaching her, not another way around her.

```bash
make k8s-status
```

**1 · Terminal** — *held for her.* Start with the ordinary shape: she is asked.
Approve it in her portal. Do this first so the room has seen a normal request
land before it stops landing.

```bash
make kagent-ask Q="What is in Alice's portfolio?" SIM=0
```

**2 · Terminal.** Her personal AI starts answering. It holds her key and her
standing consent, authenticates to her authority with an RFC 9421 signature
rather than a browser session — **it is her, arriving a different way** — and
her policy still decides.

```bash
make k8s-paios
```

**3 · Terminal** — *through · no approval.* Answered in seconds, and her portal
never moves. **Point at the empty queue on the right.** The log still prints
*Alice has been asked* — she was — and the answer came back from standing
consent she gave ahead of time. She is asleep, and this is what "she is not
woken" looks like from the other side.

```bash
make kagent-ask Q="Show me her transaction history and cost basis." SIM=0
```

**4 · Terminal** — *refused.* The trade is refused, not answered and not held.
Her AI has no channel to wake her, so it will not guess on her behalf: it
records *no channel to her* and stops. **Standing consent is not a stand-in for
her.** The surface that cannot ask her is the surface that says no.

```bash
make kagent-ask Q="Sell 100 shares of her AAPL position." SIM=0
```

**5 · Terminal.** Hand the decisions back. Nothing is rebuilt and nothing is
lost. Her portal is the surface again.

```bash
make k8s-paios-down
```

**6 · Portal — Approve or Deny.** *Held for her.* Run step 4 again — now it
waits for her. Same protocol, same tier, same request. A different surface is
answering, and the one that can reach her is the one allowed to decide this.
**Both surfaces doing the part each can do**, and neither pretending to be the
other.

**7 · Portal — Settings → Security → Agent Authorization.** One ledger, both
surfaces. The grant her AI made and the one she made herself sit in the same
record, against the same agent, correlated to the same negotiation. **Her ledger
does not distinguish them, and it should not** — both were her.
