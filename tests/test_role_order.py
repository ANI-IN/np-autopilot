"""Role order — "sequence matters" (owner requirement, 2026-09-30).

"Who teaches what" and every other place roles appear sort by BEST role
(Primary, Backup 1, Backup 2, Backup 3); within a role by the programme week of
the first module where that role is held; joint roles keep the sheet's cell
order. The owner gave the expected Backend and Testing orders.

The rule under test is the client's OWN code: the `roleSort` block between the
ROLE ORDER markers in public/index.html is run in Node on the real merged
graph's current-mastersheet roles. The facts are gathered here the way
`roleEntries` gathers them in the page (tier, role, week, cell order, domain).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.lib import graphio, taxonomy                               # noqa: E402

INDEX = (REPO / "public" / "index.html").read_text(encoding="utf-8")

EXPECTED = {
    "backend": [
        ("primary", ["Konstantinos Pappas", "Tilo Dickopp", "Robert Kreznarich",
                     "Sanjay Dhar", "Faraaz Sareshwala"]),
        ("backup_1", ["Shelby Cohen", "Jeff Wisman"]),
        ("backup_2", ["Nikhil Kolekar", "Reginald Johnson"]),
        ("backup_3", ["Ashish Kaila"]),
    ],
    "testing": [
        ("primary", ["William David Ogden", "Sindhu Singh Dua", "Bharath Anand",
                     "Rodrigo Salazar", "Hetal Modi", "Sergey Togulev",
                     "Balaji Santhanam"]),
        ("backup_1", ["Balaram Velaga", "Azeem Ghumman"]),
        ("backup_2", ["Sanjay Dhar"]),
    ],
}


def _block() -> str:
    m = re.search(r"// ROLE ORDER: begin\n(.*?)// ROLE ORDER: end", INDEX, re.S)
    assert m, "the ROLE ORDER block is gone from public/index.html"
    code = re.search(r"const DOMAIN_CODE=\{[^}]*\};", INDEX)
    assert code, "DOMAIN_CODE is gone from public/index.html"
    return m.group(1) + "\n" + code.group(0)


def _entries(g: dict) -> list[dict]:
    nodes = {n["id"]: n for n in g["nodes"]}
    week = {}
    for e in g["edges"]:
        if e["rel"] == taxonomy.edge_for_role("module_week") and e["target"] in nodes:
            week[e["source"]] = nodes[e["target"]].get("number")
    out = []
    for e in g["edges"]:
        if e.get("tier") != "mastersheet":
            continue
        a, b = nodes.get(e["source"]), nodes.get(e["target"])
        if not a or not b:
            continue
        mod = a if a["type"] == "module" else b if b["type"] == "module" else None
        ins = a if a["type"] == "instructor" else b if b["type"] == "instructor" else None
        if not mod or not ins:
            continue
        out.append({"ins": ins["id"], "label": ins["label"], "role": e.get("instructor_role"),
                    "week": week.get(mod["id"]), "dom": mod.get("domain_slug"),
                    "cell": e.get("cell_order")})
    return out


def _run(entries: list[dict], dom: str) -> list[dict]:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    js = _block() + """
const E=JSON.parse(require('fs').readFileSync(0,'utf8'));
const D=process.argv[1];
const got=roleSort(E.filter(e=>e.dom===D).map(e=>Object.assign({},e,{code:DOMAIN_CODE[e.dom]||''})));
console.log(JSON.stringify(got.map(o=>({label:o.label,role:o.role}))));
"""
    r = subprocess.run([node, "-e", js, dom], input=json.dumps(entries),
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@pytest.fixture(scope="module")
def entries():
    try:
        return _entries(graphio.load_merged())
    except FileNotFoundError as exc:
        pytest.skip(f"merged graph not available: {exc}")


@pytest.mark.parametrize("dom", sorted(EXPECTED))
def test_the_owners_order(entries, dom):
    got = _run(entries, dom)
    want = [(role, name) for role, names in EXPECTED[dom] for name in names]
    assert [(o["role"], o["label"]) for o in got] == want


def test_every_staffing_edge_carries_its_cell_order(entries):
    assert entries and all(isinstance(e["cell"], int) for e in entries), \
        "a current-mastersheet role without cell_order cannot keep the sheet's order"


@pytest.mark.parametrize("fn", ["renderMatrix", "moduleColumn"])
def test_the_views_use_the_one_rule(fn):
    i = INDEX.index(f"function {fn}(")
    body = INDEX[i:INDEX.index("\nfunction ", i + 10)]
    assert "roleSort(" in body, f"{fn} no longer orders by roleSort"


def test_the_panels_follow_the_same_order():
    for fn in ("peopleRows", "taughtRows"):
        i = INDEX.index(f"function {fn}(")
        body = INDEX[i:INDEX.index("\nfunction ", i + 10)]
        assert "best(a)-best(b)" in body, f"{fn} no longer sorts by best role first"
    assert "wk(a)-wk(b)" in INDEX, "the instructor panel no longer sorts a role group by week"
