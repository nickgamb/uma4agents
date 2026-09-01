---
templateKey: doc
title: "Demo: her own agent"
seoTitle: "Demo a first-party agent held to the same ceiling as a stranger"
description: One rule, one tier, two agents — hers goes through without waking her, and one that is not hers is asked anyway.
next:
  - title: "Demo: her personal AI"
    to: /docs/guides/demo-personal-ai/
    blurb: The other thing that can answer for her.
  - title: Her own agent
    to: /docs/overview/first-party/
    blurb: Why being hers is two facts, not one claim.
---

The degenerate case: an agent Alice activated herself. She is not at the
keyboard, it holds its own key, and her policy governs every request it makes —
so the grant does not change. **Being hers buys less friction, never more
access.**

The whole card turns on a contrast. Steps 4 and 5 are the same tier under the
same rule, so run them back to back.

## The run-through

**0 · Terminal — `make k8s-status`**
`sterling-vance` is Bob's namespace and `alice` is hers. By the end, an agent in
each will have asked her authority for the same thing.

**1 · Her portal — Settings → Security → Agent Authorization → Operators**

```
https://alice-agent.uma.lab
```

She claims an origin as hers. This is half a decision and the portal treats it
as half: **anybody may point an agent at her origin**, because a metadata
document only proves it came from the URL it names. The other half is that
**only she can put a key in her directory**.

**2 · Her portal — My Terms → Trade execution → add rule**

```
When:  the agent is one of mine
Then:  allow without asking me
```

**The rule names no agent.** Not a key, not a vendor, not a product — only that
the thing asking is hers. She is describing a relationship, and anything
entering or leaving it is covered without her editing this again.

**3 · Terminal — `make kagent RESOURCE=hers`**
As it starts, the adapter publishes its signing key in her directory and names
her origin as its client id — the second half from step 1, done the only way it
can be.

**4 · Terminal**

```bash
make kagent-ask RESOURCE=hers Q="Sell 200 shares of my AAPL position." SIM=0
```

The trade goes through and she is never asked. **Watch the right screen and say
what is not happening**: no badge, no queue, no tap. The next step is the same
rule and the same tier, so make them notice this one.

**5 · Terminal**

```bash
make kagent-ask Q="Sell 200 shares of her AAPL position." SIM=0
```

Bob's agent asks for exactly the same thing. It is attested too — a real
operator, a published key, a signed request. It is simply not hers, so her rule
does not reach it and the request stops.

**6 · Her portal — Approve or Deny**
She is asked, exactly like anybody else. Either answer makes the point: **being
hers bought less friction and no more access.** Her tier is the ceiling in both
directions; the only thing that moved was whether she had to be woken.

**7 · Her portal — Operators → Disclaim**
Re-run step 4. Her own agent is asked now, like a stranger, with no change to
the agent at all. **What made it hers was her say-so, and it was hers to
withdraw** — the difference between a relationship and a credential.

## What it establishes

An agent is first-party when the operator it names is an origin she claimed
*and* her authority found that agent's signing key in that operator's own
directory. Both halves, and the second is the one with teeth — because "this is
my agent" is the one fact in the profile that makes a requirement looser, so it
is the one place a claim can never be enough.
