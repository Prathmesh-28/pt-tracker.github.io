# India, for Prathmesh

Entry-level product and analyst roles in India, graduate programmes and campus offers, each with
what it pays, for Prathmesh: IIT Bombay, B.Tech, graduating May 2027. They show on the team site
(https://japan-applications.vercel.app) under **India jobs** when Prathmesh's list is selected,
where the team claims and applies to them as with any job. `data/roles.csv` has the same list.

## Where the roles come from

The India tracker at the root of this repo pulls entry-level business openings in India every
day from LinkedIn, Indeed and company boards, and reads each posting for the experience it asks
(see [../README.md](../README.md)). This folder keeps the kinds of role wanted, in this order:

| Order | Roles |
|---|---|
| 1 | Product analyst, associate product manager |
| 2 | Business analyst, data analyst |
| 3 | Strategy, consulting |
| 4 | Founder's office, management trainee and graduate programmes |
| 5 | Growth, category, operations |
| 6 | Business development |

Postings asking for two years or more are dropped. Campus offers and graduate programmes come
first on the list.

## What each role shows

| | How it is found |
|---|---|
| **CTC** | What freshers (0–1 years) in that role at that company report on AmbitionBox, India's salary site: the average and the typical range, and how many salaries it rests on. With too few 0–1 year salaries it uses 1–2 years, and says so. A company with no figure for the role gets the role's average across India, marked as such. |
| **Base** | AmbitionBox's fixed share when it reports one. Otherwise it is estimated from the median base-to-CTC share of the campus offers recorded, and marked "est.". |
| **Startup, MNC or Indian company** | AmbitionBox's company profile: its type (Startup, MNC), ownership and headquarters. A company in the tracker's funding store counts as a startup. |
| **Batch** | Names the 2027 batch; names other batches only; an internship; or names no batch, which usually means joining within weeks. |
| **Deadline** | The apply-by date when the posting states one. LinkedIn and Indeed postings rarely do, so most show the date posted. |

Glassdoor and Levels.fyi answer automated reading with a captcha, so their figures are not used.
AmbitionBox answers are cached for 30 days (`data/pay_cache.json`, gitignored), so a daily run only
asks about new companies. Requests go one at a time with a pause between them.

## Campus offers

`private/campus.json` holds offers seen on the placement portal (JAFs), one per company and role,
with the CTC and base. It is gitignored: placement-cell details stay off this public repo. Each
offer becomes a row on the site, visible to the approved team, and its figures override the
AmbitionBox average for that company.

```json
{"company": "Example Fintech", "role": "Analyst", "ctc_lpa": 20, "base_lpa": 16,
 "where": "IIT Bombay campus (JAF)", "seen": "2026-10-14", "deadline": "2026-10-20"}
```

## Graduate programmes

`programs.json`, checked by hand with sources: Goldman Sachs' New Analyst programme for final-year
students, and ZS Associates' analyst roles. Add others as they are found; pay is looked up like
any role.

## Running it

It runs inside the Japan refresh, every day at 8:00 IST and on the site's Refresh button
(`Japan/daily.sh`), after the India tracker's own morning run has written `data/latest.json`.

```bash
.venv/bin/python India/fetch_india.py            # pay, company type and batch for each role
.venv/bin/python India/fetch_india.py --offline  # the same from cached pay only
.venv/bin/python Japan/team/sync_jobs.py --india # send the list to the team site
```

## Files

```
India/
  fetch_india.py        roles from data/latest.json, pay and company type from AmbitionBox
  programs.json         graduate programmes, checked by hand
  private/campus.json   campus offers from the placement portal (gitignored)
  data/roles.json       the list, ranked
  data/roles.csv        the same, one row per role
  data/pay_cache.json   AmbitionBox answers (gitignored)
```

## Limits

- **AmbitionBox is self-reported.** A figure resting on a handful of salaries says how many.
- **Campus offers beat averages.** An IIT campus offer usually sits well above AmbitionBox's
  average for the company, which mixes every college and route in.
- **The roles are the India tracker's.** A company that hires only on campus, or posts only on its
  own site, appears only once its offer is added to `private/campus.json`.
