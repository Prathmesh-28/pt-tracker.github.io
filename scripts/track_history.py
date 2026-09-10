"""Maintain the recruitment history index across runs.

What the APIs can and cannot tell you:
  CAN  - when a still-open role was first published (Greenhouse first_published,
         Lever createdAt, Ashby publishedAt). That reaches back years.
  CAN  - whether a Greenhouse role was edited after publishing, which separates
         a genuinely new opening from a quietly refreshed old requisition.
  CANNOT - anything about a role that has already closed. A closed posting is
         removed from the feed and is not retrievable.

So history before the first run is limited to what is still open. From the first
run onward this file accumulates the rest: every key gets a first_seen and a
last_seen, and a key that stops appearing is marked closed on the date it went.
"""

from __future__ import annotations

import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths

import json
import pathlib
import sys
from datetime import date, datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
SEEN = paths.SEEN
HISTORY = paths.HISTORY


def load(path: pathlib.Path, fallback):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return fallback


def days_between(a: str, b: str) -> int | None:
    try:
        return (datetime.fromisoformat(b).date() - datetime.fromisoformat(a).date()).days
    except (ValueError, TypeError):
        return None


def main() -> None:
    today = date.today().isoformat()
    postings = load(paths.POSTINGS, [])
    boards = load(paths.BOARDS, [])
    seen = load(SEEN, {})

    current = set()
    for row in postings:
        key = f"{row['ats']}:{row['slug']}:{row['id']}"
        current.add(key)
        record = seen.get(key)
        if record is None:
            seen[key] = {
                "first_seen": today,
                "last_seen": today,
                "posted": row.get("posted") or "",
                "title": row.get("title") or "",
                "company": row.get("slug") or "",
                "location": row.get("location") or "",
                "url": row.get("url") or "",
                "min_years": row.get("min_years"),
                "closed": False,
                "closed_on": "",
                "reposted": bool(row.get("updated") and row.get("posted")
                                 and row["updated"] != row["posted"]),
            }
        else:
            record["last_seen"] = today
            record["closed"] = False
            record["closed_on"] = ""
            record["min_years"] = row.get("min_years")

    # Only a board we still track can tell us a role closed. When a board is
    # dropped (a slug that turned out to be a foreign namesake), its postings
    # vanish from `current` without having closed - marking them closed would
    # invent 200 closures that never happened.
    tracked = {f"{b['ats']}:{b['slug']}" for b in boards}

    newly_closed = 0
    for key, record in seen.items():
        ats, slug, _ = key.split(":", 2)
        if f"{ats}:{slug}" not in tracked:
            record["untracked"] = True
            continue
        if key not in current and not record.get("closed"):
            record["closed"] = True
            record["closed_on"] = today
            newly_closed += 1

    # age_days is how long the employer has had this role published, which is the
    # number that matters: a req open for a year is not the same as one opened
    # last week, however recently the page was scraped.
    for record in seen.values():
        record["age_days"] = days_between(record.get("posted") or "", today)

    SEEN.parent.mkdir(parents=True, exist_ok=True)
    HISTORY.mkdir(parents=True, exist_ok=True)
    SEEN.write_text(json.dumps(seen, indent=1, sort_keys=True))
    (HISTORY / f"{today}.json").write_text(
        json.dumps(sorted(current), indent=0)
    )

    opened_today = sum(1 for r in seen.values() if r["first_seen"] == today)
    live = sum(1 for r in seen.values() if not r["closed"])
    print(f"history: {len(seen)} keys tracked, {live} live, "
          f"{opened_today} first seen today, {newly_closed} closed since last run",
          file=sys.stderr)


if __name__ == "__main__":
    main()
