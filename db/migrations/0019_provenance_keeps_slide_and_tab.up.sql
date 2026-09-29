-- 0019 — node_sources dropped the content graph's locators on the floor.
--
-- `node_sources` carries `page` and `row_num` but has no column for a SLIDE or
-- a TAB. The 75-file corpus never needed them: its provenance is spreadsheet
-- rows and document pages. The row-B content graph's provenance is mostly
-- neither — a topic is cited as "slide 75 of API design - Krish.pptx" or
-- "tab 2 of Module - API Development.xlsx".
--
-- So the projection silently discarded them:
--
--     3,626 source records carrying a slide
--     1,477 carrying a tab
--     1,056 DISTINCT CITATIONS collapsed into other rows, because two topics
--           cited from different slides of the same deck became one entry
--
-- THAT IS THE WHOLE VALUE OF THE CONTENT LAYER. `validate.py`'s
-- `content-topic-locator` check asserts every one of 6,271 topic edges cites a
-- slide, page or tab; the database then stored the graph without them, and the
-- explorer's panel could say a topic came from a deck but never from where in
-- it.
--
-- HOW IT WAS FOUND, which is the part worth keeping. Not by reading the schema
-- — by `verify_migration.py --source supabase` reporting 7 of 54 checks
-- mismatched after the merged projection. The round trip rebuilds the graph
-- from the database and re-measures it, so a column that does not exist shows
-- up as a count that does not agree. A set of SQL COUNT queries would have
-- agreed with itself perfectly.
--
-- I first attributed the mismatch to the verifier's own measurement and said so.
-- That was wrong: the verifier was right and the data was lossy.
-- ---------------------------------------------------------------------------

alter table node_sources add column if not exists slide integer;
-- INTEGER. `tab` is the worksheet INDEX the extractor emits in its
-- `[tab N]` marker, not a sheet name — measured, all 1,477 values are
-- ints. Typing it text round-tripped 2 as '2' and every tab citation
-- compared unequal.
alter table node_sources add column if not exists tab   integer;

-- THE SAME DEFECT, THREE MORE FIELDS. Found by the same round trip: the
-- content graph's provenance also carries who owns the file, what kind of file
-- it is, and what kind of evidence the citation is, and none had a column.
--
-- `owner_domain` is the one that matters. `docs/PRE-CRAWL-DECISIONS.md` §D4
-- decided a file owner is recorded as a DOMAIN and never as an address, and
-- migration 0017 enforces the second half of that in the database. Without this
-- column the first half was simply discarded on projection — the decision was
-- enforced and its subject was thrown away.
alter table node_sources add column if not exists owner_domain  text;
alter table node_sources add column if not exists mime          text;
alter table node_sources add column if not exists evidence_kind text;

-- 0017 forbids an address in any provenance column, and these are provenance
-- columns. The constraint names columns explicitly, so it is extended here
-- rather than left to cover only the ones that existed when it was written.
alter table node_sources drop constraint if exists provenance_carries_no_address;
alter table node_sources
    add constraint provenance_carries_no_address
    check (
        coalesce(file, '')          not like '%@%' and
        coalesce(sheet, '')         not like '%@%' and
        coalesce(col_name, '')      not like '%@%' and
        coalesce(prop, '')          not like '%@%' and
        coalesce(evidence, '')      not like '%@%' and
        coalesce(owner_domain, '')  not like '%@%' and
        coalesce(evidence_kind, '') not like '%@%'
    );

comment on column node_sources.slide is
    'Slide number within a deck. Added 2026-09-19 with the row-B content graph; '
    'without it 1,056 distinct citations collapsed into one another.';
comment on column node_sources.tab is
    'Worksheet tab name. The spreadsheet analogue of `page` for a deck.';

-- The locator columns are what a panel joins on to say WHERE a topic came from.
create index if not exists node_sources_slide_idx on node_sources (file, slide)
    where slide is not null;
