-- 0033 (run 6, B1): data flow and people.
--   1. domain records carry the mastersheet's slug (the NP Autopilot map codes
--      current domains by it: SD1..SD4), a field the sync fills
--   2. kb.landing_stats(): the landing page's numbers from kb, counts only
--   3. kb.sync_runs.resume: a time-boxed sync saves where it stopped
--   4. proposals: 'update' (a contributor's field edit) and 'claim' ("this
--      profile is me"), both decided in Approvals
--   5. contributors: field edits, archives and type changes go to Approvals,
--      enforced here (links and relationships stay direct)
--   6. person_accounts: e-mail addresses are shown to admins only (and to the
--      person themself); how a link was made; automatic linking on sign-in by
--      e-mail, else by an unambiguous name; claims
-- Additive and reversible (0033 down).

-- 1 ------------------------------------------------------------------------
update kb.node_types
   set fields = fields || jsonb_build_array(jsonb_build_object(
        'key', 'slug', 'label', 'Slug', 'kind', 'short_text', 'required', false, 'archived', false,
        'help', 'The short identifier of a current domain in the mastersheet (the NP Autopilot map codes domains by it).'))
 where key = 'domain'
   and not exists (select 1 from jsonb_array_elements(fields) f where f ->> 'key' = 'slug');
-- After a rollback (which archives the field and keeps the values), bring it back.
update kb.node_types
   set fields = (select jsonb_agg(case when f ->> 'key' = 'slug' then f || '{"archived": false}'::jsonb else f end)
                   from jsonb_array_elements(fields) f)
 where key = 'domain'
   and exists (select 1 from jsonb_array_elements(fields) f where f ->> 'key' = 'slug' and (f ->> 'archived')::boolean);

-- 2 ------------------------------------------------------------------------
-- The landing page shows these numbers before anyone signs in (as the static
-- public/stats.json always has): aggregate counts only, no row content.
create or replace function kb.landing_stats() returns jsonb
language sql stable security definer set search_path = pg_catalog, public
as $$
    select jsonb_build_object(
        'source', 'kb',
        'nodes', (select count(*) from kb.nodes where archived_at is null),
        'edges', (select count(*) from kb.edges e where e.archived_at is null),
        -- "corpus files": the files records cite (the sync's "Source" links)
        'files', (select count(distinct nr.resource_id) from kb.node_resources nr
                    join kb.resources r on r.id = nr.resource_id
                   where nr.note = 'Source' and nr.archived_at is null and r.archived_at is null),
        'links', (select count(*) from kb.resources where archived_at is null),
        'by_type', coalesce((select jsonb_object_agg(k, c) from (
                    select t.key as k, count(*) as c from kb.nodes n join kb.node_types t on t.id = n.type_id
                    where n.archived_at is null group by t.key) x), '{}'::jsonb),
        'built_as_of', (select to_char(max(finished_at) at time zone 'UTC', 'YYYY-MM-DD')
                          from kb.sync_runs where status = 'ok'),
        'head', (select coalesce(max(id), 0) from kb.changes))
$$;
revoke all on function kb.landing_stats() from public;
grant execute on function kb.landing_stats() to authenticated;

-- 3 ------------------------------------------------------------------------
alter table kb.sync_runs add column resume jsonb;
comment on column kb.sync_runs.resume is
    'Where a run that hit its time budget stopped (phase and last key); the next run continues from it.';

-- 4 ------------------------------------------------------------------------
alter table kb.proposals drop constraint action_known;
alter table kb.proposals add constraint action_known
    check (action in ('archive', 'delete', 'create', 'type_change', 'update', 'claim'));

-- 5 ------------------------------------------------------------------------
-- A contributor (the request role, never a SECURITY DEFINER function acting on
-- its behalf, nor the sync / import owner connections) may attach links and
-- relationships; it may not edit a record's fields, archive or restore
-- anything: those are proposals an editor approves.
create or replace function kb.guard_contributor() returns trigger
language plpgsql set search_path = pg_catalog, public
as $$
begin
    if current_user <> 'authenticated' or kb.role() <> 'contributor' then
        return new;
    end if;
    if tg_table_name = 'nodes' then
        raise exception 'contributors propose record changes; an editor approves them in Approvals'
            using errcode = 'insufficient_privilege', hint = 'kb_needs_approval';
    end if;
    if (old.archived_at is null) <> (new.archived_at is null) then
        raise exception 'contributors propose archiving; an editor approves it in Approvals'
            using errcode = 'insufficient_privilege', hint = 'kb_needs_approval';
    end if;
    return new;
end;
$$;
create trigger nodes_guard_contributor before update on kb.nodes
    for each row execute function kb.guard_contributor();
create trigger edges_guard_contributor before update on kb.edges
    for each row execute function kb.guard_contributor();
create trigger resources_guard_contributor before update on kb.resources
    for each row execute function kb.guard_contributor();
create trigger node_resources_guard_contributor before update on kb.node_resources
    for each row execute function kb.guard_contributor();

-- 6 ------------------------------------------------------------------------
alter table kb.person_accounts add column linked_by text,
    add constraint linked_by_known check (linked_by is null or linked_by in ('admin', 'csv', 'sign_in_email', 'sign_in_name', 'claim'));

drop policy person_accounts_select on kb.person_accounts;
create policy person_accounts_select on kb.person_accounts for select to authenticated
    using ((select kb.role_at_least('admin')) or user_id = (select auth.uid()));

-- The person records a signed-in account can be: live instructors and team members.
create or replace function kb.person_name_of(p_user uuid) returns text
language sql stable security definer set search_path = pg_catalog, public
as $$
    select kb.norm(coalesce(
        nullif(btrim(to_jsonb(u) -> 'raw_user_meta_data' ->> 'full_name'), ''),
        nullif(btrim(to_jsonb(u) -> 'raw_user_meta_data' ->> 'name'), ''),
        regexp_replace(split_part(u.email, '@', 1), '[._-]+', ' ', 'g')))
    from auth.users u where u.id = p_user
$$;
revoke all on function kb.person_name_of(uuid) from public, anon, authenticated;

-- Automatic linking for one account: its e-mail first (unique), else its name
-- when exactly ONE unlinked person record carries it. Two records with the
-- same name are never linked automatically ('ambiguous': the person claims the
-- right one and an admin approves). Returns what happened.
create or replace function kb.auto_link_person(p_user uuid) returns text
language plpgsql security definer set search_path = pg_catalog, public
as $$
declare
    mail text;
    nm text;
    hits uuid[];
begin
    if p_user is null then return 'none'; end if;
    if exists (select 1 from kb.person_accounts where user_id = p_user) then return 'already'; end if;
    select lower(btrim(email)) into mail from public.profiles where user_id = p_user;
    if mail is null then
        select lower(btrim(email)) into mail from auth.users where id = p_user;
    end if;
    if mail is null then return 'none'; end if;
    if exists (select 1 from kb.person_accounts where lower(email) = mail) then
        update kb.person_accounts set user_id = p_user, linked_at = now(), updated_at = now(),
               linked_by = coalesce(linked_by, 'sign_in_email')
         where lower(email) = mail and user_id is distinct from p_user;
        perform kb.apply_person_owner(node_id) from kb.person_accounts where user_id = p_user;
        return 'email';
    end if;
    nm := kb.person_name_of(p_user);
    if coalesce(nm, '') = '' then return 'none'; end if;
    select array_agg(n.id) into hits
      from kb.nodes n join kb.node_types t on t.id = n.type_id
     where t.key in ('instructor', 'team_member') and n.archived_at is null and n.name_norm = nm
       and not exists (select 1 from kb.person_accounts pa where pa.node_id = n.id);
    if hits is null then return 'none'; end if;
    if array_length(hits, 1) > 1 then return 'ambiguous'; end if;
    insert into kb.person_accounts (node_id, email, linked_by) values (hits[1], mail, 'sign_in_name');
    return 'name';
end;
$$;
revoke all on function kb.auto_link_person(uuid) from public, anon, authenticated;

-- The caller links themself (the KB app asks on load): only ever auth.uid().
create or replace function kb.link_me() returns text
language sql volatile security definer set search_path = pg_catalog, public
as $$ select kb.auto_link_person(auth.uid()) $$;
revoke all on function kb.link_me() from public, anon;
grant execute on function kb.link_me() to authenticated;

-- The person records that carry the caller's name and are not linked yet (for
-- "Is this you?" when the name is ambiguous). Names and ids only.
create or replace function kb.person_candidates_for_me() returns table (id uuid, name text, type text)
language sql stable security definer set search_path = pg_catalog, public
as $$
    select n.id, n.name, t.key
      from kb.nodes n join kb.node_types t on t.id = n.type_id
     where kb.role_at_least('viewer') and t.key in ('instructor', 'team_member') and n.archived_at is null
       and n.name_norm = kb.person_name_of(auth.uid())
       and not exists (select 1 from kb.person_accounts pa where pa.node_id = n.id and pa.user_id is not null)
     order by n.is_legacy, n.name
$$;
revoke all on function kb.person_candidates_for_me() from public, anon;
grant execute on function kb.person_candidates_for_me() to authenticated;

-- On sign-in (a profile row appears or changes e-mail): the 0030 e-mail link,
-- then the name step.
create or replace function kb.profile_links_person() returns trigger
language plpgsql security definer set search_path = pg_catalog, public
as $$
declare r record;
begin
    for r in update kb.person_accounts set user_id = new.user_id, linked_at = now(), updated_at = now(),
                    linked_by = coalesce(linked_by, 'sign_in_email')
             where lower(email) = lower(new.email) and user_id is distinct from new.user_id
             returning node_id
    loop
        perform kb.apply_person_owner(r.node_id);
    end loop;
    perform kb.auto_link_person(new.user_id);
    return null;
end;
$$;

-- A claim: "this person record is me". Recorded as a proposal by the claimant
-- (any member, viewers included); an admin approves it in Approvals. The
-- proposal holds no e-mail address (proposals are audited): the account's
-- address is read when the claim is applied.
create or replace function kb.claim_person(p_node uuid, p_reason text) returns uuid
language plpgsql volatile security definer set search_path = pg_catalog, public
as $$
declare pid uuid;
begin
    if auth.uid() is null or not kb.role_at_least('viewer') then
        raise exception 'sign in to claim a profile' using errcode = 'insufficient_privilege';
    end if;
    if not exists (select 1 from kb.nodes n join kb.node_types t on t.id = n.type_id
                    where n.id = p_node and t.key in ('instructor', 'team_member') and n.archived_at is null) then
        raise exception 'only a live instructor or team member record can be claimed'
            using errcode = 'check_violation', hint = 'kb_claim_target';
    end if;
    if exists (select 1 from kb.person_accounts where node_id = p_node and user_id is not null) then
        raise exception 'this profile is already linked to an account'
            using errcode = 'check_violation', hint = 'kb_claim_linked';
    end if;
    if exists (select 1 from kb.person_accounts where user_id = auth.uid()) then
        raise exception 'your account is already linked to a profile'
            using errcode = 'check_violation', hint = 'kb_claim_self_linked';
    end if;
    select id into pid from kb.proposals
     where action = 'claim' and target_id = p_node and created_by = auth.uid() and status = 'pending';
    if pid is not null then return pid; end if;
    insert into kb.proposals (action, target_table, target_id, reason, payload, actor_type, created_by)
    values ('claim', 'nodes', p_node, left(p_reason, 2000), jsonb_build_object('user_id', auth.uid()), 'human', auth.uid())
    returning id into pid;
    return pid;
end;
$$;
revoke all on function kb.claim_person(uuid, text) from public, anon;
grant execute on function kb.claim_person(uuid, text) to authenticated;

-- Applying an approved claim (an admin decides; the service calls this).
create or replace function kb.apply_claim(p_proposal uuid) returns uuid
language plpgsql volatile security definer set search_path = pg_catalog, public
as $$
declare p record; mail text;
begin
    if not kb.role_at_least('admin') then
        raise exception 'only an admin approves a claim' using errcode = 'insufficient_privilege';
    end if;
    select * into p from kb.proposals where id = p_proposal and action = 'claim';
    if p is null then raise exception 'no such claim' using errcode = 'no_data_found'; end if;
    select lower(btrim(email)) into mail from public.profiles where user_id = p.created_by;
    if mail is null then select lower(btrim(email)) into mail from auth.users where id = p.created_by; end if;
    if mail is null then
        raise exception 'the claiming account has no e-mail address' using errcode = 'check_violation';
    end if;
    insert into kb.person_accounts (node_id, email, linked_by) values (p.target_id, mail, 'claim')
    on conflict (node_id) do update set email = excluded.email, linked_by = 'claim';
    return p.target_id;
end;
$$;
revoke all on function kb.apply_claim(uuid) from public, anon;
grant execute on function kb.apply_claim(uuid) to authenticated;
