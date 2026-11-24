# Earned autonomy

[Assurance](ASSURANCE.md) answers what Alice's authority can establish about an
agent it has never met. This page answers the next question: **once she has
met it, how much may it do without asking her?**

The vocabulary is the Cloud Security Alliance's
[Agentic Trust Framework](https://github.com/massivescale-ai/agentic-trust-framework)
(ATF), used as written. It has four maturity levels, and an
agent earns its way up them:

| ATF level | Autonomy | Human involvement |
|---|---|---|
| intern | observe and report | continuous oversight |
| junior | recommend, then act once approved | a human approves every action |
| senior | act and notify | a human is told afterwards |
| principal | autonomous within a domain | strategic oversight only |

Run it: `make autonomy-check` against the compose stack, `make fixture-autonomy`
with no identity provider and no gateway, or `make k8s-autonomy-check` in the
cluster. Unit tests, needing nothing running: `make rules-test`, `make as-test`
and `make store-test`.

## Two ladders, not one

ATF describes one ladder, held by the organization that deploys the agent.
Inside one enterprise that is the whole picture. The party governing the agent
and the party whose systems it reaches are the same party.

UMA's contribution is that they are not the same party. It has a *requesting
party* as well as a resource owner. Bob's firm runs the agent, and Alice holds
what it asks for. So under U4A **every agent stands on two ladders at once**:

| | The operator's ladder | The owner's ladder |
|---|---|---|
| Who keeps it | the firm running the agent | Alice's authorization server |
| Where it lives | the operator's [client metadata document](https://datatracker.ietf.org/doc/draft-ietf-oauth-client-id-metadata-document/), as an `atf` member | the connection record, per agent |
| Who moves it | the operator, by its own ATF governance | **Alice alone** raises it, one rung at a time. She may lower it any distance, and revoking the agent resets it |
| What it can do to her rules | **tighten only** | relax (`standing.autonomy_at_least`) or tighten (`standing.autonomy_below`) |
| A stranger starts at | wherever its operator says | intern, always |

Neither ladder is read through the other, and nothing combines them into one
level. The reason is the one [assurance](ASSURANCE.md) gives for refusing a
composite score. A combined level is how an operator's confidence in its own
agent would come to stand in for Alice's, and nobody would make that trade if
asked directly.

> **Whichever ladder stands lower governs. Nobody's promotion reaches anybody
> else. An operator's demotion reaches every owner on the agent's next request.**

## The operator's ladder

An operator publishes where it has put each class of agent on its own ladder,
in the metadata document its agents already name:

```json
{
  "client_id": "https://agent.uma.lab/agent.json",
  "client_name": "Sterling & Vance — Advisory Agent",
  "atf": {
    "version": "0.9.0",
    "maturity_level": "principal",
    "conformance": "compatible",
    "statement_uri": "https://agent.uma.lab/atf"
  }
}
```

The shape follows ATF's own conformance statement. `statement_uri` points at the
operator's statement, which the lab operator serves at `/atf`. A level is per
client, so a firm with agents at different levels publishes one document per
class of agent. The lab firm runs `/agent.json` at `principal` and
`/agents/research.json` at `intern`.

Her authority reads it only from a document that resolved and claims its own
URL. It never reads it from anything the agent sent. It reads the level as a
condition that **may only tighten**:

- `operator.autonomy_below:<level>`: the operator declares a level below this
- `operator.autonomy_undeclared`: the operator declares none

An operator that declares nothing is *not* thereby an intern. An operator that
has never heard of ATF is not saying anything about its agent. So `_below` is
false for it, and an owner who wants declarations can require one with
`_undeclared`. This mirrors how an undeclared
[consequence](CONSEQUENCE.md) is treated.

Because it can only tighten, the declaration needs no verification to be safe.
An operator that overstates its agent gains nothing, and one that understates it
costs only itself. **A lie can only cost the liar friction**, as with assurance.
Her dialog still says who made the declaration: an operator that also published
this agent's key (accountability 2), or a document any agent could have named.

A metadata document used to be cached until it fell out of memory. It now
expires (`UMA_AS_CIMD_TTL`, 300s by default, the same bound as the key
directory). The reason is that a stale copy would go on reading an operator's
level from *before* it demoted its agent, which is the direction that widens.

### Third-party attestation: deliberately not credited

ATF has two conformance tiers. *Compatible* is self-assessed. *Certified* is an
independent audit. An operator's document can say `"conformance": "certified"`,
and her authority shows that as a claim, *"it claims ATF Certified; nobody this
authority can ask has confirmed that"*. It credits nothing for it: no assurance
axis moves and no rule reads it.

This is the place ATF could fill the gap [assurance](ASSURANCE.md) leaves open.
Accountability level 2 is the operator vouching for its own agent. What is
missing is anyone *outside* the operator, and a certification body is exactly
that. It would take a party a relying authorization server can ask, such as a
registry that answers "is this origin's programme certified, at what level,
until when" with something signed. ATF's conformance document says the list of
approved auditors "will be published as this specification matures". Until it
exists, crediting the claim would mean trusting the requesting side's word for
what a third party said. See the open questions below.

## The owner's ladder

Every agent starts as an **intern with her**: a stranger, a newly admitted
connection, and an agent she revoked and later readmitted. ATF says the same
("Initial maturity level set (always Intern)"). U4A arrives there independently,
because standing starts at zero, and a level another party granted is not
standing with her.

Only she raises it, one rung at a time:

```
POST /owner/connections/autonomy
{"handle": "jkt:…", "level": "junior", "expect": "intern"}
```

- **Only the owner may promote.** `autonomy.change` refuses a promotion from
  anyone else, and the record writes who decided. No party acting for her has
  an endpoint for it. An organization's administrator already has a narrower
  tool for an agent he distrusts: shutting it out of the organization's
  resources. Her ladder covers her own accounts too, which are not his to reach
  ([ORG.md](ORG.md)).
- **One rung at a time.** ATF's promotion gates are per rung, and time at a rung
  is the only evidence she will ever have of how the agent behaves there.
- **She may demote any distance, in one step.** A restriction never needs an
  argument.
- **A stale view cannot overwrite a newer change.** `expect` is the level her
  portal showed her, and the write is a compare-and-set in both stores (a single
  `UPDATE … WHERE level = $expect` in Postgres). `make store-test` races 32
  writers at one level and asserts one lands.
- **Every move is in her record**, as `autonomy_promoted` or `autonomy_demoted`,
  with the levels before and after.

That gives the invariant that lets her level *relax* a rule, which is otherwise
something only her own decisions may do:

> **The level rises only by her hand, so whatever it reads now is at or below a
> level she personally granted.**

The conditions are `standing.autonomy_at_least:<level>` (relaxing) and
`standing.autonomy_below:<level>` (observed). Two degenerate ones are refused
where policy is stored. `at_least:intern` holds for every agent, including a
stranger, so it would relax for strangers. `below:intern` can never fire, so it
would read as a restriction that does nothing.

### What she sees before she promotes

ATF's five promotion gates are performance, security validation, business
value, incident record, and governance sign-off. Two of them are visible from her
side, and her portal shows them beside the button, read from the ledger her
decisions already wrote:

| Gate | What her record says |
|---|---|
| performance: time at level | days since it reached this rung, against ATF's illustrative 2 / 4 / 8 weeks |
| performance: acceptance | how many of the requests it put to her at this rung she approved herself (decisions taken for her do not count). ATF suggests above 95% before leaving junior |
| incident record | requests her policy refused on their own merits since it reached this rung. A refusal because of its level is the ladder working, and one because her queue was full is about her; neither counts |
| security validation, business value | the operator's programme, not this agent with her: shown as the operator's, or an evaluator's, to evidence |
| governance sign-off | hers: promoting it *is* the sign-off |

None of it promotes anything. It is advisory, and the decision is hers.

## The profile: ATF as her rules

There is no new machinery in how the levels act. The profile is eight ordinary
rules over conditions her vocabulary already had, plus the consequence the
resource declares for each operation. It is published as a preset
(`GET /owner/policy-presets`) and added to a tier like anything she types:

```json
[
  {"when": ["standing.autonomy_at_least:senior"], "then": "auto"},
  {"when": ["standing.autonomy_below:principal",
            "request.consequence_at_or_above:irreversible"], "then": "ask"},
  {"when": ["standing.autonomy_below:senior",
            "request.consequence_at_or_above:compensatable"], "then": "ask"},
  {"when": ["standing.autonomy_below:junior",
            "request.consequence_at_or_above:compensatable"], "then": "refuse"},
  {"when": ["standing.autonomy_below:junior",
            "request.consequence_unknown"], "then": "ask"},
  {"when": ["operator.autonomy_below:junior",
            "request.consequence_at_or_above:compensatable"], "then": "refuse"},
  {"when": ["operator.autonomy_below:senior",
            "request.consequence_at_or_above:compensatable"], "then": "ask"},
  {"when": ["operator.autonomy_below:principal",
            "request.consequence_at_or_above:irreversible"], "then": "ask"}
]
```

| With her | A read | An act that can be compensated | An act that cannot be undone |
|---|---|---|---|
| intern | as the tier says | **refused** | **refused** |
| junior | as the tier says | asked | asked |
| senior | granted | granted, and she is told | asked |
| principal | granted | granted, and she is told | granted, and she is told |

Then the operator's ladder, read the same way, can only make a cell stricter.
Only the first rule relaxes anything, and it reads her own decision. Restrictions
win over relaxations whatever order they are written in, as they already did.

ATF's senior rung is *act and notify*. Whenever an agent is let change something
without her being asked, her authority pushes an `acted` event on the same stream
her pending requests use, and the portal shows it as it happens.

## What `make autonomy-check` shows

Two agents from one firm. The firm has put its advisory agent at **principal**
and its research assistant at **intern** on its own ladder. Alice adds the
preset to her trade tier.

1. **A principal at its firm is an intern with her.** The advisor reads her
   holdings and is admitted, and its first trade is refused without reaching
   her. The refusal names her ladder (`standing.autonomy_below:junior`), not the
   firm's.
2. **Only she raises it, one rung at a time.** Skipping a rung is refused. As a
   junior, its trade is put to her. A promotion from a stale view is refused
   (409). As a senior, the irreversible trade still asks. As a principal, with
   its firm agreeing, it trades without asking, and her record names the
   decision of hers that allowed it.
3. **The operator's ladder can only tighten.** She promotes the research
   assistant all the way to principal. Its trade is still refused, and the
   refusal names `operator.autonomy_below:junior`.
4. **Lowering either lands at once.** She demotes the advisor two rungs in one
   step, and its next trade asks. She revokes it and it reconnects as an intern,
   whose trade is refused as on the first day.

Her trade tier is put back as she wrote it.

## Where ATF's requirements land

ATF sets 25 requirements for an organization deploying agents. Under U4A some
fall to the operator, as ATF assumes. Some are met by the resource owner's
authority on her side of the exchange, which ATF does not describe. The full
crosswalk is the appendix *Mapping to the Agentic Trust Framework* in
[the policy draft](https://u4a.ai/spec/draft-gamb-uma4agents-policy-00.html),
one row per requirement. Each is judged only for requests that reach her
resources, and given one of four statuses:

| Status | Meaning | Requirements |
|---|---|---|
| met | U4A meets it on her side | I-1, I-2, B-1, B-2, S-1, S-2, S-3, S-4, R-1, R-3, R-5 |
| partly | part of it is met on her side; the appendix says which part | I-3, I-4, B-4, B-5, D-3, D-5, S-5, R-2 |
| operator | it concerns the agent's own runtime, which she cannot see | I-5, B-3, D-1, D-2, D-4 |
| resource | undoing an act is the resource server's; U4A carries what it declares | R-4 |

Two of these are met by containment on her side:

- **S-3, rate limiting.** A tier's terms may carry `rate_limit`, such as
  `{"calls": 60, "per": "1h"}`. The agent agrees to it with the terms. Her
  authority refuses introspection with `rate_limited` once the agent has made
  that many allowed calls at the tier in the period.
- **R-1, circuit breaker.** Her enforcement point reports calls it refused after
  the agent's signature verified (`POST /audit/refused`). Three in ten minutes
  (`UMA_AS_BREAKER_REFUSALS`, `UMA_AS_BREAKER_WINDOW`) suspend the agent: its
  grants answer `suspended`, it gets no new ones, and it drops to intern. Only
  she lifts it (`POST /owner/connections/resume`).

ATF's automatic demotion triggers are a critical incident, a discovered
vulnerability, and repeated minor incidents. The operator observes all of them,
which is where ATF puts them, and they reach every owner through the operator's
ladder on the agent's next request without any owner doing anything.

## Open questions for review

These are the places the profile stops short on purpose, and where a
conversation with the ATF authors would move it:

1. **A registry for ATF Certified.** What would a relying party fetch, from
   whom, keyed on what (operator origin? `statement_uri`?), signed with which
   keys, and how would it lapse? With an answer, a certified programme becomes
   accountability level 3, still tighten-only.
2. **Per-agent rather than per-client levels.** ATF levels are per agent
   instance. A metadata document is per client. A per-key level in the
   operator's Web Bot Auth key directory would be finer, and would be attested
   by the same same-origin check that gives accountability 2. Is that worth a
   field?
3. **Does ATF want the second ladder named?** The owner-side ladder is ATF's
   model applied by a party ATF does not have. If ATF said so, for example "a
   relying party MAY keep its own maturity level for an agent and MUST NOT take
   it from the operator's", then owners' authorities would have something to
   conform to.
4. **Incidents the owner sees.** Her enforcement point refuses calls that exceed
   a grant. Those are observable incidents on her side. Should they feed her own
   automatic demotion, or only her promotion eligibility? This lab does neither
   yet.
5. **An evaluator's appraisal as promotion evidence.** ATF has an agent earn
   its level from signed records of what it did, appraised and signed by an
   evaluator. The natural place for that on her side is beside the eligibility
   gates. It would travel as a [clearance](CLEARANCE.md) does: fetched by her
   authority from the evaluator, verified against the evaluator's published
   keys, bound to this agent, and never carried by the agent itself. It would
   inform her decision and could not make it. What is open is the record and
   appraisal format, who publishes the evaluator's keys, and how an appraisal
   lapses. Clearance today attests facts about the owner. An appraisal is about
   the agent, so it needs a new subject, not a new transport.

## See also

- [ASSURANCE.md](ASSURANCE.md): what her authority can verify before she has met
  an agent, and why it is three axes and not one number
- [CONSEQUENCE.md](CONSEQUENCE.md): the declared classes the profile reads
- [FINDINGS.md](../FINDINGS.md): recommendation 29
- `services/uma-as/autonomy.py`, `services/uma-as/policy.py`,
  `clients/demo-driver/autonomy_check.py`
