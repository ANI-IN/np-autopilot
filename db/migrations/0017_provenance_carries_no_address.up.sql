-- 0017 — D4, in the database: no provenance field may carry an address.
--
-- `docs/PRE-CRAWL-DECISIONS.md` §D4 decided that a file owner is recorded as a
-- DOMAIN, never as an address, and named the enforceable form in the same
-- breath: *"no provenance field may contain `@`. That is a derived assertion
-- over stored rows, not a list of field names to remember, so a new provenance
-- column is covered by default."*
--
-- Its status table then recorded D4 as **"recorded only. The assertion is
-- specified above and not yet written."** That is `docs/A7B.md` question 2 in
-- one line — a constraint that lives in prose, which the next reader trusts as
-- a control. This writes it.
--
-- WHY IT MATTERS NOW AND DID NOT BEFORE. Every file in the 75-file corpus is
-- owned by one account, so provenance never had an owner to record. The row-B
-- content crawl reads files owned by at least 14 accounts, four of them
-- personal free-mail addresses belonging to external instructors
-- (`REGISTRY-INVENTORY.md` §5(iv)) — and an owner address is an instructor
-- email, which `docs/CONTACT-DATA.md` declined for all three populations.
--
-- DERIVED, NOT ENUMERATED. The check names no columns. It concatenates every
-- text-bearing column, so a provenance column added in a later migration is
-- covered the day it is added rather than the day somebody remembers to extend
-- a list. That is instance 8's fix applied before the bug instead of after it.
-- ---------------------------------------------------------------------------

-- NOT VALID, deliberately and temporarily.
--
-- It enforces on every INSERT and UPDATE from now on, which is what the content
-- crawl needs. It does NOT retroactively scan the 30,658 existing rows, because
-- this migration has not been run against production and a migration that fails
-- half-way through an ALTER is a worse outcome than one that is explicit about
-- what it has and has not proved.
--
-- VALIDATE IT AS A SECOND, DELIBERATE STEP once the existing rows are known to
-- be clean. The statement is written out here so it is a decision, not a
-- research task:
--
--     select count(*) from node_sources
--      where coalesce(file,'')||coalesce(sheet,'')||coalesce(col_name,'')
--          ||coalesce(prop,'')||coalesce(evidence,'') like '%@%';
--     -- expect 0, then:
--     alter table node_sources validate constraint provenance_carries_no_address;
--
-- Leaving it NOT VALID forever would be the A7B failure this migration exists
-- to close, one level up. `tests/test_documented_constraints_are_enforced.py`
-- is where that gets noticed.
alter table node_sources
    add constraint provenance_carries_no_address
    check (
        coalesce(file, '')     not like '%@%' and
        coalesce(sheet, '')    not like '%@%' and
        coalesce(col_name, '') not like '%@%' and
        coalesce(prop, '')     not like '%@%' and
        coalesce(evidence, '') not like '%@%'
    ) not valid;

comment on constraint provenance_carries_no_address on node_sources is
    'D4 (docs/PRE-CRAWL-DECISIONS.md): a file owner is stored as a domain, '
    'never an address. NOT VALID until the existing rows are counted — see the '
    'migration body for the exact statement.';
