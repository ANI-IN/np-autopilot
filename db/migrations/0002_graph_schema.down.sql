-- 0002 down — drop in reverse dependency order.
--
-- Hand-written, not generated. Reviewed once here so it does not have to be
-- reasoned about on the day it is needed.
--
-- `drop table ... cascade` is deliberately NOT used: cascade would silently
-- remove objects a later migration added on top of these tables, which is the
-- rollback equivalent of a threshold that quietly excludes.
drop table if exists projection_meta;
drop table if exists node_sources;
drop table if exists edges;
drop table if exists nodes;
drop table if exists files;
drop table if exists edge_rels;
drop table if exists node_types;
