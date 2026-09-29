-- Reverses 0019. Dropping these columns DISCARDS 1,056 distinct citations and
-- every slide and tab locator in the content graph — the data is not recoverable
-- from the remaining columns, only by re-projecting from knowledge/.
--
-- That is acceptable for a down migration precisely because the projection is
-- rebuilt by TRUNCATE + COPY on every run: nothing here is a system of record.
-- ---------------------------------------------------------------------------

drop index if exists node_sources_slide_idx;
alter table node_sources drop column if exists slide;
alter table node_sources drop column if exists tab;
alter table node_sources drop column if exists owner_domain;
alter table node_sources drop column if exists mime;
alter table node_sources drop column if exists evidence_kind;

-- Restore 0017's constraint over the columns that remain.
alter table node_sources drop constraint if exists provenance_carries_no_address;
alter table node_sources
    add constraint provenance_carries_no_address
    check (
        coalesce(file, '')     not like '%@%' and
        coalesce(sheet, '')    not like '%@%' and
        coalesce(col_name, '') not like '%@%' and
        coalesce(prop, '')     not like '%@%' and
        coalesce(evidence, '') not like '%@%'
    );
