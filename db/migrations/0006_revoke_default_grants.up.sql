-- 0006 — revoke Supabase's default grants; leave SELECT only.
--
-- FOUND BY TESTING, not by reading. The E1 write test expected an error and got
-- "NO ERROR, rowcount=0". Inspecting the grants showed why:
--
--   grants on nodes: anon DELETE/INSERT/REFERENCES/SELECT/TRIGGER/TRUNCATE/UPDATE
--                    authenticated  ... the same seven
--
-- Supabase's project bootstrap runs ALTER DEFAULT PRIVILEGES in `public`
-- granting ALL to anon, authenticated and service_role. So 0005's
-- `grant select` added nothing that was not already there, and the only thing
-- standing between an authenticated caller and a DELETE was RLS.
--
-- RLS did hold — with no UPDATE or DELETE policy, no row is visible to modify,
-- so those statements affect zero rows. But it holds SILENTLY: the caller gets
-- success and rowcount 0, not a denial. Two consequences worth a migration:
--
--   1. The failure is indistinguishable from "the row wasn't there", so a
--      genuine authorisation bug would not announce itself. DECISIONS §A.7a:
--      a guard that cannot be observed failing is not a guard you can trust.
--   2. It is one permissive policy away from real. The day someone adds a
--      `for all` policy instead of `for select`, the grant is already in place
--      and DELETE starts working.
--
-- DECISIONS §D says RLS is the only layer that protects the data if an API
-- route is misconfigured. That remains true. This makes the grant layer stop
-- being a no-op underneath it.

-- Existing tables.
revoke all on all tables in schema public from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;

-- `anon` gets NOTHING. Every policy in 0005 is `to authenticated`; an
-- unauthenticated caller has no business reaching these tables at all, and
-- leaving the grant in place while relying on policy absence is the same
-- silent-denial shape as above.

-- `authenticated` gets SELECT, and only on what the app reads.
grant select on nodes, edges, node_sources, node_types, edge_rels, files,
                projection_meta, profiles to authenticated;

-- Curation tables stay ungranted: E3 is read-only and there is no curation UI.

-- FUTURE tables, so this is not a one-time cleanup that the next migration
-- undoes by accident. Without this, `create table` in a later migration
-- re-inherits the permissive defaults and the hole reopens silently.
alter default privileges in schema public
    revoke all on tables from anon, authenticated;
alter default privileges in schema public
    revoke all on sequences from anon, authenticated;
