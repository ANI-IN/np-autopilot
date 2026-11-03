-- 0034 (run 6, B5): indexes that measurably pay off at real-data size
-- (docs/run6/PERF.md). Additive; 0034 down drops them.
--
-- kb.edges had only PARTIAL indexes on its ends (where archived_at is null).
-- Any read that includes archived relationships -- GET /api/kb/graph with
-- archived=1 (every record's degree counts archived edges then), focus mode
-- with archived=1, a record's history and delete impact, the Archived page --
-- fell back to a sequential scan of kb.edges PER RECORD: 1.0-1.4 s for the
-- graph with archived=1 on the real data. These two cover both cases; the
-- partial ones stay (smaller, and preferred for live-only reads).
create index if not exists edges_source_all_idx on kb.edges (source_id);
create index if not exists edges_target_all_idx on kb.edges (target_id);

-- Audit fixes (docs/run6/AUDIT_FINDINGS.md A1, A2): the database as the last line.
--
-- A1. The AI assistant (an ikkb_ token: kb.actor_type() = 'ai') acts with its
-- owner's role, and the service refuses it the admin-only powers in some places
-- (proposal approval, tokens, Sync now) but not in others (granting roles,
-- linking sign-ins, permanent delete). Refused here for every path.
create or replace function kb.refuse_ai_admin() returns trigger
language plpgsql set search_path = pg_catalog
as $$
begin
    if kb.actor_type() = 'ai' then
        raise exception 'the AI assistant cannot % (%)', case tg_op when 'DELETE' then 'permanently delete or remove this'
                                                              else 'change roles or sign-in links' end, tg_table_name
            using errcode = 'insufficient_privilege', hint = 'kb_ai_refused';
    end if;
    return case tg_op when 'DELETE' then old else new end;
end $$;

create trigger refuse_ai before insert or update or delete on kb.memberships
    for each row execute function kb.refuse_ai_admin();
create trigger refuse_ai before insert or update or delete on kb.person_accounts
    for each row execute function kb.refuse_ai_admin();
create trigger refuse_ai_delete before delete on kb.nodes
    for each row execute function kb.refuse_ai_admin();
create trigger refuse_ai_delete before delete on kb.edges
    for each row execute function kb.refuse_ai_admin();
create trigger refuse_ai_delete before delete on kb.resources
    for each row execute function kb.refuse_ai_admin();

-- A2. A request may not leave the workspace without an admin (set_role let the
-- only admin demote themselves; remove_member already refused it). Request
-- connections only (role `authenticated`): operator scripts and the tests'
-- owner connection manage memberships directly.
create or replace function kb.keep_an_admin() returns trigger
language plpgsql security definer set search_path = pg_catalog
as $$
begin
    if current_setting('role', true) = 'authenticated'
       and old.role = 'admin' and old.archived_at is null
       and not exists (select 1 from kb.memberships where role = 'admin' and archived_at is null) then
        raise exception 'the last admin cannot give up the admin role; make someone else an admin first'
            using errcode = 'insufficient_privilege', hint = 'kb_last_admin';
    end if;
    return null;
end $$;
revoke all on function kb.keep_an_admin() from public;

create trigger keep_an_admin after update or delete on kb.memberships
    for each row execute function kb.keep_an_admin();
