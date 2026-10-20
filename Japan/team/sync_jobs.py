"""Push the Japan roles and programs into the team tracker's Supabase database.

Takes every role in Japan/data/roles.json without a Japanese requirement, plus the
programs in Japan/programs.json that are not walled off by language or batch, and
upserts them into japan_jobs by key. A job that no longer appears in any source is
marked closed (is_open = false), never deleted, so its application history stays.
The owner's flags (priority, do not apply, notes) are never touched.

One job, one row, however often it is found:
  - the same job found again under another link (LinkedIn one day, Indeed the next) keeps
    the row it already has, so a claim or an application on it still shows;
  - a job the team added by hand is not added a second time when a search finds it;
  - a run that would close an unusual share of the open jobs (a source blocked or down)
    closes none of them and says so, unless --allow-mass-close.

Each run records when it ran and what changed in japan_settings (refreshed_<person>),
which the site shows above the list.

Needs the service-role key, which bypasses row-level security. Keep it out of git:

  Japan/private/team.env
      SUPABASE_URL=https://<project>.supabase.co
      SUPABASE_SERVICE_ROLE_KEY=...

  .venv/bin/python Japan/team/sync_jobs.py                       # Prathmesh's list
  .venv/bin/python Japan/team/sync_jobs.py --candidate madhura   # Madhura's list, from madhura/data
  .venv/bin/python Japan/team/sync_jobs.py --competitions        # Prathmesh's case competitions, from CaseCompetitions/
  .venv/bin/python Japan/team/sync_jobs.py --india               # Prathmesh's India roles with pay, from India/
  .venv/bin/python Japan/team/sync_jobs.py --dry-run             # count what would be sent
  .venv/bin/python Japan/team/sync_jobs.py --env <file>  # use another env file
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
JAPAN = HERE.parent
ROLES = JAPAN / "data" / "roles.json"
PROGRAMS = JAPAN / "programs.json"
ENV_FILE = JAPAN / "private" / "team.env"
MADHURA = JAPAN.parent / "madhura" / "data" / "roles.json"
MADHURA_PROGRAMS = JAPAN.parent / "madhura" / "programs.json"
COMPETITIONS = JAPAN.parent / "CaseCompetitions" / "data" / "competitions.json"
COMPETITION_WATCH = JAPAN.parent / "CaseCompetitions" / "data" / "watchlist.json"
# The full list, campus offers included, is private; the public copy in India/data/ leaves them out.
INDIA_ROLES = JAPAN.parent / "India" / "private" / "roles.json"
BATCH = 500
MASS_CLOSE = 0.3  # closing more than this share of the open jobs in one run means a source failed

DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PROGRAM_LANGUAGE = {"yes": "english_ok", "partly": "unstated", "taught": "japanese_plus"}
PROGRAM_FIT = {"yes": "yes", "partly": "check"}
CORP = re.compile(r"株式会社|有限会社|合同会社|社会福祉法人|学校法人|医療法人|一般社団法人|公益財団法人|npo法人|㈱|\(株\)|"
                  r"\b(?:co|corp|corporation|inc|ltd|llc|kk|k\.k|gk|limited|japan|group|holdings?)\b\.?", re.I)


def env(path: Path) -> dict[str, str]:
    values = dict(os.environ)
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                values.setdefault(k.strip(), v.strip().strip('"'))
    return values


def day(value) -> str | None:
    value = (value or "")[:10]
    return value if DATE.match(value) else None


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9぀-鿿]+", "", (s or "").lower())


def fingerprint(r: dict) -> tuple:
    """The same job whatever link it came from: title and employer, and on Madhura's
    list the place too, since a chain posts the same part-time job at every branch."""
    company = norm(CORP.sub(" ", r.get("company") or ""))[:8]
    place = norm(r.get("location"))[:12] if r["candidate"] == "madhura" else ""
    return r["candidate"], norm(r.get("title")), company, place


def role_rows(now: str) -> list[dict]:
    rows = []
    for r in json.loads(ROLES.read_text()):
        if r.get("language") == "japanese_required":
            continue
        rows.append({
            "key": r["key"], "kind": "role", "company": r.get("company") or "", "title": r.get("title") or "",
            "location": r.get("location") or "", "url": r.get("url") or "", "source": r.get("source") or "",
            "via": r.get("via") or "", "level": r.get("level") or "", "min_years": r.get("min_years"),
            "language": r.get("language") or "", "visa": r.get("visa") or "",
            "residency": bool(r.get("residency")), "grad_2027": r.get("grad_2027") or "",
            "eligibility": (r.get("eligibility") or "")[:600], "deadline": day(r.get("deadline")),
            "track": r.get("track") or "", "posted": day(r.get("posted")), "is_open": True, "synced_at": now,
            "candidate": "prathmesh", "extra": {"india": r["india"]} if r.get("india") else {},
        })
    return rows


MADHURA_EXTRA = ("japanese", "fit", "kansai", "part_time", "ssw", "family", "area", "wage", "foreigners", "students",
                 "native_english", "job_type", "rank", "area_label")


def madhura_rows(now: str) -> list[dict]:
    """Madhura's matches from madhura/find_jobs.py, which stays out of this repo."""
    rows = []
    for r in json.loads(MADHURA.read_text()):
        rows.append({
            "key": r["key"], "kind": "role", "company": r.get("company") or "", "title": r.get("title") or "",
            "location": r.get("location") or "", "url": r.get("url") or "", "source": r.get("source") or "",
            "via": "", "level": r.get("level") if r.get("level") not in (None, "", "unstated") else "entry",
            "min_years": r.get("min_years"), "language": r.get("language") or "", "visa": r.get("visa") or "",
            "residency": False, "grad_2027": "", "eligibility": (r.get("visa_evidence") or "")[:600],
            "deadline": None, "track": r.get("family") or "", "posted": day(r.get("posted")),
            "is_open": True, "synced_at": now, "candidate": "madhura",
            "extra": {k: r.get(k) for k in MADHURA_EXTRA},
        })
    # Her routes in (teaching schools, the Specified Skilled Worker route), checked by hand.
    if MADHURA_PROGRAMS.exists():
        for p in json.loads(MADHURA_PROGRAMS.read_text())["programs"]:
            rows.append({
                "key": f"madhura:program:{p['id']}", "kind": "program", "company": p["org"], "title": p["name"],
                "location": "", "url": p.get("url") or "", "source": "programs", "via": "", "level": "new_grad",
                "min_years": None, "language": "english_ok" if p.get("japanese") == "none" else "unstated",
                "visa": "", "residency": False, "grad_2027": "", "eligibility": p.get("how", "")[:600],
                "deadline": None, "track": p.get("family") or "", "posted": None, "is_open": True,
                "synced_at": now, "candidate": "madhura",
                "extra": {"japanese": p.get("japanese"), "fit": "good", "kansai": False, "part_time": False,
                          "ssw": p["id"].startswith("ssw"), "family": p.get("family"), "job_type": "full-time",
                          "area": "", "wage": "", "foreigners": False, "students": False, "native_english": False,
                          "rank": -1},
            })
    return rows


COMPETITION_EXTRA = ("rank", "band", "band_label", "score", "why", "scope", "campuses_n", "employer", "channels",
                     "prize", "prize_inr", "prize_usd", "winners", "ranks", "team", "mode", "rounds", "registered",
                     "women_only", "paid", "official_email", "festival", "first_seen", "reasons", "who")


def competition_rows(now: str) -> list[dict]:
    """Prathmesh's case competitions, from CaseCompetitions/fetch_competitions.py: only the ranked ones,
    so nothing he cannot enter and no cultural events."""
    rows = []
    for c in json.loads(COMPETITIONS.read_text())["competitions"]:
        if not c.get("rank"):
            continue
        rows.append({
            "key": c["key"], "kind": "competition", "company": c["organiser"] or "Unstop", "title": c["title"],
            "location": c["city"] or ("Online" if c["mode"] == "online" else ""), "url": c["url"],
            "source": "unstop", "via": c["kind"], "level": "", "min_years": None, "language": "", "visa": "",
            "residency": False, "grad_2027": c["fit"],
            "eligibility": "; ".join(x for x in [c["who"], *c["reasons"]] if x)[:600],
            "deadline": day(c["deadline"]), "track": c["band_label"], "posted": day(c["opened"]),
            "is_open": True, "synced_at": now, "candidate": "prathmesh",
            "extra": {**{k: c.get(k) for k in COMPETITION_EXTRA}, "deadline_at": c["deadline"],
                      "summary": (c.get("summary") or "")[:420], "campuses": (c.get("campuses") or [])[:15]},
        })
    return rows


INDIA_EXTRA = ("rank", "family", "priority", "company_type", "ctc", "lo", "hi", "base", "estimate_base", "basis", "points",
               "market", "row_kind", "deadline_line", "notes", "company_url", "fit_why", "funded", "city",
               "employer_tier")
INDIA_VIA = {"linkedin": "LinkedIn", "indeed": "Indeed", "campus": "Campus JAF", "programme": "Programme"}


def india_rows(now: str) -> list[dict]:
    """Prathmesh's India roles, campus offers and programmes, from India/fetch_india.py, with pay."""
    rows = []
    for x in json.loads(INDIA_ROLES.read_text())["roles"]:
        rows.append({
            "key": x["key"], "kind": "india", "company": x["company"] or "", "title": x["title"] or "",
            "location": x.get("city") or x.get("location") or "", "url": x.get("url") or "", "source": x.get("source") or "",
            "via": INDIA_VIA.get(x.get("source"), (x.get("source") or "").title()), "level": "",
            "min_years": x.get("min_years"), "language": "", "visa": "", "residency": False, "grad_2027": x.get("fit") or "",
            "eligibility": (x.get("fit_why") or "")[:600], "deadline": day(x.get("deadline")),
            "track": x.get("family") or "", "posted": day(x.get("posted")), "is_open": True, "synced_at": now,
            "candidate": "prathmesh", "extra": {**{k: x.get(k) for k in INDIA_EXTRA}, "pay_source": x.get("pay_source") or "",
                                                "job_kind": x.get("kind") or ""},
        })
    return rows


def program_rows(now: str) -> list[dict]:
    rows = []
    for p in json.loads(PROGRAMS.read_text())["programs"]:
        if p.get("english_only") == "no" or p.get("fits_2027") == "no" or p.get("status") == "closed":
            continue
        rows.append({
            "key": f"program:{p['id']}", "kind": "program", "company": p["org"], "title": p["name"],
            "location": "", "url": p.get("apply_url") or p.get("source_url") or "", "source": "programs",
            "via": p.get("kind") or "", "level": "new_grad", "min_years": None,
            "language": PROGRAM_LANGUAGE.get(p.get("english_only"), "unstated"), "visa": "",
            "residency": False, "grad_2027": PROGRAM_FIT.get(p.get("fits_2027"), "check"),
            "eligibility": " ".join(x for x in (p.get("fit_note"), p.get("language_note")) if x)[:600],
            "deadline": day(p.get("deadline")), "track": p.get("track") or "", "posted": None,
            "is_open": True, "synced_at": now, "candidate": "prathmesh", "extra": {},
        })
    return rows


def request(method: str, url: str, key: str, body=None, prefer: str = "return=minimal"):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json", "Prefer": prefer})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read() or b"null") if method == "GET" else r.status
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"{method} {url.split('?')[0]} failed: {exc.code} {exc.read().decode()[:400]}")


def get_all(base: str, key: str, path: str) -> list[dict]:
    out = []
    while True:
        page = request("GET", f"{base}/rest/v1/{path}&limit=1000&offset={len(out)}", key)
        out += page
        if len(page) < 1000:
            return out


def link_known(rows: list[dict], known: list[dict], applied: set[str]) -> tuple[list[dict], int, int]:
    """Give a job found under a new link the row it already has, and drop jobs the team added
    by hand. Returns the rows to send, how many were re-linked, and how many were dropped."""
    owner: dict[tuple, dict] = {}
    for k in known:
        fp = fingerprint(k)
        best = owner.get(fp)
        # Of two rows for one job, keep the one with an application, then the open one.
        score = lambda x: (x["key"] in applied, x["kind"] == "manual", x["is_open"], x["synced_at"] or "")
        if best is None or score(k) > score(best):
            owner[fp] = k
    known_keys = {k["key"] for k in known}
    out, taken, relinked, dropped = [], set(), 0, 0
    for r in rows:
        if r["kind"] != "role" or r["key"] in known_keys:
            out.append(r)
            taken.add(r["key"])
            continue
        match = owner.get(fingerprint(r))
        if match and match["kind"] == "manual":
            dropped += 1  # the team added it already
        elif match and match["kind"] == "role" and match["key"] not in taken:
            out.append(dict(r, key=match["key"]))
            taken.add(match["key"])
            relinked += 1
        else:
            out.append(r)
            taken.add(r["key"])
    # A key twice in one upsert fails the whole batch; the first row wins.
    unique = list({r["key"]: r for r in reversed(out)}.values())[::-1]
    return unique, relinked, dropped


def main() -> None:
    args = sys.argv[1:]
    env_path = Path(args[args.index("--env") + 1]) if "--env" in args else ENV_FILE
    competitions, india = "--competitions" in args, "--india" in args
    candidate = args[args.index("--candidate") + 1] if "--candidate" in args and not (competitions or india) else "prathmesh"
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if competitions or india:
        rows = competition_rows(now) if competitions else india_rows(now)
        print(f"{candidate}: {len(rows)} {'competitions' if competitions else 'India roles'} to sync; "
              f"{len({r['key'] for r in rows})} unique keys", file=sys.stderr)
    else:
        rows = madhura_rows(now) if candidate == "madhura" else program_rows(now) + role_rows(now)
        print(f"{candidate}: {len(rows)} jobs to sync ({sum(r['kind'] == 'program' for r in rows)} programs, "
              f"{sum(r['kind'] == 'role' for r in rows)} roles); {len({r['key'] for r in rows})} unique keys",
              file=sys.stderr)
    if "--dry-run" in args:
        return
    # Each run owns its kinds: a job sync never closes a competition or an India role, nor the other way round.
    kinds = ("competition",) if competitions else ("india",) if india else ("role", "program")
    seen_kinds = kinds if competitions or india else ("role", "program", "manual")

    cfg = env(env_path)
    base, key = cfg.get("SUPABASE_URL", "").rstrip("/"), cfg.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not base or not key:
        raise SystemExit(f"Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in {env_path} or the environment.")
    known = get_all(base, key, f"japan_jobs?select=key,kind,title,company,location,is_open,synced_at,candidate"
                               f"&candidate=eq.{candidate}&kind=in.({','.join(seen_kinds)})&order=key")
    applied = {a["job_key"] for a in get_all(base, key, "japan_applications?select=job_key&order=job_key")}
    rows, relinked, dropped = link_known(rows, known, applied)
    known_keys = {k["key"] for k in known}
    sending = {r["key"] for r in rows}
    added = len(sending - known_keys)

    # Every row carries the same keys, so PostgREST never fills a missing column with NULL.
    for i in range(0, len(rows), BATCH):
        request("POST", f"{base}/rest/v1/japan_jobs?on_conflict=key", key, rows[i:i + BATCH],
                prefer="resolution=merge-duplicates,return=minimal")
        print(f"  upserted {min(i + BATCH, len(rows))}/{len(rows)}", file=sys.stderr)

    # Anything from a source that this sync did not send has closed. Team-added jobs and competitions stay open.
    prefix = "comp:unstop:" if competitions else "india:" if india else ""
    was_open = [k for k in known if k["is_open"] and k["kind"] in kinds and k["key"].startswith(prefix)]
    closing = [k for k in was_open if k["key"] not in sending]
    held = len(closing) > max(50, MASS_CLOSE * len(was_open)) and "--allow-mass-close" not in args
    if held:
        print(f"NOT closing {len(closing)} of {len(was_open)} open jobs: that many vanishing at once means a source "
              f"failed, not that the jobs closed. Run with --allow-mass-close if they really did.", file=sys.stderr)
    elif closing:
        request("PATCH", f"{base}/rest/v1/japan_jobs?candidate=eq.{candidate}&kind=in.({','.join(kinds)})"
                f"&is_open=eq.true&synced_at=lt.{quote(now)}{f'&key=like.{prefix}*' if prefix else ''}", key,
                {"is_open": False})
    stats = {"at": now, "jobs": len(rows), "new": added, "closed": 0 if held else len(closing),
             "held": len(closing) if held else 0, "relinked": relinked, "skipped_manual": dropped}
    settings = [{"key": "refreshed_competitions" if competitions else "refreshed_india" if india else f"refreshed_{candidate}",
                 "value": json.dumps(stats)}]
    if competitions and COMPETITION_WATCH.exists():
        # The big competitions between seasons, shown under the list: only what the site shows.
        watch = json.loads(COMPETITION_WATCH.read_text())
        keep = ("name", "url", "leads_to", "employer", "tier", "scope", "last", "next", "before_graduation",
                "for_2027", "for_2027_note", "open_now", "checked")
        watch["entries"] = [{k: e.get(k) for k in keep} for e in watch["entries"]]
        settings.append({"key": "competitions_watch", "value": json.dumps(watch, ensure_ascii=False)})
    request("POST", f"{base}/rest/v1/japan_settings?on_conflict=key", key, settings,
            prefer="resolution=merge-duplicates,return=minimal")
    print(f"done: {len(rows)} open, {added} new, {stats['closed']} closed, {relinked} found again under a new link "
          f"(kept their row), {dropped} already added by the team", file=sys.stderr)


if __name__ == "__main__":
    main()
