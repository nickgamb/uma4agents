---
templateKey: doc
seoTitle: "What is UMA for Agents? Decentralized agent authorization"
title: Overview
description: A working profile of UMA 2.0 for the case where the thing asking is someone else's AI agent, and the person who owns the resource is asleep.
video: cxbUZndIBfg
videoTitle: The Kubernetes lab, running in a Codespace
videoPoster: /img/docs/codespace-demo.png
next:
  - title: Why the owner decides
    to: /docs/overview/why/
    blurb: The problem this shape exists to solve, and who currently cannot solve it.
  - title: The four beats
    to: /docs/overview/four-beats/
    blurb: Challenge, attempt, commit, grant — the whole negotiation.
  - title: Run the lab
    to: /docs/guides/run-the-lab/
    blurb: A three-node deployment in a browser, in about thirteen minutes.
---

UMA for Agents is a profile of [User-Managed Access
2.0](https://docs.kantarainitiative.org/uma/wg/rec-oauth-uma-grant-2.0.html)
for the case the specification was written before: the party asking for access
is an autonomous agent, it belongs to somebody else, and the person who owns
the resource is not at the keyboard.

Everything described in these docs runs. The reference implementation is
Apache-2.0 and deploys two ways — a compose stack for reading, and a
three-node Kubernetes cluster for seeing how it behaves when replicated.

## The question

Agent identity protocols answer *"is this my agent, doing my task?"* — a
question about the requester, asked by the party that owns the agent.

The harder question is *"may your agent touch my stuff?"* Answering it needs an
authority on the **owner's** side, one the resource server does not control,
and it needs a negotiation to fill that authority in while the owner is
elsewhere. UMA worked this out in 2018. What it did not anticipate is a
requester that arrives thousands of times a day, holds its own key, and can be
asked to agree to something.

## What the profile adds

UMA 2.0 assumes a requesting party who can be prompted. This profile keeps the
grant and changes four things around it:

- **Terms become an artifact.** The authorization server dictates machine-readable
  terms, the agent signs them, and both sides keep the receipt. The pattern is
  [IEEE 7012](https://standards.ieee.org/ieee/7012/7192/) — the owner proffers,
  the counterparty agrees.
- **The token binds to a key, not to a bearer.** Grants are proof-of-possession
  over [RFC 9421](https://www.rfc-editor.org/rfc/rfc9421.html) message
  signatures, and sensitive ones bind to a single operation.
- **Registration is pulled, not pushed.** The resource server publishes
  [RFC 9728](https://www.rfc-editor.org/rfc/rfc9728.html) metadata; the owner's
  authorization server reads it.
- **The agent is identifiable.** It can be pseudonymous, in which case it *is*
  its key, or identified through an agent-identity protocol such as
  [AAuth](https://github.com/dickhardt/AAuth).

## What is in these docs

Three sections, and two kinds of page. Concept pages explain one idea; guides
walk one procedure end to end.

**Overview** — this section. It explains the shape one idea at a time: the
[beats of the grant](/docs/overview/four-beats/), the
[parties](/docs/overview/parties/), what makes
[single-use mean something](/docs/overview/single-use/). It also holds the
comparisons — start at [UMA 2.0](/docs/overview/compare-uma/) if you already
run something adjacent and want to know what this adds and what it does not.

**[Guides](/docs/guides/roles/)** walk procedures. They name the *role* first
and only then say how this lab filled it, because the interesting question is
what you would build, not what we happened to choose.

**[Reference](/docs/reference/wire-contract/)** is the wire contract, the
endpoints, the events, and the exact places this profile departs from UMA 2.0.

## What this is not

It is not a product. It is a proof of concept built alongside
[Eve Maler](https://www.linkedin.com/in/evemaler/) to find out which parts of
UMA survive contact with agents. [The findings](/docs/reference/findings/) are
what it produced, and the [specification set](/docs/reference/specification/)
— seven Internet-Drafts profiling and extending UMA 2.0 — is what the findings
were for. Where the lab does something a production system would not, the page
says so.
