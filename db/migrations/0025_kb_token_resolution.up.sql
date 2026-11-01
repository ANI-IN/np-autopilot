-- 0025 — let the web app resolve a KB API token while connected as
-- `authenticated` (with no identity yet), so an MCP client can authenticate with
-- ONLY its per-user token: no database credential ever leaves the server.
--
-- Safe to grant: kb.resolve_token is SECURITY DEFINER, takes the SHA-256 of a
-- 256-bit random token, and returns only the owning user id for a live,
-- unexpired, unrevoked token — nothing to enumerate, nothing to guess.
grant execute on function kb.resolve_token(text) to authenticated;
