---
templateKey: changelog
title: Changelog
seoTitle: "Changelog — UMA for Agents"
description: Release notes for the UMA for Agents reference architecture, newest first.
---

<!-- Each merged pull request adds a release at the top.

     `## <Month D YYYY>` is the date, and every release that day is a
     `### v<YYYY.MM.N>` under it — several land on most days, and a repeated
     date heading is neither a unique anchor nor a usable contents entry.
     Under the version, `#### New`, `#### Enhancements`, `#### Bug fixes` or
     `#### Feature deprecations`.

     One line per change, prefixed with the component. State what changed;
     the reasoning belongs in the docs. The pull request template asks for
     these lines. -->

Calendar versioning in `vYYYY.MM.N` format, where `N` is the sequential
release within that month. One entry per release.

## September 23 2026

### v2026.09.14

#### New

- **Specification:** core defines refusals that are not challenges — a status and an `error` from a named set, with no challenge — and the MCP binding's `-32002` carries them.
- **Specification:** multiparty specifies the organization's metadata document at `/.well-known/u4a-organization`, the decision request and answer, the break-glass grant's claims, and the tally's `u4a_mandate_endpoint`.
- **Specification:** the requesting party token must carry `iss`, `aud`, `jti` and `exp`, and an active introspection answer must carry what enforcement reads from it.
- **Specification:** extension introspection reasons must say whether they are terminal, `organization_revoked` is, an unrecognised one is treated as terminal, and `/consume` names its `error` values.
- **Checks:** `make k8s-check-all` runs every suite the requirements register cites against the cluster, and `make rego-test` runs the charter pattern vectors through the organization's Rego.
- **Checks:** `make spec-check` requires each register row's assertions to come from the targets that row names.

#### Enhancements

- **Specification:** claim types, formats and the authorization-details type are `https://u4a.ai/spec/…#…` URIs instead of an unregistered URN namespace.
- **Specification:** a refuse rule may turn away an agent the owner has not met, and the refusal is recorded; no rule may admit one.
- **Enforcement point, embedded vault:** both build discovery documents and the owner-resources gate from `lib/uma4a_publish.py`, and the AAuth resource document follows the AAuth binding draft.
- **Enforcement point:** one function classifies why a grant is not live, for introspection and consume alike.
- **Owner API:** connection revoke, and the organization's revoke and restore, take the handle in the body.
- **Organization:** an invitation's code is shown once, to the administrator; the public read says only that she is invited.
- **Organization:** the static administrator token is refused beside an identity provider; the checks sign in as the administrator. The XAA broker's seed token is gone.
- **Organization:** a charter pattern is literal text and `*`.
- **Tally:** abandoned negotiations, tickets and unsigned terms are swept, and open negotiations per account are capped.
- **Tally, organization, XAA broker:** protocol events use the shape every other service emits.
- **n8n integration:** the lab sidecar has its own service account, key and origin, `n8n.uma.lab`, and n8n is pinned.
- **Fixture:** makes one certificate for its resource, which serves https.

#### Bug fixes

- **Authorization server:** introspect and consume disclosed another owner's grant state before the owner check.
- **Authorization server:** an agreement with no scope array, or a per-operation agreement naming no tool, was put to the owner and failed at issuance.
- **Authorization server:** the joint verdict path stored an agent's reason and mission unbounded.
- **Authorization server:** introductions without `exp` were accepted.
- **Authorization server:** a rule naming an unknown condition never fired, and a malformed stored rule raised in the grant loop.
- **Authorization server:** a holder's authority never noticed the tally publishing a different mandate; it now refuses, records it once and asks her again.
- **Authorization server:** tier creation refused a resource the serving replica had not pulled yet.
- **Enforcement point:** a consume that could not be made was reported as a lost race.
- **Enforcement point, embedded vault:** Origin was checked only on requests that reached authorization.
- **Enforcement point:** a bad signature on `/owner-resources` forced a key fetch every time; an unreachable organization or tally shortened the listing, which reads as withdrawal.
- **Enforcement point:** sidecar mode failed on any forwarded body.
- **Signatures:** a non-`ed25519` `alg` and an uncovered `Signature-Agent` were accepted.
- **Portal, console:** an unknown auth mode served without login; the session id was not rotated at login.
- **Portal:** vault errors reached the browser as bare 500s.
- **Organization:** a refused break-glass request burnt the administrator's voucher; charter notices were serial and failed on a departed member; a listed operator's new key was refused for up to five minutes.
- **XAA broker:** admin tokens were verified without key refetch and with the token's own `alg`.
- **Kwaai ability:** a refused decision was retried forever and logged as unreachable.
- **Agent shim:** a resource without discovery was reported as a version mismatch.
- **Joint vault:** transactions carried no account.
- **Kubernetes:** pAI-OS was left running after its checks and raced every later one; keygen waits were unbounded; `k8s-wait` passed without the registry pull; `chaos.sh` counted an unreadable table as a surviving request.
- **Specification build:** the render failed once the pinned draft date was more than three days old.
- **Docs:** suite counts, the MCP RFC 9728 date, the approval guide's claim checks, recommendations 27 and 28, and what guards the owner API.

## September 16 2026

### v2026.09.13

#### New

- **Kubernetes:** `make k8s-embedded-check` runs the four-beat grant against a resource carrying the enforcement obligations in-process, as a second vault at `embedded.uma.lab` standing beside the gateway one and answering to the same authority. Core §8.1 states those obligations as a conformance profile rather than a topology; running it here holds the mesh, the waypoint and the namespace boundaries in place, so the claim is no enforcement *hop* rather than no deployment.
- **Kubernetes:** `make k8s-flow-check` runs the four identity regimes in the cluster, where Bob's operator serves a key directory it was provisioned with and refuses one offered at runtime. The regime that needs the directory to hold its key signs with one that operator issued, so the check asserts what it claims to rather than falling back to a bare key.
- **Kubernetes:** `make k8s-rotation-check` rotates the authorization server's signing key under a live grant, across three replicas sharing one key from a Secret. A grant issued before the rotation still spends, one issued after carries the new kid, both kids are published, and the resource server accepts a pull signed with the new key — the failure a single process cannot exhibit. `k8s/scripts/rotate-as-key.sh` stages the second key and puts the original back.
- **Kubernetes:** `make k8s-ts-agent-check` runs the four beats from the TypeScript agent, and `make k8s-shim-test` drives the adapter under a scripted MCP client through the elicitation path, the standing-config fallback and the pend handed back as a wait. Neither needs a new image: the agent's built output is committed and imports only node builtins, and the shim is spawned by the check the way it runs beside an agent on somebody's machine.
- **Kubernetes:** `make k8s-kwaai-check` runs the personal-AI binding inside pAI-OS in her own namespace, beside the ability it imports and against the device key only she holds, so neither is a second copy.
- **Kubernetes:** an XAA broker and Northwind's own identity provider are deployed, so `make k8s-xaa-check` can run the Cross App Access arrangement where the enterprise's directory is a second provider in the enterprise's namespace rather than another realm on Meridian's.

#### Bug fixes

- **Authorization server:** the per-request call to an organization's decision endpoint had no recovery for a membership token that had been superseded, while the envelope refresh beside it has had one all along. A rejoin mints a new token; a replica that missed it was told its token was not current — true of the token and false of the membership — and refused every request over the organization's resources until its envelope happened to go stale. It now re-reads the record, evicts the cached client and asks once more with the token on record, exactly as the refresh path does. Invisible in a single-process deployment, where one cache is the only cache.
- **Authorization server:** a 403 from an organization's decision endpoint was reported as "your organization's authority could not be reached", naming the network for what is an answer. The two are now distinguished, and only a transport failure says unreachable.
- **Enforcement point:** `UMA_PEP_ORG_DISCOVERY_TTL_S` was unset in the Kubernetes deployment and defaulted to two minutes, while the compose stack sets fifteen seconds on the gateway and on the checks from one value. A check that waited seventeen seconds read a description of the organization from the charter before last. The deployment now sets it, so both processes read the same number.
- **Mesh policy:** the enforcement point reads what an organization publishes about itself over the internal name, and no rule admitted it there — the document is public at the edge, and only the mesh was in the way. So a member who had not joined was refused opaquely instead of being told which organization holds the resource and that she can enrol by signing in at her employer. The refusal decides nothing either way; what it costs is the difference between a dead end and something the person can act on. A deployment with no mesh in front of it never saw this.
- **Identity regimes check:** the Cross App Access check dereferenced a challenge it had not checked for, turning a beat that answered with a refusal into a traceback that named neither beat. It now reports what came back.
- **Resource server, embedded mode:** the in-process enforcement host was wired with a client secret by default and with no signing key at all, so a resource server holding no credential from an authority could not introduce itself — it asked for a PAT as a client that authority had never heard of, was refused, and had no way to register. `/rs/register` was never called. It now takes the same identity rule the gateway host has: with a secret it is the name it was given, and without one it is its own origin, signing with the key it publishes there. The no-secret path had never run in embedded mode in any deployment.
- **Enforcement point:** a permission ticket that an authority refused was reported as `as_unreachable`, which names the network for a credential problem and sends whoever reads it to the wrong layer. A refusal now records the authority's answer, the client id it was refused under, and the status.
- **Identity regimes check:** the Web Bot Auth regime registered its key with the operator at runtime and treated a refusal as nothing to report, so against an operator that publishes a provisioned directory it quietly became the bare-key regime and the run still passed. It now uses a provisioned identity of its own where one is mounted, and refuses to run rather than prove less than it says.

### v2026.09.12

#### New

- **Enforcement point and authorization server:** a resource server may declare what each of its operations leaves behind — `reversible`, `compensatable`, `forward_recoverable` or `irreversible` — as a `consequence` member on the tool surfaces it publishes, inside the metadata it already signs. Her authority pulls it into her registry, her rules may read it as a condition that may only tighten, and the challenge carries it so an agent learns what it is asking for before it negotiates. An operation nobody has described satisfies no rule about remedy; an owner who wants to refuse the undescribed has a condition of her own for that. The grant records the class it was issued against, and the enforcement point refuses a call whose operation has since been re-declared as leaving less remedy. `make consequence-check`.
- **Organization authority:** a charter may require facts the organization is prepared to attest about a member — a licence, a jurisdiction — before her agents may act on its resources. Her authorization server fetches the attestation over its own membership credential and verifies it against the organization's published keys; a requirement from the charter is combined with one she wrote by intersection, so it reaches terms she had already written and she cannot edit it out. An unmet requirement refuses the negotiation before terms are dictated and records why. The grant carries a digest that the check happened rather than what it found. `make clearance-check`.
- **Owner API:** `GET /owner/policies` and `GET /owner/resources` now carry the declared consequence and any clearance requirement, and `GET /owner/policy-vocabulary` offers the new conditions, each marked as unable to relax a requirement.

#### Bug fixes

- **Organization authority:** a notice took its `jti` from the payload it carried, and both break-glass notices carried the override's id there — so a member's authorization server, which spends a notice once, refused the second as a replay. The member was told an override had been opened and never that it had been used. The notice's identity is now generated last, and the override's id travels as `family`, which both sides read.

## September 15 2026

### v2026.09.11

#### Bug fixes

- **Kubernetes:** `make k8s-reset` truncated grant state on `uma-as-db-1` by name, which fails once a failover has made that instance a read-only standby. It now runs against the cluster's current primary.

## September 14 2026

### v2026.09.10

#### Bug fixes

- **Organization authority:** a policy engine that answered with no decision — what OPA returns after a restart that lost the pushed policy — was read as allow. It is now treated as the engine failing: a recent decision for the same request stands for the grace window, and otherwise the request is refused.
- **Organization authority:** joining under a name already enrolled replaced that member's record, moving her notices and break-glass alerts to whatever authority the caller named. It is now refused with 409.
- **Enforcement point:** a request path under `/mcp/` whose first segment was not a known owner, shared resource or account was judged under the primary owner's authority. The owner is now read from the path prefix the gateway routes on, and an unknown path is refused with `invalid_resource_id`.
- **Kubernetes:** the edge's single wildcard listener admitted routes from every party namespace for any hostname, so one party could attach a more specific route to another's name and serve its own keys there. Each hostname now has its own listener that admits only the namespace owning it.
- **Agent operator:** `/register` accepted any caller's key, and a key listed in Alice's directory is how her authorization server recognises her own agents, so any agent could claim first-party standing. With `AGENT_OPERATOR_REGISTER_TOKEN` set, publishing a key takes that bearer credential; Alice's operator sets it in compose and Kubernetes, and the agent library sends `UMA4A_OPERATOR_REGISTER_TOKEN`.
- **Kubernetes:** the person server's admin token and Alice's operator registration token were committed literals reachable through the public edge. `make kind-up` now generates both as Secrets once per cluster.
- **Specification:** the drafts carried no date, so rendering them on any later day produced different output from what is committed and the check comparing the two failed. Each draft now states its date.
- **Owner portal:** notification toasts inserted their title and detail as markup, so an organization's break-glass reason or name ran as script in the owner's session. They are escaped.
- **Organization console:** a group id was placed inside inline event handlers and element ids, and a member's grants were shown unescaped, so either could run script in another administrator's console. The id is read from a data attribute and both are escaped.
- **TypeScript agent:** corroboration fetched whatever metadata URL the challenge named, so a forged challenge could vouch for its own authorization server. The URL is now formed from the resource called, and a challenge naming any other is refused.
- **Agent shim:** when the resource's metadata could not be read, the shim negotiated with the challenge's authorization server uncorroborated. It now refuses.
- **XAA broker:** administration accepted a realm token for an administrator issued to any client, including the public research agent. It now requires the token to be issued to `XAA_IDP_ADMIN_CLIENT`.
- **Owner portal:** signing in accepted any account the identity provider knows, and that session could read and trade the owner's vault. A sign-in whose username is not the portal's owner is refused.
- **Agent library:** every agent's key id defaulted to `agent-req-1`, so a second agent publishing to the same operator directory replaced the first's key and cost it its operator attribution. The default is now derived from the key.
- **Compose:** the edge's `:443` and DNS `:53` were published on every interface, so anyone on the same network reached the lab and its fixed credentials. Both are bound to loopback.
- **Authorization server:** resource servers still pending or already revoked kept writing the owner's registry on every pull. Only approved resource servers are pulled.
- **Authorization server:** a tier an owner created got an `alice/` terms id whoever the owner was, so another owner's terms link resolved to Alice's store. The id now carries the owner.
- **Authorization server:** a grant carried the scopes the resource registered for the attempt, not narrowed to what the terms offered or the agent agreed to. It now carries only scopes all three allow, and a request left with none is refused.
- **Authorization server:** an approval the agent had not yet collected survived the owner blocking its operator, and the next poll issued the grant. The poll now refuses once the operator is blocked.
- **Enforcement point:** while the organization or the joint tally was unreachable, an organization answer or a mandate of any age was used, and with nothing cached the organization's ceiling was dropped. A stale answer now stands only for `UMA_PEP_STALE_GRACE_S` (default 300 s); after that the resource is refused.
- **Agent library:** an identity requirement naming any audience was honoured, so a resource could have the agent fetch an assertion meant for a different authorization server. An ask whose audience is not the server being negotiated with is refused.
- **Agent shim:** a poll that failed in transit was treated as a dead ticket, and negotiating again put a second request in front of the owner. It is now treated as still waiting.
- **Authorization server:** an assertion's member was matched against the username, the email address, the part of the email before the @ or the subject, so an employee who edited their email could be taken for another member. An email counts only when the provider has verified it, and the local part never does.
- **Organization authority:** a charter's `identity_provider.subject_claim` was dropped when the charter was saved, so the organization could not pin which claim names a member. It is kept.
- **Authorization server:** after a database failover the connection listening for owner events closed and nothing reopened it, so live updates to the owner stopped. It now reconnects.
- **Authorization server:** a sub-agent admitted while its introducing agent was being revoked was written active after the revocation had swept, and kept working. The parent is checked again immediately before the child is written.
- **Enforcement point:** a break-glass override bound to no operation was accepted for a tool the deployment treats as single-use. It is refused like any other grant without the binding.
- **Tests:** `make pep-test` signs one holder's verdict with a key she never published and asserts it is not counted.
- **Authorization server:** the pulled resource registry is one process's copy for every owner it serves, and the owner's resource listing, tier creation, the organization views and `/perm` read all of it. Each now reads only the entries for that owner, so one owner's tool id never resolves against another's.
- **Gateway:** the ext_authz header allowlists in compose and Kubernetes did not forward `content-digest`, so a signature covering the body could never be checked and requiring one refused every call. The header is forwarded.
- **Agent shim, TypeScript agent:** tool calls were signed without covering their body, so anything between the agent and the enforcement point could change a call's arguments without breaking the signature. Both now sign an RFC 9530 `Content-Digest` over the exact bytes they send, and `signed_headers` in the agent library takes the body.
- **Authorization server, enforcement point, joint tally:** an operation's `params_s256` was computed over Python's default JSON output, with spaces after separators, while `authorization_reference` used the compact form; an implementation in another language could not reproduce either without copying that detail. All of them now hash the compact, key-sorted UTF-8 form (RFC 8785 for the values these carry).
- **Tests:** joint-check's two forgery probes were re-signed by the script, so tally introspection refused them before any verdict was counted, and the conformance register cited them as proof of the verdict and mandate checks. The probes are renamed to what they prove, and the register rows now cite `make pep-test`'s verdict-signature and published-mandate cases and a new `make as-test` case comparing a folded agreement against a holder's terms.
- **Organization authority:** removing a member deleted her record before sending the `membership_ended` notice, so it was never sent. The notice goes first.
- **Organization authority:** a notice her authority answered with an error was logged as delivered, and break-glass was issued whether or not she could be told. A notice now counts as delivered only on success, and a break-glass override her authority could not be told of is voided and refused with 503.
- **Authorization server:** organization notices carried no expiry or identifier and were acted on however many times they were posted. Notices now carry `exp` and `jti`, and one already received, expired or of the wrong type is refused.
- **XAA broker:** an access token, or a token issued to another client that listed this one in its audience, was accepted as an employee's ID token. The token must be an ID token issued to the client presenting it.
- **XAA broker:** without `XAA_IDP_ISSUER` set, the broker trusted a different realm from the one compose configures as the employee directory. The default is the employee directory.
- **Authorization server:** blocking an operator revoked its agents' connections but not the sub-agents they had introduced. Those are revoked too.
- **Authorization server:** a request refused because no tier covered the resource, or because the owner's queue was full, left no entry in her record. Both are recorded.
- **Owner portal:** a failed token refresh left the session signed in, and the portfolio, transactions and trade routes never checked the token, so the portal kept reading and trading her vault after her provider session ended. A failed refresh ends the session, and those routes require a live token.
- **Owner portal:** the live-events proxy answered 200 with an empty stream when her authority refused the token, so the page reconnected indefinitely and alerts never arrived. The refusal is passed on.
- **Joint tally:** a holder authority refusing to answer (4xx) was treated as unreachable, leaving the request pending with no end. It is counted as her refusal. A failure fetching her keys to check a verdict escaped `/token` as a 500 after the ticket was spent; the request now stays pending.
- **Enforcement point:** the sidecar read a request body of any size before authorizing it. Bodies over `UMA_PEP_MAX_BODY_BYTES` (default 1 MiB) are refused with 413.
- **Agent library:** the trust store for the identity provider was written to a fixed path under `/tmp`, where another local user could add a CA. It is a private temporary file.
- **Compose:** `make smoke-test` printed FAIL for a failed check but exited 0, so `check-live` and `check-all` reported success. A failed check now fails the target.
- **Compose:** `make demo-all ACT=tier1 SIM=0` ignored `ACT` and treated `SIM=0` as asking to simulate Alice, so nothing reached her portal. Both now mean what the docs say.
- **Codespaces:** `.devcontainer/expose-web.sh` read the Keycloak admin user from the `alice` namespace, where Keycloak does not run, and stopped part-way through. It reads from `idp`.
- **Owner portal:** the default `OIDC_CLIENT_ID` was `meridian-portal`; it is `alice-portal`, the client her realm defines and the configuration reference names.
- **kagent check:** a failed read of her ledger counted as zero touches, so a failed baseline passed the check's decisive assertion. It now fails the check.
- **Conformance tool:** `integrations/conformance.py` accepted a metadata document for any resource on the same host, its proof-of-possession check could not fail, and an upstream that refused a direct call with 403 was scored as reachable. It now requires the exact resource URL, sends an unsigned proof-of-possession request, and counts a refusal as refused.
- **Tests:** the signature test for another authority also changed the `Authorization` header, so it would pass even if the authority were ignored. It changes only the authority.
- **Enforcement point:** when the authorization server could not be reached, introspection raised a 500 or sent the agent to negotiate a grant it already held, and a failed spend was reported as `already_consumed`. Both now answer 503 `temporarily_unavailable`.
- **Enforcement point:** the sidecar answered one 502 whether the resource never received a call or received it and did not answer, and an agent retrying the second could act twice. A call that was not delivered is 502; one delivered without an answer is 504 and says it may have been carried out.
- **Authorization server:** an unauthenticated client-credentials request created records for whatever owner it named. Records are created only after the resource server authenticates.
- **Authorization server:** verifying an identity assertion fetched the provider's keys on the event loop, stalling every request while the provider was slow. It runs off the loop. Each assertion is now spent once in the shared store rather than in one process's memory, so it cannot be replayed at another replica.
- **Authorization server:** the recurring registration pull fetched whatever URLs a resource server's metadata named, without the size limit or origin checks registration applies. Each fetch is capped at 1 MiB, and `jwks_uri` and the owner-resources endpoint must be https on the resource's own origin.
- **Authorization server:** owner authentication verified OIDC tokens synchronously on the event loop, fetching the realm's keys there. It runs off the loop.
- **Kubernetes:** `policy-test` counted any transport error as the mesh refusing, so a database answering an HTTP request by closing the connection, a stopped service or a wrong port all passed as refusals. Only a 403 or a reset connection counts.
- **Tests:** the organization-unreachable requirement cited a check that runs with the organization up. `make as-test` now makes it unreachable and asserts the refusal, and the register cites that. The lineage `act` claim was tested against a copy of the extraction; it is now `introduction.act_of`, which both the authorization server and the test call. `joint-check`, `xaa-check` and the live Okta check restore the lab however they exit.
- **Personal AI ability:** a standing answer for a tier also approved agents meeting her for the first time at that tier. First contact is always put to her.
- **Authorization server:** an introduced agent's pending bound counted operation requests from every connected agent, so traffic from agents never bound by it could refuse a sub-agent. Only operation requests from introduced connections count.
- **Authorization server:** joining a jointly held account did not check her tiers, so one tier could govern the account's resources and her own together. Joining is refused until such a tier is split.
- **Kubernetes:** the sterling-vance key job's comments said its Role could never rotate an existing key and named the wrong script. They now describe `agent-keys.py`, the keys it rotates on purpose, and that the script rather than RBAC keeps the long-lived keys stable.
- **Organization authority:** enrolment did not record which charter a member had been shown, so one published between her preview and her join applied to her unseen. The portal sends the previewed version, and a join against a newer charter is refused with 409.
- **Organization authority:** charter and group edits read the charter, awaited the policy engine, then appended, so two edits at once could each overwrite the other's change. Publishing now happens one at a time, and group edits and charter writes that carry `base_version` are refused with 409 when the charter has moved on.
- **Authorization server:** a membership refresh and an organization block each rewrote the whole membership record, so running together they could undo each other. Each now updates only its own key in one statement.
- **Kubernetes:** nothing at the waypoint restricted who could call her personal AI, whose pod holds her device key. A policy on its Service admits no inbound calls.
- **Docs:** the event register listed four events nothing emits and left out most that are. The phantom rows are removed and every other emitted event is listed by component.
- **Docs:** run-the-lab and KUBERNETES quoted a policy-test pair no check prints and an out-of-date count. Both give the count the suite has and say what a refusal means.
- **Docs:** START-HERE said `make kagent` brings its own model; it uses Anthropic by default, and `MODEL=ollama` runs one in the cluster.

## September 13 2026

### v2026.09.9

#### Enhancements

- **Specification:** all nine drafts are declared informational individual submissions (`category: info`) rather than standards-track.
- **Specification:** IANA Considerations request no actions. Each draft lists the identifiers it defines in an informative appendix instead of registration templates.
- **Specification:** the core draft's abstract, introduction and roles are rewritten. The software making a request is UMA's client; "Requesting Agent" is left to UMA's legal work, where it names a party; the client operator is defined; and the list of departures says whether each one profiles, extends or diverges from UMA 2.0.
- **Specification:** `terms_endpoint` is defined by the terms draft rather than the core draft.
- **Specification:** the exact form of an identified connection handle, the `contract` claim, the parameters an operation binding covers, and the octets an agreement digest is computed over are specified.
- **Docs:** the parties, concepts, glossary, architecture and comparison pages use client for the software making a request, and no longer say UMA 2.0 merged the requesting party with it.

#### Bug fixes

- **Specification:** the AAuth binding qualified identified connection handles by issuer host alone, contradicting the core draft.
- **Specification:** the multiparty verdict's `cnf_jkt` was defined as a bare thumbprint while its example carried the `jkt:` prefix; it is now `jkt(k)`.
- **Specification:** four cross-document section references pointed at the wrong sections.
- **Docs:** the specification page, the deviations page and `docs/PROTOCOL.md` cited §11 for the core draft's register of departures, which is §12.
- **Specification:** the core draft's design rule listed the `WWW-Authenticate: UMA` header as reused unchanged, contradicting its own departure 8; it now says the header is kept over HTTP but is no longer the only encoding.
- **Specification:** the federated authorization draft cited RFC 9728 §2.1 for `signed_metadata` (it is §2.2), and the terms draft cited UMA Grant §3.3.4 for `need_info` (it is §3.3.6). The core draft and the deviations page cited UMA Grant §3.3.1 for single-use permission tickets (§5.5) and for the authorization server's responses (§3.3.5 and §3.3.6).
- **Specification:** the policy draft now states that its `429` refusal at the pending-queue bound departs from UMA Grant's `403` for `request_denied`, and why.
- **Specification:** the identifier appendices were incomplete. Added: core's `insufficient_authorization`, `PoP` and the remediation members; terms' `decline` and `receipt`; lineage's `introduction` claim; multiparty's `org`, `kind` and `admin` claims. The multiparty draft now defines the `u4a-org-admin+jwt` credential it listed.
- **Specification:** the core draft said digests are taken over "canonical JSON" without defining it, and `params_s256` did not rule out whitespace. Digests over JSON values are now over the RFC 8785 serialization. Core §6.1 also states that a request with no `Authorization` header covers the `authorization` component with the empty string, and that this departs from RFC 9421 §2.5.
- **Specification:** core did not say which requests "carry meaning in the body" and must cover `Content-Digest`, or how a client presents the token; it now says any request with a body, and `Authorization: PoP <token>`, noting the scheme is unregistered. The lineage draft and the sub-agent page credited AAuth's agent credential with `act`, which AAuth carries on its auth token. The AAuth binding attributed its resource-metadata type correctly.
- **Specification:** example digests and thumbprints are full length, the MCP binding's remediation example matches the core draft's, and references a conforming implementation needs are normative.

## September 12 2026

### v2026.09.8

#### Enhancements

- **Enforcement point:** a permission's own scopes, `exp` and `nbf` are checked, not only its resource.
- **Enforcement point:** a grant marked single-use is spent wherever it is presented, and a tool the deployment treats as single-use refuses a grant bound to no operation.
- **Enforcement point:** a signature covering `Content-Digest` is checked against the body the gateway received; `UMA_PEP_REQUIRE_CONTENT_DIGEST` makes covering it mandatory.
- **Joint ownership:** an allow verdict states the key, scopes, lifetime and operation its holder agreed to, and the digest of the mandate she counted under. The enforcement point refuses a grant it cannot re-derive from those, a published mandate no verdict was given under, a mandate that does not cover the resource, and a grant with no verdicts at a jointly held account.
- **Joint tally:** grants are issued from the scopes and lifetime of the signed agreement, bounded by the folded terms.
- **Specification:** new requirements for each of the above and for each fix below, with register rows. The core draft's comparison with GNAP now reflects RFC 9635 §1.6.4, which does describe an absent resource owner approving asynchronously.
- **Tests:** `make as-test` for the authorization server's handlers and `make client-test` for the agent side, both in CI.

#### Bug fixes

- **Authorization server:** a reusable grant invalidated by revoking a connection became valid again when the same agent was admitted again. It now stays inactive, with the introspection reason `revoked`.
- **Authorization server:** introspection answered for a token of any owner under any owner's PAT.
- **Authorization server:** identified agents from two tenants of one identity provider shared a connection, because the handle was qualified by the issuer's host and not its path.
- **Authorization server:** an agreement could add scopes the terms did not offer, and a grant lasted as long as the terms allowed rather than as long as the agent agreed.
- **Authorization server:** once an owner approved a jointly held request, her authority signed an allow verdict over whatever agreement the tally presented next.
- **Authorization server:** a poll rotating its ticket could erase a decision made moments earlier; an administrator's approval could be recorded as the owner's own when a poll landed between two writes; and on Postgres a default tier she deleted was restored by the next PAT request. A decision and its author are now written together and once, and an owner is seeded once.
- **Authorization server:** a holder who stayed in a mandate but changed issuer or weight was not shown to her as a change.
- **Enforcement point:** a published mandate whose rule carried no threshold counted to zero.
- **Agent:** enterprise credentials were sent to whatever token endpoint a challenge named. `Enterprise` now names its identity provider, and nothing is sent anywhere else.
- **Agent shim:** a receipt's filename came from its unverified payload and could escape the receipts directory, and the challenge a resource enforcing in-process emits was not recognised.
- **Personal AI ability:** a decision her authority failed to record was logged as made and never sent again.

## September 11 2026

### v2026.09.7

#### New

- **Blog:** [An Agent Is Not a Principal](/blog/2026-09-11-an-agent-is-not-a-principal/) — why delegating a delegation is a category error, why an enterprise identity provider has no standing over a resource it does not own, how lineage is attested rather than transferred, and what the owner decides. Ends with a tutorial for implementing sub-agent grants on either side, with the refusals an implementer will meet and what each one means.

#### Enhancements

- **Docs:** the specification-set page states what each document covers instead of explaining how it came to be written, and the count of drafts is right in every place that gives one.
- **Blog:** *Everything You Need to Know About Deploying U4A at Scale* — key rotation and multiple owners naming different authorities were listed as open; both have since been built, and the section now says what the answers are. *Let Them* cites the RAR-metadata draft under the name it was adopted with, `draft-ietf-oauth-rar-metadata-remediation`. Both posts point at the specification set.

#### Bug fixes

- **Specification:** every cross-reference between the drafts linked to a datatracker URL for a document that has never been submitted there, so all nine 404'd. Each now resolves to its rendered page on this site. The 2010 Kantara claims reference pointed at a Confluence space that is gone; it is cited without a URL rather than with a dead one.

### v2026.09.6

#### New

- **Specification:** nine Internet-Drafts profiling and extending UMA 2.0 for autonomous agents, in `spec/src` and rendered to `site/static/spec/`: `draft-gamb-uma4agents-core-00` (the grant profile), `-terms-00` (owner-proffered terms), `-fedauthz-00` (federated authorization for agents), `-policy-00` (owner policy, assurance and attention), `-lineage-00` (agent lineage), `-multiparty-00` (organizations and co-ownership), `-owner-00` (the resource owner's API), `-mcp-00` (the MCP binding) and `-aauth-00` (the AAuth binding). `make spec` renders them through kramdown-rfc and xml2rfc in a container. Each has an identifying URI under `https://u4a.ai/spec/` that dereferences to the draft.
- **Specification:** `spec/conformance.yaml` maps every normative statement in the drafts to the check that proves it, and `make spec-check` fails the build if a statement has no row, a row cites an assertion nothing prints, or a make target that does not exist. The register is published at `/spec/conformance.yaml`.
- **Clients:** `clients/ts-agent` — a requesting agent in TypeScript sharing no code with the Python one: discovery, corroboration, the agreement, the wait, proof of possession, both challenge encodings. `make ts-agent-check` runs the four beats with it against the lab.
- **Authorization server:** metadata carries `uma_profiles_supported` with the identifying URI of each document in the set it implements, plus `consume_endpoint` and `owner_endpoint`, and is served at `/.well-known/uma2-configuration` as well as `/.well-known/uma4agents-configuration`. `grant_types_supported` and `claim_token_formats_supported` now list every value `/token` accepts. The tally advertises the three documents a counting party speaks, at both paths.
- **Authorization server:** signing-key rotation. `UMA_AS_KID` names the current key, `UMA_AS_PREVIOUS_KEYS` / `UMA_AS_PREVIOUS_KIDS` the retired ones; `/jwks` publishes the set, tokens are verified by the kid they carry, and the enforcement point refetches a key set on a signature it cannot verify rather than waiting out its cache. `make rotation-check` rotates under live grants on a Postgres-backed server and restores.
- **Enforcement point:** `make pep-test` — the refusals the enforcer makes before it asks anybody (routing-header mismatch, missing routing headers, foreign origin, bearer scheme, unknown method or tool), and that the challenge is one object under both encodings.
- **Checks:** `make check-all` runs every suite the register cites — the unit half, the register, then everything against the compose stack. `.github/workflows/ci.yml` runs the unit half, the draft render with the register, and the site build on the pinned Node on every push.
- **Docs:** `/docs/reference/specification/` — the set, what each document carries, and how the register works. The deviations page is numbered as Core §11 numbers the register — 22 entries — and names where each departure is specified. Every place that said there was no specification now points at it.

#### Enhancements

- **Authorization server:** `UMA_AS_RPT_AUDIENCE` sets the `aud` on every grant, replacing a lab constant.
- **Enforcement point:** `UMA_PEP_HOLDER_JWKS_TTL_S` sets how long a co-owner's published keys are reused for verifying verdicts, replacing a hardcoded 300 s. `UMA_PEP_MANDATE_TTL_S` is now in the configuration reference.
- **Authorization server:** a tier's `constraints` are editable through the owner API like its other terms fields.
- **Checks:** `smoke-test` asserts the profile URIs, every advertised grant type and claim format, and that a truncated authorization body is refused as `request_body_too_large`; `intent-check` asserts the three representations of a terms document at one URI and the countersigned receipt; `embedded-check` asserts every in-process refusal and that a forged replay of a single-use grant leaves it spendable; `sig-test` asserts a signature over another authority is rejected, a required body digest cannot be omitted, and another signature label is refused. `run_job` in `Makefile.k8s` regenerates the driver configmaps, so an edited check runs in the cluster as itself.
- **Docs:** the extension registers in `docs/PROTOCOL.md` and the site had diverged (three entries in each the other lacked); both now carry the same 22, cross-referenced to the drafts. `connection.introduced` and `connection.introduction_refused` are in the event register. Citations updated to the adopted `draft-ietf-oauth-rar-metadata-remediation`, the OAuth WG's client-ID-metadata draft, the webbotauth drafts, and `draft-hardt-aauth-protocol-01`; the Julie Adams report is cited as the Kantara UMA WG wiki lists it. `integrations/conformance.py` checks that the authorization server a resource names advertises this profile.

#### Bug fixes

- **Enforcement point:** a challenge for a call to the bare `/mcp` alias named the owner's per-path metadata document, whose `resource` is her canonical path; a client following the pointer, as the profile requires, is obliged by RFC 9728 §3.3 to reject it. The pointer now names the document for the path the request was made to. Found by the TypeScript agent on its first run.
- **Resource:** the vault image copied `uma4a_pep.py` without `uma4a_joint.py` and `uma4a_org.py`, which it has imported since joint ownership landed, so `ENFORCEMENT_MODE=embedded` and the minimal fixture failed on import. Both modules are copied.
- **Authorization server:** the never-met branch of `standing_facts` returned a trajectory without `calls`, unlike the store.
- **Checks:** `intent-check` read the owner's queue and then listed it again to approve, and a pend arriving between the two was approved unread; on three replicas behind the edge that gap was wide enough to hit. It now answers the listing it read.
- **Docs:** assertion counts in `docs/JOINT.md` and the joint-ownership page said 29 where the suite prints 37, and `k8s-smoke-test` prints 15 where the docs said 13; `docs/MCP-BINDING.md`'s and the site's in-process challenge example carried an error value the code does not send and omitted two fields.

### v2026.09.5

#### New

- **Enforcement point:** the tool surface is configurable. `UMA_PEP_TOOLS` names a JSON document mapping each MCP tool to a resource id, its scopes and whether its grant is single-use — which is what the owner's tiers can name, and therefore what she can approve separately. Absent, the lab's own surface is used. A malformed document stops the service rather than silently protecting the wrong tools.

- **Enforcement point:** `UMA_PEP_UPSTREAM_HEADER` and `UMA_PEP_UPSTREAM_AUTH` present a credential the upstream requires, so a resource fronted by the sidecar is not reachable around it by anyone who learns its URL.
- **Integrations:** `integrations/n8n/lab/` runs a live n8n behind a live sidecar in the lab's cluster, with a step-by-step walkthrough, and `docs/n8n-sidecar.svg` shows the flow and what is on the wire at each beat.

#### Bug fixes

- **Enforcement point:** in sidecar mode the request path was appended to `UMA_PEP_UPSTREAM` even when that named a path, so fronting a workflow tool's generated URL produced `/mcp/<id>/mcp` and a 404 that explained nothing. A configured path is now the endpoint; a bare origin still keeps the request path.
- **Enforcement point:** the upstream's `content-encoding` and `content-length` were forwarded alongside a body the sidecar had already decoded, so the client decompressed twice and failed on a header check that read like a corrupt response.
- **Integrations:** the n8n kit described a `tools.json` nothing read, an environment variable that did not exist, a client secret the registration flow does not use, and an image that was never published. It omitted the step that matters most — the owner authorizing the resource server before it can protect anything. Corrected, and the sidecar path is now verified end to end against the lab.

## September 10 2026

### v2026.09.4

#### New

- **Authorization server:** sub-agent grants. An agent holding a connection may introduce a sibling, which skips first contact and then negotiates its own terms under its own key for its own grant. Nothing is passed down and nothing is inherited.
- **Authorization server:** two ways to prove a lineage — a compact JWS signed by the introducing agent over the newcomer's key, or RFC 8693's `act` claim in a verified `aa-agent+jwt`, which is where AAuth already names the entity a request was made on behalf of.
- **Authorization server:** an agent's approval at a tier is read across its lineage, in both directions, so a tier a sub-agent earns is one the agent that introduced it stops being asked about.
- **Authorization server:** `standing.introduced` and `standing.lineage_new_at_tier`, both observed conditions. They give an owner three postures per tier — ask about every agent, ask once per fleet, or always ask about sub-agents — without either being able to widen access.
- **Authorization server:** revoking a connection revokes the ones it introduced, in the same action, and reports the count.
- **Authorization server:** `UMA_AS_SUBAGENT_FANOUT` caps how many live sub-agents one agent may have. Sub-agents also count against the owner's attention budget, and their per-operation pends count with them.
- **Store:** `lineage_approvals` and `count_children` on both backends, with an index on the parent handle.
- **Portal:** the connections table names the agent that introduced each one, and the revoke toast reports the sub-agents that went with it.
- **Docs:** `docs/SUBAGENTS.md`, a run card, a Lab demonstrations page, an overview page and a flow diagram.

#### Enhancements

- **Docs:** the events reference publishes the ledger's row shape and all twenty-three entry kinds, with the fields each one's `entry` carries. Only the five-item projection her portal renders had been documented.
- **Docs:** the revocation page states how long revocation actually takes, and separates the part that lands on the agent's next call from the enforcement point's caches of organization membership (10s), joint mandates (30s) and published keys (300s), which had gone unmentioned on a page claiming atomicity.
- **Docs:** the architecture page says how its absences are proved, and links the eleven-assertion suite — eight of them refusals — that asserts them from the requesting party's own namespace.

#### New

- **Enforcement point:** a sidecar mode. Setting `UMA_PEP_UPSTREAM` turns the enforcement point from a gateway callout into a reverse proxy that authorizes and then forwards, so U4A can be put in front of an MCP server whose author cannot change it. The verdict comes from the same code path as the callout. The agent's `Authorization` header is not forwarded upstream.
- **Integrations:** `integrations/` — the vendor-neutral contract for putting U4A in front of an existing resource, a worked n8n example with an importable workflow template and a compose file, and `conformance.py`, which asserts the four obligations from outside including that the upstream is not reachable around the enforcement point.
- **Docs:** a guide, *Put U4A in front of something you did not write*.

#### Bug fixes

- **Kubernetes:** `agent-keys.py` skipped provisioning entirely when the Secret already existed, so an agent added to the list was never given a key and was left an assurance level below where it should be, with nothing logging a reason. It now adds missing agents by JSON Patch, and names given after `--rotate` get a fresh key each apply.

## September 1 2026

### v2026.09.3

#### Enhancements

- **Docs:** the Lab demonstrations pages carry everything the run cards do — the setup, where to sign in, the Codespace and re-run notes, and how to switch model provider — with every command in a copyable block.
- **Docs:** the README and the Codespace walkthrough link the run cards.

### v2026.09.2

#### Bug fixes

- **Docs:** `make kagent` was still described as the local no-account path in `KAGENT.md`, `DEMOS.md`, `KUBERNETES.md` and the Run the lab guide after the default became a hosted model, and `kagent.sh` pinned an Anthropic model two releases behind the one the demo cards name.
- **Docs:** the Lab demonstrations pages reproduce their run cards rather than paraphrasing them, and are generated from those cards so the two cannot drift.
- **Agent shim:** `Upstream.resume()` reported "still waiting" as a bare string, the same type as the grant it had to be distinguished from. It returns an explicit state.

### v2026.09.1

#### New

- **Demos:** a run sheet per use case, in `docs/cards/` and under Guides → [Lab demonstrations](/docs/guides/demos/). Each one is driven by asking an agent a question and then deciding as the owner, rather than by running a check.
- **kagent:** `RESOURCE=` points an agent at Carol's account, a jointly held account, the firm's book, or an agent the owner operates herself — `make kagent RESOURCE=carol|joint|either|shared|hers`. Each resource publishes the authority that speaks for it, so which owner decides follows from the resource rather than from configuration.
- **Agent shim:** `UMA4A_PUBLISH_TO` publishes the adapter's signing key in an operator's key directory and names that origin as its client id, so an adapter can be the owner's own agent rather than a third party's.
- **Kubernetes:** `make k8s-demo` and `make k8s-joint-demo`, `k8s-multi-owner-demo`, `k8s-first-party-demo` — the same negotiations with nobody answering for the owner, following the Job's log rather than printing it at the end.

#### Enhancements

- **Agent shim:** a pending decision is returned as a result rather than holding the call open, for any client that cannot render an elicitation. Nothing between the agent and the owner has to keep a connection alive while she decides.
- **Agent shim:** a retry resumes the request the owner is already deciding instead of opening a second one. Re-negotiating spends the attention budget her authority keeps per agent (`UMA_AS_PEND_BUDGET`), so an agent that checked a handful of times was refused with *not accepting new agent requests* — correctly, for behaving like a nuisance.
- **kagent:** hosted models are the default; `MODEL=ollama` remains, pinned to `qwen3.5:9b`.
- **Demo driver:** the owner's decision window is `UMA4A_OWNER_WAIT_S` (900s) when nobody is simulating her. 120s is a headless budget.

#### Bug fixes

- **Kubernetes:** `run_job` waited on `Complete` *and* `Failed`, and `kubectl wait` keeps only the last `--for` — so it waited on `Failed` alone. A job that succeeded ran to the full timeout, and where that outlived the job's `ttlSecondsAfterFinished` the Job was collected before its logs printed, failing a run that had passed. `k8s-joint-check` and `k8s-org-check` failed outright; every other check paid for it in wall time. `make k8s-smoke-test` now finishes in seconds rather than minutes.
- **Docs:** `DEMOS.md` said an ask-me tier pends to her portal while her personal AI is up. It is refused — the ability records *no channel to her* and stops, which is the safe answer when the one thing it cannot do is ask her.
- **Demo cards:** the pages declare their character set. Without it they rendered as Latin-1 and every `·` and `→` came out as mojibake.

## August 26 2026

### v2026.08.26

#### New

- **Cross App Access:** `identity_provider.subject_map` in the charter — what a provider asserts, mapped to the member it means. A real tenant's `sub` is local to that tenant, so somebody has to say who it is, and the organization is the party that knows.
- **Cross App Access:** `make okta-live` runs the whole negotiation against a real tenant rather than the provider shipped beside the lab.

#### Bug fixes

- **Agent:** the token exchange borrowed the client configured for the resource server, so an agent in a deployment with a private CA could not reach a public identity provider at all — `CERTIFICATE_VERIFY_FAILED` at the moment it left the deployment. It now verifies against the public roots *and* the deployment's CA, taken from the caller, the environment or the conventional path in that order.
- **Enforcement point:** how long a refusal may be worded from a cached description of the organization is configurable (`UMA_PEP_ORG_DISCOVERY_TTL_S`), and the lab sets it short. A charter that had just started federating was described from a copy read before it did.


### v2026.08.25

#### New

- **Cross App Access:** an organization may federate identity to an enterprise identity provider. Its charter names the provider; a member's authority then asks an agent whose employee it acts for, as an ID-JAG (`draft-ietf-oauth-identity-assertion-authz-grant`) carried in the UMA claim it already had a slot for. Identity is asked for before terms, because which terms apply follows from which member it is.
- **Cross App Access:** new `northwind-idp` — the customer enterprise's own identity provider, a separate deployment from the one Meridian authenticates its surfaces with. A token from Meridian's provider is not an employee assertion.
- **Authorization server:** verified against a real tenant. Provider keys are found by OpenID discovery rather than a lab convention, permitted algorithms come from the key's type rather than the token's header, provider TLS verifies against the public roots *with* the lab CA added, and signature failures are reported separately from issuer and audience ones.
- **Cross App Access:** new `xaa-broker` service — the exchange endpoint, holding the application-to-resource edges an administrator approved. It stands in for a tenant that issues ID-JAGs itself; keys are resolved by discovery, permitted algorithms come from the key's type, and the claim naming the person is configurable, so a charter can name a real tenant instead.
- **Organization:** a member can enrol because her employer's directory vouches for her, instead of with a shared code. Only where the charter names a provider, and one employee's token does not enrol another.
- **Organization:** Charter → Settings gains federated identity — switch it on, name the provider and directory, and choose whether people may enrol without a code.
- **Authorization server:** an assertion is bound to one authorization server, one member and one use, and is only ever asked for over resources the organization actually reaches — never a member's own accounts, never anything she holds jointly.
- **Agent:** `Enterprise` credentials on the grant loop. An agent carrying them satisfies an identity challenge from a server it has never heard of; the challenge names the provider, the audience, the resource and the scope.

#### Enhancements

- **Docs:** [Try it with Okta](/docs/guides/okta-cross-app-access/) — registering the AI agent, the two fields on the resource app that decide `aud` and `aud_tenant`, the resource connection, and the organization console side. Verified against a trial tenant.
- **Docs:** an animated diagram of the two halves, from the challenge through the assertion to the three ceilings.
- **Enforcement point:** a resource refused because the caller is not a member of the organization that owns it now names that organization, and says how membership is come by where its charter federates identity. An assertion still enrols nobody — joining is agreed to, not asserted.

## August 25 2026

### v2026.08.24

#### Enhancements

- **Docs:** search moved from the docs tab bar into the site navigation. It already covered the blog and the changelog; now it is reachable from them.
- **Docs:** a long changelog contents folds into a disclosure below 1080px, rather than standing between the reader and the first release.

### v2026.08.23

#### New

- **Docs:** a changelog at `/changelog/`, back to the first release. In `⌘K` search as one row per release, in `llms.txt`, in the sitemap, published as `/changelog.md`, and readable over MCP with a new `listChangelog` tool.

#### Bug fixes

- **Docs:** contents links stopped working after the first click on every doc, post and changelog page. Heading ids were set on the live DOM and lost on the next re-render; they are part of the rendered HTML now.

### v2026.08.22

#### Enhancements

- **Organization:** a charter may only claim a namespace it names. `northwind-vault/*` is accepted; `*/get_positions` is refused.
- **Authorization server:** an organization reaches nothing an owner holds jointly with somebody else, whatever its charter claims. Enforced at her authority, not in the charter.
- **Authorization server:** terms over a jointly held resource can no longer share a tier with anything else.
- **Portal:** Agent Access → **Joint accounts** — who else holds each account, what it takes to release it, and a preview to agree to before joining.

#### Bug fixes

- **Authorization server:** the two organization-admin endpoints returned 500 instead of filtering a jointly held resource out of the results.

### v2026.08.21

#### New

- **Joint ownership:** a resource can have several owners of equal standing, none of whom can decide alone. A published **mandate** names who is entitled to be counted, at what weight and how many it takes; each owner's authority signs a **verdict** bound to one negotiation and one agreement; a **tally** collects them.
- **Tally:** new `joint-tally` service, speaking an ordinary authorization-server surface so an unmodified agent negotiates with it as with any authority. Reachable at `/mcp/joint/<account>`.
- **Tally:** every holder's terms are folded into the single document the agent signs: shortest expiry, intersected scopes, unioned prohibitions. Each holder's authority refuses anything signed that is wider than what she published.
- **Enforcement point:** a joint grant carries the holders' signed verdicts. Each is verified against that holder's published keys and the count is re-run before the call is allowed.
- **Authorization server:** `/owner/joint` to join, preview and leave a mandate; `/joint/quote` and `/joint/verdict` for the tally, answered only for a mandate she agreed to.
- **Kubernetes:** the tally runs in a namespace of its own, belonging to neither owner.

#### Bug fixes

- **Authorization server:** `save_negotiation` creates a negotiation that never had a ticket. On Postgres it was an UPDATE that matched no row, so a request created by another owner's tally never reached the owner's queue and timed out.
- **Kubernetes:** `joint-vault` gained the AuthorizationPolicy naming its caller. Without it the mesh reset the connection and the gateway reported a 500 from an upstream that never saw the request.
- **Kubernetes:** `policy-test` declares its own ServiceAccount rather than borrowing one from `smoke-test`, which made it unschedulable on a fresh cluster.

### v2026.08.20

#### New

- **Organization:** an organization can own resources, share them with members under a role, and set policy over them. Each member administers access through her own authorization server and her own terms. New `org-authority` service.
- **Console:** new `org-console`, the administrator's surface. The charter is editable as a form or as JSON, with a Rego editor for the organization's own operating rules.
- **Organization:** roles carry `delegation` — `none`, `first-party-only`, `any-agent` — naming *whose* agent may act on a shared resource.
- **Organization:** groups are managed from the console: create one, set what it reaches, choose which one joiners land in, move members between them. Each publishes a charter version.
- **Organization:** break-glass grants, signed by the organization and recognised at the enforcement point by issuer. Bounded by a disclosed clause, single-use, and notified to the member when opened.
- **Authorization server:** an organization's ceiling is clamped into her terms on write, so it appears in the document the agent signs.
- **Resource server:** `/mcp/shared/<member>` — one resource administered by several people, each under her own authority.

## August 23 2026

### v2026.08.19

#### New

- **Authorization server:** one resource server can hold many people's accounts, each governed by an authorization server of her own. Every owner-scoped artifact carries its owner: the ticket, the grant, the resource id, the terms template and the RFC 9728 document.
- **Resource server:** `POST /rs/register` — a resource server introduces itself to an authority nobody configured it against, signing with a key published at the origin of the resource it serves. Registration is `pending` until the owner authorizes it.
- **Authorization server:** a second owner runs in the lab on her own authority.

## August 21 2026

### v2026.08.18

#### Enhancements

- **kagent:** `make kagent-ask Q=…` asks your own question instead of a hardcoded one, and `SIM=0` lets a person answer the request rather than the check answering it.

#### Bug fixes

- **kagent:** the model config dropped its final line for any provider without an extra block, so `anthropic` and `openai` produced an invalid config.

### v2026.08.17

#### Enhancements

- **Licensing:** `NOTICE` rewritten from a component-by-component audit, separating the application stack, the Kubernetes platform, the website and upstream checkouts. One licence had been stated incorrectly.

## August 20 2026

### v2026.08.16

#### New

- **Authorization server:** `standing.first_party` — an agent is first-party when the operator it names is an origin the owner claimed *and* her authority found that agent's key published in that operator's directory.
- **Authorization server:** the owner as requesting party, with her own agent as a third party. No new branch in the grant loop.

## August 19 2026

### v2026.08.15

#### Bug fixes

- **Authorization server:** the derived `enforced` annotation was written through `publish_terms`, which is idempotent per template id — so on any store that had already published a version the field was dropped and never appeared. Postgres failed where the in-memory store passed, because the latter republishes on every boot.

### v2026.08.14

#### Enhancements

- **Authorization server:** her terms mark which prohibitions the enforcement point refuses outright — `operation_mismatch` and `already_consumed` — rather than presenting every line as equally a matter of trust.

### v2026.08.13

#### New

- **Protocol:** two optional requester-authored claims on the agreement — a stated reason and a cited mandate — recorded and shown to the owner, never judged. The requesting side previously had nowhere to say what it was asking for.
- **Authorization server:** every ledger entry with a party to name is attributed, so a refused or denied exchange can be traced to an agent.

#### Bug fixes

- **Portal:** requester-supplied strings were rendered unescaped.

## August 17 2026

### v2026.08.12

#### Enhancements

- **Docs:** the assurance material split by subject — what an authority can verify, the owner's attention as a denial-of-service surface, revoking an operator rather than an agent, and a guide to writing rules.

### v2026.08.11

#### Enhancements

- **Authorization server:** the owner configures the attention budget and the assurance floors from her portal, rather than them being constants.

#### Bug fixes

- **Authorization server:** `assess()` returned `binding: 1` unconditionally. Every axis now starts at 0 and is raised only by a check that ran and passed in this negotiation.

### v2026.08.10

#### New

- **Authorization server:** agent assurance — three axes an owner's authority can establish about the asking agent (binding, provenance, accountability), readable by her rules without naming an agent. No level grants access; a strong showing can only stop a rule from firing.
- **Authorization server:** a depth budget on the owner's attention, counted per lane, so a flood of anonymous agents cannot crowd out an attributable one.

## August 16 2026

### v2026.08.9

#### Enhancements

- **Docs:** the owner's side described as it now works — a browser session *or* a signature from a key her own device holds. The walkthrough gains a route to the personal-AI demo.

### v2026.08.8

#### New

- **Kwaai binding:** Kwaai's pAI-OS runs in the lab from a pinned upstream ref, with the U4A ability installed in the layout it scans for. `make paios`, `make paios-check`, `make paios-down`, and the same three in Kubernetes.
- **Kwaai binding:** it grants the tiers the owner gave standing consent to, and refuses an ask-me trade — an ability has no channel to reach its person.

### v2026.08.7

#### New

- **Protocol:** `make flow-check` — the same negotiation run four times with the requesting side arranged four ways: a bare key, an identified agent whose session key rotates, one described by a metadata document, one published in a key directory. Her terms, her grant and her policy come out identical.
- **Authorization server:** an owner credential, so her authority accepts either a browser session or a signature from a key her own device holds.

## August 15 2026

### v2026.08.6

#### New

- **Docs:** the documentation site, around thirty pages across overview, guides and reference.

## August 14 2026

### v2026.08.5

#### New

- **Kubernetes:** a devcontainer, so the Kubernetes lab runs in a browser with nothing installed.

#### Bug fixes

- **Kubernetes:** `alice/uma-as` and `meridian/uma-pep` need the waypoint label and no manifest carried it — both had been applied by hand, so a clean clone returned 6 of 13 smoke checks. Without the label the mesh judges the policy at L4, where it cannot read a path, and denies everything with nothing in any log naming a reason.

## August 12 2026

### v2026.08.4

#### Enhancements

- **Docs:** the Kubernetes reference architecture on the site.

### v2026.08.3

#### New

- **Kubernetes:** the same source deployed on Kubernetes — six namespaces, one per party, each with its own workload identity, the authorization server replicated against a replicated database, and the cross-principal boundary enforced by a service mesh.
- **Kubernetes:** `make k8s-policy-test`, asserting the refusals rather than only the allows.

## August 11 2026

### v2026.08.2

#### Enhancements

- **Kubernetes:** the deployed shape brought up to the scale the claims need.

### v2026.08.1

#### New

- **Enforcement point:** `ENFORCEMENT_MODE=gateway|embedded`. The decision logic takes request facts and returns a verdict with no transport of its own, so the same core runs in a gateway or inside the resource server.
- **Protocol:** the challenge is specified as parameters rather than a header — `401 + WWW-Authenticate: UMA` where there is a status line, JSON-RPC `-32001` carrying the same parameters where there is not.

#### Enhancements

- **MCP:** aligned to the 2026-07-28 revision. The handshake moved to `server/discover`, sessions were removed, and client identity travels per request.

#### Feature deprecations

- **Registration:** push registration removed from the main line. It remains conformant and is preserved on the `legacy/rreg-baseline` branch.

## July 29 2026

### v2026.07.1

#### New

- **Discovery:** beat 0 split into two layers. A public RFC 9728 document names the tool surfaces, the owner's authorization servers and the signing keys; a protected owner-resources listing is served only to a querier that proves possession of the owner's authority key.
- **Registration:** declarative pull registration — the resource server publishes, the authority fetches, verifies the signed metadata and materialises its registry.
- **Discovery:** a second binding encoding at `/.well-known/aauth-resource.json`, with a content-addressed vocabulary. Both documents point at the same owner-resources endpoint.
- **Licensing:** Apache 2.0.
