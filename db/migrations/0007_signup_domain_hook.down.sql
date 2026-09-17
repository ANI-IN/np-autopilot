-- 0007 down. Removing this re-opens the SIGNUP path to any Google identity.
-- Layers 1 and 2 still refuse them data, but a row would be created.
drop function if exists auth_before_user_created(jsonb);
