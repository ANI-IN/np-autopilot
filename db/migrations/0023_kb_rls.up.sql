-- 0023 — KB roles and row-level security. Enforced in the DATABASE: a viewer or
-- contributor calling a write directly (PostgREST, psql as `authenticated`, a
-- forgotten route) is refused here, not in the UI.
--
--   viewer       read everything in kb
--   contributor  + create and edit nodes, edges, resources, attachments, tags;
--                propose archive/delete
--   editor       + archive/restore, decide proposals, overwrite on conflict
--   admin        + configure types and rules, grant roles, hard-delete
--                already-archived rows
--
-- Default deny, as in 0002: RLS on every kb table, then one policy per rule.

-- ---------------------------------------------------------------------------
-- kb.role(): membership role; a signed-in IK profile with no membership is a
-- viewer; anyone else is 'none'. SECURITY DEFINER with a pinned search_path,
-- for the same reason as np_role().
-- ---------------------------------------------------------------------------
create or replace function kb.role() returns text
language sql stable security definer set search_path = pg_catalog, public
as $$
    select coalesce(
        (select m.role from kb.memberships m
          where m.user_id = auth.uid() and m.archived_at is null),
        case when public.np_role() <> 'none' then 'viewer' else 'none' end)
$$;

create or replace function kb.role_at_least(want text) returns boolean
language sql stable set search_path = pg_catalog, public
as $$
    select array_position(array['none', 'viewer', 'contributor', 'editor', 'admin'], kb.role())
        >= array_position(array['none', 'viewer', 'contributor', 'editor', 'admin'], want)
$$;

-- Archive / restore is an editor action even though contributors may UPDATE.
-- RLS cannot compare OLD and NEW, so this trigger does, for every role-bound
-- connection (the table owner and service scripts are not `authenticated`).
create or replace function kb.guard_archive() returns trigger
language plpgsql set search_path = pg_catalog, public
as $$
begin
    if current_user = 'authenticated'
       and (old.archived_at is distinct from new.archived_at)
       and pg_trigger_depth() = 1                 -- the cascade itself is not the caller
       and not kb.role_at_least('editor') then
        raise exception 'archive and restore need the editor role'
            using errcode = 'insufficient_privilege', hint = 'kb_needs_editor';
    end if;
    return new;
end;
$$;

do $$
declare t text;
begin
    foreach t in array array['nodes', 'edges', 'resources', 'node_resources', 'tags']
    loop
        execute format('create trigger %I before update on kb.%I
                        for each row execute function kb.guard_archive()', t || '_guard_archive', t);
    end loop;
end $$;

-- ---------------------------------------------------------------------------
-- RLS on, everywhere.
-- ---------------------------------------------------------------------------
alter table kb.node_types      enable row level security;
alter table kb.edge_types      enable row level security;
alter table kb.edge_type_rules enable row level security;
alter table kb.nodes           enable row level security;
alter table kb.edges           enable row level security;
alter table kb.resources       enable row level security;
alter table kb.node_resources  enable row level security;
alter table kb.tags            enable row level security;
alter table kb.node_tags       enable row level security;
alter table kb.memberships     enable row level security;
alter table kb.api_tokens      enable row level security;
alter table kb.proposals       enable row level security;
alter table kb.audit_log       enable row level security;

-- Content tables: read for viewer+, write for contributor+, hard delete for
-- admin and only of an already-archived row.
do $$
declare t text;
begin
    foreach t in array array['nodes', 'edges', 'resources', 'node_resources', 'tags']
    loop
        execute format('create policy %I on kb.%I for select to authenticated
                        using ((select kb.role_at_least(''viewer''))) ', t || '_select', t);
        execute format('create policy %I on kb.%I for insert to authenticated
                        with check ((select kb.role_at_least(''contributor''))) ', t || '_insert', t);
        execute format('create policy %I on kb.%I for update to authenticated
                        using ((select kb.role_at_least(''contributor'')))
                        with check ((select kb.role_at_least(''contributor''))) ', t || '_update', t);
        execute format('create policy %I on kb.%I for delete to authenticated
                        using ((select kb.role_at_least(''admin'')) and archived_at is not null) ',
                       t || '_delete', t);
    end loop;
end $$;

create policy node_tags_select on kb.node_tags for select to authenticated
    using ((select kb.role_at_least('viewer')));
create policy node_tags_insert on kb.node_tags for insert to authenticated
    with check ((select kb.role_at_least('contributor')));
create policy node_tags_delete on kb.node_tags for delete to authenticated
    using ((select kb.role_at_least('contributor')));

-- Configuration: everyone reads, admins write.
do $$
declare t text;
begin
    foreach t in array array['node_types', 'edge_types', 'edge_type_rules']
    loop
        execute format('create policy %I on kb.%I for select to authenticated
                        using ((select kb.role_at_least(''viewer''))) ', t || '_select', t);
        execute format('create policy %I on kb.%I for all to authenticated
                        using ((select kb.role_at_least(''admin'')))
                        with check ((select kb.role_at_least(''admin''))) ', t || '_admin', t);
    end loop;
end $$;

-- Memberships: your own row, or every row for an admin.
create policy memberships_self on kb.memberships for select to authenticated
    using (user_id = (select auth.uid()) or (select kb.role_at_least('admin')));
create policy memberships_admin on kb.memberships for all to authenticated
    using ((select kb.role_at_least('admin'))) with check ((select kb.role_at_least('admin')));

-- API tokens: strictly your own. Creating one needs at least viewer (a viewer's
-- token is read-only because the role behind it is).
create policy api_tokens_own_select on kb.api_tokens for select to authenticated
    using (user_id = (select auth.uid()));
create policy api_tokens_own_insert on kb.api_tokens for insert to authenticated
    with check (user_id = (select auth.uid()) and (select kb.role_at_least('viewer')));
create policy api_tokens_own_update on kb.api_tokens for update to authenticated
    using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

-- Proposals: viewers read, contributors propose, editors decide.
create policy proposals_select on kb.proposals for select to authenticated
    using ((select kb.role_at_least('viewer')));
create policy proposals_insert on kb.proposals for insert to authenticated
    with check ((select kb.role_at_least('contributor')) and status = 'pending');
create policy proposals_decide on kb.proposals for update to authenticated
    using ((select kb.role_at_least('editor'))) with check ((select kb.role_at_least('editor')));

-- Audit log: readable by viewers (activity feed, history), writable by nobody;
-- kb.audit() is SECURITY DEFINER. api_tokens audit rows are admin-only.
create policy audit_log_select on kb.audit_log for select to authenticated
    using ((select kb.role_at_least('viewer'))
           and (table_name <> 'api_tokens' or (select kb.role_at_least('admin'))
                or actor_id = (select auth.uid())));

-- ---------------------------------------------------------------------------
-- Token resolution for the MCP server: given a token's hash, the user it acts
-- as — only if live, unexpired and unrevoked. SECURITY DEFINER because the
-- caller has no identity yet; returns nothing else about the token.
-- ---------------------------------------------------------------------------
create or replace function kb.resolve_token(p_hash text) returns uuid
language plpgsql security definer set search_path = pg_catalog, public
as $$
declare uid uuid;
begin
    update kb.api_tokens set last_used_at = now()
     where token_hash = p_hash and revoked_at is null and archived_at is null
       and (expires_at is null or expires_at > now())
    returning user_id into uid;
    return uid;
end;
$$;
revoke all on function kb.resolve_token(text) from public;

-- ---------------------------------------------------------------------------
-- Grants. Privileges are necessary, RLS is what restricts; with no policy, a
-- grant yields nothing.
-- ---------------------------------------------------------------------------
grant usage on schema kb to authenticated;
grant select on all tables in schema kb to authenticated;
grant insert, update, delete on kb.nodes, kb.edges, kb.resources, kb.node_resources,
    kb.tags, kb.node_tags, kb.node_types, kb.edge_types, kb.edge_type_rules,
    kb.memberships, kb.proposals to authenticated;
grant insert, update on kb.api_tokens to authenticated;
grant execute on function kb.role(), kb.role_at_least(text), kb.actor_id(),
    kb.actor_type(), kb.norm(text) to authenticated;
-- Explicitly NOT granted: insert/update/delete on kb.audit_log; resolve_token.
revoke insert, update, delete on kb.audit_log from authenticated;
