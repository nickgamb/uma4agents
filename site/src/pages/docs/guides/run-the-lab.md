---
templateKey: doc
title: Run the lab
description: A three-node deployment with one command, then the sequence that shows an owner deciding while she is the only one who can.
next:
  - title: Choose an enforcement point
    to: /docs/guides/enforcement-point/
    blurb: Start building your own version of what you just watched.
  - title: Deploy it at scale
    to: /docs/guides/at-scale/
    blurb: What the deployed shape proves that a laptop cannot.
---

Two ways to run it. The Kubernetes path is the interesting one, and it needs
nothing installed if you run it in a browser.

## In a Codespace

[Open the repository in a Codespace](https://codespaces.new/nickgamb/uma4agents?devcontainer_path=.devcontainer%2Fdevcontainer.json).
The toolchain is present, `*.uma.lab` already resolves, and the walkthrough
opens beside a terminal.

Measured on the machine the devcontainer requests — 4 cores, 15 GB RAM, 32 GB
disk:

| | |
|---|---|
| `make kind-up`, cold | 13 minutes |
| Memory once up | 6.3 GB of 15 |
| Disk once up | 13 GB of 32 |

That machine is a 2× Codespaces tier, so it spends the monthly allowance at
twice the rate of the smallest one.

## On your own machine

```bash
git clone https://github.com/nickgamb/uma4agents
cd uma4agents
brew install kind helm      # docker and kubectl come with Docker Desktop
make dns-setup              # one sudo, so *.uma.lab resolves in a browser
make kind-up
```

There is no `make init` on this path and no certificate on your machine —
cert-manager issues the lab's CA inside the cluster and trust-manager copies it
into every namespace.

The compose stack is the faster alternative if you only want to read the
protocol: `make init && make up`. It runs the same code without a cluster.

## Prove it works

```bash
make k8s-smoke-test
```

Expect **13 passed, 0 failed**. Fewer usually means something is still
settling — wait a minute and run it again.

```bash
make k8s-policy-test
```

Expect **11 passed, 0 failed**, and note that eight of them are *refusals*. The
sharpest pair is two assertions against the same port on the same workload:

```
ok   the enforcement point cannot read Alice's policy      403
ok   the enforcement point can reach her published keys    200
```

That pair is the entire cross-principal argument, expressed as something CI can
fail on. A policy suite that only proved the allows would pass on a cluster with
no policy at all.

## Watch an owner decide

Open Alice's portal first, and keep it visible. In a Codespace, `make kind-up`
has already published it — find **Alice's portal** on 9010 in the **PORTS** tab.
Locally it is `https://portal.uma.lab`. Sign in as `alice` / `alice-demo`.

![Alice's holdings in the lab's portal — a fictional brokerage called Meridian
Wealth, with her positions and an Agent Access section in the
sidebar.](/img/docs/portal-holdings.png)

Meridian is her brokerage, not her authority. Everything the agent negotiates
for lives here; everything that decides lives under **Agent Access**.

**Let the agent in.**

```bash
make k8s-demo-all ACT=tier1 SIM=0
```

Bob's agent asks for holdings. Her terms would permit it, but this agent has no
standing relationship with her, and a first contact pends whatever the tier.
Approve it in her portal and watch the terminal — the agent held its ticket the
whole time, and the grant issues the moment she taps.

**Then the one she has to answer for.**

```bash
make k8s-demo-all ACT=tier3 SIM=0
```

Same agent, same standing connection, asked again — because her policy puts
trades on an ask-me tier. Approve it, and notice what the agent receives: a
grant bound to that one order. The epilogue proves it by replaying the same
token and being refused.

> `SIM=1` taps for her, which is how the headless runs work. It also means
> nothing reaches her portal, so use `SIM=0` when you want to see the point. If
> she does not answer within a couple of minutes the run ends with `grant
> denied: timed out waiting for the owner`, which is correct rather than broken.

## Read what happened

```bash
make k8s-audit
```

Three columns: what the agent **promised**, what she **personally approved**,
what was actually **touched**, correlated by negotiation id.

Read the pod logs directly and you will be misled. The authorization server runs
three replicas, so `kubectl logs deploy/uma-as` shows one of them and a single
negotiation's events are spread across all three.

## Give her a personal AI instead

Everything above had Alice answering from a browser. She does not have to. The
lab also runs **Kwaai's pAI-OS**, with a U4A ability installed, holding her key.

```bash
make k8s-paios          # or `make paios` on the compose path
make k8s-paios-check
make k8s-paios-down     # hand the decisions back to her portal
```

It answers the tiers she gave standing consent to, and Bob's agent gets its
grant without her being disturbed. What it will **not** do is answer a trade:
pAI-OS gives an ability no channel to reach its person, so anything on an ask-me
tier is refused and logged. That refusal is the interesting result, and it is
the subject of [Put the authority on her
device](/docs/guides/personal-authority/).

This is a second surface, not a replacement — both demos are worth running.
While her personal AI is up, the requests it can answer never reach her portal,
which is exactly what you would want and worth noticing. It starts stopped for
that reason.

## Break it

```bash
make k8s-chaos
```

Puts a request in front of her, deletes the authorization server that accepted
it, kills the database primary, waits for failover, then has her answer *that
same request*. Expect **5 passed**.

Starting a fresh negotiation afterwards would prove the lab still works, which
is not the question.
