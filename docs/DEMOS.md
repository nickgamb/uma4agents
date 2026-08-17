# Two demos, one lab

The lab tells one story — an agent that is not hers asks for something of
Alice's, and her side decides — and it can tell it two ways. The difference is
only **what stands on her side of the boundary**. The protocol, the terms, the
ledger and the agent are identical in both.

| | Her portal | Her personal AI |
|---|---|---|
| What answers | a browser session she signs in to | pAI-OS, holding her key |
| How she authenticates | OIDC, through her identity provider | an RFC 9421 signature |
| Who decides | her, at the moment | her standing consent, ahead of time |
| Bring it up | `make up` (the default) | `make up` then `make paios` |
| In Kubernetes | up with the cluster | `make k8s-paios` |

Both are worth showing, and the portal one is the default because it is the
one that makes the protocol visible: you watch an agent hold a ticket, you tap
approve, you watch the grant arrive.

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
pAI-OS gives an ability no channel to reach her. Those pend, and her portal is
still where she answers them. So the honest version of the second demo is:
**both surfaces, doing the part each can do.**

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
make assurance-check    # what her policy can say about an agent, and the cap
make rules-test        #   on how much of her attention a stranger can spend
```

Neither is a demo — they are checks — but the first one reads like one, and it
is the shortest route to what [ASSURANCE.md](ASSURANCE.md) argues.

## The third thing, which is not a demo

`make fixture` is a two-container stack with no identity provider, no database
and no mesh — the grant and nothing else. It exists to make a point about how
little the protocol needs, and it is a test fixture rather than a demo. See
[FIXTURE.md](FIXTURE.md).
