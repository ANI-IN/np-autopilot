"""scripts/retire_legacy_sections.py (owner decision 2026-11-07): weeks, workflows
(processes) and themes are archived reversibly; week numbers move onto the
course -> module link; owner suggestions leave the records for a local file
outside git; the sync never imports the retired source types again.

SYNTHETIC records in the local test database (kb_support resets the kb tables).
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import yaml

from kb_support import USERS, Client, owner, requires_kb, reset

REPO = Path(__file__).resolve().parent.parent
pytestmark = [requires_kb]


def _script():
    spec = importlib.util.spec_from_file_location("retire_legacy_sections", REPO / "scripts" / "retire_legacy_sections.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture()
def data():
    reset()
    ed = Client(USERS["editor"])
    _, course = ed.post("/api/kb/courses", {"name": "Retire Course"})
    _, mod = ed.post("/api/kb/nodes", {"type": "module", "name": "Retire Module", "parents": [course["id"]]})
    with owner() as c:
        c.execute("select set_config('kb.actor_type', 'sync', false), set_config('kb.operator', 'on', false)")
        tid = lambda k: c.execute("select id from kb.node_types where key = %s", (k,)).fetchone()[0]      # noqa: E731
        week = c.execute("insert into kb.nodes (type_id, name, props, scope_id) values (%s, 'Week 7', '{\"week_number\": 7}', %s) returning id",
                         (tid("week"), mod["id"])).fetchone()[0]
        proc = c.execute("insert into kb.nodes (type_id, name, props) values (%s, 'Retire Process', '{\"workflow_id\": \"9\", \"suggested_owner\": \"Person 1\"}') returning id",
                         (tid("process"),)).fetchone()[0]
        contains = c.execute("select id from kb.edge_types where key = 'contains'").fetchone()[0]
        c.execute("insert into kb.edges (edge_type_id, source_id, target_id) values (%s, %s, %s)", (contains, mod["id"], week))
    yield {"course": course["id"], "module": mod["id"], "week": str(week), "process": str(proc)}
    reset()


def _state(c, d):
    q = lambda sql, *a: c.execute(sql, a).fetchone()                        # noqa: E731
    return {
        "week_archived": q("select archived_at is not null from kb.nodes where id = %s", d["week"])[0],
        "process_archived": q("select archived_at is not null from kb.nodes where id = %s", d["process"])[0],
        "week_edge_archived": q("select archived_at is not null from kb.edges where target_id = %s", d["week"])[0],
        "schedule": q("select props->'schedule' from kb.edges where source_id = %s and target_id = %s", d["course"], d["module"])[0],
        "suggested": q("select props->>'suggested_owner' from kb.nodes where id = %s", d["process"])[0],
        "week_type_archived": q("select archived_at is not null from kb.node_types where key = 'week'")[0],
    }


def test_apply_then_revert_is_exact(data, tmp_path, monkeypatch):
    m = _script()
    monkeypatch.setattr(m, "PRIVATE", tmp_path)
    kb_types = m._config()
    assert set(kb_types) >= {"week", "process"}
    import psycopg
    from kb_support import session_dsn
    with psycopg.connect(session_dsn()) as c:
        before = _state(c, data)
        assert before == {"week_archived": False, "process_archived": False, "week_edge_archived": False,
                          "schedule": None, "suggested": "Person 1", "week_type_archived": False}
        try:
            res = m.apply(c, kb_types, "test")
            c.commit()
            assert res["suggestions_exported"] == 1 and res["links_scheduled"] == 1
            after = _state(c, data)
            assert after["week_archived"] and after["process_archived"] and after["week_edge_archived"] and after["week_type_archived"]
            assert after["schedule"] == {"week": 7, "program": None, "from_week_record": data["week"]}
            assert after["suggested"] is None
            saved = json.loads((tmp_path / "workflow-owner-suggestions-test.json").read_text(encoding="utf-8"))
            assert saved == [{"node_id": data["process"], "external_id": None, "workflow_id": "9", "suggested_owner": "Person 1"}]
            # the module itself carries no week (week and order belong to each program)
            assert c.execute("select props ? 'week_number' from kb.nodes where id = %s", (data["module"],)).fetchone()[0] is False
        finally:
            m.revert(c, kb_types, "test")
            c.commit()
        assert _state(c, data) == before


def test_the_script_refuses_production_and_remote_databases(capsys):
    import subprocess
    import sys
    from pipeline.lib.db import PROD_PROJECT_REF
    for url, extra in ((f"postgresql://u:p@db.{PROD_PROJECT_REF}.supabase.co:5432/postgres", ["--remote-ok"]),
                       ("postgresql://u:p@example.invalid:5432/postgres", [])):
        r = subprocess.run([sys.executable, str(REPO / "scripts" / "retire_legacy_sections.py"), "plan", "--db", url, *extra],
                           capture_output=True, text=True, timeout=60)
        assert r.returncode == 2 and "refused" in r.stdout


def test_the_sync_never_imports_the_retired_types():
    m = yaml.safe_load((REPO / "config" / "kb-projection-mapping.yaml").read_text(encoding="utf-8"))
    from pipeline.lib import taxonomy
    retired = set(m["retired_types"])
    assert len(retired) == 3 and retired <= set(taxonomy.node_type_names()), retired
    assert all(t in m["types"] for t in retired)            # each maps to a KB type the script archives
    src = (REPO / "web" / "lib" / "kb" / "sync.py").read_text(encoding="utf-8")
    assert 'RETIRED = set(M.get("retired_types") or ())' in src
    assert 'n["type"] not in TYPE_MAP or n["type"] in RETIRED' in src
