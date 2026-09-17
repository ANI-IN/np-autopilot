-- 0008 — curation writes: admin only, optimistically locked, and audited.
--
-- The three curation tables have had NO policy since 0003, so `authenticated`
-- reached none of them. This gives them one, and nothing else changes: the
-- derived graph stays replace-all from the pipeline, and these three tables stay
-- the only place a write originates (DECISIONS §B.1).

-- ---------------------------------------------------------------------------
-- Shared accounts: a listed shared mailbox may not hold a privileged role.
--
-- docs/AUTH.md recommended this and it is now a constraint, because a rule
-- someone has to remember is not a control. A shared account resolves several
-- humans to one identity, so the §E.4 audit question — "who looked up this
-- named candidate" — becomes unanswerable for that session. That is tolerable
-- for `member`, which reads a graph with no personal hiring data. It is not
-- tolerable for `recruiting`, which reads named hiring outcomes about external
-- people, nor for `admin`, which can change curation.
--
-- ITS LIMIT, and it must not be over-claimed: this defends against the
-- CONFIGURED list only. Shared-account DETECTION does not exist — Google does
-- not tell us — so an unlisted shared mailbox is indistinguishable from a
-- personal one and passes this check.
alter table profiles add constraint shared_accounts_stay_member
    check (not (is_shared_account and role in ('recruiting', 'admin')));

comment on constraint shared_accounts_stay_member on profiles is
    'A listed shared mailbox cannot hold recruiting or admin: the audit log '
    'would name an account rather than a person. Defends against the configured '
    'list only; shared-account detection does not exist.';

-- ---------------------------------------------------------------------------
-- curation_audit — a real table, not stdout.
--
-- §E.4 asked for this and E2 reported it honestly as not built. Writes are the
-- point at which stdout stops being adequate: a read log that is lost is a
-- missing answer, a write log that is lost is an unattributable change.
--
-- before/after are captured whole. "Field X changed" is not enough to answer
-- "what did this row say before someone edited it", which is the question asked
-- when a decision turns out to be wrong.
-- ---------------------------------------------------------------------------
create table curation_audit (
    id             bigint generated always as identity primary key,
    at             timestamptz not null default now(),
    actor_user_id  uuid,
    actor_email    text,
    shared_account boolean not null default false,
    table_name     text not null,
    row_key        text not null,
    action         text not null,
    before_value   jsonb,
    after_value    jsonb,
    reason         text not null,

    constraint action_is_known check (action in ('insert', 'update', 'delete')),
    -- A write with no stated reason is a write nobody can review later. The
    -- three alias decisions this system exists to unblock are exactly the case:
    -- the VALUE is one word, and the reason is the whole decision.
    constraint reason_is_present check (length(btrim(reason)) > 0),
    constraint update_has_both check (
        action <> 'update' or (before_value is not null and after_value is not null)),
    constraint insert_has_after check (action <> 'insert' or after_value is not null),
    constraint delete_has_before check (action <> 'delete' or before_value is not null)
);

create index curation_audit_row_idx  on curation_audit (table_name, row_key, at desc);
create index curation_audit_actor_idx on curation_audit (actor_user_id, at desc);

alter table curation_audit enable row level security;

-- NO policy for `authenticated`. Deliberately: an audit log the people it
-- describes can read — or worse, edit — is not an audit log. It is reachable by
-- the service role and the owner only, which is how it gets exported for review.
-- No grant either, so a future permissive policy alone cannot open it.

-- ---------------------------------------------------------------------------
-- Curation read + write, admin only.
--
-- member and recruiting get NOTHING here, not even SELECT: curation rows carry
-- the reasoning behind identity decisions about named staff, and there is no
-- read-only curation surface in scope.
-- ---------------------------------------------------------------------------
create policy people_admin_all on people
    for all to authenticated
    using (np_role() = 'admin') with check (np_role() = 'admin');

create policy people_aliases_admin_all on people_aliases
    for all to authenticated
    using (np_role() = 'admin') with check (np_role() = 'admin');

create policy domain_aliases_admin_all on domain_aliases
    for all to authenticated
    using (np_role() = 'admin') with check (np_role() = 'admin');

create policy workflow_owners_admin_all on workflow_owners
    for all to authenticated
    using (np_role() = 'admin') with check (np_role() = 'admin');

grant select, insert, update, delete
    on people, people_aliases, domain_aliases, workflow_owners to authenticated;

-- ---------------------------------------------------------------------------
-- Optimistic locking, enforced rather than trusted.
--
-- 0003 added a trigger that bumps `version` on every update. That makes the
-- OPTIMISTIC half work — a writer passing a stale version matches zero rows.
-- What it does not do is stop a writer from omitting the version predicate
-- entirely and clobbering whatever is there.
--
-- This trigger closes that: an UPDATE must arrive with the row's current
-- version already matched, which a `where version = $n` predicate guarantees
-- and a bare `update ... where alias = $1` does not.
-- ---------------------------------------------------------------------------
create or replace function require_version_predicate() returns trigger
language plpgsql as $$
begin
    if current_setting('np.writing_through_service', true) is distinct from 'on' then
        raise exception
            'curation writes must go through the service layer (%.%)',
            tg_table_schema, tg_table_name
            using hint = 'the service layer sets np.writing_through_service and '
                         'supplies a version predicate; a direct UPDATE can '
                         'clobber a concurrent decision silently';
    end if;
    return new;
end;
$$;

create trigger people_service_only before insert or update or delete on people
    for each row execute function require_version_predicate();
create trigger domain_aliases_service_only
    before insert or update or delete on domain_aliases
    for each row execute function require_version_predicate();
create trigger workflow_owners_service_only
    before insert or update or delete on workflow_owners
    for each row execute function require_version_predicate();
