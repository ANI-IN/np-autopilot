-- 0026 — the shape of an IK course, link health, and owner names.
--
-- Additive only: three node types and their rules, four resource kinds, one
-- new table, one function. Nothing existing is altered except a CHECK that is
-- widened (every value it accepted before is still accepted).
--
--   domain   a subject area a course covers (e.g. "Machine Learning")
--   week     a week of a course's schedule, inside a module
--   session  a live session in a week; instructors teach it
--
-- kb.link_checks holds the LAST result of checking each resource's URL. It is a
-- separate table, not columns on kb.resources, because a resource update bumps
-- its version: a link check running while someone edits the resource would
-- otherwise hand that person a spurious "this record changed" conflict.
--
-- kb.people() lets any KB member see who the members are (id + email), so a
-- record's owner can be shown by name. Profiles and memberships stay
-- self-only under RLS; this definer function is the one narrow window.

insert into kb.node_types (key, label, color, is_container, sort_order, description) values
    ('domain',  'Domain',       '#4f46e5', false, 15, 'A subject area a course covers, e.g. Machine Learning'),
    ('week',    'Week',         '#0d9488', false, 32, 'One week of a course schedule'),
    ('session', 'Live session', '#ea580c', false, 34, 'A scheduled live class within a week')
on conflict (key) do nothing;

insert into kb.edge_type_rules (edge_type_id, source_type_id, target_type_id)
select e.id, s.id, t.id
from (values
    ('covers', 'course', 'domain'),   ('covers', 'program', 'domain'),
    ('contains', 'module', 'week'),   ('contains', 'course', 'week'),
    ('contains', 'week', 'session'),  ('teaches', 'instructor', 'session'),
    ('covers', 'session', 'topic'),   ('related', 'domain', 'domain')
) as v(e, s, t)
join kb.edge_types e on e.key = v.e
join kb.node_types s on s.key = v.s
join kb.node_types t on t.key = v.t
on conflict (edge_type_id, source_type_id, target_type_id) do nothing;

alter table kb.resources drop constraint kind_known;
alter table kb.resources add constraint kind_known check (kind in
    ('link', 'doc', 'sheet', 'slides', 'video', 'pdf', 'folder', 'other',
     'recording', 'assignment', 'solution', 'repo'));

create table kb.link_checks (
    resource_id uuid primary key references kb.resources(id) on delete cascade,
    status      text not null,
    http_status integer,
    final_url   text,
    checked_at  timestamptz not null default now(),
    checked_by  uuid,
    constraint link_status_known check (status in
        ('ok', 'needs_auth', 'forbidden', 'broken', 'timeout', 'unreachable'))
);

alter table kb.link_checks enable row level security;
create policy link_checks_read on kb.link_checks for select to authenticated
    using (kb.role_at_least('viewer'));
create policy link_checks_write on kb.link_checks for all to authenticated
    using (kb.role_at_least('editor')) with check (kb.role_at_least('editor'));
grant select, insert, update, delete on kb.link_checks to authenticated;

create or replace function kb.people() returns table (user_id uuid, email text, role text)
language sql stable security definer set search_path = pg_catalog, public
as $$
    select m.user_id, p.email, m.role
      from kb.memberships m join public.profiles p on p.user_id = m.user_id
     where m.archived_at is null and kb.role_at_least('viewer')
     order by p.email
$$;
revoke all on function kb.people() from public;
grant execute on function kb.people() to authenticated;
