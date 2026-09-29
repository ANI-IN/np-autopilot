"""Mastersheet parsing — the declared tab scope, and rows that must never vanish.

Owner decisions (Animesh Kumar, 2026-09-30, checklist review part 3):

- config/mastersheet-scope.yaml declares the four domain tabs and the four
  Uplevel Resources rows as READ; nine tabs as EXCLUDED, each with a reason.
  Every read goes through one check; an undeclared tab fails the build.
- The exact live cells that broke or could break parsing:
  `Full Stack Engineering!A47` "Week 1/5: Databases" (":" separator — the row
  was silently skipped and SD1/1 lost its three instructors),
  `Full Stack Engineering!B49` "Faraaz Sareshwala/" (trailing slash),
  `Backend Engineering!B47` "Konstantinos " (trailing space).
- An instructor row that does not map to a module FAILS, loudly.

The workbook here is SYNTHETIC — built in tmp_path with those exact strings —
so the tests run in CI, where the live sheet (contact data) never is.
"""
from __future__ import annotations

import sys
from pathlib import Path

import openpyxl
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.lib import mastersheet as ms                            # noqa: E402

UP = "https://uplevel.interviewkickstart.com/synthetic/"


def _tab(ws, modules, block, people=(("Synthetic Person",),)):
    """Module section, Drive Folder row, instructor block, instructor table —
    the live layout, in miniature."""
    ws.append(["Module Name", "Module - Uplevel Link", "Resource Name", "Type",
               "Resource Type", "Link"])
    for seq, name in modules:
        ws.append([f"Week {seq} - {name}", f"{UP}m{seq}", f"{name} - Class", "Live Class",
                   "Slides", f"{UP}s{seq}"])
    ws.append([])
    ws.append(["Drive Folder", "SDx: Synthetic"])
    ws.append([])
    ws.append(["Topic", "Primary Instructor", "Backup 1", "Backup 2", "Backup 3"])
    for row in block:
        ws.append(list(row))
    ws.append([])
    ws.append(["Name of the Instructor", "Contact #", "Email id"])
    for p in people:
        ws.append(list(p))


def _book(tmp_path, fullstack_block=None, extra_tabs=(), drop=()):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name in ms.DOMAIN_TABS:
        if name in drop:
            continue
        ws = wb.create_sheet(name)
        if name == "Full Stack Engineering":
            _tab(ws, [(1, "Databases"), (2, "API Design and Implementation"),
                      (3, "Cloud Infrastructure")],
                 fullstack_block if fullstack_block is not None else [
                     # EXACT live cells, 2026-09-30
                     ("Week 1/5: Databases", "Konstantinos Pappas", "Ashish Kaila",
                      "Nikhil Kolekar"),
                     ("Week 2/5 - API Design and Implementation", "Shelby Cohen"),
                     ("Week 3/5 - Cloud Infrastructure", "Faraaz Sareshwala/"),
                 ])
        else:
            _tab(ws, [(1, "Synthetic Module")],
                 [("Week 1/5 - Database Design ", "Konstantinos ")])
    up = wb.create_sheet(ms.UPLEVEL_TAB)
    up.append([])
    up.append([None, None, "Domain", "Uplevel Link"])
    for d in ms.DOMAIN_TABS:
        up.append([None, None, d, f"{UP}{d.split()[0].lower()}"])
    up.append([None, None, "Cloud Engineering", f"{UP}cloud"])
    for t in list(ms.EXCLUDED_TABS) + list(extra_tabs):
        wb.create_sheet(t).append(["synthetic"])
    p = tmp_path / "mastersheet.xlsx"
    wb.save(p)
    return p


# --------------------------------------------------------------------------
# parsing the exact live cells
# --------------------------------------------------------------------------

def test_a_colon_separator_is_a_module_row(tmp_path):
    t = ms.parse_tab(_book(tmp_path), "Full Stack Engineering")
    sd1_1 = t.assignments_by_sequence[1]
    assert sd1_1["primary"] == ["Konstantinos Pappas"]
    assert sd1_1["backup_1"] == ["Ashish Kaila"]
    assert sd1_1["backup_2"] == ["Nikhil Kolekar"]


def test_a_trailing_slash_is_tolerated(tmp_path):
    t = ms.parse_tab(_book(tmp_path), "Full Stack Engineering")
    assert t.assignments_by_sequence[3]["primary"] == ["Faraaz Sareshwala"]


def test_a_trailing_space_is_tolerated(tmp_path):
    t = ms.parse_tab(_book(tmp_path), "Backend Engineering")
    assert t.assignments_by_sequence[1]["primary"] == ["Konstantinos"]


@pytest.mark.parametrize("cell, want", [
    ("Faraaz Sareshwala/", ["Faraaz Sareshwala"]),
    ("Konstantinos ", ["Konstantinos"]),
    ("/Bill Ogden/Sindhu Singh Dua/", ["Bill Ogden", "Sindhu Singh Dua"]),
    ("", []),
])
def test_split_people(cell, want):
    assert ms.split_people(cell) == want


def test_an_empty_name_between_separators_fails():
    with pytest.raises(ms.MastersheetError):
        ms.split_people("Deval, , Adil")


@pytest.mark.parametrize("topic", [
    "Week 1/5 Databases",          # no separator at all
    "Databases (week 1)",          # not a module row shape
])
def test_an_instructor_row_that_does_not_map_fails_loudly(tmp_path, topic):
    p = _book(tmp_path, fullstack_block=[(topic, "Konstantinos Pappas")])
    with pytest.raises(ms.MastersheetError, match="never skipped"):
        ms.parse_tab(p, "Full Stack Engineering")


def test_an_instructor_row_for_a_week_with_no_module_fails(tmp_path):
    p = _book(tmp_path, fullstack_block=[("Week 9/5 - Nowhere", "Someone Real")])
    with pytest.raises(ms.MastersheetError, match="not a module"):
        ms.parse_tab(p, "Full Stack Engineering")


def test_two_instructor_rows_for_one_week_fail(tmp_path):
    p = _book(tmp_path, fullstack_block=[("Week 1/5: Databases", "A Person"),
                                         ("Week 1/5 - Databases", "B Person")])
    with pytest.raises(ms.MastersheetError, match="second"):
        ms.parse_tab(p, "Full Stack Engineering")


# --------------------------------------------------------------------------
# the declared scope
# --------------------------------------------------------------------------

def test_the_scope_is_the_owners_decision():
    s = ms.load_scope()
    assert s["origin"] == "hand" and s["decided_by"].startswith("Animesh Kumar")
    assert s["source"]["drive_id"] == "1setMmRvBUNu9_85nT4xvvUFySodB6kiWb7bQ8qLEqAQ"
    assert [x["drive_id"] for x in s["superseded"]] == ["1f4T6u2mcWjeJuBa02_E_Svrid4BbaCnB"]
    assert set(ms.DOMAIN_TABS) == {"Full Stack Engineering", "Backend Engineering",
                                   "Frontend Engineering", "Test Engineering"}
    assert set(ms.EXCLUDED_TABS) == {
        "Indian Instructors", "Training Sheet", "Instructor(FullStack)", "Interview Repo",
        "Upskill Guide", "Cloud Engineering", "SRE Engineering", "Security Engineering",
        "Embedded Systems"}
    assert all(ms.EXCLUDED_TABS.values()), "every exclusion carries a reason"


@pytest.mark.parametrize("tab", ["Indian Instructors", "Training Sheet",
                                 "Instructor(FullStack)", "Interview Repo", "Cloud Engineering"])
def test_an_excluded_tab_is_never_read(tmp_path, tab):
    p = _book(tmp_path)
    for reader in (ms._rows, ms.red_cells, ms.cell_links):
        with pytest.raises(ms.MastersheetError, match="refusing"):
            reader(p, tab)


def test_every_exclusion_is_logged_by_name(tmp_path):
    logged = dict(ms.check_workbook_scope(ms.sheetnames(_book(tmp_path))))
    assert set(logged) == set(ms.EXCLUDED_TABS)


def test_an_undeclared_tab_fails_the_build(tmp_path):
    p = _book(tmp_path, extra_tabs=["Mobile Engineering"])
    with pytest.raises(ms.MastersheetError, match="undeclared"):
        ms.check_workbook_scope(ms.sheetnames(p))


def test_a_missing_declared_tab_fails_the_build(tmp_path):
    p = _book(tmp_path, drop=["Test Engineering"])
    with pytest.raises(ms.MastersheetError, match="missing"):
        ms.check_workbook_scope(ms.sheetnames(p))


def test_uplevel_resources_reads_only_the_four_rows(tmp_path):
    got = ms.uplevel_resources(_book(tmp_path))
    assert set(got) == set(ms.DOMAIN_TABS)
    assert not any("cloud" in v for v in got.values())


def test_every_pipeline_read_goes_through_the_scope_check():
    """No `wb[tab]` outside the one guarded reader."""
    src = (REPO / "pipeline" / "lib" / "mastersheet.py").read_text(encoding="utf-8")
    reads = [l for l in src.splitlines() if "wb[tab]" in l]
    assert len(reads) == 2, reads          # _rows, and red_cells after _scoped()
    body = src.split("def _rows(", 1)[1].split("\ndef ", 1)[0]
    assert "_scoped(tab)" in body
