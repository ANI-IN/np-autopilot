-- 0015 down. Stops NEW sign-ins from being granted `member` automatically.
--
-- IT DOES NOT REVOKE ANYTHING. Every profile this trigger already created
-- stays, and that is correct: those are real colleagues who have been reading
-- the graph. Rolling back a grant policy is not the same as de-provisioning
-- the people it granted, and doing both from one `migrate.py down` would make
-- a reversible schema change into an irreversible access change.
--
-- To actually remove someone, use pipeline/grant_access.py, which says who it
-- is removing and leaves an audit trail.
drop trigger if exists auth_user_created_grants_member on auth.users;
drop function if exists grant_member_on_signup();
