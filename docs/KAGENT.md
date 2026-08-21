# An agent framework nobody modified

Every other demo in this lab drives the grant from code in this repository —
the demo driver, the shim beside Claude Code, Alice's personal AI. That proves
the protocol works. It proves nothing about whether anyone can adopt it.

This one is the other way round. [kagent](https://kagent.dev) is not ours, has
not been changed, and has never heard of UMA. It sees three ordinary MCP tools.
Alice's policy governs it anyway.

```bash
make kagent            # opt-in: it brings a model with it
make kagent-check
make kagent-ask Q="..."  # your own question
make kagent-down
```

## The adapter is the whole trick

kagent's MCP client will not sign an RFC 9421 request or a terms agreement, and
it should not have to. Something else does.

```
kagent Agent  ──MCP──▶  U4A adapter  ──four beats──▶  Alice's authority
(knows nothing)         (Bob's key)                   (decides)
```

The adapter is `clients/agent-shim/shim.py` — the same file Bob runs beside
Claude Code — started with `UMA4A_SHIM_TRANSPORT=streamable-http` so it can be
reached over the network instead of spawned as a subprocess. That one variable
is the entire difference. It holds Bob's signing key, runs the challenge,
proffers Alice's terms to Bob's standing configuration, signs the agreement,
presents proof-of-possession and keeps the counter-signed receipts.

It lives in **Bob's** namespace, because it is his: his key, his configuration,
his receipts. Alice's authority has never heard of it and treats what comes
through it as one more agent.

### The claim, checked without a model in the way

```bash
make adapter-check        # compose
make k8s-adapter-check    # kubernetes
```

`clients/demo-driver/adapter_check.py` is a plain MCP client. It imports
nothing of ours — no `uma4a_grant`, no key, no ticket — and it reaches Alice's
holdings:

```
== An agent with no U4A code in it ==
   ok   it discovers Alice's tools as ordinary MCP
   ok   and calling one returns her data
   ok   it never saw a ticket, terms, or a signature
```

If that passes, the only thing kagent adds is deciding which tool to call.

## Choosing a model

Opt-in, because a model is a real cost — a container that pulls a couple of
gigabytes, or an account somewhere. The U4A path is identical in every case.

| | |
|---|---|
| `make kagent` | Ollama in the cluster. No account anywhere, no key. Pulls a small tool-calling model on first start, which takes a few minutes. |
| `make kagent MODEL=anthropic` | `ANTHROPIC_API_KEY` from your shell, into a Secret and nowhere else. `ANTHROPIC_MODEL` overrides the pinned model. |
| `make kagent MODEL=openai` | `OPENAI_API_KEY`, likewise, with `OPENAI_MODEL`. |
| `make kagent MODEL=bedrock` | `AWS_BEDROCK_API_KEY`, plus `AWS_REGION` and `BEDROCK_MODEL` if the defaults are wrong. |

The key never reaches this repository. `k8s/scripts/kagent.sh` reads it from
your environment, creates a `Secret`, and the `ModelConfig` references it.

**Adding a provider is a case statement.** kagent's `ModelConfig` accepts
`Anthropic`, `OpenAI`, `AzureOpenAI`, `Ollama`, `Gemini`, `GeminiVertexAI`,
`AnthropicVertexAI`, `Bedrock` and `SAPAICore`; each needs a name, a model, and
whatever block it requires of its own — Bedrock wants a `region`, Ollama wants
a `host`. Nothing about U4A changes, because the model only decides which tool
to call.

Bedrock is written and validated against the CRD but has not been run here; the
Ollama and Anthropic paths have.

Small model, on purpose. This exists to show a framework negotiating with
Alice's authority, not to demonstrate reasoning. Any tool-calling model works —
`qwen2.5:1.5b` is enough, and both it and Claude have been run against this
end to end.

If the agent answers without calling anything — "tool not found", or a fluent
paragraph about a portfolio it never fetched — suspect the *order*, not the
model. An Agent reads its tool list once at start-up, so a pod that came up
before its `RemoteMCPServer` was reconciled has no tools and will invent a
function name. `make kagent` waits for the tools to be discovered before
rolling the agent, for exactly this reason.

## What it looks like

```
== An agent framework, asked a question ==
   agent: sterling-vance/advisory-agent (kagent)
   question: What is in Alice's portfolio?
   it has one tool server: the U4A adapter. It knows nothing else.
   [alice] approving connection request for tier1

== And on Alice's side ==
   her ledger's `touched` rows: 2 before, 3 after
```

That last pair is the assertion that matters. "The agent replied without
erroring" is not evidence — a model that talks about a portfolio without
calling anything produces a perfectly cheerful answer and proves nothing. A new
`touched` row means the grant was issued and spent.

The first contact is held for her, as it is for every agent she has never met —
kagent's framework-ness earns it nothing. Her portal shows it beside Bob's
script agent and your own MCP client, with its own terms, its own trail and its
own revoke button.

## What this demonstrates, and what it does not

**It is an adoption result, not a protocol finding.** The negotiation is the
adapter's. Nothing here changes what the authorization server does, and
`make kagent-check` would pass with a different framework, or none.

What it does establish is worth having anyway:

- **The requesting side needs an adapter, not a rewrite.** An agent platform
  can be pointed at Alice's resources and governed without a line of its code
  changing. That is the difference between a protocol people admire and one
  they use.
- **Both sides of the boundary become declarative.** Alice's vault is already a
  kmcp `MCPServer` rather than a Deployment we wrote; with this, so is the
  agent asking. Two Kubernetes objects, one boundary between them.
- **The framework's identity buys nothing.** kagent arrives as a stranger, is
  held like a stranger, and appears in her connections list like a stranger.

## It is not really about kagent

The adapter is Bob's, not kagent's. It runs in his namespace, holds his key,
and speaks ordinary remote MCP — so anything that can be pointed at a remote
MCP server can be governed by Alice's policy the same way. kagent is one such
thing; Claude Code through the stdio shim is another; `adapter_check.py` is a
third with no framework at all.

That is worth saying plainly because it is easy to read this page as "we
integrated kagent". The integration surface is MCP, and the list of frameworks
that can use it is not ours to enumerate.

Note also which layer this is. A `ModelConfig` answers *what does this agent
think with*. Products that manage or govern fleets of agents are a different
layer again, and would sit above an agent rather than inside its model
configuration — they reach Alice the same way everything else does, by pointing
at the adapter.

## Kubernetes only, and why

kagent is a Kubernetes controller. There is no compose shape for it and this
does not pretend otherwise.

The part that matters *is* in compose: `make adapter` runs the adapter as a
service, and `make adapter-check` proves an unmodified MCP client reaches
Alice's things through it. What compose cannot show is a framework doing the
asking.

## See also

- [DEMOS.md](DEMOS.md) — all three demos, and when to reach for which
- [KWAAI-BINDING.md](KWAAI-BINDING.md) — the same trick on the owner's side
- `clients/agent-shim/README.md` — the adapter as Bob runs it locally
- `k8s/components/kagent/` — the Agent, and both model shapes


## Asking it something else

`make kagent-check` asks one fixed question and answers Alice's pending queue
itself, because a headless check has to. For anything else:

```bash
make kagent-ask Q="Show me her transaction history and cost basis."
make kagent-ask Q="Sell 200 shares of her AAPL position." SIM=0
```

`SIM=0` is the difference that matters. With it, nothing answers for Alice —
the request sits in her pending queue until a person decides it in her portal,
which is the only way to show that the wait is real rather than staged. The
agent simply blocks, because from its side an ask-me tier is a slow tool call.

Under `SIM=0` a refusal is a valid outcome and the run still exits zero. Her
declining a trade is the tier working, and a check that failed on it would
report the most important beat of the demo as a bug. The `touched` count in her
ledger is reported either way, so you can see whether her resources were
actually reached.

The question and the flag reach the Job through the `kagent-ask-input`
ConfigMap rather than being substituted into the manifest, so an apostrophe in
the question does not break the YAML.
