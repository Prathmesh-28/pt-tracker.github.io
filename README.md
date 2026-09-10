# pt-tracker

Entry-level, business-track job openings in India, pulled from company
applicant-tracking feeds rather than scraped from job boards.

**Live site:** see the Pages deployment for this repo.

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
| Entrackr, Inc42, YourStory | RSS | VCCircle and Moneycontrol return 403 regardless of headers. |

LinkedIn is **not** scraped. The page builds search URLs with the entry-level
and last-30-days filters pre-applied, and you click them yourself.

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
which publish a feed. A company missing here may simply not expose one under
the name that was tried. Add candidates to `scripts/probe_boards.py` and run
the refresh workflow with `rediscover` enabled.

## Everything in one file

`pt-tracker-all.json` and `pt-tracker-all.csv` at the repo root hold the whole
dataset: every funding round ingested, the roles estimated for each with a
salary band, every open posting scraped, the salary benchmarks, and the board
list. The CSV is one row per estimated role, which is the shape you actually
read. Rebuild both with `python3 scripts/compile_all.py`.

## Run it

```bash
./scripts/run_all.sh                          # the whole pipeline, in order
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
data/raw/                regenerated each run, not versioned

scripts/paths.py         every file location, in one place
scripts/probe_boards.py  find which employers expose a board
scripts/probe_funded.py  same, using the funded list as candidates
scripts/fetch_jobs.py    pull postings, filter to India and business-track
scripts/enrich.py        read descriptions, extract the experience requirement
scripts/funding.py       pull funding RSS, separate rounds from other news
scripts/ingest_paste.py  parse a pasted funding export into the store
scripts/track_history.py maintain first_seen / last_seen / closed
scripts/build_data.py    assemble data/latest.json
scripts/compile_all.py   write the two bundle files
scripts/render.py        inject data and live.js into index.html
scripts/live.js          browser-side re-pull
```
