# The lab on Kubernetes

The same source as the compose stack, deployed the way it would actually run:
each party in its own namespace, a service mesh between them, and the
authorization server replicated behind a database.

`make up` (compose) stays the fast path — ninety seconds, no cluster. This is
the second shape, and the fact that both run one codebase is itself the
finding: the grant layer does not care which it is in.

![Topology](k8s-topology.svg)

---

## Run it without installing anything

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/nickgamb/uma4agents?devcontainer_path=.devcontainer%2Fdevcontainer.json)

A Codespace gets the whole toolchain, `*.uma.lab` already in `/etc/hosts`, and
this guide open beside a terminal. Skip step 0 — `make dns-setup` and the
`brew install` are not needed there — and start at step 1.

Measured on the machine the devcontainer asks for (4 cores, 15 GB RAM, 32 GB
disk):

| | |
|---|---|
| `make kind-up`, cold | **13 minutes** |
| Memory in use once up | 6.3 GB of 15 |
| Disk in use once up | 13 GB of 32 |
| `make k8s-smoke-test` | 13 passed, 0 failed |
| `make k8s-policy-test` | 11 passed, 0 failed |

That machine is a 2× tier, so it spends the monthly Codespaces allowance at
twice the rate of the smallest one — about 60 hours a month on a free
account. Stop the Codespace when you are done rather than leaving it idle.

Alice's portal is published automatically by `make kind-up` when it runs in
a Codespace. Reach it from the **PORTS** tab beside the terminal —
**Alice's portal** on 9010, with an open-in-browser action. To republish it
after a rollout replaces the pod behind the forward:

```bash
make codespaces-web
```

Then open it from the **PORTS** tab beside the terminal — **Alice's portal**
on 9010, with an open-in-browser action. That tab is the reliable way in; it
lists whatever is listening. The URL is also printed by the command, and is
derived from the Codespace name, so it is predictable:
`https://<codespace-name>-9010.app.github.dev`.

Sign in as `alice` / `alice-demo`.

The ports stay **private**, which is what you want: this lab ships fixed
development credentials, and a public port puts them on the internet behind
nothing but an unguessable URL. Private ports open fine in your own browser
because you are already signed in to GitHub.

The lab routes by hostname under `*.uma.lab`, which your browser cannot
resolve from outside the VM, so this forwards her portal and her identity
provider directly and rewrites the three OIDC origins that would otherwise
still name `keycloak.uma.lab`. Her browser session never crosses the
enforcement point either way, so nothing being demonstrated is bypassed.

---

## Demo guide

Fifteen minutes, start to finish. Everything below is copy-paste.

### 0. Once per machine — local only, skip in a Codespace

```bash
brew install kind helm          # docker + kubectl come with Docker Desktop
make dns-setup                  # one sudo, for *.uma.lab in a browser
```

### 1. Bring it up (~10 min, mostly image pulls)

```bash
make down                       # compose and kind both want :443 and :53
make kind-up
```

**Notice:** no `make init`. No mkcert, no openssl, no certificate on your
machine — cert-manager issues the lab CA inside the cluster and trust-manager
copies it into every namespace.

### 2. Prove it works

```bash
make k8s-smoke-test             # expect 13 passed, 0 failed
```

**Notice** the last three checks. They are the ones compose cannot ask: all
three replicas of the authorization server sign with **one key**, and Bob's
namespace **cannot reach** Alice's side or the vault.

### 3. Walk Alice's day

```bash
make k8s-demo-all               # expect PASS, four acts
```

**Notice** in the output:

| Look for | What it means |
|---|---|
| `challenged: 401 … ticket tkt_…` | Beat 1. The vault refused and issued a ticket. |
| `challenge corroborated` | The agent checked the challenge against published metadata rather than trusting it. |
| `terms proffered: …` | Beat 2. Alice's server dictated terms; she is not online. |
| `Alice has been asked — holding the ticket` | Tier 3 pends. Pending is a protocol state, not an error. |
| `single-use grant is consumed` | The same grant, replayed, is refused. |
| `revocation is terminal` | She revoked; it is not an invitation to re-negotiate. |

### 4. See it in a browser

```bash
make k8s-trust-ca               # prints the one command for a green padlock
open https://portal.uma.lab     # alice / alice-demo
```

**Click:** Settings → Security → Agent Authorization.
**Notice:** connected agents, what each promised, what it touched, and the one
action she personally approved. **Click** Revoke on the agent — then re-run
`make k8s-demo-all` and watch it be refused.

### 5. The part that needs a cluster

```bash
make k8s-policy-test            # expect 11 passed, 0 failed
```

**Notice** the eight refusals. A policy suite that only proves the allows
passes on a cluster with no policy at all. The sharpest line:

```
ok   cannot read Alice's policy
```

The enforcement point **can** reach `/jwks` on that same port and workload,
and is refused `/owner/*`. Same service, different path — that is what the
waypoint is for.

```bash
make k8s-load                   # 24 agents at once; expect 3 passed
```

**Notice:** `exactly one presentation is answered (1 of 16)`. Sixteen threads
present the same ticket to three different servers. One wins.

```bash
make k8s-chaos                  # ~5 min; expect 5 passed
```

**Notice** the order of events: a request is waiting for Alice, the
authorization server that took it is **deleted**, the database primary is
**killed**, a standby takes over — and she still answers *that same request*.

### 6. What her policy may say about the agent asking

```bash
make k8s-assurance-check        # expect 20 passed
make rules-test                 # the rule engine alone; nothing need be running
```

**Notice** that the two agents differ only in whether a metadata document says
who operates them, and that the difference shows up on the *second* request:
the accountable one is granted quietly, the nameless one asks her again. And
that the flood at the end is capped at five waiting without reaching either the
established agent or a newcomer whose operator can be named. Strangers queue by
lane, because the agent you want to let in is a stranger too the first time.

Her rules are editable in the portal under **My Terms**, as sentences. The same
page adds terms of her own over any resource no tier governs yet.
[ASSURANCE.md](ASSURANCE.md) is the argument.

### 7. An agent framework nobody modified

```bash
make kagent                     # a model in the cluster; no account anywhere
make kagent-check
make kagent-ask Q="..." SIM=0   # your question; SIM=0 leaves it to her portal
make kagent-down
```

**Notice** what is doing the asking: [kagent](https://kagent.dev), which is not
ours and has never heard of UMA. It sees three ordinary MCP tools. Everything
that makes them reachable happens in the **adapter** beside it — the same shim
Bob runs next to Claude Code, started as a network service because an agent in
a cluster cannot spawn a subprocess on your laptop.

Check the claim without a model in the way:

```bash
make k8s-adapter-check          # expect 3 passed
```

`MODEL=anthropic` or `MODEL=openai` points the same Agent at a hosted model,
reading the key from your environment into a Secret. The U4A path is identical
either way — the model only decides which tool to call.
[ASSURANCE.md](ASSURANCE.md) still applies: kagent arrives a stranger and is
held like one. Full detail in [KAGENT.md](KAGENT.md).

### 8. Give Alice her own AI

```bash
make k8s-paios                  # Kwaai's pAI-OS, holding her key
make k8s-paios-check            # expect PASS
make k8s-paios-down             # hand the decisions back to her portal
```

A second surface onto her decisions, not a replacement for her portal — both
demos are worth showing, and [DEMOS.md](DEMOS.md) puts them side by side. It
runs in her namespace, behind the same waypoint, so the policy that protects
the owner API applies to it too.

**Notice** what it refuses. It answers the tiers she gave standing consent to
and never disturbs her; on an ask-me tier it **denies**, because pAI-OS gives
an ability no channel to reach its person. That is the open question in the
binding — see [KWAAI-BINDING.md](KWAAI-BINDING.md).

It starts at `replicas: 0` deliberately: while it is up, the requests it can
answer never reach her portal, and the portal demo is the default.

### 9. Look around

```bash
make k8s-status                 # what is running, per party
make k8s-audit                  # her ledger: promised / touched / approved
make k8s-reset                  # rewind the story, keep the cluster
make kind-down                  # delete everything
```

---

## The parties

| Namespace | Runs | Is |
|---|---|---|
| `uma-edge` | kgateway, hickory-dns | the public on-ramp |
| `alice` | keycloak, `uma-as` ×3, CNPG ×3, her portal | the resource owner |
| `meridian` | agentgateway, `uma-pep` ×2, the vault | the resource server |
| `sterling-vance` | agent-operator ×2, the agent | the requesting party |
| `aauth` | person-server | a third-party identity authority |
| `observability` | — | the operator plane |

FedAuthz §1.4 divides responsibility between **parties**, not processes. The
compose stack collapses all of them onto one Docker network, which is the
thing [ARCHITECTURE.md](ARCHITECTURE.md) argues against; here each is a
separate workload identity and the seam is enforced rather than described.

`alice` versus `meridian` is the one that carries the argument: Meridian holds
the assets and enforces the policy, and can never read it.

---

## Three things that are genuinely different here

**No certificates on your machine.** cert-manager mints the CA, trust-manager
distributes it to every namespace at the same path and under the same
environment variables compose uses (`UMA4A_CA_BUNDLE`, `SSL_CERT_FILE`). No
application code knows which shape it is running in.

**The authorization server is replicated for real.** Three of them, on a
synchronously-replicated Postgres, with one signing key in a Secret rather
than three minted per pod. This is what
[`services/uma-as/store.py`](../services/uma-as/store.py) was written for,
and why rec 9 in [FINDINGS.md](../FINDINGS.md) exists: single-use has to mean
*indivisible*, not merely once per process.

**The vault is a `MCPServer`.** kmcp turns it into a Deployment and a Service;
what a reader sees is a declaration of the thing being protected. That is what
"tool surfaces as registered resources" looks like when the cluster
understands the type.

---

## The split-horizon, and why the deployment depends on it

Alice's authorization server pulls its registry from the resource server's
*published* metadata — which means it dereferences `https://gateway.uma.lab/…`
**from inside the cluster**. It may not shortcut to a Service name: the
document it fetches has to be the one the public would get, verified against
the TLS name the public would see, or the pulled copy proves nothing about
what is published.

A CoreDNS rewrite sends every `*.uma.lab` query to the edge Gateway. TLS is
unaffected, and that is the property that makes it work: SNI and `Host` come
from the URL, not from the DNS answer.

Host-side, the same hickory-dns zone runs on a NodePort mapped to `:53`, so
`/etc/resolver/uma.lab` from `make dns-setup` keeps working and the Kubernetes
path introduces **no new host state**.

---

## Probes, and the deadlock they can cause

The obvious readiness signal for an authorization server in a pull profile is
"my registry is populated". It deadlocks.

The pull calls this server's own public hostname, which routes back to it for
a JWKS check. Gate readiness on the pull and the Service has no ready
endpoints, so the back-call fails, so the pull fails, so readiness never goes
green. What an operator sees is a healthy-looking pod stuck at `0/1` for two
minutes and then one quiet log line.

So `/health` is deliberately independent of the pull, and `/health/registry`
answers "has it landed" for `kubectl wait` and dashboards — **never** as a
probe. The asymmetry is the point.

---

## Six traps, each of which fails by pointing somewhere else

These cost real time. Each is commented where it bit.

**A kgateway `Gateway` ignores its `GatewayParameters`** without
`infrastructure.parametersRef`, and silently provisions a LoadBalancer on a
random port the host mapping never reaches.

**An `AuthorizationPolicy` with `selector` is enforced by ztunnel at L4.** One
naming an HTTP path must bind with `targetRefs` to the Service. Get it wrong
and ztunnel cannot evaluate the path, so it denies outright — every call 403,
and the gateway reports only "external authorization failed".

**A Gateway load-balances to endpoint addresses, not the Service VIP**, so its
traffic never passes a service-scoped waypoint. The waypoints here are
`waypoint-for: all`.

**Behind a waypoint, the second hop carries the waypoint's identity**, not the
caller's. Without a rule naming it, everything is refused *after* the policy
meant to permit it already said yes — a 503 with nothing denied in any log.

**A Service named `paios` breaks pAI-OS**, and every other workload that reads
an environment variable named after itself. Kubernetes injects legacy service
links — `PAIOS_PORT=tcp://10.96.x.x:8443` — into every pod in the namespace,
and pAI-OS parses `PAIOS_PORT` as an integer. It crash-loops on a value it
never set. `enableServiceLinks: false` is the fix and costs nothing.

**A namespace helm created is not in the mesh**, and a `principals` rule
cannot match a caller that has no identity. kagent's chart makes its own
namespace, so it misses the ambient label every namespace here gets from
`k8s/base/namespaces` — and the symptom is a connection reset with nothing
denied in any log, because ztunnel refused at L4 before the request existed.
This is the same shape as the CloudNativePG one below, met a second time from
a different direction: the rule was right and the caller was invisible to it.

And one more, found by `make k8s-chaos` rather than by reading: **a
`principals` rule silently excludes anything outside the mesh.** CloudNativePG's
operator was named correctly and `cnpg-system` was not enrolled, so its traffic
arrived with no identity at all. The database kept serving and quietly stopped
being able to fail over — invisible until the day it matters.

---

## Deliberately not here

**agentregistry.** This lab's discovery argument is that discovery is
owner-mediated: signed RFC 9728 metadata for public structure, and a protected
listing for owner-bound instances. A catalog listing "Alice's positions tool"
is the exact privacy leak `services/uma-pep/app.py` calls out.

**agentevals.** Nothing here is non-deterministic; these are conformance checks
with binary outcomes. It would earn a place if the kagent path became default.
