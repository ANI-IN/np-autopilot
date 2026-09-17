-- 0007 — layer 3: reject a non-Workspace identity AT SIGNUP.
--
-- Supabase "before user created" auth hook. Layers 1 (RLS) and 2 (token
-- verification) already refuse a non-IK caller, so this is not the thing
-- keeping data safe. What it adds is that a non-IK identity never becomes a
-- row at all — no auth.users record, no orphaned profile, nothing to clean up
-- and nothing that could be granted a role later by a careless UPDATE.
--
-- Its limit, stated because it is easy to over-claim: it covers the SIGNUP
-- path only. An account created before this hook existed stays valid, and the
-- hook cannot retro-reject one. Layers 1 and 2 are what cover those.
create or replace function auth_before_user_created(event jsonb)
returns jsonb
language plpgsql stable security definer set search_path = public, pg_temp
as $$
declare
    claims  jsonb := coalesce(event -> 'claims', '{}'::jsonb);
    email   text  := lower(coalesce(event #>> '{user_metadata,email}',
                                    event #>> '{claims,email}',
                                    event #>> '{user,email}', ''));
    hd      text  := lower(coalesce(event #>> '{user_metadata,hd}',
                                    event #>> '{claims,hd}', ''));
    allowed text  := 'interviewkickstart.com';
begin
    -- hd FIRST, and on its own. An email in the domain is not membership of the
    -- Workspace; a consumer account can carry one. Same rule as web/lib/auth.py,
    -- deliberately duplicated here because this hook runs where that code does
    -- not — GoTrue calls it directly.
    if hd is null or hd = '' then
        return jsonb_build_object('error', jsonb_build_object(
            'http_code', 403,
            'message', 'Sign in with your Interview Kickstart Workspace account. '
                       'This identity has no hosted-domain claim.'));
    end if;

    if hd <> allowed then
        return jsonb_build_object('error', jsonb_build_object(
            'http_code', 403,
            'message', format('Accounts from %s are not permitted.', hd)));
    end if;

    if email = '' or email not like ('%@' || allowed) then
        return jsonb_build_object('error', jsonb_build_object(
            'http_code', 403,
            'message', 'Workspace domain and email address disagree.'));
    end if;

    return '{}'::jsonb;
end;
$$;

comment on function auth_before_user_created(jsonb) is
    'Supabase before-user-created hook. Rejects any identity without hd = '
    'interviewkickstart.com. Covers the SIGNUP path only — accounts created '
    'before it existed are covered by RLS and by token verification.';

-- GoTrue calls the hook as supabase_auth_admin.
grant execute on function auth_before_user_created(jsonb) to supabase_auth_admin;
revoke execute on function auth_before_user_created(jsonb) from authenticated, anon;
