---
templateKey: blog-post
title: "Everything You Need to Know About Deploying U4A at Scale"
date: 2026-08-12T00:00:00.000Z
author: Nick Gamb
description: "A field guide to running owner-authoritative authorization for real: how it differs from the policy engine you already run, the parts list, the five things that will bite you, a complete Kubernetes reference architecture on the solo.io stack — and an honest list of what it does not solve yet."
featuredpost: true
featuredimage: /img/blog/u4a-at-scale.svg
category: Agentic Identity
tags:
  - Agentic Identity
  - UMA
  - U4A
  - Kubernetes
  - Authorization
---

So you read [the first post](/blog/2026-08-06-let-them-a-developers-guide-to-u4a/), ran the lab, watched an agent get told *no* by a resource server and then talked into a *yes* by its owner's terms — and now you are wondering what it takes to run that somewhere that matters.

Good. That is the interesting question, and it has a specific answer.

This is a field guide. The mental model first, then the parts list, then the five things that will bite you, then a complete reference architecture you can clone and steal from. Everything here is running code: a three-node Kubernetes cluster, the solo.io stack, and a set of tests that try to prove the whole thing wrong.

![The reference architecture](/img/blog/u4a-at-scale.svg)

## First, what "at scale" actually means here

Not requests per second. You are not going to melt an authorization server; the grant loop is four messages and most of them happen once per relationship, not once per call.

What scale means for owner-authoritative authorization is **more than one of the thing that decides**. The moment there are two authorization servers behind one address, a set of assumptions you did not know you were making stop being true. That is the whole game, and it is why this post exists.

Here is the honest framing: a single-process authorization server is a *correct* implementation of UMA that quietly relies on a property nothing wrote down. Deploying it is not a devops chore you do after the interesting work. It is where you find out which of your invariants were real.

The good news is that there are about five of them, they are all fixable, and once you know what they are you will spot them in your own design in an afternoon.

## How this differs from the policy engine you already run

Fair question to ask early, because you probably already deploy authorization at scale and it works.

If you run [OPA](https://www.openpolicyagent.org) or [Cedar](https://www.cedarpolicy.com), you have decentralized *where the decision is computed* — the policy travels to the enforcement point instead of every call travelling to a central service. If you are following [AuthZEN](https://openid.net/wg/authzen/), you are standardizing *how the decision is asked for*, so a PEP and a PDP from different vendors can talk. Both are real wins and neither is what this is.

None of them change **whose policy the decision expresses**. In each, the policy is authored by whoever operates the service — which is correct, because in the workloads those tools were built for the operator *is* the party with the authority to decide.

UMA's move, and it predates every tool in that list, is to break that identification. The resource server holds the assets and does the enforcing, and the policy it enforces belongs to someone else — someone who may be asleep, and who does not work there. That is not a different policy language. It is a different answer to *who is allowed to author the policy at all*, and it is why the sections below are about namespaces and mesh identity rather than about rule syntax. It is also why the thing you can't do with an engine alone is the negotiation: [GNAP](https://datatracker.ietf.org/doc/html/rfc9635) and UMA both have one, because when the deciding party isn't in the request path you need a protocol for reaching them, not just an API for asking.

You will likely want a policy engine *inside* the authorization server described here. The two compose. They answer different questions.

## Start with the parties, not the pods

The single most useful thing you can do before writing a manifest is stop thinking about services and start thinking about **parties**.

[FedAuthz](https://docs.kantarainitiative.org/uma/wg/rec-oauth-uma-federated-authz-2.0.html) §1.4 — the resource-server half of UMA — divides responsibility between the resource **owner**, the resource **server**, and the **authorization server**. Not between processes. Between parties, which may be different companies with different lawyers: the resource server's job there is a short list it performs *for* an authority it does not hold, starting with holding a PAT issued in the owner's name (§1.5).

That distinction is easy to lose. In a single-process lab everything shares a network and the seam survives only as a paragraph in an architecture document. So make it structural: **one namespace per party**, one service account per workload, and a mesh that gives each of them a cryptographic identity rather than an IP address.

For the reference architecture that shakes out as:

| Party | What lives there | Why it is separate |
|---|---|---|
| The owner | her authorization server, her identity provider, her portal | she decides |
| The resource server | the gateway, the enforcement point, the actual resource | it enforces, and must never be able to read her policy |
| The requesting party | its **requesting agent**, and its operator's public metadata | it asks, and gets no shortcut |
| The identity authority | whatever attests the agent | neither side owns it |
| The edge | your ingress | everything from outside arrives here |

The one to look at twice is the middle row. Your resource server holds the assets and does the enforcing — and it should be structurally incapable of reading or rewriting the policy it enforces. In a mesh that is not a code review comment, it is a rule, and you can write a test that proves it.

The row below it is worth a word on vocabulary, because the agent era makes an old distinction matter again. The **requesting party** is the human or organization asking — Bob, the advisor. The **requesting agent** is the software doing the asking on his behalf. UMA's 2010 drafts had both terms and 2.0 collapsed them, which was reasonable when the client was a web app Bob was sitting in front of. It is not reasonable now: the terms get signed by the agent, the identity being attested is the agent's, and the party who is accountable is Bob. Keep them separate in your model even if your spec of choice does not.

**Try this on your own architecture right now:** name the four parties. If two of them turn out to be the same deployment, you have found the thing to separate first.

## Your parts list

You do not need all of this. You need something in each of these roles, and here is what we used and why.

**An agent-facing gateway that speaks the protocol your agents speak.** We used [agentgateway](https://agentgateway.dev), because it already speaks MCP and can call out to an external authorization service before letting a tool call through. That callout is the whole enforcement story: your gateway asks a service "may this?" and does what it is told.

**An edge.** [kgateway](https://kgateway.dev) handles north-south, terminates TLS for your public names, and routes to whichever party owns each hostname. Running two Gateway API implementations in one cluster is completely fine and honestly clarifying — the edge and the agent-facing gateway are different jobs with different owners.

**Something that makes your resources first-class.** This is the piece I would push hardest. [kmcp](https://kagent.dev) turns an MCP server into an `MCPServer` resource, so the thing being protected is a *declaration* rather than a Deployment you hand-wrote. U4A's big transformation of UMA's resource model is that durable resources become **tool surfaces**; an `MCPServer` is exactly that, as an object your cluster understands. And the server itself contains no authorization code at all, which is the point.

**Workload identity.** [Istio ambient](https://istio.io/latest/docs/ambient/overview/) gives every workload a SPIFFE identity and mutual TLS with no sidecars — which is what lets your resource stay an unmodified MCP server and still be inside the mesh. Sidecar-per-pod would have meant touching every workload to protect any of them.

**A real database for grant state.** We used [CloudNativePG](https://cloudnative-pg.io). This is not "we needed persistence." It is that the guarantees are not *some rows*: a ticket is spent once, a per-operation grant is burned once, and a revocation must not be visible to one replica and invisible to another.

A note on that last choice, because people ask. We used Postgres rather than a cache, and the reason is that every hard requirement here is one statement you can read aloud — a conditional update, an atomic delete, a publish/subscribe for the owner's live feed — with durability for the audit ledger thrown in. A cache gets you the same atomicity through scripting gymnastics and adds a second stateful thing to explain to whoever is on call. Nothing in this workload is hot enough to need a cache tier in front of a database, and noticing that is part of the job.

## The five things that will bite you

Here they are, in the order they will hurt.

### 1. Single-use has to mean indivisible

UMA 2.0 §3.3.1 requires the authorization server to invalidate a permission ticket when it is used, handing back a fresh one if the negotiation continues. This profile adds a second single-use artifact — an operation-bound token, the thing that stops "approve this trade" from becoming "may trade."

Neither the spec nor your first implementation will say *how* "once" is enforced, because in one process the question is invisible. Read the flag, decide, write the flag; nothing can interleave.

Ours looked like this, and it was correct:

```python
claims, rec, err = _decode_rpt(token)   # read
if err:
    return {"consumed": False, "error": err}
rec["consumed"] = True                  # write
```

Correct *because* a single asyncio event loop never yields between those two lines. That is a property of the deployment, not of the design. Add a second replica and two callers present the same approved trade to two different servers, both read `false`, both write `true`, and both are told yes. The trade runs twice and nothing logs an error.

The fix is not clever:

```sql
UPDATE rpts SET consumed = true
 WHERE jti = $1 AND consumed = false
RETURNING family;
```

Zero rows means you lost the race, which means you deny.

**What to do in your own code:** design the *interface*, not the storage. Our first sketch was `get(key)` / `put(key, value)`, which is exactly wrong — it preserves the check-then-act shape and just moves the race onto the network. Every method that guards a single-use thing should be an **intent** that decides and records in one step and tells the caller whether it won. `consume_ticket`. `consume_rpt`. `decide`. Not `get` and `set`.

Once you have that lens, you will find siblings. We found two immediately: revoking a resource server flipped a status that every Protection API call reads, and revoking a connection burned live tokens in a second step that could fail independently — leaving the agent holding exactly the authority the owner just withdrew.

### 2. Never take authorization inputs from the transport

Your enforcement point rebuilds a signature base to verify proof-of-possession. Where does it get the authority — the hostname the client claims to have signed?

If your answer is "the `Host` header," you have a bug that is both a security bug and a portability bug.

The security half is obvious once said: an authority taken from a header is an authority an attacker can set. The portability half is the one that surprised us. Moving the enforcement point from a file-driven gateway to a Kubernetes-native one, everything survived — the request body, the signature headers, the path rewrite, even the rewrite expression character for character. Exactly one thing did not: `Host` arrives as the *authorization service's own address*, and no configuration changes that.

We never noticed, because the enforcer had always taken the authority from configuration:

```python
# No `authority` here on purpose: the RFC 9421 base is reconstructed from
# the enforcer's *configured* expected_authority, never from the request
```

A decision made for signature correctness turned out to be the decision that made the whole component portable. An implementation that read the transport would have broken silently, with signatures failing to verify for a reason nothing in the logs would name.

**The rule:** authorization inputs come from your configuration and from the credential. Never from the layer that delivered the request.

*A related one, free of charge:* when your gateway buffers a request body for the authorization callout, find out what it does when the body is too big. Ours **truncates and forwards** rather than refusing — despite documentation saying otherwise. A cut-off JSON-RPC body does not parse, so the tool name vanishes from a call that was merely padded. Deny-by-default caught it, but reported "unknown method," which sends you looking in the wrong place. Check for the truncation flag and fail closed *on purpose*.

### 3. Do not gate liveness on an exchange that loops back to you

This one is sneaky and it applies to far more than U4A.

In a pull-style profile, the authorization server fetches what the resource server publishes — and the resource server authenticates that fetch by retrieving the authorization server's published keys, mid-request. The pull is a **cycle**.

Now write the obvious readiness probe: *my registry is populated.*

Congratulations, you have built a deadlock. Readiness gates traffic, so the server has no ready endpoints, so the back-call has nowhere to land, so the pull fails, so readiness never goes green. What you see is a healthy-looking pod stuck at `0/1` for two minutes and then one quiet log line.

**The rule:** if two parties authenticate each other by dereference, neither one's liveness may depend on the exchange completing. Point your probes at something local. Expose "has the pull landed" as a *separate* endpoint for your waits and dashboards — it is a genuinely useful signal and a terrible probe.

### 4. Your policies are exactly as good as their selectors

This is where a service mesh will make you feel clever and then make you feel foolish, usually in the same afternoon. Four ways we got it wrong, each of which fails by pointing somewhere other than the cause:

**A policy that selects nothing protects nothing — and looks identical to one that does.** We wrote the vault's policy using the label convention its neighbours used. The controller that created the vault used the Kubernetes-recommended keys instead. Zero pods matched. The policy was accepted, displayed in `kubectl get`, and enforcing absolutely nothing.

**A path rule bound to a workload is not a path rule.** In ambient mode a policy with a workload selector is evaluated at L4, and L4 cannot read a path — so rather than falling back to permit, it denies. Every call returns 403 and your gateway says only "external authorization failed," which is a true statement about the wrong question. Path rules bind to the *service*.

**A gateway addresses endpoints, not services.** So its traffic sails straight past a service-scoped L7 proxy. Ours had to be workload-scoped. Until we worked that out we had a policy that was visibly correct and visibly not applying.

**Behind an L7 proxy, the second hop carries the proxy's identity.** Not the caller's. Without a rule naming the proxy, everything is refused *after* the policy meant to permit it already said yes — a 503, with nothing denied in any log, because from the proxy's point of view nothing was.

And a fifth we did not find by reading: **a principals rule silently excludes anything outside the mesh.** Our database operator was named correctly, and its namespace was not enrolled, so its traffic arrived with no identity and the rule could never match. The database kept serving and quietly lost the ability to fail over. Invisible until the day it matters.

### 5. Test the refusals, not the permissions

A policy suite that only proves the allows will pass on a cluster with **no policy at all**. Think about that for a second, then go look at your own.

The suite worth writing asserts the denials. From the requesting party's namespace: cannot reach the owner's authorization server, cannot reach the resource directly, cannot read the owner's policy, cannot call the enforcement callout, cannot reach the database. Then the two things that must stay open: public discovery, and a tool call that gets *challenged* rather than refused outright.

The sharpest one in ours is a pair:

```
ok   the enforcement point cannot read Alice's policy      403
ok   the enforcement point can reach her published keys    200
```

Same port. Same workload. Different path. That single pair is the entire cross-principal argument, expressed as something CI can fail on.

## Then try to break it on purpose

The premise of this whole design is that the owner may be asleep for hours. In a single-process lab that is a claim about the protocol. Once you deploy, it is a claim about your system — and a claim about a system is worth exactly what you have done to falsify it.

So we wrote a target that puts a request in front of the owner, deletes the authorization server that accepted it, kills the database primary, waits for a standby to take over, and then has her answer **that same request**. Not a fresh one. Starting a new negotiation would prove the lab still works, which is not the question.

```bash
make k8s-chaos
```

It found a real bug on its first run: the authorization server exited if the database was unreachable at startup. Which sounds fine until you notice that a replicated database is unreachable for a few seconds *every time it fails over* — so a routine promotion became a crash loop that outlived the outage by minutes. Retry your connection pool.

If you build one thing from this post that is not a manifest, build this.

## Run the reference

Everything above is in the repo, and it comes up with one command.

```bash
git clone https://github.com/nickgamb/uma4agents
cd uma4agents
brew install kind helm     # docker and kubectl come with Docker Desktop
make dns-setup             # one sudo, so *.uma.lab resolves in a browser
make kind-up               # ~10 minutes, mostly image pulls
```

Notice what is *not* in there: no `mkcert`, no `openssl`, no certificate on your machine. The cluster issues its own certificate authority and distributes it to every namespace at the same path the compose stack uses — so no application code knows which shape it is running in. That property is worth stealing on its own.

Then:

```bash
make k8s-smoke-test    # 13 checks, including "all three replicas sign with one key"
make k8s-demo-all      # the owner's whole day, from the requesting party's namespace
make k8s-policy-test   # 11 checks — eight of them refusals
make k8s-load          # 24 agents at once; exactly one presentation wins
make k8s-chaos         # break it while she is being asked
```

There is a fifteen-minute walkthrough in [docs/KUBERNETES.md](https://github.com/nickgamb/uma4agents/blob/main/docs/KUBERNETES.md) — every step a command, an expected number, and what to notice in the output. Bring a coffee.

## What this does not answer yet

Worth being straight about, because the gaps are as informative as the fixes and you will hit them in roughly this order.

**One authorization server per resource server.** RFC 9728 makes `authorization_servers` an array, and the lab configures exactly one. The resource server is genuinely multi-owner — Alice's holdings sit beside other people's — but every one of those owners is pointed at the same authorization server. The case that actually tests the model is owners who each brought their own, and that is a discovery-and-trust problem this deployment does not solve.

**No key rotation.** The signing key is minted once by a Job and mounted to all three replicas. Publishing a `jwks_uri` makes rotation *possible* — serve both keys, sign with the new one, retire the old after the longest token lifetime — but nothing here exercises it, and a rotation that races a replica rollout is its own small nightmare.

**Any issuer is a trusted issuer.** The authorization server resolves an agent token's issuer by dereferencing whatever `https` origin the token names and believing the keys it publishes. TLS is the trust root, which is AAuth's own precondition, and for a lab that is the honest default. A real deployment needs a policy about *which* issuers may attest agents to it. That policy is not a protocol gap; it is the deployment decision the protocol leaves you.

**Revocation is correct because there is one store.** Every replica reads the same database, so a revoked connection is revoked everywhere the instant it commits. Stretch that across regions or across authorization servers and you are back to a distributed-systems problem the shape of this profile does not itself solve.

## Take this, not that

**Do not copy the manifests.** They are a reference for one shape of one lab, and yours will be different — different gateway, different mesh, maybe no mesh at all.

Copy the four ideas:

1. **Model parties, not services.** Then make the boundary something your infrastructure enforces rather than something your documentation asserts.
2. **Make single-use indivisible at the storage layer**, and express it as an intent that reports who won.
3. **Take authorization inputs from configuration and the credential, never from the transport.** You get portability for free.
4. **Write the test that proves the refusals**, and a chaos target that attacks the one property your design is really claiming.

Here is the thing I keep coming back to. Almost everything that broke when we deployed was something the specification never had to say, because when it was written an authorization server was one process. That assumption is everywhere and undocumented, and the agent era is about to run into it at volume — because "an agent you have never met asks your resource server for something" is a workload that arrives in parallel by definition.

The protocol was the interesting part last time. This time the interesting part is that the protocol survives being deployed properly, and the places where it needs help are small, specific, and now written down.

---

*U4A is [open source under Apache 2.0](https://github.com/nickgamb/uma4agents). [FINDINGS.md](https://github.com/nickgamb/uma4agents/blob/main/FINDINGS.md) carries the recommendations to spec authors, each backed by running code — including the atomicity one above, which exists because we deployed it.*
