---
templateKey: doc
title: Compared to agent identity work
seoTitle: "AAuth, Web Bot Auth, CIMD and enterprise agent authorization compared"
description: AAuth, Web Bot Auth, CIMD and enterprise-managed agent auth — what each answers, and what is left over.
next:
  - title: Identity is not authorization
    to: /docs/overview/identity/
    blurb: The distinction this page depends on.
  - title: Glossary
    to: /docs/overview/glossary/
    blurb: Terms used across all of these.
---

Most current work on agents is identity work, and this profile consumes it
rather than competing with it. The distinction that keeps the comparison honest
is [identity is not authorization](/docs/overview/identity/): these answer *who
is asking*, and something still has to answer *may they*.

## AAuth

[AAuth](https://github.com/dickhardt/AAuth) gives an agent a verifiable
identity. An agent provider issues an agent token that binds an
`aauth:local@domain` identifier to the key the agent signs with, and publishes
the keys that verify it. Around the token, AAuth defines access modes of its
own, in which a person server obtains authorization for the agent from a
resource's access server.

This profile **accepts the agent token** as one way an agent identifies
itself, beside a bare key, a CIMD document, a Web Bot Auth directory and an
ID-JAG. It verifies the token against the keys its issuer publishes, with TLS
on the issuer's origin as the trust root, and files the agent under the
token's subject rather than its key, which rotates every session. It does not
use AAuth's access modes: the grant is UMA's, decided by the owner's
authorization server.

A sub-agent's token names its parent in `parent_agent`, and the profile reads
that as a lineage the issuer has attested; see
[sub-agent grants](/docs/overview/subagent-grants/). What the profile checks is
specified in [its AAuth draft](/spec/draft-gamb-uma4agents-aauth-00.html).

## Web Bot Auth

A directory where an operator publishes the keys its agents sign with, so a
server receiving a signed request from a bot it has never seen can attribute
the key.

The profile uses it as **discovery, never as authority**. A stranger's
authorization server can look up a key it has not seen and say something true
about who published it. The verifying key remains the one named in the grant.
Treating a self-published directory as an authorization input would mean anyone
who can publish a directory can influence a decision.

## CIMD

Client ID Metadata Documents let a client be described by a URL rather than by
pre-registration — useful precisely when the requester was never registered with
the service, which is the normal case for an agent from another organisation.

Used here for **display only**: the owner approving a first contact can be shown
who operates this agent, resolved and self-reference-checked. It never becomes
an authorization input, and the connection handle does not depend on it.

## Enterprise-managed agent authorization

Schemes where an enterprise's identity provider federates agent access to
services the enterprise has arranged — an admin consents once, org-wide, and
agents inherit that.

This is a real case and these schemes handle it well. It is worth being precise
about why it is a different case: the enterprise **is** the resource owner
there. The admin who consents has standing to consent, because the data belongs
to the organisation.

Collapse the owner into the enterprise and the model works. The case this
profile addresses is the one where you cannot: Alice is not an employee of the
brokerage, her advisor works somewhere else again, and no admin anywhere has
standing to agree on her behalf. That is the general case an agent economy is
made of, and the enterprise case is the special one where two parties happen to
be the same.

## The axis underneath all of these

There is a pattern worth naming, because it explains why so much adjacent work
looks similar and lands differently.

Most of it is **identity-provider centric**. The IdP is where agents are
registered, where authority is minted, and where policy about them lives.
Cross App Access and ID-JAG have an enterprise IdP issue scoped tokens onward.
The Agent Identity Protocol draft has a registry assign identifiers and a proxy
enforce policy the registry's operator wrote. Karl McGuinness's writing on the
enterprise agent control stack takes the same position — the control plane sits
with the organisation's identity infrastructure.

That is the correct design when the organisation running the IdP is the party
with authority over the data. In an enterprise, it usually is.

This profile is **resource-server centric**, or more precisely
resource-*owner* centric. The authority is on the side of whoever the resource
belongs to, and the resource server enforces for an authority it does not hold.
No IdP anywhere in the picture has standing to decide on Alice's behalf, because
she is a customer of the brokerage rather than a member of it.

Neither position is wrong. They are answers to different questions about who the
owner is, and an agent economy will need both — an enterprise IdP governing the
agents an organisation runs, and something owner-side governing what those
agents may reach that belongs to somebody else.

The lab now runs both in one negotiation. An enterprise identity provider
asserts which employee is behind an application and that an administrator
approved its reach; the member's authority decides what may then be done to
the resource, on whose terms. See
[Cross App Access](/docs/overview/cross-app-access/).

## Two levels, and everything else is description

Worth stating precisely, because it is checkable and because getting it wrong
is quiet. Running the same negotiation against all four of the above produces
**two** connection handles, not four: either the key is the identity, or a
verified issuer stands behind it. A CIMD document and a Web Bot Auth directory
change nothing about how an agent is filed or judged — the terms proffered and
the grant issued are identical with or without them.

That is the design working. See [identity stays where it
is](/docs/overview/flow/).

## What is left over

Once you know which agent is calling, who operates it, and that it holds the key
it claims, you still do not know:

- whether the **owner** has agreed
- on what **terms**, and for how long
- what happens when the answer is **ask me** and she is asleep
- how she **withdraws** it later, for that agent alone

Those four are what the rest of these docs are about.
