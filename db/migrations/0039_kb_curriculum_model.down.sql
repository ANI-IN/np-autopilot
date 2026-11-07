-- 0039 down: restore the pre-run-C model. Data converted by scripts/curriculum_model_data.py is
-- reverted by that script's `revert` command, which must run BEFORE this down migration.
alter table kb.nodes drop column search;
alter table kb.nodes add column search tsvector generated always as (
    setweight(to_tsvector('simple', coalesce(name, '')), 'A') ||
    setweight(to_tsvector('simple', coalesce(summary, '')), 'B') ||
    setweight(to_tsvector('simple', coalesce(body, '')), 'C')) stored;
create index nodes_search_idx on kb.nodes using gin (search);
alter table kb.nodes drop column if exists search_aliases;

drop trigger if exists nodes_owner_records on kb.nodes;
drop function if exists kb.check_owner_records();
drop trigger if exists edges_sme_role on kb.edges;
drop function if exists kb.check_sme_role();

update kb.node_types set allowed_parents = '{course,domain,program}' where key = 'module';
update kb.node_types set allowed_parents = '{module,week}' where key = 'session';
update kb.node_types set allowed_parents = '{program}' where key = 'course';
update kb.node_types set allowed_parents = '{course,program}' where key = 'domain';
update kb.node_types set allowed_parents = '{module,session,course}' where key = 'topic';

-- un-retire the rules 0039 archived
update kb.edge_type_rules r set archived_at = null
from kb.edge_types e, kb.node_types s, kb.node_types t
where r.edge_type_id = e.id and r.source_type_id = s.id and r.target_type_id = t.id and r.archived_at is not null
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

-- remove the rules 0039 added (only where no live edge uses them)
delete from kb.edge_type_rules r
using kb.edge_types e, kb.node_types s, kb.node_types t
where r.edge_type_id = e.id and r.source_type_id = s.id and r.target_type_id = t.id
  and (e.key, s.key, t.key) in (
    ('in_domain', 'program', 'domain'), ('in_domain', 'course', 'domain'), ('in_domain', 'module', 'domain'),
    ('variant_of', 'module', 'module'),
    ('owned_by', 'program', 'team_member'), ('owned_by', 'course', 'team_member'), ('owned_by', 'module', 'team_member'),
    ('teaches', 'instructor', 'program'), ('covers', 'topic', 'concept'), ('covers', 'module', 'concept'))
  and not exists (select 1 from kb.edges x join kb.nodes a on a.id = x.source_id join kb.nodes b on b.id = x.target_id
                  where x.edge_type_id = e.id and a.type_id = s.id and b.type_id = t.id);
delete from kb.edge_types e where e.key in ('in_domain', 'variant_of')
  and not exists (select 1 from kb.edges x where x.edge_type_id = e.id)
  and not exists (select 1 from kb.edge_type_rules r where r.edge_type_id = e.id);
delete from kb.node_types where key = 'concept' and not exists (select 1 from kb.nodes n where n.type_id = kb.node_types.id);
