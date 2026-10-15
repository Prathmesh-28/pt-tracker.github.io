"""Entry-level product, analyst and graduate roles in India for Prathmesh, with what each pays.

The India tracker at the repo root (scripts/, data/latest.json) already pulls entry-level business
openings in India every morning from LinkedIn, Indeed and company boards, and reads each posting for
the experience it asks. This keeps the kinds of role Prathmesh wants, drops those asking for two years
or more, and adds to each:

  pay       What freshers (0-1 years) in that role at that company are paid, from AmbitionBox, India's
            salary site: the average CTC, the typical range and how many salaries it rests on. Base pay
            is shown when AmbitionBox reports the fixed share, or a campus offer gives it; otherwise it
            is estimated from the base-to-CTC ratio of the campus offers recorded. A company with no
            AmbitionBox data for the role falls back to the role's figure across India. Glassdoor and
            Levels.fyi answer scripts with a captcha, so they are not read.
  company   Startup, MNC or Indian company, from AmbitionBox's company profile (its type, ownership and
            headquarters), or the funding store for a funded startup.
  timing    For a May 2027 graduate: the posting names the 2027 batch; names other batches only; is an
            internship; or names no batch (most such roles want someone to join within weeks).
  deadline  The apply-by date when the posting states one; else the date it was posted.

Campus offers (private/campus.json, gitignored: placement-cell details stay off GitHub) and graduate
programmes (programs.json) are added as rows of their own.

  .venv/bin/python India/fetch_india.py            # rank the roles, look up pay, write data/
  .venv/bin/python India/fetch_india.py --offline  # the same, from cached pay only

Writes data/roles.json and data/roles.csv. AmbitionBox answers are cached in data/pay_cache.json
(gitignored) for 30 days, so a daily run asks only about companies it has not seen.
"""

from __future__ import annotations

import csv
import difflib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = HERE / "data"
LATEST = ROOT / "data" / "latest.json"          # the root India tracker's roles
PROGRAMS = HERE / "programs.json"
CAMPUS = HERE / "private" / "campus.json"
FULL_JSON = HERE / "private" / "roles.json"   # with the campus offers, for the team site; gitignored
OUT_JSON = DATA / "roles.json"                 # without them, for this public repo
OUT_CSV = DATA / "roles.csv"
CACHE = DATA / "pay_cache.json"

AB = "https://www.ambitionbox.com"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
PAUSE = 0.8            # seconds between AmbitionBox requests, one at a time
KEEP_DAYS = 30         # how long an AmbitionBox answer is reused
MIN_POINTS = 3         # fewer salaries than this is not a figure
IST = timezone(timedelta(hours=5, minutes=30))
YEAR = 2027

# The root tracker's role families, in Prathmesh's order of preference. "Support & other" is left out.
FAMILIES = {
    "Product": (1, "Product analyst and APM"),
    "Business analyst": (2, "Business and data analyst"),
    "Strategy": (3, "Strategy"),
    "Consulting": (3, "Consulting"),
    "Founder's office": (4, "Founder's office"),
    "Management trainee": (4, "Management trainee and graduate programme"),
    "Growth": (5, "Growth"),
    "Category": (5, "Category"),
    "Operations": (5, "Operations"),
    "Business development": (6, "Business development"),
}

# Which AmbitionBox designations to read for a title, most specific first.
DESIGNATIONS = [
    (r"associate product manager|\bapm\b", ["associate-product-manager", "product-manager", "product-analyst"]),
    (r"product manager", ["product-manager", "associate-product-manager"]),
    (r"product analyst", ["product-analyst", "business-analyst", "data-analyst"]),
    (r"data analyst|analytics", ["data-analyst", "business-analyst", "analyst"]),
    (r"business analyst", ["business-analyst", "analyst"]),
    (r"strategy", ["strategy-analyst", "strategy-associate", "business-analyst"]),
    (r"consultant", ["associate-consultant", "consultant", "business-analyst"]),
    (r"founder", ["founders-office-associate", "associate", "business-analyst"]),
    (r"management trainee|\bmt\b|graduate trainee", ["management-trainee"]),
    (r"graduate engineer trainee|\bget\b", ["graduate-engineer-trainee"]),
    (r"category", ["category-manager", "category-associate", "associate"]),
    (r"growth|marketing", ["growth-associate", "marketing-associate", "associate"]),
    (r"operations|program", ["operations-associate", "program-manager", "associate"]),
    (r"business development|sales", ["business-development-associate", "business-development-executive"]),
    (r"analyst", ["analyst", "business-analyst"]),
    (r"associate", ["associate", "business-analyst"]),
]
FAMILY_DESIGNATION = {"Product": "product-analyst", "Business analyst": "business-analyst", "Strategy": "business-analyst",
                      "Consulting": "associate-consultant", "Founder's office": "business-analyst",
                      "Management trainee": "management-trainee", "Growth": "growth-associate",
                      "Category": "category-manager", "Operations": "operations-associate",
                      "Business development": "business-development-associate"}
# A hospital's "Associate Consultant, Gastroenterology" is a doctor, not a consulting analyst.
MEDICAL = re.compile(r"gastro|cardio|neuro|oncolog|orthop|physician|doctor|surgeon|\bmbbs\b|\bmd\b|dental|dentist|nurs(e|ing)|"
                     r"radiolog|patholog|ana?esthe|dermatolog|gynae?c|pa?ediatric|psychiatr|physiotherap|urolog|nephrolog", re.I)
SUFFIX = re.compile(r"\b(?:private|pvt|ltd|limited|llp|llc|inc|corp|corporation|co|company|technologies|technology|"
                    r"tech|solutions|services|labs|india|group|global|software|systems|ventures|the)\b\.?", re.I)


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", SUFFIX.sub(" ", (name or "").lower()))


def load(path: Path, fallback):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return fallback


# ---------------------------------------------------------------- AmbitionBox

class Pay:
    """AmbitionBox lookups, cached. A failure costs that lookup, never the run; after repeated
    refusals (a block) it stops asking for the rest of the run."""

    def __init__(self, offline: bool) -> None:
        self.offline = offline
        self.cache = load(CACHE, {"companies": {}, "pages": {}})
        self.refusals = 0
        self.asked = 0

    def fresh(self, entry: dict | None) -> bool:
        return bool(entry) and entry.get("at", "") >= (date.today() - timedelta(days=KEEP_DAYS)).isoformat()

    def get(self, url: str):
        if self.offline or self.refusals >= 5:
            return None
        time.sleep(PAUSE)
        self.asked += 1
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-IN,en;q=0.9"})
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return ""
            self.refusals += exc.code in (403, 429)
            print(f"  ambitionbox {exc.code} for {url[:90]}", file=sys.stderr)
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"  ambitionbox unreachable ({type(exc).__name__}) for {url[:90]}", file=sys.stderr)
        return None

    def company(self, name: str) -> dict | None:
        """The AmbitionBox company for an employer's name, matched closely or not at all."""
        key = norm(name)
        if not key:
            return None
        hit = self.cache["companies"].get(key)
        if self.fresh(hit) or (hit and self.offline):
            return hit.get("match")
        raw = self.get(f"{AB}/api/v2/search?{urllib.parse.urlencode({'query': name, 'category': 'company'})}")
        if raw is None:
            return hit.get("match") if hit else None
        try:
            found = json.loads(raw).get("data") or []
        except json.JSONDecodeError:
            found = []
        best, best_score = None, 0.0
        for c in found:
            score = difflib.SequenceMatcher(None, key, norm(c.get("name"))).ratio()
            if score > best_score or (score == best_score and best and (c.get("reviewCount") or 0) > (best.get("reviewCount") or 0)):
                best, best_score = c, score
        match = {"url": best["url"], "name": best["name"]} if best and best_score >= 0.86 else None
        self.cache["companies"][key] = {"at": date.today().isoformat(), "match": match}
        return match

    def page(self, path: str) -> dict | None:
        """One salary page's numbers: by experience, the fixed share, and the company's profile."""
        hit = self.cache["pages"].get(path)
        if self.fresh(hit) or (hit and self.offline):
            return hit.get("data")
        raw = self.get(f"{AB}{path}")
        if raw is None:
            return hit.get("data") if hit else None
        try:
            data = parse(raw) if raw else None
        except (ValueError, KeyError, TypeError, AttributeError) as exc:  # a page shaped differently costs that page
            print(f"  ambitionbox page not read ({type(exc).__name__}): {path}", file=sys.stderr)
            data = None
        self.cache["pages"][path] = {"at": date.today().isoformat(), "data": data}
        return data

    def save(self) -> None:
        if not self.offline:  # an offline run learns nothing new, and must not overwrite a live run's cache
            CACHE.write_text(json.dumps(self.cache, separators=(",", ":"), ensure_ascii=False))


def parse(html: str) -> dict | None:
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return None
    pp = (json.loads(m.group(1)).get("props") or {}).get("pageProps") or {}
    out: dict = {"levels": []}
    sd = ((pp.get("salaryData") or {}).get("data") or {}) if isinstance(pp.get("salaryData"), dict) else {}
    for lv in sd.get("experienceLevels") or []:   # a company and designation page
        out["levels"].append({"years": f"{lv.get('minExp')}-{lv.get('maxExp')}", "avg": lv.get("avgCtc"),
                              "lo": lv.get("typicalMinCtc") or lv.get("minCtc"), "hi": lv.get("typicalMaxCtc") or lv.get("maxCtc")})
    summary = sd.get("summaryData") or {}
    out["points"] = int(float(summary.get("totalSalaryDataPoints") or 0))
    out["fixed_pct"] = summary.get("fixedPercent")
    profile = ((pp.get("salaryData") or {}).get("profileSalaryData") or {}) if isinstance(pp.get("salaryData"), dict) else {}
    for lv in profile.get("experienceDistribution") or []:  # a designation page for all of India
        out["levels"].append({"years": lv.get("years"), "avg": lv.get("averageCtc"), "lo": lv.get("typicalMinCtc"),
                              "hi": lv.get("typicalMaxCtc"), "points": lv.get("datapoints")})
    info = {}
    for section in ((pp.get("companyInfo") or {}).get("overview") or {}).get("sectionsList") or []:
        if isinstance(section, dict) and isinstance(section.get("sectionData"), dict):
            info.update(section["sectionData"])
    if info:
        out["company"] = {"types": [t.get("name") for t in info.get("typeOfCompany") or [] if t.get("name")],
                          "ownership": (info.get("ownership") or {}).get("name") or info.get("type") or "",
                          "hq_country": (info.get("hq") or {}).get("country") or "",
                          "india_staff": info.get("indianEmployeeCountRange") or "",
                          "founded": info.get("foundedYear") or ""}
    return out if out["levels"] or out.get("company") else None


def fresher(levels: list[dict]) -> tuple[dict | None, str]:
    """The 0-1 years figure, or 1-2 years when 0-1 is missing or rests on too few salaries."""
    by = {lv["years"]: lv for lv in levels if lv.get("avg")}
    first = by.get("0-1")
    if first and (first.get("points") is None or first["points"] >= MIN_POINTS):
        return first, "0-1 years"
    second = by.get("1-2")
    return (second, "1-2 years (too few with 0-1)") if second else (first, "0-1 years") if first else (None, "")


def company_type(profile: dict | None, funded) -> str:
    types = [t.lower() for t in (profile or {}).get("types") or []]
    country = ((profile or {}).get("hq_country") or "").lower()
    if any("mnc" in t for t in types) and "indian" not in " ".join(types) and country != "india":
        return "MNC"
    if country and country != "india":
        return "MNC"
    if any("indian mnc" in t for t in types):
        return "Indian MNC"
    if any(t in ("startup", "unicorn") for t in types) or funded:
        return "Startup"
    if profile:
        return "Indian company, listed" if (profile.get("ownership") or "").lower() == "public" else "Indian company"
    return ""


def lakh(n) -> float:
    return round(float(n) / 1e5, 1)


def look_up_pay(pay: Pay, company: str, title: str, family: str, campus: dict, ratio: float) -> dict:
    """Expected CTC and base for one role, with where each number came from. An internship pays a
    stipend, so it gets no salary figure, and a campus offer never stands in for one."""
    if INTERN.search(title or ""):
        return {"basis": "Internship: a stipend, not a salary", "profile": None}
    offer = campus.get(norm(company))
    found = pay.company(company)
    profile, figure, used = None, None, ""
    if found:
        for desig in designations(title, family):
            data = pay.page(f"/salaries/{found['url']}-salaries/{desig}")
            if data and data.get("company"):
                profile = data["company"]
            level, span = fresher((data or {}).get("levels") or [])
            if level and (data.get("points") or 0) >= MIN_POINTS:
                figure = {"ctc": lakh(level["avg"]), "lo": lakh(level["lo"] or level["avg"]), "hi": lakh(level["hi"] or level["avg"]),
                          "span": span, "points": data.get("points"), "fixed_pct": data.get("fixed_pct"),
                          "source": f"{AB}/salaries/{found['url']}-salaries/{desig}",
                          "basis": f"AmbitionBox: {found['name']} {desig.replace('-', ' ')}s with {span}, {data.get('points')} salaries"}
                used = desig
                break
        if not profile:
            data = pay.page(f"/salaries/{found['url']}-salaries")
            profile = (data or {}).get("company")
    if not figure:
        desig = (designations(title, family) or [FAMILY_DESIGNATION.get(family, "business-analyst")])[0]
        data = pay.page(f"/profile/{desig}-salary")
        level, span = fresher((data or {}).get("levels") or [])
        if level:
            figure = {"ctc": lakh(level["avg"]), "lo": lakh(level["lo"] or level["avg"]), "hi": lakh(level["hi"] or level["avg"]),
                      "span": span, "points": level.get("points"), "fixed_pct": None,
                      "source": f"{AB}/profile/{desig}-salary",
                      "basis": f"AmbitionBox: {desig.replace('-', ' ')}s across India with {span} (no figure for this company)"}
            used = desig
    out = {"company": found["name"] if found else "", "company_url": f"{AB}/overview/{found['url']}-overview" if found else "",
           "profile": profile, "designation": used}
    if offer:   # a campus offer beats any average
        out.update(ctc=offer["ctc_lpa"], base=offer.get("base_lpa"), lo=offer["ctc_lpa"], hi=offer["ctc_lpa"],
                   basis=f"Campus offer for {offer.get('role') or 'a role'}, {offer.get('where') or 'on campus'}"
                         f"{', seen ' + day_text(offer['seen']) if offer.get('seen') else ''}", source="", estimate_base=False)
        if figure:
            out["market"] = figure
    elif figure:
        fixed = figure.get("fixed_pct")
        base = round(figure["ctc"] * float(fixed) / 100, 1) if fixed else round(figure["ctc"] * ratio, 1)
        out.update(ctc=figure["ctc"], lo=figure["lo"], hi=figure["hi"], base=base, basis=figure["basis"],
                   source=figure["source"], estimate_base=not fixed, points=figure.get("points"))
    return out


INTERN = re.compile(r"\bintern(ship)?s?\b", re.I)


def designations(title: str, family: str) -> list[str]:
    """The posting's own title as AmbitionBox would write it first ("decision-analytics-associate"),
    then the closest common designations for that kind of role."""
    t = (title or "").lower().replace("'", "").replace("’", "")
    if INTERN.search(t):
        return []   # stipends, not salaries
    core = re.split(r"\s[-–—|,:]\s|\(|\[", t)[0]
    core = re.sub(r"\b(?:i{1,3}|iv|l\d|\d{4}|fresher|freshers|entry level|jr\.?|junior|sr\.?|senior)\b", " ", core)
    own = re.sub(r"[^a-z]+", "-", core).strip("-")
    mapped = next((slugs for pattern, slugs in DESIGNATIONS if re.search(pattern, t)),
                  [FAMILY_DESIGNATION[family]] if family in FAMILY_DESIGNATION else [])
    return list(dict.fromkeys(([own] if own and 1 <= own.count("-") <= 4 else []) + mapped))


# ---------------------------------------------------------------- the list

def timing(r: dict) -> tuple[str, str]:
    """Can a May 2027 graduate take it: yes, check or no, and why."""
    batches = r.get("batches") or []
    if YEAR in batches:
        return "yes", "Names the 2027 batch"
    if batches:
        return "no", "For the " + ", ".join(map(str, batches)) + " batch" + ("es" if len(batches) > 1 else "")
    if r.get("kind") == "internship":
        return "check", "Internship: check it fits around the final semester"
    return "check", "Names no batch; most such roles want someone to join within weeks"


def day_text(iso: str) -> str:
    try:
        return f"{date.fromisoformat(iso[:10]):%-d %b %Y}"
    except ValueError:
        return iso


def deadline_line(r: dict) -> str:
    return f"Apply by {day_text(r['deadline'])}" if r.get("deadline") else "No deadline stated"


def main() -> None:
    offline = "--offline" in sys.argv
    DATA.mkdir(exist_ok=True)
    latest = load(LATEST, {})
    if not latest.get("roles"):
        raise SystemExit(f"No roles in {LATEST}; run the India tracker first (scripts/refresh.sh).")
    campus_offers = load(CAMPUS, {}).get("offers") or []
    campus = {norm(o["company"]): o for o in campus_offers if o.get("company") and o.get("ctc_lpa")}
    shares = [o["base_lpa"] / o["ctc_lpa"] for o in campus_offers if o.get("base_lpa") and o.get("ctc_lpa")]
    ratio = round(sorted(shares)[len(shares) // 2], 2) if shares else 0.8
    pay = Pay(offline)

    rows = []
    wanted = [r for r in latest["roles"] if r.get("family") in FAMILIES and r.get("tier") != "walled"
              and not MEDICAL.search(r.get("title") or "")]
    print(f"{len(wanted)} of {len(latest['roles'])} India roles are entry-level and in the families wanted", file=sys.stderr)
    for i, r in enumerate(wanted, 1):
        fit, why_fit = timing(r)
        priority, family = FAMILIES[r["family"]]
        p = look_up_pay(pay, r["company"], r["title"], r["family"], campus, ratio)
        rows.append({
            "key": f"india:{r['key']}", "title": r["title"], "company": r["company"], "city": r.get("city") or "",
            "location": r.get("location") or "", "url": r.get("apply_url") or r.get("url") or "", "family": family,
            "priority": priority, "kind": r.get("kind") or "full-time", "source": r.get("ats") or r.get("source") or "",
            "posted": r.get("posted") or "", "deadline": r.get("deadline") or "", "deadline_line": deadline_line(r),
            "min_years": r.get("min_years"), "fit": fit, "fit_why": why_fit, "batches": r.get("batches") or [],
            "company_type": company_type(p.get("profile"), r.get("funded")), "funded": r.get("funded"), **{
                k: p.get(k) for k in ("ctc", "lo", "hi", "base", "basis", "estimate_base", "points", "market",
                                      "company_url", "designation")}, "pay_source": p.get("source") or "",
            "first_seen": r.get("first_seen") or "", "row_kind": "role",
        })
        if i % 25 == 0:
            pay.save()
            print(f"  {i}/{len(wanted)} looked up ({pay.asked} AmbitionBox requests so far)", file=sys.stderr)

    for o in campus_offers:   # every campus offer is a row too, as the JAF said
        rows.append({
            "key": f"india:campus:{norm(o['company'])}:{norm(o.get('role'))}", "title": o.get("role") or "Role",
            "company": o["company"], "city": o.get("city") or "", "location": o.get("where") or "On campus",
            "url": o.get("url") or "", "family": o.get("family") or "Campus offer", "priority": 0, "kind": "full-time",
            "source": "campus", "posted": o.get("seen") or "", "deadline": o.get("deadline") or "",
            "deadline_line": f"Apply by {day_text(o['deadline'])}" if o.get("deadline") else "Through the placement cell",
            "min_years": 0, "fit": "yes", "fit_why": "A campus offer for the 2027 batch", "batches": [YEAR],
            "company_type": o.get("company_type") or "", "funded": None, "ctc": o.get("ctc_lpa"), "lo": o.get("ctc_lpa"),
            "hi": o.get("ctc_lpa"), "base": o.get("base_lpa"), "basis": f"Campus offer, {o.get('where') or 'on campus'}",
            "pay_source": "", "estimate_base": False, "points": None, "market": None, "company_url": "", "designation": "",
            "first_seen": o.get("seen") or "", "row_kind": "campus", "notes": o.get("notes") or "",
        })
    for g in load(PROGRAMS, {}).get("programs") or []:
        p = look_up_pay(pay, g["org"], g["pay_title"], g.get("pay_family") or "Business analyst", campus, ratio) \
            if g.get("pay_title") and not g.get("ctc_lpa") else {}
        if p.get("ctc"):
            g = dict(g, ctc_lpa=p["ctc"], base_lpa=p.get("base"), pay_basis=p.get("basis"), pay_source=p.get("source"),
                     pay_lo=p.get("lo"), pay_hi=p.get("hi"), estimate_base=p.get("estimate_base"))
        rows.append({
            "key": f"india:program:{g['id']}", "title": g["name"], "company": g["org"], "city": g.get("city") or "",
            "location": g.get("city") or "India", "url": g.get("url") or "", "family": g.get("family") or "Graduate programme",
            "priority": 1, "kind": "programme", "source": "programme", "posted": "", "deadline": g.get("deadline") or "",
            "deadline_line": g.get("window") or ("Apply by " + g["deadline"] if g.get("deadline") else "Window not announced"),
            "min_years": 0, "fit": g.get("fit") or "check", "fit_why": g.get("fit_why") or "", "batches": [YEAR],
            "company_type": g.get("company_type") or "", "funded": None, "ctc": g.get("ctc_lpa"),
            "lo": g.get("pay_lo") or g.get("ctc_lpa"), "hi": g.get("pay_hi") or g.get("ctc_lpa"), "base": g.get("base_lpa"),
            "basis": g.get("pay_basis") or "", "pay_source": g.get("pay_source") or "",
            "estimate_base": bool(g.get("estimate_base")), "points": None, "market": None, "company_url": "", "designation": "",
            "first_seen": "", "row_kind": "programme", "notes": g.get("notes") or "", "sources": g.get("sources") or [],
        })

    pay.save()   # after the programmes too: their lookups are cached like any role's

    order = {"yes": 0, "check": 1, "no": 2}
    rows.sort(key=lambda x: (x["row_kind"] == "role", order.get(x["fit"], 1), x["priority"], -(x.get("ctc") or 0),
                             x.get("posted") or ""))
    for i, x in enumerate(rows, 1):
        x["rank"] = i
    counts = {"roles": sum(x["row_kind"] == "role" for x in rows), "campus": len(campus_offers),
              "programmes": sum(x["row_kind"] == "programme" for x in rows),
              "with_pay": sum(bool(x.get("ctc")) for x in rows),
              "company_pay": sum(bool(x.get("ctc")) and "across India" not in (x.get("basis") or "") for x in rows),
              "types": {t or "Not known": sum(x["company_type"] == t for x in rows) for t in sorted({x["company_type"] for x in rows})},
              "base_ratio": ratio, "ambitionbox_requests": pay.asked}
    head = {"generated": datetime.now(IST).isoformat(timespec="seconds"), "source_generated": latest.get("generated")}
    FULL_JSON.parent.mkdir(exist_ok=True)
    FULL_JSON.write_text(json.dumps({**head, "counts": counts, "roles": rows}, ensure_ascii=False, indent=1) + "\n")
    public = without_campus(rows)
    OUT_JSON.write_text(json.dumps({**head, "counts": dict(counts, campus=0), "roles": public},
                                   ensure_ascii=False, indent=1) + "\n")
    write_csv(public)
    print(f"{counts['roles']} roles, {counts['campus']} campus offers, {counts['programmes']} programmes; pay for "
          f"{counts['with_pay']} ({counts['company_pay']} from the company's own salaries); company types: {counts['types']}; "
          f"{pay.asked} AmbitionBox requests", file=sys.stderr)


def without_campus(rows: list[dict]) -> list[dict]:
    """The list for this public repo: no campus offers, and a role whose pay came from one shows the
    AmbitionBox figure instead. Placement-cell details stay in private/."""
    out = []
    for x in rows:
        if x["row_kind"] == "campus":
            continue
        if (x.get("basis") or "").startswith("Campus offer"):
            m = x.get("market") or {}
            ratio = 0.8
            x = dict(x, ctc=m.get("ctc"), lo=m.get("lo"), hi=m.get("hi"), basis=m.get("basis") or "",
                     pay_source=m.get("source") or "", estimate_base=bool(m.get("ctc")),
                     base=round(m["ctc"] * ratio, 1) if m.get("ctc") else None, market=None)
        out.append(x)
    return out


def write_csv(rows: list[dict]) -> None:
    cols = ["rank", "row_kind", "family", "title", "company", "company_type", "city", "fit", "fit_why", "ctc_lpa",
            "ctc_range_lpa", "base_lpa", "base_is_estimate", "pay_basis", "deadline_line", "posted", "url"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for x in rows:
            w.writerow([x["rank"], x["row_kind"], x["family"], x["title"], x["company"], x["company_type"], x["city"], x["fit"],
                        x["fit_why"], x.get("ctc") or "", f"{x['lo']}–{x['hi']}" if x.get("lo") and x.get("hi") and x["lo"] != x["hi"] else "",
                        x.get("base") or "", "yes" if x.get("estimate_base") else "", x.get("basis") or "", x["deadline_line"],
                        x.get("posted") or "", x.get("url") or ""])


if __name__ == "__main__":
    main()
