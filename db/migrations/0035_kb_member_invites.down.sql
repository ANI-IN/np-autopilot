-- Roll back 0035: invitations go (their audit rows stay: the log is
-- append-only, and they carry no address), kb.role() and kb.audit() return to
-- their 0023 and 0032 definitions. Memberships an invitation already applied
-- are ordinary memberships and stay.
drop trigger if exists profiles_apply_kb_invite on public.profiles;
drop function if exists kb.apply_member_invite();
drop table if exists kb.member_invites;          -- its triggers and policy go with it
drop function if exists kb.member_invites_resolve();

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

create or replace function kb.role() returns text
language sql stable security definer set search_path = pg_catalog, public
as $$
    select coalesce(
        (select m.role from kb.memberships m
          where m.user_id = auth.uid() and m.archived_at is null),
        case when public.np_role() <> 'none' then 'viewer' else 'none' end)
$$;
