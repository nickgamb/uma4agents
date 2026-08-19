---
templateKey: doc
seoTitle: "UMA 2.0 vs UMA for Agents: what carries into the agent era"
title: Compared to UMA 2.0
description: What this profile keeps, what it changes, and why each change was necessary rather than preferred.
diagram: compare-uma
diagramCaption: The verdict pass from FINDINGS.md, as three columns.
next:
  - title: Deviations, in detail
    to: /docs/reference/deviations/
    blurb: The exact list, with the UMA 2.0 baseline for each.
  - title: Findings
    to: /docs/reference/findings/
    blurb: What we are asking the specification authors to consider.
---

This is a profile of UMA 2.0, not an alternative to it. The grant, the ticket,
the token endpoint, the claims-gathering loop and the protection API are all
UMA's, and where the profile could use a UMA mechanism unchanged, it does.

What changed is what the requesting party turned out to be.

## What is unchanged

The **grant type** is UMA's: present a ticket, be told what is missing, come
back with it. The **permission ticket** is UMA's, including its single-use rule.
The **protection API** shape is FedAuthz's, and the resource server holds a PAT
issued in the owner's name to call it.

Most importantly the **topology** is UMA's — an authorization server on the
owner's side that the resource server does not control. That is the idea worth
preserving, and it is the one nothing else in the market provides.

## What changed, and why

**Terms became an artifact.** UMA gathers claims; it does not give the owner a
way to state requirements the requester must accept. The profile adds a terms
document the authorization server dictates and the agent signs. Without it,
"she consented" is a claim nobody can check afterwards.

**The token stopped being bearer.** UMA's RPT is a bearer token. When the holder
is somebody else's autonomous agent, a bearer token is a credential that works
for whoever picks it up. The profile binds the grant to a key, and for sensitive
operations to a single operation.

**Registration became pullable.** FedAuthz registers resources by pushing them
to the authorization server. The profile has the resource server publish
[RFC 9728](https://www.rfc-editor.org/rfc/rfc9728.html) metadata and the
authorization server read it. Push still works; the point is that the
specification should not require it.

**The requesting agent came back.** UMA's 2010 drafts distinguished the
requesting party from the requesting agent. 2.0 collapsed them, reasonably at the
time. Agents make the distinction matter again — see
[the three parties](/docs/overview/parties/).

**The challenge became parameters.** UMA carries the challenge in
`WWW-Authenticate`, which assumes an HTTP binding. Expressed as parameters, the
same challenge rides a JSON-RPC envelope byte for byte, which is what let the
profile bind to MCP without inventing a second challenge format.

## Where the profile is stricter

UMA 2.0 does not say **where** in enforcement a single-use token is spent. The
intuitive order — consume first — lets an unsigned replay destroy an approval the
owner just gave. The profile makes the order normative and puts the burn last.

It also says single-use must mean
[indivisible](/docs/overview/single-use/), which UMA leaves to the implementer
and which is invisible until there are two replicas.

## Where UMA is stricter than the profile

Worth saying, because it cuts both ways. UMA anticipates multiple authorization
servers per resource server, and RFC 9728 makes `authorization_servers` an
array. The lab configures exactly one. Owners who each brought their own
authorization server is the general case, and this deployment does not
demonstrate it.

## What we are asking for

The changes above are not local preferences. Each is written up as a
[recommendation](/docs/reference/findings/) with the problem it solves and the
code that demonstrates it, because the useful output of a proof of concept is a
list of things the specification could say.
