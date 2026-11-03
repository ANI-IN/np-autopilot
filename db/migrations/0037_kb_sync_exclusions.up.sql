-- 0037 (run 6 resume, R3): the sync's permanent exclusions, for the owner-approved
-- permanent deletion of the legacy domains and legacy modules
-- (web/lib/kb/legacy_delete.py, pipeline/kb_legacy_delete.py).
--   unit = 'rule': a rule switched on (key 'np_legacy_domains_modules': the sync
--                  leaves out every domain NP Autopilot does not count as current
--                  and every legacy module, by NP's own logic);
--   unit = 'record': one source row (NP id) the sync must never create again.
-- The old tables (public.*) are not touched.
create table kb.sync_exclusions (
    unit       text not null check (unit in ('rule', 'record')),
    key        text not null,
    reason     text not null,
    created_at timestamptz not null default now(),
    primary key (unit, key)
);
alter table kb.sync_exclusions enable row level security;
-- Admins may read it (Settings -> Sync shows the rule); only the owner (the CLI,
-- the sync) writes it.
create policy sync_exclusions_admin_select on kb.sync_exclusions for select to authenticated
    using ((select kb.role_at_least('admin')));
grant select on kb.sync_exclusions to authenticated;
revoke insert, update, delete on kb.sync_exclusions from authenticated, anon;
