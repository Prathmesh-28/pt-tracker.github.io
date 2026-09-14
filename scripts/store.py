"""Your applications: one SQLite file, private/tracker.db, never committed.

The roles themselves are public job data and live in data/. What you did about
them - saved, tailored a resume, applied, heard back - is yours, so it lives
under private/ with the resume.

  applications   one row per role you are tracking, whatever its stage
  events         every change to an application, oldest first: the timeline
  tasks          resume-tailoring runs started from the dashboard
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, datetime

import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths

DB = paths.PRIVATE / "tracker.db"

# In the order an application moves through them. The last four are endings.
STATUSES = ["saved", "tailored", "applied", "interview", "offer", "rejected", "withdrawn", "skipped"]
LABELS = {
    "saved": "Saved", "tailored": "Resume tailored", "applied": "Applied",
    "interview": "Interviewing", "offer": "Offer", "rejected": "Rejected",
    "withdrawn": "Withdrawn", "skipped": "Not a fit",
}
FIELDS = ["status", "company", "title", "url", "city", "source", "applied_on", "follow_up",
          "notes", "fit_verdict", "fit_score", "fit_reason", "folder"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS applications (
  key TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  company TEXT, title TEXT, url TEXT, city TEXT, source TEXT,
  applied_on TEXT, follow_up TEXT, notes TEXT,
  fit_verdict TEXT, fit_score INTEGER, fit_reason TEXT, folder TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  key TEXT NOT NULL, at TEXT NOT NULL, kind TEXT NOT NULL, detail TEXT
);
CREATE INDEX IF NOT EXISTS events_key ON events(key);
CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL, key TEXT, pid INTEGER, log TEXT,
  started_at TEXT NOT NULL, finished_at TEXT, exit_code INTEGER
);
"""


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    paths.PRIVATE.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript(SCHEMA)
    return db


def applications(db: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in db.execute("SELECT * FROM applications ORDER BY updated_at DESC")]


def get(db: sqlite3.Connection, key: str) -> dict | None:
    row = db.execute("SELECT * FROM applications WHERE key = ?", (key,)).fetchone()
    return dict(row) if row else None


def timeline(db: sqlite3.Connection, key: str) -> list[dict]:
    return [dict(r) for r in db.execute("SELECT at, kind, detail FROM events WHERE key = ? ORDER BY id", (key,))]


def upsert(db: sqlite3.Connection, key: str, **fields) -> dict:
    """Create or update one application, recording what changed as events."""
    fields = {k: v for k, v in fields.items() if k in FIELDS}
    if "status" in fields and fields["status"] not in STATUSES:
        raise ValueError(f"unknown status {fields['status']!r}")
    for day in ("applied_on", "follow_up"):
        if fields.get(day) and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", fields[day]):
            raise ValueError(f"{day} must be YYYY-MM-DD")

    stamp = now()
    current = get(db, key)
    if current is None:
        fields.setdefault("status", "saved")
        cols = ["key", *fields, "created_at", "updated_at"]
        db.execute(f"INSERT INTO applications ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                   [key, *fields.values(), stamp, stamp])
        db.execute("INSERT INTO events (key, at, kind, detail) VALUES (?, ?, 'status', ?)",
                   (key, stamp, fields["status"]))
    else:
        changed = {k: v for k, v in fields.items() if current.get(k) != v}
        if not changed:
            return current
        db.execute(f"UPDATE applications SET {', '.join(f'{k} = ?' for k in changed)}, updated_at = ? WHERE key = ?",
                   [*changed.values(), stamp, key])
        if "status" in changed:
            db.execute("INSERT INTO events (key, at, kind, detail) VALUES (?, ?, 'status', ?)",
                       (key, stamp, changed["status"]))
        if "notes" in changed:
            db.execute("INSERT INTO events (key, at, kind, detail) VALUES (?, ?, 'note', 'notes edited')", (key, stamp))
    # Applying without a date means today.
    if fields.get("status") == "applied" and not (get(db, key) or {}).get("applied_on"):
        db.execute("UPDATE applications SET applied_on = ? WHERE key = ?", (date.today().isoformat(), key))
    db.commit()
    return get(db, key)


def delete(db: sqlite3.Connection, key: str) -> None:
    db.execute("DELETE FROM applications WHERE key = ?", (key,))
    db.execute("INSERT INTO events (key, at, kind, detail) VALUES (?, ?, 'deleted', NULL)", (key, now()))
    db.commit()


def counts(db: sqlite3.Connection) -> dict[str, int]:
    found = dict(db.execute("SELECT status, COUNT(*) FROM applications GROUP BY status").fetchall())
    return {s: found.get(s, 0) for s in STATUSES}


def import_legacy(db: sqlite3.Connection) -> int:
    """Fold private/applications.json, apply.py's old log, into the database once."""
    try:
        log = json.loads(paths.APPLIED_LOG.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return 0
    n = 0
    for key, e in log.items():
        if get(db, key):
            continue
        upsert(db, key, status="tailored" if e.get("folder") else "skipped",
               company=e.get("company"), title=e.get("title"), url=e.get("url"),
               fit_verdict=e.get("verdict"), fit_score=e.get("score"), folder=e.get("folder"))
        n += 1
    paths.APPLIED_LOG.rename(paths.APPLIED_LOG.with_suffix(".imported.json"))
    return n


# --------------------------------------------------------------------------
# Settings: private/settings.json, and the Gemini key in private/.env
# --------------------------------------------------------------------------

SETTINGS = paths.PRIVATE / "settings.json"
ENV = paths.PRIVATE / ".env"
DEFAULTS = {"grad_year": 2027, "refresh_time": "08:00"}


def settings() -> dict:
    try:
        return {**DEFAULTS, **json.loads(SETTINGS.read_text())}
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(DEFAULTS)


def save_settings(**changes) -> dict:
    merged = {**settings(), **{k: v for k, v in changes.items() if k in DEFAULTS}}
    paths.PRIVATE.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(merged, indent=1))
    return merged


def env() -> dict[str, str]:
    try:
        lines = ENV.read_text().splitlines()
    except FileNotFoundError:
        return {}
    pairs = (line.split("=", 1) for line in lines if "=" in line and not line.lstrip().startswith("#"))
    return {k.strip(): v.strip().strip("'\"") for k, v in pairs}


def save_env(key: str, value: str) -> None:
    values = env()
    if value:
        values[key] = value
    else:
        values.pop(key, None)
    paths.PRIVATE.mkdir(parents=True, exist_ok=True)
    ENV.write_text("".join(f"{k}={v}\n" for k, v in values.items()))
    ENV.chmod(0o600)
