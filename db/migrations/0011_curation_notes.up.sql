-- 0011 — curation_notes: the REASONING, which a column cannot hold.
--
-- The three curation YAML files carry ~200 lines of comments recording WHY each
-- decision was made. Losing them is not a cosmetic loss:
--
--   * people.yaml records that Karthika S and Karthika Pai are DIFFERENT people,
--     confirmed against the HR directory. 03_resolve.py proposes middle-name
--     variants at ANY threshold, so without that note a future fuzzy pass has
--     nothing telling it not to merge them. The note is a guard against a
--     specific, already-identified wrong merge.
--   * domain-aliases.yaml opens with the SIBLING-DOMAIN TEST and why `ML` is
--     absent from the confirmed list. That reasoning belongs to no row — it is
--     the rule the whole file is an application of.
--
-- Hence the `__file__` anchor: a note keyed to the file rather than to a row.
-- Option 1 (a rationale column per row) would have kept the Karthika note and
-- silently dropped the sibling-domain rule, which is the more load-bearing of
-- the two.
create table curation_notes (
    id         bigint generated always as identity primary key,
    scope      text not null,
    row_key    text not null,
    note       text not null,
    position   integer not null default 0,
    author_email text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    version    integer not null default 1,

    constraint scope_is_a_curation_file check (
        scope in ('people.yaml', 'domain-aliases.yaml', 'workflow-owners.yaml')),
    constraint note_is_not_empty check (length(btrim(note)) > 0),
    -- One note per (scope, row_key, position). `position` keeps a multi-block
    -- comment in order; `__file__` is the file-level anchor.
    constraint one_note_per_anchor unique (scope, row_key, position)
);

create index curation_notes_scope_idx on curation_notes (scope, row_key);

comment on column curation_notes.row_key is
    'The primary key of the row this note explains, or ''__file__'' for '
    'file-level reasoning that belongs to no row — such as the sibling-domain '
    'test at the head of domain-aliases.yaml.';

alter table curation_notes enable row level security;

-- Admin only, like the curation tables it annotates.
create policy curation_notes_admin_all on curation_notes
    for all to authenticated
    using (np_role() = 'admin') with check (np_role() = 'admin');

grant select, insert, update, delete on curation_notes to authenticated;

create trigger curation_notes_bump before update on curation_notes
    for each row execute function bump_version();
create trigger curation_notes_service_only
    before insert or update or delete on curation_notes
    for each row execute function require_version_predicate();
