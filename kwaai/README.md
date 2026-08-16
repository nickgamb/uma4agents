# kwaai — U4A as an ability of a personal AI

A personal AI that holds its person's key can answer, on her behalf, when
somebody else's agent asks for something of hers. That is the whole binding.

The write-up is [docs/KWAAI-BINDING.md](../docs/KWAAI-BINDING.md); this is
what is in the directory.

```
ability/manifest.json      what an ability of this kind needs from a host.
                           PROPOSED — the field names are ours, pending the
                           real pAI-OS schema. The `requires` block is the
                           part worth reviewing.
ability/u4a_authority.py   the ability. ~200 lines, none of it protocol.
host_demo.py               a stand-in personal AI: a key in a file, and a
                           terminal where the person would be.
check.py                   headless, against the minimal fixture
check_full.py              headless, against the full reference stack
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

## Not yet true

Nothing here has run against pAI-OS. The manifest is a proposal, and
`host_demo.py` is a stand-in. Both exist so the binding can be reviewed and
argued with before anyone writes integration code.
