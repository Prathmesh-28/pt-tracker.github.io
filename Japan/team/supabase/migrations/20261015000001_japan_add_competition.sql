-- A competition found outside Unstop, added by hand: an IIT-only contest from a placement-cell mail,
-- a company's own challenge. The daily sync never closes these (it closes only comp:unstop:* rows);
-- the site treats one as closed once its deadline passes.
create or replace function public.japan_add_competition(p_title text, p_organiser text, p_url text default '',
                                                        p_deadline date default null, p_band int default 3,
                                                        p_note text default '', p_candidate text default 'prathmesh')
returns public.japan_jobs
language plpgsql security definer set search_path = public as $$
declare
  j public.japan_jobs;
  band int := least(greatest(coalesce(p_band, 3), 1), 5);
begin
  if not public.japan_is_member() then raise exception 'Not an approved member'; end if;
  if not exists (select 1 from public.japan_candidates where id = p_candidate) then raise exception 'No such person'; end if;
  if coalesce(trim(p_title), '') = '' or coalesce(trim(p_organiser), '') = '' then
    raise exception 'A name and an organiser are needed';
  end if;
  select * into j from public.japan_jobs
   where kind = 'competition'
     and ((lower(company) = lower(trim(p_organiser)) and lower(title) = lower(trim(p_title)))
          or (coalesce(trim(p_url), '') <> '' and url = trim(p_url)))
   limit 1;
  if j.key is not null then raise exception 'Already listed: % by %', j.title, j.company; end if;
  insert into public.japan_jobs (key, kind, candidate, company, title, url, source, via, deadline, grad_2027,
                                 track, added_by, owner_note, extra)
  values ('comp:manual:' || gen_random_uuid(), 'competition', p_candidate, trim(p_organiser), trim(p_title),
          coalesce(trim(p_url), ''), 'team', 'Added by the team', p_deadline, 'yes',
          (array['IIT only', 'Top-paying employer', 'Select campuses or strong pay', 'Big company, open to all',
                 'College fest or small organiser'])[band],
          auth.uid(), coalesce(trim(p_note), ''),
          jsonb_build_object('band', band, 'scope', case when band = 1 then 'iit_only' else 'open' end,
                             'why', 'Added by the team' || case when coalesce(trim(p_note), '') <> '' then ': ' || trim(p_note) else '' end))
  returning * into j;
  insert into public.japan_events (job_key, actor, action, detail) values (j.key, auth.uid(), 'added', coalesce(trim(p_note), ''));
  return j;
end $$;

revoke all on function public.japan_add_competition(text, text, text, date, int, text, text) from public, anon;
grant execute on function public.japan_add_competition(text, text, text, date, int, text, text) to authenticated;
