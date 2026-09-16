---
templateKey: doc
title: Choose an enforcement point
description: What the component that refuses has to be able to do, the two shapes it can take, and how to keep one implementation behind both.
diagram: two-hosts
diagramCaption: Both hosts are conformant. What must not happen is two implementations of the decision.
next:
  - title: Issue the challenge
    to: /docs/guides/challenge/
    blurb: The first thing your enforcement point has to get right.
  - title: Proof-of-possession
    to: /docs/overview/proof-of-possession/
    blurb: The verification it performs on every authorized call.
---

The enforcement point is the component that says no. It sits in front of the
resource, and everything the owner's authority decides is worthless unless
something reliably declines the calls she has not agreed to.

This is the role with the most candidates in a typical stack and the sharpest
constraints, so it is worth choosing deliberately.

## What it must do

Five obligations, and a candidate that cannot do all five is not an enforcement
point for this profile:

1. **Refuse before forwarding.** The resource must never see an unauthorized
   call. A component that observes traffic after the fact is a monitor.
2. **Return a structured challenge.** Not a bare 403 — a body carrying the
   ticket and the address of the authority. See
   [Issue the challenge](/docs/guides/challenge/).
3. **Verify a request signature.** Reconstruct the signature base and check it
   against the key named in the grant.
4. **Check scope and operation binding.** Does this grant cover this tool, and
   for a single-use grant, this exact operation.
5. **Spend a single-use grant, atomically and last.**

Notice what is absent. It does not decide policy, it does not know what the
owner's terms say, and it holds nothing that would let it find out. It performs
obligations for an authority it does not hold.

## Two shapes

**As a callout.** A gateway in front of the resource asks an external
authorization service for a verdict before forwarding. Most API gateways and
service meshes have a mechanism for this — external authorization, an authorizer
plugin, a filter.

**Embedded.** The same logic runs inside the resource itself, as middleware.
No gateway in the path at all.

Both are legitimate and the choice is usually made for you by what is already in
your stack. What matters is that you do not end up with two implementations.

## Keeping one implementation

The trap is obvious in hindsight: the callout version reads a gateway's request
object, the embedded version reads a web framework's request object, and the two
drift. Six months later they disagree about something subtle and nobody knows
which is right.

The fix is to express the core in **facts** rather than in any server's request
type. Extract what the decision actually depends on — method, authority, path,
the body digest, the token, the tool name and its arguments — into a plain
structure, and write the enforcement logic against that.

Each host then does one small job: turn its own request into facts, and turn a
decision back into its own response type.

The lab does this in `lib/uma4a_pep.py`, where `AuthzFacts` is the input and
`Decision` is the output, and `make embedded-check` runs the entire grant with
no gateway in the path to prove the two hosts reach identical verdicts from one
implementation. `make k8s-embedded-check` runs the same grant in the cluster,
where the two shapes stand side by side against one authority and everything
else — the mesh, the waypoint, the namespace boundaries — is still in the way.

## Choosing a gateway

If you go the callout route, three questions decide it.

**Can the authorization service control the response body?** Many ext-authz
implementations let the authorizer return only a verdict, or a verdict plus
headers. You need the body, because the challenge carries the ticket.

**What happens to the request body?** The authorizer usually needs to see it, to
know which tool is being called. Find out what your gateway does when the body
exceeds its buffer — the honest answer is often that it **truncates and
forwards** rather than refusing, sometimes contrary to its documentation. A
cut-off JSON body does not parse, the tool name vanishes, and deny-by-default
catches it while reporting something misleading like "unknown method".

Check for the truncation flag and fail closed on purpose.

**What identity does the second hop carry?** Behind an L7 proxy, the call from
the proxy to the resource carries the *proxy's* identity, not the caller's. Any
policy naming principals has to account for that or everything is refused after
the rule meant to permit it already said yes.

## The rule that makes it portable

Take authorization inputs from your configuration and from the credential.
Never from the layer that delivered the request.

The concrete case: reconstructing an RFC 9421 signature base needs an authority.
Take it from the `Host` header and you have a security bug — an authority the
caller can set — and a portability bug. Moving the enforcement core between two
gateways, everything survived except that: `Host` arrives as the authorization
service's own address, and no configuration changes it.

A verifier that read the transport would have broken silently, with signatures
failing for a reason nothing in the logs would name.

## Verify your choice

Whatever you pick, these are the checks worth having before you build anything
on top of it:

- an unauthorized call is refused **and** the response body carries a ticket
- a request with a valid signature over a modified body is refused
- a grant for tool A presented against tool B is refused
- an oversized body is refused with a named reason rather than truncated
- the resource is unreachable except through the enforcement point

That last one is easy to assume and easy to get wrong. In the lab it is an
assertion in the policy suite, run from the requesting party's namespace, that
the vault cannot be reached directly.
