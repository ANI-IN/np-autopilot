"""D3 — the verifier must work THROUGH THE DATABASE, not only over files.

A verifier that only passes file-against-file has not been ported: the whole
point is to catch a migration that damaged something, and a migration damages
the database. So the same five injections that caught it before are re-run here
against Postgres.

Each injection damages the projection, asserts the verifier notices, and then
RESTORES by re-projecting. The restore is not cleanup — it is the last
assertion: a projection that cannot be rebuilt from the files is not a
projection, it is the source of truth by accident.

Skipped wherever there is no database. These tests need a live connection and a
completed projection; they are not part of the offline suite.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.lib import db, taxonomy                                  # noqa: E402

pytestmark = pytest.mark.skipif(
    not db.available(),
    reason="no SUPABASE_DB_URL_SESSION / psycopg — database tests skipped")


def _verify() -> tuple[int, str]:
    r = subprocess.run(
        [sys.executable, "pipeline/verify_migration.py", "--source", "supabase"],
        cwd=REPO, capture_output=True, text=True)
    return r.returncode, r.stdout


def _reproject() -> None:
    r = subprocess.run([sys.executable, "pipeline/project_graph.py"],
                       cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0, f"re-projection failed:\n{r.stdout}\n{r.stderr}"


def _damage(sql: str) -> None:
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        cur.execute(sql)
        conn.commit()


@pytest.fixture(autouse=True)
def restore_projection():
    """Leave the database exactly as found, whatever the test did."""
    yield
    _reproject()


def test_the_clean_projection_verifies():
    """The baseline. Without this, every failure below proves nothing."""
    code, out = _verify()
    assert code == 0, out
    assert "32/32 checks passed" in out


@pytest.mark.parametrize("name,sql,expect_in_output", [
    # The relational instinct that (source,target,rel) is the primary key. It is
    # not: 1,557 sourced_from duplicates in the public half carry no properties
    # at all, so they are byte-identical rows that a content-addressed id would
    # have collapsed.
    ("collapse duplicate triples",
     "delete from edges where id not in "
     "(select min(id) from edges group by rel, source_id, target_id, props)",
     "duplicates"),
    # A projection that keeps only corpus provenance, silently undoing C1.
    ("drop hand provenance",
     "delete from node_sources where origin = 'hand'",
     "provenance"),
    # An off-by-one in a batched insert.
    ("lose one node",
     "delete from nodes where id = (select id from nodes where type = 'person' "
     "order by id limit 1)",
     "node_counts"),
    # A single lost relationship.
    ("lose one edge",
     "delete from edges where id = (select id from edges where rel = 'teaches' "
     "order by id limit 1)",
     "edge_counts"),
])
def test_injected_damage_is_caught(name, sql, expect_in_output):
    _damage(sql)
    code, out = _verify()
    assert code != 0, f"{name} went undetected through the database path:\n{out}"
    assert "MISMATCH" in out
    assert any(line.startswith("  FAIL") and expect_in_output in line
               for line in out.splitlines()), (
        f"{name} was caught, but not by a {expect_in_output} check:\n"
        + "\n".join(l for l in out.splitlines() if l.startswith("  FAIL"))
    )


def test_a_count_preserving_rewiring_is_caught():
    """Counts alone would pass this. Only the content hash and components catch it."""
    rel = taxonomy.edge_for_role("workflow_theme")
    _damage(f"""
        update edges set target_id = (
            select n.id from nodes n
            where n.type = 'theme' and n.id <> edges.target_id
            order by n.id limit 1)
        where id = (select id from edges where rel = '{rel}' order by id limit 1)
    """)
    code, out = _verify()
    assert code != 0, f"a rewiring that preserves every count went undetected:\n{out}"
    fails = [l for l in out.splitlines() if l.startswith("  FAIL")]
    assert any("content_hash" in l or "components" in l for l in fails), fails
    # and prove the counts really were preserved, so the point lands
    assert not any("totals" in l or "edge_counts" in l for l in fails), (
        "the rewiring changed a count, so it does not demonstrate what it claims"
    )


def test_rls_is_enabled_on_every_table():
    """A table created without RLS is the bug that does not announce itself."""
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        cur.execute("""
            select c.relname, c.relrowsecurity
            from pg_class c join pg_namespace n on n.oid = c.relnamespace
            where n.nspname = 'public' and c.relkind = 'r'
            order by c.relname""")
        rows = cur.fetchall()
    assert rows, "no tables found"
    missing = [name for name, rls in rows if not rls]
    assert not missing, f"RLS is not enabled on: {missing}"


def test_default_deny_actually_denies():
    """RLS enabled with no policy must return nothing to anon and authenticated.

    Asserted against a table with rows in it, so "0 rows" cannot be confused
    with "empty table".
    """
    with db.connect(db.SESSION) as conn:
        with conn.cursor() as cur:
            cur.execute("select count(*) from nodes")
            owner_rows = cur.fetchone()[0]
        assert owner_rows > 0, "nodes is empty; this test would prove nothing"
        for role in ("anon", "authenticated"):
            with conn.cursor() as cur:
                cur.execute(f'set local role "{role}"')
                try:
                    cur.execute("select count(*) from nodes")
                    assert cur.fetchone()[0] == 0, f"{role} can read nodes"
                except Exception as exc:                       # noqa: BLE001
                    assert "permission denied" in str(exc).lower(), exc
                conn.rollback()


def test_the_sensitive_half_is_not_in_the_database():
    """This phase projects the public half only. Assert it, do not assume it."""
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        cur.execute("select count(*) from nodes where sensitive")
        assert cur.fetchone()[0] == 0, "sensitive nodes reached the database"
        cur.execute("select count(*) from nodes "
                    "where props->>'pipeline_status' in ('rejected','in_pipeline')")
        assert cur.fetchone()[0] == 0, "hiring-funnel records reached the database"
        cur.execute("select scope from projection_meta where id = 1")
        assert cur.fetchone()[0] == "public"


# --------------------------------------------------------------------------
# R1 — adding a node type must ADD, never rewrite
# --------------------------------------------------------------------------

def test_node_and_edge_types_are_lookup_tables_not_enums():
    """The design guarantee, pinned.

    Proved once on a real throwaway migration: inserting an `automation` node
    type and an `automates` edge type rewrote ZERO tables (relfilenode unchanged
    on nodes, edges and node_sources), the verifier stayed 32/32 with them
    present, and the rollback removed them cleanly.

    This test stops someone "tidying" the lookups into enums later, which would
    turn that insert back into DDL that takes a lock and rewrites rows.
    """
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        cur.execute("""
            select c.relname, c.relkind
            from pg_class c join pg_namespace n on n.oid = c.relnamespace
            where n.nspname = 'public'
              and c.relname in ('node_types', 'edge_rels')""")
        kinds = dict(cur.fetchall())
        assert kinds.get("node_types") == "r", "node_types is not an ordinary table"
        assert kinds.get("edge_rels") == "r", "edge_rels is not an ordinary table"

        # And no enum type is used by any column on the graph tables.
        cur.execute("""
            select c.relname, a.attname, t.typname
            from pg_attribute a
            join pg_class c on c.oid = a.attrelid
            join pg_namespace n on n.oid = c.relnamespace
            join pg_type t on t.oid = a.atttypid
            where n.nspname = 'public' and a.attnum > 0 and not a.attisdropped
              and t.typtype = 'e'""")
        enums = cur.fetchall()
        assert not enums, (
            f"enum-typed columns found: {enums}. Adding a value to an enum is "
            "DDL that takes a lock; adding a row to a lookup table is an insert."
        )


def test_adding_a_type_requires_no_schema_change_at_all():
    """A new type is an INSERT. Demonstrated, then cleaned up."""
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        cur.execute("select relfilenode from pg_class where relname = 'nodes'")
        before = cur.fetchone()[0]
        cur.execute("insert into node_types(name,description) "
                    "values ('probe_type','transient')")
        cur.execute("select relfilenode from pg_class where relname = 'nodes'")
        after = cur.fetchone()[0]
        cur.execute("delete from node_types where name = 'probe_type'")
        conn.commit()
    assert before == after, "adding a node type rewrote the nodes table"
