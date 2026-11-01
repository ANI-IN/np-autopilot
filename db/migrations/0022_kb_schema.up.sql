-- 0022 — the `kb` schema: AUTHORED knowledge, edited in the app.
--
-- WHY A NEW SCHEMA rather than columns on public.nodes / public.edges: those
-- tables are a PROJECTION of the pipeline's graph.json and are replaced
-- wholesale on every build (DECISIONS §B.1). An app edit written there would be
-- erased by the next refresh, and adding uuid/version/status columns to them
-- would change what the live explorer reads. Nothing here touches `public`.
--
-- Purely ADDITIVE. The down migration drops only what this file created.
--
-- Conventions, applied to every mutable table:
--   id uuid · created_by · updated_by · created_at · updated_at
--   version int (optimistic locking, bumped by trigger, never by a caller)
--   status · archived_at (soft delete; hard delete is admin-only and only of
--   already-archived rows — see 0023's policies)
-- Every insert/update/delete writes before/after JSON to kb.audit_log.

create schema if not exists kb;
create schema if not exists extensions;
create extension if not exists pg_trgm with schema extensions;

-- ---------------------------------------------------------------------------
-- Actor attribution. The service layer sets these per transaction:
--   kb.actor_type  human | ai | import | system
--   kb.actor_id    uuid, used only when auth.uid() is null (scripts)
-- auth.uid() wins when present: a caller cannot claim to be someone else by
-- setting a GUC, because under RLS the uid comes from the verified JWT claims.
-- ---------------------------------------------------------------------------
create or replace function kb.actor_id() returns uuid
language sql stable set search_path = pg_catalog, public
as $$
    select coalesce(
        nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub',
        nullif(current_setting('kb.actor_id', true), '')
    )::uuid
$$;

create or replace function kb.actor_type() returns text
language sql stable set search_path = pg_catalog
as $$
    select case coalesce(nullif(current_setting('kb.actor_type', true), ''), 'human')
             when 'ai' then 'ai' when 'import' then 'import'
             when 'system' then 'system' else 'human' end
$$;

-- Trim + collapse whitespace + lowercase: the duplicate-prevention key.
create or replace function kb.norm(t text) returns text
language sql immutable parallel safe
as $$ select lower(regexp_replace(btrim(t), '\s+', ' ', 'g')) $$;

-- ---------------------------------------------------------------------------
-- Configurable types.
-- ---------------------------------------------------------------------------
create table kb.node_types (
    id          uuid primary key default gen_random_uuid(),
    key         text not null unique,
    label       text not null,
    description text,
    color       text not null default '#64748b',
    icon        text,
    -- course / program: a node of this type can be the SCOPE of other nodes.
    is_container boolean not null default false,
    sort_order  integer not null default 100,
    created_by  uuid, updated_by uuid,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    version     integer not null default 1,
    status      text not null default 'active',
    archived_at timestamptz,
    constraint key_shape check (key ~ '^[a-z][a-z0-9_]{1,40}$'),
    constraint color_shape check (color ~ '^#[0-9a-fA-F]{6}$'),
    constraint status_known check (status in ('active', 'archived'))
);

create table kb.edge_types (
    id          uuid primary key default gen_random_uuid(),
    key         text not null unique,
    label       text not null,
    inverse_label text,
    description text,
    allow_self  boolean not null default false,
    created_by  uuid, updated_by uuid,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    version     integer not null default 1,
    status      text not null default 'active',
    archived_at timestamptz,
    constraint key_shape check (key ~ '^[a-z][a-z0-9_]{1,40}$'),
    constraint status_known check (status in ('active', 'archived'))
);

-- Which source type may point at which target type through an edge type.
-- An edge type with NO rules accepts no edges: the permissive default is the
-- one that lets a typo become a relationship.
create table kb.edge_type_rules (
    id             uuid primary key default gen_random_uuid(),
    edge_type_id   uuid not null references kb.edge_types(id) on delete cascade,
    source_type_id uuid not null references kb.node_types(id) on delete cascade,
    target_type_id uuid not null references kb.node_types(id) on delete cascade,
    created_by uuid, updated_by uuid,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    version    integer not null default 1,
    status     text not null default 'active',
    archived_at timestamptz,
    constraint rule_unique unique (edge_type_id, source_type_id, target_type_id)
);

-- ---------------------------------------------------------------------------
-- Nodes. Courses and programs are node TYPES (is_container), not tables: they
-- carry the same relationships, resources, history and search as any node, and
-- a separate table would duplicate all of that. `scope_id` points at the
-- course/program a node belongs to, and scopes name uniqueness.
-- ---------------------------------------------------------------------------
create table kb.nodes (
    id          uuid primary key default gen_random_uuid(),
    type_id     uuid not null references kb.node_types(id),
    name        text not null,
    name_norm   text generated always as (kb.norm(name)) stored,
    summary     text,
    body        text,
    scope_id    uuid references kb.nodes(id),
    owner_id    uuid,
    props       jsonb not null default '{}'::jsonb,
    -- Import provenance (M8). external_id = '<sheet id>:<tab>:<row key>'.
    external_id text unique,
    imported_at timestamptz,
    imported_version integer,
    search      tsvector generated always as (
                    setweight(to_tsvector('simple', coalesce(name, '')), 'A') ||
                    setweight(to_tsvector('simple', coalesce(summary, '')), 'B') ||
                    setweight(to_tsvector('simple', coalesce(body, '')), 'C')) stored,
    created_by  uuid, updated_by uuid,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    version     integer not null default 1,
    status      text not null default 'active',
    archived_at timestamptz,
    constraint name_nonempty check (length(btrim(name)) > 0),
    constraint name_length check (length(name) <= 300),
    -- Same rule as public.nodes.label_not_contact: a name is never an address.
    constraint name_not_contact check (name !~ '@' and lower(name) !~ 'https?://'),
    constraint summary_length check (summary is null or length(summary) <= 2000),
    constraint body_length check (body is null or length(body) <= 100000),
    constraint status_known check (status in ('draft', 'active', 'archived')),
    constraint archived_consistent check ((status = 'archived') = (archived_at is not null)),
    constraint not_own_scope check (scope_id is null or scope_id <> id)
);

-- One live name per type + scope, case/whitespace-insensitive. Archived rows
-- are exempt so that archiving frees a name; restoring into a taken name fails.
create unique index nodes_name_unique on kb.nodes
    (type_id, coalesce(scope_id, '00000000-0000-0000-0000-000000000000'::uuid), name_norm)
    where archived_at is null;
create index nodes_type_idx    on kb.nodes (type_id) where archived_at is null;
create index nodes_scope_idx   on kb.nodes (scope_id);
create index nodes_updated_idx on kb.nodes (updated_at desc, id);
create index nodes_search_idx  on kb.nodes using gin (search);
create index nodes_name_trgm   on kb.nodes using gin (name_norm extensions.gin_trgm_ops);

-- ---------------------------------------------------------------------------
-- Edges.
-- ---------------------------------------------------------------------------
create table kb.edges (
    id           uuid primary key default gen_random_uuid(),
    edge_type_id uuid not null references kb.edge_types(id),
    source_id    uuid not null references kb.nodes(id) on delete cascade,
    target_id    uuid not null references kb.nodes(id) on delete cascade,
    note         text,
    props        jsonb not null default '{}'::jsonb,
    -- The node whose archiving archived this edge; restore brings back exactly
    -- these and nothing a person archived deliberately.
    archived_with uuid,
    external_id  text unique,
    created_by uuid, updated_by uuid,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    version    integer not null default 1,
    status     text not null default 'active',
    archived_at timestamptz,
    constraint note_length check (note is null or length(note) <= 2000),
    constraint status_known check (status in ('active', 'archived')),
    constraint archived_consistent check ((status = 'archived') = (archived_at is not null))
);
create unique index edges_unique_live on kb.edges (source_id, target_id, edge_type_id)
    where archived_at is null;
create index edges_source_idx on kb.edges (source_id) where archived_at is null;
create index edges_target_idx on kb.edges (target_id) where archived_at is null;
create index edges_archived_with_idx on kb.edges (archived_with) where archived_with is not null;

-- ---------------------------------------------------------------------------
-- Resources — reusable, many-to-many to nodes.
-- ---------------------------------------------------------------------------
create table kb.resources (
    id          uuid primary key default gen_random_uuid(),
    url         text not null,
    url_norm    text generated always as (lower(regexp_replace(btrim(url), '/+$', ''))) stored,
    title       text not null,
    kind        text not null default 'link',
    description text,
    external_id text unique,
    imported_at timestamptz,
    imported_version integer,
    created_by uuid, updated_by uuid,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    version    integer not null default 1,
    status     text not null default 'active',
    archived_at timestamptz,
    constraint url_shape check (url ~* '^https?://[^\s/$.?#][^\s]*$' and length(url) <= 2048),
    constraint title_nonempty check (length(btrim(title)) > 0 and length(title) <= 300),
    constraint kind_known check (kind in ('link', 'doc', 'sheet', 'slides', 'video', 'pdf', 'folder', 'other')),
    constraint status_known check (status in ('active', 'archived')),
    constraint archived_consistent check ((status = 'archived') = (archived_at is not null))
);
create unique index resources_url_unique on kb.resources (url_norm) where archived_at is null;
create index resources_title_trgm on kb.resources using gin (lower(title) extensions.gin_trgm_ops);

create table kb.node_resources (
    id          uuid primary key default gen_random_uuid(),
    node_id     uuid not null references kb.nodes(id) on delete cascade,
    resource_id uuid not null references kb.resources(id) on delete cascade,
    note        text,
    position    integer not null default 0,
    archived_with uuid,
    created_by uuid, updated_by uuid,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    version    integer not null default 1,
    status     text not null default 'active',
    archived_at timestamptz,
    constraint note_length check (note is null or length(note) <= 2000),
    constraint status_known check (status in ('active', 'archived')),
    constraint archived_consistent check ((status = 'archived') = (archived_at is not null))
);
create unique index node_resources_unique_live on kb.node_resources (node_id, resource_id)
    where archived_at is null;
create index node_resources_resource_idx on kb.node_resources (resource_id);

-- ---------------------------------------------------------------------------
-- Tags.
-- ---------------------------------------------------------------------------
create table kb.tags (
    id         uuid primary key default gen_random_uuid(),
    name       text not null,
    name_norm  text generated always as (kb.norm(name)) stored,
    color      text not null default '#64748b',
    created_by uuid, updated_by uuid,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    version    integer not null default 1,
    status     text not null default 'active',
    archived_at timestamptz,
    constraint name_nonempty check (length(btrim(name)) > 0 and length(name) <= 60),
    constraint status_known check (status in ('active', 'archived'))
);
create unique index tags_name_unique on kb.tags (name_norm) where archived_at is null;

create table kb.node_tags (
    node_id    uuid not null references kb.nodes(id) on delete cascade,
    tag_id     uuid not null references kb.tags(id) on delete cascade,
    created_by uuid,
    created_at timestamptz not null default now(),
    primary key (node_id, tag_id)
);
create index node_tags_tag_idx on kb.node_tags (tag_id);

-- ---------------------------------------------------------------------------
-- Roles. A row here GRANTS a KB role; with no row, a signed-in IK profile is a
-- viewer (0023's kb.role()). Nobody is auto-admin: admins come from
-- ADMIN_EMAILS through pipeline/kb_admins.py, run by an operator.
-- ---------------------------------------------------------------------------
create table kb.memberships (
    user_id    uuid primary key,
    role       text not null,
    created_by uuid, updated_by uuid,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    version    integer not null default 1,
    status     text not null default 'active',
    archived_at timestamptz,
    constraint role_known check (role in ('admin', 'editor', 'contributor', 'viewer')),
    constraint status_known check (status in ('active', 'archived'))
);

-- Per-user API tokens for the MCP server. Only the SHA-256 is stored.
create table kb.api_tokens (
    id           uuid primary key default gen_random_uuid(),
    user_id      uuid not null,
    name         text not null,
    token_hash   text not null unique,
    prefix       text not null,
    expires_at   timestamptz,
    last_used_at timestamptz,
    revoked_at   timestamptz,
    created_by uuid, updated_by uuid,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    version    integer not null default 1,
    status     text not null default 'active',
    archived_at timestamptz,
    constraint hash_shape check (token_hash ~ '^[0-9a-f]{64}$'),
    constraint name_nonempty check (length(btrim(name)) > 0 and length(name) <= 80),
    constraint status_known check (status in ('active', 'archived'))
);
create index api_tokens_user_idx on kb.api_tokens (user_id);

-- A change an AI (or contributor) may PROPOSE but not execute: archive and
-- delete. A human editor+ approves in the app, and the approval executes it.
create table kb.proposals (
    id          uuid primary key default gen_random_uuid(),
    action      text not null,
    target_table text not null,
    target_id   uuid not null,
    reason      text,
    payload     jsonb not null default '{}'::jsonb,
    actor_type  text not null default 'human',
    decided_by  uuid,
    decided_at  timestamptz,
    created_by uuid, updated_by uuid,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    version    integer not null default 1,
    status     text not null default 'pending',
    archived_at timestamptz,
    constraint action_known check (action in ('archive', 'delete')),
    constraint table_known check (target_table in ('nodes', 'edges', 'resources', 'node_resources')),
    constraint status_known check (status in ('pending', 'approved', 'rejected'))
);
create index proposals_pending_idx on kb.proposals (created_at desc) where status = 'pending';

-- ---------------------------------------------------------------------------
-- The audit log. Written ONLY by the trigger below (SECURITY DEFINER); no role
-- may insert into it directly (0023 grants no insert).
-- ---------------------------------------------------------------------------
create table kb.audit_log (
    id         bigint generated always as identity primary key,
    at         timestamptz not null default now(),
    actor_id   uuid,
    actor_type text not null,
    table_name text not null,
    row_id     uuid,
    action     text not null,
    before     jsonb,
    after      jsonb,
    constraint action_known check (action in ('insert', 'update', 'delete'))
);
create index audit_log_row_idx on kb.audit_log (table_name, row_id, id desc);
create index audit_log_at_idx  on kb.audit_log (id desc);

-- ---------------------------------------------------------------------------
-- Triggers.
-- ---------------------------------------------------------------------------

-- Stamp authorship and bump the version. A caller cannot set version,
-- created_by, or created_at: they are overwritten here.
create or replace function kb.stamp() returns trigger
language plpgsql set search_path = pg_catalog, public
as $$
begin
    if tg_op = 'INSERT' then
        new.created_by := kb.actor_id();
        new.updated_by := new.created_by;
        new.created_at := now();
        new.updated_at := now();
        new.version := 1;
    else
        new.created_by := old.created_by;
        new.created_at := old.created_at;
        new.updated_by := kb.actor_id();
        new.updated_at := now();
        new.version := old.version + 1;
    end if;
    return new;
end;
$$;

-- Before/after for every insert/update/delete. SECURITY DEFINER so the row
-- lands even though no caller holds insert on kb.audit_log. api_tokens rows are
-- audited without their hash.
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
    -- The generated tsvector is noise in a diff.
    b := b - 'search'; a := a - 'search';
    rid := coalesce(a ->> 'id', b ->> 'id', a ->> 'user_id', b ->> 'user_id', a ->> 'node_id', b ->> 'node_id')::uuid;
    insert into kb.audit_log (actor_id, actor_type, table_name, row_id, action, before, after)
    values (kb.actor_id(), kb.actor_type(), tg_table_name, rid, lower(tg_op), b, a);
    return null;
end;
$$;

-- Edge integrity: endpoints live (locked FOR SHARE so a concurrent archive
-- serialises against this insert), self-edges only where the type allows, and
-- the (source type, target type) pair allowed by a rule.
create or replace function kb.check_edge() returns trigger
language plpgsql set search_path = pg_catalog, public
as $$
declare
    s record; t record; et record;
begin
    if new.archived_at is not null then
        return new;                -- archiving or an archived row: no re-check
    end if;
    select id, type_id, archived_at into s from kb.nodes where id = new.source_id for share;
    select id, type_id, archived_at into t from kb.nodes where id = new.target_id for share;
    if s.id is null or t.id is null then
        raise exception 'edge endpoint does not exist' using errcode = 'foreign_key_violation';
    end if;
    if s.archived_at is not null or t.archived_at is not null then
        raise exception 'cannot connect an archived node' using errcode = 'check_violation',
            hint = 'kb_endpoint_archived';
    end if;
    select * into et from kb.edge_types where id = new.edge_type_id;
    if et.archived_at is not null then
        raise exception 'edge type % is archived', et.key using errcode = 'check_violation',
            hint = 'kb_edge_type_archived';
    end if;
    if new.source_id = new.target_id and not et.allow_self then
        raise exception 'edge type % does not allow a node to point at itself', et.key
            using errcode = 'check_violation', hint = 'kb_self_edge';
    end if;
    if not exists (select 1 from kb.edge_type_rules r
                   where r.edge_type_id = new.edge_type_id and r.archived_at is null
                     and r.source_type_id = s.type_id and r.target_type_id = t.type_id) then
        raise exception 'edge type % is not allowed from % to %', et.key,
            (select key from kb.node_types where id = s.type_id),
            (select key from kb.node_types where id = t.type_id)
            using errcode = 'check_violation', hint = 'kb_edge_rule';
    end if;
    return new;
end;
$$;

-- Same lock discipline for attachments.
create or replace function kb.check_attachment() returns trigger
language plpgsql set search_path = pg_catalog, public
as $$
begin
    if new.archived_at is not null then
        return new;
    end if;
    if exists (select 1 from kb.nodes where id = new.node_id and archived_at is not null for share)
       or exists (select 1 from kb.resources where id = new.resource_id and archived_at is not null for share) then
        raise exception 'cannot attach to an archived record' using errcode = 'check_violation',
            hint = 'kb_endpoint_archived';
    end if;
    perform 1 from kb.nodes where id = new.node_id for share;
    return new;
end;
$$;

-- Archive cascade: archiving a node archives its live edges and attachments and
-- remembers why (archived_with); restoring brings back exactly those whose
-- other endpoint is live. Runs as the caller, so RLS still applies.
create or replace function kb.cascade_archive() returns trigger
language plpgsql set search_path = pg_catalog, public
as $$
begin
    if old.archived_at is null and new.archived_at is not null then
        if tg_table_name = 'nodes' then
            update kb.edges set archived_at = new.archived_at, status = 'archived',
                                archived_with = new.id
             where (source_id = new.id or target_id = new.id) and archived_at is null;
        end if;
        update kb.node_resources set archived_at = new.archived_at, status = 'archived',
                                     archived_with = new.id
         where (case when tg_table_name = 'nodes' then node_id else resource_id end) = new.id
           and archived_at is null;
    elsif old.archived_at is not null and new.archived_at is null then
        if tg_table_name = 'nodes' then
            update kb.edges e set archived_at = null, status = 'active', archived_with = null
             where e.archived_with = new.id
               and not exists (select 1 from kb.nodes n
                               where n.id in (e.source_id, e.target_id)
                                 and n.id <> new.id and n.archived_at is not null)
               and not exists (select 1 from kb.edges d
                               where d.archived_at is null and d.source_id = e.source_id
                                 and d.target_id = e.target_id and d.edge_type_id = e.edge_type_id);
        end if;
        update kb.node_resources nr set archived_at = null, status = 'active', archived_with = null
         where nr.archived_with = new.id
           and not exists (select 1 from kb.node_resources d where d.archived_at is null
                             and d.node_id = nr.node_id and d.resource_id = nr.resource_id);
    end if;
    return null;
end;
$$;

do $$
declare t text;
begin
    foreach t in array array['node_types', 'edge_types', 'edge_type_rules', 'nodes', 'edges',
                             'resources', 'node_resources', 'tags', 'memberships',
                             'api_tokens', 'proposals']
    loop
        execute format('create trigger %I before insert or update on kb.%I
                        for each row execute function kb.stamp()', t || '_stamp', t);
        execute format('create trigger %I after insert or update or delete on kb.%I
                        for each row execute function kb.audit()', t || '_audit', t);
    end loop;
end $$;
create trigger node_tags_audit after insert or update or delete on kb.node_tags
    for each row execute function kb.audit();

create trigger edges_check before insert or update on kb.edges
    for each row execute function kb.check_edge();
create trigger node_resources_check before insert or update on kb.node_resources
    for each row execute function kb.check_attachment();
create trigger nodes_cascade_archive after update of archived_at on kb.nodes
    for each row execute function kb.cascade_archive();
create trigger resources_cascade_archive after update of archived_at on kb.resources
    for each row execute function kb.cascade_archive();

-- ---------------------------------------------------------------------------
-- Starting vocabulary. Configurable: admins add types and rules in the app.
-- These are KB-workspace types, independent of the pipeline's taxonomy.yaml
-- (which describes the derived corpus graph, not authored records).
-- ---------------------------------------------------------------------------
insert into kb.node_types (key, label, color, is_container, sort_order, description) values
    ('program',  'Program',  '#7c3aed', true,  10, 'A learner-facing program, e.g. a bootcamp track'),
    ('course',   'Course',   '#2563eb', true,  20, 'A course within or across programs'),
    ('module',   'Module',   '#0891b2', false, 30, 'A unit of a course'),
    ('topic',    'Topic',    '#059669', false, 40, 'A concept taught or assessed'),
    ('instructor','Instructor','#d97706', false, 50, 'A person who teaches; name only, never contact data'),
    ('process',  'Process',  '#db2777', false, 60, 'An internal workflow or SOP');

insert into kb.edge_types (key, label, inverse_label, description) values
    ('contains',   'contains',   'part of',     'Structural containment'),
    ('covers',     'covers',     'covered by',  'Content coverage of a topic'),
    ('teaches',    'teaches',    'taught by',   'An instructor teaches a course or module'),
    ('prerequisite','requires',  'required by', 'Must come before'),
    ('related',    'related to', 'related to',  'Loose association');

insert into kb.edge_type_rules (edge_type_id, source_type_id, target_type_id)
select e.id, s.id, t.id
from (values
    ('contains', 'program', 'course'), ('contains', 'course', 'module'),
    ('contains', 'module', 'topic'),   ('contains', 'program', 'module'),
    ('covers', 'course', 'topic'),     ('covers', 'module', 'topic'),
    ('teaches', 'instructor', 'course'), ('teaches', 'instructor', 'module'),
    ('prerequisite', 'course', 'course'), ('prerequisite', 'module', 'module'),
    ('prerequisite', 'topic', 'topic'),
    ('related', 'topic', 'topic'), ('related', 'course', 'course'),
    ('related', 'module', 'module'), ('related', 'process', 'process'),
    ('related', 'process', 'course'), ('related', 'process', 'program')
) as v(e, s, t)
join kb.edge_types e on e.key = v.e
join kb.node_types s on s.key = v.s
join kb.node_types t on t.key = v.t;

-- The seed rows are system-authored; their audit rows say so.
update kb.audit_log set actor_type = 'system' where actor_id is null;
