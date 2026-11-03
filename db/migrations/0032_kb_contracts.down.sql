-- Roll back 0032: the change-only triggers, the kind/node_ids columns (the 0029
-- audit function comes back), the edge and node type style columns.
drop trigger if exists graph_positions_changes_ins on kb.graph_positions;
drop trigger if exists graph_positions_changes_upd on kb.graph_positions;
drop trigger if exists graph_positions_changes_del on kb.graph_positions;
drop trigger if exists person_accounts_changes_ins on kb.person_accounts;
drop trigger if exists person_accounts_changes_upd on kb.person_accounts;
drop trigger if exists person_accounts_changes_del on kb.person_accounts;
drop trigger if exists sync_runs_changes_upd on kb.sync_runs;
drop function if exists kb.change_only();

-- Change-only events have no audit row; they go with the columns that describe them.
delete from kb.changes c where not exists (select 1 from kb.audit_log l where l.id = c.id);

create or replace function kb.audit() returns trigger
language plpgsql security definer set search_path = pg_catalog, public
as $$
declare
    b jsonb := case when tg_op in ('UPDATE', 'DELETE') then to_jsonb(old) end;
    a jsonb := case when tg_op in ('INSERT', 'UPDATE') then to_jsonb(new) end;
    rid uuid;
    aid bigint;
begin
    if tg_table_name = 'api_tokens' then
        b := b - 'token_hash'; a := a - 'token_hash';
    end if;
    b := b - 'search'; a := a - 'search';
    rid := coalesce(a ->> 'id', b ->> 'id', a ->> 'user_id', b ->> 'user_id', a ->> 'node_id', b ->> 'node_id')::uuid;
    insert into kb.audit_log (actor_id, actor_type, table_name, row_id, action, before, after)
    values (kb.actor_id(), kb.actor_type(), tg_table_name, rid, lower(tg_op), b, a)
    returning id into aid;
    insert into kb.changes (id, actor_id, actor_type, table_name, row_id, action, version)
    values (aid, kb.actor_id(), kb.actor_type(), tg_table_name, rid, lower(tg_op),
            coalesce(a ->> 'version', b ->> 'version'));
    return null;
end;
$$;

drop function if exists kb.change_node_ids(text, jsonb, jsonb);
drop function if exists kb.change_kind(text, text, jsonb, jsonb);
alter table kb.changes drop column node_ids, drop column kind;

alter table kb.edge_types drop constraint color_shape, drop constraint line_style_known,
    drop column line_style, drop column color;
alter table kb.node_types drop constraint shape_known, drop column owner_expected, drop column shape;
