-- 0009 — the service-layer trigger silently cancelled every DELETE.
--
-- 0008's require_version_predicate() ends `return new;`. In a BEFORE DELETE row
-- trigger NEW is NULL, and returning NULL CANCELS THE OPERATION. So every delete
-- against a curation table was silently discarded and reported success with
-- rowcount 0 — indistinguishable from "the row was not there".
--
-- Found because a test teardown could not clean up: the next test hit a
-- duplicate-key error on a row that should not have existed. It would otherwise
-- have surfaced the first time someone removed a curation row and it came back.
--
-- This is precisely the class the trigger was written to prevent — a write that
-- does not happen and does not say so — reintroduced by the guard itself.
create or replace function require_version_predicate() returns trigger
language plpgsql as $$
begin
    if current_setting('np.writing_through_service', true) is distinct from 'on' then
        raise exception
            'curation writes must go through the service layer (%.%)',
            tg_table_schema, tg_table_name
            using hint = 'the service layer sets np.writing_through_service and '
                         'supplies a version predicate; a direct UPDATE can '
                         'clobber a concurrent decision silently';
    end if;
    -- NEW is NULL on DELETE, and returning NULL cancels the row operation.
    if tg_op = 'DELETE' then
        return old;
    end if;
    return new;
end;
$$;
