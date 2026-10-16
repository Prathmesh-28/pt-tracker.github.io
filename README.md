# pt-tracker

Entry-level, business-track job openings in India, pulled from company
applicant-tracking feeds and from LinkedIn and Indeed searches, with a local
script that tailors your resume and drafts a pitch for the ones worth applying to.

**On this Mac:** the roles page at http://127.0.0.1:8765 and the dashboard at
http://127.0.0.1:8765/dashboard.html, refreshed every morning at 8. See
[The dashboard](#the-dashboard) and [Running it on this Mac](#running-it-on-this-mac).
**Public copy:** the Pages deployment for this repo.

**Also here:** [Japan/](Japan/README.md), roles in Japan for English speakers and the shared team
site; [India/](India/README.md), the roles below narrowed to product and analyst roles with what
each pays; [CaseCompetitions/](CaseCompetitions/README.md), case competitions and contests that lead
to a PPI or PPO, ranked for an IIT Bombay 2027 graduate; [admissions/MBA-admissions/](admissions/MBA-admissions/README.md),
top MBA schools with GMAT targets, deadlines, costs and scholarships, plus a GMAT guide.

## What it does

Four times a day a GitHub Action re-pulls every discovered board, reads each
posting's description, extracts the experience requirement written in it, and
commits the result. The page reads that file. A **Pull live** button on the page
re-queries the APIs directly from your browser, because all three send
`Access-Control-Allow-Origin: *`.

## Why the experience requirement is parsed, not guessed

A title cannot tell you years of experience. "Product Manager" is a graduate
role at one company and a four-year role at the next, and titles like
"Category Management - DGM/GM" pass any keyword filter while sitting two
promotions above entry level. So every posting's own description is read and
the minimum stated years extracted. Roles split three ways:

| Tier | Meaning |
|---|---|
| Open to you | asks for one year or less, or says fresher |
| Doesn't say | no experience line in the description |
| Two years or more | excluded by the filter, shown so the wall is visible |

## Sources

| Source | Endpoint | Notes |
|---|---|---|
| Greenhouse | `boards-api.greenhouse.io/v1/boards/{token}/jobs` | `content=true` for descriptions. `application_deadline` and `first_published` are real. |
| Lever | `api.lever.co/v0/postings/{site}?mode=json` | Title is `text`, not `title`. `createdAt` is epoch **milliseconds**. |
| Ashby | `api.ashbyhq.com/posting-api/job-board/{board}` | Unlisted postings ship in the array. `isListed` must be checked. |
| LinkedIn, Indeed | [JobSpy](https://github.com/speedyapply/JobSpy) | Top 30 per query per site, last 30 days, 15 queries including four for internships. Descriptions included. Indeed usually gives only a state code, `KA, IN`. |
| Entrackr, Inc42, YourStory | RSS | VCCircle and Moneycontrol return 403 regardless of headers. |

Search rows differ from board rows in three ways that matter:

- **They are never marked closed.** A search returns its top matches; a role
  dropping out of them has not necessarily closed. Only `last_seen` moves.
- **The board row wins.** A role on both an employer's board and LinkedIn is
  kept once, as the board row, matched on company and title.
- **Only this Mac refreshes them on demand.** A browser can re-read the three
  ATS APIs but not LinkedIn, so on GitHub Pages the button re-reads the company
  boards only. Served from this Mac, it runs the whole pipeline.

**Not getting blocked.** JobSpy reads LinkedIn's logged-out job search, so no
LinkedIn account is involved and none can be banned; the risk is the IP being
throttled. Searches run one site at a time with 6-12 second pauses, a site that
returns nothing twice in a row is left alone for the rest of the run, and
LinkedIn and Indeed are never searched twice within 4 hours however often the
pipeline runs (`JOBSPY_COOLDOWN_HOURS`). A blocked site keeps its results from
the last good search.

JobSpy also supports Naukri, Glassdoor and Google Jobs. On 2026-09-14 Naukri
demanded a recaptcha, Glassdoor answered 403 from behind bot protection, and
Google returned nothing. Getting past the first two means impersonating a
browser, which is how IPs get banned, so they stay off. `JOBSPY_SITES`,
`JOBSPY_RESULTS`, `JOBSPY_HOURS` and `JOBSPY_PROXIES` override the defaults.

The hand-run LinkedIn links on the page use the same query list and still
matter: they return every result, not the top 30.

## Finding roles you can take

The filters above the list, all combinable:

| Filter | What it does |
|---|---|
| Batch | **Open to 2027 grads**: an internship, a posting that names 2027, or a fresher role naming no batch. A posting that names only other years is out. Or pick one named year. Set the year with `PT_GRAD_YEAR`. |
| Internship or full-time | From the title (`intern`, `summer analyst`) and the listing's job type. |
| City tier | Tier 1: the eight metros plus the NCR and Mumbai satellite cities. Tier 2: the other large cities. Tier 3: any other named city. Plus Remote, and City not given (mostly Indeed). |
| VC-funded | The employer is in the funding store, matched on exact name after dropping "Pvt Ltd" and the like. |

Few postings name a batch outright (11 of about 1,100 on 2026-09-14), so the
batch years shown are only ever what the posting says.

## What the history can and cannot show

The feeds return only currently-open roles, so a role that closed before the
first run is not recoverable. What is available:

- **When a still-open role was first published.** This reaches back years; the
  oldest role in the current pull has been open over 900 days.
- **Whether a Greenhouse role was edited after publishing**, which separates a
  genuinely new opening from a quietly refreshed requisition.
- **Everything from the first run onward.** `data/seen.json` records a
  `first_seen` and `last_seen` per role, and marks a role closed on the day it
  stops appearing.

## Coverage is the real limit

Slug discovery is guesswork against a candidate list. Most large Indian
employers run Workday, Darwinbox, SAP SuccessFactors or Naukri RMS, none of
which publish a feed; the LinkedIn and Indeed searches reach some of them. A company missing here may simply not expose one under
the name that was tried. Add candidates to `scripts/probe_boards.py` and run
the refresh workflow with `rediscover` enabled.

## Everything in one file

`pt-tracker-all.json` and `pt-tracker-all.csv` at the repo root hold the whole
dataset: every funding round ingested, the roles estimated for each with a
salary band, every open posting scraped, the salary benchmarks, and the board
list. The CSV is one row per estimated role, which is the shape you actually
read. Rebuild both with `python3 scripts/compile_all.py`.

## Applying

`scripts/apply.py` does what the n8n "job applications with AI resume
tailoring" workflow does, against this tracker's roles:

| Step | n8n | Here |
|---|---|---|
| Master resume | Google Doc | `private/resume.md`, or `resume.pdf` (transcribed once to `.md`) |
| Jobs | Apify LinkedIn scraper | `data/latest.json`: boards, LinkedIn and Indeed |
| Fit filter | GPT-4o-mini | Gemini: apply, stretch or skip, with matches and gaps |
| Tailored resume | GPT-4o, saved as a Google Doc | Gemini: `resume.md`, `.html`, `.docx` |
| Contact | Anymail Finder | Anymail Finder with `--find-email`; an address in the posting is used first |
| Email | Gmail draft | Off by default. `email.eml` with `--email`; a Gmail draft with `--gmail` |

The resume is rewritten from facts already in it: reordered, cut and reworded,
never added to. Check `changes.md` in each folder against the original anyway.
Nothing is ever sent.

**Everything it writes goes under `private/`, which is gitignored. This repo is
public and Pages serves its root. Never commit your resume.**

```bash
python scripts/apply.py --dry-run                     # which roles it would pick
python scripts/apply.py                               # screen + tailor the 5 newest fresher-OK roles
python scripts/apply.py --tier open,unstated --family Product --city Bengaluru --limit 10
python scripts/apply.py --grad-year 2027 --kind internship --city-tier "Tier 1"
python scripts/apply.py --key 'linkedin:meridian:li-4464567231'
python scripts/apply.py --email --find-email --gmail
```

| Variable | For |
|---|---|
| `GEMINI_API_KEY` | Gemini. Free key at aistudio.google.com/apikey. `GEMINI_MODEL` overrides `gemini-3.5-flash` |
| `ANYMAILFINDER_API_KEY` | `--find-email`. Paid. Only a verified address goes in `To:` |
| `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD` | `--gmail`. A Google app password, which needs 2-step verification |

Roles already screened or drafted are logged in `private/applications.json`
and skipped next time; `--force` redoes them.

## The dashboard

http://127.0.0.1:8765/dashboard.html, served by `scripts/serve.py`.

| Tab | What it is for |
|---|---|
| Overview | Roles tracked, open to your batch, new today; your applications by stage; last and next run; LinkedIn and Indeed cooldown; how the pipeline fits together |
| Applications | Every role you track: Saved, Resume tailored, Applied, Interviewing, Offer, Rejected, Withdrawn, Not a fit. Change status inline; open one for dates, follow-up, notes, the tailored resume files, the role's details and its timeline. Add roles found elsewhere by hand. |
| Workflows | The daily schedule, the search cooldown, Refresh now, every pipeline run with its steps and log, and resume-tailoring runs |
| Sources | What LinkedIn, Indeed and each company board returned, and why Glassdoor, Naukri and Google Jobs are not used |
| History | Roles ever seen, still live, and new per day by source |
| Data | Every file the tracker keeps, what it holds, how big, when it changed, and whether it is public, this Mac only, or private |
| Settings | Graduation year, daily refresh time, Gemini key |

The Shortlist and Applied buttons on the roles page write to the same tracker
(`private/tracker.db`, SQLite) when the page is served from this Mac; marks made
in a browser before that move over the first time. Tailoring a resume from an
application runs `scripts/apply.py` for that role and records the verdict and
files against it. `scripts/store.py` owns the database.

## Running it on this Mac

```bash
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
./scripts/schedule_mac.sh install 08:00       # daily refresh + the local site
```

That installs two launchd jobs. One runs `scripts/refresh.sh` at 8:00 every
morning, or as soon as the Mac wakes if it was asleep. The other keeps
`scripts/serve.py` up at http://127.0.0.1:8765, where **Refresh everything**
runs the same pipeline on demand and shows each step as it goes.

- A lock stops the morning run and a button press from overlapping.
- Each run writes `data/raw/logs/<time>.log`; `latest.log` points at the newest.
- Every LinkedIn and Indeed search is archived gzipped in `data/archive/`.
- `data/seen.json` keeps every role ever seen with its first and last day,
  and `data/history/` a snapshot per day.
- The server answers on 127.0.0.1 only, refuses refresh requests from other
  sites, and never serves `private/`.

The project has to live outside `~/Downloads`, `~/Documents` and `~/Desktop`;
macOS does not let background jobs read those folders.

```bash
./scripts/schedule_mac.sh status              # both jobs, and the last run
./scripts/schedule_mac.sh run                 # refresh now
./scripts/schedule_mac.sh uninstall
```

## Run it by hand

Python 3.10+ for the search and apply steps. The board pipeline is standard
library only.

```bash
./scripts/refresh.sh                          # the whole pipeline, locked and logged
./scripts/run_all.sh                          # the same, straight to the terminal
python3 scripts/ingest_paste.py <file>        # add a funding export
python3 scripts/probe_funded.py               # look for boards at funded companies
```

## Layout

Every path is declared in `scripts/paths.py`. Nothing writes anywhere else.

```
pt-tracker-all.json      THE compiled dataset
pt-tracker-all.csv       the same thing, one row per role
index.html               the site (generated)

data/funding.json        every funding round ever ingested, deduplicated
data/seen.json           recruitment history: first seen, last seen, closed
data/benchmarks.json     entry-level salary bands by family, stage and city
data/boards.json         employers with a readable board
data/rejected_slugs.json slugs that turned out to be foreign namesakes
data/latest.json         what the page loads
data/incoming/           the raw exports, kept as source of truth
data/history/            one snapshot per run
data/search_cache.json   last LinkedIn/Indeed results without descriptions
data/raw/                regenerated each run, not versioned; logs in data/raw/logs/
data/archive/            every search, gzipped; not versioned
private/                 your resume, tailored copies, tracker.db, settings, .env; gitignored

scripts/paths.py         every file location, in one place
scripts/probe_boards.py  find which employers expose a board
scripts/probe_funded.py  same, using the funded list as candidates
scripts/fetch_jobs.py    pull postings, filter to India and business-track
scripts/fetch_search.py  add LinkedIn and Indeed results via JobSpy
scripts/refresh.sh       one locked, logged pipeline run
scripts/serve.py         the local site, the dashboard and its API
scripts/store.py         applications, their timeline and settings (private/tracker.db)
dashboard.html           the dashboard
scripts/schedule_mac.sh  install the 8 AM refresh and the local site
scripts/apply.py         screen, tailor the resume, draft the pitch
scripts/enrich.py        read descriptions, extract the experience requirement
scripts/funding.py       pull funding RSS, separate rounds from other news
scripts/ingest_paste.py  parse a pasted funding export into the store
scripts/track_history.py maintain first_seen / last_seen / closed
scripts/build_data.py    assemble data/latest.json
scripts/compile_all.py   write the two bundle files
scripts/render.py        inject data and live.js into index.html
scripts/live.js          browser-side re-pull
```
