-- Reverses 0021. The coordinates are derived (pipeline/lib/layout.py) and are
-- recomputed by the next projection, so nothing is lost; the client falls back
-- to simulating the layout when /api/structure carries none.
drop table if exists node_layout;
