-- 0024 — a record of every Sheets → KB import run (M8). Additive.
--
-- The per-row outcome lives in `report` (the same JSON the dry run prints), so a
-- run months later can still answer "why was this row not applied?". Rows are
-- written only by an apply; a dry run writes nothing anywhere.
create table kb.import_runs (
    id          uuid primary key default gen_random_uuid(),
    source      text not null,            -- 'sheets:<spreadsheet id>' or 'fixture:<path>'
    mode        text not null,
    counts      jsonb not null,
    report      jsonb not null,
    actor_id    uuid,
    started_at  timestamptz not null default now(),
    finished_at timestamptz,
    constraint mode_known check (mode in ('apply'))
);
create index import_runs_started_idx on kb.import_runs (started_at desc);

alter table kb.import_runs enable row level security;
create policy import_runs_select on kb.import_runs for select to authenticated
    using ((select kb.role_at_least('viewer')));
create policy import_runs_insert on kb.import_runs for insert to authenticated
    with check ((select kb.role_at_least('admin')));
create policy import_runs_update on kb.import_runs for update to authenticated
    using ((select kb.role_at_least('admin'))) with check ((select kb.role_at_least('admin')));
grant select, insert, update on kb.import_runs to authenticated;
