# What an operation leaves behind

Alice can write *ask me about anything that cannot be undone* only if something
says which operations those are.

Every deployment knows. This lab has always treated `execute_trade` as an act
you cannot take back — it is single-use, bound to one operation, and her tier
asks her about it every time. What it did not do was **say so**. The knowledge
lived in two hardcoded sets in two processes, the reason for it appeared in no
document, and an owner who wanted that rule had to enumerate tools by name.

Now the resource declares it, her authority reads it, and the rule she writes
names no tool at all.

Run it: `make consequence-check`, or `make k8s-consequence-check` in the
cluster. Unit tests, needing nothing running: `make rules-test` and
`make pep-test`.

![The shape, in two lanes. The declaration lane: Meridian's vault declares a
class per tool — the two reads reversible, the trade irreversible — which is
published in RFC 9728 metadata inside the resource's own signature, pulled into
her registry rather than configured there, and read by a rule that names the act
rather than the tool. The request lane: Bob's agent calls the trade holding no
grant, the 401 challenge carries the class so the agent knows before it
negotiates, she is asked because the act cannot be undone rather than because of
its name, and the grant records the class it was issued against. Across the
bottom, the enforcement point compares what the resource declares now against
what the grant was issued against: the same class or gentler proceeds, worse is
refused.](consequence.svg)

![Six beats, top to bottom, each with what is actually on the wire beside it.
One: the resource publishes its tool surfaces, and each one carries a
consequence — get_positions reversible, execute_trade irreversible — inside the
signed metadata, so a relayed copy stays attributable. Two: her authorization
server pulls the same declaration into her registry through the protected
owner-resources listing, so what her rules read is what the resource said.
Three: she writes one rule, which names the class and no tool, and the same rule
written to grant automatically is refused at save time because a consequence may
only tighten. Four: an unauthorized call is challenged, and the remediation
object inside the challenge carries the class, so the agent learns what the act
would leave behind before it negotiates. Five: she is asked, and both the
pending request and her ledger record the class as the reason rather than the
tool. Six: the grant carries the class it was issued against, so when the
resource later re-declares that operation as irreversible the enforcement point
refuses with consequence_changed.](consequence-wire.svg)

## The vocabulary

Four classes, from [Nat Sakimura's work on governance for agentic
AI](https://nat.sakimura.org/2026/05/19/when-software-becomes-staff-governance-security-safety-for-agentic-ai/).
They are ordered by **how much remedy remains**:

| Class | The act can be | Example |
|---|---|---|
| `reversible` | undone completely, by whoever did it | reading a holdings summary |
| `compensatable` | offset by a counter-action, which leaves a trace | cancelling a booking |
| `forward_recoverable` | not undone, but recovered from by going on | repairing a workflow |
| `irreversible` | neither undone nor offset | placing a trade; disclosing a document |

The order is about remedy, **not severity**. It says how much of the world can
still be put back, not how bad it would be — a reversible act can still be
catastrophic while it stands. Nothing adds these up or scores them, for the
reason [assurance](ASSURANCE.md) gives at more length: a composite is the
mechanism by which one axis quietly excuses another.

## Who declares it

This is the whole design, and it is three rules.

**The resource declares it.** The party that owns the operation is the only one
that can say whether it can be undone, because it is the party that would have
to do the undoing. It publishes the class in the RFC 9728 metadata it already
signs, so a relayed copy stays attributable to the resource rather than to
whoever passed it along.

A requesting agent's description of *itself* stays display-only for exactly the
opposite reason — see extension 11 in [PROTOCOL.md](PROTOCOL.md). A party
describing its own trustworthiness is advertising. A resource describing what
its own tools do is not.

**Reading it can only tighten.** The condition is unwritable as a relaxation:
her editor refuses to save a rule that would grant automatically *because* an
act is irreversible. That is the same asymmetry assurance has — evidence may
raise what a request needs, and only her own decisions may lower it.

**Absent is unknown.** Not benign, and not severe. MCP's tool annotations
default to assuming the worst of an unannotated tool, which is right for a
client deciding whether to show a confirmation box and wrong here: it would
make every undescribed operation in every existing deployment look irreversible
on the day this shipped. So an undeclared operation is `None`, a rule about
severity does not fire on it, and she has a separate condition —
`request.consequence_unknown` — for refusing what nobody will describe.

## Where it travels

| Step | What carries it | Where |
|---|---|---|
| The resource states it | one table beside the tool definitions | `mcp/alice-vault/server.py`, `services/uma-pep/app.py` |
| Published, structurally | `consequence` on each `tool_surfaces` entry, inside `signed_metadata` | `lib/uma4a_publish.py` |
| Published, the other encoding | the same member on the AAuth R3 vocabulary | same file, `aauth_document` |
| Pulled into her registry | the protected owner-resources listing | `/owner-resources`, read by her AS |
| Read by her policy | `facts["request"]["consequence"]` | `services/uma-as/app.py` |
| Told to the agent | `consequence` in the challenge's `authorization_remediation` | `lib/uma4a_pep.py` |
| Carried by the grant | the RPT's `consequence` claim | `issue_rpt` |
| Re-checked at the call | introspection, against what the resource declares now | `lib/uma4a_pep.py` |
| Kept | the `promised` ledger entry | her record |

Two things are worth noticing in that list.

The class reaches the agent **in the challenge**, before it negotiates. An
agent that would rather not ask for something irreversible without its
operator's say-so can find that out at beat 1 rather than afterwards.

And the grant records the class it was **issued against**. If the resource
later re-declares the operation as less recoverable than it was — a read that
has become a disclosure — the enforcement point refuses with
`consequence_changed`. Her authority answered a question about the operation as
described; a different question needs a different answer. A grant issued before
anything was declared carries no class and is not refused retroactively, or the
day a deployment first described its tools would revoke every standing grant it
had.

## The rule she writes

```json
{"when": ["request.consequence_at_or_above:irreversible"], "then": "ask"}
```

That rule names no tool, no agent and no operator. It holds for tools she has
never seen, at resource servers she has never heard of, on the day they are
added — which is the property the whole [rules](INTENT.md) grammar exists for.

Her editor offers the classes as complete conditions, each marked as unable to
relax, through `GET /owner/policy-vocabulary`. `reversible` is deliberately not
offered: every declared operation is at or above it, and a rule that fires on
everything is not a sentence anyone writes on purpose.

## What this is not

It is not a risk score, and there is no number. It is not the agent's claim
about itself. It is not a substitute for the operation binding — an
irreversible tool still takes a grant bound to one act, and that is now
*derived* from the class rather than listed separately, because one fact stated
twice is one fact that can disagree with itself.

## Against the neighbouring work

MCP's tool annotations (`readOnlyHint`, `destructiveHint`, `idempotentHint`,
`openWorldHint`, and the proposed `reversibleHint`) describe the same territory
and are consumed where a server publishes them —
`uma4a_consequence.from_mcp_annotations` maps the ones that are explicitly
present, and never inherits MCP's pessimistic defaults, because a default is
not a statement anybody made.

Three differences are worth sending back to that work:

1. **Who reads it.** MCP's hints are published by a server to a client that may
   ignore them. Here the same fact is read by the party that bears the
   consequence — the owner's authorization server — and enforced by the
   resource itself.
2. **What it may do.** A hint that can only inform a dialog cannot be a
   control. A class that may tighten a requirement and may never relax one can.
3. **Absent is not false.** Defaulting an unannotated tool to destructive is a
   safe posture for a prompt and a bad one for policy; the honest third state
   is "nobody has said", and it deserves its own rule.
