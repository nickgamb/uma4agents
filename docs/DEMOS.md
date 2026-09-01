# Three demos, one lab

The lab tells one story — an agent that is not hers asks for something of
Alice's, and her side decides. Two of the demos change **what stands on her
side**; the third changes **what stands on his**. The protocol, the terms and
the ledger are identical in all three.

**Her side of the boundary:**

| | Her portal | Her personal AI |
|---|---|---|
| What answers | a browser session she signs in to | pAI-OS, holding her key |
| How she authenticates | OIDC, through her identity provider | an RFC 9421 signature |
| Who decides | her, at the moment | her standing consent, ahead of time |
| Bring it up | `make up` (the default) | `make up` then `make paios` |
| In Kubernetes | up with the cluster | `make k8s-paios` |

**His side of it:**

| | Bob's agent | An agent framework |
|---|---|---|
| What asks | code in this repo, or Claude Code through the shim | kagent, unmodified, which has never heard of UMA |
| Who runs the grant | the same code | the U4A adapter beside it |
| Bring it up | `make demo-all` | `make kagent` |
| In Kubernetes | `make k8s-demo-all` | `make kagent` (Kubernetes only) |

The portal demo is the default because it is the one that makes the protocol
visible: you watch an agent hold a ticket, you tap approve, you watch the grant
arrive.

## Her portal

The reference demo. See [START-HERE.md](../START-HERE.md), or:

```bash
make up
make demo-all ACT=tier1 SIM=0     # then approve at https://portal.uma.lab
```

## Her personal AI

The same lab with Kwaai's pAI-OS added, running our ability. See
[KWAAI-BINDING.md](KWAAI-BINDING.md).

```bash
make up
make paios          # her personal AI starts answering
make paios-check
make paios-down     # hand the decisions back to her portal
```

**They do not run against each other well, and that is the point.** While her
personal AI is up it answers everything she has given it standing consent for,
so those requests never appear in her portal — there is nothing left to tap.
That is not a conflict to fix; it is what "she is not woken" looks like from
the other side. `make paios-down` puts the requests back in front of her.

What her personal AI does *not* answer is anything on an ask-me tier, because
pAI-OS gives an ability no channel to reach her. It **refuses** those rather
than holding them — the ability logs `denied — no channel to her` and the
negotiation ends. A refusal it can justify is the safe answer when the one
thing it cannot do is ask; a pend nobody can resolve would be worse. Run
`make paios-down` and the same request waits for her portal instead. So the
honest version of the second demo is: **both surfaces, doing the part each
can do**, and neither pretending to be the other.

## An agent framework nobody modified

The first two demos drive the grant from code in this repository, which proves
the protocol and proves nothing about adoption. This one is the other way
round: [kagent](https://kagent.dev) is not ours, was not changed, and sees
three ordinary MCP tools.

```bash
make kagent            # a model in the cluster, no account anywhere
make kagent-check      # ask it a question; Alice decides
make kagent-down
```

Everything that makes those tools reachable happens in the **adapter** — the
same `clients/agent-shim/shim.py` Bob runs beside Claude Code, started as a
network service instead of a subprocess, holding his key and running the four
beats. The framework above it needs an adapter, not a rewrite.

That claim is checkable without a model in the way, and in both shapes:

```bash
make adapter-check       # compose
make k8s-adapter-check   # kubernetes
```

The model is your choice, and the U4A path is identical either way — it only
decides which tool to call:

```bash
make kagent                   # ollama, in the cluster, no key
make kagent MODEL=anthropic   # ANTHROPIC_API_KEY from your environment
make kagent MODEL=openai      # OPENAI_API_KEY
make kagent MODEL=bedrock     # AWS_BEDROCK_API_KEY, plus AWS_REGION
```

Full detail is in [KAGENT.md](KAGENT.md).

**Kubernetes only**, and honestly so: kagent is a Kubernetes controller and
there is no compose shape for it. What *does* run in compose is the part that
matters — the adapter, and an unmodified MCP client using it (`make adapter`,
`make adapter-check`).

## Doing it live, with a person deciding

Every check above answers for the owner, because a check has to. Each one also
has a **demo** beside it that does not: the ticket is held, the log is followed
rather than printed at the end, and somebody decides in a portal while the room
watches. Nothing else differs — same driver, same beats, same ledger.

```bash
make k8s-demo ACT=tier1        # first contact, held for her
make k8s-demo ACT=tier3        # the ask-me tier; approve or deny it
make k8s-joint-demo            # both holders, in two portals
make k8s-multi-owner-demo      # two authorities; try disagreeing
make k8s-first-party-demo      # her agent and Bob's, under one rule
make kagent-ask Q="..." SIM=0  # the same, asked by kagent
```

The wait is the demonstration, so these follow the Job's log instead of
`run_job`'s wait-then-print: a pend and a hang look identical in an empty
terminal. They also hold the ticket for fifteen minutes rather than two, which
is the difference between "the loop should have finished" and "she is reading
it on the other screen".

Each uses a fresh agent key per run, so the agent is always a stranger and the
request always reaches her — `make k8s-reset` is for rewinding her ledger, not
for making the demo work twice.

There is a run card for each of these under [cards/](cards/), with the commands,
the clicks and what to say at each beat.

## Switching between them

Nothing needs rebuilding either way, and no state is lost. A decision made by
either surface lands in the same ledger, correlated to the same negotiation —
`make audit` shows both without distinguishing them, which is the correct
behaviour and worth pointing out during a demo.

To rewind the story without rebuilding:

```bash
make reset          # compose
make k8s-reset      # kubernetes
```

## Worth running either way

```bash
make assurance-check    # what her authority can verify about an agent, and
                        # the cap on how much of her attention one can spend
make rules-test         # the rule engine alone; nothing need be running
make store-test         # both storage backends, against one property suite
```

None of these is a demo — they are checks — but the first reads like one, and
it is the shortest route to what [ASSURANCE.md](ASSURANCE.md) argues.

## When the stuff is not hers

Everything above is Alice's own account. `make org-check` is the other case:
Meridian also holds Northwind Capital's book, the firm shares parts of it with
Alice and Carol under a role, and each of them administers access to it under
her own authority and her own terms.

Two beats are worth watching for. Joining *grants* something — the firm's book
appears in her authorization server, marked shared, and leaving takes it back.
And whose agent it is decides the answer: under the analyst role's
`first-party-only`, an agent she operates reads the book and Bob's agent is
refused, with the same terms, the same key strength and the same request.

The administrator's surface is at `https://org-console.uma.lab` (`dana` /
`dana-demo`), and hers is under Agent Access → Organization in her own portal.

Two pages there are worth opening together, because they are the charter's two
halves. **Groups** is what a member gets and agrees to — create one, set what
it reaches, mark the one joiners land in, move people between them; saving
publishes a charter version, because it changes the bargain. **Charter →
Rules** is what the firm enforces operationally, in Rego, and can only refuse
or interrupt. The test for which page a rule belongs on is whether a member
would have to agree to it again. [ORG.md](ORG.md).

## Two owners, neither above the other

```bash
make joint-check               # the suite, answering for both of them
make k8s-joint-demo            # the same account, with both of them deciding
```

Meridian holds an account for Alice and Carol together. Neither of them can
release it alone, and there is no firm above them — so the thing an agent
negotiates with is a **tally**, which owns nothing and decides nothing.

Two moments are worth watching for. The agent is offered **one** terms
document that is both holders' at once: the shorter expiry, only the scopes
both of them offer, every prohibition either of them wrote. And the grant it
receives carries a signed verdict from each holder, which the gateway verifies
against the keys their authorities publish before re-running the count itself
— so a tally that fabricated an answer is refused at the door rather than
believed.

`meridian-either` is the same machinery with the rule set to `any`, which is
the "either or survivor" half of how joint accounts actually work.

Her side is **Agent Access → Joint accounts** in the portal. Worth opening
beside the Organization tab: one is a firm above her, the other is a person
beside her, and an organization reaches none of what she holds jointly —
whatever its charter claims, because her co-owner never enrolled there.
[JOINT.md](JOINT.md).

## An enterprise identity provider, beside her authority

```bash
make xaa-check
```

Northwind runs an identity provider. Alice runs an authorization server. This
is both of them in one negotiation, and the point is that neither answers the
other's question.

Watch the beats. The agent calls a tool, is refused, and is *told* which
provider to go to — it knew nothing about Northwind when it started. It comes
back with an **ID-JAG**: a short-lived assertion, audienced at Alice's
authority alone, saying which employee is behind the application and that an
administrator approved that application reaching that resource. Her authority
checks it and then does what it always does — dictates her terms.

The other thing to watch is what the assertion does *not* buy. It is not an
access token. A perfectly good one still has to negotiate, and an agent
somebody else operates is still refused by the charter's `first-party-only`
role — because whose agent it is remains her declaration, not her employer's.
And over her own account, no assertion is asked for at all.
[XAA.md](XAA.md).

## The third thing, which is not a demo

`make fixture` is a two-container stack with no identity provider, no database
and no mesh — the grant and nothing else. It exists to make a point about how
little the protocol needs, and it is a test fixture rather than a demo. See
[FIXTURE.md](FIXTURE.md).
