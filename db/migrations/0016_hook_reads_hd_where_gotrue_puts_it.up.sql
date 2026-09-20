-- 0016 — the before-user-created hook looks for `hd` where GoTrue ACTUALLY
-- puts it, and says what it saw when it refuses.
--
-- THIS IS INSTANCE 6, A SECOND TIME, IN A SECOND PLACE.
--
-- `pipeline/grant_access.py` already carries this comment, established by
-- reading a real GoTrue row rather than from documentation:
--
--     identity_data -> 'custom_claims' ->> 'hd'   <-- where it IS
--     identity_data ->> 'hd'                      <-- where the script looked
--
-- GoTrue nests NON-STANDARD OIDC claims under `custom_claims`, and `hd` is
-- non-standard. The script's first version read only the unnested path, found
-- NULL for every account, and reported "this account is not a Workspace
-- identity" when it meant "I looked in the wrong place". It would have refused
-- every legitimate user. `docs/A7B.md` lists it as instance 6.
--
-- Migration 0007's hook reads `{claims,hd}` and `{user_metadata,hd}`. Both are
-- unnested. It was written speculatively and — until the hook was registered on
-- 2026-09-21 — had never executed against a real Google identity, so nothing
-- could have caught the repeat. The same mistake, in the same codebase, in the
-- function whose entire job is to read that claim.
--
-- WHAT THIS CHANGES
--
--   * `hd` and `email` are searched across every container GoTrue plausibly
--     uses, and in each one both directly and under `custom_claims`. First
--     non-empty wins.
--   * STILL FAIL-CLOSED. An identity with no `hd` anywhere is refused. The
--     widening is about where to LOOK, never about what to accept.
--   * On refusal the hook records the payload's SHAPE — key names only, never
--     values — so the next failure is self-diagnosing instead of a mystery
--     403. A refusal that cannot tell you why it refused is the same class of
--     problem as the one this migration fixes.
--
-- The function becomes VOLATILE because it now writes that diagnostic row.
-- `stable` forbids writes and would have raised at runtime, turning a refusal
-- into a 500 — the wrong failure for the right reason, which 0015's comment
-- already warns about in the other direction.

create table if not exists auth_hook_refusals (
    id          bigserial primary key,
    at          timestamptz not null default now(),
    reason      text not null,
    -- Key NAMES only. Never a value: this table exists to diagnose a payload
    -- shape, and a diagnostic that copies the identity it refused would be a
    -- contact-data leak written by the control that refused it.
    top_keys    text[],
    nested_keys text[]
);

comment on table auth_hook_refusals is
    'Why auth_before_user_created refused, and the SHAPE of the payload it saw. '
    'Key names only, never values. Written by the hook; read by a human after a '
    'sign-in fails.';

create or replace function _hook_pick(event jsonb, key text)
returns text language sql immutable set search_path = public, pg_temp as $$
    -- Every container GoTrue plausibly uses, each checked directly AND under
    -- custom_claims. DERIVED FROM A LIST, so adding a shape is one line rather
    -- than another coalesce nobody dares touch.
    select lower(nullif(trim(v), ''))
    from (
        select coalesce(
            event #>> array['claims','custom_claims',key],
            event #>> array['claims',key],
            event #>> array['user_metadata','custom_claims',key],
            event #>> array['user_metadata',key],
            event #>> array['user','raw_user_meta_data','custom_claims',key],
            event #>> array['user','raw_user_meta_data',key],
            event #>> array['user','user_metadata','custom_claims',key],
            event #>> array['user','user_metadata',key],
            event #>> array['user','identity_data','custom_claims',key],
            event #>> array['user','identity_data',key],
            event #>> array['metadata','custom_claims',key],
            event #>> array['metadata',key],
            event #>> array['user',key],
            event #>> array[key]
        ) as v
    ) s
$$;

comment on function _hook_pick(jsonb, text) is
    'Find an OIDC claim wherever GoTrue nested it. custom_claims FIRST, because '
    'that is where non-standard claims like hd actually land — see A7B '
    'instance 6, which this repeats in a second place.';

create or replace function auth_before_user_created(event jsonb)
returns jsonb
language plpgsql volatile security definer set search_path = public, pg_temp
as $$
declare
    email   text := _hook_pick(event, 'email');
    hd      text := _hook_pick(event, 'hd');
    allowed text := 'interviewkickstart.com';
    tops    text[];
    nests   text[];
begin
    if hd is null or hd = '' then
        select array_agg(k order by k) into tops
          from jsonb_object_keys(coalesce(event, '{}'::jsonb)) k;
        select array_agg(distinct k order by k) into nests
          from jsonb_each(coalesce(event, '{}'::jsonb)) e,
               lateral jsonb_object_keys(
                   case when jsonb_typeof(e.value) = 'object'
                        then e.value else '{}'::jsonb end) k;
        insert into auth_hook_refusals (reason, top_keys, nested_keys)
        values ('no hd claim found in any known location', tops, nests);

        return jsonb_build_object('error', jsonb_build_object(
            'http_code', 403,
            'message', 'Sign in with your Interview Kickstart Workspace account. '
                       'This identity has no hosted-domain claim.'));
    end if;

    if hd <> allowed then
        insert into auth_hook_refusals (reason, top_keys)
        values (format('hd=%s, not %s', hd, allowed), null);
        return jsonb_build_object('error', jsonb_build_object(
            'http_code', 403,
            'message', format('Accounts from %s are not permitted.', hd)));
    end if;

    -- email is corroboration, and its ABSENCE must not refuse a valid Workspace
    -- identity: hd is the check, and a payload that carries hd but nests email
    -- somewhere unknown is the failure mode this migration exists to stop
    -- repeating. Refuse only on a positive disagreement.
    if email is not null and email <> '' and email not like ('%@' || allowed) then
        insert into auth_hook_refusals (reason, top_keys)
        values (format('hd=%s but email domain disagrees', hd), null);
        return jsonb_build_object('error', jsonb_build_object(
            'http_code', 403,
            'message', 'Workspace domain and email address disagree.'));
    end if;

    return '{}'::jsonb;
end;
$$;

comment on function auth_before_user_created(jsonb) is
    'Supabase before-user-created hook. Refuses any identity without '
    'hd = interviewkickstart.com, reading hd wherever GoTrue nested it. '
    'Records the payload SHAPE (key names only) on refusal so a failed sign-in '
    'is diagnosable. Registered as pg-functions://postgres/public/'
    'auth_before_user_created.';

-- The hook runs as supabase_auth_admin. Without these it raises instead of
-- refusing, and GoTrue turns that into a failed sign-in with no explanation.
grant execute on function auth_before_user_created(jsonb) to supabase_auth_admin;
grant execute on function _hook_pick(jsonb, text) to supabase_auth_admin;
grant insert on table auth_hook_refusals to supabase_auth_admin;
grant usage, select on sequence auth_hook_refusals_id_seq to supabase_auth_admin;
