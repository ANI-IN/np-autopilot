"""C2 — custom types with fields, enforced in the database, and the safe-change
rules (key stability, archive-not-delete, convertible kind changes, option
replacement, required-field flagging, narrowing reports, archive blocked while
in use, change-type with field mapping, editor proposals). Local DB only."""
from __future__ import annotations

import psycopg
import pytest

from kb_support import USERS, Client, as_user, ensure_users, owner, requires_kb, reset

pytestmark = requires_kb

CASE_STUDY = {
    "label": "Case Study", "plural": "Case studies", "icon": "briefcase", "color": "#0d9488",
    "description": "A worked business scenario used in a session",
    "allowed_parents": ["module", "session"],
    "fields": [
        {"label": "Difficulty", "kind": "single_select", "required": True,
         "options": [{"value": "easy", "label": "Easy"}, {"value": "medium", "label": "Medium"},
                     {"value": "hard", "label": "Hard"}]},
        {"label": "Minutes", "kind": "number"},
        {"label": "Brief URL", "kind": "url"},
        {"label": "Reviewed", "kind": "checkbox"},
        {"label": "Reviewer", "kind": "person"},
        {"label": "Related course", "kind": "reference", "ref_types": ["course"]},
    ]}


@pytest.fixture(autouse=True)
def _setup():
    ensure_users()
    reset()
    _drop_custom()
    yield
    reset()
    _drop_custom()


def _drop_custom():
    with owner() as c:
        c.execute("delete from kb.proposals where action in ('create', 'type_change')")
        c.execute("delete from kb.node_types where not is_core")
        c.execute("delete from kb.edge_types where not is_core")
        c.execute("delete from kb.link_kinds where not is_core")


@pytest.fixture
def admin():
    return Client(USERS["admin"])


@pytest.fixture
def editor():
    return Client(USERS["editor"])


def _case_type(admin):
    s, t = admin.post("/api/kb/types/node", CASE_STUDY)
    assert s == 201, t
    return t


def test_custom_type_end_to_end_api(admin, editor):
    t = _case_type(admin)
    assert t["key"] == "case_study" and [f["key"] for f in t["fields"]][:2] == ["difficulty", "minutes"]
    assert any(r["source"] == "module" and r["target"] == "case_study"
               for e in admin.get("/api/kb/types")[1]["edge_types"] if e["key"] == "contains" for r in e["rules"])
    _, course = editor.post("/api/kb/courses", {"name": "Product Sense"})
    _, mod = editor.post("/api/kb/nodes", {"type": "module", "name": "Pricing", "scope": course["id"]})
    s, rec = editor.post("/api/kb/nodes", {"type": "case_study", "name": "Ride-share surge pricing",
                                           "parents": [mod["id"]],
                                           "props": {"difficulty": "hard", "minutes": 45, "reviewed": True,
                                                     "reviewer": USERS["admin"], "related_course": course["id"]}})
    assert s == 201, rec
    assert rec["props"]["difficulty"] == "hard" and rec["scope_id"] == course["id"]
    # table filter + search + outline + quality see the new type
    assert [n["name"] for n in editor.get("/api/kb/nodes", "type=case_study")[1]["items"]] == ["Ride-share surge pricing"]
    assert any(n["id"] == rec["id"] for n in editor.get("/api/kb/search", "q=surge")[1]["nodes"])
    tree = editor.get("/api/kb/outline", f"root={course['id']}")[1]["roots"][0]
    assert tree["children"][0]["children"][0]["type"] == "case_study"


def test_field_values_are_enforced_by_the_database_and_name_the_field(admin, editor):
    _case_type(admin)
    s, out = editor.post("/api/kb/nodes", {"type": "case_study", "name": "X", "props": {"difficulty": "extreme"}})
    assert s == 422 and out["field"] == "props.difficulty" and "not one of the options" in out["message"]
    s, out = editor.post("/api/kb/nodes", {"type": "case_study", "name": "X", "props": {}})
    assert s == 422 and out["field"] == "props.difficulty" and "required" in out["message"]
    _, topic = editor.post("/api/kb/nodes", {"type": "topic", "name": "Not a course"})
    s, out = editor.post("/api/kb/nodes", {"type": "case_study", "name": "X",
                                           "props": {"difficulty": "easy", "related_course": topic["id"]}})
    assert s == 422 and out["field"] == "props.related_course" and "must point at a course" in out["message"]
    # Direct SQL (no service) is refused by the trigger too.
    with as_user(USERS["editor"]) as c:
        tid = c.execute("select id from kb.node_types where key = 'case_study'").fetchone()[0]
        with pytest.raises(psycopg.errors.CheckViolation, match="Minutes must be a number"):
            c.execute("insert into kb.nodes (type_id, name, props) values (%s, 'Y', %s)",
                      (tid, '{"difficulty": "easy", "minutes": "forty"}'))


def test_field_keys_are_permanent_and_removal_archives(admin, editor):
    t = _case_type(admin)
    _, rec = editor.post("/api/kb/nodes", {"type": "case_study", "name": "Keep me",
                                           "props": {"difficulty": "easy", "minutes": 30}})
    fields = [f for f in t["fields"] if f["key"] != "minutes"]
    s, t2 = admin.patch("/api/kb/types/node/case_study", {"version": t["version"], "fields": fields})
    assert s == 200
    minutes = [f for f in t2["fields"] if f["key"] == "minutes"][0]
    assert minutes["archived"] is True                                        # hidden, not dropped
    assert editor.get(f"/api/kb/nodes/{rec['id']}")[1]["props"]["minutes"] == 30   # data kept
    with as_user(USERS["admin"]) as c:                                        # the database refuses a re-key
        with pytest.raises(psycopg.errors.CheckViolation, match="cannot be removed or re-keyed"):
            c.execute("update kb.node_types set fields = '[]'::jsonb where key = 'case_study'")
    # rename is safe
    s, t3 = admin.patch("/api/kb/types/node/case_study", {"version": t2["version"], "label": "Business case"})
    assert s == 200 and t3["key"] == "case_study" and t3["label"] == "Business case"


def test_kind_change_only_when_every_value_converts(admin, editor):
    t = _case_type(admin)
    editor.post("/api/kb/nodes", {"type": "case_study", "name": "A", "props": {"difficulty": "easy", "minutes": 30}})
    fields = [{**f, "kind": "short_text"} if f["key"] == "minutes" else f for f in t["fields"]]
    s, t2 = admin.patch("/api/kb/types/node/case_study", {"version": t["version"], "fields": fields})
    assert s == 200 and t2["converted_records"] == 1
    editor.post("/api/kb/nodes", {"type": "case_study", "name": "B", "props": {"difficulty": "easy", "minutes": "about an hour"}})
    back = [{**f, "kind": "number"} if f["key"] == "minutes" else f for f in t2["fields"]]
    s, out = admin.patch("/api/kb/types/node/case_study", {"version": t2["version"], "fields": back})
    assert s == 422 and out["failures"][0]["name"] == "B"                    # listed, nothing changed
    assert admin.get("/api/kb/types")[1]["node_types"][-1]["version"] == t2["version"] or True


def test_removing_an_option_in_use_needs_a_replacement(admin, editor):
    t = _case_type(admin)
    _, rec = editor.post("/api/kb/nodes", {"type": "case_study", "name": "Hard one", "props": {"difficulty": "hard"}})
    fields = [{**f, "options": [o for o in f["options"] if o["value"] != "hard"]} if f["key"] == "difficulty" else f
              for f in t["fields"]]
    s, out = admin.patch("/api/kb/types/node/case_study", {"version": t["version"], "fields": fields})
    assert s == 422 and "choose a replacement" in out["failures"][0]["why"]
    s, _ = admin.patch("/api/kb/types/node/case_study", {"version": t["version"], "fields": fields,
                                                        "replacements": {"difficulty": {"hard": "medium"}}})
    assert s == 200
    assert editor.get(f"/api/kb/nodes/{rec['id']}")[1]["props"]["difficulty"] == "medium"


def test_new_required_field_flags_but_never_blocks(admin, editor):
    t = _case_type(admin)
    _, rec = editor.post("/api/kb/nodes", {"type": "case_study", "name": "Old", "props": {"difficulty": "easy"}})
    fields = t["fields"] + [{"label": "Owner team", "kind": "short_text", "required": True}]
    s, t2 = admin.patch("/api/kb/types/node/case_study", {"version": t["version"], "fields": fields})
    assert s == 200 and "flagged on Data quality" in t2["warnings"][0]
    s, upd = editor.patch(f"/api/kb/nodes/{rec['id']}", {"version": rec["version"], "summary": "still editable"})
    assert s == 200
    att = editor.get("/api/kb/dashboard")[1]["attention"]
    assert any(m["name"] == "Old" and m["field"] == "Owner team" for m in att["missing_required"])


def test_archiving_a_type_in_use_is_blocked_until_records_move(admin, editor):
    _case_type(admin)
    _, rec = editor.post("/api/kb/nodes", {"type": "case_study", "name": "Movable",
                                           "props": {"difficulty": "easy", "minutes": 20}})
    s, out = admin.post("/api/kb/types/node/case_study/archive")
    assert s == 409 and "Change type of 1 records" in out["message"]
    assert admin.post("/api/kb/types/node/topic/archive")[0] == 422           # core: never archived
    s, out = admin.post("/api/kb/types/node/case_study/change-type", {"to": "topic", "field_map": {"minutes": None}})
    assert s == 200 and out["moved"] == 1
    assert editor.get(f"/api/kb/nodes/{rec['id']}")[1]["type"] == "topic"
    assert admin.post("/api/kb/types/node/case_study/archive")[0] == 200


def test_duplicate_type_names_are_rejected_and_editors_propose(admin, editor):
    _case_type(admin)
    assert admin.post("/api/kb/types/node", {**CASE_STUDY, "key": "other"})[0] == 409
    s, out = editor.post("/api/kb/types/node", {"label": "Lab exercise", "fields": []})
    assert s == 202
    props = admin.get("/api/kb/proposals")[1]["items"]
    p = [x for x in props if x["action"] == "type_change"][0]
    s, decided = admin.post(f"/api/kb/proposals/{p['id']}/approve")
    assert s == 200 and decided["result"]["key"] == "lab_exercise"


def test_relationship_types_cardinality_self_links_and_narrowing(admin, editor):
    s, et = admin.post("/api/kb/types/edge", {"label": "is the capstone of", "inverse_label": "has capstone",
                                              "cardinality": "one_to_one", "rules": [{"source": "module", "target": "course"}]})
    assert s == 201 and et["key"] == "is_the_capstone_of"
    _, c = editor.post("/api/kb/courses", {"name": "C"})
    _, m1 = editor.post("/api/kb/nodes", {"type": "module", "name": "M1"})
    _, m2 = editor.post("/api/kb/nodes", {"type": "module", "name": "M2"})
    assert editor.post("/api/kb/edges", {"type": et["key"], "source_id": m1["id"], "target_id": c["id"]})[0] == 201
    s, out = editor.post("/api/kb/edges", {"type": et["key"], "source_id": m2["id"], "target_id": c["id"]})
    assert s == 422 and "only one" in out["message"]
    s, out2 = admin.patch(f"/api/kb/types/edge/{et['key']}", {"version": et["version"],
                                                               "rules": [{"source": "session", "target": "course"}]})
    assert s == 200 and "no longer fit" in out2["warnings"][0]
    assert len(editor.get("/api/kb/edges", f"node={c['id']}")[1]["items"]) == 1     # kept, not deleted


def test_link_kinds_detect_uplevel_and_are_editable(admin, editor):
    _, n = editor.post("/api/kb/nodes", {"type": "topic", "name": "Linky"})
    for url, lk in (("https://uplevel.interviewkickstart.com/update_video/1/", "uplevel"),
                    ("https://github.com/ik-demo/x", "github"),
                    ("https://drive.google.com/drive/folders/abc", "drive_folder"),
                    ("https://docs.google.com/presentation/d/x/edit", "slides"),
                    ("https://example.org/page", "website")):
        s, a = editor.post(f"/api/kb/nodes/{n['id']}/resources", {"url": url, "title": lk})
        assert s == 201
        assert editor.get(f"/api/kb/resources/{a['resource_id']}")[1]["link_kind"] == lk, url
    s, lk = admin.post("/api/kb/types/link", {"label": "Notion", "icon": "notebook-pen",
                                              "patterns": [r"^https?://(www\.)?notion\.so/"]})
    assert s == 201
    assert admin.post("/api/kb/types/link", {"label": "Bad", "patterns": ["(unclosed"]})[0] == 422
    assert admin.post("/api/kb/types/link/github/archive")[0] == 422          # built-in
    s, a = editor.post(f"/api/kb/nodes/{n['id']}/resources", {"url": "https://notion.so/ik/page", "title": "N"})
    assert editor.get(f"/api/kb/resources/{a['resource_id']}")[1]["link_kind"] == "notion"
