"""Read each posting's description and extract the stated experience requirement.

A title cannot tell you years of experience. "Product Manager" is 4 years at one
company and a graduate role at another, and Paytm's "DGM/GM" titles pass any
keyword filter while being two promotions above entry level. The description is
the only place the requirement is actually written down.

Descriptions come free on Lever and Ashby. Greenhouse needs content=true, which
roughly triples the payload, so it is fetched once per board rather than per job.
"""

from __future__ import annotations

import html
import json
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

TAGS = re.compile(r"<[^>]+>")
SPACE = re.compile(r"\s+")

# Ordered most-specific first. Each yields the MINIMUM years the posting demands.
PATTERNS = [
    # "0-2 years", "1 to 3 years", "2 - 4 yrs"
    (re.compile(r"(\d{1,2})\s*(?:-|–|—|to)\s*(\d{1,2})\s*\+?\s*(?:years?|yrs?)", re.I), "range"),
    # "minimum of 3 years", "at least 2 years"
    (re.compile(r"(?:minimum|at least|min\.?|more than|over)\s*(?:of\s*)?(\d{1,2})\s*\+?\s*(?:years?|yrs?)", re.I), "min"),
    # "5+ years", "3 + years"
    (re.compile(r"(\d{1,2})\s*\+\s*(?:years?|yrs?)", re.I), "min"),
    # "3 years of experience"
    (re.compile(r"(\d{1,2})\s*(?:years?|yrs?)\s+(?:of\s+)?(?:relevant\s+|prior\s+|work\s+|professional\s+)?experience", re.I), "min"),
]

FRESHER = re.compile(
    r"(fresher|fresh graduate|entry[- ]level|no prior (?:work )?experience|"
    r"campus hire|graduate (?:trainee|programme|program)|management trainee|"
    r"final[- ]year student|20(?:26|27) (?:batch|pass ?out|graduat))",
    re.I,
)

BATCH = re.compile(r"\b(202[5-9])\s*(?:batch|pass ?out|graduates?)", re.I)


def clean(raw: str) -> str:
    return SPACE.sub(" ", html.unescape(TAGS.sub(" ", raw or ""))).strip()


def min_years(text: str) -> int | None:
    """Smallest number of years the posting will accept, or None if unstated."""
    found: list[int] = []
    for pattern, kind in PATTERNS:
        for m in pattern.finditer(text):
            try:
                found.append(int(m.group(1)))
            except (ValueError, IndexError):
                continue
    if FRESHER.search(text):
        found.append(0)
    return min(found) if found else None


def fetch_descriptions(board: dict) -> dict[str, str]:
    """Map posting id -> plain-text description for one board."""
    ats, slug = board["ats"], board["slug"]
    if ats == "greenhouse":
        url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
        key, field = "id", "content"
    elif ats == "lever":
        url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
        key, field = "id", "descriptionPlain"
    else:
        url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"
        key, field = "id", "descriptionPlain"

    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            payload = json.loads(r.read().decode("utf-8", "replace"))
    except Exception as exc:
        print(f"  {ats}/{slug} description fetch failed: {exc}", file=sys.stderr)
        return {}

    rows = payload if isinstance(payload, list) else (payload.get("jobs") or [])
    return {str(row.get(key)): clean(row.get(field) or "") for row in rows}


def main() -> None:
    boards = json.load(open("boards.json"))
    postings = json.load(open("all_postings.json"))

    print(f"fetching descriptions for {len(boards)} boards", file=sys.stderr)
    lookup: dict[tuple[str, str], dict[str, str]] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for board, descriptions in zip(boards, pool.map(fetch_descriptions, boards)):
            lookup[(board["ats"], board["slug"])] = descriptions

    stated = unstated = 0
    for row in postings:
        text = lookup.get((row["ats"], row["slug"]), {}).get(row["id"], "")
        row["description"] = text
        years = min_years(text) if text else None
        row["min_years"] = years
        batch = BATCH.search(text) if text else None
        row["batch"] = batch.group(1) if batch else ""
        if years is None:
            unstated += 1
        else:
            stated += 1

    json.dump(postings, open("all_postings.json", "w"), indent=2)
    print(f"\nexperience stated on {stated}, unstated on {unstated}", file=sys.stderr)


if __name__ == "__main__":
    main()
