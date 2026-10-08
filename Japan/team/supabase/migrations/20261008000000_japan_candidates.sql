-- The people the team applies for. Every job and every resume belongs to one of them,
-- so Prathmesh's search and Madhura's never mix: different jobs, different resumes,
-- and an application can only use a resume of the person the job is for.

create table if not exists public.japan_candidates (
  id text primary key check (id ~ '^[a-z0-9-]+$'),
  name text not null,
  notes text not null default '',
  lives_in_japan boolean not null default false,  -- "must live in Japan" is no obstacle for them
  sort int not null default 0,
  created_at timestamptz not null default now()
);

insert into public.japan_candidates (id, name, notes, lives_in_japan, sort) values
  ('prathmesh', 'Prathmesh', 'IIT Bombay, graduating 2027. English-only roles; applies from India, so needs visa sponsorship.', false, 1),
  ('madhura', 'Madhura', '', true, 2)  -- her details live in the database, not in this public repo
on conflict (id) do nothing;

alter table public.japan_jobs add column if not exists candidate text not null default 'prathmesh'
  references public.japan_candidates (id);
alter table public.japan_jobs add column if not exists extra jsonb not null default '{}'::jsonb;  -- per-person labels
alter table public.japan_resumes add column if not exists candidate text not null default 'prathmesh'
  references public.japan_candidates (id);
create index if not exists japan_jobs_candidate_idx on public.japan_jobs (candidate);
create index if not exists japan_resumes_candidate_idx on public.japan_resumes (candidate);

alter table public.japan_candidates enable row level security;
grant select, insert, update on public.japan_candidates to authenticated;
grant all on public.japan_candidates to service_role;
revoke all on public.japan_candidates from anon;
drop policy if exists "japan: members read candidates" on public.japan_candidates;
create policy "japan: members read candidates" on public.japan_candidates for select using (public.japan_is_member());
drop policy if exists "japan: owner adds candidates" on public.japan_candidates;
create policy "japan: owner adds candidates" on public.japan_candidates for insert with check (public.japan_is_owner());
drop policy if exists "japan: owner edits candidates" on public.japan_candidates;
create policy "japan: owner edits candidates" on public.japan_candidates for update
  using (public.japan_is_owner()) with check (public.japan_is_owner());

-- Applying now also checks the resume belongs to the person the job is for.
create or replace function public.japan_apply(p_job text, p_resume uuid, p_with text default '', p_note text default '')
returns public.japan_applications
language plpgsql security definer set search_path = public as $$
declare a public.japan_applications;
begin
  if not public.japan_is_member() then raise exception 'Not an approved member'; end if;
  if p_resume is null or not exists (
       select 1 from public.japan_resumes r join public.japan_jobs j on j.key = p_job
        where r.id = p_resume and r.active and r.candidate = j.candidate) then
    raise exception 'Pick one of this person''s active resumes';
  end if;
  select * into a from public.japan_applications where job_key = p_job for update;
  if a.job_key is null then
    a := public.japan_claim(p_job);
  end if;
  if a.status <> 'claimed' then
    raise exception 'Already % by %', a.status, public._japan_who(coalesce(a.applied_by, a.claimed_by));
  end if;
  if a.claimed_by is distinct from auth.uid() and not public.japan_is_owner() then
    raise exception 'Claimed by %', public._japan_who(a.claimed_by);
  end if;
  update public.japan_applications
     set status = 'applied', applied_by = auth.uid(), applied_at = now(), resume_id = p_resume,
         applied_with = coalesce(p_with, ''), note = coalesce(nullif(p_note, ''), note), updated_at = now()
   where job_key = p_job
  returning * into a;
  insert into public.japan_events (job_key, actor, action, detail)
  values (p_job, auth.uid(), 'applied', (select label from public.japan_resumes where id = p_resume));
  return a;
end $$;

-- Adding a job found elsewhere now says whose list it goes on.
drop function if exists public.japan_add_job(text, text, text, text, text);
create or replace function public.japan_add_job(p_company text, p_title text, p_url text,
                                               p_location text default '', p_note text default '',
                                               p_candidate text default 'prathmesh')
returns public.japan_jobs
language plpgsql security definer set search_path = public as $$
declare j public.japan_jobs;
begin
  if not public.japan_is_member() then raise exception 'Not an approved member'; end if;
  if not exists (select 1 from public.japan_candidates where id = p_candidate) then raise exception 'No such person'; end if;
  if coalesce(trim(p_company), '') = '' or coalesce(trim(p_title), '') = '' then
    raise exception 'Company and title are needed';
  end if;
  select * into j from public.japan_jobs
   where candidate = p_candidate
     and ((lower(company) = lower(trim(p_company)) and lower(title) = lower(trim(p_title)))
          or (coalesce(trim(p_url), '') <> '' and url = trim(p_url)))
   limit 1;
  if j.key is not null then raise exception 'Already listed: % at %', j.title, j.company; end if;
  insert into public.japan_jobs (key, kind, candidate, company, title, url, location, source, added_by, owner_note)
  values ('manual:' || p_candidate || ':' || md5(lower(trim(p_company)) || '|' || lower(trim(p_title)) || '|' || coalesce(trim(p_url), '')),
          'manual', p_candidate, trim(p_company), trim(p_title), coalesce(trim(p_url), ''), coalesce(trim(p_location), ''),
          'manual', auth.uid(), coalesce(p_note, ''))
  returning * into j;
  insert into public.japan_events (job_key, actor, action, detail) values (j.key, auth.uid(), 'added', coalesce(p_note, ''));
  return j;
end $$;
revoke all on function public.japan_add_job(text, text, text, text, text, text) from public, anon;
grant execute on function public.japan_add_job(text, text, text, text, text, text) to authenticated;
