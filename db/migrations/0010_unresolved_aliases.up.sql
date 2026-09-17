-- 0010 — an unresolved alias has no target yet, and must be able to say so.
--
-- 0003 made domain_aliases.domain NOT NULL, which only fits a RESOLVED alias.
-- The three this system exists to unblock — ML (157 claims), Agentic AI (64),
-- Product Management (51) — have no target by definition: that is the whole
-- decision. Storing a placeholder would be the `Ambiguous`-collapse failure in
-- a column.
alter table domain_aliases alter column domain drop not null;

-- An alias with a target must be resolvable; one without must not claim to be.
alter table domain_aliases add constraint confirmed_needs_a_domain
    check (not confirmed or domain is not null);

comment on column domain_aliases.domain is
    'NULL means UNRESOLVED — no target has been chosen. Not a defect: three '
    'aliases are deliberately unjoined because more than one domain could '
    'plausibly be meant, and picking one with no signal is the failure '
    'lib/resolve.py exists to prevent.';
