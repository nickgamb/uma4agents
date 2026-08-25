# Shared ownership: when the stuff is not hers

U4A's question is *can your agent access my stuff*. This is what happens when
some of that stuff is not mine.

A firm owns a book. It shares it with the people who work on it. It has
obligations about it that none of them can waive. And the person who decides
whether an agent may touch it is not the firm and not the agent's operator —
it is whichever member of staff that part of the book was shared with.

UMA has had a name for her role since 2015: **resource rights administrator**,
the party who administers access to resources she does not necessarily own.
The [PP2PI healthcare analysis](https://kantarainitiative.org/) calls the
general shape *co-administration* and lays out the four states it can be in.
What neither has had is a mechanism. This is the mechanism.

Run it:

```bash
make org-check        # 63 assertions across six processes
make org-test         # the ceiling algebra and the charter validator, no stack
```

In the cluster, where the three parties are three namespaces with no path
between them: `make k8s-org-check`.

![Shared ownership in seven beats. One resource server holds three owners of record: Alice's account, Carol's account, and Northwind Capital's book. The firm shares its book with Alice under a role that grants two resources and sets delegation to first-party-only, so the book appears in her authorization server as something she administers rather than owns. She writes the terms an agent must accept and the charter's ceiling is clamped into that same document. Bob's agent asks for the book and is refused — not by her terms but by the organization's engine, because somebody else operates it. An agent she operates herself makes the identical request and is granted. Two columns then list what the organization can do — see and shut out the agents that touch its book, answer requests about its own resources, break the glass under a clause she was shown — against what it cannot: see the agents that touch her own accounts, read her policy, widen anything, or act as her. Leaving takes back the access and leaves every narrowing in place.](shared-ownership.gif)

## The three kinds of owner

Meridian Wealth runs one resource server. Behind it are three owners of
record and they are not variations on one thing:

| | |
|---|---|
| **Alice** | A customer. Her brokerage account is hers. Nobody else has any say over it, and nothing below changes that. |
| **Carol** | The same, separately. See [MULTI-OWNER.md](MULTI-OWNER.md). |
| **Northwind Capital** | A company. It owns a book, shares parts of it with Alice and Carol under a role, and sets policy over it that neither of them can waive. |

The third is the new one. It is an owner in exactly the protocol sense — it
holds resources and decides about them — and it differs in two ways that
matter: the deciding is done by an administrator on its behalf, and what it
owns is *administered by other people*, each under her own authorization
server.

## What is shared, and how it is reached

The firm's book is one process. It is reached at a path per member:

```
/mcp                      Alice's own account   -> alice's authority
/mcp/carol                Carol's own account   -> carol's authority
/mcp/shared/alice         the firm's book       -> alice's authority
/mcp/shared/carol         the firm's book       -> carol's authority
```

The last two are the same resource. The member segment does not select *which
resource*; it selects **whose authorization server the enforcement point will
ask**, and therefore whose terms an agent has to accept. That is shared
ownership in one line of routing, and it is why the challenge for
`/mcp/shared/alice` names `alice-as.uma.lab` even though the book is
Northwind's.

The resource ids do not vary by member. `northwind-vault/get_positions` is one
resource; two people administer access to it; Northwind's charter governs it
whichever of them is asked.

## Joining is an exchange

A governance layer that only narrowed would be a strange thing to volunteer
for, and every version of this that begins with the obligations gets the
direction of the relationship wrong. Membership is a trade:

- the organization gets policy over its own resources, and a say about the
  agents that touch them;
- the member gets **access to those resources**, under a role, expressed as
  resources her own authority protects and her own terms govern.

The role is the ordinary thing an organization already has, and one field of
it is the thing nobody else has anywhere to put:

```json
"roles": {
  "analyst": {
    "grants": ["northwind-vault/get_positions",
               "northwind-vault/get_transactions"],
    "delegation": "first-party-only"
  },
  "trader": {
    "grants": ["northwind-vault/*"],
    "delegation": "any-agent"
  }
}
```

`delegation` is `none`, `first-party-only`, or `any-agent`. It does not say
what may be accessed. It says **whose agent** may do the accessing on behalf
of which person:

| | |
|---|---|
| `none` | She may reach the firm's book herself. Nothing she delegates to an agent reaches it. |
| `first-party-only` | An agent she operates may be granted access under her terms. Somebody else's may not — however much she trusts it, and whatever her own terms say. |
| `any-agent` | Any agent, subject to her terms and the charter. |

That sentence is not expressible in an authorization system built around one
party, because it is not about permissions. It is about parties: it rests on
her authority already knowing the difference between an agent she activated
and an agent somebody else runs — see [`first_party_fact`](../services/uma-as/app.py)
and `make first-party-check`. The requesting side cannot assert it. Only she
can claim an operator, and only that operator can publish an agent's key in
its own directory.

## The charter

The organization's policy document. Four parts, and they are not the same
kind of thing:

```
claims        which resources are the organization's at all
roles         what a member may reach, and what she may delegate
envelope      a ceiling on the terms she writes over them   -> clamped
conditions    what a request must look like                 -> decided
break_glass   when the organization may reach past her
rego          the administrator's own rules, which may only tighten
```

**The envelope is clamped.** A ceiling on what her terms may say is an algebra
over two documents, so it is computed in Python — `services/uma-as/org.py`,
`make org-test` — at the moment she edits, and the result is *written into her
tiers*. The obvious alternative is to leave her tiers alone and apply the
ceiling at grant time. It is less code and it is wrong: the terms document is
what an agent dereferences, reads and signs, and a document that says 24 hours
while the grant lasts one is a document that lies to both of them. Clamping on
write means what the organization requires is *in* what the agent agreed to.

Every envelope field moves in one direction. There is no field that can
lengthen an expiry, add a scope, remove a prohibition or turn off an ask —
which is what makes it safe to run on every write without checking first
whether it would help or hurt. `lib/test_org.py` enumerates the combinations
and asserts it.

**The decision is asked for.** Whether one particular request is acceptable is
a judgement about that request, and it is made at the organization's own
decision point against policy the member's authority never sees. That decision
point is [OPA](https://www.openpolicyagent.org), evaluating `org.rego`.

## Why an engine here and not there

The [comparison page](https://u4a.ai/docs/overview/compare-policy-engines/)
says an engine slots in as the evaluation core of an authorization server and
that the two compose. This is that claim standing up, and *which* layer gets
the engine is the interesting part.

An organization is the case a policy engine was built for: the operator **is**
the deciding party, there is a compliance function, and the policy outlives
whoever wrote it. A person editing her own sharing rules is the opposite case
— she should never need a debugger to understand what she permitted. So the
member's layer stays a small legible document and the organization's layer
gets Rego, and each party has the tool that fits whose policy it is.

The declarative `conditions` are a front end onto the shipped module, so an
administrator who never opens the code editor still gets an engine-evaluated
policy. One who does gets a `u4a.custom` package that can contribute exactly
two things — `deny` and `ask` — and there is no third. That is a property of
the shape rather than a convention: no charter and no administrator's Rego can
make a request easier than the member's own policy already makes it.

## The composition rule

One sentence:

> **Both layers must allow, and either may refuse.**

Her policy is what permits. The organization's `allow` means it has no
objection, never "grant this". Concretely, in `/token`:

```
tier_for_resource        her terms over this resource
policy.evaluate          her rules                        -> auto | ask | refuse
organization_verdict     the charter, at its own PDP      -> allow | ask | refuse
                                                             (never widens)
```

An organization's `ask` raises `auto` to `ask` and is shown to her in the
organization's own words, separately from her own rules — she should be able
to tell which of the two layers is the reason she is being interrupted.

## What the organization can see

This is the boundary, and it is the half most likely to be got wrong.

An administrator can see, and act on, **what touches the organization's
resources**. Not her queue, not her agents, not her record. Her authority
filters by what the charter claims before it answers anything:

| | |
|---|---|
| `GET /org/admin/{owner}/pending` | requests over org-claimed resources only |
| `GET /org/admin/{owner}/connections` | agents granted or approved at a tier that governs one |
| `GET /org/admin/{owner}/operators` | the operators behind *those* agents |
| `GET /org/admin/{owner}/ledger` | entries about org resources, plus the membership's own history |

An agent that reads only her brokerage account does not appear on any of them.
It cannot be denied from there, cannot be revoked from there, and there is no
view of it to open.

What the organization is told about her *policy* is a count and the names of
its own fields that bit — `{"tiers_governed": 1, "clamped_fields":
["max_expires_in"], "within": true}`. Never a value out of her terms. It is
entitled to know its ceiling is being applied; it is not entitled to read the
arrangements she made underneath it.

**Revocation is scoped the same way.** An administrator shutting an agent out
does not end her relationship with it — that agent may be reading her own
portfolio for her every morning. What it does is narrower and exact: the agent
stops reaching anything the charter claims, at once, and everything else about
its standing with her is untouched. Held in the membership record, so it
vanishes when the membership does.

**Everything an administrator does is attributed.** Her ledger records who
did it and her portal says so on the screen, live. A record in which one
party's decision appeared as another's would be worse than no record: it is a
record that would be believed.

## Consent

Joining hands another party standing authority over her agents. So:

1. she enters a code, or accepts an invitation addressed to her;
2. she is shown the whole charter in sentences, what it would share with her,
   what it would let the organization do, what it could never touch, and
   **exactly what it would change about terms she has already written**;
3. she agrees to that, explicitly;
4. only then does anything happen.

Her authorization server refuses a join that does not carry the agreement, so
a surface that forgot to ask fails rather than enrolling her quietly. The
record keeps *what she agreed to* against the charter version, so "what was I
told this would let them do" stays answerable after the organization has
edited its charter a dozen times.

An invitation creates a question and nothing else. Until she accepts, the
organization does not know where her authorization server is and has no way to
touch anything of hers.

## Break-glass

The one direction that is a genuine override, and a separate code path because
it does not go through her authority at all. The organization signs those
grants with its own key; the enforcement point verifies them against the JWKS
the organization publishes. That is the only shape in which "the organization
owns this data" is a technical fact rather than a request — it works whether or
not a member's authorization server chose to cooperate.

Three things bound it, all of them in the charter she read before she joined:

- it reaches only resources the charter both **claims** and **names for
  break-glass**. An override outside what was disclosed is not an override, it
  is a second front door;
- it is short, single-use and bound to the key that asked for it;
- it is **loud**. An administrator opens a window and she is told at that
  moment — before an agent has redeemed anything and before any data has
  moved — and every use lands in her own record.

Two steps rather than one, because the split is what puts the notification at
the moment a human decided rather than at the moment something took.

## Leaving

Membership is what granted the access, so leaving takes it back: the firm's
book stops being hers to administer and disappears from her authority.

Her **terms keep every narrowing the charter required**. Leaving withdraws a
ceiling; it does not raise what is underneath one. An unenrolment that
silently widened every grant she had made would be the most dangerous button
in this system. Anything she wants back she widens herself, deliberately, one
tier at a time.

## Limits

- **Leaving is self-serve here.** In a real deployment membership would be
  bound to the organization's identity provider and leaving would be an act of
  the organization. The lab does it the other way round because the
  interesting property survives either: leaving cannot widen anything.
- **One organization per owner.** Two ceilings over one terms document would
  have to be intersected, and an intersection nobody wrote is a policy nobody
  agreed to. The honest version of that feature is per-resource enrolment, and
  it is not here.
- **The invitation endpoint is unauthenticated.** Before she accepts there is
  no relationship to authenticate — her authority has never spoken to this
  service and this service has never heard of her. Anyone who can reach it can
  learn whether a *name* has been invited. A deployment where that matters
  federates the identity provider and issues invitations against it.
- **The enforcement point caches membership.** `UMA_PEP_MEMBERSHIP_TTL_S`,
  ten seconds by default. The window is somebody's access to the firm's book
  after the firm withdrew it, which is why it is short and why it is
  configuration. Listings are always read fresh.
- **The organization's authority is one process holding its own state.**
  Restarting it loses membership, exactly as restarting Carol's authority
  loses her record. The honest cost of the small shape.
- **The enforcement point can only check half the ceiling from a token.**
  Expiry and scope are in the grant; the prohibitions a charter requires and
  the approvals it insists on are in the *terms*, and a token carries only a
  hash of those. So an enforcement point can prove the ceiling held on the
  first two and cannot prove it held on the rest. The member's authority
  writes the whole ceiling into the terms document, where the agent reads and
  signs it; this catches the part that would still be visible if that
  authority had never applied it at all.

## See also

- [MULTI-OWNER.md](MULTI-OWNER.md) — many owners of one resource server, which this builds on
- [PROTOCOL.md](PROTOCOL.md) — the four beats the shared surface runs unchanged
- [ASSURANCE.md](ASSURANCE.md) — where `first_party` comes from, and why it may relax
- `services/org-authority/charter.py` — the charter, and what may be said in it
- `services/org-authority/org.rego` — the shipped module, and the delegation rule
- `services/uma-as/org.py` — the clamp, and the party boundary from the member's side
- `clients/demo-driver/org_check.py` — the 63 assertions
