---
templateKey: doc
title: "Demo: what an operation leaves behind"
seoTitle: "Demo a policy rule that names the act rather than the tool"
description: She replaces a rule that names a tool with one that names the act, and it holds for tools she has never seen.
next:
  - title: What an operation leaves behind
    to: /docs/overview/consequence/
  - title: Alice to Bob
    to: /docs/guides/demo-alice-to-bob/
---

She stops naming tools and starts naming the act.

**Left screen** — Terminal, `~/uma4agents`
**Right screen** — Alice's portal, `https://portal.uma.lab`

## Pre-demo setup

From cold to ready. Three commands on a Mac, one in a Codespace, about 15
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
`kind-up`. In a Codespace run `make codespaces-web` instead.

```bash
make k8s-trust-ca
sudo security add-trusted-cert -d -r trustRoot \
  -k /Library/Keychains/System.keychain /tmp/u4a-k8s-ca.pem
```

Then open `https://portal.uma.lab` on the right screen and log in as **alice** /
**alice-demo**.

**Running it again.** Rewinds her ledger and her connections.

```bash
make k8s-reset
```

## The run-through

Step 1 is the one the room came for: she deletes a rule that names a tool and
writes one that names the act.

**0 · Portal — Settings › Security › Agent Authorization.** Find **Trade
execution**. *Ask me every time* is on, because somebody decided once that this
tool was the dangerous one. It is a list of tool names, kept by hand.

**1 · Portal — turn it off, add a rule, Save changes.** The rule is *if it
cannot be undone at all — ask me first*. Then try the same condition with *grant
without asking*. Her authority will not save it: reading what an act costs can
raise what a request needs, never lower it.

**2 · Terminal.** Bob's agent asks for her holdings and stops. She has never met
it, so this is first contact rather than the new rule. **Approve it on the
right.**

```bash
make k8s-demo ACT=tier1
```

**3 · Terminal — watch the right screen.** The same read, now that she knows the
agent. It goes straight through and nothing appears in her portal. The vault
publishes that reading holdings is `reversible`.

```bash
make k8s-demo ACT=tier1
```

**4 · Terminal — watch it.** The agent asks to place a trade, and it stops.
Nobody added the trade endpoint to a list.

```bash
make k8s-demo ACT=tier3
```

**5 · Portal — open the request.** Under **Why you**: *it cannot be undone at
all*. That is the rule she wrote, reading what the vault published about its own
operation. **Approve.**

**6 · Terminal.** The trade completes, and the promise on her record carries the
class alongside the tier and the operation.

```bash
make k8s-audit
```

**7 · Terminal — if there is time.** Twenty-two assertions over the same path:
the class is inside the signature on the resource's metadata, it reaches her
registry by a pull, and a resource that re-declares an operation cannot spend a
grant she issued against the old claim.

```bash
make k8s-consequence-check
```

## FAQs

**Who decides the class?** The resource server, in the metadata it signs. It is
the party that would have to undo the act. An agent's description of itself
stays display-only for the opposite reason.

**What about tools nobody has described?** Undeclared is unknown. A rule about
remedy does not fire on it, and she has a separate condition — *nobody has said
whether it can be undone* — if she wants those refused too.

**Is this a risk score?** No. The classes order by how much remedy remains, not
by how bad the outcome is. A reversible act can still be catastrophic while it
stands, and nothing here adds the classes up.

**Can a resource lie?** Claiming an act is worse than it is costs it friction.
Claiming it is better buys nothing: the class is published in metadata the
resource signs, and the grant records the class it was issued against, so a
later re-declaration cannot spend a grant given under the old one.

**Does the agent see it?** Yes, in the refusal. The challenge carries the class,
so an agent learns what it is asking for before it negotiates.
