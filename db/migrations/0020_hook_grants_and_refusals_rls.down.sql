-- Reverses 0020 — to PRODUCTION's pre-0020 state, read 2026-09-30, not to a
-- fresh apply's.
--
-- Before 0020, production's ACLs were:
--   auth_before_user_created  {postgres=X, service_role=X, supabase_auth_admin=X}
--   _hook_pick                {=X (PUBLIC), postgres=X, anon=X, authenticated=X,
--                              service_role=X, supabase_auth_admin=X}
--   auth_hook_refusals        RLS off, no policies
--
-- A fresh apply of 0001–0019 also leaves `=X` (PUBLIC) on the hook. This down
-- deliberately does NOT restore that: rolling back a fix must not reopen the
-- hole the fix closed, and production never had it.
-- ---------------------------------------------------------------------------

drop policy if exists auth_hook_refusals_gotrue_insert on auth_hook_refusals;
alter table auth_hook_refusals disable row level security;

grant execute on function auth_before_user_created(jsonb) to service_role;
grant execute on function _hook_pick(jsonb, text)
    to public, anon, authenticated, service_role;
