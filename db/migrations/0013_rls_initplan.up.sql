-- 0013 — evaluate np_role() ONCE per query instead of once per row.
--
-- FOUND BY THE G4 LATENCY MEASUREMENT, and it is not what the measurement
-- first looked like. Search measured 40.7 ms of server-side execution while
-- every other endpoint was under 3 ms, so migration 0013 added a trigram index
-- on the assumption that `label ILIKE '%q%'` was the cost. It changed nothing.
-- The plan says why:
--
--   Seq Scan on nodes  (actual time=11.553..40.578 rows=2)
--     Filter: (((sensitive AND (np_role() = ANY ('{recruiting,admin}')))
--              OR ((NOT sensitive) AND (np_role() <> 'none')))
--             AND (label ~~* '%karthika%'))
--     Rows Removed by Filter: 3144
--
-- The RLS predicate runs FIRST, and `np_role()` is called once PER ROW — 3,146
-- calls, each doing its own lookup in `profiles`. The ILIKE was never the
-- problem; the policy was.
--
-- `np_role()` is STABLE, not IMMUTABLE — correctly, since it depends on session
-- state — so the planner will not fold it to a constant. Wrapping it in a
-- scalar subquery with no correlated reference makes it an InitPlan, which
-- Postgres evaluates exactly once per statement.
--
-- The rule this generalises to: in an RLS policy, a function that reads session
-- state should be written `(select f())`, not `f()`. The two are identical in
-- meaning and differ by a factor of the table's row count in cost.
--
-- NOTHING ABOUT WHO SEES WHAT CHANGES HERE. Each policy below is the existing
-- definition with the call wrapped; the test suite that proves the role
-- boundary is unchanged and must still pass.
--
-- AND THE TRIGRAM INDEX IS STILL NOT WANTED, now that the real cost is gone.
-- With np_role() evaluated once, search is 4.62 ms and the planner still
-- chooses a sequential scan: at 3,146 rows a scan beats a GIN lookup plus heap
-- fetches, and it is right to. Revisit if the projected graph grows by an order
-- of magnitude; do not add the index back on the strength of the word "index".


drop policy if exists curation_notes_admin_all on curation_notes;
create policy curation_notes_admin_all on curation_notes
    for all to authenticated
    using (((select np_role()) = 'admin'::text))
    with check (((select np_role()) = 'admin'::text));

drop policy if exists domain_aliases_admin_all on domain_aliases;
create policy domain_aliases_admin_all on domain_aliases
    for all to authenticated
    using (((select np_role()) = 'admin'::text))
    with check (((select np_role()) = 'admin'::text));

drop policy if exists edge_rels_select on edge_rels;
create policy edge_rels_select on edge_rels
    for select to authenticated
    using (((select np_role()) <> 'none'::text));

drop policy if exists edges_select on edges;
create policy edges_select on edges
    for select to authenticated
    using ((((select np_role()) <> 'none'::text) AND (EXISTS ( SELECT 1 FROM nodes n WHERE (n.id = edges.source_id))) AND (EXISTS ( SELECT 1 FROM nodes n WHERE (n.id = edges.target_id)))));

drop policy if exists files_select on files;
create policy files_select on files
    for select to authenticated
    using (((select np_role()) <> 'none'::text));

drop policy if exists node_sources_select on node_sources;
create policy node_sources_select on node_sources
    for select to authenticated
    using ((((select np_role()) <> 'none'::text) AND (EXISTS ( SELECT 1 FROM nodes n WHERE (n.id = node_sources.node_id)))));

drop policy if exists node_types_select on node_types;
create policy node_types_select on node_types
    for select to authenticated
    using (((select np_role()) <> 'none'::text));

drop policy if exists nodes_member_select on nodes;
create policy nodes_member_select on nodes
    for select to authenticated
    using (((NOT sensitive) AND ((select np_role()) <> 'none'::text)));

drop policy if exists nodes_recruiting_select on nodes;
create policy nodes_recruiting_select on nodes
    for select to authenticated
    using ((sensitive AND (select np_can_see_sensitive())));

drop policy if exists people_admin_all on people;
create policy people_admin_all on people
    for all to authenticated
    using (((select np_role()) = 'admin'::text))
    with check (((select np_role()) = 'admin'::text));

drop policy if exists people_aliases_admin_all on people_aliases;
create policy people_aliases_admin_all on people_aliases
    for all to authenticated
    using (((select np_role()) = 'admin'::text))
    with check (((select np_role()) = 'admin'::text));

drop policy if exists projection_meta_select on projection_meta;
create policy projection_meta_select on projection_meta
    for select to authenticated
    using (((select np_role()) <> 'none'::text));

drop policy if exists workflow_owners_admin_all on workflow_owners;
create policy workflow_owners_admin_all on workflow_owners
    for all to authenticated
    using (((select np_role()) = 'admin'::text))
    with check (((select np_role()) = 'admin'::text));
