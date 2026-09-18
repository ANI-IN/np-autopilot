"""Constraints the documents assert, that nothing in the program checked.

Found by running DECISIONS §A.7b instance 9's question over STATE.md,
DECISIONS.md, AUTH.md and 07-risks.md: *for every constraint these assert, what
in the program would fail if it stopped being true?* 113 constraint-shaped
statements, 54 naming a concrete artefact, 24 distinct system constraints — and
five with no test at all.

THE PATTERN IN THE FIVE, which is the part worth keeping: four are in CLAUDE.md
or STATE.md, the documents most read and least executable, and three of those
four encode a bug that ALREADY HAPPENED ONCE. The constraints with the best
stories behind them were the least likely to have a test, because the story
feels like the safeguard. See §A.7b, "the story is not the test".

Ordered as they were written: the read-only rule first, because it is the only
one whose failure writes to the corpus.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.lib import db                                            # noqa: E402

PIPELINE = REPO / "pipeline"


# ---------------------------------------------------------------------------
# 1. The corpus is READ-ONLY — CLAUDE.md §1, the first rule in the file
# ---------------------------------------------------------------------------

def _writable_workbook_opens(source: str, where: str) -> list[str]:
    """Calls to load_workbook that do not pass read_only=True."""
    bad = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        name = (node.func.attr if isinstance(node.func, ast.Attribute)
                else getattr(node.func, "id", None))
        if name != "load_workbook":
            continue
        ro = next((k for k in node.keywords if k.arg == "read_only"), None)
        if ro is None or not (isinstance(ro.value, ast.Constant) and ro.value.value is True):
            bad.append(f"{where}:{node.lineno}")
    return bad


def test_every_workbook_is_opened_read_only():
    """`CLAUDE.md` §1: never write, move, rename or delete a corpus file.

    Enforced by every reader passing read_only=True. That was true of all
    thirteen call sites and asserted by nothing, so a fourteenth written without
    it would modify the corpus — the one failure in this file that is not
    recoverable by re-running anything.
    """
    offenders = []
    for py in sorted(PIPELINE.rglob("*.py")):
        if "__pycache__" in py.parts:
            continue
        offenders += _writable_workbook_opens(
            py.read_text(encoding="utf-8"), str(py.relative_to(REPO)))
    assert not offenders, (
        f"workbooks opened WRITABLE: {offenders}. The corpus mirrors a live "
        "Drive folder and is read-only; pass read_only=True.")


def test_the_read_only_check_catches_a_writable_open():
    """NEGATIVE CONTROL. Every real call site passes, so the positive case
    proves nothing about the checker."""
    assert _writable_workbook_opens(
        "import openpyxl\nwb = openpyxl.load_workbook(p, read_only=True)\n", "x") == []
    assert _writable_workbook_opens(
        "import openpyxl\nwb = openpyxl.load_workbook(p)\n", "x") == ["x:2"]
    assert _writable_workbook_opens(
        "import openpyxl\nwb = openpyxl.load_workbook(p, read_only=False)\n", "x") == ["x:2"]


# ---------------------------------------------------------------------------
# 2. Never name a pipeline script after a stdlib module — CLAUDE.md §3
# ---------------------------------------------------------------------------

def test_no_pipeline_script_shadows_a_stdlib_module():
    """`inspect.py` cost a full run: openpyxl and python-docx both import
    `inspect`, so every spreadsheet and Word read failed with a misleading
    circular-import error that looked like a data problem.

    Derived from sys.stdlib_module_names rather than the hand-written list in
    CLAUDE.md, so a module that becomes stdlib later is covered too.
    """
    shadows = sorted(
        str(py.relative_to(REPO)) for py in PIPELINE.rglob("*.py")
        if "__pycache__" not in py.parts
        and py.stem in sys.stdlib_module_names and py.stem != "__init__")
    assert not shadows, (
        f"these shadow a stdlib module: {shadows}. Anything importing the real "
        "module gets this one instead, and the error names an import cycle "
        "rather than the file.")


# ---------------------------------------------------------------------------
# 3. Employee IDs are evidence only, never the key — CLAUDE.md §2a
# ---------------------------------------------------------------------------

def test_employee_ids_are_evidence_never_a_key():
    """`IK-294` and `IK-INT30` each map to TWO people, and `Animesh Kumar` has
    two ids. Keying on them merges people; the key is the curated slug.

    Checks the two shapes that would reintroduce it: a lookup built from the
    field, and SQL joining on it.
    """
    offenders = []
    for py in sorted(REPO.rglob("*.py")):
        if "__pycache__" in py.parts or py.name == Path(__file__).name:
            continue
        if not any(p in py.parts for p in ("pipeline", "web", "api")):
            continue
        src = py.read_text(encoding="utf-8")
        if "employee_id" not in src:
            continue
        for i, line in enumerate(src.splitlines(), 1):
            code = line.split("#", 1)[0]
            if re.search(r"\b(join|JOIN)\b[^\n]*employee_id", code):
                offenders.append(f"{py.relative_to(REPO)}:{i} joins on employee_id")
            if re.search(r"(by_employee_id|\{[^}]*employee_id[^}]*:\s*)", code):
                offenders.append(f"{py.relative_to(REPO)}:{i} builds a lookup keyed on it")
    assert not offenders, (
        "employee ids used as an identity: " + "; ".join(offenders) +
        ". They are secondary evidence only — key on the slug in config/people.yaml.")


# ---------------------------------------------------------------------------
# 4. profiles.domain_is_ik — AUTH.md. The DATABASE enforces it; nothing
#    verified the enforcement still existed.
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not db.available(), reason="no database")
def test_the_domain_check_constraint_still_exists():
    """A migration dropping it would be silent: rows would simply start being
    accepted. This is instance 8's shape — a guard whose ABSENCE nobody notices.
    """
    with db.connect(db.SESSION) as conn, conn.cursor() as cur:
        cur.execute("""
            select c.conname from pg_constraint c
            join pg_class t on t.oid = c.conrelid
            where t.relname = 'profiles' and c.contype = 'c'
        """)
        names = {r[0] for r in cur.fetchall()}
    assert "domain_is_ik" in names, (
        f"profiles.domain_is_ik is gone; CHECK constraints present: {sorted(names)}. "
        "AUTH.md says the domain rule lives in the database so a route that "
        "forgot to check cannot create a row that bypasses it.")


# ---------------------------------------------------------------------------
# 5. pipeline/ never runs on Vercel — STATE.md
# ---------------------------------------------------------------------------

def test_vercelignore_excludes_every_pipeline_entrypoint():
    """Only `.vercelignore` stood behind this, and it is a hand-written path
    list — so a script added later is included by default.

    Derived: every top-level pipeline script must be excluded. `pipeline/lib/`
    is deliberately kept, because api/staffing.py reaches taxonomy through it.
    """
    ignore = (REPO / ".vercelignore").read_text(encoding="utf-8")
    patterns = [ln.strip() for ln in ignore.splitlines()
                if ln.strip() and not ln.strip().startswith("#")]

    def excluded(rel: str) -> bool:
        from fnmatch import fnmatch
        return any(fnmatch(rel, p) or fnmatch(rel, p.rstrip("/") + "/*")
                   for p in patterns)

    missing = sorted(
        f"pipeline/{py.name}" for py in PIPELINE.glob("*.py")
        if py.name != "__init__.py" and not excluded(f"pipeline/{py.name}"))
    assert not missing, (
        f"these pipeline scripts would be uploaded to Vercel: {missing}. "
        "Nothing in pipeline/ runs there; the function needs pipeline/lib/ only.")
