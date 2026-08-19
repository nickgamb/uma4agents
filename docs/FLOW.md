# Flow: identity stays where it is

The idea this profile turns on is not the ticket or the token. It is that
**Alice never has to know how Bob's agent is identified.**

She writes her terms and sets her tiers. Whether the agent asking is a bare
key with no issuer anywhere, an AAuth-identified agent whose session keys
rotate every run, one described by a CIMD document, or one whose keys are
published in a Web Bot Auth directory — none of that reaches her. Governance
of the agent stays with Bob, who runs it. Governance of the resource stays
with Alice, who owns it. Neither side has to adopt the other's identity
system for the grant to work.

That is a claim, so it is checked:

```
make flow-check
```

## What it does

Four negotiations against the same authorization server, with the requesting
side arranged four different ways, and a comparison of what Alice's side did.

| Regime | What the agent brings | What it is |
|---|---|---|
| pseudonymous | a bare Ed25519 key | the key *is* the identity |
| identified | an AAuth `aa-agent+jwt`, fresh session key each run | a verified issuer stands behind it |
| described | a CIMD document at a URL | who operates it — display only |
| published | a Web Bot Auth directory | where its keys can be looked up |

Measured output:

```
her policy: 3 tiers
nothing in it names an agent, an issuer or an identity scheme

terms:  identical in all four
grant:  identical in all four
as_uri: identical in all four
her policy: unchanged
```

## Two levels, not four

Four regimes do not produce four handles. The run says so:

```
pseudonymous   aauth:pseudonymous-agent
identified     aauth:6db1c44a-…@ps.uma.lab
described      aauth:pseudonymous-agent
published      aauth:pseudonymous-agent
```

There are **two identity levels**, not four. Either the key is the identity,
or a verified issuer stands behind it. CIMD and Web Bot Auth are *additive
description*: they let a party who has never met this agent say something true
about who operates it, and they change nothing about how it is filed or
judged.

Description is not identity, and neither is authorization.

## The negative that makes it falsifiable

An assertion that everything is identical proves nothing on its own — a system
that ignored all four inputs would also pass. So the check also asserts that
**her policy document contains no identity vocabulary at all**: no issuer, no
`aauth`, no `cimd`, no thumbprint, no `jkt`, no `agent_token`.

If any identity signal ever became an authorization input, one of the two
halves would break: either her policy would have to name it, or the four runs
would stop agreeing.

## Why this is the design and not an accident

Three decisions, each already in the profile, add up to it:

**The verifying key is always the grant's `cnf`.** Not the CIMD document, not
the Web Bot Auth directory, not the issuer. Those are consulted for display and
discovery; the thing that decides whether a request is authentic is the key the
grant names.

**The connection handle follows the identity level, and nothing else.** A
pseudonymous agent is filed under its RFC 7638 thumbprint, because the key is
the identity and must persist for the relationship to persist. An identified
agent is filed under its issuer-qualified subject, because AAuth binds a fresh
session key per run and a thumbprint-keyed connection would forget it every
time. Both are handles; neither is a permission.

**Her terms are about the access, not the asker.** Purpose, scope, expiry,
prohibitions. Nothing in a terms template has anywhere to put an issuer.

## What this costs

Alice cannot write a policy like "only agents from this issuer." She can decide
per agent, per tier and per operation, and she can revoke a connection — but
she cannot express a rule over an identity system she is deliberately blind to.

She *can*, since [ASSURANCE.md](ASSURANCE.md), write "an agent whose credential
I cannot trace must ask me." That is a rule about the evidence, not about an
issuer: her policy vocabulary contains no issuer, no `cimd`, no thumbprint and
no `agent_token`, so swapping the mechanism underneath leaves it unchanged. And
it can only ever *add* friction — nothing an agent asserts about itself can
lower what her policy requires. The four runs above still receive identical
terms, an identical grant and identical `as_uri`; what can now differ is how
often she is asked, which is hers to decide and no agent's to influence.

Whether that is a limitation or the point is the interesting question. Today it
is the point: it is what lets an agent from an organisation she has never heard
of ask her for something without either side onboarding to the other. A
deployment that wants issuer rules is describing a different trust model, and
should say so rather than reaching for this one.

## See also

- [FIXTURE.md](FIXTURE.md) — the minimal fixture, and how little the protocol
  needs underneath it
- [ASSURANCE.md](ASSURANCE.md) — policy that faces the agent without naming one
- [KWAAI-BINDING.md](KWAAI-BINDING.md) — a personal AI as the owner's side
- `clients/demo-driver/flow_check.py` — the check itself
