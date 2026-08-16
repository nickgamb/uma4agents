# kwaai — U4A as an ability of a personal AI

A personal AI that holds its person's key can answer, on her behalf, when
somebody else's agent asks for something of hers. That is the whole binding.

The write-up is [docs/KWAAI-BINDING.md](../docs/KWAAI-BINDING.md); this is
what is in the directory.

```
ability/u4a_authority.py   the ability. ~200 lines, none of it protocol.
abilities/                 the same thing packaged the way pAI-OS installs it:
  u4a-owner-authority/       abilities/<id>/<semver>/, with a metadata.json
    0.1.0/                   its own AbilitiesManager parses.
Dockerfile                 pAI-OS from the pinned upstream ref, with the
entrypoint.sh              ability installed and both started.
paios_check.py             runs inside that container: the OS finds the
                           ability, the ability decides, one decision is
                           refused because it cannot reach her.
host_demo.py               a personal AI you can be: a key in a file, and a
                           terminal where the person would be.
check.py                   headless, against the full reference stack
```

## Run it

Against the real stack, with her portal and her identity provider up:

```bash
make up
make kwaai-check
```

Interactively, against the fixture:

```bash
make fixture
make kwaai-host              # each request is put to you
make kwaai-host AUTO=tier1   # standing approval for one tier
```

## The interface

Four methods. A host that can do these can host the owner's authority:

| | |
|---|---|
| `sign(payload)` | signs with her key, which never leaves the host |
| `public_key_pem()` | enrolled once with her authorization server |
| `ask(request)` | puts a decision to her; may wait indefinitely |
| `log(event, detail)` | whatever the platform does with a record |

`ask` is the one worth dwelling on. The agent waiting on the other side is
holding a ticket, not a connection, so an answer tomorrow is still an answer.
A host is free to notify, batch, or sit on it.

## Inside pAI-OS

The lab runs it for real, as an ability of theirs rather than a process of
ours:

```bash
make up
make paios          # her personal AI starts answering
make paios-check
make paios-down     # hand the decisions back to her portal
```

In Kubernetes: `make k8s-paios`, `make k8s-paios-check`, `make k8s-paios-down`.

## What it cannot do

**It cannot reach her.** pAI-OS starts an ability as a process configured by
environment variables and gives it no channel to its person. So `ask()` is
unimplementable, and the ability denies anything on an ask-me tier and logs
why. Standing consent (`U4A_AUTO_TIERS`) works; judgement does not.

That is the open question, and the most interesting one in the binding.
[docs/KWAAI-BINDING.md](../docs/KWAAI-BINDING.md) has the rest of them.
