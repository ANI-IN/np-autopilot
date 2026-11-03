-- 0034 down: drop the run-6 performance indexes. Nothing depends on them.
drop index if exists kb.edges_target_all_idx;
drop index if exists kb.edges_source_all_idx;
drop trigger if exists keep_an_admin on kb.memberships;
drop function if exists kb.keep_an_admin();
drop trigger if exists refuse_ai on kb.memberships;
drop trigger if exists refuse_ai on kb.person_accounts;
drop trigger if exists refuse_ai_delete on kb.nodes;
drop trigger if exists refuse_ai_delete on kb.edges;
drop trigger if exists refuse_ai_delete on kb.resources;
drop function if exists kb.refuse_ai_admin();
