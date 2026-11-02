-- 0029 — run 3: named actors, an append-only and role-scoped audit log, a
-- content-free change feed, reviewable relationship types, graph positions.
--
-- 1. Actors (owner bug A2). A write with no verified user and no declared actor
--    (a migration, psql, a test fixture) used to be stamped actor_type 'human'
--    with a null actor_id, which the UI could only call "Someone". It is now
--    'system'. Existing rows are re-labelled the same way.
-- 2. The audit log is append-only for everyone, the API included: UPDATE and
--    DELETE raise unless the CURRENT role is a superuser (none on Supabase).
--    The local demo seed and test resets clear it with TRUNCATE (owner only).
-- 3. Who reads it (B4), enforced here:
--      admin   every row;
--      editor  rows they made, and rows about records in their scope (records
--              they own or co-own and everything placed inside them, the links
--              they own);
--      others  nothing directly; a record's History goes through
--              kb.record_history(), which returns that record's rows only.
-- 4. Because viewers no longer read the audit log, collaboration needs a feed
--    without content: kb.changes (id, table, row, action, version, actor). The
--    audit trigger writes both; Realtime now publishes kb.changes.
-- 5. Relationship types (B2): review_status (an editor's new type is usable at
--    once but 'unreviewed' until an admin confirms, renames or merges it) and
--    merged_into. Editors may INSERT only unreviewed, non-core types and rules
--    for the types they created; admins keep full control. Names that match an
--    existing type or inverse after normalising case, spacing, plurals and verb
--    endings are refused (kb.rel_stem).
-- 6. kb.graph_positions: per graph layout ('default' or a saved view id) node
--    coordinates. Layout only: nothing here changes a record.

-- 1 ------------------------------------------------------------------------
create or replace function kb.actor_type() returns text
language sql stable set search_path = pg_catalog, public
as $$
    select case coalesce(nullif(current_setting('kb.actor_type', true), ''),
                         case when kb.actor_id() is null then 'system' else 'human' end)
             when 'ai' then 'ai' when 'import' then 'import'
             when 'system' then 'system' else 'human' end
$$;
update kb.audit_log set actor_type = 'system' where actor_id is null and actor_type = 'human';

-- 2 ------------------------------------------------------------------------
create or replace function kb.audit_immutable() returns trigger
language plpgsql set search_path = pg_catalog
as $$
begin
    if coalesce((select rolsuper from pg_roles where rolname = current_user), false) then
        return case when tg_op = 'DELETE' then old else new end;
    end if;
    raise exception 'the activity log is append-only'
        using errcode = 'insufficient_privilege', hint = 'kb_audit_immutable';
end;
$$;
create trigger audit_log_immutable before update or delete on kb.audit_log
    for each row execute function kb.audit_immutable();

-- 3 ------------------------------------------------------------------------
-- The records an editor is responsible for: owned or co-owned, plus everything
-- placed inside them (contains edges and scope), to any depth.
create or replace function kb.my_scope_ids() returns uuid[]
language sql stable security definer set search_path = pg_catalog, public
as $$
    with recursive kids(parent, child) as (
        select e.source_id, e.target_id from kb.edges e
        join kb.edge_types et on et.id = e.edge_type_id and et.key = 'contains'
        where e.archived_at is null
        union all
        select n.scope_id, n.id from kb.nodes n where n.scope_id is not null
    ), mine(id) as (
        select n.id from kb.nodes n
        where auth.uid() is not null and (n.owner_id = auth.uid() or auth.uid() = any(n.co_owners))
        union
        select k.child from mine m join kids k on k.parent = m.id
    )
    select coalesce(array_agg(id), '{}') from (
        select id from mine
        union select r.id from kb.resources r where auth.uid() is not null and r.owner_id = auth.uid()
    ) s
$$;
revoke all on function kb.my_scope_ids() from public;
grant execute on function kb.my_scope_ids() to authenticated;

drop policy audit_log_select on kb.audit_log;
create policy audit_log_select on kb.audit_log for select to authenticated
    using ((select kb.role_at_least('admin'))
           or ((select kb.role_at_least('editor')) and table_name not in ('api_tokens', 'memberships')
               and (actor_id = (select auth.uid())
                    or row_id = any((select kb.my_scope_ids())::uuid[])
                    or (coalesce(after, before) ->> 'source_id')::uuid = any((select kb.my_scope_ids())::uuid[])
                    or (coalesce(after, before) ->> 'target_id')::uuid = any((select kb.my_scope_ids())::uuid[])
                    or (coalesce(after, before) ->> 'node_id')::uuid = any((select kb.my_scope_ids())::uuid[]))));

-- A record's history for anyone who may see records (viewer+; every live or
-- archived record is readable at that role, 0023): the record's own rows, its
-- relationships, its links and tags. Never api_tokens or memberships rows.
create or replace function kb.record_history(rid uuid, max_rows integer default 50)
returns setof kb.audit_log
language plpgsql stable security definer set search_path = pg_catalog, public
as $$
begin
    if not kb.role_at_least('viewer') then
        raise exception 'reading history needs the viewer role' using errcode = 'insufficient_privilege';
    end if;
    return query
    select a.* from kb.audit_log a
    where a.table_name in ('nodes', 'resources', 'edges', 'node_resources', 'node_tags')
      and (a.row_id = rid
           or (a.table_name = 'edges' and rid::text in (coalesce(a.after, a.before) ->> 'source_id', coalesce(a.after, a.before) ->> 'target_id'))
           or (a.table_name in ('node_resources', 'node_tags') and rid::text in (coalesce(a.after, a.before) ->> 'node_id', coalesce(a.after, a.before) ->> 'resource_id')))
    order by a.id desc limit least(greatest(max_rows, 1), 200);
end;
$$;
revoke all on function kb.record_history(uuid, integer) from public, anon;
grant execute on function kb.record_history(uuid, integer) to authenticated;
create index if not exists audit_log_edges_src_idx on kb.audit_log ((coalesce(after, before) ->> 'source_id')) where table_name = 'edges';
create index if not exists audit_log_edges_tgt_idx on kb.audit_log ((coalesce(after, before) ->> 'target_id')) where table_name = 'edges';
create index if not exists audit_log_link_node_idx on kb.audit_log ((coalesce(after, before) ->> 'node_id')) where table_name in ('node_resources', 'node_tags');
create index if not exists audit_log_link_res_idx on kb.audit_log ((coalesce(after, before) ->> 'resource_id')) where table_name in ('node_resources', 'node_tags');
create index if not exists audit_log_actor_idx on kb.audit_log (actor_id, id desc);
create index if not exists audit_log_table_idx on kb.audit_log (table_name, id desc);

-- 4 ------------------------------------------------------------------------
create table kb.changes (
    id         bigint primary key,
    at         timestamptz not null default now(),
    actor_id   uuid,
    actor_type text not null,
    table_name text not null,
    row_id     uuid,
    action     text not null,
    version    text
);
alter table kb.changes enable row level security;
create policy changes_select on kb.changes for select to authenticated
    using ((select kb.role_at_least('viewer'))
           and (table_name not in ('api_tokens', 'memberships') or (select kb.role_at_least('admin'))
                or actor_id = (select auth.uid())));
grant select on kb.changes to authenticated;
revoke insert, update, delete on kb.changes from authenticated;
insert into kb.changes (id, at, actor_id, actor_type, table_name, row_id, action, version)
select id, at, actor_id, actor_type, table_name, row_id, action, coalesce(after ->> 'version', before ->> 'version')
from kb.audit_log;

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

do $$
begin
    if exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
        if exists (select 1 from pg_publication_tables where pubname = 'supabase_realtime'
                   and schemaname = 'kb' and tablename = 'audit_log') then
            execute 'alter publication supabase_realtime drop table kb.audit_log';
        end if;
        execute 'alter publication supabase_realtime add table kb.changes';
    end if;
end $$;

-- 5 ------------------------------------------------------------------------
alter table kb.edge_types
    add column review_status text not null default 'reviewed',
    add column merged_into uuid references kb.edge_types(id),
    add constraint review_status_known check (review_status in ('reviewed', 'unreviewed'));

-- "Teaches", "teach", "taught by" (as an inverse), "mentors"/"mentored by":
-- lower-case, collapse spaces, drop punctuation, strip common verb and plural
-- endings word by word.
create or replace function kb.rel_stem(t text) returns text
language sql immutable parallel safe set search_path = pg_catalog
as $$
    select string_agg(case
             when w ~ '^.{3,}ies$' then regexp_replace(w, 'ies$', 'y')
             when w ~ '^.{3,}(ches|shes|sses|xes)$' then regexp_replace(w, 'es$', '')
             when w ~ '^.{3,}ing$' then regexp_replace(w, 'ing$', '')
             when w ~ '^.{3,}ed$' then regexp_replace(w, 'ed$', '')
             when w ~ '^.{3,}[^s]s$' then regexp_replace(w, 's$', '')
             else w end, ' ' order by i)
    from unnest(regexp_split_to_array(btrim(regexp_replace(lower(coalesce(t, '')), '[^a-z0-9]+', ' ', 'g')), ' ')) with ordinality as x(w, i)
    where w <> ''
$$;

create or replace function kb.check_edge_type_name() returns trigger
language plpgsql set search_path = pg_catalog, public
as $$
declare
    hit record;
    stems text[] := array_remove(array[kb.rel_stem(new.label), kb.rel_stem(new.inverse_label)], null);
begin
    if new.archived_at is not null then return new; end if;
    if tg_op = 'UPDATE' and kb.rel_stem(new.label) is not distinct from kb.rel_stem(old.label)
       and kb.rel_stem(new.inverse_label) is not distinct from kb.rel_stem(old.inverse_label)
       and old.archived_at is null then
        return new;
    end if;
    select et.key, et.label into hit from kb.edge_types et
    where et.id <> new.id and et.archived_at is null
      and (kb.rel_stem(et.label) = any(stems) or kb.rel_stem(et.inverse_label) = any(stems))
    limit 1;
    if found then
        raise exception 'a relationship type like this already exists: %', hit.label
            using errcode = 'unique_violation', hint = 'kb_rel_duplicate:' || hit.key;
    end if;
    return new;
end;
$$;
create trigger edge_types_check_name before insert or update on kb.edge_types
    for each row execute function kb.check_edge_type_name();

drop policy edge_types_admin on kb.edge_types;
create policy edge_types_admin on kb.edge_types for all to authenticated
    using ((select kb.role_at_least('admin'))) with check ((select kb.role_at_least('admin')));
create policy edge_types_editor_insert on kb.edge_types for insert to authenticated
    with check ((select kb.role_at_least('editor')) and review_status = 'unreviewed'
                and not is_core and merged_into is null);
drop policy edge_type_rules_admin on kb.edge_type_rules;
create policy edge_type_rules_admin on kb.edge_type_rules for all to authenticated
    using ((select kb.role_at_least('admin'))) with check ((select kb.role_at_least('admin')));
create policy edge_type_rules_editor_insert on kb.edge_type_rules for insert to authenticated
    with check ((select kb.role_at_least('editor')) and exists (
        select 1 from kb.edge_types et where et.id = edge_type_id and et.review_status = 'unreviewed'
        and et.created_by = (select auth.uid())));

-- 6 ------------------------------------------------------------------------
create table kb.graph_positions (
    layout     text not null,
    node_id    uuid not null references kb.nodes(id) on delete cascade,
    x          double precision not null,
    y          double precision not null,
    updated_by uuid default auth.uid(),
    updated_at timestamptz not null default now(),
    primary key (layout, node_id),
    constraint layout_shape check (layout = 'default' or layout ~ '^[0-9a-f-]{36}$'),
    constraint finite check (x between -1e7 and 1e7 and y between -1e7 and 1e7)
);
alter table kb.graph_positions enable row level security;
create policy graph_positions_select on kb.graph_positions for select to authenticated
    using ((select kb.role_at_least('viewer')));
create policy graph_positions_write on kb.graph_positions for all to authenticated
    using ((select kb.role_at_least('contributor'))) with check ((select kb.role_at_least('contributor')));
grant select, insert, update, delete on kb.graph_positions to authenticated;

-- 7 ------------------------------------------------------------------------
-- Names for the activity log (A2): the email of ANY profile that ever acted,
-- including people whose membership was removed since, so an old entry still
-- says who did it. Viewer+ only, and only for ids passed in.
create or replace function kb.actor_emails(ids uuid[]) returns table (user_id uuid, email text)
language sql stable security definer set search_path = pg_catalog, public
as $$
    select p.user_id, p.email from public.profiles p
    where kb.role_at_least('viewer') and p.user_id = any(ids)
$$;
revoke all on function kb.actor_emails(uuid[]) from public, anon;
grant execute on function kb.actor_emails(uuid[]) to authenticated;
