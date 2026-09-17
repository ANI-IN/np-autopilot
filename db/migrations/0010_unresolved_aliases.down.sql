-- 0010 down. Restoring NOT NULL requires every unresolved alias to be given a
-- target or removed — which is a DECISION, so the rollback refuses rather than
-- inventing one.
do $$
begin
    if exists (select 1 from domain_aliases where domain is null) then
        raise exception 'cannot roll back 0010: % unresolved alias(es) have no '
            'domain. Resolving them is a curation decision, not a migration.',
            (select count(*) from domain_aliases where domain is null);
    end if;
end $$;
alter table domain_aliases drop constraint if exists confirmed_needs_a_domain;
alter table domain_aliases alter column domain set not null;
