# Case competitions

Case competitions, and any other contest that leads to a job (a pre-placement interview, a
pre-placement offer or an internship), pulled live from Unstop every morning and ranked for
Prathmesh: IIT Bombay, B.Tech Civil with an IEOR minor, graduating 2027 (`profile.json`).

They show on the team site (https://japan-applications.vercel.app) under **Competitions** when
Prathmesh's list is selected, where anyone on the team can take one on, mark it registered and
move it through the rounds, as with jobs. `data/competitions.csv` has the same list for a
spreadsheet.

## How they are ranked

IIT-only competitions come first, then the employers that pay an IIT graduate most. Big companies
that take everyone rank lower: Tata, ITC, Reliance and FMCG hire in volume and pay an IITian less.

| Band | What lands here |
|---|---|
| 1. IIT only | Only IIT students may enter (Unstop's list of allowed campuses is all IITs) |
| 2. Top-paying employer | Quant and trading firms, investment banks, McKinsey, BCG and Bain, big tech; with a hiring route or a prize |
| 3. Select campuses or strong pay | A short list of campuses that includes IIT Bombay, or a well-paying employer (product, fintech, payments, consulting) |
| 4. Big company, open to all | Tata, ITC, Reliance, HUL, FMCG, auto, banks, IT services, the Big Four |
| 5. College fest or small organiser | The prize and a line on the CV |

Within a band: a PPO, PPI or internship first, then the bigger prize pool, then the
better-paying employer, then a case competition over other formats; ties go to the nearer
deadline. Each entry carries a one-line reason, for example *"12 premier campuses, IIT Bombay
included · Product and fintech: strong pay · PPI · ₹2 lakh in prizes"*.

The employer tiers are groupings by type of employer, not salary data. Move a company by editing
its pattern in `employers.json`.

## What each entry shows

- **Deadline**: when registration closes, to the minute, in India time, and the days left.
- **Prize pool** and **how many win**: the cash on every prize line, or the pool the organiser
  states when it is larger ("prizes worth INR 20,00,000").
- **Hiring route**: PPO or job offer, PPI, internship. From the organiser's prize flags and from
  what the prizes and the page say. Organisers tick these loosely, so read the prize lines.
- **Who can enter** and, if only some campuses may, which ones.
- **Rounds**: each stage with its dates and what happens in it.
- **Team size**, online or in person, entry fee, how many have registered.

## Who can enter

Read from each competition's own Unstop page, not guessed from the title:

| Left out, with the reason kept in the data | Example |
|---|---|
| Another batch | "For the 2028 batch" (most internship-linked contests target pre-final years) |
| MBA or PGDM only | B-school tracks of TVS RiDE, Sun PRISM, Airtel iCreate |
| A campus list without IIT Bombay | Unstop lists the campuses allowed; IIT Bombay is organisation 604 |
| Other branches only | "Other branches only: Computer Science and Engineering" |
| Working professionals, or not open in India | |

"Women only" and "eligibility not stated" are kept, marked **Check**, because the listing alone
cannot settle them. So are cultural events, workshops and ambassador programmes: they are not
ranked at all.

## Between seasons: the watchlist

Most big competitions open once a year, so the site also shows **When the big ones open**
(`watchlist.json`). For those on Unstop (Tata Imagination Challenge, HUL, Hero Campus Challenge,
Meesho DICE, Amazon ML Challenge, American Express, Aditya Birla, Maruti Suzuki and others)
every past edition is read live with its dates, and the next one is expected a year after the
last. Those run elsewhere (the Inter IIT Tech Meet, WorldQuant's championship, IMC Prosperity,
Citadel, Goldman Sachs and J.P. Morgan hackathons, Flipkart GRiD, L'Oréal Brandstorm, Imagine
Cup) carry dates checked by hand, with sources, on 15 October 2026.

Many internship-linked contests (Flipkart GRiD, Amazon ML Challenge, the bank hackathons) take
the batch a year from graduating, so for a 2027 graduate their next editions are often too late.
The watchlist says so for each.

## Running it

It runs inside the Japan refresh, every day at 8:00 IST and on the site's Refresh button
(`Japan/daily.sh`): fetch, then sync.

```bash
.venv/bin/python CaseCompetitions/fetch_competitions.py            # pull from Unstop, rank, write data/
.venv/bin/python CaseCompetitions/fetch_competitions.py --offline  # re-rank the last pull without requests
.venv/bin/python Japan/team/sync_jobs.py --competitions            # send the ranked list to the team site
```

The first run reads every listing's own page (about 600, ten minutes); later runs read only the
listings that changed. Requests go one at a time with a pause between them.

## Files

```
CaseCompetitions/
  profile.json             who the ranking is for: institute, degree, branch, batch
  employers.json           employer pay tiers, as name patterns
  watchlist.json           the big competitions to watch between seasons
  fetch_competitions.py    pull, judge, rank, write data/
  data/competitions.json   every open listing: ranked ones first, then the rest with the reason
  data/competitions.csv    the same, one row per listing
  data/watchlist.json      the watchlist with every edition found
  data/seen.json           the first and last day each listing was open
  data/details.json        each listing's own page, cached (gitignored)
  data/listings.json       the last raw pull, for --offline (gitignored)
```

## Limits

- **Unstop only, live.** Nearly every Indian case competition registers there, but contests run
  on a company's own site (quant firms, banks, Flipkart GRiD since 2025) are only in the
  watchlist, checked by hand.
- **IIT-only contests announced inside IIT channels** (the placement cell, the technical council,
  department mailing lists) never reach Unstop. Add them on the site with a note.
- **A PPI is the organiser's word.** "PPI opportunity subject to business requirement" is common.
