-- 0012 — people_aliases: take back the write grants nothing uses.
--
-- FOUND BY A TEST that was rewritten to derive its rule instead of listing
-- names. test_anon_holds_no_grants_at_all used to carry a hardcoded set of
-- curation tables permitted to hold write grants. Migration 0011 added
-- curation_notes and the test failed as an unrecognised table — telling nobody
-- what was actually wrong. Rewritten to assert the PROPERTY that makes a write
-- grant safe (admin-only RLS, plus the trigger that refuses a write arriving
-- outside the service layer), it immediately found people_aliases: granted
-- INSERT, UPDATE and DELETE to `authenticated` since 0008, with neither trigger.
--
-- Nothing writes it that way. `people_aliases` is (alias, canonical) with no
-- version column, it is absent from WRITABLE in web/lib/curation_service.py,
-- and the only writer is pipeline/curation.py's import, which connects as the
-- owner over the session pooler and is unaffected by a grant to `authenticated`.
--
-- So the grant protected nothing and permitted an unaudited write by any admin
-- session that chose to issue one: no optimistic-locking predicate, no
-- curation_audit row, no version bump. Least privilege is the fix rather than a
-- third trigger, because a capability nothing needs should not exist to be
-- guarded.
--
-- SELECT stays. The admin alias UI reads it, and admin-only RLS already means
-- a member sees nothing.
revoke insert, update, delete on people_aliases from authenticated;

comment on table people_aliases is
    'alias -> canonical person. WRITTEN ONLY by pipeline/curation.py import, as '
    'the owner. `authenticated` holds SELECT only: there is no row-by-row '
    'service path, so there is no safe row-by-row grant (0012).';
