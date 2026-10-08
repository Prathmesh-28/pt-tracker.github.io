-- Japan applications team tracker.
--
-- A group of friends applies to jobs in Japan on the owner's behalf. Every job has at
-- most one application row (the primary key), and every change goes through the
-- functions below, so two people can never apply to the same job: the second claim
-- fails inside the database, whatever the browsers show.
--
-- Everything is prefixed japan_ so this can live in a project that hosts other apps.

-- ------------------------------------------------------------------ settings

create table if not exists public.japan_settings (
  key text primary key,
  value text not null
);

-- owner_email: the account that becomes the owner when it joins. Set it before anyone joins:
--   update public.japan_settings set value = 'you@example.com' where key = 'owner_email';
-- claim_hours: a claim nobody turns into an application within this many hours can be taken over.
insert into public.japan_settings (key, value) values
  ('owner_email', 'set-me@example.com'),
  ('claim_hours', '48')
on conflict (key) do nothing;

-- ------------------------------------------------------------------ tables

create table if not exists public.japan_members (
  user_id uuid primary key references auth.users (id) on delete cascade,
  email text not null unique,
  name text not null default '',
  role text not null default 'helper' check (role in ('owner', 'helper')),
  approved boolean not null default false,
  created_at timestamptz not null default now()
);

create table if not exists public.japan_resumes (
  id uuid primary key default gen_random_uuid(),
  label text not null,
  file_path text not null unique,            -- object path in the private japan-resumes bucket
  file_name text not null default '',
  notes text not null default '',
  active boolean not null default true,
  uploaded_by uuid references auth.users (id) on delete set null default auth.uid(),
  created_at timestamptz not null default now()
);

create table if not exists public.japan_jobs (
  key text primary key,
  kind text not null default 'role' check (kind in ('role', 'program', 'manual')),
  company text not null,
  title text not null,
  location text not null default '',
  url text not null default '',
  source text not null default '',
  via text not null default '',
  level text not null default '',
  min_years int,
  language text not null default '',
  visa text not null default '',
  residency boolean not null default false,
  grad_2027 text not null default '',
  eligibility text not null default '',
  deadline date,
  track text not null default '',
  posted date,
  is_open boolean not null default true,       -- false once the posting leaves every source
  priority boolean not null default false,     -- the owner's picks
  do_not_apply boolean not null default false, -- the owner's vetoes
  owner_note text not null default '',
  added_by uuid references auth.users (id) on delete set null,
  synced_at timestamptz not null default now()
);
create index if not exists japan_jobs_company_idx on public.japan_jobs (lower(company));

create table if not exists public.japan_applications (
  job_key text primary key references public.japan_jobs (key) on delete cascade,
  status text not null check (status in ('claimed', 'applied', 'interview', 'offer', 'rejected', 'withdrawn', 'skipped')),
  claimed_by uuid references auth.users (id) on delete set null,
  claimed_at timestamptz,
  applied_by uuid references auth.users (id) on delete set null,
  applied_at timestamptz,
  resume_id uuid references public.japan_resumes (id) on delete set null,
  applied_with text not null default '',       -- which email or account the application used
  note text not null default '',
  updated_at timestamptz not null default now()
);

create table if not exists public.japan_events (
  id bigint generated always as identity primary key,
  job_key text references public.japan_jobs (key) on delete cascade,
  actor uuid references auth.users (id) on delete set null,
  action text not null,
  detail text not null default '',
  at timestamptz not null default now()
);
create index if not exists japan_events_job_idx on public.japan_events (job_key, at desc);
create index if not exists japan_events_at_idx on public.japan_events (at desc);

-- ------------------------------------------------------------------ who may do what

-- Table access for signed-in users; the row-level policies below narrow it. Anonymous
-- visitors get nothing. The service role (the sync script) gets everything.
grant select on public.japan_settings, public.japan_members, public.japan_resumes,
                public.japan_jobs, public.japan_applications, public.japan_events to authenticated;
grant update on public.japan_settings, public.japan_members, public.japan_jobs to authenticated;
grant delete on public.japan_members to authenticated;
grant insert, update, delete on public.japan_resumes to authenticated;
grant all on public.japan_settings, public.japan_members, public.japan_resumes,
             public.japan_jobs, public.japan_applications, public.japan_events to service_role;
grant usage, select on sequence public.japan_events_id_seq to service_role;
revoke all on public.japan_settings, public.japan_members, public.japan_resumes,
              public.japan_jobs, public.japan_applications, public.japan_events from anon;

create or replace function public.japan_is_member() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.japan_members where user_id = auth.uid() and approved)
$$;

create or replace function public.japan_is_owner() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.japan_members where user_id = auth.uid() and approved and role = 'owner')
$$;

alter table public.japan_settings enable row level security;
alter table public.japan_members enable row level security;
alter table public.japan_resumes enable row level security;
alter table public.japan_jobs enable row level security;
alter table public.japan_applications enable row level security;
alter table public.japan_events enable row level security;

drop policy if exists "japan: members read settings" on public.japan_settings;
create policy "japan: members read settings" on public.japan_settings for select using (public.japan_is_member());
drop policy if exists "japan: owner edits settings" on public.japan_settings;
create policy "japan: owner edits settings" on public.japan_settings for update
  using (public.japan_is_owner()) with check (public.japan_is_owner());

-- Someone waiting for approval sees only their own row.
drop policy if exists "japan: read members" on public.japan_members;
create policy "japan: read members" on public.japan_members for select
  using (user_id = auth.uid() or public.japan_is_member());
drop policy if exists "japan: owner edits members" on public.japan_members;
create policy "japan: owner edits members" on public.japan_members for update
  using (public.japan_is_owner()) with check (public.japan_is_owner());
drop policy if exists "japan: owner removes members" on public.japan_members;
create policy "japan: owner removes members" on public.japan_members for delete
  using (public.japan_is_owner() and user_id <> auth.uid());

drop policy if exists "japan: members read resumes" on public.japan_resumes;
create policy "japan: members read resumes" on public.japan_resumes for select using (public.japan_is_member());
drop policy if exists "japan: owner adds resumes" on public.japan_resumes;
create policy "japan: owner adds resumes" on public.japan_resumes for insert with check (public.japan_is_owner());
drop policy if exists "japan: owner edits resumes" on public.japan_resumes;
create policy "japan: owner edits resumes" on public.japan_resumes for update
  using (public.japan_is_owner()) with check (public.japan_is_owner());
drop policy if exists "japan: owner deletes resumes" on public.japan_resumes;
create policy "japan: owner deletes resumes" on public.japan_resumes for delete using (public.japan_is_owner());

drop policy if exists "japan: members read jobs" on public.japan_jobs;
create policy "japan: members read jobs" on public.japan_jobs for select using (public.japan_is_member());
drop policy if exists "japan: owner edits jobs" on public.japan_jobs;
create policy "japan: owner edits jobs" on public.japan_jobs for update
  using (public.japan_is_owner()) with check (public.japan_is_owner());

-- Applications and events change only through the functions below; there are no write policies.
drop policy if exists "japan: members read applications" on public.japan_applications;
create policy "japan: members read applications" on public.japan_applications for select using (public.japan_is_member());
drop policy if exists "japan: members read events" on public.japan_events;
create policy "japan: members read events" on public.japan_events for select using (public.japan_is_member());

-- ------------------------------------------------------------------ joining

-- Called once after signing in. The owner's email is approved as owner; everyone else
-- waits for the owner to approve them.
create or replace function public.japan_join(p_name text default '') returns public.japan_members
language plpgsql security definer set search_path = public as $$
declare
  m public.japan_members;
  me text := lower(coalesce(auth.jwt() ->> 'email', ''));
  owner text := lower((select value from public.japan_settings where key = 'owner_email'));
begin
  if auth.uid() is null then raise exception 'Sign in first'; end if;
  insert into public.japan_members (user_id, email, name, role, approved)
  values (auth.uid(), me, coalesce(nullif(trim(p_name), ''), split_part(me, '@', 1)),
          case when me = owner then 'owner' else 'helper' end, me = owner)
  on conflict (user_id) do update set name = coalesce(nullif(trim(p_name), ''), public.japan_members.name)
  returning * into m;
  return m;
end $$;

-- ------------------------------------------------------------------ the workflow

create or replace function public._japan_who(p_user uuid) returns text
language sql stable security definer set search_path = public as $$
  select coalesce((select coalesce(nullif(name, ''), email) from public.japan_members where user_id = p_user), 'someone')
$$;

-- Claim a job before applying, so nobody else starts on it. Atomic: of two people
-- claiming at the same moment, exactly one succeeds.
create or replace function public.japan_claim(p_job text) returns public.japan_applications
language plpgsql security definer set search_path = public as $$
declare
  a public.japan_applications;
  hours int := coalesce((select value::int from public.japan_settings where key = 'claim_hours'), 48);
begin
  if not public.japan_is_member() then raise exception 'Not an approved member'; end if;
  if not exists (select 1 from public.japan_jobs where key = p_job) then raise exception 'No such job'; end if;
  if exists (select 1 from public.japan_jobs where key = p_job and do_not_apply) then
    raise exception 'The owner marked this job "do not apply"';
  end if;
  -- A claim that was never turned into an application expires.
  delete from public.japan_applications
   where job_key = p_job and status = 'claimed' and claimed_at < now() - make_interval(hours => hours);
  insert into public.japan_applications (job_key, status, claimed_by, claimed_at)
  values (p_job, 'claimed', auth.uid(), now())
  on conflict (job_key) do nothing
  returning * into a;
  if a.job_key is null then
    select * into a from public.japan_applications where job_key = p_job;
    raise exception 'Already % by %', a.status, public._japan_who(coalesce(a.applied_by, a.claimed_by));
  end if;
  insert into public.japan_events (job_key, actor, action) values (p_job, auth.uid(), 'claimed');
  return a;
end $$;

-- Record the application: which resume, which email or account, any note.
create or replace function public.japan_apply(p_job text, p_resume uuid, p_with text default '', p_note text default '')
returns public.japan_applications
language plpgsql security definer set search_path = public as $$
declare a public.japan_applications;
begin
  if not public.japan_is_member() then raise exception 'Not an approved member'; end if;
  if p_resume is null or not exists (select 1 from public.japan_resumes where id = p_resume and active) then
    raise exception 'Pick one of the active resumes';
  end if;
  select * into a from public.japan_applications where job_key = p_job for update;
  if a.job_key is null then
    a := public.japan_claim(p_job);  -- claim and apply in one step
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

-- Move an application on: interview, offer, rejected, withdrawn; or skip a job as not a fit.
create or replace function public.japan_set_status(p_job text, p_status text, p_note text default '')
returns public.japan_applications
language plpgsql security definer set search_path = public as $$
declare a public.japan_applications;
begin
  if not public.japan_is_member() then raise exception 'Not an approved member'; end if;
  if p_status not in ('interview', 'offer', 'rejected', 'withdrawn', 'skipped') then
    raise exception 'Unknown status %', p_status;
  end if;
  select * into a from public.japan_applications where job_key = p_job for update;
  if a.job_key is null then
    if p_status <> 'skipped' then raise exception 'Apply before moving it on'; end if;
    insert into public.japan_applications (job_key, status, claimed_by, claimed_at)
    values (p_job, 'skipped', auth.uid(), now())
    on conflict (job_key) do nothing
    returning * into a;
    if a.job_key is null then raise exception 'Someone just took this job'; end if;
  else
    if not public.japan_is_owner() and auth.uid() is distinct from coalesce(a.applied_by, a.claimed_by) then
      raise exception 'Only % or the owner can change this', public._japan_who(coalesce(a.applied_by, a.claimed_by));
    end if;
    if p_status = 'skipped' and a.status not in ('claimed', 'skipped') then
      raise exception 'Already applied; use withdrawn instead';
    end if;
    if p_status <> 'skipped' and a.status in ('claimed', 'skipped') then
      raise exception 'Apply before moving it on';
    end if;
    update public.japan_applications
       set status = p_status, note = coalesce(nullif(p_note, ''), note), updated_at = now()
     where job_key = p_job
    returning * into a;
  end if;
  insert into public.japan_events (job_key, actor, action, detail) values (p_job, auth.uid(), p_status, coalesce(p_note, ''));
  return a;
end $$;

-- Give a claim back, or undo a skip. The owner can also reset an application completely.
create or replace function public.japan_release(p_job text) returns void
language plpgsql security definer set search_path = public as $$
declare a public.japan_applications;
begin
  if not public.japan_is_member() then raise exception 'Not an approved member'; end if;
  select * into a from public.japan_applications where job_key = p_job for update;
  if a.job_key is null then return; end if;
  if public.japan_is_owner() then
    delete from public.japan_applications where job_key = p_job;
    insert into public.japan_events (job_key, actor, action, detail) values (p_job, auth.uid(), 'reset', a.status);
    return;
  end if;
  if a.status not in ('claimed', 'skipped') then raise exception 'Only the owner can undo an application'; end if;
  if a.claimed_by is distinct from auth.uid() then raise exception 'Claimed by %', public._japan_who(a.claimed_by); end if;
  delete from public.japan_applications where job_key = p_job;
  insert into public.japan_events (job_key, actor, action) values (p_job, auth.uid(), 'released');
end $$;

-- A comment on a job, for the group.
create or replace function public.japan_note(p_job text, p_text text) returns void
language plpgsql security definer set search_path = public as $$
begin
  if not public.japan_is_member() then raise exception 'Not an approved member'; end if;
  if coalesce(trim(p_text), '') = '' then raise exception 'Empty note'; end if;
  insert into public.japan_events (job_key, actor, action, detail) values (p_job, auth.uid(), 'note', trim(p_text));
end $$;

-- A job someone found elsewhere. Matching company and title, or the same link, is the same job.
create or replace function public.japan_add_job(p_company text, p_title text, p_url text,
                                               p_location text default '', p_note text default '')
returns public.japan_jobs
language plpgsql security definer set search_path = public as $$
declare j public.japan_jobs;
begin
  if not public.japan_is_member() then raise exception 'Not an approved member'; end if;
  if coalesce(trim(p_company), '') = '' or coalesce(trim(p_title), '') = '' then
    raise exception 'Company and title are needed';
  end if;
  select * into j from public.japan_jobs
   where (lower(company) = lower(trim(p_company)) and lower(title) = lower(trim(p_title)))
      or (coalesce(trim(p_url), '') <> '' and url = trim(p_url))
   limit 1;
  if j.key is not null then raise exception 'Already listed: % at %', j.title, j.company; end if;
  insert into public.japan_jobs (key, kind, company, title, url, location, source, added_by, owner_note)
  values ('manual:' || md5(lower(trim(p_company)) || '|' || lower(trim(p_title)) || '|' || coalesce(trim(p_url), '')),
          'manual', trim(p_company), trim(p_title), coalesce(trim(p_url), ''), coalesce(trim(p_location), ''),
          'manual', auth.uid(), coalesce(p_note, ''))
  returning * into j;
  insert into public.japan_events (job_key, actor, action, detail) values (j.key, auth.uid(), 'added', coalesce(p_note, ''));
  return j;
end $$;

-- Everyone may call these; each checks membership itself.
revoke all on function public.japan_join(text) from public, anon;
revoke all on function public.japan_claim(text) from public, anon;
revoke all on function public.japan_apply(text, uuid, text, text) from public, anon;
revoke all on function public.japan_set_status(text, text, text) from public, anon;
revoke all on function public.japan_release(text) from public, anon;
revoke all on function public.japan_note(text, text) from public, anon;
revoke all on function public.japan_add_job(text, text, text, text, text) from public, anon;
revoke all on function public._japan_who(uuid) from public, anon;
grant execute on function public.japan_join(text) to authenticated;
grant execute on function public.japan_claim(text) to authenticated;
grant execute on function public.japan_apply(text, uuid, text, text) to authenticated;
grant execute on function public.japan_set_status(text, text, text) to authenticated;
grant execute on function public.japan_release(text) to authenticated;
grant execute on function public.japan_note(text, text) to authenticated;
grant execute on function public.japan_add_job(text, text, text, text, text) to authenticated;

-- ------------------------------------------------------------------ live updates

do $$
begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
    if not exists (select 1 from pg_publication_tables where pubname = 'supabase_realtime' and tablename = 'japan_applications') then
      alter publication supabase_realtime add table public.japan_applications;
    end if;
    if not exists (select 1 from pg_publication_tables where pubname = 'supabase_realtime' and tablename = 'japan_events') then
      alter publication supabase_realtime add table public.japan_events;
    end if;
  end if;
end $$;

-- ------------------------------------------------------------------ resume files

insert into storage.buckets (id, name, public) values ('japan-resumes', 'japan-resumes', false)
on conflict (id) do nothing;

drop policy if exists "japan: members download resumes" on storage.objects;
create policy "japan: members download resumes" on storage.objects for select
  using (bucket_id = 'japan-resumes' and public.japan_is_member());
drop policy if exists "japan: owner uploads resumes" on storage.objects;
create policy "japan: owner uploads resumes" on storage.objects for insert
  with check (bucket_id = 'japan-resumes' and public.japan_is_owner());
drop policy if exists "japan: owner replaces resumes" on storage.objects;
create policy "japan: owner replaces resumes" on storage.objects for update
  using (bucket_id = 'japan-resumes' and public.japan_is_owner());
drop policy if exists "japan: owner deletes resumes" on storage.objects;
create policy "japan: owner deletes resumes" on storage.objects for delete
  using (bucket_id = 'japan-resumes' and public.japan_is_owner());
