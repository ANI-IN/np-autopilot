-- Roll back 0029. Refuses while data depends on it: unreviewed or merged
-- relationship types, or saved graph positions (drop them deliberately first).
do $$
begin
    if exists (select 1 from kb.edge_types where review_status <> 'reviewed' or merged_into is not null) then
        raise exception '0029 down: relationship types are unreviewed or merged; review them first';
    end if;
    if exists (select 1 from kb.graph_positions) then
        raise exception '0029 down: kb.graph_positions holds saved layouts; delete them first';
    end if;
end $$;

drop table kb.graph_positions;
drop function if exists kb.actor_emails(uuid[]);

drop policy edge_type_rules_editor_insert on kb.edge_type_rules;
drop policy edge_type_rules_admin on kb.edge_type_rules;
create policy edge_type_rules_admin on kb.edge_type_rules for all to authenticated
    using ((select kb.role_at_least('admin'))) with check ((select kb.role_at_least('admin')));
drop policy edge_types_editor_insert on kb.edge_types;
drop policy edge_types_admin on kb.edge_types;
create policy edge_types_admin on kb.edge_types for all to authenticated
    using ((select kb.role_at_least('admin'))) with check ((select kb.role_at_least('admin')));
drop trigger edge_types_check_name on kb.edge_types;
drop function kb.check_edge_type_name();
drop function kb.rel_stem(text);
alter table kb.edge_types drop constraint review_status_known, drop column merged_into, drop column review_status;

do $$
begin
    if exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
        if exists (select 1 from pg_publication_tables where pubname = 'supabase_realtime'
                   and schemaname = 'kb' and tablename = 'changes') then
            execute 'alter publication supabase_realtime drop table kb.changes';
        end if;
        if not exists (select 1 from pg_publication_tables where pubname = 'supabase_realtime'
                       and schemaname = 'kb' and tablename = 'audit_log') then
            execute 'alter publication supabase_realtime add table kb.audit_log';
        end if;
    end if;
end $$;

create or replace function kb.audit() returns trigger
language plpgsql security definer set search_path = pg_catalog, public
as $$
declare
    b jsonb := case when tg_op in ('UPDATE', 'DELETE') then to_jsonb(old) end;
    a jsonb := case when tg_op in ('INSERT', 'UPDATE') then to_jsonb(new) end;
    rid uuid;
begin
    if tg_table_name = 'api_tokens' then
        b := b - 'token_hash'; a := a - 'token_hash';
    end if;
    b := b - 'search'; a := a - 'search';
    rid := coalesce(a ->> 'id', b ->> 'id', a ->> 'user_id', b ->> 'user_id', a ->> 'node_id', b ->> 'node_id')::uuid;
    insert into kb.audit_log (actor_id, actor_type, table_name, row_id, action, before, after)
    values (kb.actor_id(), kb.actor_type(), tg_table_name, rid, lower(tg_op), b, a);
    return null;
end;
$$;
drop table kb.changes;

drop index if exists kb.audit_log_edges_src_idx;
drop index if exists kb.audit_log_edges_tgt_idx;
drop index if exists kb.audit_log_link_node_idx;
drop index if exists kb.audit_log_link_res_idx;
drop index if exists kb.audit_log_actor_idx;
drop index if exists kb.audit_log_table_idx;
drop function kb.record_history(uuid, integer);

drop policy audit_log_select on kb.audit_log;
create policy audit_log_select on kb.audit_log for select to authenticated
    using ((select kb.role_at_least('viewer'))
           and (table_name <> 'api_tokens' or (select kb.role_at_least('admin'))
                or actor_id = (select auth.uid())));
drop function kb.my_scope_ids();

drop trigger audit_log_immutable on kb.audit_log;
drop function kb.audit_immutable();

-- 'system' rows written since 0029 stay 'system' (truthful); the function
-- returns to its 0022 default.
create or replace function kb.actor_type() returns text
language sql stable set search_path = pg_catalog
as $$
    select case coalesce(nullif(current_setting('kb.actor_type', true), ''), 'human')
             when 'ai' then 'ai' when 'import' then 'import'
             when 'system' then 'system' else 'human' end
$$;
