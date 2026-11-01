-- Reverses 0023: policies, guard triggers, role functions and grants on kb.
-- Leaves 0022's tables in place (and therefore default-deny with RLS removed is
-- NOT the result: RLS is disabled again only on the kb tables this pair owns).
do $$
declare r record;
begin
    for r in select policyname, tablename from pg_policies where schemaname = 'kb' loop
        execute format('drop policy %I on kb.%I', r.policyname, r.tablename);
    end loop;
end $$;

drop trigger if exists nodes_guard_archive on kb.nodes;
drop trigger if exists edges_guard_archive on kb.edges;
drop trigger if exists resources_guard_archive on kb.resources;
drop trigger if exists node_resources_guard_archive on kb.node_resources;
drop trigger if exists tags_guard_archive on kb.tags;

revoke all on all tables in schema kb from authenticated;
revoke usage on schema kb from authenticated;

drop function if exists kb.resolve_token(text);
drop function if exists kb.guard_archive();
drop function if exists kb.role_at_least(text);
drop function if exists kb.role();
