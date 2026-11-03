-- Roll back 0030. Refuses while data depends on it: legacy-archived records
-- (restore them first: python pipeline/kb_legacy.py restore), linked person
-- accounts, owners assigned by role, or sync history.
do $$
begin
    if exists (select 1 from kb.legacy_archive) then
        raise exception '0030 down: records are archived by the legacy step; restore them first (pipeline/kb_legacy.py restore)';
    end if;
    if exists (select 1 from kb.person_accounts) then
        raise exception '0030 down: person records are linked to accounts (kb.person_accounts); remove the links first';
    end if;
    if exists (select 1 from kb.nodes where owner_record_id is not null or co_owner_record_ids <> '{}' or is_legacy) then
        raise exception '0030 down: records carry owners-by-role or the legacy flag; clear them first';
    end if;
    if exists (select 1 from kb.sync_map) or exists (select 1 from kb.sync_runs) then
        raise exception '0030 down: the sync has state (kb.sync_map / kb.sync_runs); clear it first';
    end if;
end $$;

drop table kb.legacy_archive;
drop table kb.sync_runs;
drop table kb.sync_map;
drop trigger profiles_link_kb_person on public.profiles;
drop function kb.profile_links_person();
drop trigger person_accounts_apply on kb.person_accounts;
drop trigger person_accounts_resolve on kb.person_accounts;
drop function kb.person_accounts_apply();
drop function kb.person_accounts_resolve();
drop function kb.apply_person_owner(uuid);
drop table kb.person_accounts;
drop index if exists kb.nodes_co_owner_records_idx;
drop index if exists kb.nodes_owner_record_idx;
drop index if exists kb.nodes_live_current_idx;
alter table kb.nodes drop constraint owner_record_not_self,
    drop column co_owner_record_ids, drop column owner_record_id, drop column is_legacy;

create or replace function kb.actor_type() returns text
language sql stable set search_path = pg_catalog, public
as $$
    select case coalesce(nullif(current_setting('kb.actor_type', true), ''),
                         case when kb.actor_id() is null then 'system' else 'human' end)
             when 'ai' then 'ai' when 'import' then 'import'
             when 'system' then 'system' else 'human' end
$$;
