-- 0034 down: drop the run-6 performance indexes. Nothing depends on them.
drop index if exists kb.edges_target_all_idx;
drop index if exists kb.edges_source_all_idx;
