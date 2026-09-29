-- Row counts, migration level and projection identity: run before and after
-- every window step. Read-only.
select 'migration' as what, max(version)::text as value from np_schema_migrations
union all select 'content_hash', content_hash from projection_meta
union all select 'projected_at', projected_at::text from projection_meta
union all select 'nodes', count(*)::text from nodes
union all select 'edges', count(*)::text from edges
union all select 'node_sources', count(*)::text from node_sources
union all select 'files', count(*)::text from files
union all select 'node_types', count(*)::text from node_types
union all select 'edge_rels', count(*)::text from edge_rels
union all select 'people', count(*)::text from people
union all select 'people_aliases', count(*)::text from people_aliases
union all select 'domain_aliases', count(*)::text from domain_aliases
union all select 'workflow_owners', count(*)::text from workflow_owners
union all select 'curation_notes', count(*)::text from curation_notes
union all select 'curation_audit', count(*)::text from curation_audit
union all select 'profiles', count(*)::text from profiles
union all select 'shared_accounts', count(*)::text from shared_accounts;
