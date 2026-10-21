-- Prathmesh's Overseas list: entry-level business roles outside India and Japan whose postings say they
-- sponsor a work visa (Overseas/fetch_overseas.py; sync_jobs.py --overseas sends them). Rows of japan_jobs
-- with kind 'overseas', so other syncs never close them and the site shows them in their own tab.
alter table public.japan_jobs drop constraint if exists japan_jobs_kind_check;
alter table public.japan_jobs add constraint japan_jobs_kind_check
  check (kind in ('role', 'program', 'manual', 'competition', 'india', 'overseas'));
