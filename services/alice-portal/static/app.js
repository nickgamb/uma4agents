/* Meridian portal SPA. Vanilla JS, hash routing, dark. */
const $ = (s, r = document) => r.querySelector(s);
const el = (h) => { const t = document.createElement("template"); t.innerHTML = h.trim(); return t.content.firstChild; };
const fmt = (n) => "$" + Number(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmt0 = (n) => "$" + Number(n).toLocaleString("en-US", { maximumFractionDigits: 0 });
const pct = (n) => (n >= 0 ? "+" : "") + Number(n).toFixed(2) + "%";
const cls = (n) => (n >= 0 ? "pos" : "neg");
const arrow = (n) => (n >= 0 ? "▲" : "▼");
const ALLOC_COLORS = ["#5b8cff", "#2ed079", "#8f6bff", "#f2b955", "#ff5a6a", "#3fd8d0"];

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (r.status === 401) { location.href = "/login"; throw new Error("auth"); }
  const body = await r.json().catch(() => ({}));
  if (!r.ok) {
    // Her authorization server refuses a policy that could widen access on
    // evidence the agent controls, and says which condition and why. Throwing
    // with that text is the whole point: a rejected edit that reported success
    // would be a control she believes she has and does not.
    const err = new Error(body.detail || body.error || `request failed (${r.status})`);
    err.status = r.status;
    throw err;
  }
  return body;
}

function toast(title, detail, kind = "") {
  const t = el(`<div class="toast ${kind}"><div class="t">${title}</div><div class="d">${detail || ""}</div></div>`);
  $("#toasts").appendChild(t);
  setTimeout(() => { t.style.opacity = "0"; t.style.transition = "opacity .3s"; setTimeout(() => t.remove(), 300); }, 5200);
}

function toggleMenu(e) { e.stopPropagation(); $("#usermenu").classList.toggle("open"); }
document.addEventListener("click", () => $("#usermenu")?.classList.remove("open"));

/* ---- Router ------------------------------------------------------------- */
const routes = {};
function route(name, fn) { routes[name] = fn; }
function go(r) { location.hash = "#/" + r; }
document.querySelectorAll("[data-route]").forEach(a =>
  a.addEventListener("click", (e) => { e.preventDefault(); go(a.dataset.route); }));

async function render() {
  const hash = location.hash.replace(/^#\//, "") || "dashboard";
  const parts = hash.split("/");
  const base = parts[0];
  document.querySelectorAll("#mainnav a").forEach(a => {
    const r = a.dataset.route || "";
    a.classList.toggle("active", r === hash || (r === "settings" && base === "settings" && !hash.includes("agent-authorization")) || (r.includes("agent-authorization") && hash.includes("agent-authorization")));
  });
  const view = $("#view");
  view.innerHTML = `<div class="empty">Loading…</div>`;
  const handler = hash.startsWith("settings") ? routes["settings"] : routes[base];
  try { await (handler || routes.dashboard)(view, parts); }
  catch (e) { view.innerHTML = `<div class="empty">Could not load this view.</div>`; console.error(e); }
}
window.addEventListener("hashchange", render);

function setTitle(title, crumbs) {
  $("#pageTitle").textContent = title;
  $("#crumbs").innerHTML = crumbs || "";
}

/* ---- Dashboard ---------------------------------------------------------- */
route("dashboard", async (view) => {
  setTitle("Dashboard", "");
  const p = await api("/api/portfolio");
  const dayChange = p.total_value * 0.0042; // presentational intraday move
  const donut = allocationDonut(p.positions);
  view.innerHTML = `
    <div class="grid cols-4" style="margin-bottom:18px">
      <div class="card"><h3>Portfolio value</h3><div class="big num">${fmt(p.total_value)}</div>
        <div class="sub">as of ${p.as_of}</div></div>
      <div class="card"><h3>Today</h3><div class="big num ${cls(dayChange)}">${arrow(dayChange)} ${fmt(Math.abs(dayChange))}</div>
        <div class="sub"><span class="${cls(dayChange)}">${pct(0.42)}</span> intraday</div></div>
      <div class="card"><h3>Total gain / loss</h3><div class="big num ${cls(p.total_gain)}">${fmt(p.total_gain)}</div>
        <div class="sub"><span class="${cls(p.total_gain)}">${pct(p.total_gain_pct)}</span> all time</div></div>
      <div class="card"><h3>Cost basis</h3><div class="big num">${fmt(p.total_cost)}</div>
        <div class="sub">${p.positions.length} positions</div></div>
    </div>
    <div class="grid cols-2">
      <div class="card pad-lg">
        <div class="section-head"><h2>Performance</h2><span class="chip pos">${pct(p.total_gain_pct)} all time</span></div>
        ${perfChart(p)}
      </div>
      <div class="card pad-lg">
        <div class="section-head"><h2>Allocation</h2></div>
        <div class="alloc">${donut.svg}<div class="legend">${donut.legend}</div></div>
      </div>
    </div>
    <div class="card pad-lg" style="margin-top:18px">
      <div class="section-head"><h2>Top holdings</h2><a href="#/holdings">View all →</a></div>
      ${holdingsTable(p.positions.slice(0, 4), false)}
    </div>`;
});

function allocationDonut(positions) {
  const R = 62, C = 2 * Math.PI * R, cx = 80, cy = 80;
  let off = 0;
  const segs = positions.map((p, i) => {
    const frac = p.weight / 100, len = frac * C, color = ALLOC_COLORS[i % ALLOC_COLORS.length];
    const s = `<circle cx="${cx}" cy="${cy}" r="${R}" fill="none" stroke="${color}" stroke-width="18"
      stroke-dasharray="${len} ${C - len}" stroke-dashoffset="${-off}" transform="rotate(-90 ${cx} ${cy})"/>`;
    off += len; return s;
  }).join("");
  const legend = positions.map((p, i) =>
    `<div class="row"><span class="sw" style="background:${ALLOC_COLORS[i % ALLOC_COLORS.length]}"></span>
     <span>${p.symbol}</span><span class="pct num">${p.weight.toFixed(1)}%</span></div>`).join("");
  const svg = `<svg width="160" height="160" viewBox="0 0 160 160" class="spark">${segs}
    <text x="80" y="76" text-anchor="middle" fill="var(--text-dim)" font-size="11">Positions</text>
    <text x="80" y="94" text-anchor="middle" fill="var(--text)" font-size="20" font-weight="700">${positions.length}</text></svg>`;
  return { svg, legend };
}

function perfChart(p) {
  // A smooth upward line built to end at the current all-time gain %.
  const w = 480, h = 150, n = 24, gain = Math.max(-8, Math.min(30, p.total_gain_pct));
  const pts = Array.from({ length: n }, (_, i) => {
    const t = i / (n - 1);
    const wobble = Math.sin(i * 0.9) * 1.6 + Math.sin(i * 0.3) * 1.1;
    const v = gain * Math.pow(t, 1.15) + wobble;
    return v;
  });
  const min = Math.min(...pts, 0), max = Math.max(...pts, 1);
  const x = (i) => (i / (n - 1)) * w, y = (v) => h - ((v - min) / (max - min)) * (h - 10) - 5;
  const line = pts.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const area = `${line} L${w},${h} L0,${h} Z`;
  return `<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" preserveAspectRatio="none">
    <defs><linearGradient id="pg" x1="0" x2="0" y1="0" y2="1">
      <stop offset="0" stop-color="rgba(46,208,121,0.28)"/><stop offset="1" stop-color="rgba(46,208,121,0)"/></linearGradient></defs>
    <path d="${area}" fill="url(#pg)"/><path d="${line}" fill="none" stroke="var(--pos)" stroke-width="2.2"/></svg>`;
}

function holdingsTable(positions, detailed) {
  const rows = positions.map(p => `
    <tr>
      <td><div class="tick"><div class="badge2">${p.symbol.slice(0, 4)}</div>
        <div><div class="nm">${p.symbol}</div><div class="full">${p.name}</div></div></div></td>
      ${detailed ? `<td class="r num">${p.quantity.toLocaleString()}</td><td class="r num">${fmt(p.price)}</td>` : ""}
      <td class="r num">${fmt(p.market_value)}</td>
      ${detailed ? `<td class="r num">${fmt(p.cost_basis)}</td>` : ""}
      <td class="r num ${cls(p.gain)}">${fmt(p.gain)}</td>
      <td class="r"><span class="chip ${p.gain >= 0 ? "pos" : "neg"}">${pct(p.gain_pct)}</span></td>
      ${detailed ? `<td class="r num">${p.weight.toFixed(1)}%</td>` : ""}
    </tr>`).join("");
  return `<table><thead><tr><th>Instrument</th>
    ${detailed ? "<th class='r'>Qty</th><th class='r'>Price</th>" : ""}
    <th class="r">Market value</th>${detailed ? "<th class='r'>Cost basis</th>" : ""}
    <th class="r">Gain / loss</th><th class="r">Return</th>${detailed ? "<th class='r'>Weight</th>" : ""}</tr></thead>
    <tbody>${rows}</tbody></table>`;
}

/* ---- Holdings ----------------------------------------------------------- */
route("holdings", async (view) => {
  setTitle("Holdings", "");
  const p = await api("/api/portfolio");
  view.innerHTML = `
    <div class="grid cols-3" style="margin-bottom:18px">
      <div class="card"><h3>Market value</h3><div class="big num">${fmt(p.total_value)}</div></div>
      <div class="card"><h3>Unrealized gain</h3><div class="big num ${cls(p.total_gain)}">${fmt(p.total_gain)}</div>
        <div class="sub"><span class="${cls(p.total_gain)}">${pct(p.total_gain_pct)}</span></div></div>
      <div class="card"><h3>Positions</h3><div class="big num">${p.positions.length}</div></div>
    </div>
    <div class="card pad-lg"><div class="section-head"><h2>All positions</h2>
      <span class="muted">as of ${p.as_of}</span></div>
      ${holdingsTable(p.positions, true)}</div>`;
});

/* ---- Trade -------------------------------------------------------------- */
let tradeState = { side: "buy", symbol: "VTI", qty: 10 };
route("trade", async (view) => {
  setTitle("Trade", "");
  const p = await api("/api/portfolio");
  const syms = p.positions.filter(x => x.symbol !== "CASH");
  const price = (s) => (syms.find(x => x.symbol === s) || {}).price || 0;
  const draw = () => {
    const est = price(tradeState.symbol) * tradeState.qty;
    $("#estCost").textContent = fmt(est);
    $("#estPrice").textContent = fmt(price(tradeState.symbol));
    document.querySelectorAll(".seg button").forEach(b => b.classList.toggle("active", b.dataset.side === tradeState.side));
    $("#reviewBtn").className = "btn " + (tradeState.side === "buy" ? "pos" : "danger") + "";
    $("#reviewBtn").textContent = `Review ${tradeState.side} order`;
  };
  view.innerHTML = `
    <div class="grid cols-2">
      <div class="card pad-lg">
        <div class="section-head"><h2>Order ticket</h2></div>
        <div class="seg" style="margin-bottom:4px">
          <button data-side="buy" class="buy">Buy</button><button data-side="sell" class="sell">Sell</button></div>
        <label class="fld"><div class="lbl">Instrument</div>
          <select id="symSel">${syms.map(s => `<option value="${s.symbol}">${s.symbol} · ${s.name}</option>`).join("")}</select></label>
        <label class="fld"><div class="lbl">Quantity (shares)</div>
          <input type="number" id="qtyInput" value="${tradeState.qty}" min="1"></label>
        <label class="fld"><div class="lbl">Order type</div>
          <select><option>Market</option><option>Limit</option></select></label>
        <div style="display:flex;justify-content:space-between;margin-top:20px;color:var(--text-dim)">
          <span>Est. price</span><span class="num" id="estPrice"></span></div>
        <div style="display:flex;justify-content:space-between;margin-top:8px;font-weight:650;font-size:16px">
          <span>Estimated ${tradeState.side === "buy" ? "cost" : "proceeds"}</span><span class="num" id="estCost"></span></div>
        <button class="btn pos" id="reviewBtn" style="width:100%;margin-top:22px;justify-content:center">Review order</button>
        <div id="tradeResult" style="margin-top:16px"></div>
      </div>
      <div class="card pad-lg">
        <div class="section-head"><h2>Buying power</h2></div>
        <div class="big num">${fmt((p.positions.find(x => x.symbol === "CASH") || {}).market_value || 0)}</div>
        <div class="sub">Settled cash available to trade</div>
        <div style="margin-top:24px;padding-top:20px;border-top:1px solid var(--border-soft)">
          <h3 style="color:var(--text-dim);font-size:13px;margin:0 0 12px">This is the surface agents negotiate for</h3>
          <p style="color:var(--text-faint);font-size:13px;line-height:1.6;margin:0">
            When Alice trades here, it's her own account — instant. When
            <b style="color:var(--text-dim)">an advisor's agent</b> proposes the same
            order, it must carry Alice's signed terms and — for execution — her
            explicit per-trade approval. Same operation, governed differently by
            <a href="#/settings/security/agent-authorization">Agent&nbsp;Authorization</a>.</p>
        </div>
      </div>
    </div>`;
  $("#symSel").value = tradeState.symbol;
  $("#symSel").onchange = (e) => { tradeState.symbol = e.target.value; draw(); };
  $("#qtyInput").oninput = (e) => { tradeState.qty = Math.max(1, parseInt(e.target.value) || 1); draw(); };
  document.querySelectorAll(".seg button").forEach(b => b.onclick = () => { tradeState.side = b.dataset.side; draw(); });
  $("#reviewBtn").onclick = async () => {
    const r = $("#tradeResult");
    r.innerHTML = `<div class="card" style="background:var(--surface-2)">
      <div class="kv"><span class="k">Action</span><b>${tradeState.side.toUpperCase()} ${tradeState.qty} ${tradeState.symbol}</b></div>
      <div class="kv"><span class="k">Est. value</span><span class="num">${fmt(price(tradeState.symbol) * tradeState.qty)}</span></div>
      <button class="btn primary sm" id="confirmTrade" style="margin-top:10px">Confirm order</button></div>`;
    $("#confirmTrade").onclick = async () => {
      const res = await api("/api/trade", { method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ symbol: tradeState.symbol, side: tradeState.side, quantity: tradeState.qty }) });
      r.innerHTML = `<div class="card" style="border-color:var(--pos)"><b class="pos">✓ Order ${res.status}</b>
        <div class="sub">${tradeState.side.toUpperCase()} ${tradeState.qty} ${tradeState.symbol} · ${res.note}</div></div>`;
      toast("Order executed", `${tradeState.side.toUpperCase()} ${tradeState.qty} ${tradeState.symbol}`);
    };
  };
  draw();
});

/* ---- Settings ----------------------------------------------------------- */
route("settings", async (view, parts) => {
  const sub = parts.slice(1).join("/");
  setTitle("Settings", sub.includes("agent-authorization")
    ? `<b>Security</b> › Agent Authorization` : sub ? `<b>${sub}</b>` : "");
  view.innerHTML = `<div class="settings">
    <div class="settings-nav">
      <div class="group">Account</div>
      <a data-r="profile">Profile</a>
      <a data-r="notifications">Notifications</a>
      <div class="group">Security</div>
      <a data-r="security">Overview</a>
      <a data-r="security/agent-authorization">Agent Authorization</a>
    </div>
    <div id="settingsBody"></div></div>`;
  view.querySelectorAll(".settings-nav a").forEach(a => {
    a.classList.toggle("active", ("settings/" + a.dataset.r) === ("settings/" + sub) || (a.dataset.r === "security/agent-authorization" && sub.includes("agent-authorization")));
    a.onclick = (e) => { e.preventDefault(); go("settings/" + a.dataset.r); };
  });
  const body = $("#settingsBody");
  if (sub.includes("agent-authorization")) return agentAuthView(body);
  if (sub === "security") return settingsPlaceholder(body, "Security", "Password, two-factor, active sessions, and device management.");
  if (sub === "notifications") return settingsPlaceholder(body, "Notifications", "Statement, trade confirmation, and alert preferences.");
  return settingsPlaceholder(body, "Profile", "Name, contact details, tax information, and beneficiaries.");
});

function settingsPlaceholder(body, title, desc) {
  body.innerHTML = `<div class="card pad-lg"><div class="section-head"><h2>${title}</h2></div>
    <p style="color:var(--text-faint)">${desc}</p>
    <p style="color:var(--text-faint);font-size:13px">This surface is scaffolding for the demo — the
    live control panel is under <a href="#/settings/security/agent-authorization">Security › Agent Authorization</a>.</p></div>`;
}

/* ---- Agent Authorization ------------------------------------------------ */
let agentTab = "approvals";
async function agentAuthView(body) {
  body.innerHTML = `
    <div class="card pad-lg" style="margin-bottom:18px">
      <div class="section-head"><h2>Agent Authorization</h2></div>
      <p style="color:var(--text-dim);margin:0;max-width:60ch">Govern what other people's AI agents may do
      with your accounts. Your authorization server dictates the terms each request must accept, records
      every promise and action, and asks you before anything sensitive happens.</p>
    </div>
    <div class="subtabs">
      <button data-t="approvals">Approvals <span id="apCount"></span></button>
      <button data-t="connections">Connected agents</button>
      <button data-t="resources">Protected resources</button>
      <button data-t="terms">My Terms</button>
      <button data-t="ledger">Activity ledger</button>
    </div>
    <div id="aaBody"></div>`;
  body.querySelectorAll(".subtabs button").forEach(b => {
    b.classList.toggle("active", b.dataset.t === agentTab);
    b.onclick = () => { agentTab = b.dataset.t; agentAuthView(body); };
  });
  const target = $("#aaBody");
  if (agentTab === "approvals") return renderApprovals(target);
  if (agentTab === "connections") return renderConnections(target);
  if (agentTab === "resources") return renderResources(target);
  if (agentTab === "terms") return renderTerms(target);
  if (agentTab === "ledger") return renderLedger(target);
}

async function renderApprovals(target) {
  // The dialog names the rule that routed this to her, in her own words, so
  // the vocabulary has to be loaded even when she never opened the policy tab.
  if (!VOCAB) VOCAB = await api("/api/agent/policy-vocabulary").catch(() => []);
  const items = await api("/api/agent/pending");
  updateBadge(items.length);
  if (!items.length) { target.innerHTML = `<div class="empty">Nothing is waiting on you. Requests that your policy
    routes to you — new agents, or trades — will appear here in real time.</div>`; return; }
  target.innerHTML = items.map(p => {
    const isConn = p.kind === "connection";
    return `<div class="card pending-card ${isConn ? "connection" : ""}" style="margin-bottom:14px">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
        <span class="chip ${isConn ? "" : "warn"}">${isConn ? "New agent" : "Trade approval"}</span>
        <b>${p.tier_name || p.tier}</b></div>
      <div class="kv"><span class="k">Purpose</span><span>${p.purpose}</span></div>
      ${p.operation ? `<div class="kv"><span class="k">Operation</span>
        <span class="mono">${p.operation.tool}(${JSON.stringify(p.operation.params)})</span></div>` : ""}
      <div class="kv"><span class="k">Identity</span><span>${p.identity?.level || "unknown"}${p.identity?.sub ? " · " + p.identity.sub : ""}</span></div>
      ${p.handle ? `<div class="kv"><span class="k">Agent</span><span class="thumb">${p.handle}</span></div>` : ""}
      ${(p.assurance_notes || []).length ? `<div class="kv"><span class="k">Checked</span><span>
        ${p.assurance_notes.map(n => `<div class="note">${n}</div>`).join("")}</span></div>` : ""}
      ${(p.because || []).length ? `<div class="kv"><span class="k">Why you</span><span>
        ${p.because.map(b => `<span class="chip warn">${condLabel(b)}</span>`).join(" ")}</span></div>` : ""}
      <div class="kv"><span class="k">Prohibited</span><span>${(p.prohibited || []).map(x => `<span class="chip prohibit">${x}</span>`).join(" ")}</span></div>
      <div style="display:flex;gap:10px;margin-top:14px">
        <button class="btn pos sm" onclick="decide('${p.family}','approved')">${isConn ? "Connect this agent" : "Approve this operation"}</button>
        <button class="btn danger sm" onclick="decide('${p.family}','denied')">Deny</button></div>
    </div>`;
  }).join("");
}
window.decide = async (family, decision) => {
  await api(`/api/agent/pending/${family}/decision`, { method: "POST",
    headers: { "content-type": "application/json" }, body: JSON.stringify({ decision }) });
  toast(decision === "approved" ? "Approved" : "Denied", `Request ${family}`);
  renderApprovals($("#aaBody"));
};

async function renderConnections(target) {
  const conns = await api("/api/agent/connections");
  if (!conns.length) { target.innerHTML = `<div class="empty">No agents are connected yet. The first time an
    agent presents your terms, you'll be asked whether to establish a relationship — approved agents appear here.</div>`; return; }
  target.innerHTML = `<div class="card pad-lg"><table>
    <thead><tr><th>Agent</th><th>Identity</th><th>Handle</th><th>Connected</th><th>Last active</th><th class="r">Status</th><th></th></tr></thead>
    <tbody>${conns.map(c => `<tr>
      <td><div class="tick"><div class="badge2">🤖</div><div class="nm">${c.label}</div></div></td>
      <td>${c.identity?.level || "—"}</td>
      <td class="thumb">${c.handle.length > 24 ? c.handle.slice(0, 22) + "…" : c.handle}</td>
      <td>${(c.first_seen || "").replace("T", " ").replace("Z", "")}</td>
      <td>${c.last_access ? c.last_access.replace("T", " ").replace("Z", "") : "—"}</td>
      <td class="r"><span class="chip ${c.status === "active" ? "pos" : "neg"}">${c.status}</span></td>
      <td class="r">${c.status === "active" ? `<button class="btn danger sm" onclick="revoke('${c.handle}')">Revoke</button>` : ""}</td>
    </tr>`).join("")}</tbody></table></div>`;
}
window.revoke = async (handle) => {
  const res = await api(`/api/agent/connections/${encodeURIComponent(handle)}/revoke`, { method: "POST" });
  toast("Agent revoked", `${res.rpts_deactivated} active grant(s) deactivated`, "warn");
  renderConnections($("#aaBody"));
};

async function renderResources(target) {
  const [resources, servers] = await Promise.all([
    api("/api/agent/resources"), api("/api/agent/resource-servers")]);
  const serverCard = `<div class="card pad-lg" style="margin-bottom:14px">
    <div class="section-head"><h2>Resource servers</h2></div>
    <div class="muted" style="font-size:12.5px;margin-bottom:10px">Services you have authorized to use
      your authorization server's protection API (they hold a PAT issued in your name). Revoking one cuts
      off its registrations, tickets, and token checks immediately.</div>
    <table><thead><tr><th>Service</th><th>Consent</th><th>Last PAT issued</th><th class="r">Status</th><th></th></tr></thead>
    <tbody>${servers.map(s => `<tr>
      <td><div class="tick"><div class="badge2">🛡️</div>
        <div><div class="nm">${s.name}</div><div class="cell-sub mono">${s.client_id}</div></div></div></td>
      <td class="prose">${s.consented}</td>
      <td class="nowrap">${s.last_pat_issued
        ? `${s.last_pat_issued.slice(0, 10)}<div class="cell-sub mono">${s.last_pat_issued.slice(11, 19)} UTC</div>`
        : "—"}</td>
      <td class="r"><span class="chip ${s.status === "active" ? "pos" : "neg"}">${s.status}</span></td>
      <td class="r">${s.status === "active" ? `<button class="btn danger sm" onclick="revokeRs('${s.client_id}')">Revoke</button>` : ""}</td>
    </tr>`).join("")}</tbody></table></div>`;
  if (!resources.length) { target.innerHTML = serverCard + `<div class="empty">No resources are registered with your
    authorization server yet. When your brokerage's gateway registers the surfaces it protects, they
    appear here — this is what your policy tiers attach to.</div>`; return; }
  target.innerHTML = serverCard + `<div class="card pad-lg">
    <div class="section-head"><h2>Protected resources</h2></div>
    <div class="muted" style="font-size:12.5px;margin-bottom:12px">Everything your authorization server
      is protecting, as registered by your brokerage's gateway. Each resource is governed by one of your
      policy tiers — edit the terms under <b>My Terms</b>.</div>
    <table>
    <thead><tr><th>Resource</th><th>Source</th><th>Scopes</th><th>Governing tier</th><th class="r">On request</th></tr></thead>
    <tbody>${resources.map(r => `<tr>
      <td><div class="tick"><div class="badge2">🗄️</div>
        <div><div class="nm">${r.name}</div><div class="cell-sub mono">${r._id}</div></div></div></td>
      <td>${r.registered_via === "pull" ? `<span class="chip">published · pulled</span>` : `<span class="chip">pushed</span>`}</td>
      <td>${(r.resource_scopes || []).map(s => `<span class="chip">${s}</span>`).join(" ")}</td>
      <td class="nowrap">${r.tier_name
        ? `${r.tier_name}<div class="cell-sub mono">${r.tier}</div>`
        : `<span class="chip neg">no tier — unreachable</span>`}</td>
      <td class="r">${r.tier ? (r.ask_me ? `<span class="chip warn">ask me</span>` : `<span class="chip pos">auto under terms</span>`) : "—"}</td>
    </tr>`).join("")}</tbody></table></div>`;
}

window.revokeRs = async (clientId) => {
  const res = await api(`/api/agent/resource-servers/${clientId}/revoke`, { method: "POST" });
  toast("Resource server revoked", `${res.client_id} can no longer use your protection API`, "warn");
  renderResources($("#aaBody"));
};

let policyMode = "ui";
let VOCAB = null;          // conditions her authority will accept, and which may relax
const draft = {};          // conditions being composed, per tier

const OUTCOMES = { ask: "ask me first", refuse: "refuse outright",
                   auto: "grant without asking" };

function condLabel(condition) {
  const vocab = VOCAB || [];
  // Level-taking conditions are enumerated per level, so the exact string is
  // its own sentence. Only durations carry a value worth appending.
  const exact = vocab.find(c => c.condition === condition);
  if (exact) return exact.label;
  const [name, value] = condition.split(":");
  const v = vocab.find(c => c.condition === name);
  return v ? `${v.label} ${value || ""}`.trim() : condition;
}

function ruleSentence(rule) {
  const when = Array.isArray(rule.when) ? rule.when : [rule.when];
  return `If ${when.map(condLabel).join(", and ")} — <b>${OUTCOMES[rule.then] || rule.then}</b>`;
}

async function renderTerms(target) {
  if (!VOCAB) VOCAB = await api("/api/agent/policy-vocabulary");
  const tiers = await api("/api/agent/policies");
  if (policyMode === "code") return renderTermsCode(target, tiers);
  // Resources her authority protects that no tier governs yet. A new tier can
  // only be written over these: two tiers over one resource would make which
  // terms apply depend on storage order.
  const resources = await api("/api/agent/resources").catch(() => []);
  const free = resources.filter(r => !r.tier);
  const termsUri = (t) => `https://alice-as.uma.lab/terms/${t.terms.template_id}`;
  target.innerHTML = Object.entries(tiers).map(([id, t]) => `
    <div class="card pad-lg" style="margin-bottom:14px">
      <div class="section-head"><h2>${t.name}</h2>
        <span class="muted mono">${t.resources.join(", ") || "no resources yet"}</span>
        <button class="btn ghost sm" style="margin-left:auto"
                onclick="deleteTier('${id}')">Delete tier</button></div>
      <div class="muted" style="font-size:12.5px">Published terms:
        <a class="mono" href="${termsUri(t)}" target="_blank">${t.terms.template_id}</a>
        — the persistent document agents agree to</div>
      <label class="fld"><div class="lbl">Purpose your terms require the agent to accept</div>
        <input type="text" id="${id}-purpose" value="${t.terms.purpose}"></label>
      <label class="fld"><div class="lbl">Access expires after (seconds)</div>
        <input type="number" id="${id}-expires" value="${t.terms.expires_in}"></label>
      <label class="fld"><div class="lbl">Prohibited actions (comma-separated)</div>
        <input type="text" id="${id}-prohibited" value="${t.terms.prohibited.join(", ")}"></label>
      <div style="display:flex;align-items:center;gap:12px;margin-top:18px">
        <div class="toggle"><input type="checkbox" id="${id}-askme" ${t.ask_me ? "checked" : ""}><span class="track"></span></div>
        <div><div style="font-weight:560">Ask me every time</div>
          <div style="color:var(--text-faint);font-size:12.5px">Hold the request and notify me before granting</div></div>
        <button class="btn primary sm" style="margin-left:auto" onclick="savePolicy('${id}')">Save changes</button>
      </div>
      ${ruleEditor(id, t)}
    </div>`).join("") + `
    ${newTierForm(free)}
    <div style="display:flex;justify-content:flex-end;margin-top:6px">
      <button class="btn ghost sm" onclick="policyMode='code';renderTerms(document.getElementById('aaBody'))">
        ⌗ Advanced — edit policy as code</button></div>`;
}
function newTierForm(free) {
  return `
    <div class="card pad-lg" style="margin-bottom:14px;border-style:dashed">
      <div class="section-head"><h2>Add terms of your own</h2></div>
      <div class="muted" style="font-size:12.5px;margin-bottom:14px">
        A tier is a set of your terms and the resources they govern. You can only
        write terms over resources your authorization server already protects —
        a resource server registers what it holds, and you attach policy to it.
        ${free.length ? "" : "<b>Everything you protect is already governed by a tier</b>, so a new one would have nothing to cover. It can still be written now and attached later."}
      </div>
      <label class="fld"><div class="lbl">Name it</div>
        <input type="text" id="nt-name" placeholder="e.g. Statements and tax documents"></label>
      <label class="fld"><div class="lbl">Short id — this becomes part of the terms document agents cite</div>
        <input type="text" id="nt-id" placeholder="e.g. statements"></label>
      <label class="fld"><div class="lbl">Purpose your terms require the agent to accept</div>
        <input type="text" id="nt-purpose" placeholder="e.g. Preparing my annual return"></label>
      <label class="fld"><div class="lbl">Access expires after (seconds)</div>
        <input type="number" id="nt-expires" value="86400"></label>
      <label class="fld"><div class="lbl">Prohibited actions (comma-separated)</div>
        <input type="text" id="nt-prohibited" placeholder="e.g. retention-after-filing, model-training"></label>
      <div class="lbl" style="margin-top:14px">Which of your resources does it govern?</div>
      ${free.length ? free.map(r => `
        <label class="rule-row"><input type="checkbox" class="nt-res" value="${r._id}">
          <span>${r.name} <span class="muted mono">${r._id}</span></span></label>`).join("")
        : `<div class="muted" style="font-size:12.5px">Nothing is ungoverned right now.</div>`}
      <div style="display:flex;align-items:center;gap:12px;margin-top:16px">
        <div class="toggle"><input type="checkbox" id="nt-askme"><span class="track"></span></div>
        <div><div style="font-weight:560">Ask me every time</div>
          <div style="color:var(--text-faint);font-size:12.5px">Hold the request and notify me before granting</div></div>
        <button class="btn primary sm" style="margin-left:auto" onclick="createTier()">Create these terms</button>
      </div>
    </div>`;
}

window.createTier = async () => {
  const body = {
    id: $("#nt-id").value.trim(),
    name: $("#nt-name").value.trim(),
    ask_me: $("#nt-askme").checked,
    resources: [...document.querySelectorAll(".nt-res:checked")].map(c => c.value),
    terms: {
      purpose: $("#nt-purpose").value.trim(),
      expires_in: parseInt($("#nt-expires").value, 10),
      prohibited: $("#nt-prohibited").value.split(",").map(s => s.trim()).filter(Boolean),
    },
  };
  try {
    const created = await api("/api/agent/policies", { method: "POST",
      headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
    toast("Terms created", `${created.name} → ${created.terms.template_id}`);
  } catch (e) { toast("Not created", e.message, "warn"); }
  renderTerms($("#aaBody"));
};

window.deleteTier = async (id) => {
  try {
    const res = await api(`/api/agent/policies/${id}`, { method: "DELETE" });
    toast("Tier deleted", res.ungoverned?.length
      ? `${res.ungoverned.join(", ")} — now ungoverned, so requests for them are refused`
      : "It governed no resources");
  } catch (e) { toast("Not deleted", e.message, "warn"); }
  renderTerms($("#aaBody"));
};

function ruleEditor(id, t) {
  const rules = t.rules || [];
  const d = draft[id] || (draft[id] = { when: [], then: "ask" });
  const opts = (VOCAB || []).map(c =>
    `<option value="${c.condition}" data-takes="${c.takes || ""}" data-relax="${c.may_relax}">
       ${c.label}${c.takes === "duration" ? " …" : ""}</option>`).join("");
  return `
    <div class="rules">
      <div class="lbl" style="margin-top:20px">When may an agent be treated differently?</div>
      <div class="muted" style="font-size:12.5px;margin-bottom:10px">These name no agent, so they hold for
        every agent — including ones you have never seen. Only what <b>you</b> have decided may make a
        request easier; anything an agent shows about itself can only make one stricter.</div>
      ${rules.length ? rules.map((r, i) => `
        <div class="rule-row">
          <span>${ruleSentence(r)}</span>
          <button class="btn ghost sm" onclick="dropRule('${id}',${i})">Remove</button>
        </div>`).join("") : `<div class="muted" style="font-size:12.5px">No rules — this tier's answer
          applies to every agent equally.</div>`}
      ${d.when.length ? `<div class="rule-row draft"><span>If ${d.when.map(condLabel).join(", and ")} …</span>
        <button class="btn ghost sm" onclick="clearDraft('${id}')">Clear</button></div>` : ""}
      <div class="rule-add">
        <select id="${id}-cond" onchange="condChanged('${id}')">${opts}</select>
        <input type="text" id="${id}-val" placeholder="e.g. 90d" style="max-width:110px;display:none">
        <button class="btn ghost sm" onclick="addCond('${id}')">+ and</button>
        <select id="${id}-then">
          ${Object.entries(OUTCOMES).map(([k, v]) =>
            `<option value="${k}" ${k === d.then ? "selected" : ""}>${v}</option>`).join("")}
        </select>
        <button class="btn primary sm" onclick="addRule('${id}')">Add rule</button>
      </div>
    </div>`;
}

window.condChanged = (id) => {
  // Only a duration is open-ended. Everything else is a complete sentence
  // already, so a value box beside it is a question with no answer.
  const sel = $(`#${id}-cond`);
  $(`#${id}-val`).style.display =
    sel.selectedOptions[0].dataset.takes === "duration" ? "" : "none";
};

function currentCondition(id) {
  const sel = $(`#${id}-cond`);
  const takes = sel.selectedOptions[0].dataset.takes;
  const value = $(`#${id}-val`).value.trim();
  if (takes && !value) { toast("That condition needs a value", `Give it a ${takes}`, "warn"); return null; }
  return takes ? `${sel.value}:${value}` : sel.value;
}

window.addCond = (id) => {
  const c = currentCondition(id);
  if (!c) return;
  draft[id].when.push(c);
  renderTerms($("#aaBody"));
};
window.clearDraft = (id) => { draft[id] = { when: [], then: "ask" }; renderTerms($("#aaBody")); };

window.addRule = async (id) => {
  const d = draft[id] || { when: [] };
  const when = [...d.when];
  const c = currentCondition(id);
  if (c) when.push(c);
  if (!when.length) { toast("Nothing to add", "Choose a condition first", "warn"); return; }
  const then = $(`#${id}-then`).value;
  await putRules(id, [...(await currentRules(id)), { when, then }]);
};
window.dropRule = async (id, i) => {
  const rules = await currentRules(id);
  rules.splice(i, 1);
  await putRules(id, rules);
};

async function currentRules(id) {
  const tiers = await api("/api/agent/policies");
  return (tiers[id] && tiers[id].rules) || [];
}

async function putRules(id, rules) {
  try {
    const updated = await api(`/api/agent/policies/${id}`, { method: "PUT",
      headers: { "content-type": "application/json" }, body: JSON.stringify({ rules }) });
    draft[id] = { when: [], then: "ask" };
    toast("Rules updated", `${updated.name} — ${(updated.rules || []).length} rule(s)`);
  } catch (e) {
    // The refusal is the teaching moment: her authority says which condition
    // cannot do what she asked of it, and why.
    toast("That rule was not accepted", e.message, "warn");
  }
  renderTerms($("#aaBody"));
}

window.renderTerms = renderTerms;
window.savePolicy = async (id) => {
  const patch = { ask_me: $(`#${id}-askme`).checked, terms: {
    purpose: $(`#${id}-purpose`).value,
    expires_in: parseInt($(`#${id}-expires`).value),
    prohibited: $(`#${id}-prohibited`).value.split(",").map(s => s.trim()).filter(Boolean) } };
  const updated = await api(`/api/agent/policies/${id}`, { method: "PUT",
    headers: { "content-type": "application/json" }, body: JSON.stringify(patch) });
  toast("Terms updated", `${updated.name} → ${updated.terms.template_id}`);
  renderTerms($("#aaBody"));
};

function renderTermsCode(target, tiers) {
  target.innerHTML = `
    <div class="editor-wrap">
      <div class="editor-bar"><span class="dot" style="background:var(--pos)"></span>
        <span class="mono" style="font-size:12.5px">policy.tiers.json</span>
        <span class="muted" style="margin-left:auto;font-size:12px">Express your terms as code — the same policy the UI edits</span></div>
      <div id="monaco"></div>
    </div>
    <div style="display:flex;gap:10px;justify-content:flex-end;margin-top:14px">
      <button class="btn ghost sm" onclick="policyMode='ui';renderTerms(document.getElementById('aaBody'))">← Back to form</button>
      <button class="btn primary sm" id="applyPolicy">Apply policy</button></div>`;
  require.config({ paths: { vs: "https://cdn.jsdelivr.net/npm/monaco-editor@0.52.2/min/vs" } });
  require(["vs/editor/editor.main"], () => {
    monaco.editor.defineTheme("meridian", { base: "vs-dark", inherit: true, rules: [],
      colors: { "editor.background": "#0f131c", "editor.lineHighlightBackground": "#151b26" } });
    const ed = monaco.editor.create($("#monaco"), {
      value: JSON.stringify(tiers, null, 2), language: "json", theme: "meridian",
      fontSize: 13, minimap: { enabled: false }, scrollBeyondLastLine: false,
      fontFamily: "ui-monospace, 'SF Mono', Menlo, monospace", padding: { top: 14 } });
    $("#applyPolicy").onclick = async () => {
      let parsed; try { parsed = JSON.parse(ed.getValue()); }
      catch (e) { toast("Invalid JSON", e.message, "warn"); return; }
      try {
      for (const [id, t] of Object.entries(parsed)) {
        await api(`/api/agent/policies/${id}`, { method: "PUT",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ ask_me: t.ask_me, terms: t.terms,
                                 rules: t.rules || [] }) });
      }
      toast("Policy applied", "All tiers updated from code");
      policyMode = "ui"; renderTerms($("#aaBody"));
      } catch (e) { toast("Policy not applied", e.message, "warn"); }
    };
  });
}

async function renderLedger(target) {
  const entries = await api("/api/agent/ledger");
  if (!entries.length) { target.innerHTML = `<div class="empty">No agent activity yet. Every promise made, every
    resource touched, and every approval you grant is recorded here.</div>`; return; }
  const kindChip = { promised: "", touched: "pos", approved: "warn", denied: "neg", refused: "neg", connected: "", revoked: "neg" };
  target.innerHTML = `<div class="card pad-lg"><table>
    <thead><tr><th>Time</th><th>Event</th><th>Details</th><th class="r">Negotiation</th></tr></thead>
    <tbody>${entries.slice().reverse().map(e => {
      let d = "";
      if (e.kind === "promised") d = `${e.purpose}<br><span style="font-size:12px">${(e.prohibited || []).map(x => `<span class="chip prohibit">${x}</span>`).join(" ")}</span>${e.operation ? `<br><span class="mono" style="font-size:12px">${e.operation.tool}(${JSON.stringify(e.operation.params)})</span>` : ""}${e.terms_uri ? `<br><a class="thumb" href="${e.terms_uri}" target="_blank">${e.terms_uri.split("/terms/")[1] || e.terms_uri}</a>` : ""}<br><span class="thumb">${e.contract}</span>`;
      else if (e.kind === "touched") d = `<span class="mono">${e.tool}</span> ${e.summary || ""}`;
      else if (e.kind === "approved") d = "you personally approved this";
      else if (e.kind === "denied") d = "you denied this request";
      else if (e.kind === "refused") d = `the requesting side declined your terms${e.terms_uri ? ` · <a class="thumb" href="${e.terms_uri}" target="_blank">${e.terms_uri.split("/terms/")[1]}</a>` : ""}`;
      else if (e.kind === "connected") d = `agent connected · <span class="thumb">${e.handle}</span>`;
      else if (e.kind === "revoked") d = `access revoked · ${e.rpts_deactivated} grant(s) killed`;
      return `<tr><td class="thumb">${(e.ts || "").replace("T", " ").replace("Z", "")}</td>
        <td><span class="chip ${kindChip[e.kind] || ""}">${e.kind}</span></td>
        <td>${d}</td><td class="r thumb">${e.family}</td></tr>`;
    }).join("")}</tbody></table></div>`;
}

function updateBadge(n) {
  const nav = $("#navbadge"), ap = $("#apCount");
  if (nav) { nav.textContent = n; nav.classList.toggle("hidden", !n); }
  if (ap) ap.textContent = n ? `(${n})` : "";
}

/* ---- Live approvals ----------------------------------------------------- */
async function pollBadge() {
  try { const items = await api("/api/agent/pending"); updateBadge(items.length); } catch (e) {}
}
function connectEvents() {
  const es = new EventSource("/api/agent/events");
  es.addEventListener("pending", (e) => {
    const d = JSON.parse(e.data);
    toast(d.kind === "connection" ? "New agent wants to connect" : "Trade needs your approval",
      d.purpose || "", "warn");
    pollBadge();
    if (location.hash.includes("agent-authorization") && agentTab === "approvals") renderApprovals($("#aaBody"));
  });
  es.addEventListener("decided", () => {
    pollBadge();
    if (location.hash.includes("agent-authorization")) agentAuthView($("#settingsBody") || document.body);
  });
  es.onerror = () => { es.close(); setTimeout(connectEvents, 3000); };
}

/* ---- Boot --------------------------------------------------------------- */
(async () => {
  const me = await api("/api/me");
  const name = me.name || "Alice";
  $("#whoName").textContent = name;
  $("#avatar").textContent = name[0].toUpperCase();
  if (!location.hash) location.hash = "#/dashboard";
  await render();
  pollBadge();
  connectEvents();
})();
