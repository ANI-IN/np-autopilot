-- 0003 — curation tables.
--
-- DECISIONS §B.1: Postgres is the source of truth for CURATION; the pipeline
-- stays the source of truth for everything derived. These three tables are the
-- only files a human ever hand-edits — people.yaml, domain-aliases.yaml,
-- workflow-owners.yaml — and the only place a write originates.
--
-- Everything in 0002 is a projection and is replaced wholesale on every build.
-- Everything here is authored and must never be.
--
-- OPTIMISTIC LOCKING, per §A.8. Two people resolving the `ML` alias differently
-- at the same moment is a real scenario, and last-write-wins would discard a
-- decision silently. `lib/resolve.py` returns Ambiguous rather than picking
-- because three bugs came from picking with no signal to the caller; a lost
-- curation update is that same failure with a database underneath it.

-- ---------------------------------------------------------------------------
-- people — keyed on the CURATED NAME, never on an employee id.
--
-- taxonomy.yaml: ids are not unique (IK-294 and IK-INT30 each map to two
-- people), not stable (Animesh Kumar carries two after an intern-to-FTE
-- renumber), and sometimes absent (Yash Mathur has 11 rows with a blank ENo,
-- which is normal HR lag for a recent joiner and a permanent condition, not a
-- defect). Employee ids are evidence only, so they live in props.
-- ---------------------------------------------------------------------------
create table people (
    canonical  text primary key,
    team       text not null,
    title      text,
    seniority  text,
    props      jsonb not null default '{}'::jsonb,
    version    integer not null default 1,
    updated_at timestamptz not null default now(),
    constraint canonical_nonempty check (length(btrim(canonical)) > 0),
    -- taxonomy: title and seniority are required when team is np, absent
    -- otherwise. Structural, so it is a constraint rather than a report.
    constraint np_has_title_and_seniority
        check (team <> 'np' or (title is not null and seniority is not null)),
    constraint non_np_has_neither
        check (team = 'np' or (title is null and seniority is null))
);

-- Aliases are multi-valued and are the strings a corpus row resolves through,
-- so they get rows rather than a JSON array: they are looked up, not just read.
create table people_aliases (
    alias     text primary key,
    canonical text not null references people(canonical) on update cascade
                                                         on delete cascade
);
create index people_aliases_canonical_idx on people_aliases (canonical);

-- ---------------------------------------------------------------------------
-- domain_aliases — the three unresolved ones (ML, Agentic AI, Product
-- Management) are 272 expert_in edges waiting on a human decision.
--
-- `confirmed` defaults FALSE and the pipeline reads only confirmed rows. An
-- alias that has not passed the sibling-domain test must not become an edge
-- because someone forgot a flag.
-- ---------------------------------------------------------------------------
create table domain_aliases (
    alias        text primary key,
    domain       text not null,
    claims       integer,
    sibling_test text,
    confirmed    boolean not null default false,
    confirmed_by text,
    confirmed_at date,
    note         text,
    props        jsonb not null default '{}'::jsonb,
    version      integer not null default 1,
    updated_at   timestamptz not null default now(),
    -- A confirmed alias must say who confirmed it. "Confirmed by nobody" is how
    -- an unreviewed guess becomes 157 edges.
    constraint confirmed_names_a_confirmer
        check (not confirmed or (confirmed_by is not null and confirmed_at is not null))
);

-- ---------------------------------------------------------------------------
-- workflow_owners — 92 rows, all currently unconfirmed, and that is the
-- CORRECT final state. Workflow-level ownership does not exist in New Programs;
-- everyone does every kind of work. Never report a blank owner as a gap.
-- ---------------------------------------------------------------------------
create table workflow_owners (
    workflow_id text primary key,
    name        text,
    theme_id    integer,
    owner       text references people(canonical) on update cascade,
    confirmed   boolean not null default false,
    suggestion  text,
    evidence    text,
    props       jsonb not null default '{}'::jsonb,
    version     integer not null default 1,
    updated_at  timestamptz not null default now(),
    -- Rows with confirmed: false are ignored entirely by the builder, INCLUDING
    -- their suggestion field. A suggestion is a prompt for a human, not a fact.
    constraint confirmed_has_an_owner check (not confirmed or owner is not null)
);

-- Bump `version` and stamp `updated_at` on every update, so optimistic locking
-- cannot be defeated by a writer that forgets. A trigger is used here — and
-- only here — because this is the one place rows are authored rather than
-- replaced, and because the alternative is trusting every future writer.
create or replace function bump_version() returns trigger
language plpgsql as $$
begin
    new.version := old.version + 1;
    new.updated_at := now();
    return new;
end;
$$;

create trigger people_bump          before update on people
    for each row execute function bump_version();
create trigger domain_aliases_bump  before update on domain_aliases
    for each row execute function bump_version();
create trigger workflow_owners_bump before update on workflow_owners
    for each row execute function bump_version();

alter table people          enable row level security;
alter table people_aliases  enable row level security;
alter table domain_aliases  enable row level security;
alter table workflow_owners enable row level security;
