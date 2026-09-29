-- Restore 0002's broad `label_not_contact`.
--
-- THIS DOWN MIGRATION WILL FAIL IF THE CONTENT GRAPH IS PROJECTED, and that is
-- correct rather than unfortunate: 116 rows genuinely violate the old check, so
-- a down that succeeded would have had to drop them or leave the constraint
-- unenforced. Roll the projection back first (the Phase C backup), then this.
--
-- A rollback that fails loudly is recoverable. One that silently leaves rows
-- outside a constraint it claims to enforce is the `A7B.md` shape.
--
-- APPLY THIS IN A TRANSACTION. `pipeline/migrate.py` runs each migration inside
-- one and rolls back on failure, so the sanctioned path is safe. Run the file
-- through `psql` WITHOUT a transaction and the DROP commits before the ADD
-- fails, leaving the table with NO constraint at all — measured on a local
-- PostgreSQL 17 instance while testing this migration, which is the reason
-- the DROP is now `if exists` and the reason this paragraph exists.
-- ---------------------------------------------------------------------------

alter table nodes drop constraint if exists label_not_contact;

alter table nodes
    add constraint label_not_contact
    check (label !~ '@' and lower(label) !~ 'http');
