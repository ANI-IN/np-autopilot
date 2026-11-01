-- Reverses 0022. Drops ONLY the `kb` schema this migration created. The
-- pipeline projection in `public` is untouched. pg_trgm is left installed: other
-- objects may come to depend on it and it holds no data.
--
-- DATA LOSS WARNING: this removes every authored KB record. Before running it
-- anywhere shared, back up: `pg_dump --schema=kb "$SUPABASE_DB_URL_SESSION"`.
drop schema if exists kb cascade;
