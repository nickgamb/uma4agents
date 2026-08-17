# Start here

You are in a Codespace with the whole lab ready to run. Nothing to install.

The premise: **Alice's money sits at a brokerage. Bob's AI agent wants at it.
Alice is asleep.** You will play both sides — the agent from this terminal,
Alice from her portal — and watch her policy decide without her.

## Watch it first, if you like

[![The lab running in a Codespace: the cluster comes up, Alice signs in, an agent is refused and then admitted, and a trade waits for her tap](screenshots/codespace-demo-poster.png)](screenshots/codespace-demo.mp4)

Two and a half minutes of exactly what follows. *(Click through for the
video — GitHub only plays videos it hosts itself, so from the repo page this
is a still that opens the file.)*

---

The **k8s-topology** tab beside this one is what you are about to build:
one namespace per party, a mesh between them, and the authorization server
replicated behind a database. Worth thirty seconds now — the namespaces in
it are the ones `kubectl get pods -A` will show you.

## 1. Bring it up — about 13 minutes

```bash
make kind-up
```

A three-node Kubernetes cluster, one namespace per party, a service mesh
between them. Most of the time is image pulls.

Notice there is no `make init` and no certificate on your machine —
cert-manager issues the lab's CA inside the cluster.

## 2. Open Alice's portal and sign in

Do this before running anything else — the whole point is watching her decide,
and you cannot watch if you are not looking.

Her portal is already published; `make kind-up` did it. Open the **PORTS** tab
beside this terminal, find **Alice's portal** on 9010, and use its
open-in-browser action. Sign in as **alice / alice-demo**.

The URL is predictable if you would rather type it:
`https://<codespace-name>-9010.app.github.dev`. If the port ever stops
answering — a rollout replaces the pod the forward was attached to — run
`make codespaces-web` to republish it.

> The forwarded ports stay **private**, which is what you want: this lab ships
> fixed development credentials, and a public port would put them on the
> internet behind nothing but an unguessable URL. Private ports open fine in
> your own browser because you are already signed in to GitHub.

Keep that tab where you can see it.

## 3. Let the agent in — approve the connection

```bash
make k8s-demo-all ACT=tier1 SIM=0
```

Bob's agent asks for Alice's holdings. Her terms would permit that on their
own, but this agent has **no standing relationship with her yet**, and a
first contact pends regardless of how permissive the tier is. Nothing about
the request is wrong; she has simply never met it.

**Go to her portal and approve it.** Then watch the terminal: the agent was
holding its ticket the whole time, and the grant is issued the moment she
taps.

That connection is now standing. The next request from this agent will not
ask her again — which is exactly what makes the next step mean something.

> `SIM=0` leaves the tap to you. `SIM=1` taps for you and is how the headless
> runs work, but it also means nothing ever appears in her portal.
>
> **Do not leave it sitting.** The agent gives up after a couple of minutes
> and the run ends with `grant denied: timed out waiting for the owner` —
> which is correct behaviour, not a failure, but it is not what you came to
> see.

## 4. Now the one she has to answer for — a trade

```bash
make k8s-demo-all ACT=tier3 SIM=0
```

Same agent, same standing connection, and this time she is asked anyway.
Her policy puts trades on an ask-me tier: the connection got the agent
through the door, and it still cannot move her money without her.

Approve it in the portal, and notice what the agent receives — a grant
**bound to that one order**. Not "may trade". The epilogue in the terminal
proves it by replaying the same token and being refused.

## 5. Read what actually happened

```bash
make k8s-audit
```

The ledger, in three columns: what the agent **promised** (the signed terms,
hash and all), what Alice **personally approved**, and what was actually
**touched** — every row correlated by its negotiation id.

> Reading raw pod logs instead will mislead you. The authorization server
> runs **three replicas**, so `kubectl logs deploy/uma-as` shows one of them
> and the events of a single negotiation are spread across all three. The
> audit target is a projection over the whole stream, which is why it exists.

## 6. Check the boundary holds

```bash
make k8s-smoke-test     # expect 13 passed, 0 failed
make k8s-policy-test    # expect 11 passed, 0 failed
```

Eight of those eleven are **refusals**. A policy suite that only proves the
allows would pass on a cluster with no policy at all.

## 7. Bring your own agent

Everything so far has been Bob's agent — one requesting party among however
many there turn out to be. Point **your own** at the same vault and Alice
treats it as what it is: a stranger, like every agent before it and every one
after.

Run it from a terminal **in this Codespace**. The lab answers to
`gateway.uma.lab` only from inside this machine, so an agent on your laptop
cannot reach it.

```bash
make k8s-trust-ca      # exports the cluster's CA to /tmp/u4a-k8s-ca.pem
```

Then point any MCP client at the shim — it is a plain stdio MCP server, so
whatever launches MCP servers for your agent will launch this:

```json
{
  "mcpServers": {
    "alice-vault": {
      "command": "uv",
      "args": [
        "run", "--with", "mcp>=2,<3", "--with", "httpx", "--with", "pyjwt[crypto]",
        "python", "/workspaces/uma4agents/clients/agent-shim/shim.py"
      ],
      "env": {
        "PYTHONPATH": "/workspaces/uma4agents/lib",
        "UMA4A_CACERT": "/tmp/u4a-k8s-ca.pem"
      }
    }
  }
}
```

Ask it *"what's in Alice's portfolio?"* and watch what happens: it is
challenged, it signs her terms, and then it **pends** — because a pseudonymous
agent is its key, your agent's key is not Bob's, and Alice has never met it.
Approve it in her portal and it appears beside his in **Connected Agents**,
with its own terms, its own trail, and its own revoke button.

Notice what she did **not** have to do: add you to anything. Her tiers are
written against resources — which tools, what terms, whether she must tap —
and name no agent at all. That is what makes this scale past Bob to an
unbounded number of strangers: one policy, written once, and everyone
negotiates against it.

Run the shim again with a different `UMA4A_KEYSTORE` and you get a third
agent, a fourth, as many as you like — each pending on first contact, each
with its own terms, trail and revoke button.

Full detail, including what changes between MCP clients, is in
[clients/agent-shim/README.md](clients/agent-shim/README.md).

## 8. Say something about the agent, without naming one

Everything so far treated every agent alike. Her policy can also read what her
authority was able to *establish* about the one asking — and the rules she
writes for that still name no agent, so they hold for the next stranger too.

```bash
make k8s-assurance-check
```

Watch what it proves. Two agents identical but for a metadata document saying
who operates them: the accountable one goes quiet on its second request, the
nameless one asks her every time. An agent whose claimed operator does not
resolve gains nothing by claiming it. And a flood of anonymous agents is capped
without reaching either the agent she already knows **or a newcomer whose
operator can be named** — because her attention is the one resource here that
was previously unbounded, and the agent you want to let in is a stranger too
the first time.

It also blocks an operator: one action shuts out every agent that operator
runs and revokes what is already connected, instead of revoking them one at a
time. Which is what the lane split is for — it makes a flood attributable, and
an attributable flood is one she can answer in a single click.

The rule the first part reads is one line, and it names no agent:

```json
{"when": ["assurance.accountability_below:1"], "then": "ask"}
```

**She writes these in her portal**, under Settings → Security → Agent
Authorization → My Terms — as sentences, not JSON. That page is also where she
adds terms of her own: a new tier over any resource her authority protects that
no tier governs yet.

The rule engine has unit tests that need nothing running:

```bash
make rules-test
```

Why an agent can never buy access by showing more, only avoid friction it would
otherwise have cost, is [docs/ASSURANCE.md](docs/ASSURANCE.md).

## 9. Give Alice her own AI

Everything so far had Alice answering from a browser. She does not have to.
The side that decides is an authority and a way to reach her, and both can sit
on a machine of hers — so the lab also runs **Kwaai's pAI-OS**, with a U4A
ability installed, holding her key.

```bash
make k8s-paios          # her personal AI starts answering
make k8s-paios-check
```

It answers the tiers she has given standing consent to, and Bob's agent gets
its grant without her being disturbed. What it will **not** do is answer a
trade: pAI-OS gives an ability no way to reach its person, so anything on an
ask-me tier is refused and logged. That refusal is the interesting result, and
the open question we are taking to Kwaai.

```bash
make k8s-paios-down     # hand the decisions back to her portal
```

This does not replace the portal demo — it is a second surface onto the same
decisions, and a decision made by either lands in the same ledger. While her
personal AI is up, requests it can answer never reach her portal, which is
exactly what you would want and worth noticing during a demo.
[docs/DEMOS.md](docs/DEMOS.md) has both, side by side.

## 10. Try to break it

```bash
make k8s-chaos
```

Puts a request in front of Alice, deletes the authorization server that
accepted it, kills the database primary, waits for failover, then has her
answer *that same request*. Not a fresh one.

## Where to read more

- **[docs/DEMOS.md](docs/DEMOS.md)** — the two demos, her portal and her
  personal AI, and when to reach for which
- **[docs/ASSURANCE.md](docs/ASSURANCE.md)** — what her policy may say about
  an agent, why it starts at zero, and the cap on her attention
- **[docs/KUBERNETES.md](docs/KUBERNETES.md)** — the same walkthrough with
  what to notice at each step, plus the five traps this deployment hit
- **[docs/PROTOCOL.md](docs/PROTOCOL.md)** — the wire contract, and where
  this profile deviates from UMA 2.0 and why
- **[FINDINGS.md](FINDINGS.md)** — the recommendations to the spec authors,
  each backed by something in here that runs

## When you are done

**Closing the browser tab does not stop it.** The Codespace keeps running
until it idles out, and a stopped Codespace still bills storage. To actually
finish:

- **Stop it** (keeps your work, stops burning compute hours) —
  Command Palette (`F1`) → *Codespaces: Stop Current Codespace*
- **Delete it** (nothing here is worth keeping; the lab rebuilds from the
  repo in thirteen minutes) — <https://github.com/codespaces> → the `...`
  menu beside this Codespace → *Delete*

From your own machine, `gh codespace list` shows what you have running, and
`gh codespace delete -c <name>` removes one.

The machine this lab asks for is a 2× tier, so it spends the free monthly
allowance about twice as fast as the smallest one — roughly 60 hours a month
on a free account. Worth deleting rather than leaving idle.
