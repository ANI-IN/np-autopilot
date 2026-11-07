-- 0039 (run C, 2026-11-07): the curriculum model, owners and SMEs, week-agnostic.
--
-- Owner decisions (2026-11-07):
--   Program -> Course -> Module -> Topic -> Concept -> Resource.
--   A DOMAIN CLASSIFIES programs, courses and modules (relationship in_domain); it is not a container.
--   Module variants link to one canonical module (variant_of).
--   OWNER = an NP team member responsible for a program, course or module (owned_by -> team_member,
--   many-to-many). Never an instructor.
--   SME = an instructor who teaches a module (sme instructor -> module, many-to-many) with a REQUIRED
--   role: 'primary', 'backup' (rank 1, 2 or 3) or another role named in the sources. Several
--   primaries on one module are allowed (the sources have them) and flagged by Data quality.
--   Completely week-agnostic: no week records or relationships; a program-specific schedule may live
--   only as optional data on the program's links (edges.props.schedule).
--
-- Data changes are NOT here (they need the backup / export sequence); scripts/curriculum_model_data.py
-- converts DEV and local data. This migration only changes the model and refuses bad writes.

-- 1. concept: tools and technologies for now ---------------------------------------------------------
insert into kb.node_types (key, label, plural, color, icon, is_container, sort_order, shape, description, owner_expected)
values ('concept', 'Concept', 'Concepts', '#7c3aed', 'sparkles', false, 45, 'tag',
        'A tool, technology or idea a topic or module uses (tools and technologies for now)', false)
on conflict (key) do update set archived_at = null, status = 'active';

-- 1b. NP team members and the owner relationship exist in every database, not only where the sync
--     created them (a database built from the migrations alone has neither).
insert into kb.node_types (key, label, plural, color, icon, is_container, sort_order, shape, description, owner_expected)
values ('team_member', 'Team member', 'Team members', '#475569', 'users', false, 100, 'ellipse',
        'A member of the Interview Kickstart New Programs team (an owner of programs, courses and modules)', false)
on conflict (key) do nothing;
insert into kb.edge_types (key, label, inverse_label, description, is_core, color, line_style)
select 'owned_by', 'owned by', 'owns', 'An NP team member responsible for a program, course or module', true, '#1d4ed8', 'solid'
where not exists (select 1 from kb.edge_types where key = 'owned_by');

-- Part of the model now, so core (a database where the sync created team_member had it as custom).
update kb.node_types set is_core = true where key in ('team_member', 'concept');
update kb.edge_types set is_core = true where key = 'owned_by';

-- 2. new relationship types -------------------------------------------------------------------------
insert into kb.edge_types (key, label, inverse_label, description, is_core, color, line_style)
select * from (values
    ('in_domain', 'in domain', 'classifies', 'The domain a program, course or module belongs to (a classification)', true, '#0e7490', 'dotted'),
    ('variant_of', 'variant of', 'has variant', 'A program-specific version of a canonical module', true, '#64748b', 'dashed')
) v(key, label, inverse_label, description, is_core, color, line_style)
where not exists (select 1 from kb.edge_types e where e.key = v.key);
update kb.edge_types set archived_at = null, status = 'active' where key in ('in_domain', 'variant_of') and archived_at is not null;

-- 3. rules: add the model's pairs, retire the old ones ----------------------------------------------
insert into kb.edge_type_rules (edge_type_id, source_type_id, target_type_id)
select e.id, s.id, t.id
from (values
    ('in_domain', 'program', 'domain'), ('in_domain', 'course', 'domain'), ('in_domain', 'module', 'domain'),
    ('variant_of', 'module', 'module'),
    ('owned_by', 'program', 'team_member'), ('owned_by', 'course', 'team_member'), ('owned_by', 'module', 'team_member'),
    ('teaches', 'instructor', 'program'),
    ('covers', 'topic', 'concept'), ('covers', 'module', 'concept'),
    ('contains', 'program', 'course'), ('contains', 'course', 'module'), ('contains', 'program', 'module'),
    ('contains', 'module', 'topic')
) as v(edge, src, tgt)
join kb.edge_types e on e.key = v.edge
join kb.node_types s on s.key = v.src
join kb.node_types t on t.key = v.tgt
where not exists (select 1 from kb.edge_type_rules r where r.edge_type_id = e.id and r.source_type_id = s.id
                    and r.target_type_id = t.id and r.archived_at is null);

-- Retired pairs (archived, not deleted: the down migration restores them). Existing edges of these
-- shapes are converted by the data script; the check trigger refuses NEW ones from now on.
update kb.edge_type_rules r set archived_at = now()
from kb.edge_types e, kb.node_types s, kb.node_types t
where r.edge_type_id = e.id and r.source_type_id = s.id and r.target_type_id = t.id and r.archived_at is null
  and (e.key, s.key, t.key) in (
    ('contains', 'module', 'week'), ('contains', 'week', 'session'), ('contains', 'course', 'week'),
    ('contains', 'theme', 'process'),
    ('contains', 'program', 'domain'), ('contains', 'domain', 'module'), ('contains', 'course', 'domain'),
    ('covers', 'program', 'domain'), ('covers', 'course', 'domain'),
    ('sme', 'instructor', 'session'), ('sme', 'instructor', 'topic'), ('sme', 'instructor', 'domain'),
    ('sme', 'instructor', 'course'),
    ('teaches', 'instructor', 'module'),
    ('owned_by', 'domain', 'team_member'),
    ('related', 'process', 'course'), ('related', 'process', 'process'), ('related', 'process', 'program'));

-- A module's parents are a course or a program; a session's a module. Never a week or a domain.
update kb.node_types set allowed_parents = '{course,program}' where key = 'module';
update kb.node_types set allowed_parents = '{module}' where key = 'session';
update kb.node_types set allowed_parents = '{program}' where key = 'course';
update kb.node_types set allowed_parents = '{}' where key = 'domain';
update kb.node_types set allowed_parents = '{module}' where key = 'topic';
update kb.node_types set allowed_parents = '{topic,module}' where key = 'concept';

-- 4. SME roles, enforced --------------------------------------------------------------------------------
-- props.role: 'primary' | 'backup' (with props.rank 1..3) | another role named in the sources (free text,
-- up to 60 characters). Normalised: role lower-case, rank an integer.
create or replace function kb.check_sme_role() returns trigger
language plpgsql set search_path = pg_catalog, public
as $$
declare
    k text; role text; rnk int;
begin
    if new.archived_at is not null then
        return new;
    end if;
    select key into k from kb.edge_types where id = new.edge_type_id;
    if k is distinct from 'sme' then
        return new;
    end if;
    role := lower(btrim(coalesce(new.props->>'role', '')));
    if role = '' then
        raise exception 'an SME assignment needs a role (primary, backup or a named role)'
            using errcode = 'check_violation', hint = 'kb_sme_role_required';
    end if;
    if role = 'backup' then
        begin
            rnk := (new.props->>'rank')::int;
        exception when others then
            rnk := null;
        end;
        if rnk is null or rnk not between 1 and 3 then
            raise exception 'a backup SME needs an order of 1, 2 or 3'
                using errcode = 'check_violation', hint = 'kb_sme_backup_rank';
        end if;
        new.props := jsonb_set(jsonb_set(new.props, '{role}', '"backup"'), '{rank}', to_jsonb(rnk));
    elsif role = 'primary' then
        new.props := jsonb_set(new.props - 'rank', '{role}', '"primary"');
    else
        if length(role) > 60 then
            raise exception 'an SME role name is at most 60 characters' using errcode = 'check_violation',
                hint = 'kb_sme_role_required';
        end if;
        new.props := new.props - 'rank';
    end if;
    -- Not unique on purpose: the sources list two primaries on some modules (and two first backups on
    -- one). That is reported by Data quality ("several primary SMEs"), never silently rewritten.
    return new;
end;
$$;
drop trigger if exists edges_sme_role on kb.edges;
create trigger edges_sme_role before insert or update on kb.edges
    for each row execute function kb.check_sme_role();

-- 5. Owners are NP team members, never instructors ----------------------------------------------------
-- owned_by is limited to team_member targets by the rules above. The older "owner by role" columns
-- (owner_record_id, co_owner_record_ids, run 5) held instructors; they may now point only at team
-- members, and the data script moves the instructor values to SME assignments.
create or replace function kb.check_owner_records() returns trigger
language plpgsql set search_path = pg_catalog, public
as $$
declare bad int;
begin
    if new.owner_record_id is null and cardinality(new.co_owner_record_ids) = 0 then
        return new;
    end if;
    if tg_op = 'UPDATE' and new.owner_record_id is not distinct from old.owner_record_id
       and new.co_owner_record_ids = old.co_owner_record_ids then
        return new;                 -- untouched (rows written before 0039 are converted by the data script)
    end if;
    select count(*) into bad
      from unnest(array_remove(array[new.owner_record_id] || new.co_owner_record_ids, null)) as x(id)
      left join kb.nodes n on n.id = x.id
      left join kb.node_types t on t.id = n.type_id
     where t.key is distinct from 'team_member';
    if bad > 0 then
        raise exception 'an owner must be an NP team member record, not an instructor or another record'
            using errcode = 'check_violation', hint = 'kb_owner_team_member';
    end if;
    return new;
end;
$$;
drop trigger if exists nodes_owner_records on kb.nodes;
create trigger nodes_owner_records before insert or update of owner_record_id, co_owner_record_ids on kb.nodes
    for each row execute function kb.check_owner_records();

-- 6. Hidden search aliases ---------------------------------------------------------------------------
-- Old names (SD1-SD4, the long domain names) are searchable but never displayed: they live in
-- search_aliases (space-separated), which only the search vector reads. No API returns it for display.
alter table kb.nodes add column search_aliases text not null default '';
alter table kb.nodes drop column search;
alter table kb.nodes add column search tsvector generated always as (
    setweight(to_tsvector('simple', coalesce(name, '')), 'A') ||
    setweight(to_tsvector('simple', coalesce(search_aliases, '')), 'A') ||
    setweight(to_tsvector('simple', coalesce(summary, '')), 'B') ||
    setweight(to_tsvector('simple', coalesce(body, '')), 'C')) stored;
create index nodes_search_idx on kb.nodes using gin (search);

-- 7. Week-agnostic --------------------------------------------------------------------------------------
-- The week type stays archived (2026-11-07 B); no record type may require a week field.
update kb.node_types set archived_at = coalesce(archived_at, now()) where key in ('week', 'theme', 'process');
