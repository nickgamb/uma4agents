---
templateKey: blog-post
title: "Let Them: A Developer's Guide to UMA for Agents"
date: 2026-08-06T00:00:00.000Z
author: Nick Gamb
description: "The industry is fighting over how agents prove who they are. That is the wrong fight. The question that decides whether an agent economy works is whether the owner of a resource can set the terms — and U4A is what that looks like in running code."
featuredpost: true
featuredimage: /img/blog/u4a-two-shapes.jpeg
category: Agentic Identity
tags:
  - Agentic Identity
  - UMA
  - U4A
  - MCP
  - Authorization
---

There is a fight happening right now over how AI agents should prove who they are. Centralized or decentralized. Ephemeral or enrolled. A new identity type in your IdP, or a cryptographic key that never touches one. Every vendor has a position, most of them have an acronym, and a good deal of the noise is non-human identity marketing wearing a new hat.

I want to make an argument that will sound like a dodge and is not: **let them.**

They want to use Okta for agent identity? Let them. They want AAuth? Let them. Ephemeral keys minted per session? Let them. Decentralized identifiers, verifiable credentials, a workload identity from their cloud provider? Let them.

I borrowed the framing from Mel Robbins, whose *Let Them Theory* is about the freedom you get when you stop trying to control what other people do. It applies almost too neatly to identity architecture. The energy going into controlling how someone else's agent attests itself is energy not going into the thing that actually protects you: **what happens when that agent shows up at your resource server and asks for something.**

That is the part you own. That is the part nobody is specifying.

## The gap: RqP ≠ RO

Here is the distinction the whole argument rests on, in the vocabulary UMA has used since 2015.

The **resource owner** (RO) is the person or organization whose stuff it is. The **requesting party** (RqP) is whoever is asking. In classic enterprise SSO these collapse into one another, because the employee asking for the file and the employer who owns the file are inside the same trust domain. One IdP. One policy home. One vendor.

An agent economy is not shaped like that.

Bob is a financial advisor. Alice is his client. Bob's firm runs an agent, and that agent wants to read Alice's holdings. Bob's employer federated Bob's identity. Bob's employer did not federate Alice. Alice does not work there. Alice has never heard of their IdP.

So when Bob's agent knocks on Alice's brokerage:

- **Who is the requesting party?** Bob, or his firm, or the agent acting for them.
- **Who is the resource owner?** Alice.
- **Whose authorization server decides?** This is the entire question.

Every agent-identity protocol on the table answers *"is this my agent doing my task?"* That is a real question and worth answering well. None of them answers *"may your agent touch my stuff?"* — because answering it requires an authority sitting on the owner's side of the line, and a negotiation to fill it.

UMA worked that out a decade ago. It did not need a new primitive. It needed agent-shaped mechanics.

## Two shapes

![Two shapes for agent authorization: XAA/EMA IdP-to-MCP SSO versus U4A owner-authoritative cross-principal](/img/blog/u4a-two-shapes.jpeg)

On the left is the shape most of the market is building: Cross-App Access and Enterprise-Managed Agents. An IT admin consents once, org-wide. The IdP issues a scoped token through an ID-JAG exchange. The MCP server consumes the token and has no policy voice of its own. It works, it ships, and inside one trust domain it is genuinely useful.

Look at what is missing. Alice is in the diagram as a red box, and the label is the point: *no message in the protocol reaches her*. No terms. No ask-me. No per-operation grant. No owner revocation. The protocol assumes RO is the enterprise, because in the case it was designed for, it is.

XAA and EMA solve intra-domain distribution. That is the **RO = enterprise special case**. U4A is the general case, and an agent economy is made almost entirely of general cases: my doctor's agent, my advisor's agent, my lawyer's agent, my kid's school's agent, all touching resources whose owner does not work for the company that built the agent.

On the right, the ticket is minted at Alice's authorization server from message one. Policy lives with the person.

## What the resource server actually does

The move is to stop treating the resource server as a token consumer and start treating it as the place where the owner's terms are enforced.

Concretely, in the [U4A proof of concept](https://github.com/nickgamb/uma4agents), an agent calls an MCP tool and gets refused:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: UMA realm="alice-vault",
  error="insufficient_authorization",
  as_uri="https://alice-as.uma.lab",
  ticket="<ticket>",
  resource_metadata="https://gateway.uma.lab/.well-known/oauth-protected-resource/mcp",
  scope="trades:execute",
  authorization_remediation="<base64url JSON>"
```

Two parameters carry the whole idea. `as_uri` names **Alice's** authorization server, not the agent's. `ticket` is an opaque handle to a negotiation that has already started on her side.

That challenge is deliberately a superset of the RAR-metadata step-up draft rather than a rival to it. `error` and `authorization_remediation` are `draft-ietf-oauth-rar-metadata-remediation` unchanged, so a client that implements that draft can read most of this without knowing UMA exists. Decoded, the remediation object is ordinary RAR:

```json
{
  "authorization_details": [{
    "type": "urn:uma4agents:authorization-details:tool-call",
    "locations": ["https://gateway.uma.lab"],
    "identifier": "alice-vault/execute_trade",
    "actions": ["execute_trade"],
    "datatypes": ["trades:execute"]
  }],
  "authorization_reference": "s256:6cR6qTmCj6s0S95MxCfdfwfXJ8myLtBg-PiL8v93H0g",
  "authorization_server": "https://alice-as.uma.lab",
  "ticket": "<ticket>"
}
```

`authorization_server` and `ticket` are the two additions, and they are the difference between a client submitting a template to its own authorization server — which cannot work when the resource belongs to someone else — and a client being handed a ticket it can present but cannot widen. The client authors nothing.

## The four beats

The negotiation runs in four beats. This is the part worth internalizing, because it is where owner terms stop being a policy document and become a wire protocol.

**1 · Challenge.** The agent calls a tool, the policy enforcement point registers the attempt, and the gateway answers with the 401 above. A host with a status line sends `401` + `WWW-Authenticate`; an in-process one sends a JSON-RPC `-32001` carrying the same parameters. The client accepts either.

**2 · Attempt.** The agent presents the ticket at Alice's token endpoint:

```http
POST /token
grant_type = urn:ietf:params:oauth:grant-type:uma-ticket
ticket     = <ticket>
```

Alice's AS answers `403 need_info` with a rotated ticket and **the terms it dictates for that tier**. This is classic UMA claims-gathering, transformed. In 2018 the AS named claim formats it wanted. Here it proffers a terms template, MyTerms and IEEE 7012 shaped: what the agent may do, what it must not do, how long it has.

**3 · Commit.** The agent signs those terms as an intent contract, echoing them back, and re-presents. For a known agent under a permissive tier, that is enough. For a new agent, or for anything Alice marked `ask_me`, the AS returns `request_submitted` and holds the ticket while her portal buzzes.

The requesting side does not block through that wait. After a short window the shim hands it up to the calling client as an MCP `input_required` with a resumable `request_state`, so the call suspends rather than hangs.

**4 · Grant.** Alice taps approve. The AS issues a proof-of-possession RPT scoped to exactly what was agreed. The agent retries the signed call, the gateway introspects, and the call goes through.

Everything else — registration, the PAT, introspection — is setup the agent never sees.

## Notice what the owner never had to do

Alice was not online for beats one through three. She did not run an IdP. She did not federate with Bob's firm. She did not pre-provision an identity for Bob's agent, and she could not have, because she cannot enumerate every agent that will ever want to talk to her brokerage.

What she did was write a small policy document — editable in her portal as a form or as JSON — that says which resources sit in which tier and whether granting requires asking her. Three tiers in the demo:

| Tier | Resource | Behavior |
| --- | --- | --- |
| 1 | Holdings summary | Auto-grant under standard terms |
| 2 | Transaction history | Auto-grant under visibly stricter terms |
| 3 | Trade execution | `ask_me` — pends for per-operation approval |

That is the whole surface. The agent's identity model never entered into it.

## Four things the agent era actually demands

Building this surfaced capabilities UMA 2.0 has no slot for. Two are new uses of old machinery. Two are genuinely new.

**Per-operation, single-use grants.** "Approve this trade" must not silently become "may trade." Classic UMA scopes authorize *classes* of action. The RPT here carries an operation hash and is consumed on use. This is the single most important reshaping, and it is the one that makes an owner willing to say yes to anything sensitive.

**The owner's app as the consent surface.** UMA's 2010 wireframes assumed an out-of-band consent channel that did not exist yet. Everyone now carries one.

**Owner-mediated agent registration.** An agent with no standing connection pends on first contact regardless of tier. `request_submitted` does double duty as a day-1 handshake, and Alice sees the identity level, the key thumbprint, the operation, and the prohibitions the agent signed before she decides.

**A standing-relationship handle that survives key rotation.** This one bit us in the build, and it is worth the warning. We keyed connections on the agent's RFC 7638 JWK thumbprint, which is correct for a pseudonymous agent — the agent *is* its key. Then we wired up identified agents through AAuth, which binds a fresh key per session, and Alice's brokerage forgot the enrolled agent on every run. **Once real agent identity arrives, the key cannot be the relationship key.** The handle has to be the verified issuer-qualified subject.

That failure is a small illustration of the larger thesis. The identity layer changed underneath us and the authorization layer had to be indifferent to it. Building the authorization layer to be indifferent is the work.

## Run it

The whole stack comes up locally. Docker Desktop and `mkcert` are the only prerequisites.

```bash
git clone https://github.com/nickgamb/uma4agents
cd uma4agents
make init        # local CA, TLS certs, signing keys, DNS for *.uma.lab
make up          # the whole stack
make smoke-test  # verify every service, including a live grant challenge
```

Then walk the three acts, or drive it yourself:

```bash
make demo-all SIM=1   # SIM approves Alice's taps for you
make audit            # the promised / touched / approved ledger
```

Open `https://portal.uma.lab` and sign in as Alice (`alice` / `alice-demo`). Watch approvals arrive live, edit her terms, revoke a connection and watch live tokens die with it.

Bob's agent can be an unmodified MCP client. A local shim handles agent identity, request signing, and the negotiation, surfacing Alice's terms for you to approve. Point your own agent at it and see what your stack does when a resource server asks it to agree to something.

## What the market should be arguing about

I am not neutral here. [Eve Maler](https://www.linkedin.com/in/evemaler/) and I built this because we think the industry is spending its attention in the wrong place, and the diagram above is the argument in one frame.

If you are building agent identity, keep going. Ephemeral, enrolled, centralized, decentralized — genuinely, let them. The general case does not require you to win that argument, and U4A does not care which of you does.

What the general case requires is that when somebody else's agent shows up at your resource server, **you** get to state the terms, **you** get asked about the operations that matter, and **you** can revoke it afterward. Not your agent's vendor. Not the requesting party's IdP. Not an admin at a company you have no relationship with.

Agent identity is a solved-enough problem with too many solutions. Owner-authoritative authorization is an unsolved problem with almost no one working on it. That is the gap worth closing, and UMA already had the shape.

---

*U4A is [open source under Apache 2.0](https://github.com/nickgamb/uma4agents). [FINDINGS.md](https://github.com/nickgamb/uma4agents/blob/main/FINDINGS.md) carries the recommendations to spec authors — which UMA 2.0 primitives to keep, transform, or park, each backed by running code. Those recommendations are now written as the [U4A specification set](/docs/reference/specification/), nine Internet-Drafts, and comment on them is wanted.*
