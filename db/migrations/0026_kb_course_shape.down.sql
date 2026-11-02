-- Reverses 0026. Refuses, rather than destroys, when data already uses what it
-- added: archive or re-type those records and resources first.
do $$
begin
    if exists (select 1 from kb.nodes n join kb.node_types t on t.id = n.type_id
               where t.key in ('domain', 'week', 'session')) then
        raise exception '0026 down: records of type domain/week/session exist; remove them first';
    end if;
    if exists (select 1 from kb.resources
               where kind in ('recording', 'assignment', 'solution', 'repo')) then
        raise exception '0026 down: resources of kind recording/assignment/solution/repo exist; re-kind them first';
    end if;
end $$;

drop function if exists kb.people();
drop table if exists kb.link_checks;

alter table kb.resources drop constraint kind_known;
alter table kb.resources add constraint kind_known check (kind in
    ('link', 'doc', 'sheet', 'slides', 'video', 'pdf', 'folder', 'other'));

-- Rules go with their types (on delete cascade).
delete from kb.node_types where key in ('domain', 'week', 'session');
