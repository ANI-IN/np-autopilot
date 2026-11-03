-- Roll back 0033. Pending claim / update proposals are rejected first (the old
-- action list does not know them); person_accounts rows made by sign-in or a
-- claim stay (they are links, written through the 0030 table).
drop function if exists kb.apply_claim(uuid);
drop function if exists kb.claim_person(uuid, text);
drop function if exists kb.link_me();
drop function if exists kb.person_candidates_for_me();
drop function if exists kb.auto_link_person(uuid);
drop function if exists kb.person_name_of(uuid);
drop function if exists kb.person_name_key(text);

create or replace function kb.profile_links_person() returns trigger
language plpgsql security definer set search_path = pg_catalog, public
as $$
declare r record;
begin
    for r in update kb.person_accounts set user_id = new.user_id, linked_at = now(), updated_at = now()
             where lower(email) = lower(new.email) and user_id is distinct from new.user_id
             returning node_id
    loop
        perform kb.apply_person_owner(r.node_id);
    end loop;
    return null;
end;
$$;

drop policy person_accounts_select on kb.person_accounts;
create policy person_accounts_select on kb.person_accounts for select to authenticated
    using ((select kb.role_at_least('editor')) or user_id = (select auth.uid()));
alter table kb.person_accounts drop constraint linked_by_known, drop column linked_by;

drop trigger if exists nodes_guard_contributor on kb.nodes;
drop trigger if exists edges_guard_contributor on kb.edges;
drop trigger if exists resources_guard_contributor on kb.resources;
drop trigger if exists node_resources_guard_contributor on kb.node_resources;
drop function if exists kb.guard_contributor();

update kb.proposals set status = 'rejected', decided_at = now()
 where action in ('update', 'claim') and status = 'pending';
alter table kb.proposals drop constraint action_known;
-- Decided update / claim rows cannot satisfy the old list: they are kept by
-- widening it no further than needed (NOT VALID keeps history, checks new rows).
alter table kb.proposals add constraint action_known
    check (action in ('archive', 'delete', 'create', 'type_change')) not valid;

alter table kb.sync_runs drop column resume;

drop function if exists kb.landing_stats();

-- A field is never removed (kb.check_type_def): the slug field is ARCHIVED, and
-- the domains keep their values (0033 up brings the field back as it was).
update kb.node_types
   set fields = (select jsonb_agg(case when f ->> 'key' = 'slug' then f || '{"archived": true}'::jsonb else f end)
                   from jsonb_array_elements(fields) f)
 where key = 'domain'
   and exists (select 1 from jsonb_array_elements(fields) f where f ->> 'key' = 'slug');
