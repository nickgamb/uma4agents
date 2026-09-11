// A requesting agent for the UMA 2.0 profile for autonomous agents.
//
// Written against the drafts, not against the Python client, so that two
// implementations meet on the wire and nowhere else. Node's own crypto does
// everything needed: Ed25519 keys, JWK export, and raw signatures over the
// bytes this file assembles. No dependencies.
import { createHash, createPrivateKey, generateKeyPairSync, sign } from "node:crypto";
import { readFileSync, writeFileSync, existsSync } from "node:fs";
export const GRANT_TYPE = "urn:ietf:params:oauth:grant-type:uma-ticket";
export const AGREEMENT_FORMAT = "urn:uma4agents:format:myterms-agreement-v1+jws";
export const MCP_PROTOCOL_VERSION = "2026-07-28";
export const b64url = (b) => Buffer.from(b).toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
export const s256 = (bytes) => "s256:" + b64url(createHash("sha256").update(bytes).digest());
/** The agent's key: the identity, for a pseudonymous agent. Ed25519, PKCS#8 PEM on disk. */
export class AgentKeys {
    key;
    keyid;
    constructor(key, keyid = "ts-agent-1") {
        this.key = key;
        this.keyid = keyid;
    }
    static loadOrCreate(path, keyid = "ts-agent-1") {
        if (existsSync(path))
            return new AgentKeys(createPrivateKey(readFileSync(path)), keyid);
        const { privateKey } = generateKeyPairSync("ed25519");
        writeFileSync(path, privateKey.export({ type: "pkcs8", format: "pem" }), { mode: 0o600 });
        return new AgentKeys(privateKey, keyid);
    }
    publicJwk() {
        const jwk = this.key.export({ format: "jwk" });
        return { kty: jwk.kty, crv: jwk.crv, x: jwk.x };
    }
    /** RFC 7638 thumbprint, under the profile's `jkt:` prefix. */
    thumbprint() {
        const { crv, kty, x } = this.publicJwk();
        return "jkt:" + b64url(createHash("sha256").update(JSON.stringify({ crv, kty, x })).digest());
    }
}
/** The HTTP encoding: `WWW-Authenticate: UMA realm=…, as_uri=…, ticket=…`. */
export function parseWwwAuthenticate(header) {
    if (!header || !/^\s*UMA\b/.test(header))
        return null;
    const get = (name) => header.match(new RegExp(`${name}="([^"]+)"`))?.[1];
    const asUri = get("as_uri"), ticket = get("ticket");
    if (!asUri || !ticket)
        return null;
    const blob = get("authorization_remediation");
    const remediation = blob
        ? JSON.parse(Buffer.from(blob.replace(/-/g, "+").replace(/_/g, "/"), "base64").toString())
        : undefined;
    return { asUri, ticket, resourceMetadata: get("resource_metadata"), remediation };
}
/** The JSON-RPC encoding: error code -32001 with the parameters in `data`. */
export function parseJsonRpcChallenge(error) {
    if (!error || error.code !== -32001 || !error.data)
        return null;
    const d = error.data;
    if (typeof d.as_uri !== "string" || typeof d.ticket !== "string")
        return null;
    return {
        asUri: d.as_uri, ticket: d.ticket,
        resourceMetadata: typeof d.resource_metadata === "string" ? d.resource_metadata : undefined,
        remediation: d.authorization_remediation ?? undefined,
    };
}
// ---- Beat 0: corroborate the authority the challenge named -------------------
/** RFC 9728 §3.3 plus Core §3.4: the document must be for this resource and must list as_uri. */
export async function corroborate(fetchFn, resourceUrl, ch) {
    if (!ch.resourceMetadata)
        throw new Error("challenge names no resource_metadata");
    const doc = (await (await fetchFn(ch.resourceMetadata)).json());
    if (doc.resource !== resourceUrl)
        throw new Error(`metadata is for ${doc.resource}, not ${resourceUrl}`);
    if (!(doc.authorization_servers ?? []).some((s) => s.replace(/\/$/, "") === ch.asUri.replace(/\/$/, "")))
        throw new Error(`the resource never published ${ch.asUri} as an authorization server`);
}
/** Echo the proffered template, signed with the agent's key. Nothing is weakened; nothing widens. */
export function signAgreement(template, keys, asUri, extra = {}) {
    const claims = {
        iss: `agent:${keys.keyid}`, aud: asUri, iat: Math.floor(Date.now() / 1000),
        template_id: template.template_id, terms_uri: template.terms_uri, purpose: template.purpose,
        scope: template.scope, expires_in: template.expires_in, prohibited: template.prohibited,
        nonce: template.nonce, family: template.family,
    };
    if (extra.operation)
        claims.operation = extra.operation;
    if (extra.reason)
        claims.reason = extra.reason;
    const header = { typ: "myterms-agreement-v1+jws", alg: "EdDSA", kid: keys.keyid, jwk: keys.publicJwk() };
    const signingInput = `${b64url(JSON.stringify(header))}.${b64url(JSON.stringify(claims))}`;
    const jws = `${signingInput}.${b64url(sign(null, Buffer.from(signingInput), keys.key))}`;
    return b64url(jws); // the claim_token is the base64url of the compact JWS
}
// ---- Beats 2–4: the negotiation ------------------------------------------------
export class GrantDenied extends Error {
}
export async function runGrant(fetchFn, ch, keys, approve, opts = {}) {
    const say = opts.onStatus ?? (() => { });
    const token = `${ch.asUri}/token`;
    const post = async (form) => {
        const r = await fetchFn(token, { method: "POST", headers: { "content-type": "application/x-www-form-urlencoded" },
            body: new URLSearchParams(form).toString() });
        return (await r.json());
    };
    say("presenting the ticket");
    let body = await post({ grant_type: GRANT_TYPE, ticket: ch.ticket });
    if (body.error === "need_info") {
        const template = body.required_claims[0].terms_template;
        say(`terms proffered: ${template.purpose} (expires ${template.expires_in}s)`);
        if (!approve(template)) {
            await post({ grant_type: GRANT_TYPE, ticket: body.ticket, decline: "true" });
            throw new GrantDenied("declined the terms");
        }
        const claim = signAgreement(template, keys, ch.asUri, { operation: opts.operation, reason: opts.reason });
        say("agreement signed, committing");
        body = await post({ grant_type: GRANT_TYPE, ticket: body.ticket, claim_token: claim, claim_token_format: AGREEMENT_FORMAT });
    }
    const deadline = Date.now() + (opts.maxWaitMs ?? 60_000);
    while (body.error === "request_submitted") {
        say("the owner has been asked — holding the ticket");
        if (Date.now() > deadline)
            throw new GrantDenied("timed out waiting for the owner");
        await new Promise((r) => setTimeout(r, (body.interval ?? 3) * 1000));
        body = await post({ grant_type: GRANT_TYPE, ticket: body.ticket });
    }
    if (body.access_token) {
        say("grant issued");
        return { rpt: body.access_token, receipt: body.receipt };
    }
    throw new GrantDenied(body.error_description ?? body.error ?? "unknown");
}
// ---- Beat 4: proof of possession on the call ----------------------------------
/** RFC 9421 over @method @authority @path authorization, label sig1, alg ed25519. */
export function signRequest(method, authority, path, authorization, keys) {
    const created = Math.floor(Date.now() / 1000);
    const covered = ['"@method"', '"@authority"', '"@path"', '"authorization"'];
    const params = `(${covered.join(" ")});created=${created};keyid="${keys.keyid}";alg="ed25519"`;
    const base = [`"@method": ${method}`, `"@authority": ${authority}`, `"@path": ${path}`,
        `"authorization": ${authorization}`, `"@signature-params": ${params}`].join("\n");
    const sig = sign(null, Buffer.from(base), keys.key);
    return { Authorization: authorization, "Signature-Input": `sig1=${params}`, Signature: `sig1=:${sig.toString("base64")}:` };
}
// ---- MCP over streamable HTTP ----------------------------------------------------
export async function mcpCall(fetchFn, url, method, params, headers = {}) {
    const h = {
        "content-type": "application/json", accept: "application/json, text/event-stream",
        "MCP-Protocol-Version": MCP_PROTOCOL_VERSION, "Mcp-Method": method, ...headers,
    };
    if (method === "tools/call")
        h["Mcp-Name"] = String(params.name ?? "");
    const meta = { "io.modelcontextprotocol/protocolVersion": MCP_PROTOCOL_VERSION,
        "io.modelcontextprotocol/clientCapabilities": {}, "io.modelcontextprotocol/clientInfo": { name: "uma4a-ts-agent", version: "0.1" } };
    const r = await fetchFn(url, { method: "POST", headers: h, body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params: { ...params, _meta: meta } }) });
    const text = await r.text();
    const line = text.split("\n").find((l) => l.startsWith("data:"));
    let body = null;
    try {
        body = JSON.parse(line ? line.slice(5).trim() : text);
    }
    catch {
        body = null;
    }
    return { status: r.status, headers: r.headers, body };
}
