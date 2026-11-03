-- 0030 — run 5: legacy flag, owners from roles, accounts for people, the
-- scheduled sync's bookkeeping, the reversible legacy archive.
--
-- 1. kb.nodes.is_legacy: NP Autopilot's "older sheets" (a module without a
--    mastersheet identity, a domain offering no current module, an instructor
--    with no current role, every programme). Hidden from default lists and
--    counts, filterable. Set by the import/sync only.
-- 2. Owners from roles: owner_record_id (the Primary) and co_owner_record_ids
--    (Backups in order) point at PERSON RECORDS (instructors, team members).
--    They become real account owners (owner_id, co_owners) once the person
--    record is linked to a sign-in account.
-- 3. kb.person_accounts: a person record's e-mail. When an account with that
--    e-mail exists (now, or the first time that person signs in), the link
--    resolves and every record they own by role gets them as owner_id /
--    co_owners. Additive only: an owner set by hand in the KB is never replaced.
-- 4. kb.sync_map / kb.sync_runs: what the sync wrote for each source row (with
--    its checksum), conflicts, removed-at-source, and the run log.
-- 5. kb.legacy_archive: what the legacy step archived, so one command restores it.
-- 6. actor_type 'sync' (Activity shows "Sync").

-- 6 -------------------------------------------------------------------------
create or replace function kb.actor_type() returns text
language sql stable set search_path = pg_catalog, public
as $$
    select case coalesce(nullif(current_setting('kb.actor_type', true), ''),
                         case when kb.actor_id() is null then 'system' else 'human' end)
             when 'ai' then 'ai' when 'import' then 'import' when 'sync' then 'sync'
             when 'system' then 'system' else 'human' end
$$;

-- 1, 2 ----------------------------------------------------------------------
alter table kb.nodes
    add column is_legacy boolean not null default false,
    add column owner_record_id uuid references kb.nodes(id) on delete set null,
    add column co_owner_record_ids uuid[] not null default '{}',
    add constraint owner_record_not_self check (owner_record_id is null or owner_record_id <> id);
create index nodes_live_current_idx on kb.nodes (type_id) where archived_at is null and not is_legacy;
create index nodes_owner_record_idx on kb.nodes (owner_record_id) where owner_record_id is not null;
create index nodes_co_owner_records_idx on kb.nodes using gin (co_owner_record_ids);

-- 3 -------------------------------------------------------------------------
create table kb.person_accounts (
    node_id    uuid primary key references kb.nodes(id) on delete cascade,
    email      text not null,
    user_id    uuid,
    linked_at  timestamptz,
    created_by uuid default kb.actor_id(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint email_shape check (email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$' and length(email) <= 254)
);
create unique index person_accounts_email_unique on kb.person_accounts (lower(email));
create index person_accounts_user_idx on kb.person_accounts (user_id);
alter table kb.person_accounts enable row level security;
create policy person_accounts_select on kb.person_accounts for select to authenticated
    using ((select kb.role_at_least('editor')) or user_id = (select auth.uid()));
create policy person_accounts_admin on kb.person_accounts for all to authenticated
    using ((select kb.role_at_least('admin'))) with check ((select kb.role_at_least('admin')));
grant select, insert, update, delete on kb.person_accounts to authenticated;

-- Give the linked account the records this person owns by role. Additive:
-- owner_id only where it is empty; co_owners only appended.
create or replace function kb.apply_person_owner(p_node uuid) returns integer
language plpgsql security definer set search_path = pg_catalog, public
as $$
declare uid uuid; n integer := 0; k integer;
begin
    select user_id into uid from kb.person_accounts where node_id = p_node;
    if uid is null then return 0; end if;
    update kb.nodes set owner_id = uid
     where owner_record_id = p_node and owner_id is null and archived_at is null;
    get diagnostics k = row_count; n := n + k;
    update kb.nodes set co_owners = co_owners || uid
     where p_node = any(co_owner_record_ids) and not (uid = any(co_owners))
       and owner_id is distinct from uid and archived_at is null;
    get diagnostics k = row_count; n := n + k;
    return n;
end;
$$;
revoke all on function kb.apply_person_owner(uuid) from public, anon, authenticated;

-- Resolve the e-mail to an account when the link is written...
create or replace function kb.person_accounts_resolve() returns trigger
language plpgsql security definer set search_path = pg_catalog, public
as $$
begin
    new.email := lower(btrim(new.email));
    select p.user_id into new.user_id from public.profiles p where lower(p.email) = new.email;
    new.linked_at := case when new.user_id is not null then coalesce(new.linked_at, now()) end;
    new.updated_at := now();
    return new;
end;
$$;
create trigger person_accounts_resolve before insert or update of email on kb.person_accounts
    for each row execute function kb.person_accounts_resolve();
create or replace function kb.person_accounts_apply() returns trigger
language plpgsql security definer set search_path = pg_catalog, public
as $$
begin
    if new.user_id is not null then perform kb.apply_person_owner(new.node_id); end if;
    return null;
end;
$$;
create trigger person_accounts_apply after insert or update on kb.person_accounts
    for each row execute function kb.person_accounts_apply();

-- ...and when that person signs in later (a profile row appears or changes e-mail).
create or replace function kb.profile_links_person() returns trigger
language plpgsql security definer set search_path = pg_catalog, public
as $$
declare r record;
begin
    for r in update kb.person_accounts set user_id = new.user_id, linked_at = now(), updated_at = now()
             where lower(email) = lower(new.email) and user_id is distinct from new.user_id
             returning node_id
    loop
        perform kb.apply_person_owner(r.node_id);
    end loop;
    return null;
end;
$$;
create trigger profiles_link_kb_person after insert or update of email on public.profiles
    for each row execute function kb.profile_links_person();

-- 4 -------------------------------------------------------------------------
create table kb.sync_map (
    unit        text not null,          -- record | link | relationship | attachment
    key         text not null,          -- the source identity (projection ids)
    kb_table    text not null,
    kb_id       uuid,
    checksum    text not null,          -- of the desired content, from the source
    kb_checksum text,                   -- of what the sync last wrote: a different value now = edited in the KB
    first_seen  timestamptz not null default now(),
    last_seen   timestamptz not null default now(),
    last_written timestamptz,
    removed_at  timestamptz,            -- gone from the source: flagged, never deleted
    conflict_at timestamptz,            -- changed at source AND edited in the KB: not overwritten
    conflict_checksum text,
    primary key (unit, key),
    constraint unit_known check (unit in ('record', 'link', 'relationship', 'attachment'))
);
create index sync_map_kb_idx on kb.sync_map (kb_id);
create index sync_map_flags_idx on kb.sync_map (unit) where removed_at is not null or conflict_at is not null;
alter table kb.sync_map enable row level security;
create policy sync_map_select on kb.sync_map for select to authenticated using ((select kb.role_at_least('editor')));
grant select on kb.sync_map to authenticated;

create table kb.sync_runs (
    id          bigint generated always as identity primary key,
    started_at  timestamptz not null default now(),
    finished_at timestamptz,
    status      text not null default 'running',
    trigger     text not null,
    actor_id    uuid,
    counts      jsonb not null default '{}'::jsonb,
    conflicts   integer not null default 0,
    errors      jsonb not null default '[]'::jsonb,
    message     text,
    constraint status_known check (status in ('running', 'ok', 'error', 'skipped')),
    constraint trigger_known check (trigger in ('cron', 'manual', 'cli'))
);
create index sync_runs_recent_idx on kb.sync_runs (id desc);
alter table kb.sync_runs enable row level security;
create policy sync_runs_select on kb.sync_runs for select to authenticated using ((select kb.role_at_least('admin')));
grant select on kb.sync_runs to authenticated;

-- 5 -------------------------------------------------------------------------
create table kb.legacy_archive (
    node_id     uuid primary key references kb.nodes(id) on delete cascade,
    archived_at timestamptz not null default now(),
    reason      text not null
);
alter table kb.legacy_archive enable row level security;
create policy legacy_archive_select on kb.legacy_archive for select to authenticated using ((select kb.role_at_least('editor')));
grant select on kb.legacy_archive to authenticated;
