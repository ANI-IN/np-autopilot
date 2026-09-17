-- Restores write grants that no code path uses and no trigger guards.
--
-- Rolling this back re-opens an unaudited write route to people_aliases for any
-- session holding the admin role: no version predicate, no curation_audit row.
-- If you are rolling back because a real writer needs these grants, that writer
-- needs the service-layer trigger and a version column FIRST — the grant is the
-- last step, not the first.
grant insert, update, delete on people_aliases to authenticated;
