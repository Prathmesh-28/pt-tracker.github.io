"""The site's Refresh button, seen from this Mac. Japan/daily.sh uses it to pick up a
refresh someone asked for and to report what the run is doing, which the site shows live.

  refresh_queue.py waiting          exit 0 if someone pressed Refresh and it has not started
  refresh_queue.py start TRIGGER    claim that request, or open one for the schedule; print its id
  refresh_queue.py step ID TEXT     say what the run is doing now
  refresh_queue.py synced ID        a list was synced: the site reloads its jobs
  refresh_queue.py finish ID done|failed

Reads the service-role key from Japan/private/team.env, as sync_jobs.py does. Never fails
the run: if the database cannot be reached, the refresh goes on without reporting.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from sync_jobs import ENV_FILE, env

CANDIDATES = (("prathmesh", "Prathmesh"), ("madhura", "Madhura"))


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Db:
    def __init__(self) -> None:
        cfg = env(ENV_FILE)
        self.base = cfg.get("SUPABASE_URL", "").rstrip("/") + "/rest/v1/"
        self.key = cfg.get("SUPABASE_SERVICE_ROLE_KEY", "")

    def call(self, method: str, path: str, body=None, prefer: str = "return=representation", headers=None):
        req = urllib.request.Request(self.base + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"apikey": self.key, "Authorization": f"Bearer {self.key}",
                                              "Content-Type": "application/json", "Prefer": prefer, **(headers or {})})
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
            return (json.loads(raw) if raw else None), r.headers

    def rows(self, path: str) -> list[dict]:
        return self.call("GET", path)[0] or []

    def patch(self, rid: str, **fields) -> None:
        self.call("PATCH", f"japan_refreshes?id=eq.{int(rid)}", dict(fields, updated_at=now()), prefer="return=minimal")

    def count(self, path: str) -> int:
        _, headers = self.call("GET", path, headers={"Range": "0-0"}, prefer="count=exact")
        return int((headers.get("Content-Range") or "*/0").split("/")[-1] or 0)


def start(db: Db, trigger: str) -> str:
    # A run that went quiet two hours ago died with the Mac; a new one may start.
    quiet = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(timespec="seconds")
    db.call("PATCH", f"japan_refreshes?status=eq.running&updated_at=lt.{quote(quiet)}",
            {"status": "failed", "finished_at": now(), "summary": "Stopped without finishing"}, prefer="return=minimal")
    open_ = db.rows("japan_refreshes?select=id,status&status=in.(queued,running)&order=id.desc&limit=1")
    if open_:
        db.patch(open_[0]["id"], status="running", started_at=now(), step="Starting")
        return str(open_[0]["id"])
    made = db.call("POST", "japan_refreshes", {"trigger": trigger, "status": "running", "started_at": now(),
                                               "step": "Starting"})[0]
    return str(made[0]["id"])


def finish(db: Db, rid: str, status: str) -> None:
    row = db.rows(f"japan_refreshes?select=started_at&id=eq.{int(rid)}")
    since = quote(row[0]["started_at"]) if row and row[0]["started_at"] else quote(now())
    bits = []
    for cid, name in CANDIDATES:
        new = db.count(f"japan_jobs?select=key&candidate=eq.{cid}&kind=not.in.(competition,india)&created_at=gte.{since}")
        open_ = db.count(f"japan_jobs?select=key&candidate=eq.{cid}&kind=not.in.(competition,india)&is_open=eq.true")
        bits.append(f"{name}: {open_:,} open, {new:,} new")
    for kind, label in (("india", "India"), ("competition", "competitions")):
        open_ = db.count(f"japan_jobs?select=key&kind=eq.{kind}&is_open=eq.true")
        if open_:
            new = db.count(f"japan_jobs?select=key&kind=eq.{kind}&created_at=gte.{since}")
            bits.append(f"{label}: {open_:,} open, {new:,} new")
    summary = " · ".join(bits) + ("" if status == "done" else " · some sources failed; the rest is updated")
    db.patch(rid, status=status, finished_at=now(), step="", summary=summary)
    print(summary)


def main() -> None:
    args = sys.argv[1:]
    if not args:
        raise SystemExit(__doc__)
    try:
        db = Db()
        if args[0] == "waiting":
            sys.exit(0 if db.rows("japan_refreshes?select=id&status=eq.queued&limit=1") else 1)
        if args[0] == "start":
            print(start(db, args[1] if len(args) > 1 else "schedule"))
        elif args[0] == "step" and args[1]:
            db.patch(args[1], step=" ".join(args[2:])[:200])
        elif args[0] == "synced" and args[1]:
            row = db.rows(f"japan_refreshes?select=syncs&id=eq.{int(args[1])}")
            db.patch(args[1], syncs=(row[0]["syncs"] if row else 0) + 1)
        elif args[0] == "finish" and args[1]:
            finish(db, args[1], "done" if args[2:3] == ["done"] else "failed")
    except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError) as exc:
        if args[0] == "waiting":
            sys.exit(1)  # offline: nobody can be waiting on us
        print(f"refresh_queue {args[0]}: {type(exc).__name__}: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
