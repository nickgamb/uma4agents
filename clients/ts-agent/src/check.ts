// The four beats, from a second implementation.
//
// Runs against the lab from where an agent stands: discovers, is challenged,
// corroborates the authority the challenge named, signs the owner's terms,
// waits for her, spends the grant, and is refused when it should be. Nothing
// here imports from the Python client; the two meet on the wire.

import { AgentKeys, GrantDenied, corroborate, mcpCall, parseWwwAuthenticate, runGrant, signRequest } from "./uma4a.js";

const GATEWAY = process.env.UMA4A_GATEWAY ?? "https://gateway.uma.lab/mcp";
const AUTHORITY = process.env.UMA4A_GATEWAY_AUTHORITY ?? "gateway.uma.lab";
const AS = process.env.UMA4A_AS ?? "https://alice-as.uma.lab";
const KEYCLOAK = process.env.KEYCLOAK ?? "https://keycloak.uma.lab";
const CA = process.env.UMA4A_CA_BUNDLE ?? "/driver/rootCA.pem";
const KEYS = process.env.UMA4A_KEYS ?? "/driver/keys";

const passed: string[] = [], failed: string[] = [];
const check = (name: string, ok: boolean, detail = "") => {
  (ok ? passed : failed).push(name);
  console.log((ok ? "   ok   " : "   FAIL ") + name + (detail && !ok ? ` — ${detail}` : ""));
};
const say = (m: string) => console.log(`   ${m}`);

// Every name here is signed by the lab CA, which reaches Node's fetch through
// NODE_EXTRA_CA_CERTS in the environment; nothing to configure per call.
if (!process.env.NODE_EXTRA_CA_CERTS) console.warn(`NODE_EXTRA_CA_CERTS is unset; expected ${CA}`);
const fetchLab: typeof fetch = fetch;

async function ownerHeaders(): Promise<Record<string, string>> {
  const r = await fetchLab(`${KEYCLOAK}/realms/alice/protocol/openid-connect/token`, {
    method: "POST", headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ grant_type: "password", client_id: "meridian-portal", username: "alice",
      password: process.env.ALICE_PASSWORD ?? "alice-demo" }).toString() });
  const { access_token } = (await r.json()) as { access_token: string };
  return { Authorization: `Bearer ${access_token}` };
}

/** Stand in for Alice's tap: approve the first pending item that appears. */
function approveInBackground(): void {
  (async () => {
    const hdrs = await ownerHeaders();
    for (let i = 0; i < 60; i++) {
      const items = (await (await fetchLab(`${AS}/owner/pending`, { headers: hdrs })).json()) as { family: string }[];
      for (const p of items)
        await fetchLab(`${AS}/owner/pending/${p.family}/decision`, { method: "POST",
          headers: { ...hdrs, "content-type": "application/json" }, body: JSON.stringify({ decision: "approved" }) });
      if (items.length) return;
      await new Promise((r) => setTimeout(r, 500));
    }
  })().catch(() => undefined);
}

async function main(): Promise<number> {
  const keys = AgentKeys.loadOrCreate(`${KEYS}/ts-agent.pem`);
  say(`this agent is ${keys.thumbprint()}`);

  console.log("\n== Beat 1: the challenge ==");
  const first = await mcpCall(fetchLab, GATEWAY, "tools/call", { name: "get_positions", arguments: {} });
  const ch = parseWwwAuthenticate(first.headers.get("www-authenticate"));
  check("an unauthorized call is refused with a UMA challenge", first.status === 401 && ch !== null, `${first.status}`);
  if (!ch) return 1;
  check("the challenge carries structured remediation naming the authority and the ticket",
    ch.remediation?.authorization_server === ch.asUri && ch.remediation?.ticket === ch.ticket);

  console.log("\n== Beat 0: corroborate the authority ==");
  try { await corroborate(fetchLab, GATEWAY, ch); check("the resource's metadata names the authorization server the challenge did", true); }
  catch (e) { check("the resource's metadata names the authorization server the challenge did", false, String(e)); return 1; }

  console.log("\n== Beats 2–4: terms, agreement, the owner, the grant ==");
  approveInBackground();
  let rpt: string, receipt: string | undefined;
  try { ({ rpt, receipt } = await runGrant(fetchLab, ch, keys, () => true, { reason: "A second implementation, meeting the first on the wire.", onStatus: say })); }
  catch (e) { check("a grant is issued", false, String(e)); return 1; }
  check("a grant is issued", Boolean(rpt));
  check("with a receipt countersigned by her authority", typeof receipt === "string" && receipt.split(".").length === 3);

  console.log("\n== The call, proof of possession ==");
  const ok = await mcpCall(fetchLab, GATEWAY, "tools/call", { name: "get_positions", arguments: {} },
    signRequest("POST", AUTHORITY, "/mcp", `PoP ${rpt}`, keys));
  check("the signed call is served", ok.status === 200 && ok.body?.result !== undefined, `${ok.status} ${JSON.stringify(ok.body)?.slice(0, 100)}`);

  const forged = signRequest("POST", AUTHORITY, "/mcp", `PoP ${rpt}`, AgentKeys.loadOrCreate(`${KEYS}/ts-forger.pem`, "forger"));
  const bad = await mcpCall(fetchLab, GATEWAY, "tools/call", { name: "get_positions", arguments: {} }, forged);
  check("the same grant under another key is refused", bad.status === 401, `${bad.status}`);

  const bearer = await mcpCall(fetchLab, GATEWAY, "tools/call", { name: "get_positions", arguments: {} }, { Authorization: `Bearer ${rpt}` });
  check("and as a bearer token it is refused", bearer.status === 401, `${bearer.status}`);

  console.log("\n== Declining ==");
  const again = parseWwwAuthenticate((await mcpCall(fetchLab, GATEWAY, "tools/call", { name: "get_transactions", arguments: {} })).headers.get("www-authenticate"));
  if (again) {
    try { await runGrant(fetchLab, again, AgentKeys.loadOrCreate(`${KEYS}/ts-decliner.pem`, "decliner"), () => false, { onStatus: say }); check("a decline ends the negotiation", false, "granted"); }
    catch (e) { check("a decline ends the negotiation", e instanceof GrantDenied, String(e)); }
  }

  console.log(`\n${passed.length} passed, ${failed.length} failed`);
  if (!failed.length) console.log("\nPASS: a second implementation, sharing no code with the first, ran the four beats.");
  return failed.length ? 1 : 0;
}

main().then((c) => process.exit(c), (e) => { console.error(e); process.exit(1); });
