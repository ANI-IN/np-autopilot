-- 0006 down — restore Supabase's permissive defaults.
--
-- Rolling this back RE-OPENS the hole it closed. Written out anyway, and said
-- plainly, because a down migration that quietly does less than it claims is
-- worse than one that is honest about restoring a weaker state.
alter default privileges in schema public
    grant all on tables to anon, authenticated;
alter default privileges in schema public
    grant all on sequences to anon, authenticated;
grant all on all tables in schema public to anon, authenticated;
grant all on all sequences in schema public to anon, authenticated;
