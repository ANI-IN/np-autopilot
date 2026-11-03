"""Run 6 (B1): owners become real people. Settings -> People (CSV preview, then
confirm), automatic linking on sign-in, "Claim this profile" (Approvals),
"Owned by you", and the Data quality lists. Synthetic people only; e-mail
addresses never reach the audit log, the change feed, or a non-admin."""
from __future__ import annotations

import json
import uuid

import pytest

from kb_support import USERS, Client, as_user, ensure_users, owner, requires_kb, reset

pytestmark = requires_kb

DOMAIN = "interviewkickstart.com"
NEW = {k: str(uuid.uuid5(uuid.NAMESPACE_URL, f"np-kb-test/people/{k}")) for k in ("ada", "una", "twin", "nobody", "mail")}


@pytest.fixture(autouse=True)
def _setup():
    ensure_users()
    reset()
    _cleanup()
    yield
    reset()
    _cleanup()


def _cleanup():
    with owner() as c:
        c.execute("truncate kb.person_accounts")
        c.execute("delete from kb.proposals where action = 'claim'")
        c.execute("delete from public.profiles where user_id = any(%s::uuid[])", (list(NEW.values()),))
        c.execute("delete from auth.users where id = any(%s::uuid[])", (list(NEW.values()),))


@pytest.fixture
def admin():
    return Client(USERS["admin"])


@pytest.fixture
def editor():
    return Client(USERS["editor"])


def _node(c, type_, name, **kw):
    s, n = c.post("/api/kb/nodes", {"type": type_, "name": name, **kw})
    assert s == 201, n
    return n


def _owned(c, name, **owners):
    """A module owned by role (owners by role are set by an edit, not at create)."""
    n = _node(c, "module", name, owner_id=None)
    s, n = c.patch(f"/api/kb/nodes/{n['id']}", {"version": n["version"], **owners})
    assert s == 200, n
    return n


def sign_in(key: str, email: str, full_name: str | None = None) -> str:
    """What a first sign-in does: an auth user and the profile the 0015 hook makes."""
    uid = NEW[key]
    with owner() as c:
        c.execute("insert into auth.users (id, email, raw_user_meta_data, created_at) values (%s, %s, %s, now())",
                  (uid, email, json.dumps({"full_name": full_name} if full_name else {})))
        c.execute("insert into profiles (user_id, email, email_domain, role) values (%s, %s, %s, 'member')",
                  (uid, email, DOMAIN))
    return uid


def _account(node_id):
    with owner() as c:
        return c.execute("select email, user_id::text, linked_by from kb.person_accounts where node_id = %s",
                         (node_id,)).fetchone()


def _no_address_anywhere(address: str):
    with owner() as c:
        assert c.execute("select count(*) from kb.audit_log where coalesce(before::text, '') || coalesce(after::text, '') ilike %s",
                         (f"%{address}%",)).fetchone()[0] == 0
        assert c.execute("select count(*) from kb.changes where row_to_json(changes)::text ilike %s",
                         (f"%{address}%",)).fetchone()[0] == 0
        assert c.execute("select count(*) from kb.proposals where coalesce(payload::text, '') ilike %s",
                         (f"%{address}%",)).fetchone()[0] == 0


# ---------------------------------------------------------------------------- CSV
def test_csv_preview_matches_and_writes_nothing(admin):
    ada = _node(admin, "instructor", "Ada Example")
    bo = _node(admin, "instructor", "Bo Lee")
    # two people with one name: the KB keeps them apart as "Sam Twin" and "Sam Twin (2)"
    t1, t2 = _node(admin, "instructor", "Sam Twin"), _node(admin, "instructor", "Sam Twin (2)")
    csv = "\n".join(["name,email", "Ada Example,ada@example.org", "  bo   LEE ,bo@example.org",
                     "Ada Exampel,ada2@example.org", "Sam Twin,sam@example.org", "Nobody Known,nobody@example.org",
                     ",x@example.org", "Bad Mail,not-an-address"])
    s, out = admin.post("/api/kb/person-records/preview", {"csv": csv})
    assert s == 200, out
    st = {r["name"].strip(): r for r in out["rows"]}
    assert st["Ada Example"]["status"] == "exact" and st["Ada Example"]["match"]["id"] == ada["id"]
    assert st["bo   LEE"]["status"] == "normalised" and st["bo   LEE"]["match"]["id"] == bo["id"]
    assert st["Ada Exampel"]["status"] == "suggested" and st["Ada Exampel"]["candidates"][0]["id"] == ada["id"]
    assert st["Sam Twin"]["status"] == "ambiguous" and {x["id"] for x in st["Sam Twin"]["candidates"]} == {t1["id"], t2["id"]}
    assert "match" not in st["Sam Twin"]                                 # never picked for the admin
    assert st["Nobody Known"]["status"] == "none"
    assert [r["status"] for r in out["rows"] if r["status"] == "invalid"] == ["invalid", "invalid"]
    assert out["written"] == 0
    with owner() as c:
        assert c.execute("select count(*) from kb.person_accounts").fetchone()[0] == 0
        assert c.execute("select count(*) from kb.changes where kind = 'owner.account'").fetchone()[0] == 0


def test_csv_confirm_links_only_the_confirmed_rows_and_keeps_addresses_private(admin, editor):
    ada, bo = _node(admin, "instructor", "Ada Example"), _node(admin, "instructor", "Bo Lee")
    s, out = admin.post("/api/kb/person-records/link", {"links": [{"node_id": ada["id"], "email": "Ada@Example.org"}]})
    assert s == 200 and out["written"] == 1 and out["waiting_for_sign_in"] == 1
    assert _account(ada["id"]) == ("ada@example.org", None, "csv") and _account(bo["id"]) is None
    _no_address_anywhere("ada@example.org")
    # admins only: the list, the preview and the confirm; editors read no address
    assert editor.get("/api/kb/person-records")[0] == 403
    assert editor.post("/api/kb/person-records/preview", {"csv": "a,b@c.de"})[0] == 403
    assert editor.post("/api/kb/person-records/link", {"links": [{"node_id": bo["id"], "email": "b@c.de"}]})[0] == 403
    with as_user(USERS["editor"]) as c:
        assert c.execute("select count(*) from kb.person_accounts").fetchone()[0] == 0
    s, n = editor.get(f"/api/kb/nodes/{ada['id']}")
    assert n["account"] is None
    s, lst = admin.get("/api/kb/person-records", "q=ada")
    assert [x["email"] for x in lst["items"]] == ["ada@example.org"]
    # the same address on a second record is refused (one account, one person)
    s, err = admin.post("/api/kb/person-records/link", {"links": [{"node_id": bo["id"], "email": "ada@example.org"}]})
    assert s == 409, err


# ---------------------------------------------------------------------------- sign-in
def test_sign_in_links_by_email_then_by_an_unambiguous_name(admin):
    ada = _node(admin, "instructor", "Ada Example")
    module = _owned(admin, "Ada's Module", owner_record_id=ada["id"])
    admin.post("/api/kb/person-records/link", {"links": [{"node_id": ada["id"], "email": "ada@example.org"}]})
    uid = sign_in("ada", "ada@example.org")
    assert _account(ada["id"])[1:] == (uid, "csv")
    with owner() as c:            # she now owns, as an account, what her record owns by role
        assert str(c.execute("select owner_id from kb.nodes where id = %s", (module["id"],)).fetchone()[0]) == uid

    una = _node(admin, "instructor", "Una Unique")
    uid2 = sign_in("una", "una.unique@example.org", "Una  unique")
    assert _account(una["id"]) == ("una.unique@example.org", uid2, "sign_in_name")
    _no_address_anywhere("una.unique@example.org")


def test_two_people_with_the_same_name_are_never_linked_automatically(admin):
    a = _node(admin, "instructor", "Sam Twin")
    t2 = _node(admin, "instructor", "Sam Twin (2)")                     # one name, two people
    uid = sign_in("twin", "sam.twin@example.org")
    assert _account(a["id"]) is None and _account(t2["id"]) is None
    me = Client(uid)
    s, out = me.post("/api/kb/my/link")
    assert s == 200 and out["status"] == "ambiguous" and out["person"] is None
    assert {x["id"] for x in out["candidates"]} == {a["id"], t2["id"]}
    # "Claim this profile" -> Approvals -> an admin approves
    s, cl = me.post("/api/kb/claims", {"node_id": a["id"], "reason": "the backend one"})
    assert s == 202 and cl["proposal_id"]
    assert me.post("/api/kb/claims", {"node_id": a["id"]})[1]["proposal_id"] == cl["proposal_id"]   # once
    assert _account(a["id"]) is None
    props = admin.get("/api/kb/proposals")[1]["items"]
    claim = next(p for p in props if p["id"] == cl["proposal_id"])
    assert claim["action"] == "claim" and "sam.twin" not in json.dumps(claim)
    assert Client(USERS["editor"]).post(f"/api/kb/proposals/{claim['id']}/approve")[0] == 403    # admins decide claims
    s, d = admin.post(f"/api/kb/proposals/{claim['id']}/approve")
    assert s == 200, d
    assert _account(a["id"]) == ("sam.twin@example.org", uid, "claim") and _account(t2["id"]) is None
    assert me.post("/api/kb/my/link")[1]["person"]["id"] == a["id"]
    _no_address_anywhere("sam.twin@example.org")


def test_a_sign_in_with_no_match_links_nothing(admin):
    _node(admin, "instructor", "Someone Else")
    uid = sign_in("nobody", "nobody.here@example.org")
    with owner() as c:
        assert c.execute("select count(*) from kb.person_accounts").fetchone()[0] == 0
    s, out = Client(uid).post("/api/kb/my/link")
    assert s == 200 and out["status"] == "none" and out["person"] is None and not out.get("candidates")


def test_owned_by_you_counts_your_account_and_your_person_record(admin):
    ada = _node(admin, "instructor", "Ada Example")
    by_role = _owned(admin, "Owned By Role", owner_record_id=ada["id"])
    backup = _owned(admin, "Backed Up", co_owner_record_ids=[ada["id"]])
    _node(admin, "module", "Someone Else's", owner_id=None)
    uid = sign_in("mail", "ada.mail@example.org")
    mine = _node(admin, "module", "Owned As Account", owner_id=uid)
    admin.post("/api/kb/person-records/link", {"links": [{"node_id": ada["id"], "email": "ada.mail@example.org"}]})
    s, out = Client(uid).get("/api/kb/my/owned")
    assert s == 200, out
    got = {x["name"]: x["how"] for x in out["items"]}
    assert got == {"Owned As Account": "owner", "Owned By Role": "owner", "Backed Up": "co-owner"} or \
        set(got) == {"Owned As Account", "Owned By Role", "Backed Up"}
    assert out["person"]["id"] == ada["id"] and out["total"] == 3
    assert {by_role["id"], backup["id"], mine["id"]} == {x["id"] for x in out["items"]}


# ---------------------------------------------------------------------------- Data quality lists
def test_legacy_domains_still_referenced_as_expertise(admin):
    legacy_dom = _node(admin, "domain", "Old Domain")
    other = _node(admin, "domain", "Other Old Domain")
    current = _node(admin, "instructor", "Current Teacher")
    with owner() as c:
        c.execute("update kb.nodes set is_legacy = true where id = any(%s::uuid[])", ([legacy_dom["id"], other["id"]],))
    s, e = admin.post("/api/kb/edges", {"type": "sme", "source_id": current["id"], "target_id": legacy_dom["id"]})
    assert s == 201, e
    s, out = Client(USERS["viewer"]).get("/api/kb/quality/legacy-expertise")
    assert s == 200 and [x["name"] for x in out["items"]] == ["Old Domain"] and out["items"][0]["instructors"] == 1
