"""Entry-level business roles outside India and Japan whose postings say they sponsor a work visa.

Reads every full careers board the repo already knows (Japan/boards.json and India/top_employers.json;
Greenhouse, Lever, Ashby and Workable ones, which list every job with its description) and keeps a role when:

  where     outside India and Japan (those have their own tabs)
  what      a kind of role that fits Prathmesh's primary resume (India/fetch_top.py's families: product,
            analyst, strategy, consulting, finance, founder's office, growth); not senior, not an internship
  years     the posting asks for at most one year, or says nothing; not only earlier batches
  visa      the posting says outright that it sponsors a visa or supports relocation with a visa, and does
            not also say it will not sponsor or that applicants must already have the right to work there.
            A posting that says nothing about visas is left out: silence is not sponsorship.

The sentence that decided the visa call is kept as `visa_evidence`, so a wrong call is visible.

Company boards list few such roles, so LinkedIn and Indeed are also searched for "visa sponsorship" in the
countries Indians most often move to, at most once a day (the answers are cached in data/search_raw.json,
gitignored), with a pause between searches. The same filters apply to what they return.

  .venv/bin/python Overseas/fetch_overseas.py           # boards, plus the searches if a day has passed
  .venv/bin/python Overseas/fetch_overseas.py --boards  # boards only
"""

from __future__ import annotations

import json
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "India"))
sys.path.insert(0, str(ROOT / "Japan"))
sys.path.insert(0, str(ROOT / "scripts"))
from fetch_top import FEEDS, INDIA, family  # noqa: E402  the India tracker's feeds and role filter
from fetch_japan import JAPAN, clean, snippet  # noqa: E402
from enrich import batches, min_years  # noqa: E402

OUT = HERE / "data" / "roles.json"
SEARCH_RAW = HERE / "data" / "search_raw.json"
SEARCH_EVERY = timedelta(hours=24)
# (LinkedIn location, Indeed country) for the countries searched.
PLACES = [("United Kingdom", "UK"), ("Singapore", "Singapore"), ("United Arab Emirates", "United Arab Emirates"),
          ("Germany", "Germany"), ("Netherlands", "Netherlands"), ("Ireland", "Ireland"),
          ("United States", "USA"), ("Canada", "Canada"), ("Australia", "Australia")]
LINKEDIN_QUERIES = ["visa sponsorship analyst", "visa sponsorship graduate"]
INDEED_QUERY = "visa sponsorship analyst"
IST = timezone(timedelta(hours=5, minutes=30))
YEAR = 2027
FULL_BOARDS = ("greenhouse", "lever", "ashby")

# Ways a posting outside Japan says the applicant must already be allowed to work there.
NO_RIGHT = re.compile(
    r"(?:must|should)\W+(?:already\W+)?(?:have|hold|possess|be)\W+(?:a\W+|the\W+|valid\W+|an\W+|full\W+)*"
    r"(?:legal\W+)?(?:right|authori[sz](?:ation|ed)|eligib(?:le|ility)|permission)\W+to\W+(?:live\W+and\W+)?work|"
    r"(?:not|unable|cannot|can'?t|won'?t|will\W+not|do\W+not|does\W+not)\W+(?:\w+\W+){0,4}?"
    r"(?:sponsor|offer|provide|support)\w*\W+(?:\w+\W+){0,2}(?:visa|sponsorship|immigration)|"
    r"(?:no|without)\W+(?:\w+\W+){0,3}(?:visa\W+)?sponsorship|sponsorship\W+(?:is\W+)?not\W+(?:available|offered|provided|possible)|"
    r"(?:us|u\.s\.)\W+citizen(?:ship)?\W+(?:is\W+)?required|citizens\W+only|security\W+clearance|"
    r"(?:only|solely)\W+(?:consider|accept)\w*\W+(?:applicants|candidates)\W+(?:who\W+are\W+)?(?:already\W+)?(?:based|located|residing)",
    re.I)
# Sponsorship said outright by the employer about this job. Looser wording ("visa sponsorship" alone) is
# too often a refusal or a description of an HR team's work.
SPONSORS = re.compile(
    r"\b(?:we|will|can|able\W+to|happy\W+to|do)\W+(?:\w+\W+){0,2}sponsor\w*\W+(?:\w+\W+){0,3}visas?\b|"
    r"visa\W+sponsorship\W+(?:is\W+|will\W+be\W+)?(?:available|provided|offered)|"
    r"(?:provide|provides|offer|offers|including|includes)\W+(?:full\W+)?(?:work\W+)?visa\W+(?:sponsorship|support)|"
    r"relocation\W+(?:and|&)\W+visa\W+(?:support|sponsorship|assistance)|visa\W+(?:and|&)\W+relocation\W+(?:support|assistance)",
    re.I)
# Roles about visas themselves (HR mobility, immigration teams) are not sponsored roles.
VISA_WORK = re.compile(r"mobility|immigration|visa\b", re.I)

COUNTRIES = {
    "United States": r"\b(?:usa?|united states|new york|nyc|san francisco|seattle|boston|chicago|austin|los angeles|"
                     r"denver|atlanta|miami|washington|palo alto|mountain view|menlo park|sunnyvale|san jose|"
                     r"remote\W+us|, ?(?:ca|ny|wa|tx|ma|il|co|ga|fl|nj|va|pa|nc|or|ut|az|mn|mi|oh)\b)",
    "United Kingdom": r"\b(?:uk|united kingdom|london|manchester|edinburgh|cambridge, uk|england|scotland)\b",
    "Ireland": r"\b(?:ireland|dublin)\b",
    "Germany": r"\b(?:germany|berlin|munich|münchen|hamburg|frankfurt)\b",
    "Netherlands": r"\b(?:netherlands|amsterdam|rotterdam)\b",
    "France": r"\b(?:france|paris)\b",
    "Spain": r"\b(?:spain|madrid|barcelona)\b",
    "Switzerland": r"\b(?:switzerland|zurich|zürich|geneva)\b",
    "Singapore": r"\bsingapore\b",
    "Hong Kong": r"\bhong kong\b",
    "UAE": r"\b(?:uae|dubai|abu dhabi|united arab emirates)\b",
    "Australia": r"\b(?:australia|sydney|melbourne)\b",
    "Canada": r"\b(?:canada|toronto|vancouver|montreal)\b",
    "Poland": r"\b(?:poland|warsaw|krakow|kraków)\b",
    "Portugal": r"\b(?:portugal|lisbon)\b",
    "Sweden": r"\b(?:sweden|stockholm)\b",
    "Denmark": r"\b(?:denmark|copenhagen)\b",
    "Israel": r"\b(?:israel|tel aviv)\b",
    "South Korea": r"\b(?:korea|seoul)\b",
    "China": r"\b(?:china|shanghai|beijing|shenzhen)\b",
    "Brazil": r"\b(?:brazil|são paulo|sao paulo)\b",
    "Mexico": r"\b(?:mexico|ciudad de méxico)\b",
}
COUNTRIES = {k: re.compile(v, re.I) for k, v in COUNTRIES.items()}


def country_of(location: str) -> str:
    return next((name for name, rx in COUNTRIES.items() if rx.search(location or "")), "")


def boards() -> list[dict]:
    """Full boards only, each employer once, with its tier when the India list ranks it."""
    out: dict[tuple, dict] = {}
    for b in json.loads((ROOT / "Japan" / "boards.json").read_text()):
        if b["ats"] in FULL_BOARDS and not b.get("japan_only"):
            out[(b["ats"], b["slug"])] = {"company": b["company"], "ats": b["ats"], "slug": b["slug"], "tier": ""}
    for e in json.loads((ROOT / "India" / "top_employers.json").read_text())["employers"]:
        if e["ats"] in FULL_BOARDS:
            out[(e["ats"], e["slug"])] = {"company": e["company"], "ats": e["ats"], "slug": e["slug"], "tier": e["tier"]}
    return list(out.values())


def sponsorship(text: str) -> tuple[str, str]:
    """("yes", sentence) when the posting says it sponsors and never says it will not; else ("", "")."""
    if not text:
        return "", ""
    if m := NO_RIGHT.search(text):
        return "", ""
    if m := SPONSORS.search(text):
        return "yes", snippet(text, m.start(), m.end(), 80)
    return "", ""


def keep(j: dict, company: str, tier: str, source: str) -> dict | None:
    """The row for one posting when it passes every filter, else None."""
    where = j.get("location") or ""
    if INDIA.search(where) or JAPAN.search(where):
        return None
    fam = family(j["title"])
    if not fam or VISA_WORK.search(j["title"]):
        return None
    text = j.get("text") or ""
    years = min_years(text) if text else None
    if years is not None and years > 1:
        return None
    named = batches(text) if text else []
    if named and max(named) < YEAR:
        return None
    call, evidence = sponsorship(text)
    if call != "yes":
        return None
    return {"key": f"overseas:{source}:{re.sub(r'[^a-z0-9]+', '', company.lower())}:{j['id']}",
            "title": " ".join(j["title"].split()), "company": company, "tier": tier, "family": fam,
            "location": where, "country": country_of(where) or "Not stated", "url": j.get("url") or "",
            "posted": j.get("posted") or "", "min_years": years, "batches": named, "visa_evidence": evidence,
            "source": source}


def search(force: bool) -> list[dict]:
    """LinkedIn and Indeed postings that mention visa sponsorship, at most once a day, cached."""
    cached = json.loads(SEARCH_RAW.read_text()) if SEARCH_RAW.exists() else {"at": "", "rows": []}
    if cached["at"] and not force and datetime.now(IST) - datetime.fromisoformat(cached["at"]) < SEARCH_EVERY:
        print(f"Searched under a day ago; using the cached {len(cached['rows'])} postings.", file=sys.stderr)
        return cached["rows"]
    try:
        from jobspy import scrape_jobs
    except ImportError:
        print("jobspy is not installed; run with .venv/bin/python. Using cached postings.", file=sys.stderr)
        return cached["rows"]
    rows, empty = [], {"linkedin": 0, "indeed": 0}
    asks = [("linkedin", q, li, ind) for li, ind in PLACES for q in LINKEDIN_QUERIES] + \
           [("indeed", INDEED_QUERY, li, ind) for li, ind in PLACES]
    for site, query, li, ind in asks:
        if empty[site] >= 3:   # three empty answers running usually means the site is refusing us
            continue
        kwargs = dict(site_name=[site], search_term=query, results_wanted=25, hours_old=24 * 30,
                      description_format="markdown", verbose=0)
        kwargs.update(location=li, linkedin_fetch_description=True) if site == "linkedin" else \
            kwargs.update(location=li, country_indeed=ind)
        try:
            records = scrape_jobs(**kwargs).to_dict("records")
        except Exception as exc:
            print(f"  {site} '{query}' in {li} failed: {type(exc).__name__}", file=sys.stderr)
            records = []
        empty[site] = 0 if records else empty[site] + 1
        for rec in records:
            v = lambda k: "" if rec.get(k) is None or (isinstance(rec.get(k), float) and rec.get(k) != rec.get(k)) else str(rec.get(k))
            if v("title") and v("company") and v("job_url"):
                rows.append({"site": site, "id": v("id") or v("job_url"), "company": v("company"), "title": v("title"),
                             "location": v("location") or li, "url": v("job_url"), "posted": v("date_posted")[:10],
                             "text": clean(v("description"))})
        print(f"  {site} '{query}' in {li}: {len(records)}", file=sys.stderr)
        time.sleep(6 + random.uniform(0, 6))
    if rows:
        SEARCH_RAW.parent.mkdir(exist_ok=True)
        SEARCH_RAW.write_text(json.dumps({"at": datetime.now(IST).isoformat(timespec="seconds"), "rows": rows},
                                         ensure_ascii=False))
        return rows
    return cached["rows"]


def read(b: dict) -> tuple[dict, list[dict]]:
    report = {"company": b["company"], "ats": b["ats"], "listed": 0, "kept": 0, "error": ""}
    kept = []
    try:
        for j in FEEDS[b["ats"]](b):
            report["listed"] += 1
            if row := keep(j, b["company"], b["tier"], b["ats"]):
                kept.append(row)
    except Exception as exc:   # one board failing costs that board, not the run
        report["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
    report["kept"] = len(kept)
    return report, kept


def main() -> None:
    bs = boards()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(read, bs))
    rows = [r for _, kept in results for r in kept]
    found = [] if "--boards" in sys.argv else search("--force" in sys.argv)
    seen = {r["url"] for r in rows}
    for j in found:
        if j["url"] not in seen and (row := keep(j, j["company"], "", j["site"])):
            rows.append(row)
            seen.add(j["url"])
    one: dict[tuple, dict] = {}   # the same role posted twice keeps one row
    for r in rows:
        one.setdefault((r["company"].lower(), r["title"].lower()), r)
    rows = sorted(one.values(), key=lambda r: r["posted"] or "", reverse=True)
    reports = [rep for rep, _ in results]
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"generated": datetime.now(IST).isoformat(timespec="seconds"),
                               "boards": reports, "roles": rows}, ensure_ascii=False, indent=1) + "\n")
    for rep in reports:
        if rep["kept"] or rep["error"]:
            print(f"  {rep['company']:<28} listed {rep['listed']:>5}  kept {rep['kept']:>3}"
                  f"{'  ERROR ' + rep['error'] if rep['error'] else ''}", file=sys.stderr)
    print(f"{len(rows)} roles kept: {sum(r['source'] in ('linkedin', 'indeed') for r in rows)} from LinkedIn and Indeed, "
          f"the rest from {len(bs)} company boards ({sum(bool(r['error']) for r in reports)} failed)", file=sys.stderr)


if __name__ == "__main__":
    main()
