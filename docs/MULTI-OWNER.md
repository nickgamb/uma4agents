# Many owners, and an authority that is hers

Two questions that sound different and are the same question from two sides:

- can one resource server hold many people's accounts, each governed by its
  own owner's policy?
- can an owner name an authorization server the resource server has never
  heard of?

The first is what a firm asks. The second is what a person asks. A deployment
that answers only the first has multi-tenancy — one operator running one
authority over many customers, which is the arrangement UMA was written to
replace. Answering the second is what makes the first worth having, because it
is the point at which "her policy" stops being a row in someone else's table.

The lab answers both with two owners who differ in nothing but which one they
are.

Run it:

```bash
make multi-owner-check       # two owners, one resource server, nothing shared
make establishment-check     # an authority nobody configured the firm against
```

In the cluster, where the separation is namespaces rather than variables:
`make k8s-multi-owner-check` and `make k8s-establishment-check`.

![Two owners of one resource server. Down the middle, Meridian's gateway and
the enforcement point in front of it, holding two protected resources — one
per owner — at /mcp/alice and /mcp/carol. To the left, Bob's agent, which
negotiates with both and knows nothing about either beyond what each challenge
tells it. To the right, two authorities that share nothing: Alice's, three
replicas over a synchronous Postgres cluster, provisioned alongside the
gateway and holding a client secret; and Carol's, one small process holding
its own state, which the firm was never configured against and which the
gateway had to introduce itself to by signing with the key it publishes at its
own origin. Between the enforcement point and Carol's authority, the
registration path: register, pend, her answer, then a PAT — and beneath it the
same four beats running unchanged against each
authority.](multi-owner.svg)

## What belongs to an owner

| | |
|---|---|
| Her authorization server | Named in the challenge for her resource, and nowhere else. Two owners of one resource server can name two different ones, and that is the whole of BYOAS. |
| Its signing key | An RPT for Alice does not verify against Carol's JWKS. Neither authority's key is in the other's. |
| Her identity provider | A realm of her own. An authority that accepts another party's tokens for its owner is only partly hers: whoever runs that provider can mint her. |
| Her policy — tiers, resources, standing terms | Her rules over her resources. Nothing in one owner's tiers can name another's. |
| Her terms documents | `alice/tier1`, `carol/tier1`. Dereferenceable without a token, because an agent has to read them before it has one. |
| Her record | Her ledger, her connections, her operator blocks, her pending queue and the budget that bounds it. |
| Her resource-server registry | Which servers may use her Protection API, and the status she can flip. |
| Her instance of the resource | A separate vault holding her positions, not a row in Alice's. |
| Her portal | The same Meridian UI, pointed at her authority, her realm and her vault. One image; four values differ. |

And what is shared, because it belongs to the firm rather than to either of
them: the resource server process, the enforcement point in front of it, the
gateway, the origin those publish under, and the key that identifies that
origin.

## The partition, and why it is structural

Every accessor in the store hangs off an owner rather than taking one as an
argument:

```
Store          # the backend: connections, listeners, and owner(name)
  └── OwnerStore   # every read and write, already scoped
```

`Store.owner(name)` returns an `OwnerStore`, and there is no method on it that
can reach another owner's rows. This is deliberately not a parameter threaded
through some forty methods: a parameter can be forgotten in one of them, and
the failure is silent and is the worst one this system has. Scoping that is
structural cannot be forgotten, and it has the second property that matters
here — an `OwnerStore` *is* the surface a personal authorization server needs.
The small deployment is not a special mode; it is one of these with nothing
else in the process.

`make store-test` runs the same assertions against both backends, including a
partition suite that walks every accessor and asserts that two owners' rows
never meet — and that one owner approving a resource server does not approve
it for anybody else.

How many owners live in one process is a packaging choice the grant loop
cannot observe. The compose stack runs one owner per process; the cluster runs
one per namespace; a firm could run a thousand in one. What must not vary is
which rows an owner can reach, and that is the same code either way.

## How a request says whose resource it is

On the first call there is no credential, so the path is the only thing that
can say:

| | |
|---|---|
| `/mcp/<owner>` | The protected resource, one per owner. |
| `/.well-known/oauth-protected-resource/mcp/<owner>` | RFC 9728 metadata for that resource, naming **her** authorization server in `authorization_servers`. This is where an agent finds out whose authority governs what it was just refused by. |
| `WWW-Authenticate: … as_uri=…` | The challenge names her authority. An agent that cannot be told this cannot choose one, which is why the challenge and not configuration is the answer. |
| the ticket | Carries the owner, so it resolves at the authority that minted it and nowhere else. |
| the RPT | Carries an `owner` claim, checked on every spend. |
| resource ids | `alice-vault/get_positions`, `carol-vault/get_positions`. A tool id from one namespace never resolves against another owner's policy. |

An authorization server serving one owner refuses everyone else at the door
rather than serving them and filtering — `UMA_AS_OWNER` fixes whose server it
is, and a request naming anybody else gets a 403 before any store is touched.

## Bring your own authorization server

FedAuthz begins with a resource server that already holds a PAT and says
nothing about how it got one. Where one operator runs both sides, a
provisioned client secret is a fair model of it: somebody stood up the
authority and the gateway together and configured each against the other.
Alice's relationship with Meridian still works exactly that way, and the lab
keeps it, because it is the true account of most deployments.

It stops being an account of anything the moment the authority is the owner's.
There is no point at which anyone could configure Carol's server and
Meridian's gateway against each other, because the two belong to different
people. She will not paste a secret into her brokerage's console and the
brokerage will not hold one secret per customer.

So the resource server authenticates as its origin.

```
1  register   RS  →  AS    POST /rs/register, signed (RFC 9421), no credential
2  verify     AS  →  RS    fetch the RFC 9728 document at the claimed resource
                           — and the JWKS it names — and check the signature
3  pend       AS  →  her   the registration lands in her registry as pending
4  decide     her →  AS    POST /owner/resource-servers/decision
5  PAT        RS  →  AS    POST /token, signed the same way, no client_secret
```

Nothing is provisioned in advance and no secret is ever transmitted. What is
being trusted is control of the origin — which is what the address in her
challenge already pointed at, so the check adds no party to trust that the
protocol did not already depend on.

Three things must hold about the document fetched at step 2, and each closes
one way of registering as somebody else:

| | |
|---|---|
| it claims **this** `resource` | a host cannot publish metadata about a resource it does not serve |
| its `jwks_uri` is **same-origin** | the keys come from the party being identified, not one it points at |
| it names **this** authorization server | a resource server cannot register with an authority it does not send its own callers to |

This is the same discipline the server already applies to an agent's operator
metadata (see [ASSURANCE.md](ASSURANCE.md)), with one deliberate difference:
there, a document that will not resolve leaves a claim self-asserted rather
than counting against the agent, because an operator's outage is not evidence.
Here the document *is* the credential, and a credential that cannot be fetched
has not been presented. Unreachable is refused.

### What it costs to expose

`/rs/register` takes no credential — that is the whole point of it — so
anybody can make this server fetch a URL they chose. That is inherent: origin
authentication means dereferencing the origin, and a check that only ran for
callers already known would not help the caller who is not.

What bounds it here: the document is read up to a cap rather than into memory
(`UMA_AS_RS_MAX_BYTES`), redirects are not followed, only `https` is fetched,
and a resource that did not check out is remembered as refused for a short
window (`UMA_AS_RS_MISS_TTL`) so a flood of bad registrations does not become
a flood of outbound requests.

What is *not* bounded, and should be by whoever deploys this: the set of hosts
this server will dial. The obvious control — refuse addresses on private
ranges — is wrong here rather than merely unimplemented, because the resource
server is on a private range in every deployment where the two are near each
other, including this lab. An egress policy naming what the authority may
reach is the right layer for it, and it is a deployment decision rather than a
protocol one.

### What registration does not buy

A verified signature settles who is asking. Whether they may is hers, and
`make establishment-check` is mostly about the ways of not getting an answer.
All of the refusals below are one status code from outside — the check holds
no key any origin publishes, so each of its attempts fails on the signature as
well as on the thing it is testing, and only the authority's event log
separates them. Each cause is isolated where it can be, which for the
freshness window is `make sig-test`:

| | |
|---|---|
| an origin that does not publish the key that signed | 401 `invalid_client` |
| a claim to a resource whose own metadata names another | 401 |
| a resource_uri at an origin publishing no metadata at all | 401 |
| a signature old enough to have been captured and replayed | 401 — the profile's freshness window is 60 seconds, covered on its own by `make sig-test` |
| a verified registration, before she has answered | 403 `authorization_pending`, and the call it was for stops with the same code rather than a generic failure |
| after she withdraws it | the next call stops; asking again puts it back in front of her as pending, and cannot restore itself |

Where "she" acts, the surface is her authority's owner API — `GET
/owner/resource-servers` and `POST /owner/resource-servers/decision`. Each owner's
portal renders that registry and offers Approve on a pending row;
`establishment_check.py` calls the same two endpoints directly, which is what
the portal does for her. Which surface an owner uses is hers to choose, and the
authority cannot tell the difference — it authenticates her credential, not
her client.

That last row is the one worth reading twice. A withdrawn resource server may
register again — it is the same shape as an agent she has blocked asking a
second time — and doing so lands it in `pending`, never in `active`. Asking
again is not a way to undo her answer. The resource server also throttles
itself: re-registering on every request would put the same question in front
of her as fast as traffic arrives, which is a way of pestering someone into a
yes.

### What still has to be configured, and why that is correct

The credential gap is closed. The *discovery* gap is not, and should not be:
the resource server is told which authority governs which owner
(`UMA_OWNER_AUTHORITIES`), and that is Carol declaring where her authority
lives.

There is no protocol that can remove this. Which server speaks for a person is
a fact only that person holds; a resource server that could work it out for
itself would be a resource server that could be told it by someone else. In a
product this is a field on her account profile, set by her, the same way she
sets a mailing address. What the establishment path removes is the part that
had to be arranged *between the two companies* — and that was the part that
made a personal authority impossible.

## An authority small enough to be a person's

The two authorities in the cluster are the same image running the same code
and are deployed at deliberately different sizes:

| | Alice's | Carol's |
|---|---|---|
| replicas | 3, with a disruption budget | 1, `Recreate` |
| state | a three-instance Postgres cluster, synchronous | in the process |
| footprint | ~3 × 128Mi, plus the database | 128Mi |
| provisioned with the resource server | yes, by shared secret | no, and it could not have been |

Nothing on the wire distinguishes them, and `make k8s-multi-owner-check` runs
against both without knowing which is which. That is the claim: an
authorization server is small enough to be a person's — a home server, a small
VM, an edge isolate — and the cost of that is a deployment decision rather
than a different protocol.

The single-replica shape is correct only because the store is in the process.
Two replicas of an in-process store are two authorities answering behind one
name, and a ticket minted by one would be unspendable at the other. That is
what the Postgres backend exists for, and why Carol's Deployment says
`Recreate` rather than leaving the default to make two of her during a rollout.

### What could move further out, and what cannot

Worth being precise, because "at the edge" is usually said about things that
cannot go there:

| | |
|---|---|
| `policy.evaluate` | pure — inputs to a verdict, no writes. Runs anywhere, including an isolate per request. |
| terms documents, JWKS, discovery | static artifacts. Cacheable and replicable without coordination. |
| `consume_ticket`, `consume_rpt` | **indivisible.** A single-use artifact is burned in one step that either happens or does not; a read followed by a write is a double-spend under concurrency. These serialize somewhere, and that somewhere is the authority's state. See recommendation 9 in [FINDINGS.md](../FINDINGS.md), and `make store-test`, which races 32 callers at each of them. |
| an ask-me decision | human latency. Already anywhere she is — the pend outlives the request. |

So the part that has to hold still is small and well-marked, which is the
useful finding: it is not the whole authority that resists being distributed,
it is two functions.

## Adding a third owner

There is no third kind of thing to add. An owner is:

1. a realm in the identity provider (`keycloak/<name>-realm.json`);
0. — and a portal instance, if she wants the same UI the others use;
2. an authorization server with `UMA_AS_OWNER=<name>` and her own issuer,
   signing key and hostname;
3. a route publishing that hostname;
4. an instance of the resource holding her account;
5. one entry in `UMA_EXTRA_OWNERS` and one in `UMA_OWNER_AUTHORITIES` on the
   resource server;
6. a portal instance pointed at the four of those, if she wants the same UI
   everyone else uses.

In the cluster that is a copy of `k8s/base/carol/` and the policy block that
matches it, and nothing in Alice's namespace changes. The checks are written
over a table of owners rather than over two names, so a third is a row.

## Limits

- **The realm string on the challenge is the resource server's, not the
  owner's.** `UMA_REALM` names the protection realm of the resource server —
  which is what UMA specifies — so both owners' challenges carry
  `realm="alice-vault"`. It reads as an asymmetry and is not one; it is the
  name of the thing enforcing, and there is one of those.
- **Carol's authority in the cluster loses its state if the pod restarts.**
  That is the honest cost of the in-process store, and it is why the checks
  drive establishment rather than assuming it. A person running one for real
  would give it a disk.
- **An owner is never created by a registration.** A resource server naming
  an owner that does not exist is refused; owners come from a person setting
  one up. On a server holding one owner `UMA_AS_OWNER` settles it before
  anything else runs.
- **Registration is per (owner, resource server).** One resource server
  serving two owners registers twice and holds two PATs. There is deliberately
  no cross-owner registration: it would be a single credential whose
  revocation by one person affected another.

## See also

- [PROTOCOL.md](PROTOCOL.md) — `/rs/register` and the owner-side decision endpoint
- [KUBERNETES.md](KUBERNETES.md) — the namespaces, and where each owner's parts live
- [ARCHITECTURE.md](ARCHITECTURE.md) — why the parties are separated at all
- [FINDINGS.md](../FINDINGS.md) — recommendation 9, and the establishment gap
- `services/uma-as/store.py`, `clients/demo-driver/establishment_check.py`
