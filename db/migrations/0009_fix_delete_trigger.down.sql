-- 0009 down — restores the version that silently cancels deletes. Stated
-- plainly, because that is a regression rather than a neutral rollback.
create or replace function require_version_predicate() returns trigger
language plpgsql as $$
begin
    if current_setting('np.writing_through_service', true) is distinct from 'on' then
        raise exception 'curation writes must go through the service layer (%.%)',
            tg_table_schema, tg_table_name;
    end if;
    return new;
end;
$$;
