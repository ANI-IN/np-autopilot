-- 0038 (2026-11-07, Phase 1 performance): kb.changes(at, table_name).
-- Additive, no data change; 0038 down drops it.
--
-- The dashboard's "changed in 7 days" count and the sidebar totals filter the
-- change feed by time and table. kb.changes had only its primary key, so each
-- call scanned the whole feed (17,000+ rows on the real data, and it only grows).
create index if not exists changes_at_table_idx on kb.changes (at, table_name);
