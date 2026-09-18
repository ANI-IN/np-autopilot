-- Returns is_shared_account to being whatever the caller claims.
--
-- Rolling this back means migration 0008's CHECK is once again keyed on a
-- value the application supplies, and an application that computes it wrong —
-- an unset NP_SHARED_ACCOUNTS is enough — disables the constraint silently. A
-- shared account could then be granted `recruiting`, which reads named hiring
-- outcomes about external people with an access log that cannot say who looked.
drop trigger if exists profiles_derive_shared on profiles;
drop function if exists derive_shared_account();
drop table if exists shared_accounts;
