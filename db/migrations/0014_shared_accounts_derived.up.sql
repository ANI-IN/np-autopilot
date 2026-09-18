-- 0014 — the database decides which accounts are shared, not the caller.
--
-- FOUND BY TESTING THE GUARD AGAINST A REAL ACCOUNT. The shared team mailbox
-- b2c-courses-new-programs@interviewkickstart.com signed in, and
-- `grant_access.py grant ... --role recruiting` GRANTED it. Both layers that
-- were supposed to stop that did nothing:
--
--   * The script checks NP_SHARED_ACCOUNTS. That variable was set in Vercel and
--     never in the laptop environment the script runs in, so the list was
--     empty, so no account is shared, so there was nothing to refuse.
--   * Migration 0008's CHECK (not (is_shared_account and role in
--     ('recruiting','admin'))) is keyed on is_shared_account — a column the
--     APPLICATION supplies. The script wrote false. The constraint held
--     perfectly over a value that was already wrong.
--
-- A CHECK constraint keyed on a value the caller controls is not a constraint.
-- It is the caller's opinion, stored, with a constraint's reputation.
--
-- And the failure is A.7b again: an unset variable means "no shared accounts
-- exist" is indistinguishable from "I was never told which accounts are
-- shared". The first is a fact; the second is an absence. Defaulting to the
-- permissive reading is what let it through.
--
-- So the list moves into the database, and a trigger DERIVES the flag. The
-- caller can no longer supply it: whatever is passed is overwritten.
create table shared_accounts (
    local_part text primary key,
    note       text,
    added_at   timestamptz not null default now(),

    constraint local_part_has_no_domain check (position('@' in local_part) = 0)
);

comment on table shared_accounts is
    'Local-parts of known shared mailboxes. A shared account resolves several '
    'humans to one identity, so its access log names an account, not a person. '
    'CONFIGURED, not detected: Google does not tell us, and an unlisted shared '
    'mailbox is indistinguishable from a personal one.';

insert into shared_accounts (local_part, note) values
    ('b2c-courses-new-programs',
     'Owns the Drive folder and the Vercel project. Signed in 2026-09-18.');

alter table shared_accounts enable row level security;
-- Readable by admins so the alias UI can explain a refusal; written by nobody
-- over HTTP. Changing who counts as shared is a migration, deliberately.
create policy shared_accounts_admin_read on shared_accounts
    for select to authenticated using ((select np_role()) = 'admin');
grant select on shared_accounts to authenticated;

-- THE DERIVATION. Runs on every insert and update, overwriting whatever the
-- caller passed, so is_shared_account is a fact about the email rather than a
-- claim about it.
create or replace function derive_shared_account()
returns trigger language plpgsql security definer
set search_path = public, pg_temp as $$
begin
    new.is_shared_account := exists (
        select 1 from shared_accounts s
        where s.local_part = lower(split_part(new.email, '@', 1)));
    return new;
end;
$$;

create trigger profiles_derive_shared
    before insert or update on profiles
    for each row execute function derive_shared_account();

-- Re-derive anything already stored, so the column is consistent with the rule
-- rather than with whatever wrote it.
update profiles set email = email;
