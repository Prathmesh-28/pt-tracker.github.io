"""Case competitions, and any contest that leads to a job, live from Unstop and ranked for Prathmesh.

Unstop (once Dare2Compete) is where nearly every Indian case competition, corporate challenge and
hackathon takes registrations. Its public API returns every open listing, and each listing's own page
says who may enter (passout years, courses, branches, the campuses allowed), the prizes and whether
they include a pre-placement interview (PPI) or offer (PPO), the rounds and the dates.

Every open listing is read and ranked for the person in profile.json (IIT Bombay, B.Tech, 2027):

  1  IIT only                only IIT students may enter
  2  Top-paying employer     quant and trading, investment banks, top strategy consulting, big tech,
                             with a hiring route or a prize
  3  Select campuses         a short list of campuses that includes IIT Bombay, or an employer that
     or strong pay           pays well (product, fintech, payments, consulting)
  4  Big company             open to everyone: Tata, ITC, Reliance, FMCG, banks, IT services, which
                             pay an IITian less (employers.json)
  5  College or other        college fests and small organisers: the prize and a line on the CV

Within a band: a PPO, PPI or internship first, then the bigger prize, then the better-paying employer,
then a case competition; ties go to the nearer deadline. Listings an IIT Bombay 2027 B.Tech cannot
enter (MBA only, other batches, other campuses, working professionals) are kept with the reason but
not ranked, and neither are cultural events, workshops or ambassador programmes.

The watchlist (watchlist.json) covers the big competitions between seasons: every past edition found
on Unstop, or dates checked by hand for those run elsewhere (quant contests, bank hackathons).

  .venv/bin/python CaseCompetitions/fetch_competitions.py            # pull, rank, write data/
  .venv/bin/python CaseCompetitions/fetch_competitions.py --offline  # re-rank the last pull, no requests

Writes data/competitions.json (every open listing, ranked, with the reasons), data/competitions.csv,
data/watchlist.json and data/seen.json (the first and last day each listing was open). Each listing's
own page is cached in data/details.json (gitignored) and read again only when the listing changes.
"""

from __future__ import annotations

import csv
import html
import json
import math
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
PROFILE = HERE / "profile.json"
EMPLOYERS = HERE / "employers.json"
WATCHLIST = HERE / "watchlist.json"
OUT_JSON = DATA / "competitions.json"
OUT_CSV = DATA / "competitions.csv"
WATCH_OUT = DATA / "watchlist.json"
SEEN = DATA / "seen.json"
LISTINGS = DATA / "listings.json"   # the last raw pull, for --offline; gitignored
DETAILS = DATA / "details.json"     # each listing's own page, trimmed; gitignored

API = "https://unstop.com/api/public"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
KINDS = ("competitions", "hackathons", "quizzes")
PAUSE = 0.7        # seconds between requests, one at a time
IST = timezone(timedelta(hours=5, minutes=30))
USD_INR = 85       # rough, only to rank a prize paid in dollars against one in rupees

BANDS = {1: "IIT only", 2: "Top-paying employer", 3: "Select campuses or strong pay",
         4: "Big company, open to all", 5: "College fest or small organiser"}
CHANNEL_POINTS = {"ppo": 30, "ppi": 25, "intern": 15}
CHANNEL_LABEL = {"ppo": "PPO or job offer", "ppi": "PPI", "intern": "Internship"}

PROF = json.loads(PROFILE.read_text())
YEAR = int(PROF["passout_year"])
MY_IDS = set(PROF["unstop_institute_ids"])
MY_NAME = re.compile(PROF["institute_pattern"], re.I)
NOT_MINE = re.compile(PROF["not_institute_pattern"], re.I)
MY_COURSES = set(PROF["unstop_courses"])
MY_BRANCH = re.compile(PROF["branch_pattern"], re.I)

_EMP = json.loads(EMPLOYERS.read_text())
GROUPS = [dict(g, re=re.compile(g["pattern"], re.I)) for g in _EMP["groups"]]
NOT_EMPLOYER = re.compile(_EMP["not_employer"], re.I)

# ---------------------------------------------------------------- reading the text

TAG = re.compile(r"<[^>]+>")
PPO = re.compile(r"\bPPOs?\b|pre[- ]?placement offers?|job offers?|full[- ]time (?:offers?|roles?|positions?)|"
                 r"placement offers?", re.I)
PPI = re.compile(r"\bPPIs?\b|pre[- ]?placement interviews?|interview (?:opportunit|call|shortlist)|"
                 r"fast[- ]?track(?:ed)? (?:to|into|for) (?:an? |the )?(?:final )?interview|direct (?:final )?interviews?", re.I)
INTERN = re.compile(r"internship (?:offers?|opportunit\w*|roles?)|summer internships?|paid internships?|"
                    r"\bPPI for internship|internships? (?:at|with)\b", re.I)
COMMUNITY = re.compile(r"ambassador|developer groups?|\bgdg\b|user groups?|communit|learn student|cloud club", re.I)
# A company counts as behind a college event only when the event says so: named next to the offer
# ("PPI with Yes Securities"), joined to the title ("Optiver & Economicus", "Anthill Ventures X Yes
# Securities", "powered by Swiggy"), or after "sponsored by" and the like in the description. A
# company's name alone is not enough: "Graviton" and "Voice of the Oracle" are college events.
OFFER_FROM = re.compile(r"(?i:PP[IO]s?|interviews?|internships?|offers?)\s+(?i:with|at|from|by)\s+([A-Z][\w&.' -]{2,40})")
JOINED = r"(?:sponsored|powered|presented|supported|brought to you) by|in (?:association|collaboration|partnership) with|partnered with"
TITLE_JOIN = re.compile(rf"\s(?:x|×|&)\s|{JOINED}", re.I)
TITLE_PARTS = re.compile(rf"\s(?:x|×|&)\s|{JOINED}|\s[|:–—-]\s|[|:]", re.I)
BODY_JOIN = re.compile(rf"{JOINED}|title sponsor(?:ed by)?:?", re.I)
NOT_SPONSOR = re.compile(r"credits?|vouchers?|goodies|swag|merch|subscription|premium", re.I)
REWARD = re.compile(r"prizes?|rewards?|winners?|winning|finalists?|runners?[- ]up|top \d+|perks?|benefits?|stand a chance|"
                    r"will (?:get|receive|be offered|be considered)|shortlisted", re.I)
SUBSTANTIVE = ("Case competition", "Hackathon or coding", "Ideathon", "Hiring challenge", "B-plan or pitch", "Quiz")
NOT_COMPETITION = re.compile(
    r"campus ambassador|ambassador program|\bworkshop|webinar|masterclass|bootcamp|\bcourse\b|certification|"
    r"learn(?:ing)? with|study jam|skill ?fest|giveaway|open mic|fashion|ramp walk|\bdance|singing|\bmusic|"
    r"drama|theatre|photography|painting|sketch|poetry|rangoli|mehendi|cooking|gaming|free fire|bgmi|valorant|"
    r"e-?sports|\bchess\b|\bsports?\b|cricket|football|kabaddi|debat", re.I)
BUSINESS = re.compile(
    r"\bcase|strateg|consult|product|financ|invest|equity|stock|trading|quant|analytic|\bdata\b|marketing|"
    r"operation|supply chain|business|b-?plan|startup|venture|ideathon|innovation|policy|econom|fintech|growth|"
    r"brand|\bhr\b|human resource|\bsales\b|management|decision|crisis|valuation|research", re.I)
IIT_FAMILY = re.compile(r"Indian Institute of Technology|\bIIT\b|\bIISc\b|Indian Institute of Science\b", re.I)
PREMIER = re.compile(
    r"Indian Institute of (?:Technology|Management|Science)|\bII[TM]\b|IISc|\bBITS\b|Birla Institute of Technology "
    r"(?:&|and) Science|Indian School of Business|\bISB\b|XLRI|Faculty of Management Studies|\bFMS\b|SPJIMR|"
    r"S\.? ?P\.? Jain|Jamnalal Bajaj|JBIMS|Management Development Institute|\bMDI\b|National Institute of Technology|"
    r"\bNIT\b|Delhi Technological|\bDTU\b|\bIIIT|International Institute of Information Technology|"
    r"Indian Statistical Institute|\bISI\b|Chennai Mathematical|Delhi School of Economics|Shailesh J\.? Mehta|"
    r"NITIE|Indian Institute of Foreign Trade|\bIIFT\b|St\.? Stephen|Shri Ram College|\bSRCC\b", re.I)
# Campuses named in the rules rather than in Unstop's list: "only for students of IITs", or "students
# enrolled at: IITs: Bombay, Delhi, … NITs: …". Plural IITs only: "exclusively for the IIT Gandhinagar
# zonal round" is a zone, not a campus rule.
CAMPUS_TEXT = re.compile(r"(?:enrolled|studying)\s+(?:at|in)\s*:?\s*(IITs\b.{0,600})|"
                         r"(?:only|exclusively)\s+(?:for|to|open to)\s+(?:the\s+|all\s+)?(?:students\s+(?:of|from)\s+)?"
                         r"(?:the\s+|all\s+)?(IITs\b.{0,300})|\b(IIT students only)\b", re.I)
OTHER_CAMPUSES = re.compile(r"\b(?:NITs?|IIITs?|BITS|IIMs?|ISB|XLRI|SRCC|Others?|other colleges|universities)\b")
AMOUNT = re.compile(r"(?:INR|Rs\.?|₹)\s*([\d,]+(?:\.\d+)?)\s*(lakhs?|lacs?|crores?|cr\b|k\b)?|"
                    r"([\d.]+)\s*(lakhs?|lacs?|crores?)\b", re.I)


def text_of(markup: str | None) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG.sub(" ", markup or ""))).strip()


def when(value) -> datetime | None:
    if not value:
        return None
    s = str(value).strip().replace(" GMT", "").replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=IST)


def short_day(dt: datetime | None) -> str:
    return f"{dt.astimezone(IST):%-d %b %Y}" if dt else ""


def load(path: Path, fallback):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return fallback


# ---------------------------------------------------------------- fetching

def http(url: str, tries: int = 4):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 502, 503, 504) and attempt < tries - 1:
                time.sleep(int(exc.headers.get("Retry-After") or 0) or 10 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt < tries - 1:
                time.sleep(5 * (attempt + 1))
                continue
            raise


def search(params: dict) -> dict:
    return http(f"{API}/opportunity/search-result?{urllib.parse.urlencode(params)}")["data"]


def pull_listings() -> list[dict]:
    """Every open competition, hackathon and quiz. Hackathons are mostly inside competitions too."""
    found: dict[int, dict] = {}
    for kind in KINDS:
        page = 1
        while True:
            d = search({"opportunity": kind, "per_page": 100, "oppstatus": "open", "page": page})
            for r in d["data"]:
                found.setdefault(r["id"], r)
            if page >= d["last_page"]:
                break
            page += 1
            time.sleep(PAUSE)
        print(f"  {kind}: {d['total']} open; {len(found)} listings so far", file=sys.stderr)
        time.sleep(PAUSE)
    return list(found.values())


def trim(c: dict) -> dict:
    """The parts of a listing's own page that the ranking and the site use."""
    rr = c.get("regnRequirements") or {}
    rounds = []
    for r in sorted(c.get("rounds") or [], key=lambda r: r.get("round_order") or 0):
        for d in (r.get("details") if isinstance(r.get("details"), list) else [])[:1]:
            rounds.append({"title": (d.get("title") or "").strip(), "start": d.get("start_date") or "",
                           "end": d.get("end_date") or "", "what": text_of(d.get("display_text"))[:240]})
    return {
        "campuses": [{"id": o.get("id"), "name": o.get("name") or "", "type": o.get("eligibility_type", 1)}
                     for o in rr.get("organisations") or []],
        "gender": rr.get("gender") or [],
        "official_email": bool(rr.get("only_official_domains")),
        "eligibility": rr.get("eligibility") or "",
        "countries": c.get("eligible_countries") or [],
        "overall_prizes": text_of(c.get("overall_prizes"))[:400],
        "prizes": c.get("prizes") or [],
        "rounds": rounds,
        "body": text_of(c.get("details"))[:6000],
        "paid": bool(c.get("paid")),
    }


def details(listings: list[dict], cache: dict, offline: bool) -> None:
    """Read each listing's own page, unless the cached copy is as new as the listing."""
    todo = [r for r in listings if (cache.get(str(r["id"])) or {}).get("updated_at") != r.get("updated_at")
            and worth_reading(r)]
    if offline or not todo:
        return
    print(f"  reading {len(todo)} listing pages ({len(listings) - len(todo)} cached or skipped)", file=sys.stderr)
    for i, r in enumerate(todo, 1):
        try:
            c = http(f"{API}/competition/{r['id']}")["data"]["competition"]
            cache[str(r["id"])] = dict(trim(c), updated_at=r.get("updated_at"))
        except Exception as exc:  # one page failing costs that listing its details, not the run
            print(f"  details failed for {r['id']} ({type(exc).__name__}); ranked from the listing alone",
                  file=sys.stderr)
        if i % 50 == 0:
            print(f"  {i}/{len(todo)} pages read", file=sys.stderr)
            DETAILS.write_text(json.dumps(cache, separators=(",", ":"), ensure_ascii=False))
        time.sleep(PAUSE)


def worth_reading(r: dict) -> bool:
    """Skip the pages of listings already ruled out by the list itself: wrong batch, MBA-only, a dance-off."""
    if NOT_COMPETITION.search(r.get("title") or ""):
        return False
    return eligibility(r, {})["fit"] != "no"


# ---------------------------------------------------------------- judging one listing

def employer(org: str, title: str, prize_text: str, body: str) -> dict:
    """How well the company behind a listing pays an IIT graduate. A college event counts the
    best-paying company it says it is run with."""
    host = "college" if NOT_EMPLOYER.search(org) else "company"
    if COMMUNITY.search(org):  # a student-ambassador or developer-group event is not the company hiring
        return {"tier": 4, "label": "Student community", "host": "college", "sponsor": ""}
    hit = None if host == "college" else tier_of(org)
    if hit:
        return {"tier": hit[0], "label": hit[1], "host": host, "sponsor": ""}
    found = [h for h in map(tier_of, sponsors(title, prize_text, body)) if h]
    if found:
        tier, label, name = min(found, key=lambda h: h[0])
        return {"tier": tier, "label": label, "host": host, "sponsor": name}
    label = "College or student body" if host == "college" else "Small company or platform"
    return {"tier": 4, "label": label, "host": host, "sponsor": ""}


def offer_names(prize_text: str) -> list[str]:
    """'PPI with Yes Securities and a chance to network' -> Yes Securities."""
    names = (re.split(r"[.!?;,](?:\s|$)|\s+(?:and|for|as|to|in|on|after|subject)\b", raw)[0].strip(" .!,;")
             for raw in OFFER_FROM.findall(prize_text))
    return [n for n in names if n]


def sponsors(title: str, prize_text: str, body: str) -> list[str]:
    """Names the event itself joins to it: in the title, next to the offer, or after "sponsored by"."""
    out = offer_names(prize_text)
    if TITLE_JOIN.search(title):
        out += [p for p in TITLE_PARTS.split(title) if p and len(p.split()) <= 5]
    for m in BODY_JOIN.finditer(body):
        tail = re.split(r"[.;(]| at | for | to | is | are ", body[m.end():m.end() + 90])[0]
        out += [p for p in re.split(r",| and |&", tail) if p.strip() and len(p.split()) <= 5]
    return [p.strip() for p in out
            if not COMMUNITY.search(p) and not NOT_SPONSOR.search(p) and not NOT_EMPLOYER.search(p)]


def tier_of(text: str) -> tuple[int, str, str] | None:
    for g in GROUPS:
        m = g["re"].search(text or "")
        if m:
            return g["tier"], g["label"], m.group(0)
    return None


def channels(prizes: list[dict], prize_text: str, body: str) -> list[str]:
    """PPO, PPI or internship, from the prize flags, the prize lines, and the page's sentences about
    what winners and finalists get. Elsewhere on a page "internship opportunities" is often a pitch."""
    flag_i = any(p.get("pre_placement_internship") for p in prizes)
    flag_o = any(p.get("pre_placement_opportunity") for p in prizes)
    rewards = " ".join(s for s in re.split(r"(?<=[.!?])\s+|\s[•●▪]\s", body) if REWARD.search(s))
    text = f"{prize_text} {rewards}"
    out = []
    if PPO.search(text) or (flag_o and not INTERN.search(prize_text)):
        out.append("ppo")
    if PPI.search(text) or (flag_i and not INTERN.search(prize_text)):
        out.append("ppi")
    if INTERN.search(text) or ((flag_i or flag_o) and INTERN.search(prize_text)):
        out.append("intern")
    return out


def winners_in(rank: str) -> int:
    rank = rank or ""
    m = re.search(r"top\s*(\d+)", rank, re.I)
    if m:
        return min(int(m.group(1)), 1000)
    m = re.search(r"(\d+)\s*(?:-|to|–)\s*(\d+)", rank)
    if m and int(m.group(2)) > int(m.group(1)):
        return min(int(m.group(2)) - int(m.group(1)) + 1, 1000)
    return 1


def stated_pool(text: str) -> int:
    """'Prizes worth INR 20,00,000', 'Cash Prize Pool of INR 25 Lakhs': the largest amount named."""
    best = 0
    for m in AMOUNT.finditer(text or ""):
        num, unit = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        try:
            value = float(num.replace(",", ""))
        except ValueError:
            continue
        unit = (unit or "").lower()
        value *= 1e5 if unit.startswith(("lakh", "lac")) else 1e7 if unit.startswith(("crore", "cr")) else \
            1e3 if unit == "k" else 1
        best = max(best, int(value))
    return best


def prize(prizes: list[dict], overall: str) -> dict:
    inr = sum(p.get("cash") or 0 for p in prizes if (p.get("currency") or "fa-rupee") == "fa-rupee")
    usd = sum(p.get("cash") or 0 for p in prizes if p.get("currency") == "fa-dollar")
    stated = stated_pool(overall)
    ranks = [{"rank": (p.get("rank") or "").strip(), "cash": p.get("cash") or 0,
              "cur": "USD" if p.get("currency") == "fa-dollar" else "INR",
              "perk": text_of(p.get("others"))[:160]} for p in prizes]
    return {"inr": max(inr, stated), "usd": usd, "stated": stated, "ranks": ranks,
            "winners": sum(winners_in(p.get("rank")) for p in prizes)}


def money(inr: int, usd: int = 0) -> str:
    def rupees(n: int) -> str:
        if n >= 1e7:
            return f"₹{n / 1e7:.2g} crore"
        if n >= 1e5:
            return f"₹{n / 1e5:.3g} lakh"
        s = str(int(n))
        head, tail = s[:-3], s[-3:]
        head = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", head) if head else ""
        return "₹" + (f"{head},{tail}" if head else tail)
    bits = [rupees(inr)] if inr else []
    if usd:
        bits.append(f"${usd:,}")
    return " + ".join(bits)


def kind_of(r: dict) -> str:
    sub, title = r.get("subtype") or "", (r.get("title") or "").lower()
    if sub == "case_competition" or re.search(r"\bcase\b|case ?study", title):
        return "Case competition"
    if r.get("type") == "quizzes" or re.search(r"\bquiz", title):
        return "Quiz"
    if sub == "online_coding_challenge" or re.search(r"hack|\bcode|coding|programming", title):
        return "Hackathon or coding"
    if sub == "innovation_challenge" or re.search(r"ideathon|innovation|\bidea", title):
        return "Ideathon"
    if re.search(r"b-?plan|business plan|pitch|startup|venture", title):
        return "B-plan or pitch"
    if sub == "hiring_challenge":
        return "Hiring challenge"
    return "Other competition"


def join_years(years: list[int]) -> str:
    return ", ".join(map(str, years[:-1])) + (" and " if len(years) > 1 else "") + str(years[-1]) if years else ""


def eligibility(r: dict, det: dict) -> dict:
    """Can an IIT Bombay B.Tech graduating in 2027 enter, and which campuses may: yes, check or no, with why."""
    raw = det.get("eligibility") or (r.get("regnRequirements") or {}).get("eligibility") or "{}"
    try:
        el = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        el = {}
    el = el if isinstance(el, dict) else {}
    tags = {f.get("name") for f in r.get("filters") or [] if f.get("type") == "eligible"}
    no, check = [], []

    sector = [str(s).lower() for s in el.get("sector") or []]
    if sector and not {"students", "all"} & set(sector):
        no.append("For working professionals" if "professionals" in sector else "Not open to students")

    years = el.get("studentPassoutYearsSelected") or []
    if years and not any(str(y).lower() == "all" for y in years):
        ys = sorted({int(y) for y in years if str(y).isdigit()})
        if ys and YEAR not in ys:
            no.append(f"For the {join_years(ys)} batch{'es' if len(ys) > 1 else ''}")

    eng = el.get("engineering") or []
    rows = [x for x in eng if isinstance(x, dict)]
    mine = [x for x in rows if x.get("course") in MY_COURSES]
    if any(isinstance(x, str) and x.lower() in ("allcourses", "all") for x in eng):
        pass
    elif mine:
        fits_year = [x for x in mine if {"all", str(YEAR)} & {str(y).lower() for y in x.get("passoutYear") or ["all"]}]
        fits_branch = [x for x in fits_year if any(MY_BRANCH.search(str(s)) for s in x.get("specialization") or ["all"])]
        if not fits_year:
            no.append("B.Tech batches other than 2027")
        elif not fits_branch:
            specs = sorted({str(s) for x in fits_year for s in x.get("specialization") or []})
            no.append("Other branches only: " + ", ".join(specs[:3]) + ("…" if len(specs) > 3 else ""))
    elif rows and tags & {"All", "Undergraduate"}:
        check.append("B.Tech is not in its course list, though it names undergraduates")
    elif rows:
        no.append("Not open to B.Tech students")
    elif tags & {"All", "Engineering Students", "Undergraduate"}:
        pass
    elif not tags and {"all", "allcourses"} & {str(x).lower() for x in el.get("others") or []}:
        pass
    elif el.get("bSchools") and (not tags or tags <= {"Postgraduate", "Management"}):
        no.append("MBA and PGDM students only")
    elif tags:
        no.append("Open to " + ", ".join(sorted(t for t in tags if t)))
    else:
        check.append("Eligibility not stated")

    scope, n_campuses = "open", 0
    allowed = [c for c in det.get("campuses") or [] if c.get("type", 1) == 1]
    if allowed:
        n_campuses = len(allowed)
        if not any(c.get("id") in MY_IDS or (MY_NAME.search(c["name"]) and not NOT_MINE.search(c["name"]))
                   for c in allowed):
            no.append(f"Only {n_campuses} listed campus{'es' if n_campuses > 1 else ''}, and IIT Bombay is not one")
            scope = "not_mine"
        elif all(IIT_FAMILY.search(c["name"]) for c in allowed):
            scope = "iit_only"
        elif sum(bool(PREMIER.search(c["name"])) for c in allowed) >= 0.75 * n_campuses and n_campuses <= 25:
            scope = "premier"
        else:
            scope = "select"
    else:
        scope = campus_text(det.get("body") or "")
        if scope == "not_mine":
            no.append("The rules name the campuses allowed, and IIT Bombay is not one")

    gender = {str(g).upper() for g in det.get("gender") or []}
    women = bool(gender) and "F" in gender and not {"A", "M"} & gender
    if women:
        check.append("Women only")
    countries = json.dumps(det.get("countries") or [])
    if det.get("countries") and "India" not in countries and '"IN"' not in countries:
        no.append("Not open in India")

    fit = "no" if no else "check" if check else "yes"
    return {"fit": fit, "reasons": no + check, "scope": scope, "campuses_n": n_campuses,
            "campuses": [c["name"] for c in allowed][:40], "women_only": women,
            "who": (el.get("eligibilitySummery") or "").strip()[:300]}


def campus_text(body: str) -> str:
    """Who may enter, when the rules list campuses in words: iit_only, premier, not_mine or open."""
    m = CAMPUS_TEXT.search(body)
    if not m:
        return "open"
    seg = next(g for g in m.groups() if g)
    if seg.lower() == "iit students only":
        return "iit_only"
    others = OTHER_CAMPUSES.search(seg)
    iit_part = seg[:others.start()] if others else seg[:200]
    # "IITs: Bombay, Delhi, …" names the IITs allowed; a bare "IITs" means every one of them.
    named = IIT_CITIES.findall(iit_part.split(".")[0])
    if named and not any(MY_NAME.search(f"IIT {n}") for n in named):
        return "not_mine"
    return "premier" if others else "iit_only"


IIT_CITIES = re.compile(r"\b(Bombay|Delhi|Madras|Kanpur|Kharagpur|Roorkee|Guwahati|Hyderabad|Indore|Gandhinagar|Jodhpur|"
                        r"Patna|Ropar|Bhubaneswar|Mandi|Varanasi|BHU|Dhanbad|ISM|Tirupati|Palakkad|Bhilai|Goa|Jammu|Dharwad)\b")


def judge(r: dict, det: dict, now: datetime) -> dict:
    """One listing, everything the ranking and the site need."""
    org = (r.get("organisation") or {}).get("name") or ""
    prizes = det.get("prizes") or r.get("prizes") or []
    perks = " ".join(text_of(p.get("others")) for p in prizes)
    prize_text = f"{perks} {det.get('overall_prizes') or ''}"
    body = det.get("body") or text_of(r.get("details"))[:6000]
    rr = r.get("regnRequirements") or {}
    deadline, opened = when(rr.get("end_regn_dt")), when(rr.get("start_regn_dt"))
    p = prize(prizes, det.get("overall_prizes") or "")
    el = eligibility(r, det)
    addr = r.get("address_with_country_logo") or {}
    c = {
        "id": r["id"], "key": f"comp:unstop:{r['id']}", "title": (r.get("title") or "").strip(), "organiser": org,
        "url": r.get("seo_url") or f"https://unstop.com/{r.get('public_url') or ''}",
        "kind": kind_of(r), "mode": (r.get("region") or "").lower(),
        "city": "" if (r.get("region") or "") == "online" else (addr.get("city") or ""),
        "festival": ((r.get("festival") or {}).get("name") or ""),
        "opened": opened.isoformat() if opened else "", "deadline": deadline.isoformat() if deadline else "",
        "days_left": max(0, (deadline.astimezone(IST).date() - now.date()).days) if deadline else None,
        "team": [rr.get("min_team_size"), rr.get("max_team_size")],
        "prize_inr": p["inr"], "prize_usd": p["usd"], "prize": money(p["inr"], p["usd"]),
        "winners": p["winners"], "ranks": p["ranks"][:8],
        "channels": channels(prizes, prize_text, body),
        # Who makes the offer, when the prize lines say: "a PPI for an internship with Unstop" on a
        # LinkedIn contest is Unstop's offer, not LinkedIn's.
        "offer_with": next(iter(offer_names(prize_text)), "")[:40],
        "employer": employer(org, r.get("title") or "", prize_text, body),
        **el,
        "paid": bool(det.get("paid") or r.get("isPaid")),
        "official_email": det.get("official_email", False),
        "registered": r.get("registerCount") or 0, "views": r.get("viewsCount") or 0,
        "rounds": [{"title": x["title"], "start": x["start"], "end": x["end"], "what": x["what"][:160]}
                   for x in det.get("rounds") or []][:8],
        "summary": body[:700],
        "functions": [w.get("name") for w in r.get("workfunction") or [] if w.get("name")][:4],
        "details_read": bool(det),
    }
    c["relevant"] = relevant(c)
    rank(c)
    return c


def relevant(c: dict) -> bool:
    """A contest worth a place on the list: a case competition or anything with a hiring route, a company's
    challenge, a well-paid hackathon, or a business-minded event. Not dance-offs, workshops or debates."""
    if NOT_COMPETITION.search(c["title"]):
        return False
    if c["scope"] == "iit_only":
        return True
    if c["channels"] or c["kind"] in ("Case competition", "Hiring challenge", "Ideathon", "B-plan or pitch"):
        return True
    if c["employer"]["tier"] <= 3:
        return True
    if c["kind"] == "Hackathon or coding":
        return c["prize_inr"] + c["prize_usd"] * USD_INR >= 50_000
    return bool(BUSINESS.search(" ".join([c["title"], *c["functions"]])))


def rank(c: dict) -> None:
    """Band first (who may enter, then how well the employer pays), then points inside the band. Past
    the IIT-only band, an employer or a campus list counts only with a hiring route or a prize on a real
    contest: a LinkedIn profile contest is not a LinkedIn job."""
    tier, scope, hiring = c["employer"]["tier"], c["scope"], bool(c["channels"])
    pool = c["prize_inr"] + c["prize_usd"] * USD_INR
    offer = tier_of(c["offer_with"]) if c["offer_with"] else None
    # The offer is the employer's own (its name or brand), or from a company that pays as well.
    own = (not c["offer_with"] or c["offer_with"].lower() in c["organiser"].lower()
           or bool(offer and offer[0] <= tier))
    worth = (hiring and own) or (pool > 0 and c["kind"] in SUBSTANTIVE)
    if scope == "iit_only":
        band = 1
    elif tier == 1 and worth:
        band = 2
    elif (scope in ("premier", "select") and (hiring or pool)) or (tier == 2 and worth):
        band = 3
    elif tier <= 3:
        band = 4
    else:
        band = 5
    # A small organiser's "PPO opportunity" is worth less than a known employer's PPI.
    score = max([CHANNEL_POINTS[x] for x in c["channels"]], default=0) * (1 if tier < 4 and own else 0.35)
    score += min(15, 3 * math.log10(pool / 1000 + 1))
    score += {1: 12, 2: 8, 3: 4, 4: 0}[tier]
    score += {"premier": 6, "select": 3}.get(scope, 0)
    score += 6 if c["kind"] == "Case competition" else 2 if c["kind"] in SUBSTANTIVE else 0
    score -= 20 if c["fit"] == "check" else 0
    c["band"], c["band_label"], c["score"] = band, BANDS[band], round(score, 1)
    c["why"] = why(c)


def why(c: dict) -> str:
    """The ranking in a line: who may enter, the employer, the hiring route, the prize."""
    bits = []
    n, premier = c["campuses_n"], "premier " if c["scope"] == "premier" else ""
    if c["scope"] == "iit_only":
        bits.append(f"IIT students only ({n} campuses)" if n else "IIT students only")
    elif c["scope"] in ("premier", "select"):
        bits.append(f"{n} {premier}campuses, IIT Bombay included" if n else f"Only {premier}campuses, IIT Bombay included")
    else:
        bits.append("Open to all colleges")
    e = c["employer"]
    tiers = {1: "top pay for IIT grads", 2: "strong pay", 3: "pays an IITian less"}
    if e["tier"] < 4:
        who = f"{e['label']}" + (f" ({e['sponsor']}, which runs it with the organiser)" if e["sponsor"] else "")
        bits.append(f"{who}: {tiers[e['tier']]}")
    else:
        bits.append(e["label"])
    if c["channels"]:
        bits.append(" and ".join(CHANNEL_LABEL[x] for x in c["channels"]) + (f" (with {c['offer_with']})" if c["offer_with"] else ""))
    if c["prize"]:
        bits.append(f"{c['prize']} in prizes")
    return " · ".join(bits)


# ---------------------------------------------------------------- the watchlist

def editions(entry: dict, cache: dict, now: datetime, offline: bool, before: dict) -> list[dict]:
    """Every past edition of a watched competition that Unstop still lists, newest first."""
    u = entry["unstop"]
    if offline:
        return before.get(entry["id"], {}).get("editions", [])
    try:
        rows = search({"opportunity": "all", "per_page": 40, "page": 1, "searchTerm": u["search"]})["data"]
    except Exception as exc:
        print(f"  watchlist: {entry['name']} lookup failed ({type(exc).__name__}); kept the last answer", file=sys.stderr)
        return before.get(entry["id"], {}).get("editions", [])
    finally:
        time.sleep(PAUSE)
    org, title = re.compile(u["org"], re.I), re.compile(u.get("title") or ".", re.I)
    out = []
    for r in rows:
        if not (org.search((r.get("organisation") or {}).get("name") or "") and title.search(r.get("title") or "")):
            continue
        if NOT_COMPETITION.search(r.get("title") or ""):
            continue
        rr = r.get("regnRequirements") or {}
        start, end = when(rr.get("start_regn_dt")), when(rr.get("end_regn_dt"))
        el = eligibility(r, cache.get(str(r["id"])) or {})
        out.append({"id": r["id"], "title": r["title"].strip(), "url": r.get("seo_url") or "",
                    "start": start.isoformat() if start else "", "end": end.isoformat() if end else "",
                    "open": bool(end and end > now and (not start or start <= now)),
                    "fit": el["fit"], "reasons": el["reasons"]})
    out.sort(key=lambda e: e["start"], reverse=True)
    return out[:8]


def watch(now: datetime, cache: dict, offline: bool, by_id: dict) -> list[dict]:
    spec = json.loads(WATCHLIST.read_text())
    before = {w["id"]: w for w in load(WATCH_OUT, {}).get("entries", [])}
    grad = datetime.strptime(PROF["graduates_by"], "%Y-%m").replace(tzinfo=IST)
    out = []
    for e in spec["entries"]:
        w = {k: e.get(k, "") for k in ("id", "name", "employer", "scope", "leads_to", "how", "url", "last", "next",
                                        "next_month", "for_2027", "for_2027_note", "sources")}
        w["checked"] = "" if e.get("unstop") and not e.get("last") else spec.get("checked", "")
        hit = tier_of(e.get("employer") or "")
        w["tier"] = e.get("tier") or (hit[0] if hit else 4)
        w["open_now"] = []
        if e.get("unstop"):
            eds = editions(e, cache, now, offline, before)
            w["editions"] = eds
            w["open_now"] = [{"title": x["title"], "url": x["url"], "end": x["end"], "fit": x["fit"],
                              "listed": x["id"] in by_id} for x in eds if x["open"]]
            past = [x for x in eds if not x["open"] and x["start"]]
            if eds and not e.get("last"):
                latest = past[0] if past else eds[0]
                same = [x for x in eds if x["start"][:7] == latest["start"][:7]]
                w["last"] = (f"{latest['title']}{f' (+{len(same) - 1} tracks)' if len(same) > 1 else ''}: "
                             f"registration {short_day(when(latest['start']))} – {short_day(when(latest['end']))}")
                if not w["url"]:
                    w["url"] = latest["url"]
            if eds and not e.get("next_month"):
                latest = past[0] if past else None
                if w["open_now"]:
                    w["next"] = "Open now"
                elif latest:
                    nxt = when(latest["start"]) + timedelta(days=365)
                    while nxt < now - timedelta(days=30):  # an edition skipped a year or two
                        nxt += timedelta(days=365)
                    w["next_month"] = f"{nxt:%Y-%m}"
                    w["next"] = f"Expect around {nxt:%B %Y}, a year after the last"
            if eds and not e.get("for_2027"):
                if w["open_now"]:
                    fits = [x["fit"] for x in w["open_now"]]
                    w["for_2027"] = "yes" if "yes" in fits else "check" if "check" in fits else "no"
                    w["for_2027_note"] = "; ".join(sorted({r for x in eds if x["open"] for r in x["reasons"]}))[:200]
                else:
                    last = [x for x in eds if x["start"][:4] == (past[0]["start"][:4] if past else "")]
                    took = any(x["fit"] != "no" for x in last)
                    nxt = when(w["next_month"] + "-01T00:00:00+05:30") if w["next_month"] else None
                    after = bool(nxt and nxt > grad)
                    w["for_2027"] = "no" if after else "check"
                    w["for_2027_note"] = (("The last edition took the 2027 batch; " if took else
                                           "The last edition was not open to an IIT Bombay 2027 B.Tech; ")
                                          + ("the next comes after the final semester" if after else
                                             "check the batch when the next one opens"))
            elif not eds and not e.get("last"):
                w["last"] = "No edition found on Unstop"
        nxt = w.get("next_month") or ""
        w["before_graduation"] = bool(nxt and nxt <= PROF["graduates_by"])
        out.append(w)
    order = {"yes": 0, "check": 1, "no": 2}
    scope_rank = {"iit_only": 0, "premier": 1}
    # Ones Prathmesh can enter first, open ones first among those; ones not open to Prathmesh last.
    out.sort(key=lambda w: (w["for_2027"] == "no", not w["open_now"], order.get(w["for_2027"], 1),
                            scope_rank.get(w["scope"], 2), w["tier"], w.get("next_month") or "9999"))
    return out


# ---------------------------------------------------------------- history and output

def track(rows: list[dict], today: str, previous_open: int) -> None:
    """First and last day each listing was open. A pull that came back far smaller than the last one
    means Unstop failed, not that listings closed, so nothing is marked closed then."""
    seen = load(SEEN, {})
    current = {str(c["id"]) for c in rows}
    for c in rows:
        s = seen.setdefault(str(c["id"]), {"first_seen": today})
        s.update(last_seen=today, title=c["title"], organiser=c["organiser"], deadline=c["deadline"][:10])
        s.pop("closed", None)
        c["first_seen"] = s["first_seen"]
    if len(current) >= 0.6 * previous_open:
        for k, s in seen.items():
            if k not in current and "closed" not in s:
                s["closed"] = today
    else:
        print(f"  NOT marking listings closed: {len(current)} open now against {previous_open} last time",
              file=sys.stderr)
    SEEN.write_text(json.dumps(dict(sorted(seen.items())), ensure_ascii=False, indent=0) + "\n")


CSV_COLUMNS = ["rank", "band", "priority", "title", "organiser", "employer", "type", "who_may_enter", "fit",
               "why_not", "hiring_route", "prize_pool", "winners", "team", "deadline_ist", "days_left", "mode",
               "city", "registered", "first_seen", "url", "why_ranked"]


SCOPE_LABEL = {"iit_only": "IIT students only", "premier": "Premier campuses incl. IIT Bombay",
               "select": "Select campuses incl. IIT Bombay", "not_mine": "Listed campuses, not IIT Bombay",
               "open": "Open to all"}


def team_text(team: list) -> str:
    lo, hi = team
    return f"{lo}–{hi}" if lo and hi and lo != hi else str(lo or hi or "")


def write_csv(rows: list[dict]) -> None:
    with OUT_CSV.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(CSV_COLUMNS)
        for c in rows:
            dl = when(c["deadline"])
            ranked = bool(c.get("rank"))
            w.writerow([c.get("rank") or "", c["band"] if ranked else "", c["band_label"] if ranked else "",
                        c["title"], c["organiser"], f"Tier {c['employer']['tier']}: {c['employer']['label']}",
                        c["kind"], SCOPE_LABEL[c["scope"]], c["fit"], "; ".join(c["reasons"]),
                        ", ".join(CHANNEL_LABEL[x] for x in c["channels"]), c["prize"], c["winners"],
                        team_text(c["team"]), f"{dl.astimezone(IST):%Y-%m-%d %H:%M}" if dl else "",
                        c["days_left"], c["mode"], c["city"], c["registered"], c.get("first_seen", ""), c["url"],
                        c["why"]])


def main() -> None:
    offline = "--offline" in sys.argv
    DATA.mkdir(exist_ok=True)
    now = datetime.now(IST)
    cache = load(DETAILS, {})
    previous = load(OUT_JSON, {})
    if offline:
        listings = load(LISTINGS, [])
        if not listings:
            raise SystemExit("Nothing saved to re-rank; run without --offline first.")
    else:
        listings = pull_listings()
        if not listings:
            raise SystemExit("Unstop returned no open listings; kept the last pull.")
        LISTINGS.write_text(json.dumps(listings, separators=(",", ":"), ensure_ascii=False))
    details(listings, cache, offline)
    DETAILS.write_text(json.dumps(cache, separators=(",", ":"), ensure_ascii=False))

    rows = []
    for r in listings:
        deadline = when((r.get("regnRequirements") or {}).get("end_regn_dt"))
        if deadline and deadline < now:
            continue  # registration shut since the listing was pulled
        rows.append(judge(r, cache.get(str(r["id"])) or {}, now))
    track(rows, f"{now:%Y-%m-%d}", previous.get("counts", {}).get("open", 0))

    ranked = sorted((c for c in rows if c["relevant"] and c["fit"] != "no"),
                    key=lambda c: (c["band"], -c["score"], c["deadline"] or "9999"))
    for i, c in enumerate(ranked, 1):
        c["rank"] = i
    rest = sorted((c for c in rows if not c.get("rank")), key=lambda c: (not c["relevant"], c["deadline"] or "9999"))
    by_id = {c["id"]: c for c in ranked}
    watched = watch(now, cache, offline, by_id)
    counts = {"open": len(rows), "ranked": len(ranked), "not_eligible": sum(c["fit"] == "no" for c in rows),
              "not_relevant": sum(not c["relevant"] for c in rows),
              "by_band": {BANDS[b]: sum(c["band"] == b for c in ranked) for b in BANDS},
              "with_hiring_route": sum(bool(c["channels"]) for c in ranked),
              "closing_7_days": sum(c["days_left"] is not None and c["days_left"] <= 7 for c in ranked)}
    out = {"generated": now.isoformat(timespec="seconds"), "source": "unstop.com public API",
           "profile": {k: PROF[k] for k in ("name", "institute", "degree", "branch", "minor", "passout_year")},
           "bands": BANDS, "counts": counts, "competitions": ranked + rest}
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    WATCH_OUT.write_text(json.dumps({"generated": out["generated"], "entries": watched}, ensure_ascii=False, indent=1) + "\n")
    write_csv(ranked + rest)

    print(f"{len(rows)} open listings on Unstop: {len(ranked)} ranked for {PROF['name']}, "
          f"{counts['not_eligible']} not open to an {PROF['institute']} {PROF['passout_year']} {PROF['degree']}, "
          f"{counts['not_relevant']} not competitions with a hiring route or a business case", file=sys.stderr)
    for label, n in counts["by_band"].items():
        print(f"  {n:4}  {label}", file=sys.stderr)
    for c in ranked[:12]:
        print(f"  #{c['rank']:<3} {c['band_label'][:22]:22} {c['title'][:52]:52} | {c['organiser'][:26]:26} | "
              f"closes {short_day(when(c['deadline']))}", file=sys.stderr)


if __name__ == "__main__":
    main()
