-- Prathmesh's India list: entry-level product, analyst and graduate roles with what each pays
-- (India/fetch_india.py; sync_jobs.py --india sends them). Rows of japan_jobs with kind 'india', so a
-- job sync never closes them and the site shows them in their own tab; applying works as for any job.
alter table public.japan_jobs drop constraint if exists japan_jobs_kind_check;
alter table public.japan_jobs add constraint japan_jobs_kind_check
  check (kind in ('role', 'program', 'manual', 'competition', 'india'));
