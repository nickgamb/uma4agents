/* Meridian Organization Console. Vanilla JS, hash routing, dark — the same
   chassis as the client portal, because it is the same kind of thing: a
   surface over an authority, holding nothing itself.

   What differs is whose policy is being edited. In the portal, a person
   writes terms over her own resources. Here an administrator writes a
   ceiling over what every member may permit — and the console's job is to
   keep that distinction visible, including the parts that limit the
   administrator. He cannot read a member's policy from this screen, and
   nothing he writes here can make a member's terms wider. */
const $ = (s, r = document) => r.querySelector(s);
const el = (h) => { const t = document.createElement("template"); t.innerHTML = h.trim(); return t.content.firstChild; };
/* Same rule as the portal: everything rendered here came from somewhere else
   — a member's authority reported it, or another administrator typed it —
   and none of it reaches the DOM as markup. */
const esc = (v) => String(v ?? "").replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (r.status === 401) { location.href = "/login"; throw new Error("auth"); }
  const body = await r.json().catch(() => ({}));
  if (!r.ok) {
    /* The authority's own words. A charter is refused either by its validator
       ("break_glass.resources names something the charter does not claim") or
       by OPA's compiler with a line number, and both are more useful than
       anything this console could say instead. */
    const err = new Error(body.detail || body.error || `request failed (${r.status})`);
    err.status = r.status;
    throw err;
  }
  return body;
}

function toast(title, detail, kind = "") {
  const t = el(`<div class="toast ${kind}"><div class="t">${esc(title)}</div><div class="d">${esc(detail || "")}</div></div>`);
  $("#toasts").appendChild(t);
  setTimeout(() => { t.style.opacity = "0"; t.style.transition = "opacity .3s"; setTimeout(() => t.remove(), 300); }, 6000);
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
  const hash = location.hash.replace(/^#\//, "") || "overview";
  const [base, ...rest] = hash.split("/");
  document.querySelectorAll("#mainnav a").forEach(a =>
    a.classList.toggle("active", a.dataset.route === base));
  const view = $("#view");
  view.innerHTML = `<div class="empty">Loading…</div>`;
  try { await (routes[base] || routes.overview)(view, decodeURIComponent(rest.join("/"))); }
  catch (e) { view.innerHTML = `<div class="empty">Could not load this view.</div>`; console.error(e); }
}
window.addEventListener("hashchange", render);

async function orgHeader() {
  /* Which organization this console administers, and which charter version is
     in force. Filled here rather than per route: it is true of every page, and
     a route that forgot to set it left the placeholder from the markup on
     screen looking like a page that had not finished loading. */
  try {
    const org = await api("/api/org/org");
    $("#orgPill").textContent = org.name;
    $("#charterChip").textContent = `charter v${org.charter_version}`;
  } catch (e) { /* the login redirect handles this */ }
}

function setTitle(title, crumbs) {
  $("#pageTitle").textContent = title;
  $("#crumbs").innerHTML = crumbs || "";
}

/* ---- Overview ----------------------------------------------------------- */
route("overview", async (view) => {
  setTitle("Overview", "");
  const [org, members] = await Promise.all([api("/api/org/org"), api("/api/org/members")]);
  $("#charterChip").textContent = `charter v${org.charter_version}`;
  $("#memberCount").textContent = members.length;
  $("#memberCount").classList.toggle("hidden", !members.length);
  const outside = members.filter(m => m.state !== "within");
  view.innerHTML = `
    <div class="grid cols-4" style="margin-bottom:18px">
      <div class="card"><h3>Members</h3><div class="big num">${members.length}</div>
        <div class="sub">${outside.length ? `${outside.length} not yet confirmed inside the ceiling` : "all confirmed inside the ceiling"}</div></div>
      <div class="card"><h3>Charter</h3><div class="big num">v${esc(org.charter_version)}</div>
        <div class="sub">${esc(org.published_at)} by ${esc(org.published_by)}</div></div>
      <div class="card"><h3>Versions</h3><div class="big num">${esc(org.versions)}</div>
        <div class="sub">every one still readable</div></div>
      <div class="card"><h3>Break glass</h3><div class="big num">${org.break_glass ? "on" : "off"}</div>
        <div class="sub">${org.break_glass ? "members are told every time" : "no override exists"}</div></div>
    </div>
    <div class="card pad-lg" style="margin-bottom:18px">
      <div class="section-head"><h2>What this charter requires</h2>
        <a href="#/charter">Edit →</a></div>
      <div class="muted" style="font-size:12.5px;margin-bottom:12px;max-width:74ch">These are the exact
        sentences a member is shown before she joins, generated from the charter rather than written
        beside it — a summary maintained by hand is one edit away from describing a policy that is no
        longer in force.</div>
      ${(org.summary || []).map(l => `<div class="note">${esc(l)}</div>`).join("")}
    </div>
    <div class="card pad-lg">
      <div class="section-head"><h2>Enrolment code</h2></div>
      <div class="muted" style="font-size:12.5px;margin-bottom:12px;max-width:74ch">Anyone who
        administers accounts for this organization joins with this code, from their own portal. It
        admits; it does not sustain — rotating it does not remove anybody.</div>
      <div style="display:flex;align-items:center;gap:12px">
        <span class="mono" style="font-size:18px;letter-spacing:.06em">${esc(org.join_code)}</span>
        <button class="btn ghost sm" onclick="rotateCode()">Rotate</button>
      </div>
    </div>`;
});

window.rotateCode = async () => {
  try {
    const r = await api("/api/org/join-code/rotate", { method: "POST" });
    toast("Code rotated", `New code ${r.join_code} — existing members are unaffected`);
  } catch (e) { toast("Not rotated", e.message, "warn"); }
  render();
};

/* ---- Groups -------------------------------------------------------------
   The one screen in this console that hands something out. Everything else
   here narrows — the ceiling, the conditions, revoking an agent — and a
   member joined because of what is on this page.

   A group is charter data, not engine data, and saving one publishes a
   charter version. That is deliberate and it is the answer to "why isn't
   this in the policy engine": who is in which group is *state*, and a
   decision engine that stored state would be a database with a worse query
   language. The engine reads the group and decides; this service remembers
   it. Rules in the Rego tab can say "traders may not do this before the
   market opens" precisely because the group arrives in `input.role`. */
route("groups", async (view) => {
  setTitle("Groups", "");
  const [doc, org] = await Promise.all([
    api("/api/org/roles"), api("/api/org/org")]);
  const roles = doc.roles || {}, held = doc.members || {};
  const ids = Object.keys(roles).sort();
  $("#charterChip").textContent = `charter v${org.charter_version}`;
  const claims = (org.claims || []).join(", ");
  view.innerHTML = `
    <div class="card pad-lg" style="margin-bottom:14px">
      <div class="section-head"><h2>What a group is</h2><span class="chip">charter v${esc(org.charter_version)}</span></div>
      <div class="muted" style="font-size:12.5px;max-width:78ch">A named set of this organization's
        resources, plus whether a member may let an agent reach them at all. It is the reason somebody
        joins: everything else in this charter is a ceiling on terms she was going to write anyway.
        A group may only grant what the charter claims — <span class="mono">${esc(claims)}</span> —
        which is what stops a group from being a route to somebody's personal accounts.
        Editing one publishes a new charter version, because it changes the bargain every member was
        shown.</div>
    </div>
    ${ids.length ? ids.map(id => groupCard(id, roles[id], held[id] || [], doc.default_role)).join("")
      : `<div class="empty">No groups yet. A charter with no groups is a ceiling and nothing else —
         members can join, and joining gives them nothing.</div>`}
    ${(doc.unassigned || []).length ? `<div class="card pad-lg" style="margin-bottom:14px">
      <div class="section-head"><h2>In no group</h2></div>
      <div class="muted" style="font-size:12.5px;margin-bottom:10px;max-width:74ch">Enrolled, and this
        organization's ceiling applies to their terms — but nothing here is shared with them.</div>
      ${doc.unassigned.map(o => `<div class="row"><span class="mono">${esc(o)}</span>
        <a href="#/member/${encodeURIComponent(o)}">Open →</a></div>`).join("")}
    </div>` : ""}
    <div class="card pad-lg">
      <div class="section-head"><h2>New group</h2></div>
      ${groupFields("new", { name: "", grants: [], delegation: "first-party-only" })}
      <button class="btn" onclick="saveGroup('new')">Create group</button>
    </div>`;
});

function groupFields(id, role) {
  const d = role.delegation || "none";
  const opt = (v, label) =>
    `<option value="${v}"${d === v ? " selected" : ""}>${label}</option>`;
  return `
    <label class="fld"><div class="lbl">Group id</div>
      <input type="text" id="g-id-${id}" value="${id === "new" ? "" : esc(id)}"
        ${id === "new" ? `placeholder="trader"` : "readonly"}></label>
    <label class="fld"><div class="lbl">Name members are shown</div>
      <input type="text" id="g-name-${id}" value="${esc(role.name || "")}"></label>
    <label class="fld"><div class="lbl">Grants — resources this group may reach (comma-separated)</div>
      <input type="text" id="g-grants-${id}" value="${esc((role.grants || []).join(", "))}"></label>
    <label class="fld"><div class="lbl">Whose agent may act on them</div>
      <select id="g-deleg-${id}">
        ${opt("none", "Nobody's — only the member herself")}
        ${opt("first-party-only", "Only agents she operates herself")}
        ${opt("any-agent", "Any agent, if her own terms allow it")}
      </select></label>`;
}

function groupCard(id, role, members, defaultRole) {
  const isDefault = defaultRole === id;
  return `<div class="card pad-lg" style="margin-bottom:14px">
    <div class="section-head"><h2>${esc(role.name || id)}</h2>
      <span class="chip mono">${esc(id)}</span>
      ${isDefault ? `<span class="chip">joined into by default</span>` : ""}
      <span class="chip">${members.length} member${members.length === 1 ? "" : "s"}</span></div>
    ${groupFields(id, role)}
    <div style="display:flex;gap:8px;align-items:center;margin-top:4px">
      <button class="btn sm" onclick="saveGroup('${esc(id)}')">Save</button>
      ${isDefault ? "" :
        `<button class="btn ghost sm" onclick="makeDefault('${esc(id)}')">Make default</button>`}
      <button class="btn ghost sm" onclick="deleteGroup('${esc(id)}')">Delete</button>
    </div>
    ${members.length ? `<div style="margin-top:14px">
      <div class="lbl">In this group</div>
      ${members.map(o => `<div class="row"><span class="mono">${esc(o)}</span>
        <a href="#/member/${encodeURIComponent(o)}">Open →</a></div>`).join("")}
    </div>` : ""}
  </div>`;
}

window.saveGroup = async (key) => {
  const id = ($(`#g-id-${key}`).value || "").trim();
  if (!id) { toast("Not saved", "A group needs an id", "warn"); return; }
  const body = {
    name: $(`#g-name-${key}`).value,
    grants: ($(`#g-grants-${key}`).value || "").split(",").map(s => s.trim()).filter(Boolean),
    delegation: $(`#g-deleg-${key}`).value,
  };
  try {
    const r = await api(`/api/org/roles/${encodeURIComponent(id)}`, {
      method: "PUT", headers: { "content-type": "application/json" },
      body: JSON.stringify(body) });
    toast("Group saved", `Charter v${r.version}. Every member's authority is told, and the ones in
      this group pick up the change on their next envelope read.`);
  } catch (e) { toast("Not saved", e.message, "warn"); }
  render();
};

window.makeDefault = async (id) => {
  try {
    const r = await api("/api/org/roles/default", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ role: id }) });
    toast("Default set", `Charter v${r.version}. New members land in ${id}; nobody already
      enrolled moves.`);
  } catch (e) { toast("Not set", e.message, "warn"); }
  render();
};

window.deleteGroup = async (id) => {
  try {
    const r = await api(`/api/org/roles/${encodeURIComponent(id)}`, { method: "DELETE" });
    toast("Group removed", `Charter v${r.version}`);
  } catch (e) { toast("Not removed", e.message, "warn"); }
  render();
};

/* ---- Members ------------------------------------------------------------
   The screen an administrator expects to be able to read everything from,
   and cannot. What a member permits is hers; what crosses to here is that
   her authority applied the ceiling and which of its fields bit. The empty
   columns are the feature. */
route("members", async (view) => {
  setTitle("Members", "");
  const [members, invites, roleDoc] = await Promise.all([
    api("/api/org/members"), api("/api/org/invites").catch(() => []),
    api("/api/org/roles").catch(() => ({ roles: {} }))]);
  const ROLES = roleDoc.roles || {};
  if (!members.length && !invites.length) {
    view.innerHTML = inviteCard([]) + `<div class="empty">Nobody has joined yet. Invite someone above,
      or hand out this organization's code — see <a href="#/overview">Overview</a>.</div>`;
    wireInvites(view);
    return;
  }
  const DELEGATION = {
    none: `<span class="chip neg">no agent</span>`,
    "first-party-only": `<span class="chip warn">only theirs</span>`,
    "any-agent": `<span class="chip pos">any agent</span>`,
  };
  const STATE = {
    within: "inside the ceiling", stale: "clamping to the new charter",
    outside: "outside the ceiling", unreported: "has not reported yet",
  };
  if (!members.length) {
    // An empty table with headers reads as a broken screen rather than an
    // empty one.
    view.innerHTML = inviteCard(invites) + `<div class="empty">Nobody has accepted yet.</div>`;
    wireInvites(view);
    return;
  }
  view.innerHTML = inviteCard(invites) + `
    <div class="card pad-lg" style="margin-bottom:14px">
      <div class="muted" style="font-size:12.5px;max-width:74ch">A member's role is what she may
        reach of this organization's resources, and whether an agent may act on them for her at all.
        Everything else on this screen is deliberately thin: this organization can see that its
        ceiling is being applied and which of its fields narrowed her, and it cannot see her terms,
        her own accounts, or the agents that only touch them. An organization able to read every
        member's private arrangements would have replaced the member's layer rather than sat above
        it.</div>
    </div>
    <div class="card pad-lg"><div class="table-scroll"><table>
      <thead><tr><th>Member</th><th>Role</th><th>Agents may act</th><th>Joined</th>
        <th>Charter</th><th>Narrowed by</th><th class="r">State</th><th></th></tr></thead>
      <tbody>${members.map(m => `<tr>
        <td><div class="tick"><div class="badge2">👤</div>
          <div class="nm"><a href="#/member/${encodeURIComponent(m.owner)}">${esc(m.owner)}</a></div></div></td>
        <td class="role-cell"><select data-role-for="${esc(m.owner)}">
          <option value=""${m.role ? "" : " selected"}>no access</option>
          ${Object.entries(ROLES).map(([id, r]) =>
            `<option value="${esc(id)}"${id === m.role ? " selected" : ""}>${esc(r.name || id)}</option>`).join("")}
        </select><div class="cell-sub mono">${(m.grants || []).join(", ") || "—"}</div></td>
        <td>${DELEGATION[m.delegation] || esc(m.delegation)}</td>
        <td class="nowrap" title="${esc((m.joined || "").replace("T", " ").replace("Z", ""))}">${
          esc((m.joined || "").slice(0, 10))}</td>
        <td>v${esc(m.charter_version)}${m.charter_version !== m.current_version
          ? `<div class="cell-sub">current is v${esc(m.current_version)}</div>` : ""}</td>
        <td>${((m.compliance || {}).clamped_fields || []).map(f =>
          `<span class="chip">${esc(f)}</span>`).join(" ") || "—"}</td>
        <td class="r state-cell"><span class="member-state ${esc(m.state)}">${esc(STATE[m.state] || m.state)}</span></td>
        <td class="r"><button class="btn danger sm" data-remove="${esc(m.owner)}">Remove</button></td>
      </tr>`).join("")}</tbody></table></div></div>`;
  /* Bound by attribute rather than an inline handler: an owner name arrives
     from a member's enrolment and building JavaScript out of it is the one
     way this table could be made to run someone else's code. */
  view.querySelectorAll("[data-remove]").forEach(b =>
    b.addEventListener("click", () => removeMember(b.dataset.remove)));
  /* The one control in this console that widens anything. Everything else
     here narrows; a role is what the organization gives, and it is the
     reason anybody joins. */
  view.querySelectorAll("[data-role-for]").forEach(sel =>
    sel.addEventListener("change", () => setRole(sel.dataset.roleFor, sel.value)));
  wireInvites(view);
});

async function setRole(owner, role) {
  try {
    const r = await api(`/api/org/members/${encodeURIComponent(owner)}/role`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ role }) });
    toast("Role set", role
      ? `${owner} can now reach what ${role} grants — their authority picks it up immediately`
      : `${owner} keeps membership and loses access to this organization's resources`);
  } catch (e) { toast("Not set", e.message, "warn"); }
  render();
}

/* Inviting is the direction this relationship usually runs in: an
   organization knows who works for it. What it produces is a question, not a
   membership — until the person accepts from her own portal, nothing about
   her authority, her policy or her resources has changed, and this console
   does not even know where her authorization server is. An organization able
   to enrol somebody by naming her would be an organization able to clamp a
   stranger's terms. */
function inviteCard(invites) {
  const open = (invites || []).filter(i => i.state === "open");
  const answered = (invites || []).filter(i => i.state !== "open");
  return `<div class="card pad-lg" style="margin-bottom:14px">
    <div class="section-head"><h2>Invite someone</h2></div>
    <div class="muted" style="font-size:12.5px;margin-bottom:14px;max-width:74ch">Their invitation
      appears in their own portal as a decision waiting on them. They see the whole charter in
      sentences, and exactly what accepting would do to the terms they have already written, before
      they answer. You will see here whether they accepted or declined.</div>
    <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end">
      <label class="fld" style="max-width:260px;margin:0"><div class="lbl">Who — the identifier they sign in with</div>
        <input type="text" id="inv-owner" placeholder="e.g. carol" autocomplete="off"></label>
      <label class="fld" style="flex:1;min-width:260px;margin:0"><div class="lbl">A note they will read (optional)</div>
        <input type="text" id="inv-note" placeholder="e.g. For the accounts you cover on the Hartwell mandate"></label>
      <button class="btn primary sm" id="inviteBtn">Send invitation</button>
    </div>
    ${open.length ? `<div class="lbl" style="margin-top:20px">Waiting on them</div>
      <table><thead><tr><th>Who</th><th>Invited</th><th>By</th><th>Note</th><th></th></tr></thead>
      <tbody>${open.map(i => `<tr>
        <td><div class="nm">${esc(i.owner)}</div></td>
        <td class="nowrap">${esc((i.created || "").replace("T", " ").replace("Z", ""))}</td>
        <td>${esc(i.by)}</td><td class="prose">${esc(i.note || "—")}</td>
        <td class="r"><button class="btn ghost sm" data-withdraw="${esc(i.owner)}">Withdraw</button></td>
      </tr>`).join("")}</tbody></table>` : ""}
    ${answered.length ? `<div class="lbl" style="margin-top:20px">Answered</div>
      ${answered.map(i => `<div class="note">${esc(i.owner)} <b>${esc(i.state)}</b> on
        ${esc((i.decided || "").replace("T", " ").replace("Z", ""))}
        <button class="btn ghost sm" data-withdraw="${esc(i.owner)}">Clear</button></div>`).join("")}` : ""}
  </div>`;
}

function wireInvites(view) {
  const btn = view.querySelector("#inviteBtn");
  if (btn) btn.onclick = sendInvite;
  view.querySelectorAll("[data-withdraw]").forEach(b =>
    b.addEventListener("click", () => withdrawInvite(b.dataset.withdraw)));
}

async function sendInvite() {
  const owner = $("#inv-owner").value.trim();
  if (!owner) { toast("Who?", "Give the identifier they sign in with", "warn"); return; }
  try {
    await api("/api/org/invites", { method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ owner, note: $("#inv-note").value.trim() }) });
    toast("Invitation sent", `${owner} will see it in their own portal. Nothing of theirs has changed.`);
  } catch (e) { toast("Not sent", e.message, "warn"); }
  render();
}

async function withdrawInvite(owner) {
  try { await api(`/api/org/invites/${encodeURIComponent(owner)}`, { method: "DELETE" }); }
  catch (e) { toast("Not withdrawn", e.message, "warn"); }
  render();
}

async function removeMember(owner) {
  try {
    await api(`/api/org/members/${encodeURIComponent(owner)}`, { method: "DELETE" });
    toast("Removed", `${owner} is no longer governed here. What this charter narrowed in their terms stays narrowed.`, "warn");
  } catch (e) { toast("Not removed", e.message, "warn"); }
  render();
}

/* ---- One member ---------------------------------------------------------

   Co-administration, which is the arrangement PP2PI names and nothing
   implements: two administrators over one subject's resources. The
   organization holds the accounts, so an administrator can answer for what
   is connected to them — the same pending queue, the same agents, the same
   operators the member sees.

   Two things keep it from being a takeover, and neither is enforced by this
   screen. Her authorization server is what refuses an approval over a
   resource this charter does not claim, and her authorization server is what
   writes his name into her record. A limit a console enforced would be a
   limit a console could route around. */
route("member", async (view, owner) => {
  setTitle(owner, `<b>Members</b> › ${esc(owner)}`);
  const [pending, conns, operators, ledger] = await Promise.all([
    api(`/api/org/members/${encodeURIComponent(owner)}/pending`).catch(() => []),
    api(`/api/org/members/${encodeURIComponent(owner)}/connections`).catch(() => []),
    api(`/api/org/members/${encodeURIComponent(owner)}/operators`).catch(() => []),
    api(`/api/org/members/${encodeURIComponent(owner)}/ledger`).catch(() => []),
  ]);
  view.innerHTML = `
    <div class="card pad-lg" style="margin-bottom:14px">
      <div class="section-head"><h2>${esc(owner)}</h2>
        <a href="#/members" style="margin-left:auto">← All members</a></div>
      <div class="muted" style="font-size:12.5px;max-width:74ch">Everything below concerns
        <b>this organization's resources only</b>. Agents that touch ${esc(owner)}'s own accounts do
        not appear here, requests about them cannot be answered here, and there is no view of them to
        open — her authority filters by what this charter claims before it answers. What you do act on
        is written into <b>her own record</b> with your name on it, and she sees it on her screen as it
        happens. Shutting an agent out stops it reaching the firm's book; her relationship with it
        carries on.</div>
    </div>
    ${memberPending(owner, pending)}
    ${memberConnections(owner, conns)}
    ${memberOperators(owner, operators)}
    ${memberLedger(ledger)}`;
  wireMember(view, owner);
});

function memberPending(owner, pending) {
  if (!pending.length) return `<div class="card pad-lg" style="margin-bottom:14px">
    <div class="section-head"><h2>Waiting on them, about this organization</h2></div>
    <div class="muted" style="font-size:12.5px">Nothing about this organization's resources is
      pending. Requests about their own accounts do not appear here.</div></div>`;
  return `<div class="card pad-lg" style="margin-bottom:14px">
    <div class="section-head"><h2>Waiting on them, about this organization</h2>
      <span class="chip warn">${pending.length}</span></div>
    ${pending.map(p => `<div class="card" style="background:var(--surface-2);margin-bottom:10px">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
        <span class="chip ${p.kind === "connection" ? "" : "warn"}">${p.kind === "connection" ? "New agent" : "Operation"}</span>
        <b>${esc(p.tier)}</b>
        <span class="mono muted" style="font-size:12px">${esc(p.resource_id || "")}</span>
        <span class="chip pos">this organization's</span></div>
      <div class="kv"><span class="k">Purpose</span><span>${esc(p.purpose)}</span></div>
      ${p.reason ? `<div class="kv"><span class="k">Says it is for</span>
        <span class="claimed">${esc(p.reason)}</span></div>` : ""}
      ${p.operation ? `<div class="kv"><span class="k">Operation</span>
        <span class="mono">${esc(p.operation.tool)}(${esc(JSON.stringify(p.operation.params))})</span></div>` : ""}
      <div class="kv"><span class="k">Identity</span><span>${esc(p.identity?.level || "unknown")}${
        p.identity?.sub ? " · " + esc(p.identity.sub) : ""}</span></div>
      <div style="display:flex;gap:10px;margin-top:12px">
        <button class="btn pos sm" data-decide="${esc(p.family)}" data-as="approved">Approve</button>
        <button class="btn danger sm" data-decide="${esc(p.family)}" data-as="denied">Deny</button>
      </div></div>`).join("")}</div>`;
}

function memberConnections(owner, conns) {
  if (!conns.length) return "";
  return `<div class="card pad-lg" style="margin-bottom:14px">
    <div class="section-head"><h2>Agents that touch this organization's resources</h2></div>
    <table><thead><tr><th>Agent</th><th>Identity</th><th>Handle</th><th>Connected</th>
      <th>Last active</th><th class="r">Status</th><th></th></tr></thead>
    <tbody>${conns.map(c => `<tr>
      <td><div class="tick"><div class="badge2">🤖</div><div class="nm">${esc(c.label)}</div></div></td>
      <td>${esc(c.identity?.level || "—")}</td>
      <td class="thumb">${esc(c.handle.length > 26 ? c.handle.slice(0, 24) + "…" : c.handle)}</td>
      <td class="nowrap">${esc((c.first_seen || "").replace("T", " ").replace("Z", ""))}</td>
      <td class="nowrap">${esc((c.last_access || "—").replace("T", " ").replace("Z", ""))}</td>
      <td class="r"><span class="chip ${c.status === "active" ? "pos" : "neg"}">${esc(c.status)}</span></td>
      <td class="r">${c.blocked_for_organization
        ? `<button class="btn ghost sm" data-restore="${esc(c.handle)}">Allow again</button>`
        : `<button class="btn danger sm" data-revoke="${esc(c.handle)}">Shut out</button>`}</td>
    </tr>`).join("")}</tbody></table></div>`;
}

function memberOperators(owner, operators) {
  if (!operators.length) return "";
  return `<div class="card pad-lg" style="margin-bottom:14px">
    <div class="section-head"><h2>Operators behind those agents</h2></div>
    <div class="muted" style="font-size:12.5px;margin-bottom:12px;max-width:74ch">Blocking one shuts
      out every agent it runs for this member and revokes what is already connected. It does not remove
      them from the internet: the same party can come back anonymously, with nothing standing behind
      it, and will face her policy as a stranger like any other.</div>
    <table><thead><tr><th>Operator</th><th>Agents</th><th class="r">Status</th><th></th></tr></thead>
    <tbody>${operators.map(o => `<tr>
      <td><div class="nm">${esc(o.name)}</div><div class="muted mono" style="font-size:12px">${esc(o.origin)}</div></td>
      <td>${esc(o.active)} active of ${esc(o.agents)}</td>
      <td class="r"><span class="chip ${o.blocked ? "neg" : "pos"}">${o.blocked ? "blocked" : "accepted"}</span></td>
      <td class="r">${o.blocked
        ? `<button class="btn ghost sm" data-op="unblock" data-origin="${esc(o.origin)}">Allow again</button>`
        : `<button class="btn danger sm" data-op="block" data-origin="${esc(o.origin)}">Block</button>`}</td>
    </tr>`).join("")}</tbody></table></div>`;
}

function memberLedger(entries) {
  if (!entries.length) return "";
  const recent = entries.slice(-25).reverse();
  return `<div class="card pad-lg">
    <div class="section-head"><h2>Their record</h2>
      <span class="muted" style="font-size:12.5px;margin-left:auto">the same record they read — not a
      separate administrator's view</span></div>
    <table><thead><tr><th>Time</th><th>Event</th><th>Who</th><th>Details</th></tr></thead>
    <tbody>${recent.map(e => `<tr>
      <td class="thumb">${esc((e.ts || "").replace("T", " ").replace("Z", ""))}</td>
      <td><span class="chip">${esc(e.kind)}</span></td>
      <td>${e.by ? `<span class="chip warn">${esc(e.by.admin)} · ${esc(e.by.name || e.by.org)}</span>`
        : `<span class="muted">them</span>`}</td>
      <td class="prose">${esc(e.tier || e.operator || e.purpose || e.what || e.tool || "")}</td>
    </tr>`).join("")}</tbody></table></div>`;
}

function wireMember(view, owner) {
  const call = async (path, body, ok) => {
    try {
      await api(`/api/org/members/${encodeURIComponent(owner)}/${path}`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify(body || {}) });
      toast(ok, `Recorded in ${owner}'s record, under your name`);
    } catch (e) { toast("Not done", e.message, "warn"); }
    render();
  };
  view.querySelectorAll("[data-decide]").forEach(b => b.onclick = () =>
    call(`pending/${encodeURIComponent(b.dataset.decide)}/decision`,
         { decision: b.dataset.as },
         b.dataset.as === "approved" ? "Approved" : "Denied"));
  view.querySelectorAll("[data-revoke]").forEach(b => b.onclick = () =>
    call(`connections/${encodeURIComponent(b.dataset.revoke)}/revoke`, {},
         "Agent shut out of this organization's resources"));
  view.querySelectorAll("[data-restore]").forEach(b => b.onclick = () =>
    call(`connections/${encodeURIComponent(b.dataset.restore)}/restore`, {},
         "Agent allowed again"));
  view.querySelectorAll("[data-op]").forEach(b => b.onclick = () =>
    call(`operators/${b.dataset.op}`, { origin: b.dataset.origin },
         b.dataset.op === "block" ? "Operator blocked" : "Operator allowed again"));
}

/* ---- Charter ------------------------------------------------------------
   Two ways to edit one document, exactly as the client portal offers a
   person: a form for the fields most organizations only ever change, and the
   whole charter as JSON for everything else. Neither is a different policy —
   the form writes the same document the editor shows. */
let charterMode = "form";

route("charter", async (view) => {
  setTitle("Charter", `<b>Policy</b> › version in force`);
  const doc = await api("/api/org/charter");
  $("#charterChip").textContent = `charter v${doc.version}`;
  if (charterMode === "code") return charterCode(view, doc);
  if (charterMode === "rego") return charterRego(view, doc);
  charterForm(view, doc);
});

function charterHead(doc) {
  return `<div class="card pad-lg" style="margin-bottom:14px">
    <div class="section-head"><h2>${esc(doc.charter.name)}</h2>
      <span class="chip">v${esc(doc.version)}</span>
      <span class="muted" style="margin-left:auto;font-size:12.5px">published ${esc(doc.published_at)} by ${esc(doc.published_by)}</span></div>
    <div class="muted" style="font-size:12.5px;max-width:74ch">Saving publishes a new version rather
      than editing this one. Members clamped their terms to a particular version and agents signed
      agreements under it, so what this organization required at the time has to stay answerable — the
      same reason a member's own terms are versioned rather than overwritten.</div>
  </div>`;
}

function charterTabs(active) {
  const tab = (id, label) => `<button data-c="${id}" class="${active === id ? "active" : ""}">${label}</button>`;
  return `<div class="subtabs">${tab("form", "Settings")}${tab("code", "Charter as code")}${tab("rego", "Rules (Rego)")}</div>`;
}

function wireTabs(view) {
  view.querySelectorAll(".subtabs button").forEach(b =>
    b.onclick = () => { charterMode = b.dataset.c; render(); });
}

function charterForm(view, doc) {
  const c = doc.charter, e = c.envelope || {}, k = c.conditions || {}, g = c.break_glass || {};
  const p = c.identity_provider || {};
  view.innerHTML = charterHead(doc) + charterTabs("form") + `
    <div class="card pad-lg" style="margin-bottom:14px">
      <div class="section-head"><h2>What this organization governs</h2></div>
      <div class="muted" style="font-size:12.5px;margin-bottom:12px;max-width:74ch">Resource patterns.
        A member's resources that match none of these are untouched by this charter — she enrolled part
        of what she administers, not all of it, and she is shown exactly which part before she joins.
        <span class="mono">*</span> stops at the <span class="mono">/</span>.</div>
      <label class="fld"><div class="lbl">Claims (comma-separated)</div>
        <input type="text" id="c-claims" value="${esc((c.claims || []).join(", "))}"></label>
    </div>

    <div class="card pad-lg" style="margin-bottom:14px">
      <div class="section-head"><h2>The ceiling</h2></div>
      <div class="muted" style="font-size:12.5px;margin-bottom:12px;max-width:74ch">Every field here can
        only narrow a member's terms. There is nothing in this section that can widen one — which is
        what makes it safe to apply to terms that were written before this charter existed.</div>
      <label class="fld"><div class="lbl">No grant may last longer than (seconds)</div>
        <input type="number" id="c-exp" value="${esc(e.max_expires_in)}"></label>
      <label class="fld"><div class="lbl">Scopes that may ever be granted (comma-separated, blank for no limit)</div>
        <input type="text" id="c-scopes" value="${esc((e.allowed_scopes || []).join(", "))}"></label>
      <label class="fld"><div class="lbl">Prohibitions added to every member's terms</div>
        <input type="text" id="c-prohibited" value="${esc((e.require_prohibited || []).join(", "))}"></label>
      <label class="fld"><div class="lbl">Resources a member must be asked about, whatever her own rules say</div>
        <input type="text" id="c-ask" value="${esc((e.always_ask || []).join(", "))}"></label>
    </div>

    <div class="card pad-lg" style="margin-bottom:14px">
      <div class="section-head"><h2>What a request must look like</h2></div>
      <div class="muted" style="font-size:12.5px;margin-bottom:12px;max-width:74ch">Evaluated per
        request by this organization's policy engine. Like everything else here these can only refuse
        or interrupt — evidence a requesting agent supplies about itself is allowed to make a request
        harder and never easier, at this layer exactly as at a member's.</div>
      <label class="fld"><div class="lbl">Minimum accountability (0–3) — is anyone named standing behind the agent?</div>
        <input type="number" id="c-acct" min="0" max="3" value="${esc(k.min_accountability ?? 0)}"></label>
      <label class="fld"><div class="lbl">Minimum key binding (0–3)</div>
        <input type="number" id="c-bind" min="0" max="3" value="${esc(k.min_binding ?? 0)}"></label>
      <label class="fld"><div class="lbl">Minimum credential provenance (0–3)</div>
        <input type="number" id="c-prov" min="0" max="3" value="${esc(k.min_provenance ?? 0)}"></label>
      <div style="display:flex;align-items:center;gap:12px;margin-top:16px">
        <div class="toggle"><input type="checkbox" id="c-reason" ${k.require_reason ? "checked" : ""}><span class="track"></span></div>
        <div><div style="font-weight:560">Refuse an agent that does not say what it wants access for</div></div>
      </div>
      <div style="display:flex;align-items:center;gap:12px;margin-top:12px">
        <div class="toggle"><input type="checkbox" id="c-mission" ${k.require_mission ? "checked" : ""}><span class="track"></span></div>
        <div><div style="font-weight:560">Refuse an agent that cites no mandate for its errand</div></div>
      </div>
    </div>

    <div class="card pad-lg" style="margin-bottom:14px">
      <div class="section-head"><h2>Federated identity (Cross App Access)</h2></div>
      <div class="muted" style="font-size:12.5px;margin-bottom:12px;max-width:74ch">Where this
        organization's people are asserted from. With this on, a member's authority asks an agent
        which employee it acts for — as an ID-JAG from the provider below — before it dictates her
        terms. It is an identity provider, not a policy one: it says who and which application, and
        nothing about what may be done to a resource.
        <br><br>This is a separate company's endpoint from the one you signed in with. That one is
        Meridian's and authenticates you into this console; this one is yours, and its connections
        are administered there rather than here.</div>
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:14px">
        <div class="toggle"><input type="checkbox" id="c-idp-on" ${p.enabled ? "checked" : ""}><span class="track"></span></div>
        <div><div style="font-weight:560">Federate identity to an external provider</div></div>
      </div>
      <label class="fld"><div class="lbl">Provider issuer — where assertions are minted</div>
        <input type="text" id="c-idp-iss" placeholder="https://…" value="${esc(p.issuer || "")}"></label>
      <label class="fld"><div class="lbl">Directory issuer — where your people sign in (blank to discover it from the provider)</div>
        <input type="text" id="c-idp-dir" placeholder="discovered" value="${esc(p.directory || "")}"></label>
      <div style="display:flex;align-items:center;gap:12px;margin-top:16px">
        <div class="toggle"><input type="checkbox" id="c-idp-enrol" ${p.enrol !== false ? "checked" : ""}><span class="track"></span></div>
        <div><div style="font-weight:560">Let your people enrol without a code</div>
          <div class="muted" style="font-size:12px">The provider vouching for them is the entitlement. One person's token still cannot enrol another.</div></div>
      </div>
    </div>

    <div class="card pad-lg" style="margin-bottom:14px">
      <div class="section-head"><h2>Break glass</h2></div>
      <div class="muted" style="font-size:12.5px;margin-bottom:12px;max-width:74ch">The one thing in
        this charter that is not a restriction. It lets this organization reach the resources named
        below without the member's approval and without her authorization server's cooperation — and it
        cannot be done quietly: she is told the moment a window opens, before any data moves, and every
        use lands in her own record. It may only name resources this charter already claims.</div>
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:14px">
        <div class="toggle"><input type="checkbox" id="c-glass" ${g.enabled ? "checked" : ""}><span class="track"></span></div>
        <div><div style="font-weight:560">Allow break-glass access</div></div>
      </div>
      <label class="fld"><div class="lbl">Resources it may reach</div>
        <input type="text" id="c-glass-res" value="${esc((g.resources || []).join(", "))}"></label>
      <label class="fld"><div class="lbl">A break-glass grant lasts at most (seconds)</div>
        <input type="number" id="c-glass-exp" value="${esc(g.max_expires_in ?? 900)}"></label>
      <label class="fld"><div class="lbl">Operator origins whose agents may invoke it without an administrator (blank = console only)</div>
        <input type="text" id="c-glass-inv" value="${esc((g.invokers || []).join(", "))}"></label>
    </div>

    <div style="display:flex;gap:10px;justify-content:flex-end">
      <button class="btn primary sm" onclick="saveForm()">Publish new version</button>
    </div>
    <div id="charterError"></div>`;
  wireTabs(view);
  CHARTER = doc.charter;
}

let CHARTER = null;
const list = (id) => $(id).value.split(",").map(s => s.trim()).filter(Boolean);

window.saveForm = async () => {
  const scopes = list("#c-scopes");
  const doc = {
    ...CHARTER,
    claims: list("#c-claims"),
    envelope: {
      max_expires_in: parseInt($("#c-exp").value, 10),
      // Blank means "no scope restriction", which is different from "no scope
      // may be granted". The second is a legitimate and very loud thing to
      // write and it is written as an explicit empty list in the code editor,
      // never produced by leaving a box empty.
      ...(scopes.length ? { allowed_scopes: scopes } : {}),
      require_prohibited: list("#c-prohibited"),
      always_ask: list("#c-ask"),
    },
    conditions: {
      min_accountability: parseInt($("#c-acct").value, 10) || 0,
      min_binding: parseInt($("#c-bind").value, 10) || 0,
      min_provenance: parseInt($("#c-prov").value, 10) || 0,
      require_reason: $("#c-reason").checked,
      require_mission: $("#c-mission").checked,
    },
    identity_provider: {
      enabled: $("#c-idp-on").checked,
      issuer: $("#c-idp-iss").value.trim(),
      assertion: "id-jag",
      directory: $("#c-idp-dir").value.trim(),
      enrol: $("#c-idp-enrol").checked,
    },
    break_glass: {
      enabled: $("#c-glass").checked,
      resources: list("#c-glass-res"),
      max_expires_in: parseInt($("#c-glass-exp").value, 10) || 900,
      require_reason: true,
      invokers: list("#c-glass-inv"),
    },
  };
  await publishCharter(doc);
};

async function publishCharter(doc) {
  try {
    const r = await api("/api/org/charter", { method: "PUT",
      headers: { "content-type": "application/json" }, body: JSON.stringify(doc) });
    toast("Charter v" + r.version + " published", "Every member's authority re-clamps to it");
    $("#charterError").innerHTML = "";
    render();
    return true;
  } catch (e) {
    const box = $("#charterError");
    if (box) box.innerHTML = `<div class="compile-error">${esc(e.message)}</div>`;
    toast("Not published", e.message, "warn");
    return false;
  }
}

function monacoTheme() {
  monaco.editor.defineTheme("meridian", { base: "vs-dark", inherit: true, rules: [],
    colors: { "editor.background": "#0f131c", "editor.lineHighlightBackground": "#151b26" } });
}

function charterCode(view, doc) {
  view.innerHTML = charterHead(doc) + charterTabs("code") + `
    <div class="editor-wrap">
      <div class="editor-bar"><span class="dot" style="background:var(--pos)"></span>
        <span class="mono" style="font-size:12.5px">charter.json</span>
        <span class="muted" style="margin-left:auto;font-size:12px">The whole document the form edits — every field, including the ones it does not show</span></div>
      <div id="monaco"></div>
    </div>
    <div id="charterError"></div>
    <div style="display:flex;gap:10px;justify-content:flex-end;margin-top:14px">
      <button class="btn primary sm" id="applyCharter">Publish new version</button></div>`;
  wireTabs(view);
  require.config({ paths: { vs: "https://cdn.jsdelivr.net/npm/monaco-editor@0.52.2/min/vs" } });
  require(["vs/editor/editor.main"], () => {
    monacoTheme();
    const ed = monaco.editor.create($("#monaco"), {
      value: JSON.stringify(doc.charter, null, 2), language: "json", theme: "meridian",
      fontSize: 13, minimap: { enabled: false }, scrollBeyondLastLine: false,
      fontFamily: "ui-monospace, 'SF Mono', Menlo, monospace", padding: { top: 14 } });
    $("#applyCharter").onclick = async () => {
      let parsed;
      try { parsed = JSON.parse(ed.getValue()); }
      catch (e) { $("#charterError").innerHTML = `<div class="compile-error">${esc(e.message)}</div>`; return; }
      await publishCharter(parsed);
    };
  });
}

/* The escape hatch, and the reason there is an engine here at all.

   An organization is the case a policy engine was built for: the operator is
   the deciding party, there is a compliance function, and the policy outlives
   whoever wrote it. So the charter's declarative half is a front end onto a
   shipped Rego module, and anything it cannot say goes here — with the one
   structural limit that this package can only contribute `deny` and `ask`.
   There is no rule shape available in it that grants anything. */
const REGO_STARTER = `package u4a.custom

import rego.v1

# The organization's operating rules. Two sets, and only two:
#
#   deny contains "<sentence>"   the request is refused
#   ask  contains "<sentence>"   the member is asked first
#
# The sentence ends up in the member's ledger and in the dialog she is shown,
# so write it for her rather than for you.
#
# Available: input.member, input.role.{id, name, delegation},
# input.request.{resource_id, scopes, expires_in, purpose, reason, mission,
# operation, tier, assurance, standing}, and input.charter.

# A close period. The kind of rule that belongs here rather than in the
# charter: it is true for three weeks a quarter, nobody re-consents when it
# starts, and stating it needs a clock.
deny contains msg if {
	freeze
	input.request.resource_id == "northwind-vault/execute_trade"
	msg := "the firm is in its close period and is not executing trades"
}

freeze if {
	[_, month, day] := time.date(time.now_ns())
	month in [3, 6, 9, 12]
	day >= 25
}

# Tighter than the charter's ceiling, for one group. The ceiling is what
# every member agreed to; this is what this firm currently thinks an analyst
# should hold, and it moves without touching the bargain.
deny contains msg if {
	input.role.id == "analyst"
	input.request.expires_in > 900
	msg := "an analyst's access to the firm's book is granted a quarter of an hour at a time"
}

# Outside market hours, a person decides. Not a refusal — the member is asked,
# which is the right answer when the request is unusual rather than wrong.
ask contains msg if {
	[hour, _, _] := time.clock(time.now_ns())
	hour < 13
	input.request.resource_id == "northwind-vault/execute_trade"
	msg := "this order was placed outside market hours"
}
`;

function charterRego(view, doc) {
  const existing = doc.charter.rego || "";
  view.innerHTML = charterHead(doc) + charterTabs("rego") + `
    <div class="card pad-lg" style="margin-bottom:14px">
      <div class="muted" style="font-size:12.5px;max-width:74ch;line-height:1.55">This organization's
        operating rules, evaluated per request by its policy engine alongside the settings on the first
        tab. They can contribute two things and nothing else: <span class="mono">deny</span> and
        <span class="mono">ask</span>. There is no rule you can write here that widens a member's terms,
        and that is a property of the shape rather than a convention — the shipped module reads those
        two sets and there is no third. A module that does not compile is never published, so the
        charter in force always has an engine that can evaluate it.
        <div style="margin-top:10px"><b>Which layer does a rule belong in?</b> Ask whether a member
        would need to agree to it again. The <a href="#/charter">Settings</a> tab is the bargain — what
        this organization governs, what her groups may reach, the ceiling on her terms — and every
        member is shown it in full before she joins. These rules are not shown to her line by line;
        she is told they exist and sees the sentence of any rule that stops her. So a close period,
        market hours, or a limit this firm is trying for a quarter belongs here. Widening what a group
        may reach does not: that is the bargain, and it belongs in the charter where the version
        history of it lives.</div></div>
    </div>
    <div class="editor-wrap">
      <div class="editor-bar"><span class="dot" style="background:${existing ? "var(--pos)" : "var(--text-faint)"}"></span>
        <span class="mono" style="font-size:12.5px">u4a.custom.rego</span>
        <span class="muted" style="margin-left:auto;font-size:12px">${existing ? "in force" : "not set — this organization runs the settings above and nothing else"}</span></div>
      <div id="monaco"></div>
    </div>
    <div id="charterError"></div>
    <div style="display:flex;gap:10px;justify-content:flex-end;margin-top:14px">
      ${existing ? `<button class="btn ghost sm" id="clearRego">Remove these rules</button>` : ""}
      <button class="btn primary sm" id="applyRego">Publish new version</button></div>`;
  wireTabs(view);
  require.config({ paths: { vs: "https://cdn.jsdelivr.net/npm/monaco-editor@0.52.2/min/vs" } });
  require(["vs/editor/editor.main"], () => {
    monacoTheme();
    registerRego();
    const ed = monaco.editor.create($("#monaco"), {
      value: existing || REGO_STARTER, language: "rego", theme: "meridian",
      fontSize: 13, minimap: { enabled: false }, scrollBeyondLastLine: false,
      fontFamily: "ui-monospace, 'SF Mono', Menlo, monospace", padding: { top: 14 } });
    $("#applyRego").onclick = () => publishCharter({ ...doc.charter, rego: ed.getValue() });
    const clear = $("#clearRego");
    if (clear) clear.onclick = () => publishCharter({ ...doc.charter, rego: "" });
  });
}

/* Monaco ships no Rego grammar, and an admin editing policy in an untinted
   buffer is being asked to proofread. Small Monarch tokenizer — keywords,
   strings, comments, numbers — which is the whole of what makes this
   readable. */
let regoRegistered = false;
function registerRego() {
  if (regoRegistered) return;
  regoRegistered = true;
  monaco.languages.register({ id: "rego" });
  monaco.languages.setMonarchTokensProvider("rego", {
    keywords: ["package", "import", "default", "not", "with", "as", "some", "every",
               "in", "if", "contains", "else", "true", "false", "null"],
    builtins: ["input", "data", "count", "sprintf", "concat", "sort", "object",
               "glob", "trim_space", "startswith", "endswith", "split", "sum"],
    tokenizer: {
      root: [
        [/#.*$/, "comment"],
        [/"(?:[^"\\]|\\.)*"/, "string"],
        [/\b\d+(\.\d+)?\b/, "number"],
        [/:=|==|!=|>=|<=|[<>=+\-*/%]/, "operator"],
        [/[a-zA-Z_][\w.]*/, { cases: { "@keywords": "keyword", "@builtins": "type", "@default": "identifier" } }],
      ],
    },
  });
  monaco.languages.setLanguageConfiguration("rego", {
    comments: { lineComment: "#" },
    brackets: [["{", "}"], ["[", "]"], ["(", ")"]],
    autoClosingPairs: [{ open: "{", close: "}" }, { open: "[", close: "]" },
                       { open: "(", close: ")" }, { open: '"', close: '"' }],
  });
}

/* ---- Break glass --------------------------------------------------------
   A person at this organization deciding an override is warranted. Two
   steps, and the split is the point: opening a window is the decision, and
   the member is told at that moment — before an agent has redeemed anything
   and before any data has moved. */
route("breakglass", async (view) => {
  setTitle("Break glass", "");
  const [log, members] = await Promise.all([api("/api/org/break-glass"), api("/api/org/members")]);
  const clause = log.clause || {};
  if (!clause.enabled) {
    view.innerHTML = `<div class="empty">This charter does not permit break-glass access. Members'
      requests over this organization's resources go through their own policy like anyone else's.
      Enable it under <a href="#/charter">Charter</a> if you need it.</div>`;
    return;
  }
  view.innerHTML = `
    <div class="card pad-lg" style="margin-bottom:14px">
      <div class="section-head"><h2>Open a window</h2></div>
      <div class="muted" style="font-size:12.5px;margin-bottom:14px;max-width:74ch">This reaches past a
        member's own policy on ${(clause.resources || []).map(r => `<span class="mono">${esc(r)}</span>`).join(", ")}
        for up to ${esc(clause.max_expires_in)}s. The member is notified the moment you open it, and
        every grant taken against it lands in her record with your name and this reason on it. You
        cannot make it silent, and nothing here reaches a resource this charter does not claim.</div>
      <label class="fld" style="max-width:280px"><div class="lbl">Member</div>
        <select id="bg-owner">${members.map(m => `<option>${esc(m.owner)}</option>`).join("")}</select></label>
      <label class="fld"><div class="lbl">Reason — the member reads this</div>
        <input type="text" id="bg-reason" placeholder="e.g. Regulatory hold: FINRA 4511 records request, ticket OPS-2291"></label>
      <label class="fld" style="max-width:280px"><div class="lbl">Window stays open for (seconds)</div>
        <input type="number" id="bg-window" value="300"></label>
      <button class="btn danger sm" onclick="openGlass()">Open break-glass window</button>
      <div id="bg-result"></div>
    </div>
    ${voucherCard(log)}
    <div class="card pad-lg">
      <div class="section-head"><h2>Every override, ever</h2></div>
      ${(log.grants || []).length ? `<table>
        <thead><tr><th>When</th><th>Member</th><th>Resource</th><th>Reason</th><th>Authorised by</th><th class="r">Used</th></tr></thead>
        <tbody>${log.grants.map(g => `<tr>
          <td class="nowrap">${esc((g.issued || "").replace("T", " ").replace("Z", ""))}</td>
          <td>${esc(g.member)}</td><td class="mono">${esc(g.resource_id)}</td>
          <td class="prose">${esc(g.reason)}</td><td>${esc(g.authorised_by)}</td>
          <td class="r"><span class="chip ${g.spent ? "neg" : ""}">${g.spent ? "spent" : "unused"}</span></td>
        </tr>`).join("")}</tbody></table>`
        : `<div class="muted" style="font-size:12.5px">Nothing has ever been taken this way.</div>`}
    </div>`;
});

function voucherCard(log) {
  const open = log.open_vouchers || [];
  if (!open.length) return "";
  return `<div class="card pad-lg" style="margin-bottom:14px;border-color:var(--warn)">
    <div class="section-head"><h2>Windows open now</h2></div>
    ${open.map(v => `<div class="note warn"><b>${esc(v.owner)}</b> — ${esc(v.reason)}
      · opened by ${esc(v.admin)} · closes in ${esc(v.expires_in)}s
      <div class="thumb">${esc(v.code)}</div></div>`).join("")}
    <div class="muted" style="font-size:12.5px;margin-top:10px">An agent redeems the code above,
      signing with the key the grant will bind to. Unredeemed, a window simply closes.</div>
  </div>`;
}

window.openGlass = async () => {
  const owner = $("#bg-owner").value;
  const reason = $("#bg-reason").value.trim();
  try {
    const r = await api("/api/org/break-glass", { method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ owner, reason, window_s: parseInt($("#bg-window").value, 10) }) });
    $("#bg-result").innerHTML = `<div class="note warn" style="margin-top:14px">
      Window open for ${esc(r.expires_in)}s. ${esc(owner)} has been told.
      <div class="thumb">voucher ${esc(r.voucher)}</div></div>`;
    toast("Window opened", `${owner} was notified before anything moved`, "warn");
  } catch (e) { toast("Not opened", e.message, "warn"); }
};

/* ---- Activity ----------------------------------------------------------- */
route("activity", async (view) => {
  setTitle("Activity", "");
  const rows = await api("/api/org/activity");
  if (!rows.length) { view.innerHTML = `<div class="empty">Nothing has happened yet.</div>`; return; }
  const KIND = {
    "charter.published": "", "member.joined": "pos", "member.left": "warn",
    "member.removed": "warn", "member.compliance": "", "decision": "",
    "break_glass.opened": "neg", "break_glass.granted": "neg",
    "break_glass.spent": "neg", "break_glass.used": "neg",
    "join_code.rotated": "", "notice.failed": "warn",
    "invitation.sent": "", "invitation.declined": "warn",
    "invitation.withdrawn": "", "member.administered": "warn",
    "member.role_set": "pos",
  };
  view.innerHTML = `<div class="card pad-lg"><table>
    <thead><tr><th>Time</th><th>Event</th><th>Details</th></tr></thead>
    <tbody>${rows.map(r => `<tr>
      <td class="thumb">${esc((r.ts || "").replace("T", " ").replace("Z", ""))}</td>
      <td><span class="chip ${KIND[r.kind] || ""}">${esc(r.kind)}</span></td>
      <td class="prose">${esc(Object.entries(r)
        .filter(([k]) => !["ts", "kind"].includes(k))
        .map(([k, v]) => `${k}=${Array.isArray(v) ? v.join("|") : v}`).join("  ·  "))}</td>
    </tr>`).join("")}</tbody></table></div>`;
});

/* ---- Boot --------------------------------------------------------------- */
(async () => {
  const me = await api("/api/me");
  const name = me.name || "Administrator";
  $("#whoName").textContent = name;
  $("#avatar").textContent = name[0].toUpperCase();
  await orgHeader();
  if (!location.hash) location.hash = "#/overview";
  await render();
})();
