# Japan applications team

A shared tracker for the friends applying to jobs in Japan on Prathmesh's behalf.
Everyone sees the same list. A job is claimed before anyone applies, the claim
and the application are recorded in the database, and a second claim on the
same job is refused, so nobody applies twice.

- **Backend:** Supabase (Postgres, auth, storage for the resumes, live updates)
- **Frontend:** a static page on Vercel (`web/`), no build step
- **Jobs:** the English-friendly roles and programs from `Japan/data/`, pushed by
  `sync_jobs.py`

## Live

| | |
|---|---|
| Site | https://japan-applications.vercel.app (Vercel project `japan-applications`) |
| Database | Supabase project `japan-team`, Mumbai; the ref and keys are in `Japan/private/team.env` |
| Owner | The email in `japan_settings.owner_email` becomes the owner on signing up |
| Keys | `Japan/private/team.env` (gitignored): URL, anon key, service-role key, database password |

## One list per person

The switch at the top of the site picks whose applications you are working on:
**Prathmesh** or **Madhura** (the owner can add more in Settings). Each person has
their own jobs, resumes and applications; an application can only use a resume of
the person the job is for, and that rule is enforced in the database. Madhura's list
comes from `madhura/`, which stays private and out of this repo: part-time and
full-time roles chosen for her, with her own labels (the Japanese each job asks for,
the hourly pay, how far it is, whether foreigners or students already work there).
A person marked as living in Japan gets no visa filter and no visa warnings.
Prathmesh's roles carry **Indians work here** when the company is hiring in India now or
has an India office (how that is decided: [../README.md](../README.md)), with the reason
under the role and a filter to show only those.

```bash
.venv/bin/python Japan/team/sync_jobs.py                       # Prathmesh's list
.venv/bin/python Japan/team/sync_jobs.py --candidate madhura   # Madhura's list
```

## Case competitions

Prathmesh's list has a **Competitions** tab: case competitions and other contests that lead to a
PPI, a PPO or an internship, pulled live from Unstop and ranked for an IIT Bombay B.Tech graduating
in 2027. IIT-only competitions come first, then top-paying employers (quant, banks, top consulting,
big tech), then a short campus list or a strong-paying employer, then big companies open to all
(Tata, ITC, FMCG), then college fests. How, and what each entry carries:
[../../CaseCompetitions/README.md](../../CaseCompetitions/README.md).

They are rows of `japan_jobs` with kind `competition`, so the claim rules, notes, history and live
updates are the same as for jobs:

| Button | What it does |
|---|---|
| I'll take it on | Claims it, as with a job; lapses after the same claim time if nobody registers |
| Mark registered | Records who registered, with which account, and the team; needs no resume (`japan_register`) |
| Update | Next round, Won, Out or Dropped |
| Not doing | Skips it with a reason |
| + Add a competition | One found outside Unstop, such as an IIT-only contest from a placement-cell mail, with its priority (`japan_add_competition`). The sync never closes these; they close when their deadline passes. |

Under the list, **When the big ones open** shows the watchlist: each big competition's last
edition and when the next is due, and whether a 2027 graduate can enter it.

```bash
.venv/bin/python CaseCompetitions/fetch_competitions.py        # pull and rank
.venv/bin/python Japan/team/sync_jobs.py --competitions        # send them to the site
```

## India jobs

Prathmesh's list also has an **India jobs** tab (the Jobs tab becomes **Japan jobs**): entry-level
product analyst, APM, analyst and graduate roles in India from the India tracker at the repo root,
each with what freshers there are paid (CTC, and base when known), whether the company is a startup,
an MNC or an Indian company, the batch it is for and its deadline. Campus offers from the placement
portal and graduate programmes come first. How: [../../India/README.md](../../India/README.md).
They are rows of `japan_jobs` with kind `india`; claiming and applying work as for any job.

```bash
.venv/bin/python India/fetch_india.py              # pay and company type for each role
.venv/bin/python Japan/team/sync_jobs.py --india   # send them to the site
```

## Fresh every morning, and on the Refresh button

Both lists refresh on the owner's Mac every day at 8:00 IST (`Japan/daily.sh`, scheduled
with launchd; it uses India time whatever the Mac's time zone). Anyone on the team can
also press **Refresh jobs** at the top of the site: that queues a refresh in the database
(`japan_refreshes`), the Mac picks it up within a minute, and the site shows each step
as it runs and reloads the jobs after each list is synced. One refresh runs at a time; a
second press while one waits or runs joins it, and a new one can start 10 minutes after
the last finished. The Mac must be on: a refresh asked for while it sleeps starts when
it wakes.

Each refresh pulls every company board and every open competition on Unstop. Searches keep
cooldowns so the job boards do not block us: LinkedIn and Indeed at most every 4 hours
(Prathmesh's three search sets take turns, one a day), Madhura's part-time searches every hour.

**No job twice.** The sync (`sync_jobs.py`) matches jobs by title, employer and, on
Madhura's part-time list, the branch:

| Case | What the sync does |
|---|---|
| The same job found again under another link (LinkedIn one day, Indeed the next) | Keeps the row it already has, so a claim or application on it still shows |
| A job the team added by hand turns up in a search | Leaves the team's row; does not add it again |
| One key twice in a batch | Sends it once |
| A posting leaves every source | Marks it closed, never deletes it |
| A source fails and a third of the open jobs vanish at once | Closes none of them and says so in the log |

New jobs carry a **New** badge for a day and a half, and "Newest" sorts by when a job
reached the list.

## How it keeps two people off the same job

| Step | What happens |
|---|---|
| Claim | Takes the job for you. Of two people claiming at the same moment, exactly one wins; the other is told who has it. The job leaves everyone's "Open to claim" list at once. |
| Mark applied | Records who applied, which of the resumes, with which email or account, and a note. Only the person who claimed it (or the owner) can do this. "Applied already" claims and records in one step. |
| Not a fit | Skips the job with a reason, so nobody else spends time on it. |
| Release | Gives a claim back. A claim nobody turns into an application lapses after 48 hours (Settings). |
| Interview, offer, rejected, withdrawn | Only the person who applied, or the owner, can move it on. |
| Same company | Claiming or applying shows the group's other applications at that company first. |

All of this is enforced in the database (`supabase/migrations/`), not only in the
page: nobody can write to the tables directly, everything goes through functions
that check who you are, and a job has at most one application row. 41 checks in a
local test cover it, including two people claiming the same job at once.

## Roles

| | Owner (Prathmesh) | Helper (friends) |
|---|---|---|
| See jobs, claims, applications, activity | Yes | Yes, once approved |
| Claim, apply, skip, add jobs found elsewhere, leave notes | Yes | Yes |
| Download resumes | Yes | Yes |
| Upload, retire or delete resumes | Yes | No |
| Approve, revoke or remove people; make someone an owner | Yes | No |
| Mark jobs as picks or "do not apply"; reset an application | Yes | No |
| Change the claim time limit; export everything as CSV | Yes | No |

New accounts wait in the Team tab until the owner approves them; until then they
see nothing. Resumes sit in a private storage bucket and are handed out as links
that expire after five minutes.

## Set up

### 1. Database

```bash
cd Japan/team
supabase link --project-ref <project-ref>
supabase db push                       # creates the japan_* tables, functions, bucket
```

Then, in the Supabase SQL editor, set the owner's sign-in email **before anyone
signs up**:

```sql
update public.japan_settings set value = 'your-email@example.com' where key = 'owner_email';
```

In Authentication → Sign In / Providers → Email, turn **Confirm email** off. The
owner's approval is the gate, and Supabase's built-in mailer sends only a few
emails an hour, which ten people signing up would exceed.

Everything is prefixed `japan_`, so it can share a project with other apps
without colliding. A project of its own is still better: people who sign up here
become users of that project.

### 2. Website

```bash
cd Japan/team/web
vercel link                             # once
vercel env add SUPABASE_URL production
vercel env add SUPABASE_ANON_KEY production
vercel deploy --prod
```

The anon key is public by design; row-level security decides what it can read.

### 3. Jobs

Put the service-role key where git cannot see it, then sync after each fetch:

```
Japan/private/team.env
    SUPABASE_URL=https://<project-ref>.supabase.co
    SUPABASE_SERVICE_ROLE_KEY=...
```

```bash
.venv/bin/python Japan/fetch_japan.py      # refresh the Japan data
.venv/bin/python Japan/team/sync_jobs.py   # push it to the team list
```

The sync sends every role without a Japanese requirement and every open program
that fits a 2027 graduate (about 2,100 today). It never touches the owner's picks,
vetoes or notes, and it marks a job closed rather than deleting it, so its history
stays.

### 4. Daily refresh and the Refresh button

```bash
Japan/daily.sh install    # on the Mac that runs the searches
Japan/daily.sh status     # scheduled? how did the last run go
```

To have the Mac awake at 8:00, once: `sudo pmset repeat wakeorpoweron MTWRFSU 07:58:00`.
Logs are in `Japan/private/logs/`.

### 5. People and resumes

1. Sign up on the site with the owner email. You land as the owner.
2. Resumes tab: upload each resume and name it for the team (for example
   "Business", "Data and AI", "Software"), with a line on when to use it.
3. Send the site link to your friends. They create accounts; approve them in the
   Team tab.

## Run it on this Mac

```bash
cd Japan/team
supabase start -x vector,logflare,studio,imgproxy,edge-runtime
supabase status -o env                  # API_URL and ANON_KEY for the next line
echo '{"url":"http://127.0.0.1:54321","anonKey":"<ANON_KEY>"}' > web/config.local.json
python3 -m http.server 8790 --directory web
```

`web/config.local.json` is gitignored. On localhost the page reads it; on Vercel
it asks `/api/config`, which returns the two environment variables.

## Files

```
Japan/team/
  README.md                         this file
  supabase/migrations/*.sql         tables, row-level security, workflow functions, bucket
  supabase/config.toml              local Supabase settings
  sync_jobs.py                      push Japan/data roles and programs into japan_jobs, one row per job
  refresh_queue.py                  the Refresh button seen from the Mac: claim a request, report progress
  web/index.html, app.js, style.css the site
  web/api/config.js                 hands the browser the Supabase URL and anon key
  web/vercel.json                   security headers, noindex
```
