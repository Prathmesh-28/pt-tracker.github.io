// Japan applications team tracker. Every change goes through database functions that
// refuse a second claim or application on the same job, so the list can never mislead
// two people into applying twice. This file only shows the state and calls them.
import { createClient } from "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/+esm";

const $ = s => document.querySelector(s);
const app = $("#app"), dlg = $("#dlg"), toastEl = $("#toast");
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const norm = s => String(s || "").toLowerCase().replace(/[^a-z0-9぀-鿿]+/g, "");
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} },
};

const S = {
  sb: null, session: null, me: null,
  jobs: [], apps: new Map(), members: [], resumes: [], events: [], settings: {}, cands: [], refresh: null,
  cand: store.get("jt-cand", "prathmesh"), tab: store.get("jt-tab", "jobs"), shown: 60,
  f: Object.assign({ q: "", status: "open", level: "entry", visa: "ok", kind: "all", fit: "all", priority: false, sort: "smart",
                     kansai: false, jp: "any", jt: "all", area: "any" },
                   store.get("jt-filters", {})),
};

const STATUS = {
  claimed: ["Claimed", "warn"], applied: ["Applied", "ok"], interview: ["Interview", "info"], offer: ["Offer", "ok"],
  rejected: ["Rejected", ""], withdrawn: ["Withdrawn", ""], skipped: ["Skipped", ""],
};
const LEVEL = { intern: "Internship", new_grad: "New grad", entry: "Entry level", mid: "Mid level", senior: "Senior", unstated: "Level not stated" };
const LANG = { english_ok: ["No Japanese needed", "ok"], japanese_plus: ["Japanese a plus", "info"], unstated: ["Japanese not mentioned", "warn"] };
const FIT = { yes: ["Fits 2027 grads", "ok"], likely: ["Likely fits 2027", "warn"], check: ["Check the batch", "info"], no: ["Not for 2027 grads", "bad"] };

// ---------------------------------------------------------------- helpers

function toast(msg, bad = false) {
  toastEl.textContent = msg;
  toastEl.className = "show" + (bad ? " bad" : "");
  clearTimeout(toast.t);
  toast.t = setTimeout(() => (toastEl.className = ""), bad ? 6000 : 3000);
}
const errText = e => (e && (e.message || e.error_description || String(e))) || "Something went wrong";
const who = id => { const m = S.members.find(x => x.user_id === id); return m ? (m.name || m.email) : "someone"; };
const isOwner = () => S.me?.role === "owner" && S.me?.approved;
const claimHours = () => Number(S.settings.claim_hours || 48);
function ago(iso) {
  if (!iso) return "";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}
const fmtDate = d => d ? new Date(d + (d.length === 10 ? "T00:00:00" : "")).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) : "";
function claimExpired(a) {
  return a?.status === "claimed" && a.claimed_at && Date.now() - new Date(a.claimed_at).getTime() > claimHours() * 3600e3;
}
function hoursLeft(a) {
  return Math.max(0, Math.ceil((new Date(a.claimed_at).getTime() + claimHours() * 3600e3 - Date.now()) / 3600e3));
}
// Whose list is showing. Jobs and resumes belong to one person; applications follow the job.
const candOf = j => (j && j.candidate) || "prathmesh";
const person = () => S.cands.find(c => c.id === S.cand) || { id: S.cand, name: S.cand, lives_in_japan: false };
const myJobs = () => S.jobs.filter(j => candOf(j) === S.cand);
const myResumes = () => S.resumes.filter(r => candOf(r) === S.cand);
const jobByKey = key => S.jobs.find(j => j.key === key);
const forMe = key => candOf(jobByKey(key)) === S.cand;
const JP = { none: ["No Japanese needed", "ok"], "a plus": ["Japanese a plus, not required", "ok"],
             "a little": ["A little Japanese is fine", "ok"],
             N5: ["Japanese N5 is enough", "ok"], N4: ["Japanese N4 is enough", "ok"],
             N3: ["Asks N3 (a stretch)", "warn"], "not stated": ["Japanese not mentioned", "warn"] };
// How far a job is, for a list that carries it. The place names stay in the private data.
const AREA = { campus: "Near campus", nankai: "40–60 min away", osaka: "About an hour away",
               remote: "Remote", wakayama: "Farther away", kansai: "Kansai" };
const WITHIN_HOUR = ["campus", "nankai", "osaka", "remote"];
const jobType = j => j.extra?.job_type || (j.extra?.part_time ? "part-time" : "full-time");
// Someone already living in Japan needs no sponsorship for now, so visa terms neither hide nor flag a job.
const needsVisa = () => !person().lives_in_japan;
const isEntry = j => j.kind !== "role" || ["intern", "new_grad", "entry"].includes(j.level) || ["yes", "likely", "check"].includes(j.grad_2027);

async function call(fn, args, ok) {
  const { data, error } = await S.sb.rpc(fn, args);
  if (error) { toast(errText(error), true); return null; }
  if (ok) toast(ok);
  return data ?? true;
}

// ---------------------------------------------------------------- boot

async function config() {
  // On Vercel the function answers; on this Mac a gitignored config.local.json does.
  const local = ["localhost", "127.0.0.1"].includes(location.hostname);
  for (const url of local ? ["config.local.json", "/api/config"] : ["/api/config"]) {
    try {
      const r = await fetch(url, { cache: "no-store" });
      if (r.ok) { const c = await r.json(); if (c.url && c.anonKey) return c; }
    } catch {}
  }
  return null;
}

async function boot() {
  const cfg = await config();
  if (!cfg) {
    app.innerHTML = `<div class="panel"><h2>Not connected yet</h2><p class="muted">Set SUPABASE_URL and SUPABASE_ANON_KEY in the Vercel project, then redeploy.</p></div>`;
    return;
  }
  S.sb = createClient(cfg.url, cfg.anonKey);
  S.sb.auth.onAuthStateChange((event, session) => {
    const changed = (session?.user?.id || null) !== (S.session?.user?.id || null);
    S.session = session;
    if (changed) route();
  });
  const { data } = await S.sb.auth.getSession();
  S.session = data.session;
  route();
}

async function route() {
  renderWho();
  if (!S.session) return renderAuth();
  const name = S.session.user.user_metadata?.name || "";
  const { data, error } = await S.sb.rpc("japan_join", { p_name: name });
  if (error) { app.innerHTML = `<div class="panel"><p class="error">${esc(errText(error))}</p></div>`; return; }
  S.me = data;
  renderWho();
  if (!S.me.approved) return renderPending();
  await loadAll();
  subscribe();
  render();
}

async function fetchAll(table, order) {
  const out = [];
  for (let from = 0; ; from += 1000) {
    let q = S.sb.from(table).select("*").range(from, from + 999);
    if (order) q = q.order(order, { ascending: true });
    const { data, error } = await q;
    if (error) throw error;
    out.push(...data);
    if (data.length < 1000) return out;
  }
}

async function loadAll() {
  app.innerHTML = `<p class="muted">Loading jobs…</p>`;
  try {
    const [jobs, apps, members, resumes, events, settings, cands, refresh] = await Promise.all([
      fetchAll("japan_jobs", "key"), fetchAll("japan_applications", "job_key"),
      S.sb.from("japan_members").select("*").order("created_at"),
      S.sb.from("japan_resumes").select("*").order("created_at"),
      S.sb.from("japan_events").select("*").order("at", { ascending: false }).limit(300),
      S.sb.from("japan_settings").select("*"),
      S.sb.from("japan_candidates").select("*").order("sort"),
      S.sb.from("japan_refreshes").select("*").order("id", { ascending: false }).limit(1),
    ]);
    S.jobs = jobs;
    S.apps = new Map(apps.map(a => [a.job_key, a]));
    S.members = members.data || [];
    S.resumes = resumes.data || [];
    S.events = events.data || [];
    S.settings = Object.fromEntries((settings.data || []).map(r => [r.key, r.value]));
    S.cands = cands.data?.length ? cands.data : [{ id: "prathmesh", name: "Prathmesh", lives_in_japan: false }];
    S.refresh = refresh.data?.[0] || null;
    if (!S.cands.some(c => c.id === S.cand)) S.cand = S.cands[0].id;
  } catch (e) {
    app.innerHTML = `<div class="panel"><p class="error">${esc(errText(e))}</p></div>`;
    throw e;
  }
}

let channel = null, pending = null;
function subscribe() {
  if (channel) S.sb.removeChannel(channel);
  channel = S.sb.channel("japan-team")
    .on("postgres_changes", { event: "*", schema: "public", table: "japan_applications" }, p => {
      if (p.eventType === "DELETE") S.apps.delete(p.old.job_key); else S.apps.set(p.new.job_key, p.new);
      soon();
    })
    .on("postgres_changes", { event: "INSERT", schema: "public", table: "japan_events" }, p => {
      if (!S.events.some(e => e.id === p.new.id)) S.events.unshift(p.new);
      soon();
    })
    .on("postgres_changes", { event: "*", schema: "public", table: "japan_refreshes" }, p => {
      const r = p.new, was = S.refresh;
      if (!r?.id || (was && r.id < was.id)) return;
      S.refresh = r;
      if (r.syncs > (was?.id === r.id ? was.syncs : 0) || (r.status === "done" && was?.status !== "done")) reloadJobs();
      else soon();
    })
    .subscribe();
}
const soon = () => { clearTimeout(pending); pending = setTimeout(backgroundRender, 150); };
// After a refresh syncs a list: the new jobs, without the "Loading" screen or losing your place.
async function reloadJobs() {
  try {
    const [jobs, settings] = await Promise.all([fetchAll("japan_jobs", "key"), S.sb.from("japan_settings").select("*")]);
    S.jobs = jobs;
    S.settings = Object.fromEntries((settings.data || []).map(r => [r.key, r.value]));
  } catch { /* keep the list on screen; the next reload catches up */ }
  soon();
}
window.addEventListener("focus", async () => {
  if (!S.me?.approved) return;
  const { data } = await S.sb.from("japan_jobs").select("key,priority,do_not_apply,owner_note,is_open");
  if (data) { const by = new Map(data.map(j => [j.key, j])); S.jobs.forEach(j => Object.assign(j, by.get(j.key) || {})); soon(); }
});

// ---------------------------------------------------------------- auth screens

function renderWho() {
  const el = $("#who");
  if (!S.session) { el.innerHTML = ""; return; }
  el.innerHTML = `<span>Signed in as <b>${esc(S.me?.name || S.session.user.email)}</b>${S.me ? ` · ${esc(S.me.role)}` : ""}</span>
    <button class="btn" data-act="password">Change password</button>
    <button class="btn" data-act="signout">Sign out</button>`;
}

function renderAuth(mode = "in", message = "") {
  app.innerHTML = `<div class="panel">
    <h2>${mode === "in" ? "Sign in" : "Create an account"}</h2>
    <p class="muted" style="margin:0">${mode === "in" ? "Use the email and password you signed up with." : "The owner approves every new account before it can see the jobs."}</p>
    <form id="auth">
      ${mode === "up" ? `<label for="a-name">Your name</label><input id="a-name" type="text" required autocomplete="name">` : ""}
      <label for="a-email">Email</label><input id="a-email" type="email" required autocomplete="email">
      <label for="a-pass">Password</label><input id="a-pass" type="password" required minlength="8" autocomplete="${mode === "in" ? "current-password" : "new-password"}">
      <div class="row" style="margin-top:16px">
        <button class="btn primary" type="submit">${mode === "in" ? "Sign in" : "Create account"}</button>
        <button class="link" type="button" data-act="authmode" data-mode="${mode === "in" ? "up" : "in"}">${mode === "in" ? "New here? Create an account" : "Have an account? Sign in"}</button>
      </div>
      <p class="error" id="auth-err">${esc(message)}</p>
    </form></div>`;
  $("#auth").addEventListener("submit", async e => {
    e.preventDefault();
    const email = $("#a-email").value.trim(), password = $("#a-pass").value;
    const btn = e.submitter; btn.disabled = true;
    const res = mode === "in"
      ? await S.sb.auth.signInWithPassword({ email, password })
      : await S.sb.auth.signUp({ email, password, options: { data: { name: $("#a-name").value.trim() } } });
    btn.disabled = false;
    if (res.error) { $("#auth-err").textContent = errText(res.error); return; }
    if (mode === "up" && !res.data.session) renderAuth("in", "Check your email to confirm the account, then sign in.");
  });
}

function renderPending() {
  const owner = S.settings.owner_email;
  app.innerHTML = `<div class="panel"><h2>Waiting for approval</h2>
    <p>Thanks, ${esc(S.me.name)}. The owner has to approve your account before you can see the jobs.${owner ? "" : ""}</p>
    <p class="muted">Ask them to open the Team tab. Then reload this page.</p>
    <button class="btn" data-act="reload">Reload</button></div>`;
}

// ---------------------------------------------------------------- main screen

function counts() {
  const c = { open: 0, claimed: 0, applied: 0, interview: 0, offer: 0 };
  for (const j of myJobs()) {
    if (!j.is_open && !S.apps.has(j.key)) continue;
    const a = S.apps.get(j.key);
    if (!a || claimExpired(a)) { if (!j.do_not_apply && j.is_open) c.open++; continue; }
    if (a.status === "claimed") c.claimed++;
    if (["applied", "interview", "offer", "rejected", "withdrawn"].includes(a.status)) c.applied++;
    if (a.status === "interview") c.interview++;
    if (a.status === "offer") c.offer++;
  }
  return c;
}

// The page is three parts: tabs, counters, and the current view. A refresh that comes from
// outside (a friend's change arriving live, the window regaining focus after a file picker)
// updates the tabs and counters but never redraws a view with a form someone is filling in.
const VIEWS = () => ({ jobs: viewJobs, mine: viewMine, activity: viewActivity, resumes: viewResumes, team: viewTeam, settings: viewSettings });
const FORM_VIEWS = ["resumes", "settings"];

function render() {
  if (!$("#view")) app.innerHTML = `<div class="cands" id="candbar"></div><nav class="tabs" role="tablist" id="tabsbar"></nav><section class="stats" id="statsbar"></section><div id="view"></div>`;
  renderChrome();
  VIEWS()[S.tab]();
}

// The Refresh button. The searches run on Prathmesh's Mac (Japan/daily.sh): the button queues a
// refresh, the Mac starts it within a minute, and its progress arrives here live.
function refreshBox() {
  const r = S.refresh, at = t => new Date(t).toLocaleTimeString("en-GB", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit" });
  const busy = r && ["queued", "running"].includes(r.status);
  let line;
  if (r?.status === "queued") line = `Asked ${ago(r.requested_at)} by ${esc(who(r.requested_by))}. Starts within a minute while Prathmesh's Mac is on.`;
  else if (r?.status === "running") line = `${esc(r.step || "Starting")} · started ${at(r.started_at)} IST${r.trigger === "schedule" ? " (the 8:00 run)" : ""}`;
  else if (r?.status === "done") line = `Refreshed ${at(r.finished_at)} IST · ${esc(r.summary)}`;
  else if (r?.status === "failed") line = `Last refresh stopped partway (${at(r.finished_at || r.updated_at)} IST). ${esc(r.summary)}`;
  else line = "Every morning at 8:00 IST, or now:";
  return `<div class="refresh" aria-live="polite"><span class="muted">${line}</span>
    <button class="btn ${busy ? "" : "primary"}" data-act="refresh" ${busy ? "disabled" : ""}
      title="Pulls every company board now. LinkedIn and Indeed are searched at most every 4 hours and part-time searches every hour, so they don't block us.">
      ${r?.status === "running" ? "Refreshing…" : r?.status === "queued" ? "Queued…" : "↻ Refresh jobs"}</button></div>`;
}

function renderChrome() {
  const mine = [...S.apps.values()].filter(a => forMe(a.job_key) && (a.claimed_by === S.me.user_id || a.applied_by === S.me.user_id)).length;
  const waiting = S.members.filter(m => !m.approved).length;
  $("#candbar").innerHTML = `<span class="muted">Applying for</span>${S.cands.map(c =>
    `<button class="pill" data-act="cand" data-cand="${esc(c.id)}" aria-pressed="${c.id === S.cand}">${esc(c.name)}<span class="n">${
      S.jobs.filter(j => candOf(j) === c.id && j.is_open).length}</span></button>`).join("")}${refreshBox()}`;
  const tabs = [["jobs", "Jobs", myJobs().filter(j => j.is_open).length], ["mine", "Mine", mine],
                ["activity", "Activity", ""], ["resumes", "Resumes", myResumes().filter(r => r.active).length],
                ["team", "Team", isOwner() && waiting ? `${waiting} waiting` : S.members.filter(m => m.approved).length]];
  if (isOwner()) tabs.push(["settings", "Settings", ""]);
  if (!tabs.some(t => t[0] === S.tab)) S.tab = "jobs";
  const c = counts();
  $("#tabsbar").innerHTML = tabs.map(([k, label, n]) =>
    `<button role="tab" aria-selected="${S.tab === k}" data-act="tab" data-tab="${k}">${label}${n !== "" ? `<span class="n">${esc(n)}</span>` : ""}</button>`).join("");
  $("#statsbar").innerHTML = `
    <div><b>${c.open}</b><span>Open to claim</span></div><div><b>${c.claimed}</b><span>Claimed, not sent</span></div>
    <div><b>${c.applied}</b><span>Applications sent</span></div><div><b>${c.interview}</b><span>Interviews</span></div>
    <div><b>${c.offer}</b><span>Offers</span></div>`;
}

function backgroundRender() {
  if (!S.me?.approved || !$("#view")) return;
  renderChrome();
  if (FORM_VIEWS.includes(S.tab)) return;
  const active = document.activeElement, keep = active && active.id === "f-q" ? [active.selectionStart, active.selectionEnd] : null;
  VIEWS()[S.tab]();
  if (keep) { const q = $("#f-q"); if (q) { q.focus(); q.setSelectionRange(...keep); } }
}

// ---------------------------------------------------------------- jobs

function matches(j) {
  const f = S.f, a = S.apps.get(j.key), expired = claimExpired(a);
  const st = !a || expired ? "open" : a.status;
  if (f.status === "open" && (st !== "open" || !j.is_open || j.do_not_apply)) return false;
  if (f.status === "claimed" && st !== "claimed") return false;
  if (f.status === "applied" && !["applied", "interview", "offer", "rejected", "withdrawn"].includes(st)) return false;
  if (f.status === "skipped" && st !== "skipped") return false;
  if (f.status !== "all" && f.status !== "applied" && !j.is_open && st === "open") return false;
  if (f.level === "entry" && !isEntry(j)) return false;
  if (needsVisa() && f.visa === "ok" && (j.visa === "no" || j.residency)) return false;
  if (needsVisa() && f.visa === "yes" && j.visa !== "yes") return false;
  if (hasExtras()) {
    if (f.jt !== "all" && jobType(j) !== f.jt && j.kind !== "manual") return false;
    if (f.area === "campus" && j.extra?.area !== "campus") return false;
    if (f.area === "hour" && !WITHIN_HOUR.includes(j.extra?.area)) return false;
    if (f.area === "remote" && j.extra?.area !== "remote") return false;
    if (f.jp === "n4" && !["none", "a plus", "a little", "N5", "N4"].includes(j.extra?.japanese)) return false;
    if (f.jp === "good" && j.extra?.fit !== "good") return false;
  }
  if (f.kind !== "all" && j.kind !== f.kind) return false;
  if (!hasExtras() && f.fit === "fits" && !["yes", "likely"].includes(j.grad_2027) && j.kind !== "program") return false;
  if (f.priority && !j.priority) return false;
  if (f.q) {
    const hay = `${j.title} ${j.company} ${j.location} ${j.track}`.toLowerCase();
    if (!f.q.toLowerCase().split(/\s+/).every(w => hay.includes(w))) return false;
  }
  return true;
}

const hasExtras = () => myJobs().some(j => j.extra && j.extra.japanese);

function sorted(list) {
  const by = S.f.sort;
  const deadline = j => j.deadline || "9999";
  if (by === "company") return list.sort((a, b) => a.company.localeCompare(b.company) || a.title.localeCompare(b.title));
  if (by === "newest") return list.sort((a, b) => (b.created_at || "").localeCompare(a.created_at || "") || (b.posted || "").localeCompare(a.posted || ""));
  const rank = j => j.extra?.rank ?? 1e9;
  return list.sort((a, b) => (b.priority - a.priority) || (a.kind === "program" ? -1 : 0) - (b.kind === "program" ? -1 : 0)
    || rank(a) - rank(b) || deadline(a).localeCompare(deadline(b)) || (b.visa === "yes") - (a.visa === "yes") || (b.posted || "").localeCompare(a.posted || ""));
}

function jobCard(j) {
  const a = S.apps.get(j.key), expired = claimExpired(a), me = S.me.user_id;
  const badges = [];
  if (j.priority) badges.push(`<span class="b warn">★ Owner's pick</span>`);
  if (j.do_not_apply) badges.push(`<span class="b bad">Do not apply</span>`);
  if (!j.is_open) badges.push(`<span class="b">Closed</span>`);
  else if (j.created_at && Date.now() - new Date(j.created_at).getTime() < 36 * 3600e3) badges.push(`<span class="b ok">New</span>`);
  if (j.kind === "program") badges.push(`<span class="b info">Program</span>`);
  if (j.kind === "manual") badges.push(`<span class="b info">Added by the team</span>`);
  if (LEVEL[j.level] && jobType(j) !== "part-time") badges.push(`<span class="b">${LEVEL[j.level]}${j.min_years != null ? ` · ${j.min_years}+ yrs` : ""}</span>`);
  if (j.extra?.japanese && JP[j.extra.japanese]) badges.push(`<span class="b ${JP[j.extra.japanese][1]}">${JP[j.extra.japanese][0]}</span>`);
  else if (LANG[j.language]) badges.push(`<span class="b ${LANG[j.language][1]}">${LANG[j.language][0]}</span>`);
  if (j.extra?.job_type === "part-time" || j.extra?.part_time) badges.push(`<span class="b info">Part-time</span>`);
  if (j.extra?.wage) badges.push(`<span class="b">${esc(j.extra.wage)}</span>`);
  if (AREA[j.extra?.area]) badges.push(`<span class="b ${j.extra.area === "campus" ? "ok" : "info"}">${esc(j.extra.area_label || AREA[j.extra.area])}</span>`);
  else if (j.extra?.kansai) badges.push(`<span class="b info">Kansai</span>`);
  if (j.extra?.foreigners) badges.push(`<span class="b ok">Foreigners work here</span>`);
  if (j.extra?.students) badges.push(`<span class="b info">Students welcome</span>`);
  if (j.extra?.native_english) badges.push(`<span class="b warn">Asks for native English speakers</span>`);
  if (j.extra?.ssw) badges.push(`<span class="b info">Specified Skilled Worker route</span>`);
  if (j.visa === "yes") badges.push(`<span class="b ok">Sponsors visa</span>`);
  if (j.visa === "no" && needsVisa()) badges.push(`<span class="b bad">No visa sponsorship</span>`);
  if (j.residency) badges.push(person().lives_in_japan ? `<span class="b ok">Must live in Japan (does)</span>` : `<span class="b bad">Must live in Japan</span>`);
  if (FIT[j.grad_2027]) badges.push(`<span class="b ${FIT[j.grad_2027][1]}">${FIT[j.grad_2027][0]}</span>`);
  if (j.deadline) badges.push(`<span class="b warn">Closes ${fmtDate(j.deadline)}</span>`);

  let status = "", actions = [];
  const k = esc(j.key);
  if (!a || expired) {
    status = expired ? `<div class="status">Claim by <b>${esc(who(a.claimed_by))}</b> expired; anyone can take it.</div>` : "";
    if (j.is_open && !j.do_not_apply) {
      actions.push(`<button class="btn primary" data-act="claim" data-key="${k}">Claim</button>`,
                   `<button class="btn" data-act="apply" data-key="${k}">Applied already</button>`,
                   `<button class="btn" data-act="skip" data-key="${k}">Not a fit</button>`);
    }
  } else {
    const [label, cls] = STATUS[a.status] || [a.status, ""];
    const person = a.applied_by || a.claimed_by;
    const resume = S.resumes.find(r => r.id === a.resume_id);
    let line = `<span class="b ${cls}">${label}</span> by <b>${esc(who(person))}</b> · ${ago(a.applied_at || a.claimed_at)}`;
    if (a.status === "claimed") line += ` · ${hoursLeft(a)}h before the claim lapses`;
    if (resume) line += ` · resume: <b>${esc(resume.label)}</b>`;
    if (a.applied_with) line += ` · with ${esc(a.applied_with)}`;
    if (a.note) line += `<br><span class="muted">${esc(a.note)}</span>`;
    status = `<div class="status">${line}</div>`;
    const mineNow = person === me;
    if (a.status === "claimed" && (mineNow || isOwner())) {
      actions.push(`<button class="btn primary" data-act="apply" data-key="${k}">Mark applied</button>`,
                   `<button class="btn" data-act="release" data-key="${k}">Release</button>`);
    }
    if (["applied", "interview", "offer"].includes(a.status) && (mineNow || isOwner())) {
      actions.push(`<select class="btn" data-act="setstatus" data-key="${k}" aria-label="Update status">
        <option value="">Update…</option>${["interview", "offer", "rejected", "withdrawn"].filter(s => s !== a.status)
          .map(s => `<option value="${s}">${STATUS[s][0]}</option>`).join("")}</select>`);
    }
    if (a.status === "skipped" && (mineNow || isOwner())) actions.push(`<button class="btn" data-act="release" data-key="${k}">Undo skip</button>`);
    if (isOwner() && !["claimed", "skipped"].includes(a.status)) actions.push(`<button class="btn danger" data-act="reset" data-key="${k}">Reset</button>`);
  }
  actions.push(`<button class="btn" data-act="note" data-key="${k}">Note</button>`,
               `<button class="btn" data-act="history" data-key="${k}">History</button>`);
  if (isOwner()) {
    actions.push(`<button class="btn" data-act="priority" data-key="${k}">${j.priority ? "Unpick" : "★ Pick"}</button>`,
                 `<button class="btn danger" data-act="dna" data-key="${k}">${j.do_not_apply ? "Allow" : "Do not apply"}</button>`);
  }
  const done = a && !expired && a.status !== "claimed";
  return `<article class="item ${done ? "done" : ""}">
    <div>
      <h3><a href="${esc(j.url)}" target="_blank" rel="noopener">${esc(j.title)}</a></h3>
      <div class="meta"><b>${esc(j.company)}</b>${j.location ? `<span>${esc(j.location)}</span>` : ""}${j.posted ? `<span>Posted ${fmtDate(j.posted)}</span>` : ""}${j.via ? `<span>via ${esc(j.via)}</span>` : j.source ? `<span>${esc(j.source)}</span>` : ""}</div>
      <div class="badges">${badges.join("")}</div>
      ${j.owner_note ? `<p class="muted" style="margin:6px 0 0;font-size:13px"><b>Owner:</b> ${esc(j.owner_note)}</p>` : ""}
    </div>
    <div class="actions">${actions.join("")}</div>
    ${status}
  </article>`;
}

function listHead() {
  let r = null;
  try { r = JSON.parse(S.settings[`refreshed_${S.cand}`] || "null"); } catch {}
  const lines = [];
  if (r?.at) {
    const when = new Date(r.at).toLocaleString("en-GB", { timeZone: "Asia/Kolkata", day: "numeric", month: "short",
                                                          hour: "2-digit", minute: "2-digit", hour12: false });
    const bits = [`This list was last synced ${when} IST; it refreshes every morning at 8:00 IST and on Refresh`];
    if (r.held) bits.push(`${r.held} jobs missing from the last search were kept open, in case a source was down`);
    lines.push(bits.join(" · "));
  }
  if (hasExtras() && S.f.jt !== "full-time") {
    lines.push(`Part-time on a student visa: up to 28 hours a week in term and 8 hours a day in the long holidays, once the
      permission to work (資格外活動許可) is on the residence card. Hostess and snack bars, pachinko, mahjong and game
      centres are off limits for students, and contractor gigs need a separate permission, so they are left out.`);
  }
  return lines.length ? `<div class="listhead">${lines.map(l => `<p>${esc(l)}</p>`).join("")}</div>` : "";
}

function viewJobs() {
  const f = S.f;
  const list = sorted(myJobs().filter(matches));
  $("#view").innerHTML = `
    <div class="controls">
      <input type="search" id="f-q" placeholder="Search title, company or city" value="${esc(f.q)}" aria-label="Search">
      <select id="f-status" aria-label="Status">
        ${[["open", "Open to claim"], ["claimed", "Claimed"], ["applied", "Applied and later"], ["skipped", "Skipped"], ["all", "Everything"]]
          .map(([v, l]) => `<option value="${v}" ${f.status === v ? "selected" : ""}>${l}</option>`).join("")}
      </select>
      <select id="f-level" aria-label="Level">
        <option value="entry" ${f.level === "entry" ? "selected" : ""}>Entry level, new grad, programs</option>
        <option value="all" ${f.level === "all" ? "selected" : ""}>Any level</option>
      </select>
      ${needsVisa() ? `<select id="f-visa" aria-label="Visa">
        <option value="ok" ${f.visa === "ok" ? "selected" : ""}>Visa not ruled out</option>
        <option value="yes" ${f.visa === "yes" ? "selected" : ""}>States visa sponsorship</option>
        <option value="all" ${f.visa === "all" ? "selected" : ""}>Any visa situation</option>
      </select>` : ""}
      <select id="f-kind" aria-label="Kind">
        ${[["all", "Roles and programs"], ["program", "Programs"], ["role", "Roles"], ["manual", "Added by the team"]]
          .map(([v, l]) => `<option value="${v}" ${f.kind === v ? "selected" : ""}>${l}</option>`).join("")}
      </select>
      ${hasExtras() ? "" : `<select id="f-fit" aria-label="Batch">
        <option value="all" ${f.fit === "all" ? "selected" : ""}>Any batch</option>
        <option value="fits" ${f.fit === "fits" ? "selected" : ""}>Dates fit 2027 grads</option>
      </select>`}
      <select id="f-sort" aria-label="Sort">
        ${[["smart", "Picks and deadlines first"], ["newest", "Newest"], ["company", "Company"]]
          .map(([v, l]) => `<option value="${v}" ${f.sort === v ? "selected" : ""}>${l}</option>`).join("")}
      </select>
      ${hasExtras() ? `<select id="f-jt" aria-label="Part-time or full-time">
        ${[["all", "Part-time and full-time"], ["part-time", "Part-time (student visa)"], ["full-time", "Full-time (after graduating)"]]
          .map(([v, l]) => `<option value="${v}" ${f.jt === v ? "selected" : ""}>${l}</option>`).join("")}
      </select>
      <select id="f-area" aria-label="Where">
        ${[["any", "Anywhere"], ["campus", "Near campus"], ["hour", "Within an hour, or remote"], ["remote", "Remote"]]
          .map(([v, l]) => `<option value="${v}" ${f.area === v ? "selected" : ""}>${l}</option>`).join("")}
      </select>
      <select id="f-jp" aria-label="Japanese">
        ${[["any", "Any Japanese level"], ["good", "Good fits: little Japanese, or foreigners work there"], ["n4", "States N4 or less, or none"]]
          .map(([v, l]) => `<option value="${v}" ${f.jp === v ? "selected" : ""}>${l}</option>`).join("")}
      </select>` : ""}
      <label><input type="checkbox" id="f-priority" ${f.priority ? "checked" : ""}> Owner's picks only</label>
      <button class="btn" data-act="addjob">+ Add a job</button>
      <span class="count">${list.length} shown</span>
    </div>
    ${listHead()}
    <div class="list">${list.length ? list.slice(0, S.shown).map(jobCard).join("") : `<div class="empty">No jobs match these filters.</div>`}</div>
    ${list.length > S.shown ? `<button class="btn more" data-act="more">Show more (${list.length - S.shown} left)</button>` : ""}`;
  const bind = (id, key, ev = "change", get = el => el.value) => $(id)?.addEventListener(ev, e => {
    S.f[key] = get(e.target); S.shown = 60; store.set("jt-filters", S.f);
    if (key === "q") { clearTimeout(viewJobs.t); viewJobs.t = setTimeout(() => { viewJobs(); const q = $("#f-q"); q.focus(); q.setSelectionRange(q.value.length, q.value.length); }, 200); }
    else viewJobs();
  });
  bind("#f-q", "q", "input");
  ["status", "level", "visa", "kind", "fit", "sort"].forEach(k => bind(`#f-${k}`, k));
  bind("#f-priority", "priority", "change", el => el.checked);
  ["jt", "area", "jp"].forEach(k => bind(`#f-${k}`, k));
}

// ---------------------------------------------------------------- other tabs

function viewMine() {
  const me = S.me.user_id;
  const jobsBy = new Map(S.jobs.map(j => [j.key, j]));
  const mine = [...S.apps.values()].filter(a => forMe(a.job_key) && (a.claimed_by === me || a.applied_by === me))
    .sort((x, y) => (y.updated_at || "").localeCompare(x.updated_at || ""));
  const claimed = mine.filter(a => a.status === "claimed"), rest = mine.filter(a => a.status !== "claimed");
  const block = (title, list, hint) => `<h2 style="margin-top:8px">${title}</h2><p class="muted" style="margin:0 0 10px">${hint}</p>
    <div class="list">${list.length ? list.map(a => jobsBy.get(a.job_key)).filter(Boolean).map(jobCard).join("") : `<div class="empty">Nothing here.</div>`}</div>`;
  $("#view").innerHTML = block("Claimed by you", claimed, `Apply or release these; a claim lapses after ${claimHours()} hours.`)
    + `<div style="height:24px"></div>` + block("Your applications", rest, "Update them when you hear back.");
}

function eventLine(e) {
  const j = S.jobs.find(x => x.key === e.job_key);
  const what = { claimed: "claimed", applied: "applied to", released: "released", skipped: "skipped", interview: "got an interview for",
                 offer: "got an offer for", rejected: "was rejected for", withdrawn: "withdrew from", note: "left a note on",
                 added: "added", reset: "reset" }[e.action] || e.action;
  const job = j ? `<b>${esc(j.title)}</b> at ${esc(j.company)}` : esc(e.job_key || "");
  const extra = e.detail ? (e.action === "applied" ? ` with the <b>${esc(e.detail)}</b> resume` : `: ${esc(e.detail)}`) : "";
  return `<li><b>${esc(who(e.actor))}</b> ${what} ${job}${extra}<time datetime="${esc(e.at)}">${ago(e.at)}</time></li>`;
}

function viewActivity() {
  const events = S.events.filter(e => forMe(e.job_key));
  $("#view").innerHTML = `<ul class="feed">${events.length ? events.slice(0, 200).map(eventLine).join("") : `<li class="muted">No activity yet for ${esc(person().name)}.</li>`}</ul>`;
}

function viewResumes() {
  const used = id => [...S.apps.values()].filter(a => a.resume_id === id).length;
  const rows = myResumes().map(r => `<tr>
    <td><b>${esc(r.label)}</b>${r.notes ? `<br><span class="muted">${esc(r.notes)}</span>` : ""}</td>
    <td>${esc(r.file_name || r.file_path)}</td><td>${r.active ? "Active" : "Retired"}</td><td class="mono">${used(r.id)}</td>
    <td><div class="row"><button class="btn" data-act="download" data-id="${esc(r.id)}">Download</button>
      ${isOwner() ? `<button class="btn" data-act="togglecv" data-id="${esc(r.id)}">${r.active ? "Retire" : "Reactivate"}</button>
      <button class="btn danger" data-act="deletecv" data-id="${esc(r.id)}">Delete</button>` : ""}</div></td></tr>`).join("");
  $("#view").innerHTML = `
    <p class="muted">${esc(person().name)}'s resumes. Pick the one that fits the role when you mark an application. Retired resumes stay on old applications but can't be picked.</p>
    <div class="tablewrap"><table><thead><tr><th>Resume</th><th>File</th><th>State</th><th>Used</th><th></th></tr></thead>
      <tbody>${rows || `<tr><td colspan="5" class="muted">No resumes yet.${isOwner() ? " Upload the first one below." : " The owner adds them."}</td></tr>`}</tbody></table></div>
    ${isOwner() ? `<form id="cv-form" class="panel" style="margin-top:16px">
      <h2>Add resumes for ${esc(person().name)}</h2>
      <label for="cv-file">Files (PDF or Word); pick one or several</label>
      <input id="cv-file" type="file" multiple required accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document">
      <div id="cv-single">
        <label for="cv-label">Name it for the team</label><input id="cv-label" type="text" placeholder="The file's name, unless you change it">
        <label for="cv-notes">When to use it</label><input id="cv-notes" type="text" placeholder="The file's name, unless you change it">
      </div>
      <p class="muted" id="cv-many" hidden style="margin:10px 0 0">Each file is added under its own name.</p>
      <div class="row" style="margin-top:14px"><button class="btn primary" type="submit">Upload</button></div>
      <p class="error" id="cv-err"></p></form>` : ""}`;
  const baseName = f => f.name.replace(/\.[^.]+$/, "");
  const fileInput = $("#cv-file");
  fileInput?.addEventListener("change", () => {
    const files = [...fileInput.files];
    $("#cv-single").hidden = files.length > 1;
    $("#cv-many").hidden = files.length <= 1;
    if (files.length === 1) {
      // Fill both fields with the file's name; whatever was auto-filled before is replaced.
      for (const id of ["#cv-label", "#cv-notes"]) {
        const el = $(id);
        if (!el.value || el.dataset.auto === "1") { el.value = baseName(files[0]); el.dataset.auto = "1"; }
      }
    }
  });
  for (const id of ["#cv-label", "#cv-notes"]) $(id)?.addEventListener("input", e => { e.target.dataset.auto = "0"; });
  $("#cv-form")?.addEventListener("submit", async e => {
    e.preventDefault();
    const files = [...fileInput.files];
    if (!files.length) { $("#cv-err").textContent = "Choose a file first."; return; }
    const btn = e.submitter; btn.disabled = true; $("#cv-err").textContent = "";
    let added = 0;
    for (const [i, file] of files.entries()) {
      const single = files.length === 1;
      const label = (single && $("#cv-label").value.trim()) || baseName(file);
      const notes = (single && $("#cv-notes").value.trim()) || baseName(file);
      const path = `${Date.now()}-${i}-${file.name.replace(/[^\w.\-]+/g, "_")}`;
      const up = await S.sb.storage.from("japan-resumes").upload(path, file, { contentType: file.type || "application/octet-stream" });
      if (up.error) { $("#cv-err").textContent = `${file.name}: ${errText(up.error)}`; break; }
      const ins = await S.sb.from("japan_resumes").insert({ label, notes, file_path: path, file_name: file.name, candidate: S.cand }).select().single();
      if (ins.error) { $("#cv-err").textContent = `${file.name}: ${errText(ins.error)}`; await S.sb.storage.from("japan-resumes").remove([path]); break; }
      S.resumes.push(ins.data); added++;
    }
    btn.disabled = false;
    if (added) { toast(added === 1 ? `Added ${S.resumes.at(-1).label}` : `Added ${added} resumes`); render(); }
  });
}

function viewTeam() {
  const tally = id => [...S.apps.values()].filter(a => a.applied_by === id && a.status !== "claimed" && a.status !== "skipped").length;
  const rows = S.members.map(m => `<tr>
    <td><b>${esc(m.name || "")}</b><br><span class="muted">${esc(m.email)}</span></td><td>${esc(m.role)}</td>
    <td>${m.approved ? "Approved" : `<span class="b warn">Waiting</span>`}</td><td class="mono">${tally(m.user_id)}</td>
    <td>${isOwner() && m.user_id !== S.me.user_id ? `<div class="row">
      <button class="btn ${m.approved ? "" : "primary"}" data-act="approve" data-id="${esc(m.user_id)}" data-on="${!m.approved}">${m.approved ? "Revoke" : "Approve"}</button>
      <button class="btn" data-act="role" data-id="${esc(m.user_id)}" data-role="${m.role === "owner" ? "helper" : "owner"}">${m.role === "owner" ? "Make helper" : "Make owner"}</button>
      <button class="btn danger" data-act="remove" data-id="${esc(m.user_id)}">Remove</button></div>` : ""}</td></tr>`).join("");
  $("#view").innerHTML = `<p class="muted">${isOwner() ? "Approve people you know. Revoking access hides everything from them at once; their past applications stay." : "Everyone helping, and how many applications each has sent."}</p>
    <div class="tablewrap"><table><thead><tr><th>Person</th><th>Role</th><th>Access</th><th>Sent</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>
    ${isOwner() ? `<p class="muted" style="margin-top:12px">Share the site link with your friends. They create an account and appear here as Waiting.</p>` : ""}`;
}

function viewSettings() {
  $("#view").innerHTML = `<form id="set-form" class="panel">
    <h2>Settings</h2>
    <label for="set-hours">Hours before an unused claim lapses</label>
    <input id="set-hours" type="number" min="1" max="720" value="${esc(claimHours())}">
    <div class="row" style="margin-top:14px"><button class="btn primary" type="submit">Save</button>
      <button class="btn" type="button" data-act="export">Export applications (CSV)</button></div>
  </form>
  <form id="cand-form" class="panel" style="margin-top:16px">
    <h2>People we apply for</h2>
    <p class="muted" style="margin:0">Each has their own jobs, resumes and applications. Switch at the top of the page.</p>
    <ul style="margin:10px 0 0;padding-left:18px">${S.cands.map(c => `<li><b>${esc(c.name)}</b>${c.lives_in_japan ? " · lives in Japan" : ""}${c.notes ? `<br><span class="muted">${esc(c.notes)}</span>` : ""}</li>`).join("")}</ul>
    <label for="cand-name">Add a person</label><input id="cand-name" type="text" placeholder="Name" required>
    <label><input type="checkbox" id="cand-japan"> Already lives in Japan</label>
    <div class="row" style="margin-top:12px"><button class="btn" type="submit">Add</button></div>
  </form>`;
  $("#cand-form").addEventListener("submit", async e => {
    e.preventDefault();
    const name = $("#cand-name").value.trim();
    const id = name.toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
    if (!id) return toast("Use letters or numbers in the name", true);
    const { data, error } = await S.sb.from("japan_candidates")
      .insert({ id, name, lives_in_japan: $("#cand-japan").checked, sort: S.cands.length + 1 }).select().single();
    if (error) return toast(errText(error), true);
    S.cands.push(data); toast(`Added ${name}`); render();
  });
  $("#set-form").addEventListener("submit", async e => {
    e.preventDefault();
    const v = String(Math.max(1, Math.min(720, Number($("#set-hours").value) || 48)));
    const { error } = await S.sb.from("japan_settings").update({ value: v }).eq("key", "claim_hours");
    if (error) return toast(errText(error), true);
    S.settings.claim_hours = v; toast("Saved");
  });
}

// ---------------------------------------------------------------- dialogs

function openDialog(html, onSubmit) {
  dlg.innerHTML = `<form method="dialog" class="dlg">${html}</form>`;
  const form = dlg.querySelector("form");
  form.addEventListener("submit", async e => {
    if (e.submitter?.value === "cancel") return;
    e.preventDefault();
    e.submitter && (e.submitter.disabled = true);
    const keep = await onSubmit(form);
    if (e.submitter) e.submitter.disabled = false;
    if (keep !== false) dlg.close();
  });
  dlg.showModal();
}

function sameCompany(j) {
  const c = norm(j.company);
  return S.jobs.filter(x => x.key !== j.key && candOf(x) === candOf(j) && norm(x.company) === c)
    .map(x => [x, S.apps.get(x.key)]).filter(([, a]) => a && a.status !== "skipped" && !claimExpired(a));
}

function warnSameCompany(j) {
  const others = sameCompany(j);
  if (!others.length) return "";
  return `<div class="warnbox"><b>${others.length} other application${others.length > 1 ? "s" : ""} at ${esc(j.company)}:</b><br>${
    others.slice(0, 5).map(([x, a]) => `${esc(x.title)}: ${esc(STATUS[a.status]?.[0] || a.status)} by ${esc(who(a.applied_by || a.claimed_by))}`).join("<br>")}
    <br>Some companies count several applications against you. Check with the group first.</div>`;
}

function applyDialog(j) {
  const active = S.resumes.filter(r => r.active && candOf(r) === candOf(j));
  if (!active.length) return toast(`No resumes for ${S.cands.find(c => c.id === candOf(j))?.name || "this person"} yet. The owner adds them in the Resumes tab.`, true);
  openDialog(`<h2>Mark as applied</h2>
    <p class="muted" style="margin:0">${esc(j.title)} at ${esc(j.company)}</p>
    ${warnSameCompany(j)}
    <label>Which resume did you send?</label>
    ${active.map((r, i) => `<label class="choice"><input type="radio" name="cv" value="${esc(r.id)}" ${i === 0 ? "checked" : ""}>
      <span><b>${esc(r.label)}</b>${r.notes ? `<br><span class="muted">${esc(r.notes)}</span>` : ""}<br><button class="link" type="button" data-act="download" data-id="${esc(r.id)}">Download</button></span></label>`).join("")}
    <label for="ap-with">Applied with (email or account used)</label><input id="ap-with" type="text" placeholder="e.g. his Gmail, or LinkedIn Easy Apply">
    <label for="ap-note">Note for the group</label><textarea id="ap-note" placeholder="Anything the next person should know"></textarea>
    <div class="foot"><button class="btn" value="cancel">Cancel</button><button class="btn primary" type="submit">Mark applied</button></div>`,
    async form => {
      const cv = form.querySelector("input[name=cv]:checked")?.value;
      const ok = await call("japan_apply", { p_job: j.key, p_resume: cv, p_with: $("#ap-with").value.trim(), p_note: $("#ap-note").value.trim() },
                            "Marked as applied. Thank you!");
      if (ok) { S.apps.set(j.key, ok); render(); }
      return !!ok || false;
    });
}

async function historyDialog(j) {
  const { data, error } = await S.sb.from("japan_events").select("*").eq("job_key", j.key).order("at", { ascending: false });
  if (error) return toast(errText(error), true);
  openDialog(`<h2>History</h2><p class="muted" style="margin:0 0 10px">${esc(j.title)} at ${esc(j.company)}</p>
    <ul class="feed">${data.length ? data.map(eventLine).join("") : `<li class="muted">Nothing yet.</li>`}</ul>
    ${j.eligibility ? `<p class="muted" style="font-size:13px"><b>Batch:</b> ${esc(j.eligibility)}</p>` : ""}
    <div class="foot"><button class="btn" value="cancel">Close</button></div>`, () => true);
}

function textDialog(title, label, placeholder, onSave) {
  openDialog(`<h2>${esc(title)}</h2><label for="t-text">${esc(label)}</label><textarea id="t-text" placeholder="${esc(placeholder)}" required></textarea>
    <div class="foot"><button class="btn" value="cancel">Cancel</button><button class="btn primary" type="submit">Save</button></div>`,
    async () => onSave($("#t-text").value.trim()));
}

function addJobDialog() {
  openDialog(`<h2>Add a job to ${esc(person().name)}'s list</h2>
    <p class="muted" style="margin:0">Found elsewhere? Add it so nobody applies to it twice.</p>
    <label for="nj-company">Company</label><input id="nj-company" type="text" required>
    <label for="nj-title">Role</label><input id="nj-title" type="text" required>
    <label for="nj-url">Link</label><input id="nj-url" type="url" placeholder="https://">
    <label for="nj-loc">City</label><input id="nj-loc" type="text" placeholder="Tokyo">
    <label for="nj-note">Note</label><input id="nj-note" type="text">
    <div class="foot"><button class="btn" value="cancel">Cancel</button><button class="btn primary" type="submit">Add</button></div>`,
    async () => {
      const job = await call("japan_add_job", { p_company: $("#nj-company").value, p_title: $("#nj-title").value, p_url: $("#nj-url").value,
                                               p_location: $("#nj-loc").value, p_note: $("#nj-note").value, p_candidate: S.cand }, "Added to the list");
      if (job) { S.jobs.push(job); render(); }
      return !!job || false;
    });
}

// ---------------------------------------------------------------- actions

const jobOf = key => S.jobs.find(j => j.key === key);

async function download(id) {
  const r = S.resumes.find(x => x.id === id);
  if (!r) return;
  const { data, error } = await S.sb.storage.from("japan-resumes").createSignedUrl(r.file_path, 300, { download: r.file_name || true });
  if (error) return toast(errText(error), true);
  window.open(data.signedUrl, "_blank", "noopener");
}

function exportCsv() {
  const head = ["for", "company", "title", "status", "by", "resume", "applied_with", "applied_at", "note", "url"];
  const rows = [...S.apps.values()].map(a => {
    const j = jobOf(a.job_key) || {}, r = S.resumes.find(x => x.id === a.resume_id);
    return [S.cands.find(c => c.id === candOf(j))?.name, j.company, j.title, a.status, who(a.applied_by || a.claimed_by), r?.label, a.applied_with, a.applied_at || a.claimed_at, a.note, j.url];
  });
  const csv = [head, ...rows].map(r => r.map(v => `"${String(v ?? "").replace(/"/g, '""')}"`).join(",")).join("\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  a.download = `japan-applications-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
}

document.addEventListener("click", async e => {
  const el = e.target.closest("[data-act]");
  if (!el || el.tagName === "SELECT") return;
  const act = el.dataset.act, key = el.dataset.key, j = key && jobOf(key);
  switch (act) {
    case "signout": await S.sb.auth.signOut(); S.me = null; S.session = null; if (channel) S.sb.removeChannel(channel); route(); break;
    case "authmode": renderAuth(el.dataset.mode); break;
    case "password": openDialog(`<h2>Change password</h2>
      <label for="pw-1">New password</label><input id="pw-1" type="password" minlength="8" required autocomplete="new-password">
      <label for="pw-2">Again</label><input id="pw-2" type="password" minlength="8" required autocomplete="new-password">
      <p class="error" id="pw-err"></p>
      <div class="foot"><button class="btn" value="cancel">Cancel</button><button class="btn primary" type="submit">Save</button></div>`,
      async () => {
        const a = $("#pw-1").value, b = $("#pw-2").value;
        if (a !== b) { $("#pw-err").textContent = "The two passwords differ."; return false; }
        const { error } = await S.sb.auth.updateUser({ password: a });
        if (error) { $("#pw-err").textContent = errText(error); return false; }
        toast("Password changed");
        return true;
      }); break;
    case "reload": location.reload(); break;
    case "tab": S.tab = el.dataset.tab; store.set("jt-tab", S.tab); render(); break;
    case "cand": S.cand = el.dataset.cand; store.set("jt-cand", S.cand); S.shown = 60; render(); break;
    case "more": S.shown += 60; viewJobs(); break;
    case "claim": {
      const others = sameCompany(j);
      if (others.length && !confirm(`${others.length} other application(s) at ${j.company} already. Claim this one too?`)) break;
      const a = await call("japan_claim", { p_job: key }, `Claimed. You have ${claimHours()} hours to apply.`);
      if (a) { S.apps.set(key, a); render(); }
      break;
    }
    case "apply": applyDialog(j); break;
    case "skip": textDialog("Not a fit", "Why? (helps the others)", "e.g. needs N2 Japanese, 3+ years required", async text => {
      const a = await call("japan_set_status", { p_job: key, p_status: "skipped", p_note: text }, "Skipped");
      if (a) { S.apps.set(key, a); render(); }
      return !!a || false;
    }); break;
    case "release": if (confirm("Give this job back so someone else can take it?")) {
      if (await call("japan_release", { p_job: key }, "Released")) { S.apps.delete(key); render(); }
    } break;
    case "reset": if (confirm("Reset this application completely? Its history stays in the log.")) {
      if (await call("japan_release", { p_job: key }, "Reset")) { S.apps.delete(key); render(); }
    } break;
    case "note": textDialog("Note", `For everyone, on ${j.title} at ${j.company}`, "e.g. referral contact, recruiter name", async text =>
      !!(await call("japan_note", { p_job: key, p_text: text }, "Noted")) || false); break;
    case "history": historyDialog(j); break;
    case "addjob": addJobDialog(); break;
    case "download": e.preventDefault(); download(el.dataset.id); break;
    case "priority": case "dna": {
      const patch = act === "priority" ? { priority: !j.priority } : { do_not_apply: !j.do_not_apply };
      const { error } = await S.sb.from("japan_jobs").update(patch).eq("key", key);
      if (error) return toast(errText(error), true);
      Object.assign(j, patch); render(); break;
    }
    case "togglecv": case "deletecv": {
      const r = S.resumes.find(x => x.id === el.dataset.id);
      if (act === "deletecv") {
        if (!confirm(`Delete the ${r.label} resume? Applications that used it keep their record.`)) break;
        const del = await S.sb.from("japan_resumes").delete().eq("id", r.id);
        if (del.error) return toast(errText(del.error), true);
        await S.sb.storage.from("japan-resumes").remove([r.file_path]);
        S.resumes = S.resumes.filter(x => x.id !== r.id);
      } else {
        const up = await S.sb.from("japan_resumes").update({ active: !r.active }).eq("id", r.id);
        if (up.error) return toast(errText(up.error), true);
        r.active = !r.active;
      }
      render(); break;
    }
    case "approve": case "role": case "remove": {
      const id = el.dataset.id, m = S.members.find(x => x.user_id === id);
      if (act === "remove") {
        if (!confirm(`Remove ${m.name || m.email}? They lose access; their applications stay.`)) break;
        const r = await S.sb.from("japan_members").delete().eq("user_id", id);
        if (r.error) return toast(errText(r.error), true);
        S.members = S.members.filter(x => x.user_id !== id);
      } else {
        const patch = act === "approve" ? { approved: el.dataset.on === "true" } : { role: el.dataset.role };
        if (act === "role" && patch.role === "owner" && !confirm(`Make ${m.name || m.email} an owner? Owners can approve people and delete resumes.`)) break;
        const r = await S.sb.from("japan_members").update(patch).eq("user_id", id);
        if (r.error) return toast(errText(r.error), true);
        Object.assign(m, patch);
      }
      render(); break;
    }
    case "export": exportCsv(); break;
    case "refresh": {
      el.disabled = true;
      const r = await call("japan_request_refresh", {});
      if (r) {
        S.refresh = r;
        toast(r.status === "running" ? "A refresh is already running" : "Refresh queued; it starts within a minute");
      }
      renderChrome();
      break;
    }
  }
});

document.addEventListener("change", async e => {
  const el = e.target;
  if (el.dataset?.act !== "setstatus" || !el.value) return;
  const key = el.dataset.key, status = el.value;
  const a = await call("japan_set_status", { p_job: key, p_status: status, p_note: "" }, `Marked ${STATUS[status][0].toLowerCase()}`);
  if (a) { S.apps.set(key, a); render(); } else el.value = "";
});

boot();
