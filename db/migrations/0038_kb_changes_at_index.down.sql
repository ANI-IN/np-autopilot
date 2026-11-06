-- 0038 down: drop the change-feed time index. Nothing depends on it.
drop index if exists kb.changes_at_table_idx;
