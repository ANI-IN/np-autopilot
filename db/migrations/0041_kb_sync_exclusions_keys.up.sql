-- 0041 (run C, 2026-11-07): the sync's exclusions also name relationships, links and attachments.
-- scripts/cleanup_obsolete.py removes obsolete relationships and links whose two records stay (for example
-- a program's old direct link to a module that the KYPs now place in a course). Without an exclusion the
-- next sync would write them again from the old projection tables. unit = the sync_map unit, key = its key.
alter table kb.sync_exclusions drop constraint if exists sync_exclusions_unit_check;
alter table kb.sync_exclusions add constraint sync_exclusions_unit_check
    check (unit in ('rule', 'record', 'relationship', 'link', 'attachment'));
