-- 0032 (run 6, A3): the schema behind docs/CONTRACTS.md.
--   1. node_types.shape, node_types.owner_expected
--   2. edge_types.color, edge_types.line_style
--   3. kb.changes.kind, kb.changes.node_ids, derived by the audit trigger
--   4. change events (no audit row, no content) for graph_positions,
--      person_accounts and finished sync runs
-- Additive; 0032 down restores the 0029 audit function and drops the columns.

-- 1 ------------------------------------------------------------------------
alter table kb.node_types
    add column shape text,
    add column owner_expected boolean not null default false,
    add constraint shape_known check (shape is null or shape in
        ('round-rectangle', 'ellipse', 'diamond', 'hexagon', 'triangle', 'rectangle', 'tag', 'barrel'));

-- Built-in shapes: containers are rounded rectangles, people are circles.
update kb.node_types set shape = case key
        when 'program' then 'hexagon'
        when 'course' then 'round-rectangle'
        when 'domain' then 'diamond'
        when 'module' then 'round-rectangle'
        when 'week' then 'rectangle'
        when 'session' then 'barrel'
        when 'topic' then 'tag'
        when 'instructor' then 'ellipse'
        when 'team_member' then 'ellipse'
        when 'process' then 'triangle'
        when 'theme' then 'tag'
        else shape end
    where shape is null;
update kb.node_types set owner_expected = true
    where key in ('program', 'course', 'domain', 'module', 'session', 'week', 'link');

-- 2 ------------------------------------------------------------------------
alter table kb.edge_types
    add column color text,
    add column line_style text not null default 'solid',
    add constraint line_style_known check (line_style in ('solid', 'dashed', 'dotted')),
    add constraint color_shape check (color is null or color ~ '^#[0-9a-f]{6}$');

update kb.edge_types set color = case key
        when 'contains' then '#475569'
        when 'covers' then '#0e7490'
        when 'teaches' then '#be123c'
        when 'sme' then '#a16207'
        when 'owned_by' then '#1d4ed8'
        when 'supported_by' then '#0369a1'
        when 'delivered_by' then '#c2410c'
        when 'prerequisite' then '#b91c1c'
        when 'related' then '#4d7c0f'
        else color end,
    line_style = case key
        when 'sme' then 'dashed'
        when 'supported_by' then 'dashed'
        when 'related' then 'dotted'
        when 'prerequisite' then 'dashed'
        else line_style end;

-- 3 ------------------------------------------------------------------------
alter table kb.changes
    add column kind text,
    add column node_ids uuid[] not null default '{}';

create or replace function kb.change_kind(tbl text, op text, b jsonb, a jsonb) returns text
language plpgsql immutable set search_path = pg_catalog
as $$
declare
    noun text := case tbl
        when 'nodes' then 'record' when 'edges' then 'relationship'
        when 'edge_types' then 'reltype' when 'edge_type_rules' then 'reltype'
        when 'node_types' then 'type' when 'tags' then 'tag'
        when 'resources' then 'link' end;
    quiet text[] := array['version', 'updated_at', 'updated_by'];
    owner_cols text[] := array['owner_id', 'co_owners', 'owner_record_id', 'co_owner_record_ids'];
begin
    if tbl = 'node_tags' then
        return case op when 'insert' then 'tag.attach' when 'delete' then 'tag.detach' else 'tag.update' end;
    end if;
    if tbl = 'node_resources' then
        if op = 'insert' then return 'link.attach'; end if;
        if op = 'delete' then return 'link.detach'; end if;
        if (b ->> 'archived_at') is null and (a ->> 'archived_at') is not null then return 'link.detach'; end if;
        if (b ->> 'archived_at') is not null and (a ->> 'archived_at') is null then return 'link.attach'; end if;
        return 'link.update';
    end if;
    if noun is null then
        return tbl || '.' || op;
    end if;
    if tbl = 'edge_type_rules' then
        return 'reltype.update';
    end if;
    if op = 'insert' then return noun || '.create'; end if;
    if op = 'delete' then return noun || '.delete'; end if;
    if (b ->> 'archived_at') is null and (a ->> 'archived_at') is not null then return noun || '.archive'; end if;
    if (b ->> 'archived_at') is not null and (a ->> 'archived_at') is null then return noun || '.restore'; end if;
    if tbl = 'nodes'
       and (b - quiet - owner_cols) = (a - quiet - owner_cols)
       and (b - quiet) <> (a - quiet) then
        return 'record.owner';
    end if;
    return noun || '.update';
end;
$$;

create or replace function kb.change_node_ids(tbl text, b jsonb, a jsonb) returns uuid[]
language sql immutable set search_path = pg_catalog
as $$
    select coalesce(array_agg(distinct x::uuid) filter (where x is not null), '{}')
    from unnest(case
        when tbl = 'nodes' then array[coalesce(a ->> 'id', b ->> 'id')]
        when tbl = 'edges' then array[a ->> 'source_id', a ->> 'target_id', b ->> 'source_id', b ->> 'target_id']
        when tbl in ('node_tags', 'node_resources') then array[coalesce(a ->> 'node_id', b ->> 'node_id')]
        else array[]::text[] end) as x
$$;

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
    insert into kb.changes (id, actor_id, actor_type, table_name, row_id, action, version, kind, node_ids)
    values (aid, kb.actor_id(), kb.actor_type(), tg_table_name, rid, lower(tg_op),
            coalesce(a ->> 'version', b ->> 'version'),
            kb.change_kind(tg_table_name, lower(tg_op), b, a),
            kb.change_node_ids(tg_table_name, b, a));
    return null;
end;
$$;

-- Older rows: derive the kind from the audit log once (row content stays in the log).
update kb.changes c
   set kind = kb.change_kind(l.table_name, l.action, l.before - 'search', l.after - 'search'),
       node_ids = kb.change_node_ids(l.table_name, l.before, l.after)
  from kb.audit_log l
 where l.id = c.id and c.kind is null;

-- 4 ------------------------------------------------------------------------
-- A change event with no audit row: these tables are not audited (layout moves
-- would flood the log; person_accounts holds e-mail addresses, which must not be
-- copied into an append-only log). The id comes from the audit sequence, so
-- the feed stays one monotonic cursor.
create or replace function kb.change_only() returns trigger
language plpgsql security definer set search_path = pg_catalog, public
as $$
declare
    ids uuid[];
    k text;
begin
    if tg_table_name = 'graph_positions' then
        if tg_op = 'DELETE' then
            select coalesce(array_agg(distinct node_id), '{}') into ids from old_rows;
        else
            select coalesce(array_agg(distinct node_id), '{}') into ids from new_rows;
        end if;
        k := 'layout.update';
    elsif tg_table_name = 'person_accounts' then
        if tg_op = 'DELETE' then
            select coalesce(array_agg(distinct node_id), '{}') into ids from old_rows;
        else
            select coalesce(array_agg(distinct node_id), '{}') into ids from new_rows;
        end if;
        k := 'owner.account';
    else
        -- sync_runs: one event when a run finishes
        if not exists (select 1 from new_rows n join old_rows o on o.id = n.id
                       where o.finished_at is null and n.finished_at is not null) then
            return null;
        end if;
        ids := '{}';
        k := 'sync.run';
    end if;
    if k <> 'sync.run' and ids = '{}' then
        return null;   -- the statement touched no rows
    end if;
    insert into kb.changes (id, actor_id, actor_type, table_name, row_id, action, version, kind, node_ids)
    values (nextval('kb.audit_log_id_seq'), kb.actor_id(), kb.actor_type(), tg_table_name, null,
            lower(tg_op), null, k, ids);
    return null;
end;
$$;

create trigger graph_positions_changes_ins after insert on kb.graph_positions
    referencing new table as new_rows for each statement execute function kb.change_only();
create trigger graph_positions_changes_upd after update on kb.graph_positions
    referencing old table as old_rows new table as new_rows for each statement execute function kb.change_only();
create trigger graph_positions_changes_del after delete on kb.graph_positions
    referencing old table as old_rows for each statement execute function kb.change_only();
create trigger person_accounts_changes_ins after insert on kb.person_accounts
    referencing new table as new_rows for each statement execute function kb.change_only();
create trigger person_accounts_changes_upd after update on kb.person_accounts
    referencing old table as old_rows new table as new_rows for each statement execute function kb.change_only();
create trigger person_accounts_changes_del after delete on kb.person_accounts
    referencing old table as old_rows for each statement execute function kb.change_only();
create trigger sync_runs_changes_upd after update on kb.sync_runs
    referencing old table as old_rows new table as new_rows for each statement execute function kb.change_only();

revoke all on function kb.change_only() from public;
