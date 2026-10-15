"""Live roles in Japan that a new graduate with English and no Japanese can take.

Pulls every board in Japan/boards.json, keeps the postings in Japan that read
as entry level, reads each description for what it says about Japanese, and
writes data/roles.json, data/roles.csv, data/programs.csv and index.html.

Language is read, not guessed, and lands in one of four buckets:
  english_ok         the posting says Japanese is not required, or English OR
                     Japanese will do
  japanese_plus      Japanese appears only under preferred / nice to have
  unstated           an English description that never asks for Japanese
  japanese_required  a Japanese level is asked for, or the description is
                     written in Japanese only
The sentence that decided it is kept as `evidence`, so a wrong call is visible.

Field shapes, beyond the three fetch_jobs.py already handles:
  Workable  - use the widget endpoint (one GET, descriptions included); the
              v3 search endpoint pages ten at a time and 429s an IP for a day
  Workday   - 20 per page at most; the description is a second call per job
  Amazon    - search.json filters by `normalized_country_code[]`; plain
              `country` is ignored; posted_date is "October  7, 2026"
  Lever     - `country` is an ISO code, which catches "Remote" Japan roles

  python Japan/fetch_japan.py              # boards, then rebuild the page
  python Japan/fetch_japan.py --search     # also LinkedIn and Indeed, Tokyo
  python Japan/fetch_japan.py --wide       # wider search: every function, all of Japan
  python Japan/fetch_japan.py --visa       # search for roles that sponsor visas or need no Japanese
  python Japan/fetch_japan.py --rotate     # the daily run: one of the three searches above, in turn
  python Japan/fetch_japan.py --reclassify # re-read saved descriptions, no requests
  python Japan/fetch_japan.py --render     # rebuild the page from saved data
"""

from __future__ import annotations

import csv
import html
import json
import random
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
BOARDS = HERE / "boards.json"
PROGRAMS = HERE / "programs.json"
TEMPLATE = HERE / "page.template.html"
INDEX = HERE / "index.html"
ROLES_JSON = DATA / "roles.json"
ROLES_CSV = DATA / "roles.csv"
PROGRAMS_CSV = DATA / "programs.csv"
SOURCES_JSON = DATA / "sources.json"
SEEN = DATA / "seen.json"
SEARCH_RAW = DATA / "search_raw.json"       # LinkedIn and Indeed rows with descriptions; gitignored
BOARDS_RAW = DATA / "boards_raw.json"       # every board's Japan rows with descriptions; gitignored
SEARCH_META = DATA / "search_meta.json"
INDIA_LIST = HERE / "india_presence.json"   # companies known to employ people in India, checked by hand
GETRO_INDIA_SEEN = DATA / "getro_india.json"  # the last answer for each VC-board company; gitignored

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# ---------------------------------------------------------------- filters

JAPAN = re.compile(
    r"\b(japan|tokyo|osaka|kyoto|yokohama|fukuoka|nagoya|sapporo|sendai|kobe|"
    r"kawasaki|okazaki|tsukuba|minato|shibuya|shinagawa|roppongi|osaki)\b|"
    r"日本|東京|大阪|福岡|京都|横浜|名古屋|札幌",
    re.I,
)

# Where a company is hiring in India now. A company with open roles in India employs Indians,
# which is what the "Indians work here" mark on the team site says.
INDIA = re.compile(r"\bindia\b|bengaluru|bangalore|hyderabad|\bpune\b|chennai|mumbai|gurugram|gurgaon|noida|"
                   r"new delhi|\bdelhi\b|kolkata|ahmedabad|kochi|coimbatore|jaipur|chandigarh|mohali|"
                   r"thiruvananthapuram|trivandrum|indore|vadodara|mysuru|mysore|nagpur|bhubaneswar|"
                   r"visakhapatnam|lucknow", re.I)
CITY = {"bangalore": "Bengaluru", "gurgaon": "Gurugram", "trivandrum": "Thiruvananthapuram", "mysore": "Mysuru",
        "new delhi": "Delhi"}


def india_summary(locations: list[str]) -> dict | None:
    """{count, places} for the locations in India, the three most common cities first."""
    cities, n = Counter(), 0
    for loc in locations:
        found = [m.group(0).lower() for m in INDIA.finditer(loc or "")]
        if not found:
            continue
        n += 1
        city = next((f for f in found if f != "india"), "india")
        cities[CITY.get(city, "India" if city == "india" else city.title())] += 1
    if not n:
        return None
    named = [c for c, _ in cities.most_common() if c != "India"] or ["India"]
    return {"count": n, "places": named[:3]}


def _searched(locations: list[str], total: int) -> dict | None:
    """A keyword search for "India" also finds jobs that only mention it; trust its total only
    when nearly all of the first page sits in India."""
    s = india_summary(locations)
    if not s:
        return None
    if s["count"] >= 0.8 * len(locations):
        return dict(s, count=max(total, s["count"]))
    return dict(s, more=total > len(locations))


# A title that says outright it is for students or new graduates.
ENTRY_STRONG = re.compile(
    r"intern\b|internship|インターン|new[- ]grad|\bgraduate|新卒|\d\d卒|第二新卒|第2卒|"
    r"class of 20\d\d|university|campus|early[- ]career|trainee|apprentice|academy|fresher",
    re.I,
)
# A title that is often, not always, entry level.
ENTRY_WEAK = re.compile(r"\bjunior\b|\bjr\.?\b|entry[- ]level|\bassociate\b|\banalyst\b", re.I)
HARD_SENIOR = re.compile(
    r"senior|\bsr\.?\b|principal|\bstaff\b|\blead\b|director|head of|\bvp\b|"
    r"vice president|\bchief\b|experienced|faculty|professor|lecturer|シニア|リード|責任者|部長",
    re.I,
)
SENIOR = re.compile(
    HARD_SENIOR.pattern + r"|manager|architect|specialist|expert|\bii\b|\biii\b|マネージャー|課長",
    re.I,
)
# Recruiters for the new-grad team match ENTRY_STRONG and are not entry level.
RECRUITER = re.compile(r"recruit|talent acquisition|採用", re.I)


def entry_level(title: str) -> bool:
    if RECRUITER.search(title):
        return False
    if ENTRY_STRONG.search(title):
        return not HARD_SENIOR.search(title)
    if ENTRY_WEAK.search(title):
        return not SENIOR.search(title)
    return False


TRACKS = [
    ("data-ai", re.compile(r"\bdata\b|machine learning|\bml\b|\bai\b|research|scientist|"
                           r"analytics|llm|computer vision|\bvision\b|データ|機械学習|研究", re.I)),
    ("engineering", re.compile(r"engineer|developer|software|\bsre\b|devops|security|"
                               r"front[- ]?end|back[- ]?end|full[- ]?stack|mobile|エンジニア|開発", re.I)),
    ("product", re.compile(r"product|\bpm\b|プロダクト", re.I)),
    ("business", re.compile(r"analyst|business|consult|strategy|operations|sales|marketing|"
                            r"finance|treasury|investment|associate|trainee|legal|ビジネス|営業|"
                            r"コンサル|アナリスト|アソシエイト", re.I)),
]


def track(title: str) -> str:
    for name, pattern in TRACKS:
        if pattern.search(title):
            return name
    return "other"


# ---------------------------------------------------------------- language

JA = r"(?:japanese|日本語)"

# Japanese is explicitly not needed, or English will do instead.
EN_OK = [
    # "Japanese is not required", "Japanese is a plus but not required"; never across a "required".
    re.compile(r"japanese\b(?:(?!required|必須)[^.。]){0,40}?\bnot\W{1,3}(?:required|necessary|"
               r"needed|mandatory|a requirement)", re.I),
    re.compile(r"\bno\W+japanese(?:\W+language)?(?:\W+skills?|\W+ability)?\W+(?:is\W+|are\W+)?"
               r"(?:required|necessary|needed)", re.I),
    re.compile(r"(?:without|don'?t need|do not need|no need for)\W+(?:any\W+)?japanese", re.I),
    re.compile(r"japanese\s*[:：]\s*not\s+required", re.I),
    re.compile(r"(?:fluen\w*|proficien\w*|skills?|level|business|independent|language)\W"
               r"[^.。]{0,40}?(?:english\W+or\W+japanese|japanese\W+or\W+english)", re.I),
    re.compile(r"(?:english\W+or\W+japanese|japanese\W+or\W+english)\s*[:：(（]", re.I),
    re.compile(r"english\W+(?:work\W+|working\W+|business\W+)?(?:proficiency|fluency)\W*,?\W*or\W+japanese", re.I),
    re.compile(r"日本語(?:力|能力|スキル)?(?:は)?(?:不問|不要|必須ではありません|必要ありません)"),
]

# A Japanese level is stated. Whether it is required is decided afterwards.
JA_LEVEL = [
    re.compile(r"(?:native|fluent|business|conversational|advanced|intermediate|high)"
               r"[- ]?(?:level)?\W{0,3}(?:of\W+|in\W+)?(?:written\W+and\W+spoken\W+|spoken\W+)?japanese", re.I),
    re.compile(r"japanese\W{0,3}(?:language\W{0,3})?(?:skills?|ability|abilities|proficiency|fluency|"
               r"level|communication)?\W{0,4}(?:native|fluent|business|conversational|n[1-5]\b|"
               r"jlpt|cefr|c1\b|c2\b|b2\b)", re.I),
    re.compile(r"(?:proficien\w*|fluen\w*)[^.。]{0,40}?\bjapanese", re.I),
    re.compile(r"requires?\W+(?:\w+\W+){0,3}?japanese|japanese\W+(?:is\W+)?(?:required|a must|"
               r"mandatory|essential)", re.I),
    re.compile(r"\bjlpt\W{0,3}n?[1-5]\b", re.I),
    re.compile(r"日本語(?:能力|力)?\s*[:：]?\s*(?:ネイティブ|ビジネス|日常会話|N[1-5]|流暢)"),
    re.compile(r"(?:ネイティブ|ビジネス|日常会話)\s*(?:レベル)?の?日本語"),
    re.compile(r"日本語[^。]{0,20}(?:必須|できる方)"),
]

# Benign mentions: "Japanese Social Insurance", "Japanese resumes are acceptable".
JA_BENIGN = re.compile(r"japanese\W+(?:social|national|holidays?|resumes?|cv|version|culture|"
                       r"lessons?|classes|company|companies|market|law)", re.I)

# "Japanese is a must" beats a "Preferred" heading further up; "at least N2" beats a
# heading but not a "plus" in the same sentence.
REQ_STRONG = re.compile(r"\bmust\b|\brequired\b|\brequires?\b|mandatory|essential|必須", re.I)
REQ_WEAK = re.compile(r"at least|minimum|or (?:above|higher)", re.I)
REQ_NEGATED = re.compile(r"not\W+(?:required|essential|mandatory|a must)|without", re.I)
# A "Languages" section is its own section, not part of the preferred list above it.
LANG_HEAD = re.compile(r"\*\*languages?\*\*|【language|\blanguages?\s*[:：.]|\blanguage\s+(?:requirements?|"
                       r"skills?|proficiency)\b|語学", re.I)
OTHER_LANG_PLUS = re.compile(r"other\W+(?:languages?\W+)?(?:is\W+|are\W+)?(?:of\W+|an\W+|a\W+)?"
                             r"(?:advantage|plus|bonus|preferred|welcome)\w*", re.I)
PREF_CUE = re.compile(r"\bplus\b|bonus|nice[- ]to[- ]have|preferred|advantage|desirable|"
                      r"welcome|beneficial|helpful|optional|歓迎|尚可|あれば", re.I)
REQ_HEAD = re.compile(r"minimum qualifications|basic qualifications|required qualifications|"
                      r"requirements|required skills|must[- ]haves?|what you(?:'ll)? need|"
                      r"qualifications|応募資格|必須(?:要件|条件|スキル)|必要な(?:スキル|経験)", re.I)
PREF_HEAD = re.compile(r"preferred qualifications|preferred|nice[- ]to[- ]haves?|bonus points|"
                       r"good to have|desirable|歓迎(?:要件|条件|スキル)|尚可", re.I)


def clean(text: str) -> str:
    text = html.unescape(html.unescape(text or ""))
    text = re.sub(r"<(?:br|/p|/li|/h\d|/div)[^>]*>", ". ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return re.sub(r"(?:\.\s+){2,}", ". ", text).strip()


def snippet(text: str, start: int, end: int, pad: int = 90) -> str:
    s, e = max(0, start - pad), min(len(text), end + pad)
    out = ("…" if s else "") + text[s:e].strip() + ("…" if e < len(text) else "")
    # For display only: drop markdown bold and escapes that LinkedIn descriptions carry.
    out = re.sub(r"\*\*|\\(?=[-~|*_#.()\[\]])", "", out)
    return re.sub(r"\.{2,}", ".", out)


# Sentence and bullet breaks. LinkedIn descriptions are markdown bullets (" * "), and
# without them "Preferred" from the next heading leaks into the sentence.
BREAK = re.compile(r"[.。・•■◆]|\s[*\-–]\s")


def sentence(text: str, start: int, end: int) -> str:
    left = max([m.end() for m in BREAK.finditer(text, max(0, start - 160), start)] or [max(0, start - 160)])
    right = BREAK.search(text, end, end + 160)
    return text[left:right.start() if right else end + 160]


def under_preferred_heading(text: str, pos: int) -> bool:
    window = text[max(0, pos - 2000):pos]
    last = lambda pattern: max([m.end() for m in pattern.finditer(window)] or [-1])
    pref = last(PREF_HEAD)
    return pref > -1 and pref > max(last(REQ_HEAD), last(LANG_HEAD))


def language(text: str) -> tuple[str, str]:
    """Return (bucket, evidence)."""
    if not text:
        return "unstated", ""
    for pattern in EN_OK:
        m = pattern.search(text)
        if m:
            return "english_ok", snippet(text, m.start(), m.end())

    plus = None
    for pattern in JA_LEVEL:
        for m in pattern.finditer(text):
            if JA_BENIGN.match(text, m.start()) or JA_BENIGN.search(text[m.start():m.end() + 12]):
                continue
            # "English & Japanese, other languages an advantage": the plus is about the others.
            around = OTHER_LANG_PLUS.sub(" ", sentence(text, m.start(), m.end()))
            found = snippet(text, m.start(), m.end())
            if REQ_STRONG.search(around) and not REQ_NEGATED.search(around):
                return "japanese_required", found
            if PREF_CUE.search(around):
                plus = plus or found
                continue
            if not REQ_WEAK.search(around) and under_preferred_heading(text, m.start()):
                plus = plus or found
                continue
            return "japanese_required", found
    if plus:
        return "japanese_plus", plus

    # Written only in Japanese: the reader is expected to speak it.
    english_words = len(re.findall(r"\b[A-Za-z]{3,}\b", text))
    japanese_chars = len(re.findall(r"[぀-ヿ一-鿿]", text))
    if japanese_chars > 200 and english_words < 120:
        return "japanese_required", "Description is written in Japanese only."
    return "unstated", ""


RESIDENCY = re.compile(
    r"(?:currently|already)\W+(?:reside|residing|live|living|based|located)\W+in\W+japan|"
    r"must\W+(?:currently\W+)?(?:reside|live|be\W+based|be\W+located)\W+in\W+japan|"
    r"日本(?:国内)?在住(?:の方|者)?(?:のみ|限定)", re.I)
# Sponsorship stated outright. A company that hires you from India must sponsor the work visa
# anyway; what matters is whether it says it will, or says it will not.
VISA_YES = re.compile(
    r"visa\W+(?:sponsorship|support|assistance|arrangement)s?\W+(?:is\W+|are\W+|will\W+be\W+)?(?:available|provided|offered|included)|"
    r"(?:provide|offer|offers|provides|with|including|full)\W+(?:full\W+)?(?:work\W+)?visa\W+(?:sponsorship|support|assistance)|"
    r"(?:we|will|can|able\W+to)\W+sponsor\W+(?:your\W+|a\W+|the\W+)?(?:work\W+)?visa|"
    r"sponsors?\W+visas|visa\W+sponsorship\W+for\W+eligible|"
    r"\bvisa\W+(?:sponsorship|support)\b(?![^.。]{0,25}\bnot\b)|"
    r"ビザ(?:サポート|取得支援|スポンサー|の?サポート|取得の?サポート)(?:あり|有り|可|します|いたします)?|就労ビザ(?:の)?(?:取得)?(?:支援|サポート)", re.I)
VISA_NO = re.compile(
    r"(?:no|not|unable\W+to|cannot|can'?t|do\W+not|does\W+not|will\W+not)\W+(?:be\W+able\W+to\W+)?(?:provide|offer|sponsor|support)\W+"
    r"(?:any\W+)?(?:work\W+)?(?:visa|immigration)|visa\W+sponsorship\W+(?:is\W+)?not\W+(?:available|provided|offered|possible)|"
    r"(?:must|should)\W+(?:already\W+)?(?:have|hold|possess)\W+(?:a\W+|the\W+|valid\W+|an\W+)*(?:existing\W+)?"
    r"(?:right|authori[sz]ation|eligibility|permission|visa|status)\W+(?:to\W+work\W+)?(?:in\W+japan)?|"
    r"(?:existing|valid|current)\W+(?:right|authori[sz]ation)\W+to\W+work\W+in\W+japan|"
    r"without\W+(?:visa\W+)?sponsorship|ビザ(?:サポート|支援|スポンサー)(?:は)?(?:ありません|不可|なし|対象外)|"
    r"日本での就労(?:資格|ビザ)を(?:お持ち|有する)|就労可能な(?:在留資格|ビザ)をお持ちの方", re.I)


def visa(text: str) -> tuple[str, str]:
    """("yes" | "no" | "", evidence). "no" also covers "must already be able to work in Japan"."""
    m = VISA_NO.search(text)
    if m:
        return "no", snippet(text, m.start(), m.end(), 80)
    m = VISA_YES.search(text)
    if m:
        return "yes", snippet(text, m.start(), m.end(), 80)
    return "", ""


# ---------------------------------------------------------------- experience

sys.path.insert(0, str(HERE.parent / "scripts"))
from enrich import min_years as _min_years_en  # noqa: E402  the India tracker's extractor

JP_YEARS = re.compile(r"(?:経験|実務経験|業務経験)[^。]{0,20}?(\d{1,2})\s*年以上|(\d{1,2})\s*年以上の(?:実務|業務)?経験")
LEVEL_TITLE = [
    ("intern", re.compile(r"intern\b|internship|インターン|working student|co-?op", re.I)),
    ("new_grad", re.compile(r"new\W*grad|\bgraduate\b|新卒|\d\d卒|class of 20\d\d|university|campus|"
                            r"early\W*career|trainee|apprentice|academy|fresher", re.I)),
    ("senior", re.compile(r"senior|\bsr\.?\b|principal|\bstaff\b|\blead\b|director|head of|\bvp\b|vice president|"
                          r"\bchief\b|architect|manager|expert|シニア|リード|マネージャー|責任者|部長|課長", re.I)),
    ("entry", re.compile(r"\bjunior\b|\bjr\.?\b|entry[- ]level|\bassociate\b|\bassistant\b|\banalyst\b|第二新卒", re.I)),
]


def min_years(text: str) -> int | None:
    found = [y for y in (_min_years_en(text),) if y is not None]
    for m in JP_YEARS.finditer(text):
        found.append(int(m.group(1) or m.group(2)))
    found = [y for y in found if y <= 20]
    return min(found) if found else None


def level(title: str, years: int | None) -> str:
    """intern, new_grad, entry (open to someone with no or one year), mid, senior."""
    for name, pattern in LEVEL_TITLE:
        if pattern.search(title):
            if name == "entry" and years is not None and years >= 2:
                return "mid"
            return name
    if years is None:
        return "unstated"
    return "entry" if years <= 1 else "mid" if years <= 4 else "senior"


BATCH = re.compile(
    r"class of (20\d\d)|(20\d\d)\W+(?:new\W+)?grad(?:uate)?s?\b|\b(\d\d)卒|"
    r"graduat\w*[^.。]{0,50}?(20\d\d)|join\w*[^.。]{0,40}?(?:april|october)\W+(20\d\d)|"
    r"(20\d\d)年(?:4|10)月", re.I)


def batch_years(text: str) -> str:
    years = set()
    for m in BATCH.finditer(text):
        for g in m.groups():
            if g:
                y = int(g) + (2000 if len(g) == 2 else 0)
                if 2025 <= y <= 2030:
                    years.add(y)
    return ", ".join(str(y) for y in sorted(years))


# ---------------------------------------------------------------- graduation window

# An IIT B.Tech finishes between May and July 2027. A posting fits when the graduation
# window it names covers that, or when it joins after it. Japanese classes count by
# fiscal year: 28卒 graduates April 2027 to March 2028, so it includes an IIT 2027
# graduate; 27卒 ends in March 2027 and does not. Labels lie; dates decide.
IIT_EARLIEST, IIT_DONE = (2027, 5), (2027, 7)
MONTHS = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
DATE = re.compile(
    r"(?:\d{1,2}(?:st|nd|rd|th)?\W{1,2})?(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
    r"\W{1,3}(?:\d{1,2}(?:st|nd|rd|th)?,?\W{1,2})?(20\d\d)"
    r"|(20\d\d)\s*年\s*(\d{1,2})\s*月"
    r"|(20\d\d)[/.](\d{1,2})\b", re.I)
# Segments for dates; not "・", which Japanese also uses inside 大学・大学院.
SEGMENT = re.compile(r"。|\.\s|\s[*\-–•]\s|[■◆●]")
GRAD_CTX = re.compile(r"graduat|卒業|修了|class of|cohort|intake|join|入社|start(?:ing)?\W+(?:date|in|on|work)|"
                      r"commenc|onboard|new grad|新卒|degree|学士|取得見込|見込み", re.I)
# "Graduating from a university in Japan" shuts out an IIT degree; "overseas or in Japan" does not.
JAPAN_UNI_ONLY = re.compile(r"universit(?:y|ies)\W+in\W+japan|japanese\W+universit|日本の(?:四年制)?大学|"
                            r"日本国内の大学|国内の(?:四年制)?大学", re.I)
OVERSEAS_OK = re.compile(r"overseas|abroad|outside\W+(?:of\W+)?japan|international\W+universit|国内外|海外", re.I)
POSTGRAD_ONLY = re.compile(r"master'?s?\W+(?:or|/|and)\W+(?:ph\.?d|doctoral)|(?:ph\.?d|doctoral)\W+(?:or|/)\W+master|"
                           r"修士(?:もしくは|または|・|/|、)?博士|博士(?:もしくは|または|・|/|、)?修士", re.I)
BACHELOR_OK = re.compile(r"bachelor|undergraduate|\bbs\b|\bba\b|学士|学部", re.I)
DEADLINE_CTX = re.compile(r"deadline|締切|締め切り|apply by|applications? (?:close|open|will)", re.I)
JOIN_CTX = re.compile(r"join|入社|start(?:ing)?\W+(?:date|in|on|work)|commenc|onboard|begin", re.I)
BY_BEFORE = re.compile(r"\b(?:by|before|no later than|prior to|until|up to)\W*(?:the\W+)?(?:end\W+of\W+)?$", re.I)
BY_AFTER = re.compile(r"^\s*(?:末)?\s*(?:まで|迄)")
RANGE_BETWEEN = re.compile(r"^\W*(?:[～〜~\-–—]|to|and|until|through|から)\W*$", re.I)

YES_LABEL = re.compile(r"class of 2027|\b2027\W+(?:new\W+)?grad(?:uate)?s?\b|graduat\w*\W+(?:in\W+)?2027\b|"
                       r"\b2027\W+(?:start|intake|entry|joiners?)\b|new\W+grad(?:uate)?s?\W+2027", re.I)
LIKELY_LABEL = re.compile(r"28卒|2028年卒|28年(?:度)?(?:新)?卒|28新卒|卒業年度不問")
NO_LABEL = re.compile(r"(?<!\d)27卒|2027年卒|(?<!\d)27年(?:度)?(?:新)?卒")
# "Expected to graduate in 2028" without a month: after an IIT 2027 degree, so no.
GRAD_YEAR = re.compile(r"graduat\w*\W+(?:in\W+|by\W+)?(?:the\W+year\W+)?(20\d\d)\b(\W+or\W+(?:later|after)|\W+onwards)?", re.I)
# Recruiting asks earlier graduates to get in touch rather than apply: worth a check, not a yes.
CONTACT_US = re.compile(r"ご連絡ください|お問い合わせください|please\W+(?:contact|reach out|email)", re.I)
CHECK_LABEL = re.compile(r"class of 2028|\b2028\W+(?:new\W+)?grad(?:uate)?s?\b", re.I)
MBA = re.compile(r"\bmba\b", re.I)
SUMMER = re.compile(r"summer\W+(?:intern|analyst|associate|program|internship)", re.I)
NEWGRAD = re.compile(r"新卒|new\W+grad|graduate\W+(?:program|programme|scheme|analyst|trainee)|"
                     r"early\W+career|university\W+graduate", re.I)
RANK = {"yes": 3, "likely": 2, "no": 1}


def dates(seg: str) -> list[tuple[int, int, tuple[int, int]]]:
    out = []
    for m in DATE.finditer(seg):
        if m.group(1):
            ym = (int(m.group(2)), MONTHS[m.group(1).lower()[:3]])
        elif m.group(3):
            ym = (int(m.group(3)), int(m.group(4)))
        else:
            ym = (int(m.group(5)), int(m.group(6)))
        if 2024 <= ym[0] <= 2030 and 1 <= ym[1] <= 12:
            out.append((m.start(), m.end(), ym))
    return out


def dated_verdicts(text: str) -> list[tuple[str, str]]:
    """(verdict, segment) for every graduation or joining sentence that carries a date."""
    found = []
    for seg in SEGMENT.split(text):
        if not GRAD_CTX.search(seg) or DEADLINE_CTX.search(seg):
            continue
        ds = dates(seg)
        if not ds:
            continue
        verdict, at = None, (ds[0][0], ds[0][1])
        # A window: "between December 2026 and July 2027", "2027年4月～2028年3月".
        if len(ds) >= 2 and RANGE_BETWEEN.match(seg[ds[0][1]:ds[1][0]]):
            start, end = ds[0][2], ds[1][2]
            verdict = "yes" if start <= IIT_DONE and end >= IIT_EARLIEST else "no"
            at = (ds[0][0], ds[1][1])
        else:
            for s, e, ym in ds:
                if BY_BEFORE.search(seg[max(0, s - 30):s]) or BY_AFTER.match(seg[e:e + 6]):
                    v = "yes" if ym >= IIT_DONE else "likely" if ym >= IIT_EARLIEST else "no"
                elif JOIN_CTX.search(seg):
                    v = "yes" if ym >= (2027, 8) else "likely" if ym >= (2027, 6) else "no"
                else:
                    v = "yes" if IIT_EARLIEST <= ym <= (2027, 12) else "no"
                if verdict is None or RANK[v] > RANK[verdict]:
                    verdict, at = v, (s, e)
        found.append((verdict, snippet(seg, at[0], at[1], 110).strip()))
    return found


DAY_DATE = re.compile(r"(\d{1,2})(?:st|nd|rd|th)?\W{1,2}(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\W{1,3}(20\d\d)"
                      r"|(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\W{1,3}(\d{1,2})(?:st|nd|rd|th)?,?\W{1,2}(20\d\d)"
                      r"|(20\d\d)\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", re.I)


def deadline(text: str) -> str:
    """The application deadline the posting states, as YYYY-MM-DD, or ""."""
    for seg in SEGMENT.split(text):
        if not DEADLINE_CTX.search(seg):
            continue
        m = DAY_DATE.search(seg)
        if not m:
            continue
        g = m.groups()
        if g[0]:
            y, mo, d = int(g[2]), MONTHS[g[1].lower()[:3]], int(g[0])
        elif g[3]:
            y, mo, d = int(g[5]), MONTHS[g[3].lower()[:3]], int(g[4])
        else:
            y, mo, d = int(g[6]), int(g[7]), int(g[8])
        if 2026 <= y <= 2028 and 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y:04d}-{mo:02d}-{d:02d}"
    return ""


def grad_2027(title: str, text: str) -> tuple[str, str]:
    """Whether someone finishing an IIT degree in mid-2027 can take it: yes, likely,
    no, check (a new-grad role with no dates), or none (no batch named)."""
    if MBA.search(title):
        return "no", "An MBA program."
    verdict, why = _window(title, text)
    if verdict in ("yes", "likely"):
        for m in JAPAN_UNI_ONLY.finditer(text):
            if not OVERSEAS_OK.search(sentence(text, m.start(), m.end())):
                return "no", "Only for graduates of universities in Japan. " + snippet(text, m.start(), m.end(), 90)
        if POSTGRAD_ONLY.search(why) and not BACHELOR_OK.search(why):
            return "no", "Needs a master's or PhD. " + why
        if CONTACT_US.search(why):
            return "check", "Asks earlier graduates to contact recruiting. " + why
    return verdict, why


def _window(title: str, text: str) -> tuple[str, str]:
    dated = dated_verdicts(text)
    if dated:
        best = max(dated, key=lambda d: RANK[d[0]])
        return best[0], best[1][:240]
    blob = f"{title} {text}"
    years = [(int(m.group(1)), bool(m.group(2)), m) for m in GRAD_YEAR.finditer(text) if 2024 <= int(m.group(1)) <= 2030]
    if years:
        fits = [m for y, later, m in years if y == 2027 or (later and y <= 2027)]
        m = (fits or [years[0][2]])[0]
        return ("likely" if fits else "no"), snippet(text, m.start(), m.end(), 80)
    # A label alone is weaker than dates: "2027 graduates" means by March 2027 to a Japanese firm.
    for pattern, verdict in ((YES_LABEL, "likely"), (LIKELY_LABEL, "likely"), (NO_LABEL, "no"), (CHECK_LABEL, "check")):
        m = pattern.search(blob)
        if m:
            return verdict, snippet(blob, m.start(), m.end(), 70)
    if SUMMER.search(title):
        return "no", "A summer internship, for students who graduate later."
    if NEWGRAD.search(re.sub(r"第二新卒|第2新卒|既卒", "", blob)):
        return "check", ""
    return "none", ""


# ---------------------------------------------------------------- fetching

def http(url: str, body: dict | None = None, tries: int = 4):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"User-Agent": UA, "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            wait = int(exc.headers.get("Retry-After") or 0) if exc.headers else 0
            if exc.code == 429 and wait <= 60 and attempt < tries - 1:
                time.sleep(max(wait, 12 * (attempt + 1)))
                continue
            if exc.code == 429 and wait > 60:
                raise RuntimeError(f"rate-limited; the site asks to wait {wait // 3600}h {wait % 3600 // 60}m") from exc
            raise


def details(url: str) -> dict:
    """One job's details. A failure here costs that job's description, not the board."""
    try:
        return http(url) or {}
    except Exception as exc:
        print(f"  details failed, kept without description: {url[:90]} ({type(exc).__name__})", file=sys.stderr)
        return {}


def iso(value) -> str:
    if not value:
        return ""
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, timezone.utc).date().isoformat()
    return str(value)[:10]


def row(board: dict, **kw) -> dict:
    base = {"ats": board["ats"], "slug": board["slug"], "company": board["company"],
            "id": "", "title": "", "location": "", "url": "", "posted": "", "text": "",
            "in_japan": False}
    base.update(kw)
    base["in_japan"] = bool(board.get("japan_only") or kw.get("in_japan")
                            or JAPAN.search(base["location"] or ""))
    return base


def pull_greenhouse(b: dict) -> list[dict]:
    jobs = http(f"https://boards-api.greenhouse.io/v1/boards/{b['slug']}/jobs?content=true")["jobs"]
    return [row(b, id=str(j["id"]), title=j.get("title") or "",
                location=(j.get("location") or {}).get("name") or "",
                url=j.get("absolute_url") or "",
                posted=iso(j.get("first_published") or j.get("updated_at")),
                text=clean(j.get("content"))) for j in jobs]


def pull_lever(b: dict) -> list[dict]:
    out = []
    for j in http(f"https://api.lever.co/v0/postings/{b['slug']}?mode=json"):
        cats = j.get("categories") or {}
        lists = " ".join(f"{l.get('text', '')}. {clean(l.get('content'))}" for l in j.get("lists") or [])
        text = clean(f"{j.get('descriptionPlain', '')} {lists} {j.get('additionalPlain', '')}")
        out.append(row(b, id=j["id"], title=j.get("text") or "",
                       location=cats.get("location") or "", url=j.get("hostedUrl") or "",
                       posted=iso(j.get("createdAt")), text=text,
                       in_japan=(j.get("country") or "").upper() == "JP"))
    return out


def pull_ashby(b: dict) -> list[dict]:
    out = []
    for j in http(f"https://api.ashbyhq.com/posting-api/job-board/{b['slug']}")["jobs"]:
        if not j.get("isListed", True):
            continue
        locs = [j.get("location") or ""] + [s.get("location") or "" for s in j.get("secondaryLocations") or []]
        country = (((j.get("address") or {}).get("postalAddress") or {}).get("addressCountry") or "")
        out.append(row(b, id=j["id"], title=j.get("title") or "", location=" / ".join(l for l in locs if l),
                       url=j.get("jobUrl") or "", posted=iso(j.get("publishedAt")),
                       text=clean(j.get("descriptionHtml") or j.get("descriptionPlain")),
                       in_japan=bool(JAPAN.search(country))))
    return out


def pull_workable(b: dict) -> list[dict]:
    # The widget endpoint returns every job with its description in one GET. The
    # v3 search endpoint pages ten at a time and rate-limits an IP for a day.
    slug = b["slug"]
    out = []
    for j in http(f"https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true").get("jobs") or []:
        codes = {(l.get("countryCode") or "").upper() for l in j.get("locations") or []}
        out.append(row(b, id=j["shortcode"], title=j.get("title") or "",
                       location=", ".join(x for x in (j.get("city"), j.get("country")) if x),
                       url=f"https://apply.workable.com/{slug}/j/{j['shortcode']}/",
                       posted=iso(j.get("published_on")), text=clean(j.get("description")),
                       in_japan="JP" in codes or j.get("country") == "Japan"))
    return out


GRAD_TITLE = re.compile(r"20(?:27|28)|graduate|新卒|\d\d卒|intern|trainee|junior|entry|analyst|associate", re.I)


def pull_workday(b: dict) -> list[dict]:
    host, tenant, site = b["slug"].split("/")
    base = f"https://{host}/wday/cxs/{tenant}/{site}"
    listed: dict[str, dict] = {}
    # Big employers are searched for Japan and Tokyo; a Japan-only site is read whole.
    for term in b.get("search") or [""]:
        offset = 0
        while True:
            page = http(f"{base}/jobs", {"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": term})
            for j in page.get("jobPostings") or []:
                listed.setdefault(j.get("externalPath", ""), j)
            offset += 20
            if offset >= (page.get("total") or 0) or offset >= 1000:
                break
    out = []
    for path, j in listed.items():
        where = j.get("locationsText") or ""
        r = row(b, id=path, title=j.get("title") or "", location=where, url=f"https://{host}/{site}{path}")
        unsure = bool(re.search(r"\d+ locations", where, re.I))
        if r["in_japan"] or unsure:
            info = details(f"{base}{path}").get("jobPostingInfo") or {}
            r["text"] = clean(info.get("jobDescription"))
            r["posted"] = iso(info.get("startDate"))
            r["url"] = info.get("externalUrl") or r["url"]
            if unsure:
                r["location"] = info.get("location") or where
                r["in_japan"] = bool(b.get("japan_only") or JAPAN.search(r["location"]))
        out.append(r)
    return out


def pull_smartrecruiters(b: dict) -> list[dict]:
    out, offset = [], 0
    while True:
        page = http(f"https://api.smartrecruiters.com/v1/companies/{b['slug']}/postings?country=jp&limit=100&offset={offset}")
        for j in page.get("content") or []:
            loc = j.get("location") or {}
            r = row(b, id=j["id"], title=j.get("name") or "",
                    location=", ".join(x for x in (loc.get("city"), loc.get("country")) if x),
                    url=f"https://jobs.smartrecruiters.com/{b['slug']}/{j['id']}",
                    posted=iso(j.get("releasedDate")), in_japan=(loc.get("country") or "").lower() == "jp")
            if True:
                ad = (details(j["ref"]).get("jobAd") or {}).get("sections") or {}
                r["text"] = clean(" ".join((ad.get(k) or {}).get("text") or "" for k in
                                           ("jobDescription", "qualifications", "additionalInformation")))
            out.append(r)
        offset += 100
        if offset >= (page.get("totalFound") or 0):
            break
    return out


def pull_oracle(b: dict) -> list[dict]:
    """Oracle Recruiting Cloud (JPMorgan): keyword search, then details per likely role."""
    host, site = b["slug"].split("/")
    api = f"https://{host}/hcmRestApi/resources/latest"
    listed: dict[str, dict] = {}
    for term in b.get("search") or ["Japan"]:
        offset = 0
        while True:
            url = (f"{api}/recruitingCEJobRequisitions?onlyData=true&expand=requisitionList.secondaryLocations"
                   f"&finder=findReqs;siteNumber={site},limit=50,offset={offset},keyword=%22{term}%22,"
                   f"sortBy=POSTING_DATES_DESC")
            items = (http(url).get("items") or [{}])[0]
            reqs = items.get("requisitionList") or []
            for j in reqs:
                listed.setdefault(str(j.get("Id")), j)
            offset += 50
            if not reqs or offset >= (items.get("TotalJobsCount") or 0):
                break
    out = []
    for jid, j in listed.items():
        r = row(b, id=jid, title=j.get("Title") or "", location=j.get("PrimaryLocation") or "",
                url=f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{jid}",
                posted=iso(j.get("PostedDate")))
        if r["in_japan"]:
            d = details(f"{api}/recruitingCEJobRequisitionDetails?expand=all&onlyData=true"
                     f"&finder=ById;Id=%22{jid}%22,siteNumber={site}")
            info = (d.get("items") or [{}])[0]
            r["text"] = clean(" ".join(info.get(k) or "" for k in
                                       ("ExternalDescriptionStr", "ExternalQualificationsStr", "ExternalResponsibilitiesStr")))
        out.append(r)
    return out


def pull_amazon(b: dict) -> list[dict]:
    out, offset = [], 0
    while True:
        page = http("https://www.amazon.jobs/en/search.json?normalized_country_code%5B%5D="
                    f"{b['slug']}&result_limit=100&offset={offset}&sort=recent")
        jobs = page.get("jobs") or []
        for j in jobs:
            try:
                posted = datetime.strptime(" ".join((j.get("posted_date") or "").split()), "%B %d, %Y").date().isoformat()
            except ValueError:
                posted = ""
            text = clean(" ".join(j.get(k) or "" for k in
                                  ("description", "basic_qualifications", "preferred_qualifications")))
            out.append(row(b, id=str(j.get("id_icims") or j.get("id")), title=j.get("title") or "",
                           location=j.get("normalized_location") or j.get("city") or "",
                           url="https://www.amazon.jobs" + (j.get("job_path") or ""), posted=posted, text=text))
        offset += 100
        if not jobs or offset >= (page.get("hits") or 0):
            break
    return out


def pull_pcsx(b: dict) -> list[dict]:
    """Eightfold's careers API (Microsoft): slug is "<host>/<domain>"."""
    host, domain = b["slug"].split("/", 1)
    api = f"https://{host}/api/pcsx"
    out, start = [], 0
    while True:
        data = http(f"{api}/search?domain={domain}&query=&location=Japan&start={start}&num=10").get("data") or {}
        positions = data.get("positions") or []
        for j in positions:
            places = " / ".join(j.get("locations") or [])
            r = row(b, id=str(j["id"]), title=j.get("name") or "", location=places,
                    url=f"https://{host}{j.get('positionUrl') or ''}",
                    posted=iso((j.get("postedTs") or 0) * 1000),
                    in_japan="JP" in " ".join(j.get("standardizedLocations") or []))
            if r["in_japan"]:
                d = details(f"{api}/position_details?position_id={j['id']}&domain={domain}&hl=en").get("data") or {}
                r["text"] = clean(d.get("jobDescription"))
            out.append(r)
        start += 10
        if not positions or start >= (data.get("count") or 0):
            break
    return out


def pull_google(b: dict) -> list[dict]:
    """Google careers: the results page embeds 20 jobs (with descriptions) in AF_initDataCallback ds:1."""
    out, page, total = [], 1, None
    while total is None or (page - 1) * 20 < total:
        url = f"https://www.google.com/about/careers/applications/jobs/results/?location=Japan&page={page}"
        doc = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=40).read().decode("utf-8", "replace")
        blocks = dict(re.findall(r"AF_initDataCallback\(\{key: '(ds:\d+)'.*?data:(.*?), sideChannel", doc, re.S))
        data = json.loads(blocks["ds:1"])
        total = data[2] if len(data) > 2 and isinstance(data[2], int) else 0
        for j in data[0] or []:
            places = [p[0] for p in (j[9] or []) if p]
            html_parts = " ".join(x[1] for x in (j[3], j[4], j[10], j[19]) if isinstance(x, list) and len(x) > 1 and x[1])
            out.append(row(b, id=str(j[0]), title=j[1] or "", location=" / ".join(places),
                           url=f"https://www.google.com/about/careers/applications/jobs/results/{j[0]}",
                           posted=iso((j[12] or [0])[0] * 1000) if j[12] else "", text=clean(html_parts),
                           in_japan=any("Japan" in p for p in places)))
        page += 1
        time.sleep(1.5)
        if not data[0]:
            break
    return out


# Japan Dev renders 60 jobs per page; each category page renders its own 60. The union of
# the category pages recovers most of the board. The data is Nuxt's devalue payload.
JAPANDEV_PAGES = """/jobs /jobs-in-japan-for-english-speakers /japan-jobs-relocation /remote-jobs-in-japan
/partial-remote-jobs-in-japan /ai-jobs-in-japan /ml-jobs-in-japan /backend-jobs-in-japan /front-end-jobs-in-japan
/full-stack-jobs-in-japan /devops-jobs-in-japan /sre-jobs-in-japan /security-jobs-in-japan /qa-jobs-in-japan
/design-jobs-in-japan /manager-jobs-in-japan /ios-jobs-in-japan /go-jobs-in-japan /java-jobs-in-japan
/javascript-jobs-in-japan /kotlin-jobs-in-japan /php-jobs-in-japan /python-jobs-in-japan /rails-jobs-in-japan
/react-jobs-in-japan /ruby-jobs-in-japan /rust-jobs-in-japan /swift-jobs-in-japan /vue-jobs-in-japan
/typescript-jobs-in-japan /scala-jobs-in-japan /flutter-jobs-in-japan /aws-jobs-in-japan""".split()


def _nuxt(html_text: str):
    m = re.search(r'<script type="application/json"[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', html_text, re.S)
    arr, memo = json.loads(m.group(1)), {}

    def r(i):
        if not isinstance(i, int) or i < 0:
            return None if i == -1 else i
        if i in memo:
            return memo[i]
        v = arr[i]
        if isinstance(v, list) and v and isinstance(v[0], str) and v[0] in (
                "ShallowReactive", "Reactive", "Ref", "ShallowRef", "EmptyRef", "EmptyShallowRef"):
            out = r(v[1]) if len(v) > 1 else None
        elif isinstance(v, list) and v and isinstance(v[0], str) and v[0] in ("Set", "Map", "Date"):
            out = v[1] if v[0] == "Date" else v[1:]
        elif isinstance(v, list):
            out = memo[i] = []
            out.extend(r(x) for x in v)
            return out
        elif isinstance(v, dict):
            out = memo[i] = {}
            for k, x in v.items():
                out[k] = r(x)
            return out
        else:
            out = v
        memo[i] = out
        return out
    return r(0)


def pull_japandev(b: dict) -> list[dict]:
    hits: dict[str, dict] = {}
    for page in JAPANDEV_PAGES:
        req = urllib.request.Request("https://japan-dev.com" + page, headers={"User-Agent": UA})
        try:
            doc = _nuxt(urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "replace"))["data"]
        except Exception:
            continue
        for key in [k for k in doc if k.startswith("algolia-state")]:
            for h in doc[key]["Job_production"]["results"][0]["hits"]:
                hits[str(h["id"])] = h
        time.sleep(1.5)
    out = []
    for h in hits.values():
        company = (h.get("company") or {}).get("slug") or ""
        text = " ".join(str(h.get(k) or "") for k in ("intro", "details", "requirements", "benefits"))
        out.append(row(b, id=str(h["id"]), title=h.get("title") or "", company=h.get("company_name") or "",
                       location=h.get("location") or "Japan", in_japan=True,
                       url=f"https://japan-dev.com/jobs/{company}/{h.get('slug')}",
                       posted=iso(h.get("published_at") or h.get("created_at")), text=clean(text),
                       jd={k: h.get(k) for k in ("japanese_level", "japanese_level_enum", "sponsors_visas",
                                                 "candidate_location", "seniority_level", "is_internship")},
                       via="Japan Dev"))
    return out


GETRO_INDIA: dict[int, dict | None] = {}  # a company can sit in several networks; ask once a run
UNKNOWN = "unknown"  # an India check that failed twice: keep the last answer rather than drop the mark


def _last_getro() -> dict:
    return json.loads(GETRO_INDIA_SEEN.read_text()) if GETRO_INDIA_SEEN.exists() else {}


def getro_search(network: str, host: str, body: dict) -> dict:
    req = urllib.request.Request(f"https://api.getro.com/api/v2/collections/{network}/search/jobs",
                                 data=json.dumps(body).encode(),
                                 headers={"User-Agent": UA, "Content-Type": "application/json",
                                          "Accept": "application/json", "Origin": f"https://{host}",
                                          "Referer": f"https://{host}/"})
    return json.loads(urllib.request.urlopen(req, timeout=40).read().decode())["results"]


def pull_getro(b: dict) -> list[dict]:
    """A VC portfolio job board on Getro; slug is "<network id>/<board host>"."""
    network, host = b["slug"].split("/", 1)
    out, page = [], 0
    while True:
        body = {"hitsPerPage": 100, "page": page, "filters": {"searchable_locations": ["Japan"]}, "query": ""}
        res = getro_search(network, host, body)
        for j in res.get("jobs") or []:
            places = j.get("locations") or []
            out.append(row(b, id=str(j["id"]), title=j.get("title") or "",
                           company=(j.get("organization") or {}).get("name") or b["company"],
                           location=" / ".join(places), in_japan=True, url=j.get("url") or "",
                           posted=iso((j.get("created_at") or 0) * 1000), getro_level=j.get("seniority") or "",
                           via=f"{b['company']} portfolio", org_id=(j.get("organization") or {}).get("id")))
        page += 1
        # Getro caps a page at 20 whatever hitsPerPage says, so count what came back.
        if not res.get("jobs") or len(out) >= (res.get("count") or 0):
            break
        time.sleep(1)
    # The network spans hundreds of companies; ask about India for each one that hires in Japan.
    last = _last_getro()
    for oid in {r["org_id"] for r in out if r.get("org_id")}:
        if oid not in GETRO_INDIA:
            for attempt in range(2):
                try:
                    res = getro_search(network, host, {"hitsPerPage": 20, "page": 0, "query": "", "filters": {
                        "searchable_locations": ["India"], "organization.id": [oid]}})
                    s = india_summary([" / ".join(j.get("locations") or []) for j in res.get("jobs") or []])
                    GETRO_INDIA[oid] = s and dict(s, count=max(res.get("count") or 0, s["count"]))
                    break
                except Exception:
                    time.sleep(3)
            time.sleep(0.3)
        answer = GETRO_INDIA[oid] if oid in GETRO_INDIA else last.get(str(oid))  # failed twice: last answer
        for r in out:
            if r.get("org_id") == oid and answer:
                r["india"] = answer
    return out


PULL = {"greenhouse": pull_greenhouse, "lever": pull_lever, "ashby": pull_ashby,
        "workable": pull_workable, "workday": pull_workday, "amazon": pull_amazon,
        "smartrecruiters": pull_smartrecruiters, "oracle": pull_oracle,
        "japandev": pull_japandev, "getro": pull_getro, "pcsx": pull_pcsx, "google": pull_google}


def india_check(b: dict, rows: list[dict]) -> dict | None:
    """The company's open jobs in India, or None. Boards that list every job show it in their
    own rows; the ones read for Japan only are asked once more, for India."""
    ats = b["ats"]
    if ats in ("greenhouse", "lever", "ashby", "workable"):
        return india_summary([r["location"] for r in rows if not r["in_japan"]])
    if ats == "workday":
        host, tenant, site = b["slug"].split("/")
        page = http(f"https://{host}/wday/cxs/{tenant}/{site}/jobs",
                    {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": "India"})
        return _searched([j.get("locationsText") or "" for j in page.get("jobPostings") or []], page.get("total") or 0)
    if ats == "oracle":
        host, site = b["slug"].split("/")
        items = (http(f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true"
                      f"&finder=findReqs;siteNumber={site},limit=25,offset=0,keyword=%22India%22,"
                      f"sortBy=POSTING_DATES_DESC").get("items") or [{}])[0]
        return _searched([j.get("PrimaryLocation") or "" for j in items.get("requisitionList") or []],
                         items.get("TotalJobsCount") or 0)
    if ats == "amazon":
        page = http("https://www.amazon.jobs/en/search.json?normalized_country_code%5B%5D=IND&result_limit=20&offset=0")
        s = india_summary([j.get("normalized_location") or j.get("city") or "" for j in page.get("jobs") or []])
        return s and dict(s, count=max(page.get("hits") or 0, s["count"]))
    if ats == "smartrecruiters":
        page = http(f"https://api.smartrecruiters.com/v1/companies/{b['slug']}/postings?country=in&limit=20")
        s = india_summary([f"{(j.get('location') or {}).get('city') or ''}, India" for j in page.get("content") or []])
        return s and dict(s, count=max(page.get("totalFound") or 0, s["count"]))
    if ats == "pcsx":
        host, domain = b["slug"].split("/", 1)
        data = http(f"https://{host}/api/pcsx/search?domain={domain}&query=&location=India&start=0&num=10").get("data") or {}
        s = india_summary([" / ".join(j.get("locations") or []) for j in data.get("positions") or []])
        return s and dict(s, count=max(data.get("count") or 0, s["count"]))
    if ats == "google":
        url = "https://www.google.com/about/careers/applications/jobs/results/?location=India&page=1"
        doc = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=40).read().decode("utf-8", "replace")
        blocks = dict(re.findall(r"AF_initDataCallback\(\{key: '(ds:\d+)'.*?data:(.*?), sideChannel", doc, re.S))
        data = json.loads(blocks["ds:1"])
        s = india_summary([" / ".join(p[0] for p in (j[9] or []) if p) for j in data[0] or []])
        total = data[2] if len(data) > 2 and isinstance(data[2], int) else 0
        return s and dict(s, count=max(total, s["count"]))
    return None  # Japan Dev and Getro: per company, elsewhere


def pull(board: dict) -> tuple[dict, list[dict], str, dict | None]:
    try:
        rows = PULL[board["ats"]](board)
    except Exception as exc:
        return board, [], f"{type(exc).__name__}: {exc}", UNKNOWN
    india = UNKNOWN
    for attempt in range(2):
        try:
            india = india_check(board, rows)
            break
        except Exception:
            time.sleep(5)
    return board, rows, "", india


def pull_all(boards: list[dict]) -> list[tuple[dict, list[dict], str]]:
    with ThreadPoolExecutor(max_workers=6) as pool:
        return list(pool.map(pull, boards))


def merge_locations(rows: list[dict]) -> list[dict]:
    """Amazon posts one role once per city. Keep one row, list the cities."""
    kept: dict[tuple, dict] = {}
    for r in rows:
        k = (r["company"], norm(r["title"]), r["language"])
        if k not in kept:
            kept[k] = r
            continue
        first = kept[k]
        places = [p for p in first["location"].split(" / ") if p]
        if r["location"] and r["location"] not in places:
            first["location"] = " / ".join(places + [r["location"]])
    return list(kept.values())


PRIMARY = {"greenhouse", "lever", "ashby", "workable", "workday", "smartrecruiters", "oracle", "amazon"}
SOURCE_RANK = {"japandev": 1, "linkedin": 2, "indeed": 3, "getro": 4}


def merge_sources(rows: list[dict]) -> list[dict]:
    """One row per role. A company's own board wins over Japan Dev, which wins over LinkedIn,
    Indeed and VC boards; the winner inherits visa and language facts the others state."""
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        groups.setdefault((norm(r["title"]), norm(r["company"])[:5]), []).append(r)
    out = []
    for group in groups.values():
        group.sort(key=lambda r: 0 if r["source"] in PRIMARY else SOURCE_RANK.get(r["source"], 5))
        best = dict(group[0])
        for other in group[1:]:
            if not best["visa"] and other["visa"]:
                best["visa"], best["visa_evidence"] = other["visa"], other["visa_evidence"]
            if best["language"] == "unstated" and other["language"] != "unstated":
                best["language"], best["evidence"] = other["language"], other["evidence"]
            best["residency"] = best["residency"] or other["residency"]
            best["india"] = best.get("india") or other.get("india")
            if other.get("via") and other["via"] not in best.get("via", ""):
                best["via"] = ", ".join(x for x in (best.get("via"), other["via"]) if x)
        out.append(best)
    return out


CORP = re.compile(r"株式会社|有限会社|合同会社|㈱|\b(?:co|corp|corporation|inc|ltd|llc|kk|k\.k|gk|limited|plc|ag|"
                  r"gmbh|japan|group|holdings?)\b\.?", re.I)


def company_key(name: str) -> str:
    return norm(CORP.sub(" ", name or ""))


def indians_work_here(rows: list[dict]) -> None:
    """LinkedIn, Indeed and Japan Dev rows name a company without its board: take the answer
    from the same company's board, else from the list checked by hand."""
    known = {company_key(r["company"]): r["india"] for r in rows if r.get("india")}
    if INDIA_LIST.exists():
        for c in json.loads(INDIA_LIST.read_text())["companies"]:
            for name in [c["name"]] + c.get("aliases", []):
                known.setdefault(company_key(name), {"note": c["why"], "source": c["source"]})
    for r in rows:
        if not r.get("india"):
            r["india"] = known.get(company_key(r["company"]))


def wanted(r: dict) -> bool:
    """Every role in Japan is kept and labelled; the page filters. Only empty titles go."""
    return bool((r.get("title") or "").strip())


JD_LANG = {"japanese_level_not_required": "english_ok", "japanese_level_conversational": "japanese_required",
           "japanese_level_business_level": "japanese_required", "japanese_level_fluent": "japanese_required"}
JD_LEVEL = {"seniority_level_new_grad": "new_grad", "seniority_level_junior": "entry",
            "seniority_level_mid_level": "mid", "seniority_level_senior": "senior"}
GETRO_LEVEL = {"internship": "intern", "entry_level": "entry", "associate": "entry", "mid_senior": "mid",
               "senior": "senior", "director": "senior", "vice_president": "senior", "cxo": "senior"}


def classify(r: dict) -> dict:
    text = r.get("text") or ""
    lang, evidence = language(text)
    fit, eligibility = grad_2027(r["title"], text)
    v, v_evidence = visa(text)
    years = min_years(text)
    lvl = level(r["title"], years)
    residency = bool(RESIDENCY.search(text))
    jd = r.get("jd")
    if jd:  # Japan Dev states these outright
        if jd.get("japanese_level_enum") in JD_LANG:
            lang = JD_LANG[jd["japanese_level_enum"]]
            evidence = f"Japan Dev: Japanese {jd.get('japanese_level') or ''}".strip()
        if jd.get("sponsors_visas") == "sponsors_visas_yes":
            v, v_evidence = "yes", "Japan Dev: the company sponsors visas"
        elif jd.get("sponsors_visas") == "sponsors_visas_no" and v != "yes":
            v, v_evidence = "no", "Japan Dev: no visa sponsorship"
        residency = residency or jd.get("candidate_location") == "candidate_location_japan_only"
        lvl = "intern" if jd.get("is_internship") else JD_LEVEL.get(jd.get("seniority_level"), lvl)
    if r.get("getro_level"):
        lvl = GETRO_LEVEL.get(r["getro_level"], lvl)
    entry = lvl in ("intern", "new_grad", "entry") or fit in ("yes", "likely", "check")
    return {
        "key": f"{r['ats']}:{r['slug']}:{r['id']}",
        "source": r["ats"], "company": r["company"], "title": r["title"],
        "location": r["location"], "url": r["url"], "posted": r["posted"],
        "track": track(r["title"]), "language": lang, "evidence": evidence,
        "residency": residency, "visa": v, "visa_evidence": v_evidence,
        "level": lvl, "min_years": years, "entry": entry,
        "batch": batch_years(r["title"] + " " + text),
        "grad_2027": fit, "eligibility": eligibility, "deadline": deadline(text),
        "via": r.get("via") or "", "india": r.get("india"),
    }


# ---------------------------------------------------------------- search

QUERIES = ["new graduate", "graduate program", "internship", "junior software engineer",
           "data analyst", "business analyst"]
# --visa: all of Japan, aimed at roles that say they sponsor visas or need no Japanese.
VISA_QUERIES = ["visa sponsorship", "English speaking", "Japanese not required", "relocation support",
                "no Japanese required", "international team English"]
INDEED_VISA = ["visa sponsorship", "ビザサポート", "English speaking", "外国籍 歓迎 英語"]
# --wide: every function, all of Japan, aimed at people graduating in 2027.
WIDE_QUERIES = ["2027 graduate", "new graduate 2027", "graduate analyst", "graduate engineer",
                "graduate trainee", "entry level", "junior", "new grad", "28卒", "新卒 英語"]
INDEED_WIDE = ["new graduate", "graduate program", "28卒 英語", "新卒 英語 ビザ"]
KEEP_DAYS = 21  # search rows not seen again for this long are dropped
SEARCH_MODES = ["tokyo", "wide", "visa"]
SEARCH_SITES = ["linkedin", "indeed"]
COOLDOWN_HOURS = 4
PAUSE = 6
BLOCKED_AFTER = 2


def search_rows(force: bool, mode: str = "tokyo") -> list[dict]:
    wide = mode in ("wide", "visa")
    meta = json.loads(SEARCH_META.read_text()) if SEARCH_META.exists() else {}
    # Raw rows with their descriptions, so a better classifier applies without searching again.
    cached = json.loads(SEARCH_RAW.read_text()) if SEARCH_RAW.exists() else []
    if meta.get("searched_at") and not force:
        allowed = datetime.fromisoformat(meta["searched_at"]) + timedelta(hours=COOLDOWN_HOURS)
        if datetime.now(timezone.utc) < allowed:
            print(f"LinkedIn and Indeed were searched under {COOLDOWN_HOURS}h ago; using the "
                  f"cached {len(cached)} rows. --force to search anyway.", file=sys.stderr)
            return cached
    try:
        from jobspy import scrape_jobs
    except ImportError:
        print("jobspy is not installed; run with ../.venv/bin/python. Using cached rows.", file=sys.stderr)
        return cached

    found, counts = [], {}
    for site in SEARCH_SITES:
        empty_run, counts[site] = 0, 0
        queries = {"visa": VISA_QUERIES if site == "linkedin" else INDEED_VISA,
                   "wide": WIDE_QUERIES if site == "linkedin" else INDEED_WIDE}.get(mode, QUERIES)
        for query in queries:
            if empty_run >= BLOCKED_AFTER:
                print(f"  {site}: {BLOCKED_AFTER} empty answers running, leaving it alone", file=sys.stderr)
                break
            kwargs = dict(site_name=[site], search_term=query, results_wanted=60 if mode == "visa" else 30 if wide else 25,
                          hours_old=24 * 30, description_format="markdown", verbose=0)
            if site == "linkedin":
                kwargs.update(location="Japan" if wide else "Tokyo, Japan", linkedin_fetch_description=True)
            else:
                kwargs.update(location="Tokyo", country_indeed="Japan")
            try:
                frame = scrape_jobs(**kwargs)
                records = frame.to_dict("records")
            except Exception as exc:
                print(f"  {site} '{query}' failed: {type(exc).__name__}: {exc}", file=sys.stderr)
                records = []
            empty_run = 0 if records else empty_run + 1
            for rec in records:
                def v(k):
                    x = rec.get(k)
                    return "" if x is None or (isinstance(x, float) and x != x) else str(x)
                if not (v("company") and v("title") and v("job_url")):
                    continue
                board = {"ats": site, "slug": re.sub(r"\W+", "", v("company").lower()), "company": v("company")}
                # Indeed Japan writes places as "Minato, 13, JP"; the search is Japan-only anyway.
                r = row(board, id=v("id"), title=v("title"), location=v("location"),
                        url=v("job_url"), posted=v("date_posted")[:10], text=clean(v("description")),
                        fetched=date.today().isoformat(), in_japan=site == "indeed")
                if r["in_japan"] and wanted(r):
                    found.append(r)
                    counts[site] += 1
            print(f"  {site} '{query}': {len(records)} results", file=sys.stderr)
            time.sleep(PAUSE + random.uniform(0, PAUSE))

    if not found:
        print("Search returned nothing usable; keeping the cached rows.", file=sys.stderr)
        return cached
    # New results join the saved ones; a row not seen again within KEEP_DAYS is dropped.
    cutoff = (date.today() - timedelta(days=KEEP_DAYS)).isoformat()
    kept = [r for r in cached if (r.get("fetched") or date.today().isoformat()) >= cutoff]
    unique = list({(r["ats"], r["id"]): r for r in kept + found}.values())
    SEARCH_RAW.write_text(json.dumps(unique, ensure_ascii=False))
    SEARCH_META.write_text(json.dumps({"searched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                       "counts": counts}, indent=1))
    return unique


# ---------------------------------------------------------------- output

def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9぀-鿿]+", "", (s or "").lower())


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def render() -> None:
    programs = json.loads(PROGRAMS.read_text())
    payload = {
        "generated": datetime.now(timezone.utc).astimezone().isoformat(timespec="minutes"),
        "checked": programs["checked"],
        "programs": programs["programs"],
        "roles": json.loads(ROLES_JSON.read_text()) if ROLES_JSON.exists() else [],
        "sources": json.loads(SOURCES_JSON.read_text()) if SOURCES_JSON.exists() else [],
        "search": json.loads(SEARCH_META.read_text()) if SEARCH_META.exists() else {},
    }
    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    page = TEMPLATE.read_text().replace("/*__DATA__*/null", blob)
    INDEX.write_text(page)
    write_csv(PROGRAMS_CSV, programs["programs"],
              ["org", "name", "status", "deadline", "deadline_note", "english_only", "language_note",
               "fits_2027", "fit_note", "track", "kind", "joining", "pay", "how", "apply_url", "source_url"])
    print(f"wrote {INDEX.relative_to(HERE.parent)} with {len(payload['programs'])} programs "
          f"and {len(payload['roles'])} roles", file=sys.stderr)


def main() -> None:
    args = set(sys.argv[1:])
    DATA.mkdir(exist_ok=True)
    if "--render" in args:
        render()
        return

    boards = json.loads(BOARDS.read_text())
    saved = json.loads(BOARDS_RAW.read_text()) if BOARDS_RAW.exists() else {}
    offline = "--reclassify" in args
    if offline:
        results = [(b, None, "", None) for b in boards]
    else:
        print(f"pulling {len(boards)} boards", file=sys.stderr)
        results = pull_all(boards)
    everything, sources, fresh = [], [], {}
    for board, rows, error, india in results:
        key = f"{board['ats']}:{board['slug']}"
        note = ""
        if rows is None or error:
            # Offline, or a board that failed: use the rows saved last time, so one bad run
            # does not empty it.
            last = saved.get(key) or {"total": 0, "rows": []}
            total, japan, india = last["total"], last["rows"], last.get("india")
            if error:
                note = f"  FAILED {error}; using the {len(japan)} rows saved last time"
        else:
            total, japan = len(rows), [r for r in rows if r["in_japan"]]
            if india == UNKNOWN:
                india = (saved.get(key) or {}).get("india")
        fresh[key] = {"total": total, "rows": japan, "india": india}
        for r in japan:
            if india and not r.get("org_id"):  # Getro rows carry their own company's answer
                r["india"] = india
        kept = merge_locations([classify(r) for r in japan if wanted(r)])
        everything += kept
        sources.append({"company": board["company"], "ats": board["ats"], "total": total,
                        "japan": len(japan), "entry": sum(e["entry"] for e in kept),
                        "english_ok": sum(e["language"] == "english_ok" for e in kept),
                        "visa": sum(e["visa"] == "yes" for e in kept), "error": error})
        print(f"  {board['company']:<22} {total:>4} postings, {len(japan):>4} in Japan, "
              f"{sum(e['entry'] for e in kept):>3} entry level{note}", file=sys.stderr)

    BOARDS_RAW.write_text(json.dumps(fresh, ensure_ascii=False))
    if GETRO_INDIA:
        GETRO_INDIA_SEEN.write_text(json.dumps(dict(_last_getro(), **{str(k): v for k, v in GETRO_INDIA.items()})))
    searching = bool({"--search", "--force", "--wide", "--visa", "--rotate"} & args)
    mode = "visa" if "--visa" in args else "wide" if "--wide" in args else "tokyo"
    if "--rotate" in args:
        # The daily run: one set of searches a day in turn, which LinkedIn tolerates where all
        # three at once get blocked. Results stay KEEP_DAYS, so every set stays current.
        mode = SEARCH_MODES[date.today().toordinal() % len(SEARCH_MODES)]
        print(f"today's searches: {mode}", file=sys.stderr)
    # --rotate keeps the cooldown, so pressing Refresh often never hammers LinkedIn.
    raw = search_rows(bool({"--force", "--wide", "--visa"} & args), mode) if searching else (
        json.loads(SEARCH_RAW.read_text()) if SEARCH_RAW.exists() else [])
    everything += merge_locations([classify(r) for r in raw if wanted(r)])
    everything = merge_sources(everything)
    indians_work_here(everything)

    # First and last seen, so the page can mark what is new.
    today = date.today().isoformat()
    seen = json.loads(SEEN.read_text()) if SEEN.exists() else {}
    for r in everything:
        s = seen.setdefault(r["key"], {"first_seen": today})
        s["last_seen"] = today
        r["first_seen"] = s["first_seen"]
    SEEN.write_text(json.dumps(seen, indent=1, sort_keys=True))

    order = {"english_ok": 0, "japanese_plus": 1, "unstated": 2, "japanese_required": 3}
    everything.sort(key=lambda r: r["posted"] or "", reverse=True)
    everything.sort(key=lambda r: order[r["language"]])
    for r in everything:  # why the team site says "Indians work here"
        i = r.get("india") or {}
        r["indians"] = i.get("note") or (("Hiring in India now" if i.get("more") else f"{i['count']} open roles in India now")
                                         + f" ({', '.join(i['places'])})" if i else "")
    ROLES_JSON.write_text(json.dumps(everything, indent=1, ensure_ascii=False))
    SOURCES_JSON.write_text(json.dumps(sources, indent=1))
    write_csv(ROLES_CSV, everything, ["company", "title", "location", "level", "min_years", "track", "grad_2027",
                                      "eligibility", "deadline", "language", "evidence", "visa", "visa_evidence",
                                      "residency", "batch", "posted", "first_seen", "source", "via", "indians", "url"])

    english = [r for r in everything if r["language"] != "japanese_required"]
    sponsor = [r for r in english if r["visa"] == "yes" and not r["residency"]]
    print(f"\n{len(everything)} roles in Japan; {len(english)} without a Japanese requirement; "
          f"{len(sponsor)} of those state visa sponsorship; "
          f"{sum(r['entry'] for r in sponsor)} of those are entry level or open to 2027 graduates.", file=sys.stderr)
    render()


if __name__ == "__main__":
    main()
