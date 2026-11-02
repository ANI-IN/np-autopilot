-- Reverses 0027. Refuses, rather than destroys, when data already uses what it
-- added: custom fields with values, custom types, new resource kinds, flags,
-- templates, saved views, create/type-change proposals, SME relationships.
do $$
begin
    if exists (select 1 from kb.node_types where jsonb_array_length(fields) > 0) then
        raise exception '0027 down: record types define custom fields; remove them first';
    end if;
    if exists (select 1 from kb.node_types where not is_core) then
        raise exception '0027 down: custom record types exist; archive and delete them first';
    end if;
    if exists (select 1 from kb.resources where kind in ('kyp_slides', 'speaker_notes', 'live_class_link',
               'assignment_brief', 'problem_statement', 'evaluation_criteria', 'question_bank',
               'interview_guide', 'reading', 'reference_doc')) then
        raise exception '0027 down: resources use content kinds added by 0027; re-kind them first';
    end if;
    if exists (select 1 from kb.resources where owner_id is not null or tags <> '{}') then
        raise exception '0027 down: resources carry owners or tags; clear them first';
    end if;
    if exists (select 1 from kb.nodes where review_status <> 'none' or co_owners <> '{}') then
        raise exception '0027 down: records carry review status or secondary owners; clear them first';
    end if;
    if exists (select 1 from kb.flags) or exists (select 1 from kb.templates) or exists (select 1 from kb.saved_views) then
        raise exception '0027 down: flags, templates or saved views exist; remove them first';
    end if;
    if exists (select 1 from kb.proposals where action in ('create', 'type_change')) then
        raise exception '0027 down: create/type-change proposals exist; remove them first';
    end if;
    if exists (select 1 from kb.edges e join kb.edge_types t on t.id = e.edge_type_id where t.key = 'sme') then
        raise exception '0027 down: "subject expert" relationships exist; remove them first';
    end if;
end $$;

drop policy nodes_insert on kb.nodes;
create policy nodes_insert on kb.nodes for insert to authenticated
    with check ((select kb.role_at_least('contributor')));

drop table kb.saved_views;
drop table kb.templates;
drop table kb.flags;

alter table kb.proposals drop constraint target_needed;
alter table kb.proposals drop constraint table_known;
alter table kb.proposals add constraint table_known check (target_table in ('nodes', 'edges', 'resources', 'node_resources'));
alter table kb.proposals drop constraint action_known;
alter table kb.proposals add constraint action_known check (action in ('archive', 'delete'));
alter table kb.proposals alter column target_id set not null;

alter table kb.resources drop constraint kind_known;
alter table kb.resources add constraint kind_known check (kind in
    ('link', 'doc', 'sheet', 'slides', 'video', 'pdf', 'folder', 'other',
     'recording', 'assignment', 'solution', 'repo'));
alter table kb.resources drop column link_kind, drop column owner_id, drop column tags;
drop table kb.link_kinds;
drop function kb.check_link_kind();

-- The rules 0027 added (the edges using them were refused above only for sme;
-- contains edges on the new pairs are archived-or-absent in a clean rollback).
delete from kb.edge_type_rules r using kb.edge_types e, kb.node_types s, kb.node_types t
where r.edge_type_id = e.id and r.source_type_id = s.id and r.target_type_id = t.id
  and (e.key, s.key, t.key) in (('contains', 'course', 'domain'), ('contains', 'domain', 'module'),
       ('contains', 'module', 'session'), ('contains', 'session', 'topic'), ('contains', 'program', 'domain'))
  and not exists (select 1 from kb.edges x join kb.nodes a on a.id = x.source_id join kb.nodes b on b.id = x.target_id
                  where x.edge_type_id = e.id and a.type_id = s.id and b.type_id = t.id);
delete from kb.edge_types where key = 'sme';

-- check_edge as 0022 defined it (no cardinality).
create or replace function kb.check_edge() returns trigger
language plpgsql set search_path = pg_catalog, public
as $$
declare
    s record; t record; et record;
begin
    if new.archived_at is not null then
        return new;
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
alter table kb.edges drop column position;
drop index kb.edge_types_label_unique;
alter table kb.edge_types drop constraint cardinality_known, drop column cardinality, drop column is_core;

alter table kb.nodes drop constraint review_status_known, drop column review_status, drop column co_owners;

drop trigger nodes_check_props on kb.nodes;
drop function kb.check_node_props();
drop function kb.field_value_error(jsonb, jsonb);
drop trigger node_types_check_def on kb.node_types;
drop function kb.check_type_def();
drop index kb.node_types_label_unique;
alter table kb.node_types
    drop constraint default_status_known, drop constraint owner_rule_known,
    drop constraint fields_is_array, drop constraint label_nonempty,
    drop column plural, drop column fields, drop column allowed_parents, drop column parent_required,
    drop column default_status, drop column owner_rule, drop column is_core;
