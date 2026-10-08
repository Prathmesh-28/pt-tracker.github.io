# Japan, English only

Off-campus routes into jobs in Japan for IIT students graduating in 2027 who
speak English and no Japanese: the programs open now, the platforms that place
IIT students with Japanese employers, and a script that pulls live entry-level
roles in Japan and reads each one for what it says about Japanese.

Open `Japan/index.html` in a browser, or http://127.0.0.1:8765/Japan/ when
`scripts/serve.py` is running. Checked on **7 October 2026**.

## The short answer

- **English alone is enough for engineering, data and AI roles** at
  English-first employers: Rakuten's tech organisation, Mercari, Sony, LY
  Corp's development division, Money Forward, HENNGE, PayPay and Preferred
  Networks. Most of them want a CS, IT, data or maths degree, or coding you can
  show.
- **Business-track new-grad roles almost always need Japanese.** Rakuten's
  business course wants business-level Japanese and TOEIC 800. Mercari's PM and
  data-analyst internships want Japanese (C1 for data). So do Point72's Tokyo
  academy and nearly every Amazon Japan analyst and HR role. The exceptions
  found: Morgan Stanley's Tokyo Institutional Equity Division analyst program
  ("Japanese proficiency is not required", quantitative degrees), Rakuten
  Payment's Product/Project Manager ("Japanese: Not required to Business
  Level"), Fast Retailing's global route (JLPT N2 within two years of joining,
  not at entry), and data or analyst roles at English-first tech firms.
- **Most English-only new grads get in through an internship.** Mercari,
  HENNGE, Sony and Woven run 4-week to 3-month internships in Tokyo, pay for the
  visa, flights and housing, and hire from them.
- **Japanese is the lever.** JLPT N3 to N2 opens Japanese manufacturers (Honda,
  Panasonic, Yamaha and others hire IIT engineers through the platforms below)
  and most business roles. ASIA to JAPAN teaches it free to students it places.

## Closing now

| Deadline | Program | Japanese | Notes |
|---|---|---|---|
| 30 Oct 2026, 9:00 JST | [Rakuten new-grad engineer intake, 2028 joiners](https://www.i-note.jp/rakuten-tech-entry/2028joiners/positionlist-en/fulltime.html) | Not required for AI Engineer, Research Scientist, two Data Engineer roles, Cloud Platform SWE; "not required to business" for Rakuten Payment SWE and PM | Joins April or October **2028**; the 2027 intake is closed. Coding test for most roles. From JPY 370,000 a month. |
| 31 Oct 2026, 23:59 JST | [Mercari Class of 2028 Software Engineer Internship](https://apply.workable.com/mercari/j/EC5A1078C4/) | English or Japanese at CEFR B2 | For people who can join **October 2027** or April 2028. 2 to 3 months in Japan; visa, flights and housing arranged. |
| 30 Nov 2026, 23:55 JST | [Morgan Stanley 2027 IED Full-Time Analyst Program, Tokyo](https://www.linkedin.com/jobs/view/4475188125) | Not required | Graduating by July 2027 in maths, physics, CS or another quantitative discipline; one programming language. Visa and relocation. Rolling review, so earlier is better. |
| End of Nov 2026 | [GS-JTI (METI)](https://gs-jti.go.jp/foreign-talent/) | Not required | Government-funded internships with Japanese tech firms until 12 Feb 2027, in Japan or online. Coding tests run in batches until then. Register on [Talendy](https://hub.techjapan.work/register). |
| Mid-Oct 2026 | [LY Corp 2028 new grads](https://www.lycorp.co.jp/en/recruit/newgrads) | Engineers: none in the last cycle | Positions announced mid-October; [pre-entry](https://lycorp.snar.jp/jobboard/detail.aspx?id=bbB2fkI4Rzxp3NEKsnXUZQ) is open. |
| Rolling | [HENNGE Global Internship Program](https://recruit.hennge.com/en/gip/) | Not required | Coding challenge first. 4 to 6 weeks in Shibuya; can lead to a full-time offer. |
| Monthly | [ASIA to JAPAN FAST OFFER](https://fastoffer.co.jp/intl/) | Taught free | Monthly interview fairs with 250+ Japanese companies. |

## How hiring works for a 2027 IIT graduate

- **Joining dates.** Japanese employers bring new graduates in as a cohort in
  April or October. An IIT degree ends in mid-2027, so October 2027 or April
  2028 is realistic.
- **"Class of 2028" can include you.** Japanese postings name the class by when
  you join, written 28卒. Mercari's Class of 2028 internship is explicitly for
  people joining in October 2027 or April 2028. Read the target line on each
  posting rather than the class label.
- **Selection.** Online application, then a coding test (engineering) or a web
  aptitude test, then two to four interviews, in English at the companies above.
  Rakuten makes offers from November.
- **Visa.** The employer sponsors the
  [Engineer / Specialist in Humanities / International Services](https://www.moj.go.jp/isa/applications/status/gijinkoku?lang=en)
  status. The job has to relate to your degree, and an engineering degree
  covers engineering and most analyst work. The Certificate of Eligibility takes
  one to three months.
- **J-Find does not apply.** The two-year job-hunting visa needs a university in
  the top 100 of at least two of QS, THE and the Shanghai ranking. No IIT
  qualifies.

## Platforms that place IIT students in Japan

| Platform | What it is | Japanese | Register |
|---|---|---|---|
| ASIA to JAPAN (FAST OFFER) | Monthly online interview fairs with 250+ companies including Panasonic, SEGA, Yamaha, Rakuten, Honda and Mitsubishi Electric. Runs IIT placement support. Free Japanese classes, resume help, visa processing, and flights and housing after an offer. | Taught; not needed to register | [fastoffer.co.jp](https://fastoffer.co.jp/intl/) |
| Tech Japan (Talendy Hub) | Internship-to-hire platform adopted by IITs. 350+ companies including Nidec, Mercari, Money Forward, AGC and IHI. Also runs GS-JTI registration. | Depends on the company | [hub.techjapan.work](https://hub.techjapan.work/register) |
| Cognavi (Forum Engineering) | "Work in Japan" for Indian new graduates in mechanical, electrical and IT engineering. On eight IITs. In 2026, 13 students from IIT Mandi, IIT Madras and SRM got offers of Rs 42 to 56 lakh a year. | Not stated | Through your institute; [news](https://www.forumeng.co.jp/en/news/2025/830.html) |
| JETRO Japan Career Day | Japan hiring fair, ninth edition on 22 to 23 Aug 2026 | Mixed | IIT Hyderabad students only |
| [Japan Dev](https://japan-dev.com/jobs), [TokyoDev](https://www.tokyodev.com/jobs) | Job boards of English-speaking tech roles, filterable to no Japanese | None | Mostly experienced hires, some new-grad |

## Live roles

`fetch_japan.py` pulls 134 sources: company job boards, Japan Dev, ten VC
portfolio job boards, and LinkedIn and Indeed searches. It keeps **every**
posting in Japan, at any level, and reads each description for four things:
its Japanese requirement, visa sponsorship, the years of experience it asks
for, and the graduation window it accepts. The page then filters; by default it
shows entry-level roles where a visa is not ruled out.

| Visa label | Meaning |
|---|---|
| Sponsors visa | The posting (or Japan Dev's record) says it sponsors or supports work visas |
| Not stated | Nothing either way. A company that hires you from India has to sponsor the visa, so ask |
| No visa sponsorship | Says it cannot sponsor, or that you must already have the right to work in Japan |

| Level | From |
|---|---|
| Internship, New grad, Entry level | The title (intern, graduate, 新卒, junior, associate, analyst) or at most one year asked for |
| Mid level, Senior | Two or more years asked for, or a senior title |
| Not stated | No title cue and no years mentioned |

Experience years come from the India tracker's extractor (`scripts/enrich.py`)
plus Japanese phrasings such as 実務経験3年以上.

| Language label | Meaning |
|---|---|
| English OK | Says Japanese is not required, or that English or Japanese will do |
| Japanese a plus | Japanese appears only under preferred or nice to have |
| Not stated | English description that never asks for Japanese |
| Japanese required | Asks for a Japanese level, or is written only in Japanese. Hidden by default, shown so the wall is visible. |

| Batch label | Meaning for someone finishing an IIT degree in May to July 2027 |
|---|---|
| Fits 2027 grads | The posting's dates include you: a graduation window that covers mid-2027 ("April 2027 through March 2028", "by July 2027"), or joining after it ("October 2027 or April 2028") |
| Likely fits | A label without dates, such as 28卒 or "2027 Start" |
| New-grad role, no dates | Says new graduates but names no window |
| Not for 2027 grads | The window ends before mid-2027 (27卒 means by March 2027), an MBA program, a master's or PhD only, or graduates of universities in Japan only |
| No batch named | An ordinary entry-level role |

**Japanese class labels count by fiscal year.** 28卒 is everyone graduating
between April 2027 and March 2028, which includes an IIT 2027 graduate; 27卒
ends in March 2027 and does not. Western banks use calendar years instead, so
Barclays' "2028" programme wants graduation from September 2027. Dates decide,
not labels. The sentences that decided both labels are quoted under each role,
and roles that say you must already live in Japan are hidden by default.

```bash
.venv/bin/python Japan/fetch_japan.py              # pull the boards, rebuild the page
.venv/bin/python Japan/fetch_japan.py --search     # also LinkedIn and Indeed, Tokyo, 6 queries
.venv/bin/python Japan/fetch_japan.py --wide       # all of Japan, 10 LinkedIn and 4 Indeed queries
.venv/bin/python Japan/fetch_japan.py --visa       # all of Japan, roles that sponsor visas or need no Japanese
.venv/bin/python Japan/fetch_japan.py --rotate     # one of the three searches above a day, in turn (4-hour cooldown)
.venv/bin/python Japan/fetch_japan.py --reclassify # re-read saved descriptions, no requests
.venv/bin/python Japan/fetch_japan.py --render     # rebuild the page from saved data
```

All of this runs by itself on this Mac every morning at 8:00 IST, and whenever someone
presses Refresh on the team site: `Japan/daily.sh` pulls the boards, runs that day's
search set, refreshes Madhura's list, and syncs both to the team site.

```bash
Japan/daily.sh install    # schedule it (launchd): 8:00 IST daily, whatever this Mac's time zone
Japan/daily.sh status     # is it scheduled, and how did the last run go
Japan/daily.sh now        # run it now in the background; log in Japan/private/logs/
```

| Source | Employers |
|---|---|
| Greenhouse | PayPay (3 boards), Datadog, Stripe, Coupang, Point72, Wrike, Dataiku, CircleCI, Zscaler, Databricks, Agoda, Anthropic, New Relic, MongoDB, Figma, Adyen, Airbnb, Asana, Okta, Elastic, GitLab, Dropbox, Twilio, Grafana Labs, Cloudflare, Pinterest, Roblox, Riot Games, Tripadvisor |
| Lever | Woven by Toyota, Mujin, ispace, Binance |
| Ashby | Reaktor, OpenAI, Snowflake, Notion, Kraken Technologies, Miro |
| SmartRecruiters | Bosch, ServiceNow, Roland Berger, Wise, Canva |
| Workable | Mercari, SmartNews, through the widget endpoint (one request per board). The v3 search endpoint blocks an IP for a day after rapid requests, so it is not used. |
| Workday | Sony; and, searched for Japan and Tokyo: Salesforce, Citi, Morgan Stanley, Accenture, Micron, Hitachi, NVIDIA, Mastercard, Deutsche Bank, State Street, BlackRock, PwC, Adobe, Intel, P&G, 3M, Philips, AstraZeneca, Pfizer, Abbott, Thermo Fisher, KLA, Equinix, HP, Analog Devices |
| Oracle Recruiting | JPMorgan Chase, searched for Tokyo and Japan |
| Amazon | amazon.jobs, every posting in Japan |
| Japan Dev | japan-dev.com, the union of its category pages (it renders 60 jobs per page), with its own visa, Japanese-level, seniority and apply-from-abroad fields |
| VC portfolio boards (Getro) | Japan jobs at the portfolio companies of Accel, Khosla, General Catalyst, Thrive, Insight, Notable, 8VC, Antler, Techstars, Headline and Underscore. Their apply links also revealed 44 company boards, now pulled directly |
| LinkedIn, Indeed | JobSpy. `--search` is Tokyo and six queries; `--wide` is all of Japan with "2027 graduate", "new graduate 2027", "graduate analyst", "graduate engineer", "graduate trainee", "entry level", "junior", "new grad", "28卒", "新卒 英語" on LinkedIn and four on Indeed |

Searches use the same care as the India search: one site at a time, 6 to 12
second pauses, a site left alone after two empty answers, and no second search
within 4 hours unless forced. New search results are added to the saved ones; a
result not seen again for 21 days is dropped. A board that fails uses the rows
saved last time, so one bad run does not empty it.

**What it cannot see.** Rakuten, LY Corp, Money Forward, HENNGE and most
Japanese manufacturers recruit through Japanese systems (i-web, HRMOS, Snar,
Mynavi) that publish no feed, and Goldman Sachs' and Google's sites render with
JavaScript. Those are in `programs.json`, checked by hand. Glassdoor, GaijinPot
and CareerCross block automated reads.

## Team tracker

Friends applying on your behalf share one list in `team/`: Supabase holds who
claimed and applied to what, with which resume; the site is on Vercel at
https://japan-applications.vercel.app. A job can be claimed by one person only, so
nobody applies twice. The list refreshes every morning at 8:00 IST and on the site's
Refresh button. Setup, roles and how it works: [team/README.md](team/README.md).

## Files

```
Japan/
  README.md            this file
  programs.json        programs, platforms and job boards, checked by hand (edit this)
  boards.json          employer boards fetch_japan.py pulls
  fetch_japan.py       pull, classify, write data/ and index.html
  daily.sh             the 8:00 IST refresh and the site's Refresh button: pull, search, sync
  page.template.html   the page; fetch_japan.py fills in the data
  index.html           the page (generated)
  data/roles.json      live entry-level roles in Japan with their language label
  data/roles.csv       the same, for a spreadsheet
  data/programs.csv    programs.json as a spreadsheet
  data/sources.json    what each board returned on the last pull
  data/seen.json       first and last day each role was seen
  data/search_raw.json last LinkedIn and Indeed results with descriptions; gitignored
  data/boards_raw.json every board's Japan postings with descriptions; gitignored
  data/search_meta.json when they were searched
  team/                the shared application tracker (Supabase + Vercel)
  private/             your plan, answers, application tracker, team.env and run logs; gitignored
```

`private/` holds personal material, is ignored by git, and is not served by
`scripts/serve.py`. This repo is public.

## Keeping it current

Programs change every cycle. When a date passes or a new round opens, edit
`programs.json` (each entry links its source), update `checked`, and run with
`--render`. Statuses as of 7 October 2026:

- Rakuten's 2027 intake and LY Corp's 2027 intake are closed.
- Preferred Networks' 2027 round opened in late November 2025; check its 2028 call.
- Sony's main global-hiring round opened around December, with a February
  deadline, in past years.
- Fast Retailing's 2026 Global Management Program closed on 20 Feb 2026.
- Woven by Toyota's 2026 internships have passed; watch for 2027.

## Sources

- Rakuten 2028 engineer positions and language per role: https://www.i-note.jp/rakuten-tech-entry/2028joiners/positionlist-en/fulltime.html
- Rakuten engineer intake and dates: https://global.rakuten.com/corp/careers/graduates/recruit_engineer/
- Rakuten business course: https://global.rakuten.com/corp/careers/graduates/recruit_business/business.html
- Mercari new graduates: https://careers.mercari.com/en/new-graduates/
- GS-JTI: https://gs-jti.go.jp/foreign-talent/
- HENNGE GIP: https://recruit.hennge.com/en/gip/
- LY Corp new grads: https://www.lycorp.co.jp/en/recruit/newgrads
- Money Forward students: https://recruit.moneyforward.com/students/
- Preferred Networks 2027 pre-entry: https://www.preferred.jp/en/news/2027-newgrad-preentry
- Sony Japan careers: https://sonyglobal.wd1.myworkdayjobs.com/SonyJapanCareers
- ASIA to JAPAN: https://asiatojapan.com/en
- Tech Japan: https://www.techjapan.work/
- Cognavi offers, April 2026: https://www.tribuneindia.com/news/himachal/iit-mandi-students-secure-packages-up-to-rs-56-lakh-per-annum-in-japan/
- JETRO Japan Career Day 2026: https://j-net21.smrj.go.jp/snavi2/articles/185617
- Fast Retailing careers: https://www.fastretailing.com/employment/en/
- Japan Dev English-only companies: https://japan-dev.com/companies/tags/english-only
- Work visa: https://www.moj.go.jp/isa/applications/status/gijinkoku?lang=en
- J-Find criteria: https://japan-visa.com/visas/j-find
