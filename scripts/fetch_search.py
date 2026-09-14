"""Pull LinkedIn and Indeed search results through JobSpy and fold them into
the postings file that fetch_jobs.py wrote.

Board feeds only see employers on Greenhouse, Lever or Ashby. Most large Indian
employers run Workday, Darwinbox or Naukri RMS, which publish nothing, so the
job boards are the only way to see them at all.

What differs from the board feeds, and why it matters downstream:
  - A search returns the top N matches, not an employer's full list. A role
    falling out of the results has not closed, so track_history.py never marks
    these closed.
  - Descriptions come back with the search, so enrich.py must not overwrite them.
  - Indeed writes locations as "KA, IN". The India filter needs the word.
  - The same role often sits on the employer's board too. The board row wins.

Tried from an Indian residential IP on 2026-09-14: LinkedIn and Indeed return
results with descriptions. Naukri demands a recaptcha, Glassdoor rejects the
location, Google returns nothing. Hence the default of two sites.

Glassdoor answers 403 behind bot protection and Naukri demands a recaptcha.
Getting past either means impersonating a browser, which is how IPs get banned,
so neither is attempted.

Staying under LinkedIn's radar. JobSpy reads LinkedIn's logged-out job search,
so no account is involved and none can be banned; the risk is the IP being
throttled. So: one site at a time with jittered pauses, a site that comes back
empty twice running is treated as blocked and left alone for the rest of the
run, and no second search within JOBSPY_COOLDOWN_HOURS (4) of the last one,
however often the pipeline runs. A blocked site keeps its results from the last
good run, so a bad morning does not empty the page.

  python scripts/fetch_search.py            # search if the cooldown allows, then merge
  python scripts/fetch_search.py --cached   # merge the last results, no requests
  python scripts/fetch_search.py --force    # search even inside the cooldown

Every search is also archived, gzipped, under data/archive/ on this machine.

Needs Python 3.10+ and `pip install -r requirements.txt`.
"""

from __future__ import annotations

import gzip
import json
import math
import os
import random
import re
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths

# Every site JobSpy can return. Rows from these are search results, not feeds.
SEARCH_SITES = {"linkedin", "indeed", "naukri", "glassdoor", "google", "zip_recruiter", "bayt"}

# Also the hand-run search links on the page, so the two never drift apart.
QUERIES = [
    "business analyst", "associate consultant", "strategy associate",
    "growth analyst", "product analyst", "associate product manager",
    "founder's office", "chief of staff", "category manager",
    "management trainee", "business development associate",
    # Internships, for students who cannot join full-time yet.
    "business analyst intern", "strategy intern", "product management intern",
    "founder's office intern",
]

SITES = [s.strip() for s in os.environ.get("JOBSPY_SITES", "linkedin,indeed").split(",") if s.strip()]
RESULTS = int(os.environ.get("JOBSPY_RESULTS", "30"))      # per query, per site
HOURS_OLD = int(os.environ.get("JOBSPY_HOURS", str(24 * 30)))
PROXIES = [p.strip() for p in os.environ.get("JOBSPY_PROXIES", "").split(",") if p.strip()] or None
PAUSE = 6  # seconds between requests, plus up to as much again at random
BLOCKED_AFTER = 2  # consecutive empty queries before a site is left alone
COOLDOWN_HOURS = float(os.environ.get("JOBSPY_COOLDOWN_HOURS", "4"))


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def val(x) -> str:
    """pandas hands back NaN for missing cells, which is truthy."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return ""
    return str(x).strip()


def location(raw: str) -> str:
    # "KA, IN" and "Remote, IN" -> "KA, India", so INDIA matches.
    return re.sub(r"(^|,\s*)IN$", r"\1India", raw)


def pay(row) -> str:
    lo, hi = row.get("min_amount"), row.get("max_amount")
    lo = None if val(lo) == "" else float(lo)
    hi = None if val(hi) == "" else float(hi)
    if lo is None and hi is None:
        return ""
    currency, interval = val(row.get("currency")), val(row.get("interval"))
    if currency == "INR" and interval == "yearly":
        band = "-".join(f"{v / 1e5:.1f}" for v in (lo, hi) if v is not None)
        return f"{band} LPA"
    band = "-".join(f"{v:,.0f}" for v in (lo, hi) if v is not None)
    return f"{currency} {band} {interval}".strip()


def normalise(row) -> dict | None:
    company = val(row.get("company"))
    title = val(row.get("title"))
    url = val(row.get("job_url"))
    # A listing with no employer name can be neither verified nor pitched.
    if not (company and title and url):
        return None
    site = val(row.get("site"))
    return {
        "ats": site, "id": val(row.get("id")), "slug": norm(company),
        "company": company, "title": title,
        "location": location(val(row.get("location"))),
        "url": url,
        "apply_url": val(row.get("job_url_direct")),
        "posted": val(row.get("date_posted"))[:10],
        "updated": "", "deadline": "",
        "pay": pay(row),
        "team": val(row.get("job_function")),
        "description": val(row.get("description")),
        "job_level": val(row.get("job_level")),
        "job_type": val(row.get("job_type")),
        "company_url": val(row.get("company_url_direct")),
        "emails": val(row.get("emails")),
    }


def search(site: str, query: str) -> list[dict]:
    from jobspy import scrape_jobs

    kwargs = dict(
        site_name=[site], search_term=query, location="India",
        results_wanted=RESULTS, hours_old=HOURS_OLD, country_indeed="India",
        linkedin_fetch_description=True, description_format="markdown",
        proxies=PROXIES, verbose=0,
    )
    try:
        frame = scrape_jobs(**kwargs)
    except Exception as exc:
        print(f"  {site} '{query}' failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return []
    return [r for r in (normalise(rec) for rec in frame.to_dict("records")) if r]


def dedupe(rows: list[dict], boards_only: list[dict]) -> list[dict]:
    # The same role on the employer's board and on LinkedIn: keep the board row,
    # which carries a real first-published date and can be tracked to closure.
    on_boards = set()
    for r in boards_only:
        for name in (r.get("company"), r.get("slug")):
            on_boards.add((norm(name), norm(r["title"])))
    # And the same role on LinkedIn and Indeed: keep whichever came first.
    fresh, seen_pairs = [], set()
    for r in rows:
        pair = (r["slug"], norm(r["title"]))
        if pair in on_boards or pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        fresh.append(r)
    return fresh


def last_results() -> list[dict]:
    """This machine's full copy if it has one, else the compact committed cache."""
    for path in (paths.SEARCH_POSTINGS, paths.SEARCH_CACHE):
        try:
            return json.load(open(path))
        except (FileNotFoundError, json.JSONDecodeError):
            continue
    return []


def save(rows: list[dict]) -> None:
    json.dump(rows, open(paths.SEARCH_POSTINGS, "w"), indent=2)
    # Descriptions are 90% of the size. The committed cache keeps what enrich.py
    # derived from them, so a run that cannot search still tiers these roles.
    from enrich import batches, clean, kind, min_years

    compact = []
    for r in rows:
        text = clean(r.get("description") or "")
        compact.append({**{k: v for k, v in r.items() if k != "description"},
                        "min_years": min_years(text) if text else None,
                        "batches": batches(f"{r['title']} graduates. {text}"),
                        "kind": kind(r)})
    paths.SEARCH_CACHE.write_text(json.dumps(compact, indent=0, sort_keys=True))


def load_meta() -> dict:
    try:
        return json.load(open(paths.SEARCH_META))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def within_cooldown(meta: dict) -> datetime | None:
    """When the next search is allowed, if that is still in the future."""
    if not meta.get("searched_at"):
        return None
    allowed = datetime.fromisoformat(meta["searched_at"]) + timedelta(hours=COOLDOWN_HOURS)
    return allowed if datetime.now(timezone.utc) < allowed else None


def main() -> None:
    args = sys.argv[1:]
    cached = "--cached" in args
    postings = json.load(open(paths.POSTINGS))
    # Idempotent: drop search rows a previous run of this script merged in.
    boards_only = [r for r in postings if r["ats"] not in SEARCH_SITES]
    previous = last_results()

    if not cached and "--force" not in args and (allowed := within_cooldown(load_meta())):
        print(f"LinkedIn and Indeed were searched under {COOLDOWN_HOURS:g}h ago; the next search "
              f"is allowed after {allowed.astimezone():%H:%M}. Merging the last results.",
              file=sys.stderr)
        cached = True

    if cached:
        rows = previous
        print(f"merging {len(rows)} search results from the last run, no requests", file=sys.stderr)
    else:
        try:
            import jobspy  # noqa: F401
        except ImportError:
            print("jobspy is not installed; merging the last results instead. "
                  "Run `pip install -r requirements.txt` on Python 3.10+.", file=sys.stderr)
            rows = previous
        else:
            rows, counts = scrape(previous)
            save(rows)
            archive(rows)
            now = datetime.now(timezone.utc)
            paths.SEARCH_META.write_text(json.dumps({
                "searched_at": now.isoformat(timespec="seconds"),
                "next_after": (now + timedelta(hours=COOLDOWN_HOURS)).isoformat(timespec="seconds"),
                "counts": counts,
                "blocked": [site for site, n in counts.items() if not n],
            }, indent=1))

    fresh = dedupe(rows, boards_only)
    json.dump(boards_only + fresh, open(paths.POSTINGS, "w"), indent=2)

    by_site = Counter(r["ats"] for r in fresh)
    print(f"{len(fresh)} search roles merged "
          f"({', '.join(f'{site} {n}' for site, n in sorted(by_site.items()))})", file=sys.stderr)


def archive(rows: list[dict]) -> None:
    """Keep every search, not just the latest: one gzipped file per run."""
    paths.ARCHIVE.mkdir(parents=True, exist_ok=True)
    name = paths.ARCHIVE / f"{datetime.now():%Y-%m-%d-%H%M}-search.json.gz"
    with gzip.open(name, "wt") as fh:
        json.dump(rows, fh)


def scrape(previous: list[dict]) -> tuple[list[dict], dict[str, int]]:
    print(f"searching {', '.join(SITES)} for {len(QUERIES)} queries", file=sys.stderr)
    found: dict[tuple[str, str], dict] = {}
    counts: dict[str, int] = {}
    for site in SITES:
        empty_run, got = 0, 0
        for i, query in enumerate(QUERIES):
            if empty_run >= BLOCKED_AFTER:
                print(f"  {site}: {BLOCKED_AFTER} empty queries in a row, treating as blocked; "
                      f"skipping the other {len(QUERIES) - i}", file=sys.stderr)
                break
            if i:
                time.sleep(PAUSE + random.uniform(0, PAUSE))
            rows = search(site, query)
            empty_run = 0 if rows else empty_run + 1
            got += len(rows)
            for r in rows:
                found.setdefault((r["ats"], r["id"]), r)
            print(f"  {site} {query}: {len(rows)}", file=sys.stderr)
        counts[site] = got
        if not got:
            kept = [r for r in previous if r["ats"] == site]
            print(f"  {site} returned nothing; keeping {len(kept)} results from the last good run",
                  file=sys.stderr)
            for r in kept:
                found.setdefault((r["ats"], r["id"]), r)
    return list(found.values()), counts


if __name__ == "__main__":
    main()
