-- Restore 0002's broad `label_not_contact`.
--
-- THIS DOWN MIGRATION WILL FAIL IF THE CONTENT GRAPH IS PROJECTED, and that is
-- correct rather than unfortunate: 116 rows genuinely violate the old check, so
-- a down that succeeded would have had to drop them or leave the constraint
-- unenforced. Roll the projection back first (the Phase C backup), then this.
--
-- A rollback that fails loudly is recoverable. One that silently leaves rows
-- outside a constraint it claims to enforce is the `A7B.md` shape.
-- ---------------------------------------------------------------------------

alter table nodes drop constraint label_not_contact;

alter table nodes
    add constraint label_not_contact
    check (label !~ '@' and lower(label) !~ 'http');
