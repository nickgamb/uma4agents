---
templateKey: doc
title: "Demo: sub-agent grants"
seoTitle: "Demo sub-agent delegation where every worker gets its own grant"
description: An agent spawns workers, and each one is authorized on its own — until one press takes the whole fleet away.
next:
  - title: Her own agent
    to: /docs/guides/demo-her-own-agent/
  - title: Sub-agent grants
    to: /docs/overview/subagent-grants/
---

An agent spawns workers. None of them carry its key, and each one is authorized
on its own.

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

Then open `https://portal.uma.lab` on the right screen and log in as **alice** /
**alice-demo**.

**In a Codespace.** Only steps 2 and 4. No resolver to edit, no CA to trust —
`kind-up` publishes the portal for you. To republish it later:

```bash
make codespaces-web
```

**Running it again.** No reset needed. The workers get a fresh key each run,
which is what makes them different agents — revocation is permanent on purpose.

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

Steps 3 and 5 are the two the room came for: a worker nobody approved going
straight through, and one press taking the whole fleet away. Everything else is
there so those two land.

**0 · Terminal.** Show the whole lab first. `sterling-vance` is Bob's
namespace. Everything that happens in it today is one firm's agents talking to
each other — and none of it changes what Alice's authority, over in `alice`,
will agree to.

```bash
make k8s-status
```

**1 · Terminal.** An orchestrator asks for her transaction history. It stops.
She has never met it, so nothing happens until she says so — the same first
contact as any other agent. **Watch the badge on the right.**

```bash
make k8s-subagent-demo
```

**2 · Portal — Approve, twice.** She admits it, then approves the tier. Two
taps, and this is the **only** place in the whole demo she is asked about this
fleet. Everything after this is what those two taps did and did not buy.

**3 · Terminal — watch it.** It spawns a worker, and the worker gets in without
waking her. **Point at the right screen and say what is not happening.** No
badge, no queue, no tap. Then say the part that matters: **the worker did not
get the parent's token.** It has its own key, it agreed to her terms itself,
and it holds a grant of its own that she can take away on its own.

**4 · Portal — Settings → Security → Agent Authorization.** One row per agent,
and each says who introduced it. **Not one blurred row.** She can see the
fleet, and she could revoke any single worker without touching the rest.

**5 · Terminal — watch it.** A worker asks to trade, and it stops. Nobody in
this fleet has ever been approved to trade, so it waits for her exactly as the
orchestrator would have. **The ceiling is not something she configured — it is
what a tier is.**

**6 · Portal — Approve.** She approves the worker, and the orchestrator
inherits it. The next thing the **parent** asks to trade goes straight through.
**She said yes to the fleet, not to a key** — and it ran upward, from the worker
to the agent that spawned it, because they are one relationship.

**7 · Portal — Revoke, on the orchestrator.** The toast says how many workers
went with it. **One press.** Their grants stop on the next call, not when they
expire, because the enforcement point asks her authority every single time. And
its sponsor cannot let a revoked worker back in — otherwise Revoke would be a
suggestion.

## If they ask

**"So it's delegation."** No — nothing is passed down. The parent states a fact
about a key and confers nothing. Her authority decides what that fact is worth,
and the worker negotiates for itself.

**"What stops a worker spawning workers?"** An agent that was itself introduced
may not introduce. The authority graph is one level deep, whatever the task
graph does. That is a check, not a hope.

**"Can they just spawn a thousand?"** There is a hard fan-out ceiling, and
sub-agents count against her attention budget like anybody else. She can also
say *ask me about every sub-agent, every time* — one of the three things her
terms can say here.

**"Who says it's really a sub-agent?"** Her authority checks it, and never takes
the claim's word. Both keys have to be published by one operator, in a directory
the agents cannot write to. For an agent with a real identity it is better
still: its own issuer names the parent, in AAuth's `act` claim.

**"Does this work with our stack?"** The lab runs stock kagent over A2A,
unmodified. Nothing in the agent framework knows what any of this is — the
enforcement happens at the resource, not in the agent.
