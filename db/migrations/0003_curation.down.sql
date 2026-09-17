-- 0003 down. Reverse order; triggers go with their tables.
drop trigger if exists workflow_owners_bump on workflow_owners;
drop trigger if exists domain_aliases_bump  on domain_aliases;
drop trigger if exists people_bump          on people;
drop function if exists bump_version();
drop table if exists workflow_owners;
drop table if exists domain_aliases;
drop table if exists people_aliases;
drop table if exists people;
