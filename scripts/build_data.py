"""Assemble everything the page renders into one data.json."""

from __future__ import annotations

import json
import re
import urllib.parse
from datetime import date

from fetch_jobs import INDIA, entry_level_business
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths
from fetch_search import QUERIES, SEARCH_SITES

TODAY = date.today().isoformat()

# The page's "Open to N grads" filter is worked out against this year.
def _grad_year() -> int:
    if os.environ.get("PT_GRAD_YEAR"):
        return int(os.environ["PT_GRAD_YEAR"])
    try:  # set from the dashboard's Settings page
        return int(json.loads((paths.PRIVATE / "settings.json").read_text())["grad_year"])
    except (FileNotFoundError, KeyError, ValueError):
        return 2027


GRAD_YEAR = _grad_year()

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

# The JobSpy searches and the hand-run links use one list.
LINKEDIN_QUERIES = QUERIES



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


# Tier 1 is the eight X-class cities of the government's HRA classification,
# plus the NCR and Mumbai satellite cities, which hire as part of those metros.
TIER1 = {
    "Mumbai", "Delhi", "Bengaluru", "Hyderabad", "Chennai", "Kolkata", "Pune",
    "Ahmedabad", "Gurugram", "Noida", "Greater Noida", "Ghaziabad", "Faridabad",
    "Navi Mumbai", "Thane",
}
# Tier 2 is the Y-class list, trimmed to cities that actually post these roles.
TIER2 = {
    "Jaipur", "Lucknow", "Kochi", "Coimbatore", "Chandigarh", "Mohali", "Indore",
    "Nagpur", "Surat", "Bhubaneswar", "Thiruvananthapuram", "Vadodara",
    "Visakhapatnam", "Mysuru", "Nashik", "Bhopal", "Patna", "Ludhiana", "Kanpur",
    "Madurai", "Vijayawada", "Mangaluru", "Dehradun", "Guwahati", "Raipur",
    "Ranchi", "Jodhpur", "Rajkot", "Aurangabad", "Tiruchirappalli", "Hubballi",
    "Goa", "Panaji", "Agra", "Varanasi", "Amritsar", "Jalandhar", "Gwalior",
    "Jabalpur", "Salem", "Tiruppur", "Belagavi", "Kolhapur", "Solapur", "Siliguri",
    "Durgapur", "Asansol", "Jamshedpur", "Dhanbad", "Cuttack", "Warangal",
    "Guntur", "Nellore", "Udaipur", "Ajmer", "Bikaner", "Kota", "Meerut",
    "Allahabad", "Prayagraj", "Bareilly", "Aligarh", "Moradabad", "Srinagar",
    "Jammu", "Pondicherry", "Puducherry", "Vellore", "Erode", "Thrissur",
    "Kozhikode", "Kannur", "Gandhinagar", "Bhavnagar", "Jamnagar", "Anand",
}
ALIASES = {
    "bangalore": "Bengaluru", "gurgaon": "Gurugram", "new delhi": "Delhi",
    "bombay": "Mumbai", "calcutta": "Kolkata", "madras": "Chennai",
    "cochin": "Kochi", "trivandrum": "Thiruvananthapuram", "mysore": "Mysuru",
    "baroda": "Vadodara", "vizag": "Visakhapatnam", "mangalore": "Mangaluru",
    "hubli": "Hubballi", "trichy": "Tiruchirappalli", "belgaum": "Belagavi",
    "calicut": "Kozhikode", "delhi ncr": "Delhi", "ncr": "Delhi",
    "gautam buddha nagar": "Noida",
}
KNOWN = {c.lower(): c for c in TIER1 | TIER2} | ALIASES
CITY = re.compile(r"\b(" + "|".join(sorted(map(re.escape, KNOWN), key=len, reverse=True)) + r")\b", re.I)
STATES = {
    "andhra pradesh", "arunachal pradesh", "assam", "bihar", "chhattisgarh", "goa",
    "gujarat", "haryana", "himachal pradesh", "jharkhand", "karnataka", "kerala",
    "madhya pradesh", "maharashtra", "manipur", "meghalaya", "mizoram", "nagaland",
    "odisha", "punjab", "rajasthan", "sikkim", "tamil nadu", "telangana", "tripura",
    "uttar pradesh", "uttarakhand", "west bengal", "india",
}


def place_of(location: str) -> tuple[str, str]:
    """(city, city tier) from a location string as any of the sources write it."""
    # A named city wins over "remote": "Pune/Remote" still means Pune.
    if m := CITY.search(location):
        city = KNOWN[m.group(1).lower()]
        return city, "Tier 1" if city in TIER1 else "Tier 2"
    if re.search(r"\b(remote|work from home|wfh)\b", location, re.I):
        return "Remote", "Remote"
    # LinkedIn writes "City, State, India"; a city missing from both lists is tier 3.
    first = location.split(",")[0].strip()
    if first and first.lower() not in STATES and not re.fullmatch(r"[A-Z]{2}", first):
        return first.title(), "Tier 3"
    # Indeed often gives only a state code: "KA, India".
    return "India", "City not given"


def city_of(location: str) -> str:
    return place_of(location)[0]


SUFFIXES = re.compile(
    r"\b(private|pvt|limited|ltd|llp|inc|technologies|technology|solutions|"
    r"services|india|labs|ventures|group)\b\.?", re.I)


def company_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", SUFFIXES.sub("", (name or "").lower()))


def funded_index() -> dict[str, dict]:
    """Companies in the funding store, by a key that ignores "Pvt Ltd" and the like.

    Exact matches only. Prefix matching attributed Jio Credit's roles to CRED.
    """
    try:
        store = json.load(open(paths.FUNDING))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    out = {}
    for rec in sorted(store.values(), key=lambda r: r.get("date") or ""):
        for name in (rec.get("company"), rec.get("parent")):
            k = company_key(name)
            if len(k) >= 4:
                out[k] = {"round": rec.get("round") or "", "date": rec.get("date") or ""}
    return out


def linkedin(query: str) -> str:
    params = urllib.parse.urlencode({
        "keywords": query, "location": "India",
        "f_E": "1,2", "f_TPR": "r2592000", "sortBy": "DD",
    })
    return f"https://www.linkedin.com/jobs/search/?{params}"


def main() -> None:
    postings = json.load(open(paths.POSTINGS))
    try:
        seen = json.load(open(paths.SEEN))
    except (FileNotFoundError, json.JSONDecodeError):
        seen = {}

    india = [r for r in postings if INDIA.search(r["location"])]
    biz = [r for r in india if entry_level_business(r["title"])]

    funded = funded_index()
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
        city, city_tier = place_of(r["location"])
        company = r["company"] if r["ats"] in SEARCH_SITES else display_name(r["slug"])
        roles.append({
            "age_days": hist.get("age_days"),
            "first_seen": hist.get("first_seen", ""),
            "reposted": bool(hist.get("reposted")),
            "title": r["title"].strip(),
            "company": company,
            "city": city,
            "city_tier": city_tier,
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
            "source": "search" if r["ats"] in SEARCH_SITES else "board",
            "apply_url": r.get("apply_url") or "",
            "batch": r.get("batch") or "",
            "batches": r.get("batches") or [],
            "kind": r.get("kind") or "full-time",
            "funded": funded.get(company_key(company)) or funded.get(company_key(r["slug"])),
            "key": key,
        })

    roles.sort(key=lambda r: (
        {"open": 0, "unstated": 1, "walled": 2}[r["tier"]],
        r["posted"] or "",
    ))
    roles.reverse()
    roles.sort(key=lambda r: {"open": 0, "unstated": 1, "walled": 2}[r["tier"]])

    try:
        rounds = json.load(open(paths.ROUNDS_CLEAN))
    except FileNotFoundError:
        rounds = json.load(open(paths.ROUNDS_RSS))

    # Fold in the accumulated Tracxn-style ingests. RSS gives narrative detail;
    # the export gives exact amounts and founded years. Neither alone is complete.
    try:
        store = json.load(open(paths.FUNDING))
    except (FileNotFoundError, json.JSONDecodeError):
        store = {}
    def norm(name):
        return re.sub(r"[^a-z0-9]", "", (name or "").lower())

    # RSS and the export name the same company differently: "Carrum" vs
    # "Carrum Mobility", "KARAM" vs "KARAM Safety". Match on containment.
    have = [norm(r.get("company")) for r in rounds]
    for rec in store.values():
        key = norm(rec.get("company"))
        if key and any(key in h or h in key for h in have if h):
            continue
        if not rec.get("is_venture_round", True):
            continue
        amount = (f"Rs {rec['amount_inr']/10_000_000:,.1f} Cr"
                  if rec.get("amount_inr") else "Undisclosed")
        rounds.append({
            "company": rec["company"] + (f" ({rec['parent']})" if rec.get("parent") else ""),
            "round": rec.get("round") or "",
            "amount": amount,
            "date": rec.get("date") or "",
            "investors": rec.get("investors") or [],
            "sector": f"founded {rec['founded']}" if rec.get("founded") else "",
            "source_url": "",
        })
    rounds.sort(key=lambda r: r.get("date") or "", reverse=True)

    boards = json.load(open(paths.BOARDS))

    data = {
        "generated": TODAY,
        "grad_year": GRAD_YEAR,
        # When LinkedIn and Indeed were last searched; only present on a machine that searched.
        "search": json.load(open(paths.SEARCH_META)) if paths.SEARCH_META.exists() else {},
        "roles": roles,
        "rounds": rounds,
        "searches": [{"query": q, "url": linkedin(q)} for q in LINKEDIN_QUERIES],
        "boards": boards,
        "closed_tracked": sum(1 for v in seen.values() if v.get("closed")),
        "coverage": {
            "boards": len(boards),
            "employers": len({b["slug"] for b in boards}),
            "postings_scanned": len(postings),
            "search_postings": sum(1 for r in postings if r["ats"] in SEARCH_SITES),
            "postings_india": len(india),
            "business_track": len(biz),
            "open": sum(1 for r in roles if r["tier"] == "open"),
            "unstated": sum(1 for r in roles if r["tier"] == "unstated"),
            "walled": sum(1 for r in roles if r["tier"] == "walled"),
        },
    }

    json.dump(data, open(paths.SITE_DATA, "w"), indent=2)
    c = data["coverage"]
    print(f"{c['business_track']} business-track roles: "
          f"{c['open']} open, {c['unstated']} unstated, {c['walled']} walled off")
    print(f"{len(rounds)} funding rounds")


if __name__ == "__main__":
    main()
