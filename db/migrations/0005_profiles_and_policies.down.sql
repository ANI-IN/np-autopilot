-- 0005 down. Policies go with their tables; revoke before dropping the grantee's
-- access so a partial rollback cannot leave a grant pointing at nothing.
revoke select on nodes, edges, node_sources, node_types, edge_rels, files,
                 projection_meta, profiles from authenticated;

drop policy if exists projection_meta_select on projection_meta;
drop policy if exists files_select          on files;
drop policy if exists edge_rels_select      on edge_rels;
drop policy if exists node_types_select     on node_types;
drop policy if exists node_sources_select   on node_sources;
drop policy if exists edges_select          on edges;
drop policy if exists nodes_recruiting_select on nodes;
drop policy if exists nodes_member_select     on nodes;
drop policy if exists profiles_self_select    on profiles;

drop function if exists np_can_see_sensitive();
drop function if exists np_role();
drop table if exists profiles;
