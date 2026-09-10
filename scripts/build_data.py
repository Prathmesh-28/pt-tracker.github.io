"""Assemble everything the page renders into one data.json."""

from __future__ import annotations

import json
import re
import urllib.parse
from datetime import date

from fetch_jobs import INDIA, entry_level_business

TODAY = date.today().isoformat()

FAMILIES = [
    ("Business analyst", r"business analyst|data analyst|risk analyst|financial analyst"),
    ("Consulting", r"consultant|consulting"),
    ("Strategy", r"strategy|gtm|corporate development"),
    ("Growth", r"growth|marketing|campaign|affiliate"),
    ("Product", r"product manager|product analyst|product ops|product associate|\bapm\b"),
    ("Founder's office", r"founder'?s office|chief of staff|generalist"),
    ("Category", r"category|merchandis"),
    ("Management trainee", r"trainee|graduate program|management associate"),
    ("Business development", r"business development|sales|account executive|partnership|\bbd\b"),
    ("Operations", r"\bops\b|operations|program manager|project manager|supply"),
    ("Support & other", r"."),
]

LINKEDIN_QUERIES = [
    "business analyst", "associate consultant", "strategy associate",
    "growth analyst", "product analyst", "associate product manager",
    "founder's office", "chief of staff", "category manager",
    "management trainee", "business development associate",
]



DISPLAY = {
    "atlan": "Atlan", "bureau": "Bureau", "cred": "CRED", "fampay": "FamPay",
    "meesho": "Meesho", "mindtickle": "Mindtickle", "paytm": "Paytm",
    "sarvam": "Sarvam AI", "navi": "Navi", "zeta": "Zeta", "porter": "Porter",
    "slice": "Slice", "groww": "Groww", "bluestone": "BlueStone",
    "druva": "Druva", "postman": "Postman", "netradyne": "Netradyne",
    "zenoti": "Zenoti", "velocity": "Velocity", "river": "River",
    "bounce": "Bounce", "vogo": "Vogo", "glide": "Glide", "sentry": "Sentry",
    "epifi": "Fi Money", "eternal": "Eternal (Zomato)", "pilgrim": "Pilgrim",
    "cello": "Cello", "hone": "Hone", "fampay": "FamPay",
}


def display_name(slug: str) -> str:
    return DISPLAY.get(slug.lower(), slug if slug[:1].isupper() else slug.title())


def family_of(title: str) -> str:
    for name, pattern in FAMILIES:
        if re.search(pattern, title, re.I):
            return name
    return "Support & other"


def city_of(location: str) -> str:
    m = re.search(
        r"\b(Bengaluru|Bangalore|Mumbai|Gurgaon|Gurugram|Delhi|Noida|Hyderabad|"
        r"Pune|Chennai|Kolkata|Ahmedabad|Jaipur|Indore|Kochi|Coimbatore|"
        r"Chandigarh|Bhubaneswar)\b",
        location, re.I,
    )
    if not m:
        return "India"
    city = m.group(1).title()
    return {"Bangalore": "Bengaluru", "Gurgaon": "Gurugram"}.get(city, city)


def linkedin(query: str) -> str:
    params = urllib.parse.urlencode({
        "keywords": query, "location": "India",
        "f_E": "1,2", "f_TPR": "r2592000", "sortBy": "DD",
    })
    return f"https://www.linkedin.com/jobs/search/?{params}"


def main() -> None:
    postings = json.load(open("all_postings.json"))
    try:
        seen = json.load(open("data/seen.json"))
    except (FileNotFoundError, json.JSONDecodeError):
        seen = {}

    india = [r for r in postings if INDIA.search(r["location"])]
    biz = [r for r in india if entry_level_business(r["title"])]

    roles = []
    for r in biz:
        years = r.get("min_years")
        if years is None:
            tier = "unstated"
        elif years <= 1:
            tier = "open"
        else:
            tier = "walled"
        key = f"{r['ats']}:{r['slug']}:{r['id']}"
        hist = seen.get(key, {})
        roles.append({
            "age_days": hist.get("age_days"),
            "first_seen": hist.get("first_seen", ""),
            "reposted": bool(hist.get("reposted")),
            "title": r["title"].strip(),
            "company": display_name(r["slug"]),
            "city": city_of(r["location"]),
            "location": r["location"],
            "pay": r.get("pay") or "",
            "url": r["url"],
            "posted": r.get("posted") or "",
            "deadline": r.get("deadline") or "",
            "team": r.get("team") or "",
            "family": family_of(r["title"]),
            "min_years": years,
            "tier": tier,
            "ats": r["ats"],
            "batch": r.get("batch") or "",
            "key": key,
        })

    roles.sort(key=lambda r: (
        {"open": 0, "unstated": 1, "walled": 2}[r["tier"]],
        r["posted"] or "",
    ))
    roles.reverse()
    roles.sort(key=lambda r: {"open": 0, "unstated": 1, "walled": 2}[r["tier"]])

    try:
        rounds = json.load(open("rounds_clean.json"))
    except FileNotFoundError:
        rounds = json.load(open("rounds.json"))

    boards = json.load(open("boards.json"))

    data = {
        "generated": TODAY,
        "roles": roles,
        "rounds": rounds,
        "searches": [{"query": q, "url": linkedin(q)} for q in LINKEDIN_QUERIES],
        "boards": boards,
        "closed_tracked": sum(1 for v in seen.values() if v.get("closed")),
        "coverage": {
            "boards": len(boards),
            "employers": len({b["slug"] for b in boards}),
            "postings_scanned": len(postings),
            "postings_india": len(india),
            "business_track": len(biz),
            "open": sum(1 for r in roles if r["tier"] == "open"),
            "unstated": sum(1 for r in roles if r["tier"] == "unstated"),
            "walled": sum(1 for r in roles if r["tier"] == "walled"),
        },
    }

    json.dump(data, open("data/latest.json", "w"), indent=2)
    c = data["coverage"]
    print(f"{c['business_track']} business-track roles: "
          f"{c['open']} open, {c['unstated']} unstated, {c['walled']} walled off")
    print(f"{len(rounds)} funding rounds")


if __name__ == "__main__":
    main()
