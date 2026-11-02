-- 0027 — custom types, link kinds, people, reviews, templates, saved views.
--
-- Additive: new columns with defaults, new tables, widened CHECKs, new triggers.
-- Every value accepted before is still accepted. Reversed by 0027 down.
--
-- CUSTOM TYPES (C2) are enforced HERE, not only in the service:
--   * kb.node_types.fields is a JSON array of field definitions, shape-checked
--     by kb.check_type_def(). A field's `key` is permanent: an update may add
--     fields or mark one `archived` (hidden, data kept), never drop or re-key.
--   * kb.check_node_props() validates every record's props against its type's
--     live fields (kinds, select options, reference targets). Required fields
--     are enforced on INSERT only: a field made required later FLAGS existing
--     records (Data quality), it never blocks editing them.
--   * Edge cardinality and self-links are enforced in kb.check_edge().

-- ---------------------------------------------------------------------------
-- Record types
-- ---------------------------------------------------------------------------
alter table kb.node_types
    add column plural          text,
    add column fields          jsonb   not null default '[]'::jsonb,
    add column allowed_parents text[]  not null default '{}',
    add column parent_required boolean not null default false,
    add column default_status  text    not null default 'active',
    add column owner_rule      text    not null default 'creator',
    add column is_core         boolean not null default false,
    add constraint default_status_known check (default_status in ('draft', 'active')),
    add constraint owner_rule_known check (owner_rule in ('creator', 'none')),
    add constraint fields_is_array check (jsonb_typeof(fields) = 'array'),
    add constraint label_nonempty check (length(btrim(label)) > 0);
create unique index node_types_label_unique on kb.node_types (lower(label)) where archived_at is null;

update kb.node_types set is_core = true where key in
    ('program', 'course', 'module', 'topic', 'instructor', 'process', 'domain', 'week', 'session');
update kb.node_types t set plural = v.plural, icon = v.icon, allowed_parents = v.parents
from (values
    ('program',    'Programs',      'graduation-cap', '{}'::text[]),
    ('course',     'Courses',       'book-open',      '{program}'),
    ('domain',     'Domains',       'compass',        '{course,program}'),
    ('module',     'Modules',       'layers',         '{course,domain,program}'),
    ('week',       'Weeks',         'calendar-days',  '{module,course}'),
    ('session',    'Live sessions', 'radio',          '{week,module}'),
    ('topic',      'Topics',        'lightbulb',      '{module,session,course}'),
    ('instructor', 'Instructors',   'circle-user',    '{}'),
    ('process',    'Processes',     'workflow',       '{}')
) as v(key, plural, icon, parents)
where t.key = v.key;
update kb.node_types set plural = label || 's' where plural is null;
alter table kb.node_types alter column plural set not null;

-- Shape of one field definition. Kinds and their extra keys:
--   short_text long_text number date datetime duration url checkbox person
--   single_select / multi_select  -> options: [{value, label}] (non-empty)
--   reference                     -> ref_types: [type keys] (non-empty)
create or replace function kb.check_type_def() returns trigger
language plpgsql set search_path = pg_catalog, public
as $$
declare f jsonb; k text; keys text[] := '{}'; old_keys text[];
begin
    new.plural := coalesce(nullif(btrim(new.plural), ''), new.label || 's');
    for f in select * from jsonb_array_elements(new.fields) loop
        if jsonb_typeof(f) <> 'object' then
            raise exception 'each field must be an object' using errcode = 'check_violation', hint = 'kb_field_shape';
        end if;
        k := f->>'key';
        if k is null or k !~ '^[a-z][a-z0-9_]{0,40}$' then
            raise exception 'field key % must be lowercase letters, digits and _', coalesce(k, '(missing)')
                using errcode = 'check_violation', hint = 'kb_field_shape';
        end if;
        if k = any(keys) then
            raise exception 'field key % is used twice', k using errcode = 'check_violation', hint = 'kb_field_shape';
        end if;
        keys := keys || k;
        if coalesce(btrim(f->>'label'), '') = '' then
            raise exception 'field % needs a label', k using errcode = 'check_violation', hint = 'kb_field_shape';
        end if;
        if (f->>'kind') is null or (f->>'kind') not in ('short_text', 'long_text', 'number', 'date', 'datetime',
                'duration', 'url', 'single_select', 'multi_select', 'person', 'reference', 'checkbox') then
            raise exception 'field % has an unknown kind %', k, coalesce(f->>'kind', '(missing)')
                using errcode = 'check_violation', hint = 'kb_field_shape';
        end if;
        if (f->>'kind') in ('single_select', 'multi_select')
           and (jsonb_typeof(f->'options') is distinct from 'array' or jsonb_array_length(f->'options') = 0) then
            raise exception 'select field % needs at least one option', k using errcode = 'check_violation', hint = 'kb_field_shape';
        end if;
        if (f->>'kind') = 'reference'
           and (jsonb_typeof(f->'ref_types') is distinct from 'array' or jsonb_array_length(f->'ref_types') = 0) then
            raise exception 'reference field % must name the record types it may point at', k
                using errcode = 'check_violation', hint = 'kb_field_shape';
        end if;
    end loop;
    if tg_op = 'UPDATE' then
        if new.key <> old.key then
            raise exception 'a type key never changes (rename the label instead)'
                using errcode = 'check_violation', hint = 'kb_key_immutable';
        end if;
        select coalesce(array_agg(e->>'key'), '{}') into old_keys from jsonb_array_elements(old.fields) e;
        foreach k in array old_keys loop
            if not (k = any(keys)) then
                raise exception 'field % cannot be removed or re-keyed; archive it instead (its data is kept)', k
                    using errcode = 'check_violation', hint = 'kb_field_removed';
            end if;
        end loop;
    end if;
    return new;
end;
$$;
create trigger node_types_check_def before insert or update on kb.node_types
    for each row execute function kb.check_type_def();

-- Value check for one field. Returns an error message, or null when valid.
create or replace function kb.field_value_error(f jsonb, val jsonb) returns text
language plpgsql stable set search_path = pg_catalog, public
as $$
declare kind text := f->>'kind'; s text; e jsonb; t text;
begin
    if val is null or val = 'null'::jsonb then
        return null;
    end if;
    case kind
    when 'short_text', 'long_text' then
        if jsonb_typeof(val) <> 'string' then return 'must be text'; end if;
        if kind = 'short_text' and length(val #>> '{}') > 300 then return 'is longer than 300 characters'; end if;
        if length(val #>> '{}') > 20000 then return 'is too long'; end if;
    when 'number', 'duration' then
        if jsonb_typeof(val) <> 'number' then return 'must be a number'; end if;
        if kind = 'duration' and (val #>> '{}')::numeric < 0 then return 'cannot be negative'; end if;
    when 'checkbox' then
        if jsonb_typeof(val) <> 'boolean' then return 'must be true or false'; end if;
    when 'date' then
        s := val #>> '{}';
        if jsonb_typeof(val) <> 'string' or s !~ '^\d{4}-\d{2}-\d{2}$' then return 'must be a date (YYYY-MM-DD)'; end if;
        begin perform s::date; exception when others then return 'is not a real date'; end;
    when 'datetime' then
        s := val #>> '{}';
        if jsonb_typeof(val) <> 'string' then return 'must be a date and time'; end if;
        begin perform s::timestamptz; exception when others then return 'is not a valid date and time'; end;
    when 'url' then
        if jsonb_typeof(val) <> 'string' or (val #>> '{}') !~* '^https?://[^\s/$.?#][^\s]*$' then
            return 'must be an http(s) URL'; end if;
    when 'single_select' then
        if jsonb_typeof(val) <> 'string' or not exists (
            select 1 from jsonb_array_elements(f->'options') o where o->>'value' = val #>> '{}') then
            return 'is not one of the options'; end if;
    when 'multi_select' then
        if jsonb_typeof(val) <> 'array' then return 'must be a list'; end if;
        for e in select * from jsonb_array_elements(val) loop
            if not exists (select 1 from jsonb_array_elements(f->'options') o where o->>'value' = e #>> '{}') then
                return 'contains ' || (e #>> '{}') || ', which is not one of the options'; end if;
        end loop;
    when 'person' then
        s := val #>> '{}';
        if jsonb_typeof(val) <> 'string' or s !~* '^[0-9a-f-]{36}$' then return 'must be a person'; end if;
        -- Through kb.people() (definer): memberships are self-only under RLS.
        if not exists (select 1 from kb.people() p where p.user_id = s::uuid) then
            return 'is not a member of the knowledge base'; end if;
    when 'reference' then
        s := val #>> '{}';
        if jsonb_typeof(val) <> 'string' or s !~* '^[0-9a-f-]{36}$' then return 'must be a record'; end if;
        select t2.key into t from kb.nodes n join kb.node_types t2 on t2.id = n.type_id where n.id = s::uuid;
        if t is null then return 'points at a record that does not exist'; end if;
        if not exists (select 1 from jsonb_array_elements_text(f->'ref_types') r where r = t) then
            return 'must point at a ' || array_to_string(array(select jsonb_array_elements_text(f->'ref_types')), ' or ')
                   || ', not a ' || t; end if;
    else
        return 'has an unknown kind';
    end case;
    return null;
end;
$$;

create or replace function kb.check_node_props() returns trigger
language plpgsql set search_path = pg_catalog, public
as $$
declare f jsonb; err text; v jsonb;
begin
    if jsonb_typeof(new.props) <> 'object' then
        raise exception 'props must be an object' using errcode = 'check_violation', hint = 'kb_field_value';
    end if;
    for f in select e from kb.node_types t, jsonb_array_elements(t.fields) e
             where t.id = new.type_id and coalesce((e->>'archived')::boolean, false) = false loop
        v := new.props -> (f->>'key');
        err := kb.field_value_error(f, v);
        if err is not null then
            raise exception '% %', f->>'label', err using errcode = 'check_violation',
                hint = 'kb_field_value:' || (f->>'key');
        end if;
        if tg_op = 'INSERT' and coalesce((f->>'required')::boolean, false)
           and kb.actor_type() not in ('import', 'system')
           and (v is null or v = 'null'::jsonb or v = '""'::jsonb or v = '[]'::jsonb) then
            raise exception '% is required', f->>'label' using errcode = 'check_violation',
                hint = 'kb_field_required:' || (f->>'key');
        end if;
    end loop;
    return new;
end;
$$;
create trigger nodes_check_props before insert or update of props, type_id on kb.nodes
    for each row execute function kb.check_node_props();

-- ---------------------------------------------------------------------------
-- Records: review status, secondary owners
-- ---------------------------------------------------------------------------
alter table kb.nodes
    add column review_status text not null default 'none',
    add column co_owners     uuid[] not null default '{}',
    add constraint review_status_known check (review_status in ('none', 'needs_review', 'approved'));

-- ---------------------------------------------------------------------------
-- Relationship types: cardinality, core flag, outline order
-- ---------------------------------------------------------------------------
alter table kb.edge_types
    add column cardinality text not null default 'many_to_many',
    add column is_core boolean not null default false,
    add constraint cardinality_known check (cardinality in ('many_to_many', 'one_to_many', 'many_to_one', 'one_to_one'));
create unique index edge_types_label_unique on kb.edge_types (lower(label)) where archived_at is null;
update kb.edge_types set is_core = true;
alter table kb.edges add column position integer;

insert into kb.edge_types (key, label, inverse_label, description, is_core) values
    ('sme', 'subject expert for', 'has subject expert', 'A person who reviews or advises on the content', true)
on conflict (key) do nothing;
insert into kb.edge_type_rules (edge_type_id, source_type_id, target_type_id)
select e.id, s.id, t.id
from (values
    ('sme', 'instructor', 'course'), ('sme', 'instructor', 'module'), ('sme', 'instructor', 'session'),
    ('sme', 'instructor', 'domain'), ('sme', 'instructor', 'topic'),
    ('contains', 'course', 'domain'), ('contains', 'domain', 'module'), ('contains', 'module', 'session'),
    ('contains', 'session', 'topic'), ('contains', 'program', 'domain')
) as v(e, s, t)
join kb.edge_types e on e.key = v.e join kb.node_types s on s.key = v.s join kb.node_types t on t.key = v.t
on conflict (edge_type_id, source_type_id, target_type_id) do nothing;

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
    -- Cardinality: "one_to_many" = a target has at most one source of this type.
    if et.cardinality in ('one_to_many', 'one_to_one') and exists (
        select 1 from kb.edges e where e.edge_type_id = new.edge_type_id and e.target_id = new.target_id
          and e.archived_at is null and e.id <> new.id) then
        raise exception 'a record can have only one "%" relationship pointing at it', et.label
            using errcode = 'check_violation', hint = 'kb_cardinality';
    end if;
    if et.cardinality in ('many_to_one', 'one_to_one') and exists (
        select 1 from kb.edges e where e.edge_type_id = new.edge_type_id and e.source_id = new.source_id
          and e.archived_at is null and e.id <> new.id) then
        raise exception 'a record can have only one outgoing "%" relationship', et.label
            using errcode = 'check_violation', hint = 'kb_cardinality';
    end if;
    return new;
end;
$$;

-- ---------------------------------------------------------------------------
-- Link kinds (the service a URL lives on; auto-detected from URL patterns)
-- and resource content kinds (what the link IS).
-- ---------------------------------------------------------------------------
create table kb.link_kinds (
    id          uuid primary key default gen_random_uuid(),
    key         text not null unique,
    label       text not null,
    icon        text not null default 'link',
    patterns    text[] not null default '{}',
    defaults    jsonb not null default '{}'::jsonb,
    sort_order  integer not null default 100,
    is_core     boolean not null default false,
    created_by  uuid, updated_by uuid,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    version     integer not null default 1,
    status      text not null default 'active',
    archived_at timestamptz,
    constraint key_shape check (key ~ '^[a-z][a-z0-9_]{1,40}$'),
    constraint label_nonempty check (length(btrim(label)) > 0),
    constraint status_known check (status in ('active', 'archived'))
);
create unique index link_kinds_label_unique on kb.link_kinds (lower(label)) where archived_at is null;

create or replace function kb.check_link_kind() returns trigger
language plpgsql set search_path = pg_catalog, public
as $$
declare p text;
begin
    if tg_op = 'UPDATE' and new.key <> old.key then
        raise exception 'a link kind key never changes' using errcode = 'check_violation', hint = 'kb_key_immutable';
    end if;
    foreach p in array new.patterns loop
        begin
            perform '' ~ p;
        exception when others then
            raise exception 'URL pattern % is not a valid regular expression', p
                using errcode = 'check_violation', hint = 'kb_bad_pattern';
        end;
    end loop;
    return new;
end;
$$;
create trigger link_kinds_check before insert or update on kb.link_kinds
    for each row execute function kb.check_link_kind();
create trigger link_kinds_stamp before insert or update on kb.link_kinds
    for each row execute function kb.stamp();
create trigger link_kinds_audit after insert or update or delete on kb.link_kinds
    for each row execute function kb.audit();

-- UpLevel's domain is taken from the repo's own data (tests/test_source_links.py,
-- docs/ACCEPTANCE-CHECKLIST.md): uplevel.interviewkickstart.com.
insert into kb.link_kinds (key, label, icon, patterns, defaults, sort_order, is_core) values
    ('drive_folder', 'Drive folder', 'folder',           array['^https?://drive\.google\.com/drive/(u/[0-9]+/)?folders/'], '{"kind":"reference_doc"}', 10, true),
    ('drive_file',   'Drive file',   'file',             array['^https?://drive\.google\.com/(file/d/|open\?id=|uc\?)'], '{}', 20, true),
    ('doc',          'Doc',          'file-text',        array['^https?://docs\.google\.com/document/'], '{"kind":"reference_doc"}', 30, true),
    ('sheet',        'Sheet',        'file-spreadsheet', array['^https?://docs\.google\.com/spreadsheets/'], '{}', 40, true),
    ('slides',       'Slides',       'presentation',     array['^https?://docs\.google\.com/presentation/'], '{"kind":"kyp_slides"}', 50, true),
    ('uplevel',      'UpLevel',      'graduation-cap',   array['^https?://uplevel\.interviewkickstart\.com/'], '{}', 60, true),
    ('github',       'GitHub',       'github',           array['^https?://(www\.)?(github\.com|gist\.github\.com)/'], '{"kind":"solution"}', 70, true),
    ('video',        'YouTube / video', 'youtube',       array['^https?://(www\.)?(youtube\.com|youtu\.be|vimeo\.com|loom\.com)/'], '{"kind":"recording"}', 80, true),
    ('recording',    'Recording',    'video',            array['^https?://[a-z0-9.-]*zoom\.us/rec/'], '{"kind":"recording"}', 90, true),
    ('live_class',   'Live class link', 'radio',         array['^https?://[a-z0-9.-]*zoom\.us/(j|my)/', '^https?://meet\.google\.com/', '^https?://teams\.microsoft\.com/l/meetup-join'], '{"kind":"live_class_link"}', 100, true),
    ('website',      'Website',      'globe',            '{}', '{}', 1000, true);

alter table kb.resources
    add column link_kind text references kb.link_kinds(key) on update restrict on delete restrict,
    add column owner_id  uuid,
    add column tags      text[] not null default '{}';
alter table kb.resources drop constraint kind_known;
alter table kb.resources add constraint kind_known check (kind in
    ('link', 'doc', 'sheet', 'slides', 'video', 'pdf', 'folder', 'other',
     'recording', 'assignment', 'solution', 'repo',
     'kyp_slides', 'speaker_notes', 'live_class_link', 'assignment_brief', 'problem_statement',
     'evaluation_criteria', 'question_bank', 'interview_guide', 'reading', 'reference_doc'));

-- Classify existing resources by the seeded patterns (first match by sort order; else website).
update kb.resources r set link_kind = coalesce((
    select lk.key from kb.link_kinds lk, unnest(lk.patterns) p
    where r.url ~* p order by lk.sort_order limit 1), 'website')
where link_kind is null;

-- ---------------------------------------------------------------------------
-- Proposals: creates and type changes can be proposed too.
-- ---------------------------------------------------------------------------
alter table kb.proposals alter column target_id drop not null;
alter table kb.proposals drop constraint action_known;
alter table kb.proposals add constraint action_known check (action in ('archive', 'delete', 'create', 'type_change'));
alter table kb.proposals drop constraint table_known;
alter table kb.proposals add constraint table_known check (target_table in
    ('nodes', 'edges', 'resources', 'node_resources', 'node_types', 'edge_types', 'link_kinds'));
alter table kb.proposals add constraint target_needed check (action in ('create', 'type_change') or target_id is not null);

-- ---------------------------------------------------------------------------
-- Flags ("this is incorrect") assigned to the owner for review (D3)
-- ---------------------------------------------------------------------------
create table kb.flags (
    id           uuid primary key default gen_random_uuid(),
    target_table text not null,
    target_id    uuid not null,
    reason       text not null,
    assigned_to  uuid,
    resolution   text,
    resolved_by  uuid,
    resolved_at  timestamptz,
    created_by uuid, updated_by uuid,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    version    integer not null default 1,
    status     text not null default 'open',
    archived_at timestamptz,
    constraint table_known check (target_table in ('nodes', 'resources')),
    constraint status_known check (status in ('open', 'resolved', 'dismissed')),
    constraint reason_length check (length(btrim(reason)) between 1 and 2000)
);
create index flags_open_idx on kb.flags (target_id) where status = 'open';

-- ---------------------------------------------------------------------------
-- Templates (D4) and saved views (D6)
-- ---------------------------------------------------------------------------
create table kb.templates (
    id          uuid primary key default gen_random_uuid(),
    name        text not null,
    description text,
    root_type   text not null,
    structure   jsonb not null,
    source_id   uuid,
    created_by uuid, updated_by uuid,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    version    integer not null default 1,
    status     text not null default 'active',
    archived_at timestamptz,
    constraint name_nonempty check (length(btrim(name)) between 1 and 200),
    constraint status_known check (status in ('active', 'archived'))
);
create unique index templates_name_unique on kb.templates (lower(name)) where archived_at is null;

create table kb.saved_views (
    id          uuid primary key default gen_random_uuid(),
    name        text not null,
    owner_id    uuid not null,
    shared      boolean not null default false,
    config      jsonb not null default '{}'::jsonb,
    position    integer not null default 0,
    created_by uuid, updated_by uuid,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    version    integer not null default 1,
    status     text not null default 'active',
    archived_at timestamptz,
    constraint name_nonempty check (length(btrim(name)) between 1 and 80),
    constraint status_known check (status in ('active', 'archived'))
);

do $$
declare t text;
begin
    foreach t in array array['flags', 'templates', 'saved_views'] loop
        execute format('create trigger %I before insert or update on kb.%I for each row execute function kb.stamp()', t || '_stamp', t);
        execute format('create trigger %I after insert or update or delete on kb.%I for each row execute function kb.audit()', t || '_audit', t);
    end loop;
end $$;

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------
alter table kb.link_kinds  enable row level security;
alter table kb.flags       enable row level security;
alter table kb.templates   enable row level security;
alter table kb.saved_views enable row level security;

create policy link_kinds_select on kb.link_kinds for select to authenticated using ((select kb.role_at_least('viewer')));
create policy link_kinds_admin  on kb.link_kinds for all to authenticated
    using ((select kb.role_at_least('admin'))) with check ((select kb.role_at_least('admin')));

-- Anyone who can read can flag; the assignee, the flagger or an editor resolves.
create policy flags_select on kb.flags for select to authenticated using ((select kb.role_at_least('viewer')));
create policy flags_insert on kb.flags for insert to authenticated
    with check ((select kb.role_at_least('viewer')) and status = 'open');
create policy flags_update on kb.flags for update to authenticated
    using ((select kb.role_at_least('editor')) or assigned_to = (select auth.uid()) or created_by = (select auth.uid()))
    with check ((select kb.role_at_least('editor')) or assigned_to = (select auth.uid()) or created_by = (select auth.uid()));

create policy templates_select on kb.templates for select to authenticated using ((select kb.role_at_least('viewer')));
create policy templates_write  on kb.templates for all to authenticated
    using ((select kb.role_at_least('editor'))) with check ((select kb.role_at_least('editor')));

-- Saved views: your own, plus shared ones; only the owner changes a view.
create policy saved_views_select on kb.saved_views for select to authenticated
    using ((select kb.role_at_least('viewer')) and (owner_id = (select auth.uid()) or shared));
create policy saved_views_own on kb.saved_views for all to authenticated
    using (owner_id = (select auth.uid())) with check (owner_id = (select auth.uid()) and (select kb.role_at_least('viewer')));

-- Contributors no longer insert records directly: their creates are proposals
-- (an editor approves). Enforced here so no client can bypass the service.
drop policy nodes_insert on kb.nodes;
create policy nodes_insert on kb.nodes for insert to authenticated
    with check ((select kb.role_at_least('editor')));

grant select, insert, update, delete on kb.link_kinds, kb.flags, kb.templates, kb.saved_views to authenticated;
grant execute on function kb.field_value_error(jsonb, jsonb) to authenticated;
