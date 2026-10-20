"""Entry-level business roles in India at the employers that pay IIT freshers the most, from their own careers sites.

The India tracker at the repo root reads LinkedIn, Indeed and about fifteen company boards, so big tech, global banks
and funds, consulting firms and the top Indian unicorns rarely reach India/: they post on their own careers systems.
This reads every employer in top_employers.json from its system's public feed (Greenhouse, Lever, Ashby,
SmartRecruiters, Workday, Oracle, Eightfold, Amazon, Google, Atlassian) and keeps the roles that fit Prathmesh's
primary resume and a May 2027 graduate:

  where     in India
  what      product, business or data analyst, strategy, consulting, finance, founder's office or growth; not
            software engineering, quant or trading, sales, support, operations processing, HR, legal or marketing
  level     not senior (no senior, lead, manager, director, II or III) and not an internship
  years     the posting asks for at most one year, or says nothing ("0-2 years" counts as 0); one asking for 2+ is
            dropped. A posting that names only earlier batches is dropped too.

Workday, Oracle, SmartRecruiters and Eightfold list titles first, so a description is read only for a title that
passes. fetch_india.py adds pay from AmbitionBox and ranks these with the rest.

  .venv/bin/python India/fetch_top.py    # writes data/top_roles.json
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "Japan"))
from enrich import batches, min_years  # noqa: E402  the India tracker's readers of a posting's batch and experience
from fetch_japan import UA, clean, http, iso  # noqa: E402  the Japan tracker's careers-feed helpers

EMPLOYERS = HERE / "top_employers.json"
OUT = HERE / "data" / "top_roles.json"
IST = timezone(timedelta(hours=5, minutes=30))
YEAR = 2027

INDIA = re.compile(r"\b(india|bengaluru|bangalore|mumbai|gurgaon|gurugram|delhi|new delhi|noida|ncr|hyderabad|pune|"
                   r"chennai|kolkata|ahmedabad|jaipur|kochi|chandigarh|indore|coimbatore|thiruvananthapuram|mohali|"
                   r"navi mumbai|thane)\b", re.I)
CITIES = {"bangalore": "Bengaluru", "bengaluru": "Bengaluru", "gurgaon": "Gurugram", "gurugram": "Gurugram",
          "new delhi": "Delhi", "delhi": "Delhi", "ncr": "Delhi"}

# Kinds of role that fit the primary resume, most specific first. The keys are fetch_india.py's families.
FAMILY_RULES = [
    ("Product", r"associate product manager|\bapm\b|product analyst|product associate|product manager|product strategy"),
    ("Founder's office", r"founder'?s office|chief of staff|office of the (?:ceo|founder)"),
    ("Consulting", r"consult"),
    ("Strategy", r"strateg|business operations|\bbizops\b|corporate development|business planning"),
    ("Finance", r"investment bank|equity research|\binvestment (?:analyst|associate)|private equity|venture|valuation|"
                r"corporate finance|financial (?:analyst|planning|analysis)|\bfp&a\b|credit (?:analyst|research)|"
                r"treasury analyst|research analyst|portfolio analyst|\bm&a\b|capital markets|investor relations"),
    ("Business analyst", r"business analyst|data analyst|analytics|decision scien|insights|business intelligence|"
                         r"\bbi analyst|pricing analyst|risk analyst|\banalyst\b"),
    ("Growth", r"\bgrowth\b"),
    ("Management trainee", r"management trainee|graduate trainee|graduate programme|graduate program|early careers?"),
]
FAMILY_RULES = [(name, re.compile(rx, re.I)) for name, rx in FAMILY_RULES]

# Titles that are something else even when they contain "analyst" or "associate".
OTHER = re.compile(
    r"quant|trading|\btrader\b|software|developer|engineer|\bsde\b|scientist|machine learning|\bml\b|"
    r"technology analyst|\bit analyst|systems analyst|security|\bsoc\b|cyber|network|\bqa\b|test|application analyst|"
    r"support|customer|client service|service desk|helpdesk|\bsales\b|account (?:executive|manager)|business development|"
    r"recruit|talent|\bhr\b|human resources|people (?:partner|operations)|payroll|legal|counsel|paralegal|compliance|"
    r"\baudit|\btax\b|accountant|accounting|reconcil|settlement|\bkyc\b|\baml\b|fund (?:accounting|administration)|"
    r"middle office|back office|collections?|loan (?:servicing|operations)|transaction (?:processing|services)|"
    r"marketing|admin|facilit|assistant|receptionist|technician|data ?cent(?:er|re)|warehouse|dining|catering|chef|driver|"
    r"coordinator|account mgmt|workday|functional analyst|oracle applications|servicing|reference data|finops|"
    r"accounts payable|icqa|quality associate|\bwfm\b|python|react|\bjava\b|content|creator|editor|designer|"
    r"illustrator|video|writer|procurement|german|french|spanish|japanese|mandarin|arabic|"
    # bank operations and technology roles titled "analyst" (Citi, Deutsche Bank, JPMorgan)
    r"\bproc\b|processing|capture|onboard|loan doc|proofing|\brec\b|sanctions|programmer|apps dev|"
    r"applications development|\bit business analyst|regulatory|acctg|rptg|reporting analyst|transfer pricing|"
    r"securities & derivat|control analyst|risk & control|\bcoe\b",
    re.I)
# Operations processing roles, unless the title is strategy or business operations ("Strategy & Operations Analyst").
OPS = re.compile(r"operations|\bops\b", re.I)
OPS_OK = re.compile(r"strateg|business operations|\bbizops\b|chief of staff", re.I)
SENIOR = re.compile(r"\b(?:senior|sr|staff|principal|lead|leader|head|director|vp|avp|vice president|president|chief|"
                    r"architect|expert|distinguished|fellow|officer|partner|specialist|ii|iii|iv|l[3-9]|ic[3-9]|manager)\b|"
                    r"\b(?:level|grade|band|analyst|associate|consultant)\s*[2-9]\b|\bc1\d\b|mid-level|\bld\b", re.I)
# Years written into the title ("SAS Data Analyst - 3-5 Years"); the first number is the minimum.
TITLE_YEARS = re.compile(r"(\d+)\s*(?:[-–to]+\s*\d+\s*)?\+?\s*(?:yrs?|years?)\b", re.I)
# Removed before SENIOR is checked: the entry-level titles that contain "manager" or "staff".
NOT_SENIOR = re.compile(r"(?<!group )(?:associate )?product manager|chief of staff", re.I)
INTERN = re.compile(r"\bintern(?:ship)?s?\b|\bsummer (?:analyst|associate)|apprentice|\bco-?op\b", re.I)
# An MBA, CA or CFA named as a requirement. "CA" alone is a US state too often to count.
DEGREE = re.compile(r"\bMBA\b|\bPGDM\b|\bCFA\b|[Cc]hartered [Aa]ccountant|[Qq]ualified CA\b|"
                    r"\bCA\s*(?:/|or|,|and)\s*(?:MBA|CFA|CMA|ICWA)\b|\b(?:MBA|CFA)\s*(?:/|or|,|and)\s*CA\b")
PREFERRED = re.compile(r"prefer|plus|advantage|desirable|nice to have|good to have|bonus", re.I)


def family(title: str) -> str:
    """The kind of role, or "" when it is not one the primary resume fits."""
    if OTHER.search(title) or INTERN.search(title):
        return ""
    if OPS.search(title) and not OPS_OK.search(title):
        return ""
    if SENIOR.search(NOT_SENIOR.sub(" ", title)):
        return ""
    if (m := TITLE_YEARS.search(title)) and int(m.group(1)) >= 2:
        return ""
    return next((name for name, rx in FAMILY_RULES if rx.search(title)), "")


def city_of(location: str) -> str:
    m = INDIA.search(location or "")
    if not m or m.group(1).lower() == "india":
        return "India"
    word = m.group(1).lower()
    return CITIES.get(word, word.title())


def degree_asked(text: str) -> str:
    """"preferred" or "asked" when the posting names an MBA, CA or CFA, else ""."""
    found = ""
    for m in DEGREE.finditer(text or ""):
        near = text[max(0, m.start() - 80): m.end() + 80]
        if PREFERRED.search(near):
            found = found or "preferred"
        else:
            return "asked"
    return found


# ---------------------------------------------------------------- careers feeds
# Each yields dicts: id, title, location, url, posted, and either text or detail (a function that returns
# {"text", "posted", "url", "location"} for the one job, called only when its title passes).

def gh(e):
    for j in http(f"https://boards-api.greenhouse.io/v1/boards/{e['slug']}/jobs?content=true")["jobs"]:
        where = (j.get("location") or {}).get("name") or ""
        offices = ", ".join(o.get("name") or "" for o in j.get("offices") or [])
        yield dict(id=str(j["id"]), title=j.get("title") or "", location=f"{where} ({offices})" if offices else where,
                   url=j.get("absolute_url") or "", posted=iso(j.get("first_published") or j.get("updated_at")),
                   text=clean(j.get("content")))


def lever(e):
    for j in http(f"https://api.lever.co/v0/postings/{e['slug']}?mode=json"):
        cats = j.get("categories") or {}
        where = cats.get("location") or ""
        if (j.get("country") or "").upper() == "IN" and not INDIA.search(where):
            where = f"{where}, India".strip(", ")
        lists = " ".join(f"{l.get('text', '')}. {clean(l.get('content'))}" for l in j.get("lists") or [])
        yield dict(id=j["id"], title=j.get("text") or "", location=where, url=j.get("hostedUrl") or "",
                   posted=iso(j.get("createdAt")),
                   text=clean(f"{j.get('descriptionPlain', '')} {lists} {j.get('additionalPlain', '')}"))


def ashby(e):
    for j in http(f"https://api.ashbyhq.com/posting-api/job-board/{e['slug']}")["jobs"]:
        if not j.get("isListed", True):
            continue
        locs = [j.get("location") or ""] + [s.get("location") or "" for s in j.get("secondaryLocations") or []]
        country = (((j.get("address") or {}).get("postalAddress") or {}).get("addressCountry") or "")
        where = " / ".join(l for l in locs if l) + (" (India)" if country == "India" else "")
        yield dict(id=j["id"], title=j.get("title") or "", location=where, url=j.get("jobUrl") or "",
                   posted=iso(j.get("publishedAt")), text=clean(j.get("descriptionHtml") or j.get("descriptionPlain")))


def smartrecruiters(e):
    def detail(ref):
        ad = (http(ref).get("jobAd") or {}).get("sections") or {}
        return {"text": clean(" ".join((ad.get(k) or {}).get("text") or "" for k in
                                       ("jobDescription", "qualifications", "additionalInformation")))}
    offset = 0
    while True:
        page = http(f"https://api.smartrecruiters.com/v1/companies/{e['slug']}/postings?country=in&limit=100&offset={offset}")
        for j in page.get("content") or []:
            yield dict(id=j["id"], title=j.get("name") or "", location=f"{(j.get('location') or {}).get('city') or ''}, India",
                       url=f"https://jobs.smartrecruiters.com/{e['slug']}/{j['id']}", posted=iso(j.get("releasedDate")),
                       detail=lambda ref=j["ref"]: detail(ref))
        offset += 100
        if offset >= (page.get("totalFound") or 0):
            break


def workday(e):
    host, tenant, site = e["slug"].split("/")
    base = f"https://{host}/wday/cxs/{tenant}/{site}"

    def detail(path):
        info = http(f"{base}{path}").get("jobPostingInfo") or {}
        return {"text": clean(info.get("jobDescription")), "posted": iso(info.get("startDate")),
                "url": info.get("externalUrl") or "", "location": info.get("location") or ""}
    listed: dict[str, dict] = {}
    for term in e.get("search") or ["India"]:
        offset, total = 0, 0
        while True:
            page = http(f"{base}/jobs", {"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": term})
            total = page.get("total") or total   # Workday reports the total on the first page only
            for j in page.get("jobPostings") or []:
                listed.setdefault(j.get("externalPath", ""), j)
            offset += 20
            if offset >= total or offset >= 1000 or not page.get("jobPostings"):
                break
    for path, j in listed.items():
        yield dict(id=path, title=j.get("title") or "", location=j.get("locationsText") or "",
                   url=f"https://{host}/{site}{path}", posted="", detail=lambda path=path: detail(path))


def oracle(e):
    host, site = e["slug"].split("/")
    api = f"https://{host}/hcmRestApi/resources/latest"

    def detail(jid):
        d = http(f"{api}/recruitingCEJobRequisitionDetails?expand=all&onlyData=true&finder=ById;Id=%22{jid}%22,siteNumber={site}")
        info = (d.get("items") or [{}])[0]
        return {"text": clean(" ".join(info.get(k) or "" for k in
                                       ("ExternalDescriptionStr", "ExternalQualificationsStr", "ExternalResponsibilitiesStr")))}
    offset = 0
    while True:
        items = (http(f"{api}/recruitingCEJobRequisitions?onlyData=true&expand=requisitionList.secondaryLocations"
                      f"&finder=findReqs;siteNumber={site},limit=50,offset={offset},locationId={e['location_id']},"
                      f"sortBy=POSTING_DATES_DESC").get("items") or [{}])[0]
        reqs = items.get("requisitionList") or []
        for j in reqs:
            jid = str(j.get("Id"))
            yield dict(id=jid, title=j.get("Title") or "", location=f"{j.get('PrimaryLocation') or ''} (India)",
                       url=f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{jid}",
                       posted=iso(j.get("PostedDate")), detail=lambda jid=jid: detail(jid))
        offset += 50
        if not reqs or offset >= (items.get("TotalJobsCount") or 0) or offset >= 3000:
            break


def amazon(e):
    offset = 0
    while True:
        page = http("https://www.amazon.jobs/en/search.json?normalized_country_code%5B%5D="
                    f"{e['slug']}&result_limit=100&offset={offset}&sort=recent")
        jobs = page.get("jobs") or []
        for j in jobs:
            try:
                posted = datetime.strptime(" ".join((j.get("posted_date") or "").split()), "%B %d, %Y").date().isoformat()
            except ValueError:
                posted = ""
            yield dict(id=str(j.get("id_icims") or j.get("id")), title=j.get("title") or "",
                       location=f"{j.get('normalized_location') or j.get('city') or ''} (India)",
                       url="https://www.amazon.jobs" + (j.get("job_path") or ""), posted=posted,
                       text=clean(" ".join(j.get(k) or "" for k in
                                           ("description", "basic_qualifications", "preferred_qualifications"))))
        offset += 100
        if not jobs or offset >= (page.get("hits") or 0):
            break


def pcsx(e):
    """Eightfold's careers API (Microsoft, Qualcomm): slug is "<host>/<domain>"."""
    host, domain = e["slug"].split("/", 1)
    api = f"https://{host}/api/pcsx"

    def detail(pid):
        time.sleep(2)
        return {"text": clean((http(f"{api}/position_details?position_id={pid}&domain={domain}&hl=en").get("data") or {})
                              .get("jobDescription"))}
    start = 0
    while True:
        data = http(f"{api}/search?domain={domain}&query=&location=India&start={start}&num=10").get("data") or {}
        positions = data.get("positions") or []
        for j in positions:
            std = j.get("standardizedLocations") or []
            places = " / ".join(j.get("locations") or [])
            in_india = any(re.search(r"(?:^|, )IN$", s) for s in std) or bool(INDIA.search(places))
            yield dict(id=str(j["id"]), title=j.get("name") or "", location=places + (" (India)" if in_india else ""),
                       url=f"https://{host}{j.get('positionUrl') or ''}", posted=iso((j.get("postedTs") or 0) * 1000),
                       detail=lambda pid=j["id"]: detail(pid))
        start += 10
        if not positions or start >= (data.get("count") or 0):
            break
        time.sleep(3)   # Microsoft's answers 429 to a fast run


def google(e):
    """Google's early-career roles in India: the results page embeds 20 jobs, with descriptions, per page."""
    page, total = 1, None
    while total is None or (page - 1) * 20 < total:
        url = ("https://www.google.com/about/careers/applications/jobs/results/"
               f"?location=India&target_level=EARLY&page={page}")
        doc = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=40).read().decode("utf-8", "replace")
        blocks = dict(re.findall(r"AF_initDataCallback\(\{key: '(ds:\d+)'.*?data:(.*?), sideChannel", doc, re.S))
        data = json.loads(blocks["ds:1"])
        total = data[2] if len(data) > 2 and isinstance(data[2], int) else 0
        for j in data[0] or []:
            places = [p[0] for p in (j[9] or []) if p]
            parts = " ".join(x[1] for x in (j[3], j[4], j[10], j[19]) if isinstance(x, list) and len(x) > 1 and x[1])
            yield dict(id=str(j[0]), title=j[1] or "", location=" / ".join(places),
                       url=f"https://www.google.com/about/careers/applications/jobs/results/{j[0]}",
                       posted=iso((j[12] or [0])[0] * 1000) if j[12] else "", text=clean(parts))
        if not data[0]:
            break
        page += 1
        time.sleep(1.5)


def atlassian(e):
    for j in http("https://www.atlassian.com/endpoint/careers/listings"):
        portal = j.get("portalJobPost") or {}
        yield dict(id=str(j.get("id")), title=j.get("title") or "", location=" / ".join(j.get("locations") or []),
                   url=portal.get("portalUrl") or "", posted=(portal.get("updatedDate") or "")[:10],
                   text=clean(" ".join(j.get(k) or "" for k in ("overview", "responsibilities", "qualifications"))))


FEEDS = {"greenhouse": gh, "lever": lever, "ashby": ashby, "smartrecruiters": smartrecruiters, "workday": workday,
         "oracle": oracle, "amazon": amazon, "pcsx": pcsx, "google": google, "atlassian": atlassian}


# ---------------------------------------------------------------- one employer

def read(e: dict) -> tuple[dict, list[dict]]:
    report = {"company": e["company"], "tier": e["tier"], "ats": e["ats"], "listed": 0, "titles": 0, "kept": 0, "error": ""}
    kept = []
    try:
        for j in FEEDS[e["ats"]](e):
            report["listed"] += 1
            if not INDIA.search(j["location"]) and not j.get("detail"):
                continue
            fam = family(j["title"])
            if not fam:
                continue
            if j.get("detail"):
                if not INDIA.search(j["location"]) and not re.search(r"\d+ locations", j["location"], re.I):
                    continue
                try:
                    j.update({k: v for k, v in j.pop("detail")().items() if v})
                except Exception as exc:   # a failed description costs that job's checks, not the employer
                    print(f"  {e['company']}: no description for {j['title'][:60]} ({type(exc).__name__})", file=sys.stderr)
                    j.pop("detail", None)
                if not INDIA.search(j["location"]):
                    continue
            report["titles"] += 1
            if e.get("title_has") and e["title_has"].lower() not in f"{j['title']} {j.get('text', '')}".lower():
                continue
            text = j.get("text") or ""
            years = min_years(text) if text else None
            if years is not None and years > 1:
                continue
            named = batches(text) if text else []
            if named and max(named) < YEAR:
                continue
            kept.append({
                "key": f"top:{e['ats']}:{re.sub(r'[^a-z0-9]+', '', e['company'].lower())}:{j['id']}",
                "title": " ".join(j["title"].split()), "company": e["company"], "ambitionbox": e.get("ambitionbox") or "",
                "tier": e["tier"], "family": fam, "city": city_of(j["location"]),
                "location": re.sub(r"\s*\((?:India)\)$", "", j["location"]).strip() or "India",
                "url": j.get("url") or "", "apply_url": j.get("url") or "", "posted": j.get("posted") or "",
                "deadline": "", "min_years": years, "batches": named, "kind": "full-time",
                "degree": degree_asked(text), "described": bool(text), "ats": e["ats"], "source": "careers",
                "funded": None,
            })
    except Exception as exc:   # one employer's feed failing costs that employer, not the run
        report["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
    report["kept"] = len(kept)
    return report, kept


def merge_cities(rows: list[dict]) -> list[dict]:
    """Amazon and Workday post one role once per city. Keep one row, list the cities."""
    out: dict[tuple, dict] = {}
    for r in rows:
        k = (r["company"], re.sub(r"[^a-z0-9]+", "", r["title"].lower()))
        if k not in out:
            out[k] = r
        elif r["city"] not in out[k]["location"]:
            out[k]["location"] = f"{out[k]['location']} / {r['city']}"
    return list(out.values())


def main() -> None:
    cfg = json.loads(EMPLOYERS.read_text())
    employers = cfg["employers"]
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(read, employers))
    rows = merge_cities([r for _, kept in results for r in kept])
    reports = [rep for rep, _ in results]
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"generated": datetime.now(IST).isoformat(timespec="seconds"), "tiers": cfg["tiers"],
                               "employers": reports, "roles": rows}, ensure_ascii=False, indent=1) + "\n")
    for rep in reports:
        print(f"  {rep['company']:<28} {rep['ats']:<15} listed {rep['listed']:>5}  kept {rep['kept']:>3}"
              f"{'  ERROR ' + rep['error'] if rep['error'] else ''}", file=sys.stderr)
    failed = [rep["company"] for rep in reports if rep["error"]]
    print(f"{len(rows)} roles kept from {len(employers)} employers"
          f"{'; failed: ' + ', '.join(failed) if failed else ''}", file=sys.stderr)


if __name__ == "__main__":
    main()
