-- 0008 down. Rolling this back removes the audit trail's home and re-opens
-- curation to direct writes; said plainly rather than left to be discovered.
drop trigger if exists workflow_owners_service_only on workflow_owners;
drop trigger if exists domain_aliases_service_only  on domain_aliases;
drop trigger if exists people_service_only          on people;
drop function if exists require_version_predicate();

revoke select, insert, update, delete
    on people, people_aliases, domain_aliases, workflow_owners from authenticated;

drop policy if exists workflow_owners_admin_all on workflow_owners;
drop policy if exists domain_aliases_admin_all  on domain_aliases;
drop policy if exists people_aliases_admin_all  on people_aliases;
drop policy if exists people_admin_all          on people;

drop table if exists curation_audit;

alter table profiles drop constraint if exists shared_accounts_stay_member;
