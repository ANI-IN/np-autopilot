-- 0011 down. The notes are the only machine-readable record of WHY each
-- curation decision was made; dropping this table loses that unless the YAML
-- files still carry them as comments. Export before rolling back.
drop trigger if exists curation_notes_service_only on curation_notes;
drop trigger if exists curation_notes_bump on curation_notes;
drop policy if exists curation_notes_admin_all on curation_notes;
revoke select, insert, update, delete on curation_notes from authenticated;
drop table if exists curation_notes;
