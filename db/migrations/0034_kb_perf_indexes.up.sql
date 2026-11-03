-- 0034 (run 6, B5): indexes that measurably pay off at real-data size
-- (docs/run6/PERF.md). Additive; 0034 down drops them.
--
-- kb.edges had only PARTIAL indexes on its ends (where archived_at is null).
-- Any read that includes archived relationships -- GET /api/kb/graph with
-- archived=1 (every record's degree counts archived edges then), focus mode
-- with archived=1, a record's history and delete impact, the Archived page --
-- fell back to a sequential scan of kb.edges PER RECORD: 1.0-1.4 s for the
-- graph with archived=1 on the real data. These two cover both cases; the
-- partial ones stay (smaller, and preferred for live-only reads).
create index if not exists edges_source_all_idx on kb.edges (source_id);
create index if not exists edges_target_all_idx on kb.edges (target_id);
