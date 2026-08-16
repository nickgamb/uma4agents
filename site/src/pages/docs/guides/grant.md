---
templateKey: doc
title: Mint an operation-bound grant
description: Issuing a credential that authorizes one operation rather than a capability, and the enforcement order that makes it hold.
diagram: enforcement-order
diagramCaption: Check, then act. The burn is last because everything before it can fail.
next:
  - title: Make single-use indivisible
    to: /docs/guides/indivisible/
    blurb: The one step in the order that cannot be a read followed by a write.
  - title: Wire the owner's approval path
    to: /docs/guides/approval/
    blurb: How the pend that precedes an ask-me grant reaches her.
---

Beat four. The agreement verified, the policy allows it — or the owner said yes
— and something has to be issued.

The question this guide answers is what that credential says. A token meaning
"may trade" and a token meaning "may place this order" are the same number of
bytes and a completely different security posture.

## Prerequisites

- A verified [agreement](/docs/guides/terms/) with its hash
- An [enforcement point](/docs/guides/enforcement-point/) that can verify request
  signatures
- The agent's key, from the agreement's protected header

## 1. Decide what the token binds to

The grant carries the agent's key as a confirmation claim, so it is
proof-of-possession rather than bearer. A stolen copy is useless without the
private key.

```json
{
  "iss": "https://alice-as.uma.lab",
  "sub": "<agent id or pseudonymous handle>",
  "aud": "https://gateway.uma.lab",
  "jti": "rpt_<id>",
  "exp": 1751910000,
  "cnf": { "jwk": { "…agent signing key…": "" } },
  "permissions": [
    { "resource_id": "alice-vault/get_positions",
      "resource_scopes": ["positions:read"], "exp": 1752072800 }
  ],
  "contract": "s256:<agreement-hash>"
}
```

`permissions` is UMA's introspection array, carried as a claim inside the token
itself. That is a deliberate departure: it lets an enforcement point see the
scope of a grant without a round trip, while introspection remains the authority
on whether the grant is still live.

`contract` is the hash of the agreement. Every grant names the exact terms
behind it, so an audit does not depend on timestamps lining up.

## 2. Add the operation binding where the tier demands it

For a tier the owner marked ask-me, the token gains two more fields:

```json
  "single_use": true,
  "operation": { "tool": "execute_trade",
                 "params_s256": "<hash of the exact approved order>" }
```

The hash is over the exact parameters the owner saw when she approved. Change
the ticker, change the quantity, change anything — the hash differs and the call
is refused.

This is the difference between authority for *this trade* and *trading
authority*, and it is a hash comparison.

Hash the parameters canonically. Two JSON encodings of the same object must
produce the same hash or you will refuse legitimate calls; two different objects
must not collide. Sort keys, fix the number format, decide about whitespace once
and apply it on both sides.

## 3. Enforce in this order

When the agent retries its call with the grant, the enforcement point checks
these things, and the sequence is normative:

1. **Introspect** — is the token live, and does the connection behind it still
   stand? Authorized with the enforcement point's own credential, and
   non-consuming.
2. **Scope** — does the tool being called map to a `resource_id` present in
   `permissions`?
3. **Signature** — does the request signature verify against the key in `cnf`?
   This is the step that makes the token proof-of-possession rather than bearer.
4. **Operation** — for a single-use grant, does `params_s256` match exactly?
5. **Consume** — only now is the grant spent.

The order is the whole point. Consuming at step 1 is the intuitive placement and
it is a denial of service: anyone who observes the token can replay it unsigned
and destroy an approval the owner personally gave, without passing a single
check.

Because the sequence is check-then-act, the burn has to be both **last** and
**atomic**. A caller that loses the race is told it did not win and must deny.
That is [its own guide](/docs/guides/indivisible/).

## 4. Sign the request over what matters

The agent signs over method, authority, path and the authorization header.

Notice what that list does **not** include: the body. Those four say who is
asking and what they are asking of; they say nothing about the bytes. For a
single-use grant the body is pinned anyway — `operation.params_s256` is a hash
of the exact approved parameters, and step 4 refuses anything else. For a
grant that is not single-use, it is not pinned by the signature at all.

So decide deliberately whether your bodies carry meaning that has to be
integrity-protected, and cover an [RFC 9530](https://www.rfc-editor.org/rfc/rfc9530.html)
`Content-Digest` where they do. The owner's decision endpoint is the clearest
case: its entire meaning is one word in its body, and a signature that stops at
the URL lets an intermediary invert the answer without breaking anything.

Two more rules from experience:

- Take the authority from **configuration**, not from the `Host` header. A
  caller-controlled authority is not an authority, and behind a proxy `Host` is
  frequently something else entirely.
- Verify any digest against the body the enforcement point actually read. If the
  gateway truncated the body, the digest fails — which is correct, but you want
  the log line to say "truncated body" rather than "signature invalid".

## 5. Distinguish revoked from expired

Introspection that says inactive should say why.

A revoked connection is **terminal**: answer with an access-revoked error rather
than a fresh challenge. Re-negotiating cannot change an outcome the owner has
already settled, and challenging invites a well-behaved agent into a loop it
cannot exit.

Everything else — expiry, a spent single-use grant, an unknown token — should
re-challenge. The agent negotiates again, and if the owner's policy still allows
it, gets a new grant.

## Verify it

Four checks worth having in CI:

```
a valid grant replayed a second time            → refused, spent
a grant for tool A presented against tool B     → refused, scope
a valid signature over a modified body          → refused, digest
an approved order with one parameter changed    → refused, operation
```

That last one is the one to demonstrate to a sceptic. In the lab it is the
epilogue of the ask-me run: the same token, replayed, refused.

## Troubleshooting

**Legitimate calls refused on the operation check.** Canonicalization differs
between the side that hashed at approval time and the side that hashes at
enforcement time. Compare the exact byte strings being hashed, not the objects.

**Signatures fail after a deployment change.** Something in the signature base
came from the transport. Authority is the usual culprit; path is the next, if a
proxy rewrites it.

**Tokens work after the owner revoked the connection.** Revocation is setting a
flag that introspection does not read, or the enforcement point is trusting the
`permissions` claim without introspecting. The claim tells you scope; only
introspection tells you whether the grant is still alive.

**A replayed token succeeds under load.** The consume step is a read followed by
a write. See [Make single-use indivisible](/docs/guides/indivisible/).
