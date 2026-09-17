-- 0004 — preserve the order of a hand source's `establishes` list.
--
-- A hand entry names the properties it justifies: {establishes: [title,
-- seniority]}. The loader expands that into ONE ROW PER PROPERTY, which is the
-- right model — an assertion is about one fact — but reconstruction then has to
-- put the list back in its original order, and sorting would give
-- [seniority, title] and change the content hash.
--
-- ADDITIVE, and deliberately so. §A.6 says adding a property must be a
-- migration that adds, never one that rewrites existing rows. `add column` with
-- a non-volatile default does not rewrite the table in PostgreSQL 11+, so this
-- is the requirement demonstrated on a real change rather than asserted.
alter table node_sources add column prop_ordinal integer not null default 0;

comment on column node_sources.prop_ordinal is
    'Position within a hand source''s establishes[] list. 0 for corpus entries, '
    'which establish the node itself and name no property.';
