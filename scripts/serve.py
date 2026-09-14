"""Serve the tracker and its dashboard on this Mac.

  http://127.0.0.1:8765                   the roles page
  http://127.0.0.1:8765/dashboard.html    applications, runs, sources, data, settings

The page on GitHub Pages can only re-read the three board APIs from a browser.
Served from here, Refresh runs scripts/refresh.sh on this machine instead, and
application status lives in private/tracker.db rather than one browser.

Reads
  GET  /api/status              run in progress, its log tail, search cooldown
  GET  /api/overview            the numbers on the dashboard's first tab
  GET  /api/applications        every tracked application, with its role
  GET  /api/timeline?key=       one application's history
  GET  /api/file?key=&name=     a tailored resume or its notes
  GET  /api/runs                every pipeline run, newest first
  GET  /api/log?name=           one run's log
  GET  /api/sources             what each board and job site returned
  GET  /api/history             new and closed roles per day
  GET  /api/data                every file the tracker keeps, and where
  GET  /api/settings            graduation year, refresh time, key present
  GET  /api/tasks               resume-tailoring runs
Writes (only from this server's own pages)
  POST /api/refresh             start a pipeline run
  POST /api/applications        create or update one application
  POST /api/applications/delete
  POST /api/applications/import  marks a browser saved before the dashboard existed
  POST /api/settings
  POST /api/tailor              screen and tailor the resume for one role

Listens on 127.0.0.1 only, answers only requests addressed to 127.0.0.1 or
localhost (which defeats DNS rebinding), accepts writes only from its own
origin, and never serves private/ directly.
"""

from __future__ import annotations

import json
import os
import posixpath
import re
import subprocess
import sys
import threading
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths
import store
from fetch_jobs import INDIA, entry_level_business

PORT = int(os.environ.get("PT_PORT", "8765"))
HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
ORIGINS = {f"http://{h}" for h in HOSTS}
HIDDEN = ("/private", "/.git", "/.venv", "/data/archive", "/data/raw")
PY = str(paths.ROOT / ".venv" / "bin" / "python")
LABEL_DAILY = "com.pttracker.daily"


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def hidden(raw_path: str) -> bool:
    # Decode and normalise first, or /%70rivate and /data/../private walk past the check.
    path = posixpath.normpath(unquote(urlsplit(raw_path).path)).lower()
    return any(path == h or path.startswith(h + "/") for h in HIDDEN)


_cache: dict[str, tuple[float, object]] = {}
_cache_lock = threading.Lock()


def load(path: Path, fallback):
    """JSON from disk, re-read only when the file changes. all_postings.json is 5 MB."""
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        return fallback
    with _cache_lock:
        hit = _cache.get(str(path))
        if hit and hit[0] == mtime:
            return hit[1]
    try:
        value = json.loads(path.read_text())
    except json.JSONDecodeError:
        return fallback
    with _cache_lock:
        _cache[str(path)] = (mtime, value)
    return value


def pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def running() -> bool:
    try:
        return pid_alive(int((paths.RUN_LOCK / "pid").read_text()))
    except (FileNotFoundError, ValueError):
        return False


def fits_grad(role: dict, year: int) -> bool:
    named = role.get("batches") or []
    if named:
        return year in named
    return role.get("kind") == "internship" or role.get("tier") != "walled"


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n} B"


# --------------------------------------------------------------------------
# Runs and search status
# --------------------------------------------------------------------------

PROBLEM = re.compile(r"failed|traceback|error|not permitted|returned nothing|treating as blocked", re.I)


def parse_run(path: Path) -> dict:
    lines = [l for l in path.read_text(errors="replace").splitlines() if " - INFO - " not in l]
    started = next((l for l in lines if l.startswith("started ")), "")
    finished = next((l for l in lines if l.startswith("finished ")), "")
    m_start = re.match(r"started (\S+ \S+)(?: via (\S+))?", started)
    m_end = re.match(r"finished (\S+ \S+) exit (\d+)", finished)
    begin = datetime.fromisoformat(m_start.group(1)) if m_start else None
    end = datetime.fromisoformat(m_end.group(1)) if m_end else None
    alive = not m_end and running() and path.resolve() == (paths.LOGS / "latest.log").resolve()
    return {
        "name": path.name,
        "started": begin.isoformat() if begin else None,
        "finished": end.isoformat() if end else None,
        "seconds": int((end - begin).total_seconds()) if begin and end else None,
        "trigger": (m_start.group(2) if m_start else None) or "unrecorded",
        "state": "running" if alive else ("ok" if m_end and m_end.group(2) == "0"
                                          else ("failed" if m_end else "interrupted")),
        "steps": [l[3:] for l in lines if l.startswith("== ")],
        "problems": [l.strip() for l in lines if PROBLEM.search(l)][:12],
        "summary": [l.strip() for l in lines if re.search(r"postings total|search roles merged|business-track roles", l)],
        "searched": any(l.startswith("searching ") for l in lines),
    }


def runs() -> list[dict]:
    files = sorted(paths.LOGS.glob("20*.log"), reverse=True) if paths.LOGS.exists() else []
    return [parse_run(f) for f in files]


def status() -> dict:
    meta = load(paths.SEARCH_META, {})
    allowed = meta.get("next_after")
    latest = paths.LOGS / "latest.log"
    tail = []
    if latest.exists():
        tail = [l for l in latest.read_text(errors="replace").splitlines()
                if " - INFO - " not in l and l.strip()][-12:]
    return {
        "running": running(),
        "log": tail,
        "searched_at": meta.get("searched_at"),
        "next_search_after": allowed,
        "search_allowed_now": not allowed or datetime.fromisoformat(allowed) <= datetime.now(timezone.utc),
        "counts": meta.get("counts", {}),
        "blocked": meta.get("blocked", []),
    }


def schedule() -> dict:
    installed = subprocess.run(["launchctl", "print", f"gui/{os.getuid()}/{LABEL_DAILY}"],
                               capture_output=True).returncode == 0
    return {"installed": installed, "time": store.settings()["refresh_time"]}


def start_refresh(trigger: str) -> None:
    subprocess.Popen([str(paths.ROOT / "scripts" / "refresh.sh")], cwd=paths.ROOT,
                     env={**os.environ, "PT_TRIGGER": trigger},
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


# --------------------------------------------------------------------------
# Overview, applications, sources, history, data
# --------------------------------------------------------------------------

def roles_by_key() -> dict[str, dict]:
    return {r["key"]: r for r in load(paths.SITE_DATA, {}).get("roles", [])}


def overview() -> dict:
    site = load(paths.SITE_DATA, {})
    roles = site.get("roles", [])
    year = store.settings()["grad_year"]
    today = date.today().isoformat()
    db = store.connect()
    apps = store.applications(db)
    history = runs()
    return {
        "generated": site.get("generated"),
        "grad_year": year,
        "roles": len(roles),
        "open_to_grad": sum(fits_grad(r, year) for r in roles),
        "new_today": sum(r.get("first_seen") == today for r in roles),
        "internships": sum(r.get("kind") == "internship" for r in roles),
        "tier1": sum(r.get("city_tier") == "Tier 1" for r in roles),
        "tiers": Counter(r.get("tier") for r in roles),
        "by_source": Counter(r.get("ats") for r in roles),
        "applications": store.counts(db),
        "labels": store.LABELS,
        "follow_ups": [a for a in apps if a.get("follow_up") and a["follow_up"] <= today
                       and a["status"] in ("applied", "interview")],
        "last_run": history[0] if history else None,
        "runs_7d": sum(1 for r in history if r["started"] and r["started"][:10] >= (
            date.fromordinal(date.today().toordinal() - 6)).isoformat()),
        "failed_7d": sum(1 for r in history[:14] if r["state"] == "failed"),
        "schedule": schedule(),
        "search": status(),
        "boards": len(load(paths.BOARDS, [])),
    }


def applications() -> list[dict]:
    db = store.connect()
    store.import_legacy(db)
    roles = roles_by_key()
    seen = load(paths.SEEN, {})
    out = []
    for a in store.applications(db):
        role = roles.get(a["key"], {})
        hist = seen.get(a["key"], {})
        listed = "listed" if a["key"] in roles else ("closed" if hist.get("closed") else "not in latest pull")
        out.append({**a, "role": {k: role.get(k) for k in (
            "tier", "min_years", "posted", "city", "city_tier", "kind", "batches", "family", "funded", "pay", "location")},
            "listing": listed if not a["key"].startswith("manual:") else "added by hand",
            "files": sorted(p.name for p in (paths.ROOT / a["folder"]).iterdir())
            if a.get("folder") and (paths.ROOT / a["folder"]).is_dir() else []})
    return out


def sources() -> dict:
    postings = load(paths.POSTINGS, [])
    boards = load(paths.BOARDS, [])
    roles = load(paths.SITE_DATA, {}).get("roles", [])
    in_roles = Counter((r["ats"], r["key"].split(":")[1]) for r in roles)
    per = defaultdict(lambda: {"postings": 0, "india": 0, "business": 0})
    for p in postings:
        k = (p["ats"], p["slug"])
        per[k]["postings"] += 1
        if INDIA.search(p.get("location") or ""):
            per[k]["india"] += 1
            if entry_level_business(p.get("title") or ""):
                per[k]["business"] += 1
    board_rows = [{"ats": b["ats"], "slug": b["slug"], **per[(b["ats"], b["slug"])],
                   "shown": in_roles[(b["ats"], b["slug"])]} for b in boards]
    board_rows.sort(key=lambda r: -r["postings"])
    meta = load(paths.SEARCH_META, {})
    sites = []
    for site in sorted({*meta.get("counts", {}), *(r["ats"] for r in roles if r.get("source") == "search")}):
        sites.append({"site": site, "found": meta.get("counts", {}).get(site),
                      "shown": sum(1 for r in roles if r["ats"] == site),
                      "blocked": site in meta.get("blocked", [])})
    return {"boards": board_rows, "sites": sites, "search": status(),
            "not_used": [
                {"site": "Glassdoor", "why": "Answers 403 from behind bot protection. Getting past it means "
                                             "disguising the scraper, which is how IPs get banned."},
                {"site": "Naukri", "why": "Demands a recaptcha, which cannot be passed without the same disguise."},
                {"site": "Google Jobs", "why": "Returned no results for India searches when tried on 2026-09-14."},
            ]}


def history() -> dict:
    seen = load(paths.SEEN, {})
    new = defaultdict(lambda: {"board": 0, "search": 0})
    closed = Counter()
    for key, rec in seen.items():
        source = "search" if key.split(":", 1)[0] in {"linkedin", "indeed", "naukri", "glassdoor", "google"} else "board"
        if rec.get("first_seen"):
            new[rec["first_seen"]][source] += 1
        if rec.get("closed") and rec.get("closed_on"):
            closed[rec["closed_on"]] += 1
    tracked = {}
    for f in sorted(paths.HISTORY.glob("*.json")):
        try:
            tracked[f.stem] = len(json.loads(f.read_text()))
        except json.JSONDecodeError:
            pass
    days = sorted({*new, *closed, *tracked})
    return {"days": [{"day": d, "new_board": new[d]["board"], "new_search": new[d]["search"],
                      "closed": closed[d], "tracked": tracked.get(d)} for d in days],
            "total": len(seen), "live": sum(1 for r in seen.values() if not r.get("closed"))}


DATA_ITEMS = [
    # path, what it is, who can see it
    ("data/latest.json", "Everything the roles page shows: roles, funding rounds, coverage", "public"),
    ("data/seen.json", "Every role ever seen, with first seen, last seen and closed dates", "public"),
    ("data/history", "One file per day: the roles live that day", "public"),
    ("data/search_cache.json", "Last LinkedIn and Indeed results, without descriptions", "public"),
    ("data/boards.json", "Company career boards that are pulled", "public"),
    ("data/funding.json", "Every funding round ingested", "public"),
    ("data/benchmarks.json", "Entry-level salary bands", "public"),
    ("pt-tracker-all.json", "The whole dataset in one file", "public"),
    ("pt-tracker-all.csv", "The same, one row per estimated role", "public"),
    ("data/raw/all_postings.json", "Every posting from the last run, with descriptions", "local"),
    ("data/raw/search_postings.json", "Last LinkedIn and Indeed results, with descriptions", "local"),
    ("data/archive", "Every LinkedIn and Indeed search, gzipped", "local"),
    ("data/raw/logs", "One log per pipeline run", "local"),
    ("private/tracker.db", "Your applications, statuses, notes and timeline", "private"),
    ("private/resume.md", "Your master resume", "private"),
    ("private/applications", "One folder per tailored resume", "private"),
    ("private/settings.json", "Graduation year and refresh time", "private"),
    ("private/.env", "Your Gemini key", "private"),
]
VISIBILITY = {
    "public": "Committed to git; published if you push",
    "local": "This Mac only, not in git",
    "private": "This Mac only, never committed or served",
}


def data_inventory() -> dict:
    items = []
    for rel, what, vis in DATA_ITEMS:
        p = paths.ROOT / rel
        entry = {"path": rel, "what": what, "visibility": vis, "exists": p.exists(),
                 "view": rel if vis == "public" and p.is_file() else None}
        if p.is_dir():
            files = [f for f in p.rglob("*") if f.is_file()]
            entry.update(size=human_size(sum(f.stat().st_size for f in files)),
                         records=f"{len(files)} file{'' if len(files) == 1 else 's'}",
                         modified=datetime.fromtimestamp(max((f.stat().st_mtime for f in files), default=p.stat().st_mtime)).isoformat(timespec="minutes"))
        elif p.is_file():
            st = p.stat()
            entry.update(size=human_size(st.st_size), modified=datetime.fromtimestamp(st.st_mtime).isoformat(timespec="minutes"))
            if p.suffix == ".json" and vis != "private" and st.st_size < 20_000_000:
                value = load(p, None)
                if isinstance(value, dict) and isinstance(value.get("roles"), list):
                    entry["records"] = f"{len(value['roles']):,} roles"
                elif isinstance(value, dict) and isinstance(value.get("open_roles"), list):
                    entry["records"] = f"{len(value['open_roles']):,} roles, {len(value.get('companies', [])):,} companies"
                elif isinstance(value, list) or (isinstance(value, dict) and len(value) > 20):
                    entry["records"] = f"{len(value):,} records"
        items.append(entry)
    return {"root": str(paths.ROOT), "items": items, "visibility": VISIBILITY}


# --------------------------------------------------------------------------
# Settings and tailoring
# --------------------------------------------------------------------------

def settings() -> dict:
    return {**store.settings(), "gemini_key_set": bool(store.env().get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")),
            "resume": paths.RESUME.exists(), "schedule": schedule(), "root": str(paths.ROOT)}


def rebuild_page() -> None:
    """build_data + render: no network, a second or two."""
    def work():
        for script in ("build_data.py", "render.py"):
            subprocess.run([PY, str(paths.ROOT / "scripts" / script)], cwd=paths.ROOT, capture_output=True)
    threading.Thread(target=work, daemon=True).start()


_tasks: dict[int, subprocess.Popen] = {}


def tasks() -> list[dict]:
    db = store.connect()
    out = []
    for row in db.execute("SELECT * FROM tasks ORDER BY id DESC LIMIT 30"):
        t = dict(row)
        proc = _tasks.get(t["id"])
        if t["finished_at"] is None:
            code = proc.poll() if proc else (None if pid_alive(t["pid"]) else -1)
            if code is not None:
                db.execute("UPDATE tasks SET finished_at = ?, exit_code = ? WHERE id = ?", (store.now(), code, t["id"]))
                db.commit()
                t.update(finished_at=store.now(), exit_code=code)
        t["running"] = t["finished_at"] is None
        try:
            t["output"] = [l for l in Path(t["log"]).read_text(errors="replace").splitlines() if l.strip()][-15:]
        except (FileNotFoundError, TypeError):
            t["output"] = []
        out.append(t)
    return out


def start_tailor(key: str) -> tuple[dict, int]:
    if key not in roles_by_key():
        return {"error": "That role is not in the latest pull, so there is no posting to tailor against."}, 400
    if not (store.env().get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")):
        return {"error": "Add your Gemini key in Settings first."}, 400
    if not paths.RESUME.exists():
        return {"error": "No master resume at private/resume.md."}, 400
    if any(t["running"] for t in tasks()):
        return {"error": "A tailoring run is already going; wait for it to finish."}, 409
    logs = paths.PRIVATE / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log = logs / f"tailor-{datetime.now():%Y%m%d-%H%M%S}.log"
    fh = open(log, "w")
    proc = subprocess.Popen([PY, str(paths.ROOT / "scripts" / "apply.py"), "--key", key, "--force"],
                            cwd=paths.ROOT, env={**os.environ, **store.env()},
                            stdout=fh, stderr=subprocess.STDOUT, start_new_session=True)
    db = store.connect()
    cur = db.execute("INSERT INTO tasks (kind, key, pid, log, started_at) VALUES ('tailor', ?, ?, ?, ?)",
                     (key, proc.pid, str(log), store.now()))
    db.commit()
    _tasks[cur.lastrowid] = proc
    return {"started": True, "task": cur.lastrowid}, 200


FILE_TYPES = {
    "resume.html": "text/html; charset=utf-8", "resume.md": "text/plain; charset=utf-8",
    "changes.md": "text/plain; charset=utf-8", "posting.md": "text/plain; charset=utf-8",
    "fit.json": "application/json", "email.eml": "message/rfc822",
    "resume.docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

class Handler(SimpleHTTPRequestHandler):
    # Without a charset the browser guesses Windows-1252 and "·" turns into "Â·".
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map,
                      ".html": "text/html; charset=utf-8", ".json": "application/json; charset=utf-8",
                      ".js": "text/javascript; charset=utf-8", ".csv": "text/csv; charset=utf-8",
                      ".md": "text/plain; charset=utf-8"}

    def _json(self, body, code: int = 200) -> None:
        data = json.dumps(body, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > 1_000_000:
            raise ValueError("request too large")
        return json.loads(self.rfile.read(length) or b"{}")

    def end_headers(self) -> None:
        if self.path.startswith("/data/") or self.path.endswith(".html") or self.path == "/":
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self) -> None:
        url = urlsplit(self.path)
        if url.path.startswith("/api/"):
            if self.headers.get("Host") not in HOSTS:
                return self._json({"error": "wrong host"}, 403)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            try:
                return self.api_get(url.path, q)
            except Exception as exc:  # a broken read should say so, not hang the page
                return self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)
        if hidden(self.path):
            return self.send_error(HTTPStatus.NOT_FOUND)
        return super().do_GET()

    def api_get(self, path: str, q: dict) -> None:
        if path == "/api/status":
            return self._json(status())
        if path == "/api/overview":
            return self._json(overview())
        if path == "/api/applications":
            return self._json({"applications": applications(), "statuses": store.STATUSES, "labels": store.LABELS})
        if path == "/api/timeline":
            return self._json(store.timeline(store.connect(), q.get("key", "")))
        if path == "/api/runs":
            return self._json({"runs": runs(), "status": status(), "schedule": schedule()})
        if path == "/api/log":
            name = q.get("name", "")
            f = paths.LOGS / name
            if not re.fullmatch(r"20[\d-]+\.log", name) or not f.exists():
                return self._json({"error": "no such log"}, 404)
            return self._json({"name": name, "lines": [l for l in f.read_text(errors="replace").splitlines()
                                                       if " - INFO - " not in l]})
        if path == "/api/sources":
            return self._json(sources())
        if path == "/api/history":
            return self._json(history())
        if path == "/api/data":
            return self._json(data_inventory())
        if path == "/api/settings":
            return self._json(settings())
        if path == "/api/tasks":
            return self._json(tasks())
        if path == "/api/file":
            return self.send_application_file(q.get("key", ""), q.get("name", ""))
        return self._json({"error": "not found"}, 404)

    def send_application_file(self, key: str, name: str) -> None:
        app = store.get(store.connect(), key)
        if not app or not app.get("folder") or name not in FILE_TYPES:
            return self._json({"error": "no such file"}, 404)
        folder = (paths.ROOT / app["folder"]).resolve()
        f = (folder / name).resolve()
        if paths.APPLICATIONS.resolve() not in f.parents or not f.is_file():
            return self._json({"error": "no such file"}, 404)
        data = f.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", FILE_TYPES[name])
        if name.endswith((".docx", ".eml")):
            self.send_header("Content-Disposition", f'attachment; filename="{name}"')
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_HEAD(self) -> None:
        if hidden(self.path) or self.path.startswith("/api/"):
            return self.send_error(HTTPStatus.NOT_FOUND)
        return super().do_HEAD()

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        if self.headers.get("Host") not in HOSTS or self.headers.get("Origin") not in ORIGINS:
            return self._json({"error": "writes are only accepted from the tracker's own pages"}, 403)
        try:
            body = self._body()
            return self.api_post(path, body)
        except ValueError as exc:
            return self._json({"error": str(exc)}, 400)
        except Exception as exc:
            return self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)

    def api_post(self, path: str, body: dict) -> None:
        db = store.connect()
        if path == "/api/refresh":
            if running():
                return self._json({"started": False, "running": True}, 409)
            start_refresh("dashboard" if "dashboard" in (self.headers.get("Referer") or "") else "page")
            return self._json({"started": True, **status()})

        if path == "/api/applications":
            key = (body.get("key") or "").strip()
            if not key:
                title = (body.get("title") or "").strip()
                company = (body.get("company") or "").strip()
                if not (title and company):
                    raise ValueError("a new application needs a company and a title")
                slug = re.sub(r"[^a-z0-9]+", "-", f"{company} {title}".lower()).strip("-")[:60]
                key = f"manual:{slug}:{datetime.now():%Y%m%d%H%M%S}"
            role = roles_by_key().get(key, {})
            fields = {k: body[k] for k in store.FIELDS if k in body}
            # Fill the role's details from the pull the first time it is tracked.
            if not store.get(db, key) and role:
                for f, rk in (("company", "company"), ("title", "title"), ("url", "url"),
                              ("city", "city"), ("source", "ats")):
                    fields.setdefault(f, role.get(rk))
            return self._json(store.upsert(db, key, **fields))

        if path == "/api/applications/delete":
            store.delete(db, body.get("key", ""))
            return self._json({"deleted": True})

        if path == "/api/applications/import":
            roles = roles_by_key()
            added = 0
            for key, mark in (body.get("marks") or {}).items():
                if store.get(db, key) or mark not in ("shortlist", "applied"):
                    continue
                role = roles.get(key, {})
                store.upsert(db, key, status="saved" if mark == "shortlist" else "applied",
                             company=role.get("company"), title=role.get("title"), url=role.get("url"),
                             city=role.get("city"), source=role.get("ats"))
                added += 1
            return self._json({"imported": added})

        if path == "/api/settings":
            changes = {}
            if "grad_year" in body:
                year = int(body["grad_year"])
                if not 2020 <= year <= 2035:
                    raise ValueError("graduation year looks wrong")
                changes["grad_year"] = year
            if "refresh_time" in body:
                if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", body["refresh_time"]):
                    raise ValueError("refresh time must be HH:MM, 24-hour")
                done = subprocess.run([str(paths.ROOT / "scripts" / "schedule_mac.sh"), "set-time", body["refresh_time"]],
                                      cwd=paths.ROOT, capture_output=True, text=True)
                if done.returncode != 0:
                    raise ValueError(done.stdout.strip() or done.stderr.strip() or "could not change the schedule")
                changes["refresh_time"] = body["refresh_time"]
            if "gemini_key" in body:
                key = (body["gemini_key"] or "").strip()
                if key and not re.fullmatch(r"[A-Za-z0-9_\-]{20,200}", key):
                    raise ValueError("that does not look like a Gemini API key")
                store.save_env("GEMINI_API_KEY", key)
            store.save_settings(**changes)
            if "grad_year" in changes:
                rebuild_page()
            return self._json(settings())

        if path == "/api/tailor":
            result, code = start_tailor(body.get("key", ""))
            return self._json(result, code)

        return self._json({"error": "not found"}, 404)

    def log_message(self, fmt: str, *args) -> None:
        if not self.path.startswith("/api/"):
            sys.stderr.write(f"{self.log_date_time_string()} {fmt % args}\n")


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), partial(Handler, directory=str(paths.ROOT)))
    print(f"pt-tracker on http://127.0.0.1:{PORT}", file=sys.stderr)
    server.serve_forever()


if __name__ == "__main__":
    main()
