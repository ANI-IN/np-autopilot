-- Rollback 0017.
--
-- Dropping a CHECK is cheap and total: no data is rewritten and nothing that
-- was already stored becomes invalid. What it costs is the guarantee, so a
-- rollback here is a decision to let provenance carry an address again — which
-- is why D4 is recorded in docs/PRE-CRAWL-DECISIONS.md and not only in SQL.
alter table node_sources
    drop constraint if exists provenance_carries_no_address;
