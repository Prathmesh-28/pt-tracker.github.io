# Overseas, for Prathmesh

Entry-level business roles outside India and Japan whose own posting says the employer sponsors a
work visa. They show on the team site (https://japan-applications.vercel.app) under **Overseas**
when Prathmesh's list is selected, and are claimed and applied to like any job.

## What is kept

| | Rule |
|---|---|
| Where | Outside India and Japan, which have their own tabs |
| What | The kinds of role that fit his primary resume: product, business and data analyst, strategy, consulting, finance, founder's office, growth (the same title rules as `India/fetch_top.py`); not senior, not an internship; no roles about visas themselves (HR mobility, immigration) |
| Years | At most one year asked, or none stated; not only earlier batches |
| Visa | The posting says outright that the employer sponsors a visa ("we sponsor visas", "visa sponsorship is available", "relocation and visa support"), and never says it will not sponsor or that applicants must already have the right to work there |

A posting that says nothing about visas is left out: silence is not sponsorship. The sentence that
decided it is shown under each role, so a wrong call can be seen.

## Where the roles come from

- The careers boards the repo already reads (Japan/boards.json and India/top_employers.json; the
  Greenhouse, Lever and Ashby ones, which give every job with its description).
- LinkedIn and Indeed, searched for "visa sponsorship" analyst and graduate roles in the UK,
  Singapore, the UAE, Germany, the Netherlands, Ireland, the US, Canada and Australia, at most once a
  day with a pause between searches (cached in `data/search_raw.json`, gitignored).

## Running it

It runs in the daily refresh (`Japan/daily.sh`, 8:00 IST).

```bash
.venv/bin/python Overseas/fetch_overseas.py            # boards, plus the searches if a day has passed
.venv/bin/python Overseas/fetch_overseas.py --boards   # boards only
.venv/bin/python Japan/team/sync_jobs.py --overseas    # send them to the site
```

## Limits

- Few postings say they sponsor, and fewer of those are entry-level business roles, so the list is
  short. Many employers that do sponsor never say so in the posting.
- Graduate schemes abroad that run on their own sites (UK grad schemes, bank analyst programmes) are
  not read.
- Country is guessed from the location text; "Not stated" when it names no known city or country.
