-- 0035 — run 6, F4 and F5: members added by e-mail before their first
-- sign-in, and a knowledge-base role only for an IK profile.
--
-- 1. kb.member_invites: an admin adds a person by their @interviewkickstart.com
--    address with a role. If that person has already signed in, the role is
--    applied at once (kb.member_invites_resolve); otherwise the first time they
--    sign in (kb.apply_member_invite, on the profile the sign-up creates; the
--    same place 0030/0033 link person records on sign-in).
--    The address is NEVER copied into the append-only audit log: kb.audit()
--    drops the `email` column for this table, as it drops `token_hash` for
--    api_tokens (and as 0032 kept person_accounts' addresses out of it). The
--    audit row still says who invited, which role, and when it was applied.
-- 2. kb.role(): a membership counts only for a caller with an IK profile
--    (np_role() <> 'none'; profiles.domain_is_ik guarantees the domain). Before,
--    a kb.memberships row granted its role to any uuid. Nothing in the app can
--    create such a row for a non-IK account, so this only closes the door the
--    pre-sign-in invitations would otherwise have opened wider: defence in
--    depth, never a loosening.
-- 3. The last admin can never be removed or demoted: 0034's kb.keep_an_admin()
--    already guards kb.memberships, including the membership an invitation
--    writes for an existing account. Nothing new is needed for it here.

-- 1 -------------------------------------------------------------------------
create table kb.member_invites (
    id          uuid primary key default gen_random_uuid(),
    email       text not null,
    role        text not null,
    status      text not null default 'pending',
    user_id     uuid,                       -- the account the role was applied to
    applied_at  timestamptz,
    created_by  uuid, updated_by uuid,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    version     integer not null default 1,
    archived_at timestamptz,
    constraint role_known check (role in ('admin', 'editor', 'contributor', 'viewer')),
    constraint status_known check (status in ('pending', 'applied', 'revoked')),
    -- The sign-in domain, checked by the database as well as by the service.
    constraint email_is_ik check (email = lower(btrim(email)) and length(email) <= 254
                                  and email ~ '^[^@\s]+@interviewkickstart\.com$')
);
create unique index member_invites_pending_email on kb.member_invites (email)
    where status = 'pending' and archived_at is null;
create index member_invites_user_idx on kb.member_invites (user_id) where user_id is not null;

alter table kb.member_invites enable row level security;
-- Admins only: the rows carry addresses.
create policy member_invites_admin on kb.member_invites for all to authenticated
    using ((select kb.role_at_least('admin'))) with check ((select kb.role_at_least('admin')));
grant select, insert, update on kb.member_invites to authenticated;

-- An invitation for someone who has ALREADY signed in applies at once. Runs
-- before the row is written, so the row says 'applied' from the start.
create or replace function kb.member_invites_resolve() returns trigger
language plpgsql security definer set search_path = pg_catalog, public
as $$
declare uid uuid;
begin
    new.email := lower(btrim(new.email));
    if new.status <> 'pending' or new.archived_at is not null
       or split_part(new.email, '@', 2) <> 'interviewkickstart.com' then
        return new;              -- revoked, or refused by email_is_ik right after this
    end if;
    select p.user_id into uid from public.profiles p where lower(p.email) = new.email;
    if uid is null then
        return new;              -- applied on their first sign-in (kb.apply_member_invite)
    end if;
    -- The last admin is never demoted, not by an invitation to their own
    -- address either (0034's keep_an_admin says the same for direct changes).
    if new.role <> 'admin'
       and exists (select 1 from kb.memberships where user_id = uid and role = 'admin' and archived_at is null)
       and not exists (select 1 from kb.memberships where role = 'admin' and archived_at is null and user_id <> uid) then
        raise exception 'the last admin cannot give up the admin role; make someone else an admin first'
            using errcode = 'insufficient_privilege', hint = 'kb_last_admin';
    end if;
    insert into kb.memberships (user_id, role) values (uid, new.role)
    on conflict (user_id) do update set role = excluded.role, archived_at = null, status = 'active';
    new.status := 'applied';
    new.user_id := uid;
    new.applied_at := now();
    return new;
end;
$$;
revoke all on function kb.member_invites_resolve() from public;
create trigger member_invites_resolve before insert or update of role, email on kb.member_invites
    for each row execute function kb.member_invites_resolve();

create trigger member_invites_stamp before insert or update on kb.member_invites
    for each row execute function kb.stamp();
create trigger member_invites_audit after insert or update or delete on kb.member_invites
    for each row execute function kb.audit();
create trigger refuse_ai before insert or update or delete on kb.member_invites
    for each row execute function kb.refuse_ai_admin();

-- On a first sign-in (a profile row appears, or its address changes): apply a
-- pending invitation. It must never fail a sign-up: any problem is a warning
-- and the person simply stays a viewer until an admin looks.
create or replace function kb.apply_member_invite() returns trigger
language plpgsql security definer set search_path = pg_catalog, public
as $$
declare inv record;
begin
    if split_part(lower(coalesce(new.email, '')), '@', 2) <> 'interviewkickstart.com' then
        return null;
    end if;
    select id, role into inv from kb.member_invites
     where email = lower(btrim(new.email)) and status = 'pending' and archived_at is null
     for update;
    if inv.id is null then
        return null;
    end if;
    begin
        -- A live role set some other way (pipeline/kb_admins.py) is kept.
        insert into kb.memberships (user_id, role) values (new.user_id, inv.role)
        on conflict (user_id) do update set role = excluded.role, archived_at = null, status = 'active'
            where kb.memberships.archived_at is not null;
        update kb.member_invites set status = 'applied', user_id = new.user_id, applied_at = now()
         where id = inv.id;
    exception when others then
        raise warning 'kb.apply_member_invite: invitation % was not applied (%)', inv.id, sqlstate;
    end;
    return null;
end;
$$;
revoke all on function kb.apply_member_invite() from public;
create trigger profiles_apply_kb_invite after insert or update of email on public.profiles
    for each row execute function kb.apply_member_invite();

-- The audit trigger (0032's, unchanged except the member_invites line).
create or replace function kb.audit() returns trigger
language plpgsql security definer set search_path = pg_catalog, public
as $$
declare
    b jsonb := case when tg_op in ('UPDATE', 'DELETE') then to_jsonb(old) end;
    a jsonb := case when tg_op in ('INSERT', 'UPDATE') then to_jsonb(new) end;
    rid uuid;
    aid bigint;
begin
    if tg_table_name = 'api_tokens' then
        b := b - 'token_hash'; a := a - 'token_hash';
    end if;
    -- An address never enters the append-only log (0035).
    if tg_table_name = 'member_invites' then
        b := b - 'email'; a := a - 'email';
    end if;
    b := b - 'search'; a := a - 'search';
    rid := coalesce(a ->> 'id', b ->> 'id', a ->> 'user_id', b ->> 'user_id', a ->> 'node_id', b ->> 'node_id')::uuid;
    insert into kb.audit_log (actor_id, actor_type, table_name, row_id, action, before, after)
    values (kb.actor_id(), kb.actor_type(), tg_table_name, rid, lower(tg_op), b, a)
    returning id into aid;
    insert into kb.changes (id, actor_id, actor_type, table_name, row_id, action, version, kind, node_ids)
    values (aid, kb.actor_id(), kb.actor_type(), tg_table_name, rid, lower(tg_op),
            coalesce(a ->> 'version', b ->> 'version'),
            kb.change_kind(tg_table_name, lower(tg_op), b, a),
            kb.change_node_ids(tg_table_name, b, a));
    return null;
end;
$$;

-- 2 -------------------------------------------------------------------------
create or replace function kb.role() returns text
language sql stable security definer set search_path = pg_catalog, public
as $$
    select case when public.np_role() = 'none' then 'none'
                else coalesce((select m.role from kb.memberships m
                                where m.user_id = auth.uid() and m.archived_at is null),
                              'viewer') end
$$;
