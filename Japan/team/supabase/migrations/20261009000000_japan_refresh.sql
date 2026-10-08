-- The site's Refresh button. The job searches run on the owner's Mac (Japan/daily.sh), so the
-- button only asks: it queues a refresh here, the Mac checks the queue every minute, runs the
-- same pipeline as the 8:00 IST schedule, and writes its progress back for the site to show.

-- When a job first reached the list, for the "New" badge and the count a refresh reports.
alter table public.japan_jobs add column if not exists created_at timestamptz not null default now();

create table if not exists public.japan_refreshes (
  id bigint generated always as identity primary key,
  trigger text not null default 'button' check (trigger in ('button', 'schedule')),
  requested_by uuid references auth.users (id) on delete set null,
  requested_at timestamptz not null default now(),
  status text not null default 'queued' check (status in ('queued', 'running', 'done', 'failed')),
  step text not null default '',
  syncs int not null default 0,              -- lists synced so far; the site reloads its jobs on each
  started_at timestamptz,
  updated_at timestamptz not null default now(),
  finished_at timestamptz,
  summary text not null default ''
);
-- At most one refresh waiting or running: a second press joins the first.
create unique index if not exists japan_refreshes_one_open on public.japan_refreshes ((true))
  where status in ('queued', 'running');
create index if not exists japan_refreshes_id_idx on public.japan_refreshes (id desc);

grant select on public.japan_refreshes to authenticated;
grant all on public.japan_refreshes to service_role;
grant usage, select on sequence public.japan_refreshes_id_seq to service_role;
revoke all on public.japan_refreshes from anon;
alter table public.japan_refreshes enable row level security;
drop policy if exists "japan: members read refreshes" on public.japan_refreshes;
create policy "japan: members read refreshes" on public.japan_refreshes for select using (public.japan_is_member());

create or replace function public.japan_request_refresh() returns public.japan_refreshes
language plpgsql security definer set search_path = public as $$
declare r public.japan_refreshes;
begin
  if not public.japan_is_member() then
    raise exception 'Only approved members can refresh the jobs';
  end if;
  -- A run that has said nothing for two hours stopped with the Mac; let a new one start.
  update public.japan_refreshes set status = 'failed', finished_at = now(), summary = 'Stopped without finishing'
   where status = 'running' and updated_at < now() - interval '2 hours';
  select * into r from public.japan_refreshes where status in ('queued', 'running') order by id desc limit 1;
  if found then
    return r;
  end if;
  -- Job boards block a searcher that comes back too often.
  select * into r from public.japan_refreshes
   where status = 'done' and finished_at > now() - interval '10 minutes' order by id desc limit 1;
  if found then
    raise exception 'The jobs were refreshed at % IST. You can refresh again from % IST.',
      to_char(r.finished_at at time zone 'Asia/Kolkata', 'HH24:MI'),
      to_char((r.finished_at + interval '10 minutes') at time zone 'Asia/Kolkata', 'HH24:MI');
  end if;
  begin
    insert into public.japan_refreshes (trigger, requested_by) values ('button', auth.uid()) returning * into r;
  exception when unique_violation then  -- someone pressed it at the same moment
    select * into r from public.japan_refreshes where status in ('queued', 'running') order by id desc limit 1;
  end;
  return r;
end $$;

revoke all on function public.japan_request_refresh() from public, anon;
grant execute on function public.japan_request_refresh() to authenticated;

do $$
begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
    if not exists (select 1 from pg_publication_tables where pubname = 'supabase_realtime' and tablename = 'japan_refreshes') then
      alter publication supabase_realtime add table public.japan_refreshes;
    end if;
  end if;
end $$;
