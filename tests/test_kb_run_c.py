"""Run C (owner decisions 2026-11-07): the curriculum model end to end.

  * Domains classify (in_domain); the old names are hidden search aliases, never returned.
  * Week-agnostic: no week records, no week parents.
  * OWNERS are NP team members (owned_by), many-to-many; never instructors (database + API).
  * SMEs are instructors with a REQUIRED role: primary, backup 1-3, or a named role (database + API).
  * One entity profile / one entity component: record panel, Graph editor, Map.
  * The source catalog (kb.sources) is admin-only.

SYNTHETIC records (kb_support resets the kb tables around each test). The browser half is
tests/test_kb_run_c_ui.py (screenshots under testing/evidence/, gitignored: the repo is public).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from kb_support import USERS, Client, ensure_users, owner, requires_kb, reset

from pipeline.lib import taxonomy  # noqa: E402

OWNED_BY = taxonomy.edge_for_role("domain_primary")
pytestmark = [requires_kb]
EVIDENCE = Path(__file__).resolve().parent.parent / "testing" / "evidence"


@pytest.fixture(autouse=True)
def _setup():
    ensure_users()
    reset()
    yield
    reset()


def shot(page, feature: str, test_id: str):
    d = EVIDENCE / feature
    d.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(d / f"{test_id}.png"))


def _curriculum():
    """A program -> course -> module -> topic chain, a domain, two NP team members, three instructors."""
    ad = Client(USERS["admin"])
    _, dom = ad.post("/api/kb/nodes", {"type": "domain", "name": "Backend"})
    _, prog = ad.post("/api/kb/programs", {"name": "RunC Program"})
    _, course = ad.post("/api/kb/courses", {"name": "RunC Course", "parents": [prog["id"]]})
    _, mod = ad.post("/api/kb/nodes", {"type": "module", "name": "RunC Database Design", "parents": [course["id"]]})
    _, topic = ad.post("/api/kb/nodes", {"type": "topic", "name": "RunC Indexing", "parents": [mod["id"]]})
    tm = [ad.post("/api/kb/nodes", {"type": "team_member", "name": f"RunC Owner {i}"})[1] for i in (1, 2)]
    ins = [ad.post("/api/kb/nodes", {"type": "instructor", "name": f"RunC Instructor {i}"})[1] for i in (1, 2, 3)]
    s, e = ad.post("/api/kb/edges", {"type": "in_domain", "source_id": mod["id"], "target_id": dom["id"]})
    assert s == 201, e
    return {"dom": dom, "prog": prog, "course": course, "mod": mod, "topic": topic, "tm": tm, "ins": ins}


# ------------------------------------------------------------------ database and API
def test_owners_are_team_members_only_and_many_to_many():
    d = _curriculum()
    ad = Client(USERS["admin"])
    s, e = ad.post("/api/kb/edges", {"type": OWNED_BY, "source_id": d["mod"]["id"], "target_id": d["ins"][0]["id"]})
    assert s == 422 and "not allowed" in json.dumps(e)                       # an instructor is never an owner
    for t in d["tm"]:
        assert ad.post("/api/kb/edges", {"type": OWNED_BY, "source_id": d["mod"]["id"], "target_id": t["id"]})[0] == 201
    assert ad.post("/api/kb/edges", {"type": OWNED_BY, "source_id": d["prog"]["id"], "target_id": d["tm"][0]["id"]})[0] == 201
    prof = ad.get(f"/api/kb/nodes/{d['mod']['id']}")[1]["profile"]
    assert sorted(o["name"] for o in prof["owners"]) == ["RunC Owner 1", "RunC Owner 2"]
    owns = ad.get(f"/api/kb/nodes/{d['tm'][0]['id']}")[1]["profile"]["owns"]
    assert sorted(o["name"] for o in owns) == ["RunC Database Design", "RunC Program"]
    # the run-5 owner-by-role field refuses an instructor too (API and database)
    v = ad.get(f"/api/kb/nodes/{d['mod']['id']}")[1]["version"]
    s, e = ad.patch(f"/api/kb/nodes/{d['mod']['id']}", {"version": v, "owner_record_id": d["ins"][0]["id"]})
    assert s == 422 and "team member" in e["message"]
    with owner() as c:
        with pytest.raises(Exception, match="NP team member"):
            c.execute("update kb.nodes set owner_record_id = %s where id = %s", (d["ins"][0]["id"], d["mod"]["id"]))


def test_sme_needs_a_role_and_backups_need_an_order():
    d = _curriculum()
    ad = Client(USERS["admin"])
    m = d["mod"]["id"]
    s, e = ad.post("/api/kb/edges", {"type": "sme", "source_id": d["ins"][0]["id"], "target_id": m})
    assert s == 422 and "needs a role" in e["message"]
    s, e = ad.post("/api/kb/edges", {"type": "sme", "source_id": d["ins"][0]["id"], "target_id": m, "props": {"role": "backup", "rank": 4}})
    assert s == 422 and "1, 2 or 3" in e["message"]
    s, e = ad.post("/api/kb/edges", {"type": "sme", "source_id": d["ins"][0]["id"], "target_id": d["course"]["id"], "props": {"role": "primary"}})
    assert s == 422                                                            # SMEs are module-level
    assert ad.post("/api/kb/edges", {"type": "sme", "source_id": d["ins"][2]["id"], "target_id": m, "props": {"role": "backup", "rank": 2}})[0] == 201
    assert ad.post("/api/kb/edges", {"type": "sme", "source_id": d["ins"][0]["id"], "target_id": m, "props": {"role": "Primary"}})[0] == 201
    assert ad.post("/api/kb/edges", {"type": "sme", "source_id": d["ins"][1]["id"], "target_id": m, "props": {"role": "backup", "rank": "1"}})[0] == 201
    prof = ad.get(f"/api/kb/nodes/{m}")[1]["profile"]
    assert [(s["name"], s["label"]) for s in prof["smes"]] == [("RunC Instructor 1", "Primary"), ("RunC Instructor 2", "Backup 1"),
                                                                ("RunC Instructor 3", "Backup 2")]
    # an instructor's side lists the module with the role; a role change keeps the assignment's other data
    sme_of = ad.get(f"/api/kb/nodes/{d['ins'][2]['id']}")[1]["profile"]["sme_of"]
    assert sme_of[0]["label"] == "Backup 2"
    edge = next(s for s in prof["smes"] if s["name"] == "RunC Instructor 3")
    with owner() as c:
        c.execute("update kb.edges set props = props || '{\"provenance\": {\"source\": \"test\"}}' where id = %s", (edge["edge_id"],))
        ver = c.execute("select version from kb.edges where id = %s", (edge["edge_id"],)).fetchone()[0]
    assert ad.patch(f"/api/kb/edges/{edge['edge_id']}", {"version": ver, "props": {"role": "backup", "rank": 3}})[0] == 200
    with owner() as c:
        p = c.execute("select props from kb.edges where id = %s", (edge["edge_id"],)).fetchone()[0]
    assert p["rank"] == 3 and p["provenance"] == {"source": "test"}
    # two primaries are kept (the sources have them) and reported by Data quality
    assert ad.post("/api/kb/edges", {"type": "sme", "source_id": d["ins"][2]["id"], "target_id": d["mod"]["id"], "props": {"role": "primary"}})[0] == 409
    _, mod2 = ad.post("/api/kb/nodes", {"type": "module", "name": "RunC Two Primaries"})
    for i in (0, 1):
        assert ad.post("/api/kb/edges", {"type": "sme", "source_id": d["ins"][i]["id"], "target_id": mod2["id"], "props": {"role": "primary"}})[0] == 201
    q = ad.get("/api/kb/quality")[1]
    assert any(r["name"] == "RunC Two Primaries" and r["issue"] == "several primary SMEs" for r in q["sme_roles"]["items"])


def test_week_agnostic_and_domain_is_a_classification():
    d = _curriculum()
    ad = Client(USERS["admin"])
    s, e = ad.post("/api/kb/nodes", {"type": "week", "name": "Week 3"})
    assert s in (404, 422)                                                     # the week type is retired
    types = {t["key"]: t for t in ad.get("/api/kb/types")[1]["node_types"]}
    assert "week" not in types and set(types["module"]["allowed_parents"]) == {"course", "program"}
    assert ad.post("/api/kb/nodes", {"type": "module", "name": "RunC In Domain", "parents": [d["dom"]["id"]]})[0] == 422
    prof = ad.get(f"/api/kb/nodes/{d['mod']['id']}")[1]["profile"]
    assert [x["name"] for x in prof["domains"]] == ["Backend"]
    assert [x["name"] for x in ad.get(f"/api/kb/nodes/{d['dom']['id']}")[1]["profile"]["modules"]] == ["RunC Database Design"]


def test_old_domain_names_are_hidden_search_aliases():
    d = _curriculum()
    with owner() as c:
        c.execute("update kb.nodes set search_aliases = 'SD3 Backend Engineering' where id = %s", (d["dom"]["id"],))
    vw = Client(USERS["viewer"])
    hits = vw.get("/api/kb/search", "q=SD3")[1]
    assert any(str(i["id"]) == d["dom"]["id"] for i in hits["nodes"]), hits
    assert all("SD3" not in i["name"] for i in hits["nodes"])
    node = vw.get(f"/api/kb/nodes/{d['dom']['id']}")[1]
    assert "search_aliases" not in node and "SD3" not in json.dumps(node)    # never displayed


def test_profile_shows_program_specific_schedule_and_provenance():
    d = _curriculum()
    with owner() as c:
        c.execute("""update kb.edges set props = '{"schedule": {"program": "RunC Program", "rows": [{"label": "10", "start": 10, "end": 10}]}}'
                     where source_id = %s and target_id = %s""", (d["course"]["id"], d["mod"]["id"]))
        c.execute("""update kb.nodes set props = props || '{"provenance": [{"source": "confluence", "page_title": "A KYP page",
                     "page_version": 5, "url": "https://example.invalid/kyp", "heading": "7. Curriculum", "row": 11}]}' where id = %s""", (d["mod"]["id"],))
    prof = Client(USERS["viewer"]).get(f"/api/kb/nodes/{d['mod']['id']}")[1]["profile"]
    used = prof["used_in"][0]
    assert used["name"] == "RunC Course" and used["programs"][0]["name"] == "RunC Program"
    assert used["schedule"] == {"program": "RunC Program", "labels": ["10"]}
    assert prof["sources"][0]["page_version"] == 5 and prof["sources"][0]["row"] == 11
    assert [t["name"] for t in prof["topics"]] == ["RunC Indexing"]
    # the Map reads the same record by its own id
    assert Client(USERS["viewer"]).get(f"/api/kb/nodes/by-ref/{d['mod']['id']}")[1]["profile"]["used_in"][0]["name"] == "RunC Course"


def test_source_catalog_is_admin_only():
    with owner() as c:
        c.execute("""insert into kb.sources (provider, resource_id, kind, title, url, status, failure_reason, provenance)
                     values ('drive', 'runc-1', 'document', 'RunC doc', 'https://docs.google.com/document/d/runc-1', 'extracted', null, '{registry,Folder A}'),
                            ('drive', 'runc-2', 'folder', null, 'https://drive.google.com/drive/folders/runc-2', 'failed',
                             'not found or not shared with the service account', '{registry}')
                     on conflict do nothing""")
    try:
        assert Client(USERS["viewer"]).get("/api/kb/sources")[0] == 403
        assert Client(USERS["editor"]).get("/api/kb/sources")[0] == 403
        s, d = Client(USERS["admin"]).get("/api/kb/sources", "status=failed")
        assert s == 200 and d["total"] >= 1 and d["items"][0]["failure_reason"]
        s, sm = Client(USERS["admin"]).get("/api/kb/sources/summary")
        assert s == 200 and any(r["status"] == "failed" for r in sm["by_status"])
    finally:
        with owner() as c:
            c.execute("delete from kb.sources where resource_id like 'runc-%%'")


def test_create_with_owners_and_sme_roles_in_one_save():
    d = _curriculum()
    ad = Client(USERS["admin"])
    s, n = ad.post("/api/kb/nodes", {"type": "module", "name": "RunC One Save", "parents": [d["course"]["id"]],
                                     "owners": [d["tm"][0]["id"], d["tm"][1]["id"]],
                                     "smes": [{"id": d["ins"][0]["id"], "role": "primary"}, {"id": d["ins"][1]["id"], "role": "backup", "rank": 1},
                                              {"new": {"name": "RunC New Instructor"}, "role": "backup", "rank": 2}]})
    assert s == 201, n
    prof = n["profile"]
    assert [x["label"] for x in prof["smes"]] == ["Primary", "Backup 1", "Backup 2"]
    assert len(prof["owners"]) == 2
    s, e = ad.post("/api/kb/nodes", {"type": "module", "name": "RunC Bad Owner", "owners": [d["ins"][0]["id"]]})
    assert s == 422 and e.get("field", "").startswith("owners")
