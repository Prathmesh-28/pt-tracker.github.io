# India, for Prathmesh

Entry-level product, analyst, strategy, consulting and finance roles in India, graduate programmes
and campus offers, each with what it pays, for Prathmesh: IIT Bombay, B.Tech, graduating May 2027.
He wants more than ₹20 lakh CTC as a fresher, so roles that freshers report at ₹20 lakh or more
come first, then roles at the employers that pay IIT freshers the most, then the rest. They show on the team site
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

Postings asking for two years or more are dropped. Finance roles (investment banking, research,
FP&A, valuation) come only from the top-paying employers' careers sites, below.

## Top-paying employers

Big tech, global banks and funds, consulting firms and the top Indian unicorns rarely reach the
India tracker: they post on their own careers sites. `fetch_top.py` reads the 50 employers in
`top_employers.json` from their careers systems' public feeds (Greenhouse, Lever, Ashby,
SmartRecruiters, Workday, Oracle, Eightfold, and Amazon's, Google's and Atlassian's own) and keeps
the roles in India that fit Prathmesh's primary resume:

- product, business or data analyst, strategy, consulting, finance, founder's office or growth.
  Quant and trading firms and software-engineering roles are left out at his request;
- not senior (senior, lead, manager, director, II, III) and not an internship;
- asking for at most a year of experience, or not saying. A range that starts at 0 ("0–2 years")
  counts as 0. One year is marked as a stretch, and so is a posting that names an MBA, CA or CFA.

Employers whose careers sites publish nothing readable (Goldman Sachs, American Express, Uber,
Flipkart, PhonePe, McKinsey, BCG, Bain) are not read; Goldman's New Analyst programme is in
`programs.json`. The tier in `top_employers.json` groups employers roughly; it is not pay data.

## Order

1. Roles that freshers at that company, in that role, report at ₹20 lakh CTC or more, and campus
   offers at that level.
2. Roles at the top-paying employers without such a figure.
3. Everything else.

Within each: campus offers first, then roles naming the 2027 batch, the bigger employers before
the unicorns, the kinds of role in the order above, and pay. Postings for other batches only go last.

## What each role shows

| | How it is found |
|---|---|
| **CTC** | What freshers (0–1 years) in that role at that company report on AmbitionBox, India's salary site: the average and the typical range, and how many salaries it rests on. With too few 0–1 year salaries it uses 1–2 years, and says so. A company with no figure for the role gets the role's average across India, marked as such, except at the top-paying employers, where that average would mislead and the role shows no figure. |
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
.venv/bin/python India/fetch_top.py              # roles at the top-paying employers' careers sites
.venv/bin/python India/fetch_india.py            # pay, company type and batch for each role
.venv/bin/python India/fetch_india.py --offline  # the same from cached pay only
.venv/bin/python Japan/team/sync_jobs.py --india # send the list to the team site
```

## Files

```
India/
  fetch_top.py          roles at the top-paying employers, from their careers sites
  top_employers.json    those employers, their careers feeds and tiers
  fetch_india.py        roles from data/latest.json and data/top_roles.json, pay and company type from AmbitionBox
  programs.json         graduate programmes, checked by hand
  private/campus.json   campus offers from the placement portal (gitignored)
  data/top_roles.json   what fetch_top.py kept, and how each employer's feed answered
  data/roles.json       the list, ranked
  data/roles.csv        the same, one row per role
  data/pay_cache.json   AmbitionBox answers (gitignored)
```

## Limits

- **AmbitionBox is self-reported.** A figure resting on a handful of salaries says how many.
- **Campus offers beat averages.** An IIT campus offer usually sits well above AmbitionBox's
  average for the company, which mixes every college and route in.
- **The roles are the India tracker's and the top employers' sites'.** A company that hires only
  on campus, or whose careers site publishes nothing readable, appears only once its offer is
  added to `private/campus.json`.
- **Ranking rests on AmbitionBox averages.** They mix every college and route in, so a top
  employer's IIT campus offer usually pays well above them, and a role below ₹20 lakh there may
  still clear it for an IIT graduate.
