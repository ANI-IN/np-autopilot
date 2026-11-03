-- Roll back 0037. Refuses while the exclusions are in force: run
-- `python pipeline/kb_legacy_delete.py restore` first (it restores the deleted
-- records and empties the table), or delete the rows deliberately.
do $$
begin
    if exists (select 1 from kb.sync_exclusions) then
        raise exception '0037 down: kb.sync_exclusions is in use; restore the legacy deletion first';
    end if;
end $$;
drop table kb.sync_exclusions;
