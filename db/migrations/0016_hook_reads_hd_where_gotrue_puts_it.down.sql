-- Restore 0007's hook exactly as it was: hd read from the two UNNESTED paths.
--
-- Rolling back reinstates the bug this migration fixes — a valid Google
-- Workspace identity is refused, because GoTrue nests `hd` under
-- `custom_claims` and these paths do not look there. That is what a faithful
-- down migration means here, and it is why this file says so out loud rather
-- than quietly restoring a broken control.
create or replace function auth_before_user_created(event jsonb)
returns jsonb
language plpgsql stable security definer set search_path = public, pg_temp
as $$
declare
    email   text  := lower(coalesce(event #>> '{user_metadata,email}',
                                    event #>> '{claims,email}',
                                    event #>> '{user,email}', ''));
    hd      text  := lower(coalesce(event #>> '{user_metadata,hd}',
                                    event #>> '{claims,hd}', ''));
    allowed text  := 'interviewkickstart.com';
begin
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

drop function if exists _hook_pick(jsonb, text);
drop table if exists auth_hook_refusals;
