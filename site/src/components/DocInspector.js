import React, { useState } from "react";

/**
 * The wire contract, one message at a time.
 *
 * This sits at the top of the wire contract page and **adds to** it rather
 * than replacing anything: every section below still carries its own prose and
 * its own JSON, in reading order, for someone working through the protocol
 * from the start. This is for the other reader — the one who knows the flow
 * and wants to see what beat 3 actually puts on the wire without scrolling
 * past three sections to find it.
 *
 * The messages here are the same ones the page documents. If they ever
 * disagree, the page is right and this is a bug.
 */

const BEATS = [
  {
    id: "challenge",
    tab: "1 · Challenge",
    from: "enforcement point",
    to: "agent",
    summary:
      "Refused, with the address of the authority that could grant it and a handle on the attempt. Over a transport with no status line, the same fields ride a JSON-RPC error.",
    label: "HTTP/1.1 401 Unauthorized",
    body: `WWW-Authenticate: UMA realm="alice-vault",
  error="insufficient_authorization",
  as_uri="https://alice-as.uma.lab",
  ticket="<ticket>",
  resource_metadata="https://gateway.uma.lab/.well-known/oauth-protected-resource/mcp",
  scope="trades:execute",
  authorization_remediation="<base64url JSON>"`,
    note: "The remediation object decodes to RFC 9396 authorization_details plus the two additions that make a third-party decision possible: authorization_server and ticket.",
  },
  {
    id: "attempt",
    tab: "2 · Attempt",
    from: "agent",
    to: "authority",
    summary:
      "The ticket is presented, and instead of a grant the authority proffers the owner's terms. The ticket rotates on every presentation.",
    label: "403 need_info",
    body: `{
  "error": "need_info",
  "ticket": "<rotated>",
  "required_claims": [{
    "claim_type": "https://u4a.ai/spec/terms/1.0#myterms-agreement",
    "claim_token_format": ["https://u4a.ai/spec/terms/1.0#myterms-agreement-v1+jws"],
    "terms_template": {
      "template_id": "alice/advisor-tier1/v2",
      "terms_uri": "https://alice-as.uma.lab/terms/alice/advisor-tier1/v2",
      "purpose": "Suitability review for advisory onboarding",
      "scope": ["positions:read"],
      "expires_in": 172800,
      "prohibited": ["retention-after-review", "marketing", "model-training"],
      "family": "<negotiation-family-id>",
      "nonce": "<nonce>"
    }
  }]
}`,
    note: "Standard UMA names acceptable claim formats. Proffering the claim's content is extension 1.",
  },
  {
    id: "commit",
    tab: "3 · Commit",
    from: "agent",
    to: "authority",
    summary:
      "The template echoed back and signed, with the key the agent will later use to prove possession. A weakened echo ends the negotiation.",
    label: "POST /token · claim_token",
    body: `{
  "iss": "aauth:agent:<keyid>",
  "aud": "https://alice-as.uma.lab",
  "template_id": "alice/advisor-tier1/v2",
  "terms_uri": "https://alice-as.uma.lab/terms/alice/advisor-tier1/v2",
  "purpose": "Suitability review for advisory onboarding",
  "scope": ["positions:read"],
  "expires_in": 172800,
  "prohibited": ["retention-after-review", "marketing", "model-training"],
  "family": "<negotiation-family-id>",
  "nonce": "<nonce>"
}`,
    note: "Verified on nonce, family, template id, terms URI and purpose — with prohibited not weakened and expires_in not extended.",
  },
  {
    id: "grant",
    tab: "4 · Grant",
    from: "authority",
    to: "agent",
    summary:
      "A proof-of-possession token naming the agent's key, the permissions it carries, and the hash of the terms behind it.",
    label: "200 · access_token",
    body: `{
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
}`,
    note: "An ask-me grant also carries single_use and an operation block whose params_s256 is the hash of exactly what the owner approved.",
  },
  {
    id: "call",
    tab: "The call",
    from: "agent",
    to: "enforcement point",
    summary:
      "The original call, retried with a signature over it. The enforcement point then runs five checks, and the order is normative.",
    label: "Enforcement order",
    body: `1. POST /introspect      live? connection standing?   (non-consuming)
2. permissions           does this grant cover this tool?
3. signature             verifies against the RPT's cnf key?
4. operation             params_s256 matches, for single-use
5. POST /consume         spend it — atomic, and last`,
    note: "Consuming at step 1 is the intuitive placement and it is a denial of service: an unsigned replay destroys an approval the owner gave.",
  },
];

const DocInspector = ({ caption }) => {
  const [active, setActive] = useState(BEATS[0].id);
  const beat = BEATS.find((b) => b.id === active);

  return (
    <figure className="doc-diagram doc-inspector">
      <div className="doc-inspector__tabs" role="tablist" aria-label="Messages on the wire">
        {BEATS.map((b) => (
          <button
            key={b.id}
            type="button"
            role="tab"
            aria-selected={b.id === active}
            className={`doc-inspector__tab${
              b.id === active ? " doc-inspector__tab--on" : ""
            }`}
            onClick={() => setActive(b.id)}
          >
            {b.tab}
          </button>
        ))}
      </div>

      <p className="doc-inspector__route">
        <span>{beat.from}</span>
        <span aria-hidden="true">→</span>
        <span>{beat.to}</span>
      </p>
      <p className="doc-inspector__summary">{beat.summary}</p>

      <div className="doc-inspector__message">
        <p className="doc-inspector__label">{beat.label}</p>
        <pre>
          <code>{beat.body}</code>
        </pre>
      </div>

      <p className="doc-inspector__note">{beat.note}</p>

      {caption && <figcaption>{caption}</figcaption>}
    </figure>
  );
};

export default DocInspector;
