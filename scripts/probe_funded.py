"""Probe the funded-company list for public boards.

A company that closed a round weeks ago is the highest-probability employer
there is, so the funding store doubles as a candidate list for slug discovery.

Unlike the generic probe, a hit here must show INDIA postings. That is what
stops the namesake trap: "porter", "slice", "navi" and "eternal" all resolve
to real boards belonging to unrelated foreign companies.
"""

from __future__ import annotations

import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths

import json
import pathlib
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parent.parent
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

ENDPOINTS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{}/jobs",
    "lever": "https://api.lever.co/v0/postings/{}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{}",
}

INDIA = re.compile(
    r"\b(india|bengaluru|bangalore|mumbai|gurgaon|gurugram|delhi|noida|ncr|"
    r"hyderabad|pune|chennai|kolkata|ahmedabad|jaipur|indore|kochi|coimbatore|"
    r"chandigarh|surat|nagpur|bhubaneswar|thiruvananthapuram)\b", re.I)


def variants(name: str) -> list[str]:
    base = re.sub(r"\.(com|io|ai|in)$", "", name.strip(), flags=re.I)
    base = re.sub(r"[^A-Za-z0-9 ]", "", base).strip().lower()
    if not base:
        return []
    squashed = base.replace(" ", "")
    hyphen = base.replace(" ", "-")
    first = base.split()[0]
    return list(dict.fromkeys(v for v in (squashed, hyphen, first) if len(v) > 2))


def location_of(ats: str, row: dict) -> str:
    if ats == "greenhouse":
        return (row.get("location") or {}).get("name") or ""
    if ats == "lever":
        return (row.get("categories") or {}).get("location") or ""
    return row.get("location") or row.get("address") or ""


def probe(job):
    ats, slug, company = job
    try:
        req = urllib.request.Request(ENDPOINTS[ats].format(slug), headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=25) as r:
            payload = json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return None
    rows = payload if isinstance(payload, list) else (payload.get("jobs") or [])
    if not rows:
        return None
    india = sum(1 for row in rows if INDIA.search(location_of(ats, row)))
    if not india:
        return None                     # a namesake, not the Indian company
    return {"ats": ats, "slug": slug, "postings": len(rows),
            "india": india, "matched_company": company}


def main() -> None:
    store = json.loads((paths.FUNDING).read_text())
    rejected = set()
    try:
        rejected = set(json.loads((paths.REJECTED).read_text())["slugs"])
    except Exception:
        pass

    jobs, seen = [], set()
    for rec in store.values():
        for slug in variants(rec["company"]):
            if slug in rejected:
                continue
            for ats in ENDPOINTS:
                if (ats, slug) in seen:
                    continue
                seen.add((ats, slug))
                jobs.append((ats, slug, rec["company"]))

    print(f"probing {len(jobs)} candidates from {len(store)} funded companies", file=sys.stderr)
    hits = []
    with ThreadPoolExecutor(max_workers=24) as pool:
        for res in pool.map(probe, jobs):
            if res:
                hits.append(res)
                print(f"  HIT {res['ats']:11} {res['slug']:22} "
                      f"{res['postings']:>4} postings, {res['india']:>3} India "
                      f"({res['matched_company']})", file=sys.stderr)

    (paths.FUNDED_BOARDS).write_text(json.dumps(hits, indent=2))
    print(f"\n{len(hits)} boards with a real India presence", file=sys.stderr)


if __name__ == "__main__":
    main()
