# Owner authority

Decide what other people's AI agents may do with your accounts.

When somebody else's agent asks a server for something of yours — your
brokerage, your clinic, your inbox — that server cannot answer. The data is
yours. This ability is what answers: it holds your key, states your terms to
the agent, and puts the decision to you when it matters.

It is not an agent and it does not act for you. It is the thing that says no.

## Install

```sh
cd abilities/u4a-owner-authority/0.1.0
pip install httpx cryptography
```

## Configure

| Variable | Meaning |
|---|---|
| `U4A_AUTHORITY_URL` | your authorization server |
| `U4A_AUTHORITY_NAME` | the authority your request signature is rebuilt against; must match `UMA_AS_OWNER_AUTHORITY` on the server |
| `U4A_OWNER_KEY` | your Ed25519 signing key |
| `U4A_AUTO_TIERS` | tiers to answer without asking. Empty by default |
| `U4A_CA_BUNDLE` | trust bundle, if your authority is behind a private CA |

Your authorization server has to accept a key-signed request:

```
UMA_AS_OWNER_AUTH=oidc,local-key
UMA_AS_OWNER_KEY=/path/to/your-ed25519.pub
```

Only the public half goes to the server. The private half stays here.

## Run

```sh
python3 main.py
```

## What it does not do

**It cannot reach you.** pAI-OS gives an ability no channel to its person, so
a request that needs your decision is *denied* and logged. That is the safe
default — the request is pending precisely because you have not said yes — but
it means the useful configuration today is `U4A_AUTO_TIERS`, which is standing
consent you set rather than a judgement this process made.

Giving it a way to actually ask you is the open question, and the most
interesting one: `sign()` never returns private key material, so a key the host
holds — an enclave, a passkey, the webauthn support already in the pAI-OS
backend — would work unchanged.

## More

- Protocol and findings: <https://github.com/nickgamb/uma4agents>
- The binding: `docs/KWAAI-BINDING.md`
