-- 0015 — a verified IK Workspace identity becomes a `member` automatically.
--
-- THIS REVERSES PART OF Q3's DEFAULT, deliberately, and the reversal is
-- recorded in docs/AUTH.md rather than only here. Until now `grant_access.py`
-- stated the invariant plainly: "there is no self-service path into a role."
-- An IK employee signed in, reached /api/me, and was told they had no profile
-- and therefore read nothing, until an administrator ran a script. That is a
-- real refusal for a real colleague, and the administrator step added no
-- security: layer 3 (migration 0007) had already refused every identity that
-- is not an IK Workspace account before the user row existed at all.
--
-- What the manual step actually gated was MEMBERSHIP, which 0007 already
-- decides. It never gated `recruiting`, which is the role that reads the
-- hiring funnel, and that stays manual.
--
-- WHY A TRIGGER AND NOT THE SESSION ROUTE. Writing a profile from /api/session
-- needs privileges the web app deliberately does not have. AUTH.md names the
-- service-role key as layer 1's ONLY leak path and the reason nothing in the
-- web app holds it; granting the web app write access to `profiles` to save an
-- administrator a command would undo exactly that. The database provisions its
-- own rows instead — the same argument as 0014, where the database derives the
-- value its own constraint depends on rather than trusting a caller.
--
-- THIS IS NOT A SELF-SERVICE PATH. Nothing the user calls grants anything: the
-- row appears as a consequence of GoTrue creating the account, which 0007 has
-- already vetted. There is no parameter, no request, and no role to ask for.
create or replace function grant_member_on_signup()
returns trigger language plpgsql security definer
set search_path = public, pg_temp as $$
declare
    dom text := lower(split_part(coalesce(new.email, ''), '@', 2));
begin
    -- Defence in depth, not the check. Layer 3 refuses a non-Workspace identity
    -- before this row exists; `profiles.domain_is_ik` would refuse the insert
    -- anyway. We SKIP rather than let that constraint fire, because a raise
    -- here would abort the signup transaction and turn a correctly-refused
    -- account into a 500 from GoTrue — the wrong failure for the right reason.
    if dom <> 'interviewkickstart.com' then
        return new;
    end if;

    -- 'member' IS A LITERAL, AND THAT IS THE POINT. There is no expression here
    -- that could evaluate to 'recruiting' or 'admin', and no input that reaches
    -- this statement. The auto path cannot be widened by data.
    --
    -- ON CONFLICT DO NOTHING, never DO UPDATE: this must never be able to
    -- DEMOTE. If a profile already exists for this id — an administrator who
    -- prepared one, or a replayed insert — it is left exactly as it is.
    --
    -- email_domain is derived here from the address rather than passed in, so
    -- `domain_is_ik` is checking a value the database computed. 0014's
    -- before-insert trigger still derives is_shared_account, and 0008's
    -- `shared_accounts_stay_member` still caps a shared mailbox at 'member' —
    -- which is what this grants, so the two agree by construction.
    insert into profiles (user_id, email, email_domain, role)
    values (new.id, lower(new.email), dom, 'member')
    on conflict (user_id) do nothing;

    return new;
end;
$$;

comment on function grant_member_on_signup() is
    'Gives every verified IK Workspace identity a member profile at signup. '
    'Writes the literal role ''member'' and nothing else; recruiting and admin '
    'stay manual, via pipeline/grant_access.py. Never updates an existing row.';

create trigger auth_user_created_grants_member
    after insert on auth.users
    for each row execute function grant_member_on_signup();
