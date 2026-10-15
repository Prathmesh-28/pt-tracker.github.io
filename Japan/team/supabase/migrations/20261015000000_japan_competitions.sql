-- Case competitions, and other contests that lead to a PPI, PPO or internship, on Prathmesh's list
-- (CaseCompetitions/ pulls them from Unstop and ranks them; sync_jobs.py --competitions sends them).
-- They are rows of japan_jobs with kind 'competition', so claims, notes, history and live updates work
-- as they do for jobs. Registering for one needs no resume, so it has its own function.

alter table public.japan_jobs drop constraint if exists japan_jobs_kind_check;
alter table public.japan_jobs add constraint japan_jobs_kind_check
  check (kind in ('role', 'program', 'manual', 'competition'));

-- Record a registration: who registered, with which email or account, any note. Like japan_apply, a
-- competition nobody has claimed is claimed and registered in one step.
create or replace function public.japan_register(p_job text, p_with text default '', p_note text default '')
returns public.japan_applications
language plpgsql security definer set search_path = public as $$
declare a public.japan_applications;
begin
  if not public.japan_is_member() then raise exception 'Not an approved member'; end if;
  if not exists (select 1 from public.japan_jobs where key = p_job and kind = 'competition') then
    raise exception 'Only competitions are registered for; jobs are applied to with a resume';
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
     set status = 'applied', applied_by = auth.uid(), applied_at = now(), resume_id = null,
         applied_with = coalesce(p_with, ''), note = coalesce(nullif(p_note, ''), note), updated_at = now()
   where job_key = p_job
  returning * into a;
  insert into public.japan_events (job_key, actor, action, detail)
  values (p_job, auth.uid(), 'registered', coalesce(p_with, ''));
  return a;
end $$;

revoke all on function public.japan_register(text, text, text) from public, anon;
grant execute on function public.japan_register(text, text, text) to authenticated;
