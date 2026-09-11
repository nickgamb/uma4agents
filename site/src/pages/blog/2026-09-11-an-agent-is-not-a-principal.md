---
templateKey: blog-post
title: "An Agent Is Not a Principal"
date: 2026-09-11T00:00:00.000Z
author: Nick Gamb
description: "Agents spawn agents. The usual answer is for the parent to delegate what it was delegated — a category error, because the agent was never a principal. What to do instead, why the resource owner has to be the one deciding, and how to implement it."
featuredpost: true
featuredimage: /img/blog/subagent-two-ways.svg
category: Agentic Identity
tags:
  - Agentic Identity
  - UMA
  - U4A
  - Delegation
  - Authorization
---

A planner fans out to three researchers. A coding agent starts a test runner and a linter. A support agent hands a lookup to something cheaper and waits.

Spawning workers is the ordinary shape of agent software. So here is the question the person on the other end is actually asking:

> Your agent spawned three more. May they touch my account?

Most systems answer it by accident. The parent holds a credential, the worker needs one, so the parent gives the worker what it has — whole, or attenuated if the framework is careful. Nobody decided anything. The answer fell out of the plumbing.

## Delegation is the wrong tool for this

Delegation is a real and well-specified thing. A principal with authority hands some of it to another party under terms, and the receiving party can be held to those terms. It works because there is a principal at both ends: someone who *had* the authority, and someone who can be answerable for what they do with it.

An agent is not a principal. **Bob is.**

Bob is a person with a relationship to Alice, an employer, a contract, and a reputation. Bob delegates to an agent. That agent holds authority it never had on its own, lent to it for a task, and it is answerable for nothing — you cannot sanction it, it does not persist, it has no interests. It is software Bob is running.

So when that agent spawns a worker and hands over its credential, it is delegating a delegation. Look at what that actually asserts:

- **Authority the agent never owned is being re-lent.** Bob gave it to the agent, for the agent's task. Nothing in that transaction contemplated a second recipient.
- **The new holder was evaluated by nobody.** Alice evaluated Bob's agent. She has never heard of the worker — and neither has Bob's identity provider, because the worker came into existence after the last login.
- **The party who lives with the result was not in the room.** The resource is Alice's, and she is not in this transaction at all.

That gets waved through because it looks like an implementation detail. It is not. It is the moment access stops being traceable to a decision anyone made.

![Two columns. Handing down the parent's token: an orchestrator and three workers all carrying key K0 and the same grant, and an authorization server holding a single connection row — one row, four agents acting, none of them separately visible or revocable. Introducing the worker: the same orchestrator and three workers, each carrying its own key and its own grant, and an authorization server holding four rows, each of the three workers naming the agent that introduced it.](/img/blog/subagent-two-ways.svg)

The left column is not a logging problem. Alice cannot revoke one worker, because there is nothing to revoke that is not the parent. She cannot see that a fleet exists, so she cannot decide whether she wanted one. And every worker reaches wherever the parent reached, because it is carrying the parent's authority by construction.

Attenuating helps and does not fix it. [Attenuating Authorization Tokens for Agentic Delegation Chains](https://datatracker.ietf.org/doc/draft-niyikiza-oauth-attenuating-agent-tokens/) narrows what gets handed down, which is a real improvement on passing a credential unchanged. The shape is the same: something is still handed down, and the party who lives with the consequence still did not agree to it.

## Why Bob's identity provider cannot answer this

The reflex in enterprise identity is to reach for what already works: single sign-on, and the cross-app flows built on it. [Cross App Access](https://datatracker.ietf.org/doc/draft-ietf-oauth-identity-assertion-authz-grant/) is the good version — Bob's identity provider mints an assertion saying *this is Bob, acting through this application*, and the resource side exchanges it for a token.

That is excellent, and it answers a different question from the one on the table.

An enterprise identity provider has standing over the enterprise's own data. When Bob's employer owns the resource, an administrator consenting on the company's behalf **is** the right authority, and the whole flow is correct. Collapse the resource owner into the enterprise and everything works.

Alice is not an employee of Bob's firm. She is a customer of a brokerage and the account is hers. Bob's identity provider can assert who Bob is until it runs out of electricity; it has no standing to say whether Bob's agent — let alone a worker that agent spawned ninety seconds ago — may read her positions. No administrator anywhere can consent on her behalf.

That is the general case. The special case is the one where the two parties happen to be the same.

So an identity assertion is worth carrying, and it is evidence rather than permission. In U4A it arrives as a *claim* — something the requesting side presents to the owner's authority, which then decides — rather than as a grant type that produces an access token directly. Identity says who is asking. It never says yes.

## Nobody hands anything down

The alternative rule is one sentence:

> Every agent instance negotiates its own grant, for its own task, against the owner's terms.

No exception for workers, no inheritance, no tokens passed between processes. If four agents are going to touch Alice's account, her authorization server issues four grants, each bound to a different key, each recorded as its own relationship.

The obvious objection is cost. If every worker introduces itself from nothing, and first contact with a stranger is a question Alice answers, then spawning six workers asks her six times. She will turn that off within a day, and she would be right to.

So a worker needs to arrive as something other than a stranger — without arriving as the parent.

## Attest lineage, do not transfer authority

The parent signs a short statement: *this key belongs to a worker I spawned.*

It is not a token. It carries no scope, no tier, no expiry you can spend, no permission of any kind. Its `sub` is the [RFC 7638](https://www.rfc-editor.org/rfc/rfc7638.html) thumbprint of the worker's public key, its `aud` is the owner's authorization server, and it expires in five minutes. Presenting one buys a worker exactly one thing: it is not treated as a stranger. Everything after that — the terms, the tiers, the ceiling, the record — is what any other agent gets.

Two ways to say it, and the second is nicer if you have it.

**The parent signs an introduction.** A compact JWS, `typ: u4a-introduction-v1+jws`, which rides the worker's own contract.

**The issuer says it.** If the worker's identity comes from an issuer rather than a bare key, that issuer can name the parent in the worker's own credential using the `act` claim from [RFC 8693](https://www.rfc-editor.org/rfc/rfc8693.html#section-4.1), which exists to record delegation. [AAuth](https://datatracker.ietf.org/doc/draft-hardt-aauth-protocol/) carries `act` on its agent tokens, so the lineage rides the identity the worker already has: no second document, nothing new invented, and the authority reads a claim it has already verified.

Either way the direction is inverted. Nothing moves from parent to child. The parent makes a *claim about provenance*, the owner's authority *verifies it against its own records*, and the worker then asks for itself.

![Six numbered steps with the real message beside each: the 401 UMA challenge naming her authority and a ticket, the introduction JWS claims, the connection record her authority looks up, the sub-agent's own requesting party token with cnf bound to its own key rather than the parent's, the pend it gets when it reaches a tier the lineage never had, and the revoke response carrying the cascade counts.](/img/docs/subagent-grants-wire.svg)

## What the owner's authority checks

Six things. Five are what you would expect: the introducing agent is a live connection of hers, she personally approved it at something, the worker has no revoked record of its own, one operator published both keys, and the parent is not already at its fan-out limit.

The sixth is the one worth internalising:

> **An agent that was itself introduced may not introduce another.**

It is tempting to think this needs no check. An introduced worker starts with nothing the owner personally approved, and the second check requires exactly that — so a worker could never qualify as an introducer, and depth caps itself.

That reasoning fails. The moment Alice approves that worker at any tier, her approval is recorded against it and it satisfies the check. Depth would then be bounded by the order things happened to occur in, which is not a bound. So it is an explicit check, and the two graphs come apart: orchestrate as deep as you like, and the authority graph stays exactly one level deep.

## What Alice decides

**Whether a worker's arrival wakes her.** Per tier, in her own policy editor:

| | |
|---|---|
| **Per agent** | Every agent is asked about once per tier, workers included. The default; needs no rule. |
| **Lineage-wide** | Ask once per fleet instead of once per agent. |
| **Always ask about sub-agents** | Stricter than the default: an introduced agent is asked about every time, whatever its lineage earned. |

The middle one is easy to misread. It does not say *grant when the lineage is approved*. It is the ask she already had, narrowed to fire only while nothing in the lineage has been approved yet.

That distinction is load-bearing. In this profile a fact may only *lower* a requirement if it traces to a decision the owner personally made and the requesting side had no hand in producing. Which agents join a lineage is chosen by the operator running them — so if "the lineage is approved" could relax a rule, an operator could widen its own access by spawning. Written as a narrowed restriction, the requesting side can only ever cause the ask to remain. The rule engine refuses to store it the other way round, and the test suite asserts that refusal.

Approval also runs upward, which surprises people. Approve a *worker* at a tier the parent never reached and the parent stops being asked about that tier — one relationship, settled once. Revoke the member that earned it and the lineage loses it again.

**Where the ceiling is.** A tier the lineage was never approved for stops and asks her, for a worker exactly as for the parent. That is not configurable, and it is what makes the rest safe: the shortcut is only ever *skip first contact*, never *skip the owner*.

**How wide a fleet may get.** Fan-out — how many live workers one connection may put forward — is a deployment ceiling rather than one of her rules, and defaults to three.

## Taking it back

Revoking the parent revokes every agent it introduced, in the same operation, and the response says how many connections and how many live grants that came to. The parent goes first, so a negotiation arriving mid-cascade cannot find it still active and slip in behind it. Because depth is one, there is no recursion to do.

Each worker's live grant stops working on its next call rather than at its expiry, because the enforcement point introspects at her authority every time. One action, and no action per link.

## Tutorial: implementing sub-agent grants

The requesting side, end to end. This is the lab's client library; it runs.

**1 · Give every worker its own key.** This is the step people skip. A worker that shares the parent's key *is* the parent, and nothing downstream can undo that.

```python
from uma4a_grant import AgentKeys, sign_introduction, run_grant

parent = AgentKeys.load_or_create("/keys/orchestrator.pem")
worker = AgentKeys.load_or_create("/keys/worker-1.pem")
```

**2 · Mint an introduction naming the worker's key.** The parent signs it. Note what you cannot pass: no scope, no tier, no resource. There is nowhere to put them.

```python
intro = sign_introduction(parent, worker.thumbprint(), "https://alice-as.example")
```

`thumbprint()` is the worker's RFC 7638 JWK thumbprint — the same string the owner's authority will file the worker's connection under. `aud` pins the introduction to one authorization server, so one minted for Alice's is not replayable at Carol's, and it expires in five minutes by default.

**3 · Let the worker negotiate for itself, carrying the introduction.** The worker makes its own call, takes its own challenge, and signs its own contract with its own key; the introduction rides along as one more claim.

```python
from uma4a_grant import parse_challenge

refused = worker_calls_the_tool()                       # a 401 from the resource
ch = parse_challenge(refused.headers["www-authenticate"])

rpt = run_grant(client, ch.as_uri, ch.ticket, worker,
                approve_terms, introduction=intro)
```

What comes back is the worker's grant, confirmed to the worker's key. The parent's token is not involved and never was.

**4 · Handle the case where the shortcut does not apply.** This is what separates an implementation that works from one that works on a good day.

An introduction that fails as a *document* — wrong key, wrong audience, expired, oversized — is a bad request, and you should fix it. An introduction that is well formed but that the authority declines to act on is **not an error**: the worker falls back to being a stranger, and first contact goes to the owner exactly as if no introduction had been offered. Treat that as a normal outcome, because it is one. It happens the first time an orchestrator is approved at nothing, and every time a fleet outgrows its fan-out.

The refusals you will see, and what each means:

| What the authority says | What to do about it |
|---|---|
| `the introducing agent is not a connection of this owner` | The parent has never been approved here. Negotiate the parent's own grant first. |
| `the introducing agent's connection is not active` | The owner revoked the parent. Nothing to do — this is the system working. |
| `the introducing agent has nothing this owner approved in person` | The parent has been granted automatically but never personally approved. It cannot vouch for anyone yet. |
| `an agent that was itself introduced may not introduce another` | You are nesting. Have the top-level agent introduce the worker instead. |
| `this agent's connection was revoked and cannot be restored by an introduction` | The owner revoked this worker specifically. Do not retry with a fresh introduction. |
| `the two agents are not published by the same operator` | Both keys must appear in the same operator key directory, at the same origin. |
| `the introducing agent already has N sub-agents, which is the limit (M)` | The fan-out ceiling. Reap finished workers, or run fewer at once. |

**5 · If you are implementing the authority side**, the ordering is specified and it matters. Verify the document first — signature against the key in its own header, `aud`, expiry, and that `sub` matches the key that signed the contract it arrived on. Then decide admission against your own records. And write the worker's connection *after* every refusal gate you would apply to a first contact, never before: a blocked operator or an exhausted attention budget has to be able to stop a worker, and a record written early is a live relationship for a party you just refused.

[Agent Lineage](/spec/draft-gamb-uma4agents-lineage-00.html) §2 and §3 are the normative version of all of this, including the introduction's exact claims and the six checks in order.

## It is a draft — tell us what is wrong with it

Sub-agent grants are written up as [Agent Lineage](/spec/draft-gamb-uma4agents-lineage-00.html), one of the nine Internet-Drafts in the [U4A specification set](/docs/reference/specification/): a profile and extensions to [UMA 2.0](https://docs.kantarainitiative.org/uma/wg/rec-oauth-uma-grant-2.0.html), written from a working lab rather than ahead of one.

If you work on agent authorization, delegation chains, or anything downstream of *which party does this token actually represent*, we would like your reading — including the parts you think are wrong. [Open an issue](https://github.com/nickgamb/uma4agents/issues), or use the [contact form](/contact/).

## Run it

The quick path is the compose stack:

```bash
git clone https://github.com/nickgamb/uma4agents && cd uma4agents
make init && make up
make subagent-check
```

That is the whole sequence as twenty-one assertions: an orchestrator connecting, a worker admitted without waking her, a worker stopped at a tier the lineage never reached, approval flowing back up to the parent, every refusal in the table above, and the revocation cascade.

The one worth watching is [the sub-agent demo](/docs/guides/demo-subagent-grants/) — the three-node Kubernetes deployment with Alice's portal open beside the terminal, where the fleet arrives in her connection list one worker at a time and then leaves in a single press. [Run the lab](/docs/guides/run-the-lab/) is that deployment without the demo script.

`make introduction-test` is twenty-five more assertions over the introduction document and the admission decision on their own, with nothing running. It mints introductions with the client library and verifies them with the server module, so the two sides check each other rather than agreeing with themselves.

The mechanism, the wire payloads and the three postures are on [the sub-agent grants page](/docs/overview/subagent-grants/).
