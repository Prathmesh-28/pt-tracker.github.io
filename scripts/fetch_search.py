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

Needs Python 3.10+ and `pip install -r requirements.txt`.
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
import time

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
]

SITES = [s.strip() for s in os.environ.get("JOBSPY_SITES", "linkedin,indeed").split(",") if s.strip()]
RESULTS = int(os.environ.get("JOBSPY_RESULTS", "30"))      # per query, per site
HOURS_OLD = int(os.environ.get("JOBSPY_HOURS", str(24 * 30)))
PROXIES = [p.strip() for p in os.environ.get("JOBSPY_PROXIES", "").split(",") if p.strip()] or None
PAUSE = 4  # seconds between queries; LinkedIn starts returning 429s when hammered


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
        "company_url": val(row.get("company_url_direct")),
        "emails": val(row.get("emails")),
    }


def search(query: str) -> list[dict]:
    from jobspy import scrape_jobs

    kwargs = dict(
        site_name=SITES, search_term=query, location="India",
        results_wanted=RESULTS, hours_old=HOURS_OLD, country_indeed="India",
        linkedin_fetch_description=True, description_format="markdown",
        proxies=PROXIES, verbose=0,
    )
    try:
        frame = scrape_jobs(**kwargs)
    except Exception as exc:
        print(f"  '{query}' failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return []
    return [r for r in (normalise(rec) for rec in frame.to_dict("records")) if r]


def main() -> None:
    try:
        import jobspy  # noqa: F401
    except ImportError:
        print("jobspy is not installed; skipping search sources. "
              "Run `pip install -r requirements.txt` on Python 3.10+.", file=sys.stderr)
        return

    postings = json.load(open(paths.POSTINGS))
    # Idempotent: drop search rows a previous run of this script merged in.
    boards_only = [r for r in postings if r["ats"] not in SEARCH_SITES]

    print(f"searching {', '.join(SITES)} for {len(QUERIES)} queries", file=sys.stderr)
    found: dict[tuple[str, str], dict] = {}
    for i, query in enumerate(QUERIES):
        if i:
            time.sleep(PAUSE)
        rows = search(query)
        for r in rows:
            found.setdefault((r["ats"], r["id"]), r)
        print(f"  {query}: {len(rows)}", file=sys.stderr)

    # The same role on the employer's board and on LinkedIn: keep the board row,
    # which carries a real first-published date and can be tracked to closure.
    on_boards = set()
    for r in boards_only:
        for name in (r.get("company"), r.get("slug")):
            on_boards.add((norm(name), norm(r["title"])))
    # And the same role on LinkedIn and Indeed: keep whichever came first.
    fresh, seen_pairs = [], set()
    for r in found.values():
        pair = (r["slug"], norm(r["title"]))
        if pair in on_boards or pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        fresh.append(r)

    json.dump(fresh, open(paths.SEARCH_POSTINGS, "w"), indent=2)
    json.dump(boards_only + fresh, open(paths.POSTINGS, "w"), indent=2)

    by_site = {s: sum(1 for r in fresh if r["ats"] == s) for s in SITES}
    print(f"\n{len(found)} search results, {len(found) - len(fresh)} duplicates dropped, "
          f"{len(fresh)} added ({', '.join(f'{s} {n}' for s, n in by_site.items())})",
          file=sys.stderr)


if __name__ == "__main__":
    main()
