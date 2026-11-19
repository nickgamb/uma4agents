---
templateKey: doc
title: Deploy it at scale
description: Separating the parties so the seam is enforced rather than described, replicating an authority correctly, and the checks that prove it held.
next:
  - title: The wire contract
    to: /docs/reference/wire-contract/
    blurb: Everything that travels between the parties, in one place.
  - title: Revocation and the ledger
    to: /docs/overview/revocation/
    blurb: What the owner can see and undo once this is running.
---

A single-machine deployment can demonstrate the protocol and cannot demonstrate
the property the protocol exists for. When every party runs on one network as one
identity, "the resource server cannot read the owner's policy" is a claim about
source code.

This guide is about making that claim enforceable, and about what breaks when
the number of agents stops being one.

## Prerequisites

- The [four beats](/docs/overview/four-beats/) working somewhere
- A platform with workload identity and authorization policy between workloads
- A store that survives an instance disappearing

## 1. Give each party its own identity boundary

Divide by **party**, not by process. The lab uses one namespace each:

| Party | Runs |
|---|---|
| The public on-ramp | the edge gateway and its DNS |
| The resource owner | her identity provider, her authority, her database, her portal |
| The resource server | the enforcement point and the resource behind it |
| The requesting party | the agent, whatever operates it, and the directory its people sign in with |
| The requesting party's issuer | the person server that vouches for its agents, kept apart from them |

The pair that carries the argument is owner and resource server. The resource
server holds the assets and enforces the policy, and can never read it.

## 2. Write the policy that proves the seam

Deny by default between namespaces, then permit exactly the paths the protocol
needs. The enforcement point must be able to reach the authority's protection
endpoints and its published keys, and nothing else.

Then write the **refusals** as assertions. A policy suite that only tests the
allows would pass on a cluster with no policy at all.

The sharpest pair is two assertions against the same port on the same workload:

```
the enforcement point cannot read the owner's policy      403
the enforcement point can reach her published keys        200
```

Same source, same destination, same port, opposite outcomes. That is the
cross-principal argument stated as something CI can fail on.

Add the negative that people forget: from the requesting party's namespace, the
resource must be unreachable except through the enforcement point.

## 3. Replicate the authority properly

More than one instance, sharing state, signing with **one** key held as a secret
rather than a key minted per pod. Three instances with three keys is three
authorities wearing the same name.

Two consequences follow immediately:

- **Single-use must be indivisible**, because "once per process" is now
  meaningless. See [that guide](/docs/guides/indivisible/).
- **Reading logs from one pod will mislead you.** A single negotiation's events
  are spread across every replica. Correlate by negotiation id from a shipped
  event stream, not by tailing a deployment.

Held tickets, pending decisions and the owner's ledger all belong in the shared
store for the same reason.

## 4. Get the certificate story right

Mint a CA in the cluster and distribute it to every namespace at the same path
and under the same environment variables everything already reads. No
certificate installed on anyone's machine, and no application code that knows
which shape it is running in.

One trap worth naming: on some runtimes, setting a trust file **replaces** the
system trust store rather than adding to it. That is fine inside a cluster where
every name is yours, and it breaks the moment a component has to fetch something
from a public URL — a tunnelled hostname, a real identity provider. When that
happens, separate the two: one bundle for the private mesh, the platform trust
for everything else.

## 5. Keep published identifiers and fetch locations separate

If the owner's authority pulls its registry from the resource server's
*published* metadata, it has to dereference the public URL from inside the
cluster. Shortcutting to an internal service name means the document it fetched
is not the document the public gets, and the pulled copy proves nothing.

Route the public names internally at the DNS layer instead. TLS is unaffected,
because the server name and host come from the URL rather than from the DNS
answer.

The same split shows up whenever the deployment is reachable under two names —
a tunnel, a preview environment, an internal address alongside an external one.
The rule that resolves every case: **an issuer is an identifier, a metadata URL
is a fetch location, and they are allowed to differ.** Configure them
separately.

## 6. Do not gate readiness on a call that comes back to you

The intuitive readiness signal for an authority in a pull profile is "my
registry is populated". It deadlocks.

The pull dereferences a public hostname that routes back to this same service
for a key check. Gate readiness on the pull and the service has no ready
endpoints, so the back-call fails, so the pull fails, so readiness never turns
green. What an operator sees is a healthy-looking pod stuck at zero-of-one, then
one quiet log line.

Keep health independent of the pull, and expose "has the registry landed" as a
separate endpoint for waits and dashboards — never as a probe.

## 7. Scale to agents you did not configure

An owner with one agent is a demo. The design has to hold when arbitrarily many
agents want access to her resources, most of which she has never heard of.

Nothing in the four beats requires the owner's side to know an agent in advance.
An agent arrives with a key, gets challenged, signs terms, and pends as first
contact. What has to be true for that to scale:

- **The connection handle follows the identity level.** A pseudonymous agent is
  keyed by its key thumbprint, which means the key must persist for the
  relationship to persist. An identified agent is keyed by issuer and subject,
  because session keys rotate and a thumbprint-keyed connection would forget it
  every session.
- **Registration is not a prerequisite.** No client registry, no allow-list of
  agents. The owner's decision at first contact is the registration.
- **Per-agent state is bounded.** A connection, its terms agreements, its live
  grants. Nothing grows with the number of agents except rows.
- **The owner's queue is the scarce resource.** N new agents means N first-contact
  decisions. Tiering exists so that number stays proportional to what she cares
  about rather than to traffic.

Test it as a load test that mints N distinct keys and asserts N independent
connections, each with its own terms agreement and its own grants, none of them
able to use another's.

## 8. Prove it survives failure

Put a request in front of the owner. Delete the authority instance holding it.
Kill the database primary. Wait for failover. Then have her answer *that same
request*.

Starting a fresh negotiation afterwards proves the system still works, which is
not the question. The question is whether the specific thing she was asked
survived.

One failure this catches and nothing else does: an authorization rule naming
principals silently excludes anything outside the mesh. A database operator that
was named correctly but never enrolled arrives with no identity at all — the
database keeps serving and quietly stops being able to fail over. Invisible until
the day it matters.

## Verify it

- Cross-namespace refusals assert as loudly as the allows
- The resource is unreachable except through the enforcement point
- Every authority replica verifies a token signed by any other
- A negotiation survives losing the instance that started it
- N distinct agents hold N distinct connections that cannot cross
- Revoking a connection kills its live grants immediately

## Troubleshooting

**Every call is 403 and the gateway says only "external authorization failed".**
An authorization rule is being evaluated at the wrong layer — commonly a rule
naming an HTTP path that got bound in a way that only permits L4 evaluation, so
it denies outright.

**Traffic bypasses the proxy you inserted.** A gateway load-balances to endpoint
addresses rather than to the service address, so a service-scoped proxy is never
in the path. Label both the service and the pod template.

**Everything is refused after the rule meant to permit it said yes.** The second
hop carries the proxy's identity, not the caller's. Name it.

**Signatures fail only in the deployed shape.** Something in the signature base
is coming from the transport rather than from configuration. Authority first.
