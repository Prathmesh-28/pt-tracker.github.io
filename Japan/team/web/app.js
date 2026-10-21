// Japan applications team tracker. Every change goes through database functions that
// refuse a second claim or application on the same job, so the list can never mislead
// two people into applying twice. This file only shows the state and calls them.
import { createClient } from "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/+esm";
import { MBA_SCHOOLS } from "./mba.js";

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
  cand: store.get("jt-cand", "prathmesh"), tab: store.get("jt-tab", "jobs"), shown: 60, cshown: 40,
  f: Object.assign({ q: "", status: "open", level: "entry", visa: "ok", kind: "all", fit: "all", priority: false, sort: "smart",
                     kansai: false, jp: "any", jt: "all", area: "any", indian: false },
                   store.get("jt-filters", {})),
  cf: Object.assign({ q: "", status: "open", band: "all", route: false, kind: "all", soon: false, fit: "all", sort: "rank" },
                    store.get("jt-cfilters", {})),
  ishown: 60, oshown: 60,
  of: Object.assign({ q: "", status: "open", country: "all", family: "all", sort: "newest" }, store.get("jt-ofilters", {})),
  inf: Object.assign({ q: "", status: "open", family: "all", type: "all", timing: "all", sort: "priority", pay: false },
                     store.get("jt-ifilters", {})),
  mf: Object.assign({ q: "", region: "all", fit: "all", ivy: false, intake: "any", early: false, sort: "gmat" },
                    store.get("jt-mfilters", {})),
};

const STATUS = {
  claimed: ["Claimed", "warn"], applied: ["Applied", "ok"], interview: ["Interview", "info"], offer: ["Offer", "ok"],
  rejected: ["Rejected", ""], withdrawn: ["Withdrawn", ""], skipped: ["Skipped", ""],
};
const LEVEL = { intern: "Internship", new_grad: "New grad", entry: "Entry level", mid: "Mid level", senior: "Senior", unstated: "Level not stated" };
const LANG = { english_ok: ["No Japanese needed", "ok"], japanese_plus: ["Japanese a plus", "info"], unstated: ["Japanese not mentioned", "warn"] };
const FIT = { yes: ["Fits 2027 grads", "ok"], likely: ["Likely fits 2027", "warn"], check: ["Check the batch", "info"], no: ["Not for 2027 grads", "bad"] };
// Case competitions (CaseCompetitions/, from Unstop) share the jobs table as kind "competition". Their
// statuses read differently: registering replaces applying, a round passed replaces an interview.
const COMP_STATUS = {
  claimed: ["Taking it on", "warn"], applied: ["Registered", "ok"], interview: ["Next round", "info"], offer: ["Won", "ok"],
  rejected: ["Out", ""], withdrawn: ["Dropped", ""], skipped: ["Not doing", ""],
};
const BAND = { 1: ["IIT only", "ok"], 2: ["Top-paying employer", "ok"], 3: ["Select campuses or strong pay", "info"],
               4: ["Big company, open to all", ""], 5: ["College fest or small organiser", ""] };
const CHANNEL = { ppo: "PPO or job offer", ppi: "PPI", intern: "Internship" };
const TIER_CLASS = { 1: "ok", 2: "info", 3: "" };

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
const isComp = j => j?.kind === "competition";
// India roles (India/, with pay from AmbitionBox and campus offers) are rows of kind "india", in their own tab.
const isIndia = j => j?.kind === "india";
// Roles abroad whose postings say they sponsor a visa (Overseas/), rows of kind "overseas", in their own tab.
const isOverseas = j => j?.kind === "overseas";
const myRoles = () => myJobs().filter(j => !isComp(j) && !isIndia(j) && !isOverseas(j));
const myOverseas = () => myJobs().filter(isOverseas);
const myComps = () => myJobs().filter(isComp);
const myIndia = () => myJobs().filter(isIndia);
const statusOf = (j, s) => (isComp(j) ? COMP_STATUS : STATUS)[s] || [s, ""];
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
// Why a company counts as one where Indians work: its open roles in India now, or a sourced note.
const indiaWhy = i => i.note || `${i.more ? "Hiring in India now" : `${i.count} open roles in India now`} (${(i.places || []).join(", ")})`;
const hasIndia = () => myRoles().some(j => j.extra?.india);
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
  for (const j of myRoles()) {
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
const VIEWS = () => ({ jobs: viewJobs, india: viewIndia, overseas: viewOverseas, comps: viewComps, mba: viewMba, mine: viewMine, activity: viewActivity,
                       resumes: viewResumes, team: viewTeam, settings: viewSettings });
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
  else if (r?.status === "running") line = `${esc(r.step || "Starting")} · started ${at(r.started_at)} IST${r.trigger === "schedule" && at(r.started_at).startsWith("08:") ? " (the 8:00 run)" : ""}`;
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
      S.jobs.filter(j => candOf(j) === c.id && j.is_open && !isComp(j) && !isIndia(j) && !isOverseas(j)).length}</span></button>`).join("")}${refreshBox()}`;
  const tabs = [["jobs", myIndia().length ? "Japan jobs" : "Jobs", myRoles().filter(j => j.is_open).length]];
  if (myIndia().length) tabs.push(["india", "India jobs", myIndia().filter(j => j.is_open).length]);
  if (myOverseas().length) tabs.push(["overseas", "Overseas", myOverseas().filter(j => j.is_open).length]);
  if (myComps().length) tabs.push(["comps", "Competitions", myComps().filter(compOpen).length]);
  if (S.cand === "prathmesh") tabs.push(["mba", "MBA", MBA_SCHOOLS.length]);
  tabs.push(["mine", "Mine", mine], ["activity", "Activity", ""], ["resumes", "Resumes", myResumes().filter(r => r.active).length],
            ["team", "Team", isOwner() && waiting ? `${waiting} waiting` : S.members.filter(m => m.approved).length]);
  if (isOwner()) tabs.push(["settings", "Settings", ""]);
  if (!tabs.some(t => t[0] === S.tab)) S.tab = "jobs";
  $("#tabsbar").innerHTML = tabs.map(([k, label, n]) =>
    `<button role="tab" aria-selected="${S.tab === k}" data-act="tab" data-tab="${k}">${label}${n !== "" ? `<span class="n">${esc(n)}</span>` : ""}</button>`).join("");
  if (S.tab === "india") {
    const k = indiaCounts();
    $("#statsbar").innerHTML = `
      <div><b>${k.open}</b><span>Open to apply</span></div><div><b>${k.product}</b><span>Product analyst and APM</span></div>
      <div><b>${k.paid}</b><span>With the company's own pay</span></div><div><b>${k.startups} · ${k.mncs}</b><span>Startups · MNCs</span></div>
      <div><b>${k.applied}</b><span>Applications sent</span></div>`;
    return;
  }
  if (S.tab === "overseas") {
    const open = myOverseas().filter(j => j.is_open);
    const countries = new Set(open.map(j => j.extra?.country).filter(c => c && c !== "Not stated"));
    const sent = myOverseas().filter(j => ["applied", "interview", "offer"].includes(S.apps.get(j.key)?.status)).length;
    $("#statsbar").innerHTML = `
      <div><b>${open.length}</b><span>Open roles that state visa sponsorship</span></div>
      <div><b>${countries.size}</b><span>Countries</span></div>
      <div><b>${open.filter(j => j.extra?.tier).length}</b><span>At the top-paying employers</span></div>
      <div><b>${sent}</b><span>Applications sent</span></div>`;
    return;
  }
  if (S.tab === "mba") {
    const days = Math.ceil((new Date("2027-01-05T12:00:00-05:00") - Date.now()) / 864e5);
    $("#statsbar").innerHTML = `
      <div><b>705+</b><span>GMAT Focus target for the M7 and Ivies</span></div>
      <div><b>${MBA_SCHOOLS.filter(s => /Target|Likely/.test(s.fit)).length}</b><span>Target or likely schools</span></div>
      <div><b>${MBA_SCHOOLS.filter(mbaHasEarly).length}</b><span>Deferred routes open to final-year students</span></div>
      <div><b>${days > 0 ? days : "—"}</b><span>Days to HBS Round 2 (5 Jan 2027)</span></div>
      <div><b>$275</b><span>GMAT fee, any day of the year</span></div>`;
    return;
  }
  if (S.tab === "comps") {
    const k = compCounts();
    $("#statsbar").innerHTML = `
      <div><b>${k.open}</b><span>Open to register</span></div><div><b>${k.top}</b><span>IIT only or top-paying</span></div>
      <div><b>${k.route}</b><span>With a PPI, PPO or internship</span></div><div><b>${k.soon}</b><span>Closing within 7 days</span></div>
      <div><b>${k.registered}</b><span>Registered</span></div>`;
    return;
  }
  const c = counts();
  $("#statsbar").innerHTML = `
    <div><b>${c.open}</b><span>Open to claim</span></div><div><b>${c.claimed}</b><span>Claimed, not sent</span></div>
    <div><b>${c.applied}</b><span>Applications sent</span></div><div><b>${c.interview}</b><span>Interviews</span></div>
    <div><b>${c.offer}</b><span>Offers</span></div>`;
}

function backgroundRender() {
  if (!S.me?.approved || !$("#view")) return;
  renderChrome();
  if (FORM_VIEWS.includes(S.tab)) return;
  const active = document.activeElement, id = active && ["f-q", "c-q", "i-q", "m-q"].includes(active.id) ? active.id : null;
  const keep = id ? [active.selectionStart, active.selectionEnd] : null;
  VIEWS()[S.tab]();
  if (keep) { const q = $(`#${id}`); if (q) { q.focus(); q.setSelectionRange(...keep); } }
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
  if (f.indian && hasIndia() && !j.extra?.india) return false;
  if (f.q) {
    const hay = `${j.title} ${j.company} ${j.location} ${j.track}`.toLowerCase();
    if (!f.q.toLowerCase().split(/\s+/).every(w => hay.includes(w))) return false;
  }
  return true;
}

const hasExtras = () => myRoles().some(j => j.extra && j.extra.japanese);

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
  const badges = isIndia(j) ? indiaBadges(j) : isOverseas(j) ? overseasBadges(j) : [];
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
  if (j.extra?.india) badges.push(`<span class="b ok" title="${esc(indiaWhy(j.extra.india))}">Indians work here</span>`);
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
      ${j.extra?.india ? `<p class="muted why">Indians work here: ${esc(indiaWhy(j.extra.india))}</p>` : ""}
      ${isIndia(j) ? indiaLines(j) : ""}
      ${isOverseas(j) && j.eligibility ? `<p class="muted why">Visa: “${esc(j.eligibility)}”</p>` : ""}
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
  const list = sorted(myRoles().filter(matches));
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
      ${hasIndia() ? `<label title="The company is hiring in India now, or has an India office"><input type="checkbox" id="f-indian" ${f.indian ? "checked" : ""}> Indians work here</label>` : ""}
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
  bind("#f-indian", "indian", "change", el => el.checked);
  ["jt", "area", "jp"].forEach(k => bind(`#f-${k}`, k));
}

// ---------------------------------------------------------------- India

const TYPE_CLASS = { MNC: "info", Startup: "ok", "Indian MNC": "info" };
const lakhs = n => `₹${Number(n).toLocaleString("en-IN", { maximumFractionDigits: 1 })} lakh`;

function indiaBadges(j) {
  const x = j.extra || {}, out = [];
  if (x.row_kind === "campus") out.push(`<span class="b ok">On campus (JAF)</span>`);
  if (x.row_kind === "programme") out.push(`<span class="b info">Graduate programme</span>`);
  if (x.ctc) {
    const base = x.base ? ` · ${lakhs(x.base)} base${x.estimate_base ? " (est.)" : ""}` : "";
    out.push(`<span class="b ok">${lakhs(x.ctc)} CTC${base}</span>`);
  }
  if (x.company_type) out.push(`<span class="b ${TYPE_CLASS[x.company_type] || ""}">${esc(x.company_type)}</span>`);
  if (j.track && x.row_kind === "role") out.push(`<span class="b">${esc(j.track)}</span>`);
  if (x.job_kind === "internship") out.push(`<span class="b info">Internship</span>`);
  return out;
}

// Where the pay figure comes from, and when to apply by.
function indiaLines(j) {
  const x = j.extra || {};
  const range = x.lo && x.hi && x.lo !== x.hi ? `, typical ${lakhs(x.lo)}–${lakhs(x.hi)}` : "";
  const src = x.pay_source ? ` <a href="${esc(x.pay_source)}" target="_blank" rel="noopener">source</a>` : "";
  const pay = x.basis ? `Pay: ${esc(x.basis)}${range}${x.estimate_base ? "; base estimated from the campus offers' base-to-CTC share" : ""}.${src}`
                      : "Pay: no AmbitionBox figure for this role.";
  const market = x.market?.ctc ? ` AmbitionBox average for comparison: ${lakhs(x.market.ctc)} CTC (${esc(x.market.span)}).` : "";
  return `<p class="muted why">${esc(x.deadline_line || "")}${j.eligibility ? ` · ${esc(j.eligibility)}` : ""}</p>
    <p class="muted why">${pay}${market}${x.notes ? ` ${esc(x.notes)}` : ""}</p>`;
}

function indiaCounts() {
  const k = { open: 0, product: 0, paid: 0, startups: 0, mncs: 0, applied: 0 };
  for (const j of myIndia()) {
    const a = S.apps.get(j.key), x = j.extra || {};
    if (a && ["applied", "interview", "offer"].includes(a.status)) k.applied++;
    if (!j.is_open || j.do_not_apply || (a && !claimExpired(a))) continue;
    k.open++;
    if (/^Product/.test(j.track || "")) k.product++;
    if (x.ctc && !/across India/.test(x.basis || "")) k.paid++;
    if (x.company_type === "Startup") k.startups++;
    if (/MNC/.test(x.company_type || "")) k.mncs++;
  }
  return k;
}

function indiaMatches(j) {
  const f = S.inf, x = j.extra || {}, a = S.apps.get(j.key), expired = claimExpired(a);
  const st = !a || expired ? "open" : a.status;
  if (f.status === "open" && (st !== "open" || !j.is_open || j.do_not_apply)) return false;
  if (f.status === "claimed" && st !== "claimed") return false;
  if (f.status === "applied" && !["applied", "interview", "offer", "rejected", "withdrawn"].includes(st)) return false;
  if (f.status === "skipped" && st !== "skipped") return false;
  if (f.family !== "all" && j.track !== f.family) return false;
  if (f.type === "mnc" && !/MNC/.test(x.company_type || "")) return false;
  if (f.type === "startup" && x.company_type !== "Startup") return false;
  if (f.type === "indian" && !/^Indian company/.test(x.company_type || "")) return false;
  if (f.timing === "2027" && j.grad_2027 !== "yes") return false;
  if (f.timing === "not_other" && j.grad_2027 === "no") return false;
  if (f.pay && !x.ctc) return false;
  if (f.q) {
    const hay = `${j.title} ${j.company} ${j.location} ${j.track} ${x.company_type || ""}`.toLowerCase();
    if (!f.q.toLowerCase().split(/\s+/).every(w => hay.includes(w))) return false;
  }
  return true;
}

function indiaSorted(list) {
  const by = S.inf.sort, ctc = j => j.extra?.ctc || 0;
  const due = j => j.deadline || "9999";
  if (by === "pay") return list.sort((a, b) => ctc(b) - ctc(a) || (a.extra?.rank ?? 1e9) - (b.extra?.rank ?? 1e9));
  if (by === "newest") return list.sort((a, b) => (b.posted || "").localeCompare(a.posted || "") || ctc(b) - ctc(a));
  if (by === "deadline") return list.sort((a, b) => due(a).localeCompare(due(b)) || (b.posted || "").localeCompare(a.posted || ""));
  if (by === "company") return list.sort((a, b) => a.company.localeCompare(b.company) || a.title.localeCompare(b.title));
  return list.sort((a, b) => (b.priority - a.priority) || (a.extra?.rank ?? 1e9) - (b.extra?.rank ?? 1e9));
}

function indiaHead() {
  let r = null;
  try { r = JSON.parse(S.settings.refreshed_india || "null"); } catch {}
  const when = r?.at ? new Date(r.at).toLocaleString("en-GB", { timeZone: "Asia/Kolkata", day: "numeric", month: "short",
                                                               hour: "2-digit", minute: "2-digit", hour12: false }) : "";
  return `<div class="listhead">
    <p>Entry-level roles in India from LinkedIn, Indeed and company boards (the India tracker in this repo), kept to product analyst
      and APM first, then business and data analyst, strategy, consulting, founder's office, management trainee and other early
      business roles; ones asking two years or more are left out. Campus offers from the placement portal and graduate programmes
      come first.</p>
    <p>Pay is what freshers (0–1 years) in that role at that company report on AmbitionBox, India's salary site: CTC, the typical
      range, and the base when it is reported, else estimated from the campus offers' base-to-CTC share. Glassdoor and Levels.fyi
      block automated reading. Few postings state a deadline, so most show the date posted. ${esc(person().name)} graduates in May
      2027: "Check the batch" means the posting names no batch.${when ? ` Last synced ${esc(when)} IST.` : ""}</p></div>`;
}

function viewIndia() {
  const f = S.inf, list = indiaSorted(myIndia().filter(indiaMatches));
  const families = [...new Set(myIndia().map(j => j.track).filter(Boolean))].sort().map(v => [v, v]);
  $("#view").innerHTML = `
    <div class="controls">
      <input type="search" id="i-q" placeholder="Search title, company or city" value="${esc(f.q)}" aria-label="Search India roles">
      <select id="i-status" aria-label="Status">${opts([["open", "Open to claim"], ["claimed", "Claimed"], ["applied", "Applied and later"],
                                                         ["skipped", "Skipped"], ["all", "Everything"]], f.status)}</select>
      <select id="i-family" aria-label="Kind of role">${opts([["all", "Every kind of role"], ...families], f.family)}</select>
      <select id="i-type" aria-label="Company">${opts([["all", "Every company"], ["mnc", "MNCs"], ["startup", "Startups"],
                                                       ["indian", "Indian companies"]], f.type)}</select>
      <select id="i-timing" aria-label="Batch">${opts([["all", "Any batch"], ["not_other", "Not for other batches only"],
                                                       ["2027", "Names the 2027 batch"]], f.timing)}</select>
      <select id="i-sort" aria-label="Sort">${opts([["priority", "Product roles and campus first"], ["pay", "Pay, highest first"],
                                                    ["newest", "Newest"], ["deadline", "Deadline"], ["company", "Company"]], f.sort)}</select>
      <label><input type="checkbox" id="i-pay" ${f.pay ? "checked" : ""}> With a pay figure</label>
      <span class="count">${list.length} shown</span>
    </div>
    ${indiaHead()}
    <div class="list">${list.length ? list.slice(0, S.ishown).map(jobCard).join("") : `<div class="empty">No roles match these filters.</div>`}</div>
    ${list.length > S.ishown ? `<button class="btn more" data-act="imore">Show more (${list.length - S.ishown} left)</button>` : ""}`;
  const bind = (id, key, ev = "change", get = el => el.value) => $(id)?.addEventListener(ev, e => {
    S.inf[key] = get(e.target); S.ishown = 60; store.set("jt-ifilters", S.inf);
    if (key === "q") { clearTimeout(viewIndia.t); viewIndia.t = setTimeout(() => { viewIndia(); const q = $("#i-q"); q.focus(); q.setSelectionRange(q.value.length, q.value.length); }, 200); }
    else viewIndia();
  });
  bind("#i-q", "q", "input");
  ["status", "family", "type", "timing", "sort"].forEach(k => bind(`#i-${k}`, k));
  bind("#i-pay", "pay", "change", el => el.checked);
}

// ---------------------------------------------------------------- competitions

// When registration shuts: Unstop's exact time, else the end of the deadline day in India.
const compDeadline = j => j.extra?.deadline_at ? new Date(j.extra.deadline_at) : j.deadline ? new Date(`${j.deadline}T23:59:00+05:30`) : null;
// Days left counted in India calendar days: a deadline at 18:29 today is "today", not "1 day left".
const istDate = d => Date.parse(d.toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" }));
function daysLeft(j) {
  const d = compDeadline(j);
  return d ? Math.max(0, Math.round((istDate(d) - istDate(new Date())) / 864e5)) : null;
}
// Open to register: still listed, and the deadline not passed (the sync closes Unstop ones each morning;
// ones the team added close when their deadline does).
const compOpen = j => j.is_open && !(compDeadline(j)?.getTime() < Date.now());
const istTime = d => d.toLocaleString("en-GB", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false });
const shortDay = iso => iso ? new Date(iso).toLocaleDateString("en-GB", { timeZone: "Asia/Kolkata", day: "numeric", month: "short" }) : "";
const teamText = t => { const [lo, hi] = t || []; return lo === 1 && hi === 1 ? "Solo" : lo && hi && lo !== hi ? `Team of ${lo}–${hi}` : lo || hi ? `Team of ${lo || hi}` : ""; };
const opts = (pairs, current) => pairs.map(([v, l]) => `<option value="${esc(v)}" ${current === v ? "selected" : ""}>${esc(l)}</option>`).join("");

function compCounts() {
  const k = { open: 0, top: 0, route: 0, soon: 0, registered: 0 };
  for (const j of myComps()) {
    const a = S.apps.get(j.key), x = j.extra || {}, left = daysLeft(j);
    if (a && ["applied", "interview", "offer"].includes(a.status)) k.registered++;
    if (!compOpen(j) || j.do_not_apply || (a && !claimExpired(a))) continue;
    k.open++;
    if (x.band <= 2) k.top++;
    if ((x.channels || []).length) k.route++;
    if (left !== null && left <= 7) k.soon++;
  }
  return k;
}

function compMatches(j) {
  const f = S.cf, x = j.extra || {}, a = S.apps.get(j.key), left = daysLeft(j);
  const st = !a || claimExpired(a) ? "open" : a.status;
  if (f.status === "open" && (st !== "open" || !compOpen(j) || j.do_not_apply)) return false;
  if (f.status === "ours" && ["open", "skipped"].includes(st)) return false;
  if (f.status === "skipped" && st !== "skipped") return false;
  if (f.band === "iit" && x.band !== 1) return false;
  if (f.band === "top" && !(x.band <= 2)) return false;
  if (f.band === "good" && !(x.band <= 3)) return false;
  if (f.route && !(x.channels || []).length) return false;
  if (f.kind !== "all" && j.via !== f.kind) return false;
  if (f.soon && !(left !== null && left <= 7)) return false;
  if (f.fit === "yes" && j.grad_2027 !== "yes") return false;
  if (f.q) {
    const hay = `${j.title} ${j.company} ${j.via} ${x.why || ""} ${x.festival || ""}`.toLowerCase();
    if (!f.q.toLowerCase().split(/\s+/).every(w => hay.includes(w))) return false;
  }
  return true;
}

function compSorted(list) {
  const by = S.cf.sort, end = j => compDeadline(j)?.getTime() ?? Infinity;
  const pool = j => (j.extra?.prize_inr || 0) + (j.extra?.prize_usd || 0) * 85;
  if (by === "deadline") return list.sort((a, b) => end(a) - end(b));
  if (by === "prize") return list.sort((a, b) => pool(b) - pool(a) || end(a) - end(b));
  if (by === "newest") return list.sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""));
  return list.sort((a, b) => (b.priority - a.priority) || (a.extra?.band ?? 9) - (b.extra?.band ?? 9)
    || (a.extra?.rank ?? 1e9) - (b.extra?.rank ?? 1e9) || end(a) - end(b));
}

function compCard(j) {
  const x = j.extra || {}, a = S.apps.get(j.key), expired = claimExpired(a), me = S.me.user_id, k = esc(j.key);
  const dl = compDeadline(j), left = daysLeft(j), open = compOpen(j);
  const badges = [];
  const [band, bandCls] = BAND[x.band] || [];
  if (band) badges.push(`<span class="b ${bandCls}">${x.rank ? `#${x.rank} · ` : ""}${esc(band)}</span>`);
  if (j.priority) badges.push(`<span class="b warn">★ Owner's pick</span>`);
  if (j.do_not_apply) badges.push(`<span class="b bad">Do not enter</span>`);
  if (!open) badges.push(`<span class="b">Registration closed</span>`);
  else if (j.created_at && Date.now() - new Date(j.created_at).getTime() < 36 * 3600e3) badges.push(`<span class="b ok">New</span>`);
  for (const c of x.channels || []) badges.push(`<span class="b ok">${esc(CHANNEL[c] || c)}</span>`);
  if (x.prize) badges.push(`<span class="b info">${esc(x.prize)} in prizes${x.winners > 1 ? `, ${x.winners} winners` : ""}</span>`);
  if (x.employer && x.employer.tier < 4) {
    badges.push(`<span class="b ${TIER_CLASS[x.employer.tier]}">${esc(x.employer.label)}${x.employer.sponsor ? `: ${esc(x.employer.sponsor)}` : ""}</span>`);
  }
  if (j.via) badges.push(`<span class="b">${esc(j.via)}</span>`);
  if (teamText(x.team)) badges.push(`<span class="b">${teamText(x.team)}</span>`);
  if (j.grad_2027 === "check") badges.push(`<span class="b warn">Check: ${esc((x.reasons || []).join("; ") || "eligibility not stated")}</span>`);
  if (x.paid) badges.push(`<span class="b warn">Entry fee</span>`);

  let status = "";
  const actions = [];
  if (!a || expired) {
    status = expired ? `<div class="status"><b>${esc(who(a.claimed_by))}</b> took this on but did not register in time; anyone can take it.</div>` : "";
    if (open && !j.do_not_apply) {
      actions.push(`<button class="btn primary" data-act="register" data-key="${k}">Mark registered</button>`,
                   `<button class="btn" data-act="claim" data-key="${k}">I'll take it on</button>`,
                   `<button class="btn" data-act="skip" data-key="${k}">Not doing</button>`);
    }
  } else {
    const [label, cls] = statusOf(j, a.status), by = a.applied_by || a.claimed_by;
    let line = `<span class="b ${cls}">${label}</span> by <b>${esc(who(by))}</b> · ${ago(a.applied_at || a.claimed_at)}`;
    if (a.status === "claimed") line += ` · ${hoursLeft(a)}h left to register`;
    if (a.applied_with) line += ` · with ${esc(a.applied_with)}`;
    if (a.note) line += `<br><span class="muted">${esc(a.note)}</span>`;
    status = `<div class="status">${line}</div>`;
    const mineNow = by === me;
    if (a.status === "claimed" && (mineNow || isOwner())) {
      actions.push(`<button class="btn primary" data-act="register" data-key="${k}">Mark registered</button>`,
                   `<button class="btn" data-act="release" data-key="${k}">Release</button>`);
    }
    if (["applied", "interview", "offer"].includes(a.status) && (mineNow || isOwner())) {
      actions.push(`<select class="btn" data-act="setstatus" data-key="${k}" aria-label="Update status">
        <option value="">Update…</option>${["interview", "offer", "rejected", "withdrawn"].filter(s => s !== a.status)
          .map(s => `<option value="${s}">${COMP_STATUS[s][0]}</option>`).join("")}</select>`);
    }
    if (a.status === "skipped" && (mineNow || isOwner())) actions.push(`<button class="btn" data-act="release" data-key="${k}">Undo</button>`);
    if (isOwner() && !["claimed", "skipped"].includes(a.status)) actions.push(`<button class="btn danger" data-act="reset" data-key="${k}">Reset</button>`);
  }
  actions.push(`<button class="btn" data-act="note" data-key="${k}">Note</button>`,
               `<button class="btn" data-act="history" data-key="${k}">History</button>`);
  if (isOwner()) {
    actions.push(`<button class="btn" data-act="priority" data-key="${k}">${j.priority ? "Unpick" : "★ Pick"}</button>`,
                 `<button class="btn danger" data-act="dna" data-key="${k}">${j.do_not_apply ? "Allow" : "Do not enter"}</button>`);
  }

  const rounds = (x.rounds || []).filter(r => r.title).map(r => `<li><b>${esc(r.title)}</b>${r.start || r.end
    ? ` · ${[shortDay(r.start), shortDay(r.end)].filter(Boolean).join(" – ")}` : ""}${r.what ? `<br><span class="muted">${esc(r.what)}</span>` : ""}</li>`).join("");
  const ranks = (x.ranks || []).filter(r => r.rank).map(r => `<li>${esc(r.rank)}${r.cash ? `: ${r.cur === "USD" ? "$" : "₹"}${Number(r.cash).toLocaleString("en-IN")}` : ""}${
    r.perk ? ` · <span class="muted">${esc(r.perk)}</span>` : ""}</li>`).join("");
  const campuses = (x.campuses || []).length
    ? `<p><b>Campuses allowed (${x.campuses_n}):</b> ${esc(x.campuses.join("; "))}${x.campuses_n > x.campuses.length ? "; …" : ""}</p>` : "";
  const deadline = dl ? `<span class="dl ${open && left <= 3 ? "soon" : ""}">${open ? "Closes" : "Closed"} ${istTime(dl)} IST${
    open ? ` · ${left === 0 ? "today" : left === 1 ? "1 day left" : `${left} days left`}` : ""}</span>` : "";
  const done = a && !expired && a.status !== "claimed";
  return `<article class="item ${done ? "done" : ""}">
    <div>
      <h3><a href="${esc(j.url)}" target="_blank" rel="noopener">${esc(j.title)}</a></h3>
      <div class="meta"><b>${esc(j.company)}</b>${deadline}${x.mode ? `<span>${x.mode === "online" ? "Online" : `In person${j.location ? `, ${esc(j.location)}` : ""}`}</span>` : ""}${
        x.festival ? `<span>${esc(x.festival)}</span>` : ""}${x.registered ? `<span>${Number(x.registered).toLocaleString("en-IN")} registered</span>` : ""}</div>
      <div class="badges">${badges.join("")}</div>
      ${x.why ? `<p class="muted why">${esc(x.why)}</p>` : ""}
      ${j.owner_note ? `<p class="muted" style="margin:6px 0 0;font-size:13px"><b>Owner:</b> ${esc(j.owner_note)}</p>` : ""}
    </div>
    <div class="actions">${actions.join("")}</div>
    ${status}
    <details class="more-info"><summary>What it is, the rounds and the prizes</summary>
      ${x.summary ? `<p>${esc(x.summary)}${x.summary.length >= 420 ? "…" : ""}</p>` : ""}
      ${j.eligibility ? `<p><b>Who can enter:</b> ${esc(j.eligibility)}</p>` : ""}${campuses}
      ${rounds ? `<p><b>Rounds</b></p><ol class="rounds">${rounds}</ol>` : ""}
      ${ranks ? `<p><b>Prizes</b></p><ul class="rounds">${ranks}</ul>` : ""}
    </details>
  </article>`;
}

function compHead() {
  let r = null;
  try { r = JSON.parse(S.settings.refreshed_competitions || "null"); } catch {}
  const when = r?.at ? new Date(r.at).toLocaleString("en-GB", { timeZone: "Asia/Kolkata", day: "numeric", month: "short",
                                                               hour: "2-digit", minute: "2-digit", hour12: false }) : "";
  return `<div class="listhead">
    <p>Ranked for an IIT Bombay B.Tech graduating in 2027. Competitions only IIT students may enter come first; then quant and
      trading firms, investment banks, top consulting and big tech; then a short list of campuses or an employer that pays well;
      then big companies open to everyone (Tata, ITC, Reliance, FMCG), which pay an IITian less; then college fests. Within each,
      a PPO or PPI comes first, then the bigger prize. Ones ${esc(person().name)} cannot enter (MBA only, other batches, other
      campuses) are left out.</p>
    <p>${when ? `Pulled live from Unstop; this list was last synced ${esc(when)} IST. ` : ""}It refreshes every morning at 8:00 IST
      and on Refresh. Deadlines are registration deadlines in India time.</p></div>`;
}

function watchSection() {
  let w = null;
  try { w = JSON.parse(S.settings.competitions_watch || "null"); } catch {}
  const rows = w?.entries || [];
  if (!rows.length) return "";
  const forYou = { yes: ["Can enter", "ok"], check: ["Check the batch", "warn"], no: ["Can't enter", ""] };
  const tierName = { 1: "Top pay", 2: "Strong pay", 3: "Pays an IITian less" };
  const scopeName = { iit_only: ["IIT only", "ok"], premier: ["Premier campuses", "info"], b_schools: ["B-schools only", ""] };
  const checked = rows.find(e => e.checked)?.checked;
  const body = rows.map(e => {
    const [fy, fyc] = forYou[e.for_2027] || ["", ""], [sc, scc] = scopeName[e.scope] || [];
    const open = (e.open_now || []).map(o => `<a href="${esc(o.url)}" target="_blank" rel="noopener">${esc(o.title)}</a>, closes ${shortDay(o.end)}`).join("<br>");
    return `<tr>
      <td><a href="${esc(e.url)}" target="_blank" rel="noopener"><b>${esc(e.name)}</b></a>${e.leads_to ? `<br><span class="muted">${esc(e.leads_to)}</span>` : ""}</td>
      <td>${esc(e.employer)}<br><span class="b ${TIER_CLASS[e.tier] ?? ""}">${tierName[e.tier] || "Other"}</span>${sc ? ` <span class="b ${scc}">${sc}</span>` : ""}</td>
      <td>${open ? `<span class="b ok">Open now</span><br>${open}` : esc(e.last || "")}</td>
      <td>${esc(e.next || "")}${e.before_graduation && !open ? `<br><span class="muted">before graduating</span>` : ""}</td>
      <td>${fy ? `<span class="b ${fyc}">${fy}</span>` : ""}${e.for_2027_note ? `<br><span class="muted">${esc(e.for_2027_note)}</span>` : ""}</td></tr>`;
  }).join("");
  return `<h2 class="section">When the big ones open</h2>
    <p class="muted sectionnote">The competitions with a hiring route that matter most, between seasons. Those on Unstop are read live on every
      refresh, every past edition with its dates; the ones run elsewhere (quant contests, bank hackathons) were checked by hand${checked ? ` on ${esc(fmtDate(checked))}` : ""}.</p>
    <div class="tablewrap"><table class="watch"><thead><tr><th>Competition</th><th>Employer</th><th>Last edition</th><th>Next</th><th>${esc(person().name)}</th></tr></thead>
      <tbody>${body}</tbody></table></div>`;
}

// ---------------------------------------------------------------- overseas

function overseasBadges(j) {
  const x = j.extra || {}, out = [];   // the card adds "Sponsors visa" from j.visa
  if (x.country && x.country !== "Not stated") out.push(`<span class="b info">${esc(x.country)}</span>`);
  if (j.track) out.push(`<span class="b">${esc(j.track)}</span>`);
  if (x.tier) out.push(`<span class="b">${esc(x.tier)}</span>`);
  return out;
}

function overseasMatches(j) {
  const f = S.of, a = S.apps.get(j.key), st = !a || claimExpired(a) ? "open" : a.status;
  if (f.status === "open" && (st !== "open" || !j.is_open || j.do_not_apply)) return false;
  if (f.status === "claimed" && st !== "claimed") return false;
  if (f.status === "applied" && !["applied", "interview", "offer", "rejected", "withdrawn"].includes(st)) return false;
  if (f.status === "skipped" && st !== "skipped") return false;
  if (f.country !== "all" && (j.extra?.country || "Not stated") !== f.country) return false;
  if (f.family !== "all" && j.track !== f.family) return false;
  if (f.q) {
    const hay = `${j.title} ${j.company} ${j.location} ${j.track} ${j.extra?.country || ""}`.toLowerCase();
    if (!f.q.toLowerCase().split(/\s+/).every(w => hay.includes(w))) return false;
  }
  return true;
}

function viewOverseas() {
  const f = S.of, list = myOverseas().filter(overseasMatches).sort((a, b) => f.sort === "company"
    ? a.company.localeCompare(b.company) || a.title.localeCompare(b.title)
    : (b.priority - a.priority) || (b.posted || "").localeCompare(a.posted || ""));
  const uniq = k => [...new Set(myOverseas().map(k).filter(Boolean))].sort().map(v => [v, v]);
  $("#view").innerHTML = `
    <div class="controls">
      <input type="search" id="o-q" placeholder="Search title, company or country" value="${esc(f.q)}" aria-label="Search overseas roles">
      <select id="o-status" aria-label="Status">${opts([["open", "Open to claim"], ["claimed", "Claimed"], ["applied", "Applied and later"],
                                                         ["skipped", "Skipped"], ["all", "Everything"]], f.status)}</select>
      <select id="o-country" aria-label="Country">${opts([["all", "Every country"], ...uniq(j => j.extra?.country || "Not stated")], f.country)}</select>
      <select id="o-family" aria-label="Kind of role">${opts([["all", "Every kind of role"], ...uniq(j => j.track)], f.family)}</select>
      <select id="o-sort" aria-label="Sort">${opts([["newest", "Newest"], ["company", "Company"]], f.sort)}</select>
      <span class="count">${list.length} shown</span>
    </div>
    <div class="listhead"><p>Entry-level product, analyst, strategy, consulting and finance roles outside India and Japan whose
      own posting says the employer sponsors a work visa. The sentence that says so is under each role. Postings that say nothing
      about visas are left out, and so are ones that ask for an existing right to work there or for two years or more. From the
      careers boards of about 90 employers, and LinkedIn and Indeed searched for "visa sponsorship" in nine countries.</p></div>
    <div class="list">${list.length ? list.slice(0, S.oshown).map(jobCard).join("") : `<div class="empty">No roles match these filters.</div>`}</div>
    ${list.length > S.oshown ? `<button class="btn more" data-act="omore">Show more (${list.length - S.oshown} left)</button>` : ""}`;
  const bind = (id, key, ev = "change") => $(id)?.addEventListener(ev, e => {
    S.of[key] = e.target.value; S.oshown = 60; store.set("jt-ofilters", S.of);
    if (key === "q") { clearTimeout(viewOverseas.t); viewOverseas.t = setTimeout(() => { viewOverseas(); const q = $("#o-q"); q.focus(); q.setSelectionRange(q.value.length, q.value.length); }, 200); }
    else viewOverseas();
  });
  bind("#o-q", "q", "input");
  ["status", "country", "family", "sort"].forEach(k => bind(`#o-${k}`, k));
}

function viewComps() {
  const f = S.cf, list = compSorted(myComps().filter(compMatches));
  const kinds = [...new Set(myComps().map(j => j.via).filter(Boolean))].sort().map(v => [v, v]);
  $("#view").innerHTML = `
    <div class="controls">
      <input type="search" id="c-q" placeholder="Search name, organiser or company" value="${esc(f.q)}" aria-label="Search competitions">
      <select id="c-status" aria-label="Status">${opts([["open", "Open to register"], ["ours", "Taken on, registered and later"],
                                                         ["skipped", "Not doing"], ["all", "Everything, closed too"]], f.status)}</select>
      <select id="c-band" aria-label="Priority">${opts([["all", "Every priority"], ["iit", "IIT only"], ["top", "IIT only and top-paying employers"],
                                                        ["good", "The top three priorities"]], f.band)}</select>
      <select id="c-kind" aria-label="Type">${opts([["all", "Every type"], ...kinds], f.kind)}</select>
      <select id="c-fit" aria-label="Eligibility">${opts([["all", "Eligible, or worth checking"], ["yes", "Clearly eligible"]], f.fit)}</select>
      <select id="c-sort" aria-label="Sort">${opts([["rank", "Priority"], ["deadline", "Deadline, soonest first"], ["prize", "Prize pool"],
                                                    ["newest", "Newest"]], f.sort)}</select>
      <label><input type="checkbox" id="c-route" ${f.route ? "checked" : ""}> PPI, PPO or internship</label>
      <label><input type="checkbox" id="c-soon" ${f.soon ? "checked" : ""}> Closing within 7 days</label>
      <button class="btn" data-act="addcomp">+ Add a competition</button>
      <span class="count">${list.length} shown</span>
    </div>
    ${compHead()}
    <div class="list">${list.length ? list.slice(0, S.cshown).map(compCard).join("") : `<div class="empty">No competitions match these filters.</div>`}</div>
    ${list.length > S.cshown ? `<button class="btn more" data-act="cmore">Show more (${list.length - S.cshown} left)</button>` : ""}
    ${watchSection()}`;
  const bind = (id, key, ev = "change", get = el => el.value) => $(id)?.addEventListener(ev, e => {
    S.cf[key] = get(e.target); S.cshown = 40; store.set("jt-cfilters", S.cf);
    if (key === "q") { clearTimeout(viewComps.t); viewComps.t = setTimeout(() => { viewComps(); const q = $("#c-q"); q.focus(); q.setSelectionRange(q.value.length, q.value.length); }, 200); }
    else viewComps();
  });
  bind("#c-q", "q", "input");
  ["status", "band", "kind", "fit", "sort"].forEach(k => bind(`#c-${k}`, k));
  bind("#c-route", "route", "change", el => el.checked);
  bind("#c-soon", "soon", "change", el => el.checked);
}

function registerDialog(j) {
  openDialog(`<h2>Mark as registered</h2>
    <p class="muted" style="margin:0">${esc(j.title)} · ${esc(j.company)}</p>
    <label for="rg-with">Registered with (email or Unstop account)</label><input id="rg-with" type="text" placeholder="e.g. the IITB email on Unstop">
    <label for="rg-note">Team and anything the group should know</label><textarea id="rg-note" placeholder="Teammates, the track picked, when the next round is"></textarea>
    <div class="foot"><button class="btn" value="cancel">Cancel</button><button class="btn primary" type="submit">Mark registered</button></div>`,
    async () => {
      const a = await call("japan_register", { p_job: j.key, p_with: $("#rg-with").value.trim(), p_note: $("#rg-note").value.trim() },
                           "Marked as registered");
      if (a) { S.apps.set(j.key, a); render(); }
      return !!a || false;
    });
}

// A competition from outside Unstop: an IIT-only contest from a placement-cell mail, a company's own challenge.
function addCompDialog() {
  openDialog(`<h2>Add a competition to ${esc(person().name)}'s list</h2>
    <p class="muted" style="margin:0">Found outside Unstop? Add it so it is ranked with the rest and nobody misses the deadline.</p>
    <label for="nc-title">Competition</label><input id="nc-title" type="text" required>
    <label for="nc-org">Organiser or company</label><input id="nc-org" type="text" required>
    <label for="nc-url">Link</label><input id="nc-url" type="url" placeholder="https://">
    <label for="nc-deadline">Registration deadline</label><input id="nc-deadline" type="date">
    <label for="nc-band">Priority</label><select id="nc-band">${opts(Object.entries(BAND).map(([b, [l]]) => [b, l]), "1")}</select>
    <label for="nc-note">Note (the prize, the PPI, who may enter)</label><input id="nc-note" type="text">
    <div class="foot"><button class="btn" value="cancel">Cancel</button><button class="btn primary" type="submit">Add</button></div>`,
    async () => {
      const job = await call("japan_add_competition", { p_title: $("#nc-title").value, p_organiser: $("#nc-org").value,
        p_url: $("#nc-url").value, p_deadline: $("#nc-deadline").value || null, p_band: Number($("#nc-band").value),
        p_note: $("#nc-note").value, p_candidate: S.cand }, "Added to the list");
      if (job) { S.jobs.push(job); render(); }
      return !!job || false;
    });
}

const card = j => isComp(j) ? compCard(j) : jobCard(j);

// ---------------------------------------------------------------- MBA
// Top business schools for Prathmesh, from admissions/MBA-admissions/ (build_schools.py writes mba.js).
// Static reference data: nothing here is claimed or stored in the database.
const FIT_ORDER = { Likely: 0, Target: 1, Stretch: 2, Reach: 3, "Later option": 4 };
const FIT_BADGE = { Likely: "ok", Target: "info", Stretch: "warn", Reach: "bad", "Later option": "" };
const mbaHasEarly = s => !!s.early_route && !/^—|not open|undergrads only|^Needs|^MSc|Master in Management/i.test(s.early_route);
const mbaCost = s => parseFloat(String(s.total_cost_inr).replace(/[^\d.]/g, "")) * (/Cr/.test(s.total_cost_inr) ? 100 : 1);

function mbaMatches(s) {
  const f = S.mf, q = f.q.trim().toLowerCase();
  return (f.region === "all" || s.region === f.region) && (f.fit === "all" || s.fit === f.fit) && (!f.ivy || s.ivy === "Yes") &&
    (f.intake === "any" || (f.intake === "spring" ? /Spring|Jan/i.test(s.intakes) : /Fall/i.test(s.intakes))) &&
    (!f.early || mbaHasEarly(s)) && (!q || Object.values(s).join(" ").toLowerCase().includes(q));
}

function mbaCard(s) {
  return `<article class="item">
    <div>
      <h3>${esc(s.school)}</h3>
      <div class="meta"><span>${esc(s.programme)}</span><span>${esc(s.country)}</span><span>${esc(s.length)}</span><span>Avg work exp ${esc(s.avg_work_exp)}</span></div>
      <div class="badges"><span class="b ${FIT_BADGE[s.fit] ?? ""}">${esc(s.fit)}</span>${s.ivy === "Yes" ? `<span class="b info">Ivy League</span>` : ""}
        ${/Spring|Jan/i.test(s.intakes) ? `<span class="b ok">January / spring intake</span>` : ""}${mbaHasEarly(s) ? `<span class="b ok">Deferred route for students</span>` : ""}</div>
    </div>
    <div class="mbanums">
      <div><b>${esc(s.avg_gmat_focus)}</b><span>class avg GMAT</span></div>
      <div><b>${esc(s.target_gmat)}</b><span>your target</span></div>
      <div><b>${esc(s.total_cost_inr)}</b><span>total cost</span></div>
    </div>
    <dl class="mbadl">
      <dt>Deadlines</dt><dd>${esc(s.rounds)}</dd>
      <dt>Intake</dt><dd>${esc(s.intakes)}</dd>
      <dt>While at IITB</dt><dd>${esc(s.early_route)}</dd>
      <dt>Looking for</dt><dd>${esc(s.looking_for)}</dd>
      <dt>Tuition</dt><dd>${esc(s.tuition_total)}</dd>
      <dt>Scholarships</dt><dd>${esc(s.scholarships)}</dd>
    </dl>
  </article>`;
}

function mbaGuide() {
  return `
    <h2 class="section">Where the profile stands</h2>
    <p class="muted sectionnote">10th CBSE 90.8% · 12th Maharashtra Board 77.17% · IIT Bombay B.Tech Civil (IEOR minor), CGPA 6.56 / 10, graduating 2027.
      The IIT Bombay name is strong, but the 6.56 is the weak point, and Indian male engineers are the most crowded applicant pool, so the GMAT
      has to sit above the class average. Make up for the CGPA with: a Quant section score of 85+; one or two graded quant courses with an A (HBS Online
      CORe, UC Berkeley or UCLA Extension statistics, MITx Supply Chain MicroMasters); a three-line optional essay; and work with measurable results.
      The 12th-grade marks barely matter, except a little at ISB and the IIMs.</p>
    <div class="tablewrap"><table><thead><tr><th>Aiming for</th><th>Class average</th><th>Target with CGPA 6.56</th><th>Percentile</th></tr></thead><tbody>
      <tr><td>HBS, Stanford (incl. HBS 2+2)</td><td>685-690</td><td><b>715+</b></td><td>~99</td></tr>
      <tr><td>Wharton, Columbia, Booth, Kellogg, MIT Sloan, Yale</td><td>675-690</td><td><b>705+</b></td><td>~98-99</td></tr>
      <tr><td>Tuck, Haas, Stern</td><td>670-675</td><td><b>695+</b></td><td>~97</td></tr>
      <tr><td>Cornell, Ross, Fuqua, Darden, UCLA, LBS, INSEAD, ISB</td><td>660-675</td><td><b>685+</b></td><td>~96</td></tr>
      <tr><td>Oxford, Cambridge, HEC, IESE, Tepper</td><td>650-660</td><td><b>675+</b></td><td>~94</td></tr>
      <tr><td>Imperial, NUS, Rotman</td><td>~635</td><td><b>665+</b></td><td>~90</td></tr>
    </tbody></table></div>
    <p class="muted sectionnote" style="margin-top:8px"><b>The Ivies:</b> only six have an MBA (Harvard, Wharton, Columbia, Yale, Tuck, Cornell); Brown and Princeton don't.
      Best Ivy picks for this profile: <b>Cornell Johnson</b> (most realistic; the 1-year Tech MBA suits engineers; the Park Fellowship pays full tuition),
      <b>Yale Silver Scholars</b> (you apply while still at IITB), and <b>Columbia</b> (January J-Term start and a deferred programme). Harvard and Wharton are a reach.</p>

    <h2 class="section">Two ways to go</h2>
    <div class="tablewrap"><table><thead><tr><th>When</th><th>Route A: deferred MBA, apply in final year</th><th>Route B: work first</th></tr></thead><tbody>
      <tr><td>Oct-Dec 2026</td><td>Take a free official GMAT practice exam as a diagnostic, then prep 12-15 hrs a week</td><td>Same: an early GMAT score is valid 5 years</td></tr>
      <tr><td>Dec 2026 - Feb 2027</td><td>GMAT attempt 1, retake 3-4 weeks later if needed. Apply to <b>ISB YLP</b></td><td>GMAT done; push the last-semester CGPA up</td></tr>
      <tr><td>Feb-Apr 2027</td><td>HBS 2+2 (~late Apr), Yale Silver Scholars, Stanford R3, MIT Early Admission, Booth / Kellogg / Columbia / Haas / Stern / Darden deferred</td><td>Pick a first job with ownership: consulting, product, analytics, infrastructure finance</td></tr>
      <tr><td>Jul 2027 - 2029</td><td>Work 2-4 years, then join the school</td><td>Work; aim for a promotion and results you can put numbers on</td></tr>
      <tr><td>Sep 2029</td><td>—</td><td><b>Round 1</b> to 5-7 schools (best round for internationals and scholarships); Round 2 in Jan 2030</td></tr>
    </tbody></table></div>
    <p class="muted sectionnote" style="margin-top:8px">US schools have one intake (Aug-Sep) with rounds in Sep, Jan and Apr. January ("spring") starts exist only at Columbia J-Term,
      INSEAD and HEC Paris; ISB and the IIM one-year programmes start in April. Today, Round 1 for Fall 2027 has closed and <b>Round 2 (early January 2027) is open</b>.</p>

    <h2 class="section">GMAT: dates, fees, format</h2>
    <div class="tablewrap"><table><tbody>
      <tr><th>Dates</th><td>No fixed attempts and no "four times a year": it runs almost every day, at a Pearson VUE centre (Mumbai, Pune…) or online. Book 2-4 weeks ahead on mba.com.</td></tr>
      <tr><th>Retakes</th><td>At least 16 days apart · at most 5 in 12 months · 8 in a lifetime · you choose which score to send · scores valid 5 years</td></tr>
      <tr><th>Fee</th><td>$275 at a centre, $300 online (India may add 18% GST, ~₹27-30k) · reschedule $55-$165 · score report $35 each after the 5 free ones</td></tr>
      <tr><th>Format</th><td>2 h 15 min, 3 sections × 45 min, in any order you choose: <b>Quant</b> 21 Q (no geometry, no calculator) · <b>Verbal</b> 23 Q (reading comprehension, critical reasoning) ·
        <b>Data Insights</b> 20 Q (data sufficiency, tables, graphs, multi-source; calculator allowed). Score 205-805; you can review and change up to 3 answers per section.</td></tr>
      <tr><th>Take it by</th><td>~20 Dec 2026 for US Round 2 · Jan-Feb 2027 for deferred programmes · before Mar 2029 for Route B</td></tr>
      <tr><th>Prep</th><td>GMAT Official Guide (Focus Edition) and the Quant, Verbal and DI review books, the 6 official practice exams, the GMAT Club question bank; Target Test Prep (Quant), e-GMAT (Verbal)</td></tr>
    </tbody></table></div>

    <h2 class="section">Paying for it</h2>
    <div class="tablewrap"><table><thead><tr><th>Source</th><th>What it gives</th></tr></thead><tbody>
      <tr><td>HBS / Stanford</td><td>Need-based only: avg ~$45-47k a year; Knight-Hennessy (Stanford) covers the full cost</td></tr>
      <tr><td>Wharton, Booth, Kellogg, Columbia, Ross, Darden, Fuqua, Tepper, Stern</td><td>Merit awards, $10k to full tuition. A high GMAT and applying in Round 1 bring the most. Many schools reconsider an award if you show a better offer from a peer school</td></tr>
      <tr><td>Cornell Park Fellowship · Oxford Pershing Square · Chevening (UK)</td><td>Full tuition (and living costs for Pershing Square and Chevening)</td></tr>
      <tr><td>JN Tata Endowment · K.C. Mahindra · Aga Khan</td><td>Indian loan scholarships and grants, about ₹1-10 L; apply Jan-Mar of the year you go</td></tr>
      <tr><td>School loans, Prodigy, MPOWER, SBI / Credila / Avanse</td><td>Loans with no cosigner (top US schools) or with collateral (Indian banks, up to ~₹1.5 Cr; interest is tax-deductible under Sec 80E)</td></tr>
      <tr><td>Cheaper routes</td><td>One-year programmes (INSEAD, Oxford, Cambridge, ISB, Kellogg 1Y, Cornell Tech) halve the salary you give up; the US summer internship pays ~$35-50k</td></tr>
    </tbody></table></div>
    <p class="muted sectionnote" style="margin-top:8px">Figures are approximate for the 2026-27 cycle, as of Oct 2026. Check each school's own site before relying on one.
      The full write-up is in the repo under admissions/MBA-admissions/.</p>`;
}

function viewMba() {
  const f = S.mf, list = MBA_SCHOOLS.filter(mbaMatches).sort((a, b) =>
    f.sort === "cost" ? mbaCost(a) - mbaCost(b) : f.sort === "fit" ? FIT_ORDER[a.fit] - FIT_ORDER[b.fit] || b.avg_gmat_focus - a.avg_gmat_focus
      : b.avg_gmat_focus - a.avg_gmat_focus);
  const regions = [...new Set(MBA_SCHOOLS.map(s => s.region))].map(r => [r, r]);
  $("#view").innerHTML = `
    <div class="controls">
      <input type="search" id="m-q" placeholder="Search school, country or scholarship" value="${esc(f.q)}" aria-label="Search schools">
      <select id="m-region" aria-label="Region">${opts([["all", "Every region"], ...regions], f.region)}</select>
      <select id="m-fit" aria-label="Fit">${opts([["all", "Every fit"], ["Reach", "Reach"], ["Stretch", "Stretch"], ["Target", "Target"],
                                                  ["Likely", "Likely"], ["Later option", "Later option"]], f.fit)}</select>
      <select id="m-intake" aria-label="Intake">${opts([["any", "Any intake"], ["fall", "Fall intake"], ["spring", "January / spring intake"]], f.intake)}</select>
      <select id="m-sort" aria-label="Sort">${opts([["gmat", "Class GMAT, highest first"], ["fit", "Best fit first"], ["cost", "Cheapest first"]], f.sort)}</select>
      <label><input type="checkbox" id="m-ivy" ${f.ivy ? "checked" : ""}> Ivy League only</label>
      <label><input type="checkbox" id="m-early" ${f.early ? "checked" : ""}> Deferred route for students</label>
      <span class="count">${list.length} shown</span>
    </div>
    <div class="listhead"><p>Top business schools in the US, UK, Europe, Asia and Canada for an IIT Bombay B.Tech graduating in 2027 (CGPA 6.56).
      <b>Fit</b> assumes the target GMAT shown on each school and 3-4 years of good work experience, or applying through a deferred programme.</p></div>
    <div class="list">${list.length ? list.map(mbaCard).join("") : `<div class="empty">No schools match these filters.</div>`}</div>
    ${mbaGuide()}`;
  const bind = (id, key, ev = "change", get = el => el.value) => $(id)?.addEventListener(ev, e => {
    S.mf[key] = get(e.target); store.set("jt-mfilters", S.mf);
    if (key === "q") { clearTimeout(viewMba.t); viewMba.t = setTimeout(() => { viewMba(); const q = $("#m-q"); q.focus(); q.setSelectionRange(q.value.length, q.value.length); }, 200); }
    else viewMba();
  });
  bind("#m-q", "q", "input");
  ["region", "fit", "intake", "sort"].forEach(k => bind(`#m-${k}`, k));
  bind("#m-ivy", "ivy", "change", el => el.checked);
  bind("#m-early", "early", "change", el => el.checked);
}

// ---------------------------------------------------------------- other tabs

function viewMine() {
  const me = S.me.user_id;
  const jobsBy = new Map(S.jobs.map(j => [j.key, j]));
  const mine = [...S.apps.values()].filter(a => forMe(a.job_key) && (a.claimed_by === me || a.applied_by === me))
    .sort((x, y) => (y.updated_at || "").localeCompare(x.updated_at || ""));
  const claimed = mine.filter(a => a.status === "claimed"), rest = mine.filter(a => a.status !== "claimed");
  const block = (title, list, hint) => `<h2 style="margin-top:8px">${title}</h2><p class="muted" style="margin:0 0 10px">${hint}</p>
    <div class="list">${list.length ? list.map(a => jobsBy.get(a.job_key)).filter(Boolean).map(card).join("") : `<div class="empty">Nothing here.</div>`}</div>`;
  $("#view").innerHTML = block("Claimed by you", claimed, `Apply or release these; a claim lapses after ${claimHours()} hours.`)
    + `<div style="height:24px"></div>` + block("Your applications", rest, "Update them when you hear back.");
}

function eventLine(e) {
  const j = S.jobs.find(x => x.key === e.job_key);
  const what = (isComp(j)
    ? { claimed: "took on", registered: "registered for", released: "released", skipped: "is not doing", interview: "went through a round of",
        offer: "won", rejected: "went out of", withdrawn: "dropped", note: "left a note on", reset: "reset" }
    : { claimed: "claimed", applied: "applied to", released: "released", skipped: "skipped", interview: "got an interview for",
        offer: "got an offer for", rejected: "was rejected for", withdrawn: "withdrew from", note: "left a note on",
        added: "added", reset: "reset" })[e.action] || e.action;
  const job = j ? `<b>${esc(j.title)}</b> ${isComp(j) ? "by" : "at"} ${esc(j.company)}` : esc(e.job_key || "");
  const extra = e.detail ? (e.action === "applied" ? ` with the <b>${esc(e.detail)}</b> resume`
                            : e.action === "registered" ? ` with ${esc(e.detail)}` : `: ${esc(e.detail)}`) : "";
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
    case "cand": S.cand = el.dataset.cand; store.set("jt-cand", S.cand); S.shown = 60; S.cshown = 40; render(); break;
    case "more": S.shown += 60; viewJobs(); break;
    case "cmore": S.cshown += 40; viewComps(); break;
    case "imore": S.ishown += 60; viewIndia(); break;
    case "omore": S.oshown += 60; viewOverseas(); break;
    case "claim": {
      const others = isComp(j) ? [] : sameCompany(j);
      if (others.length && !confirm(`${others.length} other application(s) at ${j.company} already. Claim this one too?`)) break;
      const a = await call("japan_claim", { p_job: key }, isComp(j) ? `Yours to register within ${claimHours()} hours.`
                                                                    : `Claimed. You have ${claimHours()} hours to apply.`);
      if (a) { S.apps.set(key, a); render(); }
      break;
    }
    case "apply": applyDialog(j); break;
    case "register": registerDialog(j); break;
    case "skip": textDialog(isComp(j) ? "Not doing this one" : "Not a fit", "Why? (helps the others)",
                            isComp(j) ? "e.g. clashes with end-sems, MBA only after all" : "e.g. needs N2 Japanese, 3+ years required", async text => {
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
    case "addcomp": addCompDialog(); break;
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
  const a = await call("japan_set_status", { p_job: key, p_status: status, p_note: "" }, `Marked ${statusOf(jobOf(key), status)[0].toLowerCase()}`);
  if (a) { S.apps.set(key, a); render(); } else el.value = "";
});

boot();
