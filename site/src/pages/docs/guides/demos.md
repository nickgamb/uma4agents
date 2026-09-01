---
templateKey: doc
title: Lab demonstrations
seoTitle: "Live demos of owner-authoritative agent authorization"
description: Six run sheets for demonstrating the lab to a room — what to type, what to click, and what is worth saying while it happens.
next:
  - title: Alice to Bob
    to: /docs/guides/demo-alice-to-bob/
    blurb: The reference demo. An unmodified agent framework, held to her policy.
  - title: Run the lab
    to: /docs/guides/run-the-lab/
    blurb: Get the cluster up before you walk into the room.
---

Each of these is a run sheet rather than a tutorial. They assume the lab is
already up and that you are showing it to somebody: a terminal on the left, an
owner's portal on the right, and a sequence that has been rehearsed so it does
not need to be.

They all share the same shape. **You drive an agent by asking it a question in
plain language**, and then you play the owner and decide. Nothing is scripted
on either side — there is no test harness to run and no simulated approval.
That is deliberate: a demo where a script answers for the owner cannot show the
thing this protocol exists for, which is that she is the one who answers.

## The six

| | What it shows |
|---|---|
| [Alice to Bob](/docs/guides/demo-alice-to-bob/) | An agent framework nobody modified, governed by her policy anyway |
| [Two owners, one account](/docs/guides/demo-joint-account/) | A jointly held account where neither owner can release it alone |
| [Two owners, two authorities](/docs/guides/demo-two-authorities/) | One agent, two owners, opposite answers, nothing reconciling them |
| [Her own agent](/docs/guides/demo-her-own-agent/) | Being hers buys less friction and no more access |
| [Her personal AI](/docs/guides/demo-personal-ai/) | Standing consent answering, and refusing what it cannot ask her about |
| [The firm's book](/docs/guides/demo-the-firms-book/) | A resource that exists in her authority only while she is a member |

Start with **Alice to Bob**. It is the one that establishes the shape — an
agent asks, she is held, she decides — and every other demo is a variation on
a party in that sentence.

## What every one of them needs

The lab, and a model for the agent to think with:

```bash
make kind-up                     # the cluster, ~13 minutes cold
export ANTHROPIC_API_KEY=sk-ant-...
make kagent                      # the agent framework and its adapter
```

`make kagent MODEL=openai` and `make kagent MODEL=ollama` work the same way;
the U4A path does not change, because the model only decides which tool to
call. Full setup, including trusting the lab's certificate authority so the
portals load cleanly, is in [Run the lab](/docs/guides/run-the-lab/).

## Waiting is the demonstration

Every one of these has a moment where the terminal stops and nothing happens
until a person decides. Do not rush it, and do not apologise for it. An agent
holding a request open while an owner sleeps is the entire argument: the
alternative — standing privilege, granted in advance because nobody wanted to
wait — is what the room is already doing.

The agent polls while it waits, and each check resumes the request she is
already deciding rather than opening another one. That distinction is not
cosmetic. Her authority keeps a budget for how much of her attention any one
agent may spend, and an agent that re-asks instead of resuming spends it —
correctly getting throttled for behaving like a nuisance.
