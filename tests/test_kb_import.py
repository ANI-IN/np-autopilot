"""M8 — Sheets import against the SYNTHETIC fixture (fixtures/sheets_sample.json):
dry run writes nothing, apply creates, re-apply creates nothing, an app edit is
flagged and never overwritten, a sheet change to an unedited record applies,
an app-created duplicate is flagged, and a contact column is refused."""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

import pytest

from kb_support import USERS, Client, ensure_users, owner, requires_kb, reset

pytestmark = requires_kb

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "fixtures" / "sheets_sample.json"

import importlib.util                                                   # noqa: E402

_spec = importlib.util.spec_from_file_location("kb_import_sheets", REPO / "pipeline" / "kb_import_sheets.py")
importer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(importer)

from pipeline.lib import kb_sheets                                    # noqa: E402


@pytest.fixture(autouse=True)
def _setup():
    ensure_users()
    reset()
    yield
    reset()


def run(apply=False, fixture=FIXTURE):
    return importer.run(argparse.Namespace(as_email="kbtest-admin@interviewkickstart.com", fixture=str(fixture),
                                           sheet_id=None, apply=apply, allow_production=False, report=None))


def _count(table):
    with owner() as c:
        return c.execute(f"select count(*) from kb.{table}").fetchone()[0]


def test_dry_run_reports_and_writes_nothing():
    r = run()
    assert r["mode"] == "dry-run"
    assert r["counts"]["create"] == 13 and r["counts"]["invalid"] == 7
    why = {(x["tab"], x["row"]): x["why"] for x in r["rows_needing_attention"]}
    assert "duplicate of row 3" in why[("Courses", 4)]
    assert "empty value in a list" in why[("Instructors", 3)]
    assert "invalid URL" in why[("Resources", 4)]
    assert "address or URL" in why[("Topics", 3)]
    assert r["broken_references"][0]["missing"] == "program 'No Such Program'"
    assert _count("nodes") == 0 and _count("audit_log") == 0 and _count("import_runs") == 0


def test_apply_then_reapply_is_a_no_op():
    r = run(apply=True)
    w = r["written"]
    assert w["nodes_created"] == 11 and w["resources_created"] == 2
    assert w["edges_created"] >= 6 and w["attachments_created"] == 2
    nodes, edges, audit = _count("nodes"), _count("edges"), _count("audit_log")
    with owner() as c:
        actor_types = {r[0] for r in c.execute("select distinct actor_type from kb.audit_log")}
        assert actor_types == {"import"}
        # module "Week 1" exists twice, scoped to two different courses
        assert c.execute("select count(*) from kb.nodes where name = 'Week 1'").fetchone()[0] == 2
    again = run(apply=True)
    assert again["counts"]["create"] == 0 and again["counts"]["update"] == 0
    assert again["counts"]["unchanged"] == 13
    assert all(v == 0 for v in again["written"].values()), again["written"]
    assert (_count("nodes"), _count("edges"), _count("audit_log")) == (nodes, edges, audit)
    assert _count("import_runs") == 2


def test_app_edit_is_flagged_and_never_overwritten(tmp_path):
    run(apply=True)
    with owner() as c:
        nid, ver = c.execute("select id, version from kb.nodes where name = 'Synthetic System Design'").fetchone()
    s, out = Client(USERS["editor"]).patch(f"/api/kb/nodes/{nid}", {"version": ver, "summary": "edited in the app"})
    assert s == 200
    changed = json.loads(FIXTURE.read_text(encoding="utf-8"))
    courses = next(v for v in changed["valueRanges"] if v["range"].startswith("Courses"))
    courses["values"][1][2] = "sheet changed this summary"
    courses["values"][2][2] = "sheet changed the algorithms summary"
    f = tmp_path / "changed.json"
    f.write_text(json.dumps(changed), encoding="utf-8")
    r = run(apply=True, fixture=f)
    statuses = {(x["tab"], x["row"]): x for x in r["rows_needing_attention"]}
    assert statuses[("Courses", 2)]["status"] == "conflict"
    assert "edited in the app" in statuses[("Courses", 2)]["why"]
    assert r["counts"]["update"] == 1 and r["written"]["nodes_updated"] == 1
    with owner() as c:
        assert c.execute("select summary from kb.nodes where id = %s", (nid,)).fetchone()[0] == "edited in the app"
        assert c.execute("select summary from kb.nodes where name = 'Synthetic Algorithms'").fetchone()[0] \
            == "sheet changed the algorithms summary"


def test_an_app_record_with_the_same_name_is_a_duplicate_not_a_second_record():
    Client(USERS["editor"]).post("/api/kb/programs", {"name": "synthetic backend track"})
    r = run()
    dup = [x for x in r["rows_needing_attention"] if x["status"] == "duplicate"]
    assert [(d["tab"], d["row"]) for d in dup] == [("Programs", 2)]
    run(apply=True)
    with owner() as c:
        assert c.execute("select count(*) from kb.nodes where name_norm = 'synthetic backend track'").fetchone()[0] == 1


def test_a_contact_column_is_refused_even_if_mapped(tmp_path):
    m = kb_sheets.load_mapping(REPO / "config" / "kb-sheets-mapping.yaml")
    bad = copy.deepcopy(m)
    bad["tabs"]["Instructors"]["fields"]["summary"] = "Email"
    p = tmp_path / "bad.yaml"
    import yaml
    p.write_text(yaml.safe_dump(bad), encoding="utf-8")
    with pytest.raises(kb_sheets.MappingError, match="contact-shaped"):
        kb_sheets.load_mapping(p)


def test_unmapped_columns_are_never_read():
    tabs = kb_sheets.parse_tabs(json.loads(FIXTURE.read_text(encoding="utf-8")))
    staged = kb_sheets.stage(kb_sheets.load_mapping(REPO / "config" / "kb-sheets-mapping.yaml"), tabs, "x")
    prog = [s for s in staged if s.tab == "Programs"][0]
    assert set(prog.values) == {"name", "summary"}
    assert "ignored" not in json.dumps([s.values for s in staged])
