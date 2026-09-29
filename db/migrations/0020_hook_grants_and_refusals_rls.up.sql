-- 0020 — the sign-in hook's safety, stated by the migrations instead of
-- inherited from the environment.
--
-- Found 2026-09-29 by the first run of the DB tests against Supabase's real
-- local stack (docs/HANDOFF.md §G). Two properties production happened to have,
-- or happened to lack, that no migration ever stated:
--
-- 1. `auth_hook_refusals` (0016) was created WITHOUT row level security — in
--    production too (relrowsecurity = false). Not exposed there: anon and
--    authenticated hold no privilege on it and it has 0 rows. But "no grant
--    today" is a default somebody can change; RLS is the control every other
--    table in `public` carries, and tests/test_db_migration_verification.py
--    asserts it of all of them.
--
-- 2. 0007 revoked EXECUTE on the hook from `anon` and `authenticated` but never
--    from PUBLIC, and a function is executable by PUBLIC on creation. On a
--    fresh apply to Supabase's image the hook's ACL is `=X/postgres` — anyone
--    may call it. Production's ACL has no PUBLIC entry, for a reason no file
--    records. Safe by environment, not by migration.
--
-- Owner approval: Animesh Kumar, 2026-09-30 (origin: hand) — written and tested
-- locally only; goes to production in Phase C with 0017–0019.
-- ---------------------------------------------------------------------------

-- (1) RLS on, and the one writer GoTrue needs given a policy.
--
-- The hook is SECURITY DEFINER, owned by `postgres`, so its INSERT runs as the
-- table owner and RLS does not stop it. The policy keeps 0016's explicit
-- `grant insert … to supabase_auth_admin` meaningful rather than silently
-- void under RLS, should the function ever become SECURITY INVOKER. Nothing
-- else gets a policy, so every other non-owner role is denied by default.
alter table auth_hook_refusals enable row level security;

create policy auth_hook_refusals_gotrue_insert
    on auth_hook_refusals
    for insert
    to supabase_auth_admin
    with check (true);

-- (2) EXECUTE on the hook and its claim reader: supabase_auth_admin only.
--
-- GoTrue calls the hook as supabase_auth_admin (0016). The owner keeps EXECUTE
-- implicitly. Everyone else — PUBLIC, anon, authenticated, and service_role,
-- which Supabase's default privileges grant it — loses it: nothing but GoTrue
-- has a reason to run a sign-in hook.
revoke execute on function auth_before_user_created(jsonb)
    from public, anon, authenticated, service_role;
revoke execute on function _hook_pick(jsonb, text)
    from public, anon, authenticated, service_role;

grant execute on function auth_before_user_created(jsonb) to supabase_auth_admin;
grant execute on function _hook_pick(jsonb, text) to supabase_auth_admin;
