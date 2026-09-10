"""Pull Indian startup funding RSS and separate real rounds from everything else.

Entrackr's <description> carries the round detail (amount, investors, sometimes
valuation), which is why it is worth more than the headline alone. VCCircle and
Moneycontrol both 403 regardless of headers, so they are not attempted.

Headline classification is mostly deterministic: an acquisition, an IPO, a stake
sale, an appointment or a VC closing its own fund all announce themselves in the
verb. What survives that filter is a funding round, with the recipient as the
grammatical subject.
"""

from __future__ import annotations

import html
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

FEEDS = {
    "Entrackr": "https://entrackr.com/rss",
    "Inc42": "https://inc42.com/feed/",
    "YourStory": "https://yourstory.com/feed",
}

TAGS = re.compile(r"<[^>]+>")
SPACE = re.compile(r"\s+")

# Verbs that mean this is NOT a startup raising a round.
NOT_A_ROUND = re.compile(
    r"\b(acquires?|acquisition|acquired|buys?|bought|merges?|merger|"
    r"ipo\b|lists? on|listing|drhp|public issue|"
    r"stake sale|sells? stake|offloads?|divests?|exits?|"
    r"lays? off|layoffs?|shuts? down|shutdown|winds? down|insolvency|"
    r"appoints?|elevates?|names? .{0,20}(?:ceo|cfo|cto|coo)|resigns?|steps? down|quits?|"
    r"launches? .{0,25}fund|closes? .{0,25}fund|raises? .{0,15}fund\b|"
    r"maiden fund|fund i{1,3}\b|corpus)",
    re.I,
)

# Verbs that mean a company raised money.
RAISE = re.compile(
    r"\b(raises?|raised|bags?|bagged|secures?|secured|mops? up|mopped up|"
    r"nets?|netted|garners?|picks? up|lands?|closes? .{0,20}round|"
    r"funding|funded)\b",
    re.I,
)

ROUND = re.compile(
    r"\b(pre-?seed|seed|pre-?series [a-e]|series [a-j]|"
    r"bridge|angel|venture debt|debt|growth|pre-?ipo)\b",
    re.I,
)

AMOUNT = re.compile(
    r"(\$\s?\d[\d,.]*\s?(?:mn|million|bn|billion|k)?|"
    r"(?:rs\.?|inr|₹)\s?\d[\d,.]*\s?(?:cr|crore|lakh|mn|million|bn|billion)?)",
    re.I,
)

INVESTORS = re.compile(
    r"(?:led by|co-?led by|backed by|from|participation from|joined by)\s+"
    r"([A-Z][A-Za-z0-9&.'\- ]+(?:,\s*[A-Z][A-Za-z0-9&.'\- ]+)*)",
)


def clean(raw: str) -> str:
    return SPACE.sub(" ", html.unescape(TAGS.sub(" ", raw or ""))).strip()


def company_from(title: str) -> str | None:
    """The recipient is the subject, so it is whatever precedes the raise verb."""
    m = RAISE.search(title)
    if not m:
        return None
    subject = title[: m.start()].strip(" ,;:-–—")
    # Drop a leading outlet tag like "Exclusive:" or "Funding Alert:".
    subject = re.sub(r"^[A-Za-z ]{0,20}:\s*", "", subject).strip()
    return subject or None


def fetch(name: str, url: str) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            body = r.read()
    except Exception as exc:
        print(f"  {name} failed: {exc}", file=sys.stderr)
        return []

    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        print(f"  {name} unparseable: {exc}", file=sys.stderr)
        return []

    items = []
    for node in root.iter("item"):
        title = clean(node.findtext("title") or "")
        link = (node.findtext("link") or "").strip()
        desc = clean(node.findtext("description") or "")
        pub = node.findtext("pubDate") or ""
        try:
            when = parsedate_to_datetime(pub).astimezone(timezone.utc)
        except (TypeError, ValueError):
            when = None
        items.append({
            "source": name, "title": title, "url": link,
            "description": desc,
            "date": when.date().isoformat() if when else "",
            "_dt": when,
        })
    print(f"  {name}: {len(items)} items", file=sys.stderr)
    return items


def classify(item: dict) -> dict:
    blob = f"{item['title']} {item['description']}"
    if NOT_A_ROUND.search(item["title"]):
        return {**item, "company": None, "round": None, "investors": [], "amount": None}
    if not RAISE.search(item["title"]):
        return {**item, "company": None, "round": None, "investors": [], "amount": None}

    stage = ROUND.search(blob)
    amount = AMOUNT.search(blob)
    names: list[str] = []
    for m in INVESTORS.finditer(blob):
        for part in re.split(r",| and ", m.group(1)):
            part = part.strip(" .")
            if 2 < len(part) < 40 and part not in names:
                names.append(part)

    return {
        **item,
        "company": company_from(item["title"]),
        "round": (stage.group(1).title() if stage else None),
        "amount": (amount.group(1).strip() if amount else None),
        "investors": names[:6],
    }


def main() -> None:
    window = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    cutoff = datetime.now(timezone.utc) - timedelta(days=window)

    print(f"pulling {len(FEEDS)} feeds", file=sys.stderr)
    raw: list[dict] = []
    for name, url in FEEDS.items():
        raw.extend(fetch(name, url))

    classified = [classify(i) for i in raw]
    rounds = [
        c for c in classified
        if c["company"] and (c["_dt"] is None or c["_dt"] >= cutoff)
    ]

    for c in classified:
        c.pop("_dt", None)

    rounds.sort(key=lambda c: c["date"], reverse=True)
    json.dump(classified, open(paths.HEADLINES, "w"), indent=2)
    json.dump(rounds, open(paths.ROUNDS_RSS, "w"), indent=2)

    print(f"\n{len(raw)} headlines, {len(rounds)} funding rounds inside {window} days",
          file=sys.stderr)
    print(f"{len(classified) - len(rounds)} were not rounds or fell outside the window",
          file=sys.stderr)


if __name__ == "__main__":
    main()
