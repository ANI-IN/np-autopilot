-- Restores per-row evaluation of np_role().
-- Identical access, ~40ms of avoidable CPU per scan of `nodes`.

drop policy if exists curation_notes_admin_all on curation_notes;
create policy curation_notes_admin_all on curation_notes
    for all to authenticated
    using ((np_role() = 'admin'::text))
    with check ((np_role() = 'admin'::text));

drop policy if exists domain_aliases_admin_all on domain_aliases;
create policy domain_aliases_admin_all on domain_aliases
    for all to authenticated
    using ((np_role() = 'admin'::text))
    with check ((np_role() = 'admin'::text));

drop policy if exists edge_rels_select on edge_rels;
create policy edge_rels_select on edge_rels
    for select to authenticated
    using ((np_role() <> 'none'::text));

drop policy if exists edges_select on edges;
create policy edges_select on edges
    for select to authenticated
    using (((np_role() <> 'none'::text) AND (EXISTS ( SELECT 1
   FROM nodes n
  WHERE (n.id = edges.source_id))) AND (EXISTS ( SELECT 1
   FROM nodes n
  WHERE (n.id = edges.target_id)))));

drop policy if exists files_select on files;
create policy files_select on files
    for select to authenticated
    using ((np_role() <> 'none'::text));

drop policy if exists node_sources_select on node_sources;
create policy node_sources_select on node_sources
    for select to authenticated
    using (((np_role() <> 'none'::text) AND (EXISTS ( SELECT 1
   FROM nodes n
  WHERE (n.id = node_sources.node_id)))));

drop policy if exists node_types_select on node_types;
create policy node_types_select on node_types
    for select to authenticated
    using ((np_role() <> 'none'::text));

drop policy if exists nodes_member_select on nodes;
create policy nodes_member_select on nodes
    for select to authenticated
    using (((NOT sensitive) AND (np_role() <> 'none'::text)));

drop policy if exists nodes_recruiting_select on nodes;
create policy nodes_recruiting_select on nodes
    for select to authenticated
    using ((sensitive AND np_can_see_sensitive()));

drop policy if exists people_admin_all on people;
create policy people_admin_all on people
    for all to authenticated
    using ((np_role() = 'admin'::text))
    with check ((np_role() = 'admin'::text));

drop policy if exists people_aliases_admin_all on people_aliases;
create policy people_aliases_admin_all on people_aliases
    for all to authenticated
    using ((np_role() = 'admin'::text))
    with check ((np_role() = 'admin'::text));

drop policy if exists projection_meta_select on projection_meta;
create policy projection_meta_select on projection_meta
    for select to authenticated
    using ((np_role() <> 'none'::text));

drop policy if exists workflow_owners_admin_all on workflow_owners;
create policy workflow_owners_admin_all on workflow_owners
    for all to authenticated
    using ((np_role() = 'admin'::text))
    with check ((np_role() = 'admin'::text));
