"""Pull every posting from the discovered boards and keep the India-based,
entry-level, business-track ones.

Field shapes differ per ATS and the differences bite:
  Lever   - title is `text`, not `title`; createdAt is epoch MILLISECONDS
  Ashby   - unlisted postings ship in the array; isListed must be checked
  Ashby   - compensationTierSummary is a ready-made band string
  Greenhouse - location is an object; application_deadline is a real date
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

ENDPOINTS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{}/jobs",
    "lever": "https://api.lever.co/v0/postings/{}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{}?includeCompensation=true",
}

INDIA = re.compile(
    r"\b(india|bengaluru|bangalore|mumbai|gurgaon|gurugram|delhi|noida|ncr|"
    r"hyderabad|pune|chennai|kolkata|ahmedabad|jaipur|indore|kochi|cochin|"
    r"coimbatore|chandigarh|surat|nagpur|bhubaneswar|thiruvananthapuram)\b",
    re.I,
)

# Role families the user asked for.
WANTED = re.compile(
    r"(business analyst|product analyst|growth analyst|data analyst|"
    r"operations analyst|financial analyst|research analyst|\banalyst\b|"
    r"associate consultant|\bconsultant\b|strategy|growth|"
    r"associate product manager|product manager|\bapm\b|product associate|"
    r"founder'?s office|chief of staff|category|"
    r"management trainee|graduate trainee|trainee|"
    r"business development|\bbd\b|inside sales|sales associate|"
    r"account executive|customer success|partnerships|"
    r"program manager|project manager|operations associate|\bops\b|"
    r"associate|generalist)",
    re.I,
)

# Seniority markers that disqualify. "Chief of Staff" is handled before this runs.
SENIOR = re.compile(
    r"(senior|\bsr\.?\b|staff\b|principal|\blead\b|leader|head of|\bhead\b|"
    r"director|\bvp\b|vice president|president|\bchief\b|architect|"
    r"manager ii|manager iii|\bii\b|\biii\b|\biv\b|\bl[3-9]\b)",
    re.I,
)

# Technical individual-contributor roles the user is not looking for.
ENGINEERING = re.compile(
    r"(software engineer|\bengineer\b|engineering|developer|\bsde\b|\bsdet\b|"
    r"devops|\bsre\b|\bqa\b|quality assurance|data scientist|scientist|"
    r"machine learning|\bml\b|backend|back-end|frontend|front-end|fullstack|"
    r"full-stack|android|\bios\b|mobile dev|security|infrastructure|platform eng|"
    r"designer|\bdesign\b|technical writer)",
    re.I,
)


def get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def iso(value) -> str:
    """Normalise the three date encodings these APIs use."""
    if not value:
        return ""
    if isinstance(value, (int, float)):
        # Lever ships epoch milliseconds.
        return datetime.fromtimestamp(value / 1000, timezone.utc).date().isoformat()
    text = str(value)
    if text.isdigit():
        return datetime.fromtimestamp(int(text) / 1000, timezone.utc).date().isoformat()
    return text[:10]


def normalise(ats: str, slug: str, raw: dict) -> dict | None:
    if ats == "greenhouse":
        title = raw.get("title") or ""
        location = (raw.get("location") or {}).get("name") or ""
        return {
            "ats": ats, "id": str(raw.get("id")), "slug": slug,
            "company": raw.get("company_name") or slug, "title": title,
            "location": location, "url": raw.get("absolute_url") or "",
            "posted": iso(raw.get("first_published") or raw.get("updated_at")),
            "updated": iso(raw.get("updated_at")),
            "deadline": iso(raw.get("application_deadline")),
            "pay": "",
            "team": ", ".join(d.get("name", "") for d in (raw.get("departments") or [])),
        }

    if ats == "lever":
        cats = raw.get("categories") or {}
        return {
            "ats": ats, "id": str(raw.get("id")), "slug": slug,
            "company": slug, "title": raw.get("text") or "",
            "location": cats.get("location") or "",
            "url": raw.get("hostedUrl") or raw.get("applyUrl") or "",
            "posted": iso(raw.get("createdAt")), "updated": "", "deadline": "",
            "pay": "",
            "team": cats.get("team") or cats.get("department") or "",
        }

    if ats == "ashby":
        if not raw.get("isListed", True):
            return None
        comp = raw.get("compensation") or {}
        band = comp.get("compensationTierSummary") or ""
        if not raw.get("shouldDisplayCompensationOnJobPostings", True):
            band = ""
        return {
            "ats": ats, "id": str(raw.get("id")), "slug": slug,
            "company": slug, "title": raw.get("title") or "",
            "location": raw.get("location") or raw.get("address") or "",
            "url": raw.get("jobUrl") or raw.get("applyUrl") or "",
            "posted": iso(raw.get("publishedAt")), "updated": "", "deadline": "",
            "pay": band,
            "team": raw.get("department") or raw.get("team") or "",
        }
    return None


def entry_level_business(title: str) -> bool:
    if re.search(r"chief of staff", title, re.I):
        return True
    if ENGINEERING.search(title):
        return False
    if SENIOR.search(title):
        return False
    return bool(WANTED.search(title))


def pull(board: dict) -> list[dict]:
    ats, slug = board["ats"], board["slug"]
    try:
        payload = get(ENDPOINTS[ats].format(slug))
    except Exception as exc:
        print(f"  {ats}/{slug} failed: {exc}", file=sys.stderr)
        return []
    rows = payload if isinstance(payload, list) else (payload.get("jobs") or [])
    out = []
    for raw in rows:
        row = normalise(ats, slug, raw)
        if row and row["url"]:
            out.append(row)
    return out


def main() -> None:
    boards = json.load(open(paths.BOARDS))
    print(f"pulling {len(boards)} boards", file=sys.stderr)

    everything: list[dict] = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        for rows in pool.map(pull, boards):
            everything.extend(rows)

    india = [r for r in everything if INDIA.search(r["location"])]
    keep = [r for r in india if entry_level_business(r["title"])]

    keep.sort(key=lambda r: (r["posted"] or ""), reverse=True)

    json.dump(everything, open(paths.POSTINGS, "w"), indent=2)
    json.dump(keep, open(paths.SHORTLIST, "w"), indent=2)

    print(f"\n{len(everything)} postings total", file=sys.stderr)
    print(f"{len(india)} in India", file=sys.stderr)
    print(f"{len(keep)} entry-level business-track -> shortlist.json", file=sys.stderr)


if __name__ == "__main__":
    main()
