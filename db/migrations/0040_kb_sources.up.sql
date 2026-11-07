-- 0040 (run C, 2026-11-07): the source catalog.
--
-- The registry sheet is the single source of truth for which sources exist; the KYPs (Confluence) are
-- the reference for curriculum structure. Every source is stored as its LIVE URL + resource id +
-- version / modified time + provenance (how the registry reaches it). Downloaded copies are only a
-- processing cache outside the database, never the source of truth.
--
-- One row per (provider, resource id). A re-crawl updates the row by id: a changed version or modified
-- time sets last_changed; a source no longer reached sets removed_at (kept, never deleted here).
-- Failures (permission, not found, unsupported format, missing shortcut target, too large) are rows
-- with status 'failed' and the reason, so no inaccessible source is skipped silently.
-- Written by pipeline/kb_load_sources.py (the table owner). Read by admins (Admin > Sources & sync).
create table kb.sources (
    id               uuid primary key default gen_random_uuid(),
    provider         text not null check (provider in ('drive', 'sheets', 'confluence', 'web')),
    resource_id      text not null,
    kind             text not null,
    title            text,
    url              text not null,
    mime             text,
    version          text,
    modified_at      timestamptz,
    size_bytes       bigint,
    md5              text,
    parent_resource_id text,
    provenance       text[] not null default '{}',
    status           text not null check (status in ('extracted', 'extracted_empty', 'listed', 'media_listed', 'failed',
                                                     'do_not_use', 'deferred', 'imported', 'attachment_listed')),
    failure_reason   text,
    text_chars       integer,
    text_sha1        text,
    extracted_at     timestamptz,
    first_seen       timestamptz not null default now(),
    last_seen        timestamptz not null default now(),
    last_changed     timestamptz,
    removed_at       timestamptz,
    unique (provider, resource_id)
);
create index sources_status_idx on kb.sources (status);
create index sources_parent_idx on kb.sources (parent_resource_id);
create index sources_title_trgm on kb.sources using gin (lower(title) extensions.gin_trgm_ops);

alter table kb.sources enable row level security;
create policy sources_admin_select on kb.sources for select to authenticated
    using ((select kb.role_at_least('admin')));
grant select on kb.sources to authenticated;
revoke insert, update, delete on kb.sources from authenticated, anon;
