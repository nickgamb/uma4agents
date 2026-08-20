---
templateKey: doc
title: Put the authority on her device
description: Running the owner's side inside a personal AI — the credential it needs, the four methods it has to provide, and what stays the authorization server's job.
next:
  - title: Wire the owner's approval path
    to: /docs/guides/approval/
    blurb: The general version of what this specialises.
  - title: Identity stays where it is
    to: /docs/overview/flow/
    blurb: Why her side can stay this small.
---

The owner's authority does not have to be a service somebody operates for her.
It can run where she is — on a laptop, on a home server, inside a personal AI
that already holds her keys and already has her attention.

This guide covers what that takes. It is less than it sounds, and the reason
is structural: the profile already puts the deciding authority on her side, so
the surface only has to *answer* an authority rather than become one.

## Prerequisites

- An [authorization server](/docs/guides/roles/) you control the configuration of
- A signing key the device holds — a file, a keychain, a secure enclave
- Somewhere to reach the person

## 1. Give her a credential that is not a login

This is the piece most deployments will have to add, because UMA 2.0 and
FedAuthz say nothing about how the owner authenticates to her own authorization
server. In 2018 the answer was obviously "it is a web application and she logs
in." That answer requires an identity provider, which a personal device should
not need.

The alternative costs one code path: she signs her own owner-API requests.

```
UMA_AS_OWNER_AUTH=oidc              # her browser session
UMA_AS_OWNER_AUTH=local-key         # a key her device holds
UMA_AS_OWNER_AUTH=oidc,local-key    # both
```

In key mode the owner API verifies an RFC 9421 signature over
`@method @authority @path authorization` against a public key she enrolled
once. That is the **same message-signature profile the agent uses to prove
possession of a grant**, pointed at the owner — so it is a third direction
through a verifier you already have rather than new machinery.

There is no account, no session and nothing issued. A new credential is a new
key.

## 2. Accept more than one

Configure both, and mean it. A person reaches her own things more than one way:
a browser on her laptop, an app on her phone, a personal AI holding a key.

Each credential should be **independently sufficient and independently
revocable**, and none should be a fallback for another. The practical test is
that a decision made through either surface lands in the same ledger,
correlated to the same negotiation — if the two surfaces produce two records,
you have built two authorities.

## 3. Take the authority from configuration

The signature base needs an authority, and it must come from your config, never
from the request. An authority read off the `Host` header is an authority the
caller chooses.

This does not relax because the caller happens to be the owner. It is the same
rule as everywhere else in the profile, and the same bug if you break it.

## 4. Decide what the surface actually has to do

Very little. Holding the key and asking the person is all of it:

| It must | It must not |
|---|---|
| sign requests with her key | implement the grant |
| show a request in terms a person can act on | hold the terms roster |
| take approve or deny, with an unbounded wait | issue or verify tokens |
| keep a record | be reachable by the requesting agent |

The ticket, the terms, the signed agreement, the proof-of-possession token, the
single-use burn and the ledger all stay with the authorization server. A
surface that reimplements any of them has forked the protocol.

That last row matters: the agent waiting on the other side holds a *ticket*,
not a connection. An answer tomorrow is still an answer, so the surface may
notify, batch, or sit on it.

## 5. Enrol the key, not the person

Only the public half should ever reach the authority. Generating her private
key server-side would put the authority in possession of the credential it is
supposed to be checking.

In the lab this is one `make owner-key`, which writes a keypair and hands over
only the public part. A real deployment enrols a key the device already holds
and never had to generate.

## What it is like when the host cannot ask

The fourth method is what separates a personal AI from a
standing policy, and it is the one a host is least likely to have.

The lab runs this against a real personal-AI runtime — Kwaai's pAI-OS, with
the ability installed under `abilities/<id>/<semver>/` where its own loader
finds it (`make paios`, or `make k8s-paios` in the cluster). It starts an
ability as a process configured by environment variables, which is enough for
three of the four methods and not for `ask`: there is no notification, no
prompt, no inbox.

So the ability **denies** anything that needs her, and records why:

```json
{"event": "cannot-ask", "family": "trade:execute",
 "outcome": "denied — no channel to her"}
```

Denying is the right default — a request pends precisely because she has not
said yes — but it narrows what the surface can do to the tiers she stood
behind ahead of time. If you are building one of these, build the channel
first. Everything else in this guide is mechanical by comparison.

## Verify it

- An unsigned owner request is refused
- A request signed by a key she did not enrol is refused
- Her other credential still works on its own
- A decision made through the device surface appears in the ledger her other
  surface reads
- Her private key is not on the authority's filesystem

## Troubleshooting

**Every request is refused with a signature error.** The authority the two
sides reconstruct the base against differs. Both take it from configuration;
make them agree.

**The surface polls forever and never sees anything.** It is probably failing
to reach the authority and swallowing the error. A surface behind a private CA
needs the trust bundle passed in — and it should log the failure rather than
silently retrying, which is a bug worth avoiding by design.

**It refuses everything that needs her.** Then it has no way to ask, and it is
behaving correctly. Either give it a channel to her, or configure the tiers
she is willing to stand behind in advance — and be clear which one you have.

**Two ledgers.** The surface is recording decisions locally instead of making
them at the authority. The record belongs to the authority; the surface is a
way of reaching it.
