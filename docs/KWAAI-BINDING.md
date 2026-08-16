# The personal-AI binding

A personal AI is the natural home for the owner's side of this protocol. It
already runs on her device, it already holds her keys, and it already has her
attention. What it has been missing is a way to decide anything on her behalf
that somebody else's server will honour.

That is what U4A gives it, and the finding is how little the integration takes.

![A personal AI deciding for its person: the agent asks, the server refuses and
names her authority, her terms are stated and signed, she is asked when it
matters, and a permission is issued for one operation](kwaai-flow.svg)

## What the personal AI has to do

Two things. Hold her key, and ask her.

```python
class Host(Protocol):
    def sign(self, payload: bytes) -> bytes: ...        # her key never leaves
    def public_key_pem(self) -> bytes: ...              # enrolled once
    def ask(self, request: Request) -> bool: ...        # unbounded wait
    def log(self, event: str, detail: dict) -> None: ...
```

None of the protocol is its job. The ticket, the terms, the signed agreement,
the proof-of-possession token, the single-use burn and the ledger all belong to
the authorization server. The ability is an adapter — roughly 200 lines in
`kwaai/ability/u4a_authority.py`, and most of that is the request shape a
person needs in order to answer.

The reason it is that small is structural rather than lucky: U4A already puts
the deciding authority on the owner's side, and already lets her authenticate
to it with a key rather than a login. A personal AI does not have to become an
authorization server. It has to become the thing that answers one.

## The one change this needed

Before this branch, the owner authenticated to her own authority with an OIDC
token from an identity provider. That is right for a deployment that has one
and wrong for a device that does not — a personal AI cannot reasonably require
its person to stand up Keycloak first.

So the owner API now accepts either, or both:

```
UMA_AS_OWNER_AUTH=oidc              # her browser session
UMA_AS_OWNER_AUTH=local-key         # a key her device holds
UMA_AS_OWNER_AUTH=oidc,local-key    # both — what the reference stack runs
```

`local-key` verifies an RFC 9421 signature over
`@method @authority @path authorization` against her enrolled public key — the
same message-signature profile the agent uses for proof-of-possession, pointed
at the owner, verified by the same module.

A request with a body must also cover an RFC 9530 `Content-Digest`, and the
owner API refuses one that does not. Those four components say who is asking
and what of; they say nothing about the bytes, and this endpoint's whole
meaning is a word in its body. See recommendation 11 in FINDINGS.

**Both is the interesting configuration**, and it is a finding in its own
right: a person reaches her own things more than one way. A browser on her
laptop, an app on her phone, a personal AI holding a key. Each credential is
independently sufficient and independently revocable, and neither is a fallback
for the other. UMA 2.0 and FedAuthz are silent on owner authentication
entirely, which is defensible for 2018 and is not once the authority can be
personal.

## Packaged as a real ability

pAI-OS takes an extension as a directory under `abilities/<id>/<semver>/` with
a `metadata.json` in it — "akin to plugins in WordPress", as their own README
puts it. Ours is `kwaai/abilities/u4a-owner-authority/0.1.0/`, and pAI-OS finds
it with its own `AbilitiesManager`, not with our reading of its layout.

One thing to flag for Kwaai, because it cost us an afternoon. pAI-OS **does**
publish a manifest schema — `abilities/schema-metadata.json`, with a
`validate-metadata.py` beside it — but the schema has drifted from the runtime.
It types `dependencies` as an object keyed by platform; the runtime and every
shipped ability use an array. Their own validator rejects their own abilities:

```
$ python validate-metadata.py chroma/0.1.0
ValidationError: [{'id': 'chromadb', 'type': 'python', …}] is not of type 'object'
On instance['dependencies']:
```

So our `metadata.json` follows the runtime and the shipped abilities rather
than the schema, and satisfies the schema in every other respect. Which of the
two is authoritative is a question for them, and worth an issue either way.

## Running it

Against the full reference stack — her identity provider, her replicated
authority, the gateway, the vault and her portal all present:

```bash
make up
make kwaai-check
```

```
== Two credentials, one owner ==
   her portal session: still accepted
   her device key, held by a personal AI: also accepted
   neither is a fallback for the other

   [her personal AI] An agent you have not met wants access: Suitability review…
   [agent] grant issued
   the call went through
   her ledger, read from the portal: includes the one the personal AI made
```

That last line is the one that matters for adoption. Her portal and her
personal AI are two surfaces onto one record: a decision made by either appears
in the same ledger, correlated to the same negotiation. Nothing forks.

Interactively, against the minimal fixture:

```bash
make fixture
make kwaai-host              # puts each request to you
make kwaai-host AUTO=tier1   # standing approval for one tier
```

## Inside pAI-OS

The above runs the ability as a process of ours. The lab also runs it as an
ability of theirs: `kwaai/Dockerfile` builds Kwaai's pAI-OS from the pinned
upstream ref `make fetch-upstream` clones, installs our directory under its
`abilities/`, and starts both.

```bash
make up            # her portal demo, as always
make paios         # add her personal AI
make paios-check
make paios-down    # back to the portal demo
```

It is a second surface onto her decisions, not a replacement for her portal.
The two are alternatives — see [DEMOS.md](DEMOS.md).

```
== pAI-OS finds the ability ==
   u4a-owner-authority — Owner authority (UMA for Agents)
   start: python3 main.py   dependencies: httpx, cryptography
   found by its own AbilitiesManager, under abilities/<id>/<semver>/

== A tier she has given standing consent to ==
   granted — the personal AI answered, she was not disturbed

== An ask-me tier, which needs her ==
   refused — and that is correct
```

Two upstream accommodations were needed, both small and both noted in the
Dockerfile: the pinned ref imports `pkg_resources`, so setuptools is held below
81, and `PAIOS_HOST` defaults to localhost, which binds to nothing another
container can reach.

**The refusal is the finding.** pAI-OS starts an ability as a process
configured by environment variables. It gives it no channel to its person — no
notification, no prompt, no inbox. So `ask()` cannot be implemented, and the
ability denies and logs why:

```json
{"event": "cannot-ask", "family": "trade:execute",
 "outcome": "denied — no channel to her"}
```

That is the safe answer: a request pends precisely because she has not said
yes. But it means the only thing that works unattended is `U4A_AUTO_TIERS`,
which is standing consent she configured rather than a judgement the process
made. A personal AI that cannot reach its person can hold a standing policy;
it cannot hold her attention.

## Open questions for Kwaai

1. **A channel to the person.** This is the one that matters. An ability has
   no way to ask. `ask()` is the whole difference between standing consent and
   a personal AI, and it needs a host affordance that does not exist yet.
2. **Whose key.** Can an ability sign with a key the host holds and will not
   release — an enclave, a passkey, the webauthn already in their backend? The
   ability only ever calls `sign()`, so the answer being yes costs nothing and
   is strictly better than a key in a file, which is what it does today.
3. **Which manifest is authoritative**, the schema or the runtime. See above.
4. **What she sees.** The request carries the exact operation and the terms the
   agent signed. How a personal AI puts that to a person, in a sentence, is a
   product question we have deliberately not answered.

## See also

- [FLOW.md](FLOW.md) — why she does not need to know what the asking agent is
- [PROTOCOL.md](PROTOCOL.md) — the wire contract the ability does not implement
- `kwaai/README.md` — the directory itself
