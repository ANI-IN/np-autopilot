-- 0002 — the graph schema.
--
-- Shape follows docs/DECISIONS.md §A: normalised nodes/edges, provenance in its
-- own table, content-addressed assertion ids, JSONB for the sparse property
-- tail, and type/rel as lookup tables rather than enums.
--
-- RLS is enabled on every table AT CREATION with no policies — default deny. A
-- table created without RLS is the bug that does not announce itself: it works
-- perfectly until the day something other than the loader connects.

-- ---------------------------------------------------------------------------
-- Lookups. NOT enums.
--
-- §A.6: adding a node type must be a migration that ADDS, never one that
-- rewrites existing rows. Adding a value to a Postgres enum is DDL that takes a
-- lock; adding a row to a lookup table is an insert. This is that requirement
-- showing up in the first object created.
-- ---------------------------------------------------------------------------
create table node_types (
    name        text primary key,
    description text
);

create table edge_rels (
    name        text primary key,
    -- NOT a foreign key: `sourced_from` declares from_type '*' by design, and
    -- taxonomy.yaml says that wildcard is permitted for exactly one edge. A FK
    -- here would force a fake '*' row into node_types and make the wildcard
    -- look like a type.
    from_type   text not null,
    to_type     text not null references node_types(name),
    description text
);

-- ---------------------------------------------------------------------------
-- Files. Keyed on relative_path, which is the citation key — and the reason
-- filename typos are load-bearing and must never be corrected.
-- ---------------------------------------------------------------------------
create table files (
    relative_path text primary key,
    sha256        text,
    bytes         bigint,
    sheet_count   integer,
    parsed        boolean not null default false,
    drive_file_id text,
    drive_url     text,           -- still null; pass 0 can populate it now
    constraint relative_path_is_relative check (relative_path !~ '^/')
);

-- ---------------------------------------------------------------------------
-- Nodes.
-- ---------------------------------------------------------------------------
create table nodes (
    id        text primary key,
    type      text not null references node_types(name),
    label     text not null,
    label_raw text,
    -- REQUIRED, no default. taxonomy.yaml: "every node has sensitive set
    -- explicitly". A default would let an unclassified node look classified.
    sensitive boolean not null,
    props     jsonb not null default '{}'::jsonb,
    constraint id_shape      check (id ~ '^[a-z]{3}_[0-9a-f]{16}$'),
    constraint label_nonempty check (length(btrim(label)) > 0),
    -- taxonomy: no node label may contain @ or http. Structural, so it belongs
    -- here rather than in a report nobody runs before inserting.
    constraint label_not_contact check (label !~ '@' and lower(label) !~ 'http')
);

create index nodes_type_idx  on nodes (type);
create index nodes_label_idx on nodes (lower(label));
create index nodes_props_idx on nodes using gin (props);

-- ---------------------------------------------------------------------------
-- Edges.
--
-- SURROGATE key, deliberately, and this is the one place a content hash does
-- NOT work. 1,665 of the duplicate triples are `sourced_from` edges that carry
-- no properties at all, so two edges from the same node to the same file are
-- byte-identical. A content-addressed id would silently collapse them, which is
-- exactly the migration mistake the verifier tests for.
--
-- The distinguishing information lives in node_sources, one row per cited
-- source entry. The edge multiplicity mirrors that count.
-- ---------------------------------------------------------------------------
create table edges (
    id        bigint generated always as identity primary key,
    rel       text not null references edge_rels(name),
    source_id text not null references nodes(id) on delete cascade,
    target_id text not null references nodes(id) on delete cascade,
    props     jsonb not null default '{}'::jsonb
);

create index edges_source_idx on edges (source_id);
create index edges_target_idx on edges (target_id);
create index edges_rel_idx    on edges (rel);
-- The traversal index. Every real query filters rel and walks one direction,
-- and every traversal must exclude provenance or the degree-18,134 file hubs
-- destroy the result.
create index edges_rel_source_idx on edges (rel, source_id);
create index edges_rel_target_idx on edges (rel, target_id);

-- ---------------------------------------------------------------------------
-- node_sources — the ASSERTIONS table.
--
-- Content-addressed id over (node, prop, origin, coordinates, ordinal). The
-- collision check that forced the ordinal is in DECISIONS §A.4: full provenance
-- coordinates gave 32,724 distinct keys for 32,730 entries, six short, all the
-- same person listed twice in one grid row.
--
-- `prop` is the property-grained half C1 anticipated. NULL means the entry
-- establishes the node itself — which is what a corpus row does. A hand entry
-- names the properties it justifies, so the HR screenshot behind a title cannot
-- be presented as though a scan produced it.
-- ---------------------------------------------------------------------------
create table node_sources (
    id          text primary key,
    node_id     text not null references nodes(id) on delete cascade,
    prop        text,
    origin      text not null,
    file        text references files(relative_path),
    sheet       text,
    row_num     integer,
    -- TWO columns, because the source data has two shapes and a typed schema is
    -- what surfaced it. `column` in the JSON is None 21,087 times, an integer
    -- index 6,507 times (extract_domains, the grid extractor) and a column
    -- HEADER STRING 3,049 times (scan_column, which records the header it
    -- matched). Both are legitimate provenance; they are not the same fact.
    -- Collapsing them to text would have worked and lost the distinction.
    col_num     integer,
    col_name    text,
    page        integer,
    within_cell integer,
    ordinal     integer not null default 0,
    evidence    text,
    entered_at  date,

    constraint id_is_sha256 check (id ~ '^[0-9a-f]{64}$'),
    -- The two source SHAPES from taxonomy.yaml, as constraints rather than as
    -- prose. Both were documented for the life of the project and enforced
    -- nowhere; `origin: hand` appeared in the graph zero times until C1.
    constraint origin_is_known    check (origin in ('corpus', 'hand')),
    constraint corpus_names_a_file check (origin <> 'corpus' or file is not null),
    constraint hand_has_evidence   check (origin <> 'hand'
                                          or (evidence is not null
                                              and length(btrim(evidence)) > 0)),
    -- A hand entry that named a file would emit a provenance edge and disguise
    -- out-of-corpus evidence as a citation. That is the disguise the rule exists
    -- to prevent.
    constraint hand_names_no_file  check (origin <> 'hand' or file is null)
);

create index node_sources_node_idx on node_sources (node_id);
create index node_sources_file_idx on node_sources (file);
create index node_sources_prop_idx on node_sources (prop) where prop is not null;
-- A provenance coordinate is either an index or a header name, never both.
alter table node_sources add constraint col_is_index_or_name
    check (col_num is null or col_name is null);

-- ---------------------------------------------------------------------------
-- What this projection is, so a reader can tell whether they are looking at the
-- whole graph or the public half.
-- ---------------------------------------------------------------------------
create table projection_meta (
    id             integer primary key default 1,
    scope          text not null,
    content_hash   text not null,
    built_as_of    date,
    plugin_version text,
    taxonomy_version integer,
    node_count     integer not null,
    edge_count     integer not null,
    source_count   integer not null,
    projected_at   timestamptz not null default now(),
    constraint single_row check (id = 1),
    constraint scope_is_known check (scope in ('public', 'full'))
);

-- ---------------------------------------------------------------------------
-- RLS — every table, at creation, default deny.
--
-- No policies are added. With RLS enabled and no policy, anon and authenticated
-- get nothing; the table owner and service_role still reach the data, which is
-- how the loader works. The `recruiting` path and any member-facing policy come
-- in a later migration, deliberately, rather than being sketched here.
-- ---------------------------------------------------------------------------
alter table node_types      enable row level security;
alter table edge_rels       enable row level security;
alter table files           enable row level security;
alter table nodes           enable row level security;
alter table edges           enable row level security;
alter table node_sources    enable row level security;
alter table projection_meta enable row level security;
