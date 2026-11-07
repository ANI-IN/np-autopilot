-- 0041 down: only rule / record exclusions (the key exclusions go).
delete from kb.sync_exclusions where unit in ('relationship', 'link', 'attachment');
alter table kb.sync_exclusions drop constraint if exists sync_exclusions_unit_check;
alter table kb.sync_exclusions add constraint sync_exclusions_unit_check check (unit in ('rule', 'record'));
