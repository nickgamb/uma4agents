# The minimal deployment

*A test harness, not a deployment. If you are looking for the argument that
agent identity stays on the requesting side, that is [FLOW.md](FLOW.md).*

The reference architecture is a brokerage's: an identity provider, a
replicated authorization server on Postgres, a gateway carrying the
enforcement obligations, a certificate authority, a DNS zone. Thirteen
containers. That is the right shape for a firm holding other people's assets,
and it is also a lot of infrastructure to look at when the question is *how
much of this is the protocol?*

This is the answer, run rather than argued.

![The reference architecture and the minimal fixture, side by side, with the
four beats unchanged across both](reference-vs-fixture.svg)

```
make fixture
```

Two containers. No `make init`, no certificate, no DNS zone, no sudo, no host
state at all. Cold start under ten seconds once the images are built, and about
90 MB resident. And the same four
beats, the same terms, the same proof-of-possession token, the same refusals.

## What was removed, and what it cost

| Removed | Replaced by | Cost |
|---|---|---|
| Keycloak | a key Alice holds | she enrols one public key instead of running an IdP |
| Postgres ×3 | the in-memory store | state does not survive a restart, and single-use is only indivisible within one process |
| agentgateway + uma-pep | the resource enforcing in-process | the resource has authorization code in it |
| mkcert CA, DNS zone, edge | plain http on the container network | no transport confidentiality — a lab-only trade |
| push registration | the pull that was already the default | none; this was already true |

The middle two are the ones to argue about. The rest are the point.

## The one piece that could not be removed

Everything else in this profile was already portable enough to strip. The owner's
authentication was not: `uma-as` validated her OIDC token against a Keycloak
realm, so an authority meant to be *personal* still required her to stand up an
identity provider before she could answer a single request.

That is now a choice:

```
UMA_AS_OWNER_AUTH=oidc        # the default; right where an IdP already exists
UMA_AS_OWNER_AUTH=local-key   # she signs her own requests with her own key
```

In `local-key` mode the owner API takes an RFC 9421 signature over
`@method @authority @path authorization` — the *same message-signature profile
the agent uses to prove possession of a grant*, pointed at the owner. The
authority holds one public key and checks a signature against it.

There is no account, no session, no bearer token, nothing issued and nothing to
revoke centrally. If she wants a new credential she makes a new key and enrols
it.

Two things worth noticing about that:

**It reuses the verifier that was already there.** `lib/uma4a_http_sig.py`
verifies agent signatures at the enforcement point and the owner's authority's
signature at the protected discovery endpoint. This is the third direction
through the same code.

**The authority comes from configuration.** `UMA_AS_OWNER_AUTHORITY`, never the
`Host` header — the same rule the rest of the profile follows, and it does not
relax because the caller happens to be the owner.

## Try it

```bash
make fixture                    # brings it up and checks the whole grant
make owner ARGS=pending   # what is waiting on her
make owner ARGS="approve fam_..."
make fixture-down
```

`clients/owner-cli/owner.py` is her side of it: about 200 lines, no dependency
on this repo's services beyond one URL and her key.

## What this is not

Not a recommendation. A deployment holding other people's assets should have
every one of the things this configuration removes — an audit trail that
survives a restart, a store where "spent once" is indivisible across replicas,
TLS, an enforcement point the resource cannot bypass.

The claim is narrower: **the protection is a property of the protocol rather
than of the stack.** An owner's authority can therefore live somewhere small —
a laptop, a home server, a personal AI — and still be the thing that decides.

That last one has a binding of its own: [KWAAI-BINDING.md](KWAAI-BINDING.md).

## One that cost an hour

Both compose files define a service called `uma-as`. Under one project name —
which is the default, taken from the directory — `make fixture` did not start
a second authorization server beside the reference stack's. It **replaced** it,
with a configuration that accepts only her device key, and every OIDC owner
request in the running reference deployment began failing.

`compose.fixture.yml` now declares `name: uma4agents-fixture`. Worth knowing if you
keep a second stack alongside the first: compose isolates by project, and two
files in one directory share a project unless told otherwise.

## Findings this produced

**Owner authentication belongs in the profile.** UMA 2.0 and FedAuthz say
nothing about how the resource owner authenticates to her own authorization
server, because in 2018 the answer was obviously "the AS is a web application
and she logs in." Once the authority can be personal, that answer stops being
obvious, and a profile that is silent leaves every implementer to invent it.
A key-based mode costs one code path and removes the last dependency on
centralized identity.

**The pull was already decentralized and we were not saying so.** Registration
by publication means no federation is pre-established: a resource server
publishes, and whichever authority the owner designates reads it. Onboarding is
one URL. That was true before this branch — it just was not demonstrated
anywhere you could see it in eight seconds.
