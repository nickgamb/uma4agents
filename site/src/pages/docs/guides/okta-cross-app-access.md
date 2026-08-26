---
templateKey: doc
title: Try it with Okta
seoTitle: "Connect a real Okta tenant to a UMA authorization server with Cross App Access"
description: Register an AI agent, point it at an authorization server that is not Okta's, and watch an enterprise assertion and an owner's terms settle two halves of one request.
next:
  - title: Cross App Access
    to: /docs/overview/cross-app-access/
    blurb: What the two halves are, and why the assertion is a claim rather than a grant.
  - title: Run the lab
    to: /docs/guides/run-the-lab/
    blurb: The rest of the lab this plugs into.
---

Everything in [Cross App Access](/docs/overview/cross-app-access/) runs against
the provider shipped beside the lab. This is the same thing against a real
Okta tenant, which takes about twenty minutes and a free trial.

Worth knowing before you start: **agent-to-app Cross App Access needs only SSO
and a super admin.** It is not gated behind Okta for AI Agents — that
subscription raises the ID-JAG ceiling above the SSO allowance rather than
unlocking the flow. A trial org can do all of this.

## What you are building

Okta plays Northwind's identity provider — a customer enterprise whose
employees the brokerage does not manage. Two objects go in your tenant:

| Okta object | what it is here |
|---|---|
| **AI agent** (requesting app) | the agent asking for the firm's book |
| **resource app** | the member's authorization server |
| **resource connection** | the edge an administrator approved, and the scopes on it |

Nothing needs to reach *into* your lab. Every leg is outbound — the agent
calls Okta, and your authorization server fetches Okta's keys — so a laptop
works and no tunnel is required.

## 1. Register the AI agent

**Directory → AI agents → Register AI agent → Register manually.**

1. Under **Profile**, name it (`Northwind Research Agent`) and continue.
2. Under **User access**, choose **Create a new OIDC app linked to this AI
   agent**. That linked app is the requesting app: it is what an employee
   signs into, and it is where the agent's OAuth identity lives.
3. On the **Client registration** tab, choose **Client secret** and
   **Generate secret**. Keep the **Client ID** and the secret.
4. **Activate**, then assign yourself: **User access → Application →
   Assignments**.

Then one thing the console does not do for you. Open the linked app under
**Applications** and make sure its **grant types** include **Refresh Token**
alongside Authorization Code. Okta's exchange takes a *refresh token* as the
subject token, so without it the agent can never obtain one and the exchange
fails with nothing useful in the error.

See Okta's [Configure AI agent-to-app with XAA](https://developer.okta.com/docs/guides/xaa-agent-to-app/main/).

## 2. Create the resource app

This object stands for **the member's authorization server**, which is not
Okta's and which Okta never calls.

1. **Applications → Create App Integration → OIDC**. Name it for the resource
   (`Meridian Wealth`).
2. Open it, go to the **Resource Server** tab, and next to **Cross App Access
   (XAA)** click **Edit → Enable**.
3. Set the two fields, and get them the right way round:

   | field | value | lands in the ID-JAG as |
   |---|---|---|
   | **Issuer URL** | the authorization server's issuer, e.g. `https://alice-as.uma.lab` | `aud` |
   | **Audience/tenant ID** | which tenant at that resource, e.g. `northwind` | `aud_tenant` |

**Issuer URL is the one that matters, and it cannot be changed afterwards.**
Okta greys the field out once the app exists. It becomes the assertion's
`aud`, and the member's authority refuses anything not audienced at itself —
which is what stops an assertion minted for one member being spent at
another's. Get it right at creation, or delete the app and make it again;
there is no third option, and a placeholder here produces a token that
verifies perfectly and is then refused.

Recreating the resource app also destroys any resource connection pointing at
it, so step 3 has to be done again afterwards.

Audience/tenant ID is editable, and is a *tenant* rather than a person —
`northwind`, not the name of the administrator configuring it.

## 3. Connect them

**Directory → AI Agents →** your agent **→ Resource connections → Add resource
connection.**

- **Application instance** — the resource app from step 2.
- **Resource indicator** — the resource server's URI, e.g.
  `https://gateway.uma.lab/mcp`. This is the API being reached, not the
  authorization server.
- **AI agent's client ID registered in this app** — the agent's client ID.
- **Scopes** — the operations an administrator is willing to assert for, e.g.
  `get_positions`, `get_balance`.

Those scopes are the **first of three ceilings**. Okta will not assert
anything outside them, whatever an agent asks for.

## 4. Dana's side, in the organization console

The Okta half says who Northwind's people are. It says nothing about what may
be done to a resource, and the organization still has to publish that
separately — in Meridian's console, which Dana signs into with Meridian's own
identity provider rather than with Okta.

**Charter → Settings → Federated identity (Cross App Access):**

- **Federate identity to an external provider** — on.
- **Provider issuer** — your Okta org, `https://trial-NNNNNNN.okta.com`.
- **Directory issuer** — leave blank. It is discovered from the provider's own
  metadata, and a charter carrying two endpoints that disagree is a charter
  that trusts the wrong one.
- **Let your people enrol without a code** — on, if you want employees to join
  on the strength of the directory rather than a shared code.

Saving publishes a new charter version. Every member's authority re-clamps to
it, and each of them can read which provider her authority now takes assertions
from — an organization cannot start accepting somebody else's word about who
its people are without republishing the bargain.

## 5. Point the lab at it

One field in the charter is the whole integration:

```json
"identity_provider": {
  "enabled": true,
  "issuer":  "https://trial-NNNNNNN.okta.com",
  "directory": ""
}
```

Then the part everybody hits. **Okta's `sub` is an identifier local to your
tenant, and its `email` is an email — neither is the name a member's authority
knows her by.** Two separate questions follow, and running them together is
why an integration can look finished and still refuse every request:

- *which claim carries the name* — `preferred_username`, `email`, the email's
  local part and `sub` are all compared; `identity_provider.subject_claim`
  names one explicitly where a tenant's claim set makes it ambiguous;
- *who that name is here* — `identity_provider.subject_map`.

```json
"identity_provider": {
  "enabled": true,
  "issuer":  "https://trial-NNNNNNN.okta.com",
  "subject_map": { "alice@northwind.example": "alice" }
}
```

The map lives in the charter because the organization is the party that knows.
These are its people; it enrolled them, and it is the only party that can say
its provider's `00u1…` is the member an authority calls `alice`. Neither Okta
nor the member's authority can answer that alone.

## What you should see

The agent calls the tool, is refused, and is told which provider to visit.
It exchanges at Okta and comes back with something like:

```json
{ "typ": "oauth-id-jag+jwt", "alg": "RS256" }
{
  "iss": "https://trial-NNNNNNN.okta.com",
  "aud": "https://alice-as.uma.lab",
  "sub": "00u16v9nrbu…",
  "email": "alice@northwind.example",
  "client_id": "wlp16vatepit…",
  "scope": "get_positions",
  "act": { "sub": "wlp16vatepit…", "sub_profile": "ai_agent" },
  "aud_tenant": "northwind",
  "exp": "+300s"
}
```

Note `act`: the agent named separately from the employee it acts for. And note
what is absent — nothing in it says what may be done to the book. That is the
next beat, and it belongs to the member.

## When it does not work

- **`invalid_target: Token Exchange requests must include a valid audience`** —
  the `audience` does not match the resource app's **Issuer URL**. A 403 rather
  than a 400 means the audience *is* recognised and something else was refused,
  which is a useful distinction when guessing what a field was set to.
- **`access_denied` with everything apparently configured** — check the
  resource connection still has its **Scopes**. A connection with no scopes
  authorises nothing.
- **The agent cannot obtain a subject token** — the linked app is missing the
  **Refresh Token** grant.
- **`the assertion names ['00u1…'] — which this organization does not map to
  'alice'`** — the assertion is good and nobody has said who that identifier
  belongs to. Add the pair to `subject_map`.
- **`CERTIFICATE_VERIFY_FAILED` the moment the agent leaves the deployment** —
  a trust store holding a private CA *instead of* the public roots rather than
  as well as them. Both an authorization server and an agent need both.
- **"could not be reached to check the assertion"** — the authorization server
  cannot fetch the tenant's keys. Where a deployment trusts a private CA, that
  CA has to be *added to* the public roots rather than replacing them, or every
  public issuer fails and reads as the provider being down.
