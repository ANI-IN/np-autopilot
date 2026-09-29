-- 0021 — B3: the structure view's layout, computed once at projection time.
--
-- The client ran a force simulation on every page load: 366 frames, ~6.4 s to
-- a settled layout (docs/perf/b3-local-before.json), recomputing the same
-- coordinates every time for a graph that changes only when the projection
-- runs. project_graph.py now computes them (pipeline/lib/layout.py) and writes
-- them here; /api/structure ships them and the client starts frozen.
--
-- ITS OWN TABLE, not columns on `nodes`: the nodes COPY, rows_for() and the
-- verifier's round trip are unchanged, and a coordinate is presentation, not a
-- fact about the node.
--
-- RLS exactly as node_sources: a coordinate is visible only when its node is.
-- The EXISTS runs under the caller's RLS on `nodes`, so a withheld node's
-- position is withheld with it. Rebuilt by TRUNCATE + COPY on every projection.
-- ---------------------------------------------------------------------------

create table node_layout (
    node_id text primary key references nodes(id) on delete cascade,
    x       real not null,
    y       real not null
);

comment on table node_layout is
    'Structure-view coordinates, computed at projection time '
    '(pipeline/lib/layout.py). Presentation only; RLS follows nodes.';

alter table node_layout enable row level security;

create policy node_layout_select on node_layout
    for select to authenticated
    using ((((select np_role()) <> 'none'::text)
            AND (EXISTS ( SELECT 1 FROM nodes n WHERE (n.id = node_layout.node_id)))));

grant select on node_layout to authenticated;
