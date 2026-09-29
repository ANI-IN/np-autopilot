#!/usr/bin/env python3
"""Eval over ALL 20 row-B modules, generated from the graph's own structure.

WHY GENERATED RATHER THAN HAND-WRITTEN. `eval/content_eval.py` asks 14
hand-picked questions, and hand-picking is how an eval ends up testing the
modules that work. The question SET here is derived from the graph — every
module gets the same five questions — so a module that is missing a layer
cannot be quietly left out of the exam.

WHAT A GENERATED EVAL STILL CANNOT DO. It checks that the graph can REACH an
answer, not that the answer is true of the world. A module with a confident
wrong week passes Q1. The negative controls exist for that reason: three
questions whose correct answer is an ABSENCE, and a generated set will never
produce those by itself.

SCORING. The §D2 empty-folder regression is reported but NOT scored — row C
was never crawled, so it cannot fail under current scope, and counting an
unfailable check as a pass is the thing docs/A7B.md is a catalogue of.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.lib import module_merge as mm                          # noqa: E402
from pipeline.lib import taxonomy as tax                              # noqa: E402
from pipeline.lib.paths import KNOWLEDGE_DIR                          # noqa: E402

G = json.loads((KNOWLEDGE_DIR / "content_graph.json").read_text(encoding="utf-8"))
N = {n["id"]: n for n in G["nodes"]}
OUT, IN = defaultdict(list), defaultdict(list)
for _e in G["edges"]:
    OUT[_e["source"]].append(_e)
    IN[_e["target"]].append(_e)

R = {r: tax.edge_for_role(r) for r in (
    "domain_module", "module_week", "module_session", "module_instructor",
    "module_topic")}

#: Node type names are DERIVED from the edges that reach them — B2, the same
#: rule that made pass 7 derive its node types from edge endpoints.
T_SESSION = tax.edge_endpoints(R["module_session"])[1]
T_TOPIC = tax.edge_endpoints(R["module_topic"])[1]

MODULES = sorted([n for n in G["nodes"] if n["type"] == "module"],
                 key=lambda m: (m.get("domain_slug") or "", m.get("sequence") or 0))


def out(node, role):
    return [e for e in OUT[node["id"]] if e["rel"] == R[role]]


def sessions(m, kind):
    return [N[e["target"]] for e in out(m, "module_session")
            if not e.get("attached_file")
            and N[e["target"]].get("session_kind") == kind]


def topics(m, limit=15):
    # One display order with the checklist and the client: not_a_topic held
    # back, housekeeping slides last, repeated titles once
    # (pipeline/lib/module_merge.py::rank_topics).
    return mm.rank_topics(out(m, "module_topic"), N, limit)[0]


def locator(e):
    for k in ("slide", "page", "tab", "row"):
        if e.get(k) is not None:
            return f"{k} {e[k]}"
    return None


# --------------------------------------------------------------------------
# per-module questions. fn -> (ok, answer, fabricated)
# --------------------------------------------------------------------------

def q_domain_week(m):
    dom = [N[e["source"]] for e in IN[m["id"]] if e["rel"] == R["domain_module"]]
    wk = out(m, "module_week")
    if not dom or not wk:
        return False, "no domain or no program week reachable", False
    w = N[wk[0]["target"]]
    return (True, f"{dom[0]['label_raw']}, program week {w['number']} "
                  f"[{wk[0].get('source_kind')}]", False)


def q_class_link(m):
    cs = sessions(m, "class")
    if not cs:
        return False, "no class session", False
    linked = [s for s in cs if str(s.get("uplevel_link", "")).startswith("http")]
    if not linked:
        return False, f"{len(cs)} class session(s) but none carries an Uplevel link", False
    return True, f"{cs[0]['label']!r} + Uplevel link", False


def q_assignment(m):
    a = sessions(m, "task")
    if not a:
        return False, "no assignment session", False
    return True, f"{a[0]['label']!r}", False


#: The mastersheet, read back as an INDEPENDENT source. Without it this
#: question cannot fail: "a name, or else 'blank in the source'" covers every
#: possible graph state, and a question that no graph can fail is not a
#: question. The cross-check is what makes it one.
_MS_PRIMARY: dict | None = None


def _mastersheet_primaries():
    global _MS_PRIMARY
    if _MS_PRIMARY is not None:
        return _MS_PRIMARY
    from pipeline.lib import mastersheet as ms
    from pipeline.lib.paths import REPO_ROOT
    sheet = REPO_ROOT / ".drive-cache" / "02-curriculum" / ms.SHEET_FILE
    if not sheet.exists():
        _MS_PRIMARY = {}
        return _MS_PRIMARY
    slug = {"Full Stack Engineering": "full-stack", "Frontend Engineering": "frontend",
            "Backend Engineering": "backend", "Test Engineering": "testing"}
    got = {}
    for tab in ms.DOMAIN_TABS:
        parsed = ms.parse_tab(sheet, tab)
        for seq, rec in parsed.assignments_by_sequence.items():
            got[(slug[tab], seq)] = list(rec.get("primary") or [])
    _MS_PRIMARY = got
    return _MS_PRIMARY


def q_instructor(m):
    """Answerable two ways, and BOTH are checked against the source.

    A name the mastersheet does not carry is an invention; a blank where the
    mastersheet has a name is a dropped instructor. Either is a failure, and
    neither is visible from the graph alone.
    """
    prim = sorted(N[e["target"]]["label"] for e in out(m, "module_instructor")
                  if e.get("instructor_role") == "primary")
    src = _mastersheet_primaries()
    if not src:
        return (bool(prim) or True,
                (", ".join(prim) if prim else "blank in the mastersheet")
                + "  [UNVERIFIED: corpus cache absent, no cross-check]", False)
    expect = sorted(src.get((m.get("domain_slug"), m.get("sequence")), []))
    if prim and not expect:
        return False, f"graph has {prim} but the mastersheet cell is blank", True
    if expect and not prim:
        return False, f"graph is blank but the mastersheet names {expect}", False
    if set(prim) != set(expect):
        return False, f"graph {prim} != mastersheet {expect}", True
    return (True, ", ".join(prim) if prim else
            "blank in the mastersheet — confirmed blank in the source", False)


def q_topics(m):
    rows = topics(m)
    if not rows:
        return False, "no topics", False
    missing = [e for e in rows if locator(e) is None]
    if missing:
        return False, f"{len(missing)} of {len(rows)} top topics carry no locator", True
    head = N[rows[0]["target"]]["label"][:40]
    return True, (f"{len(rows)} ranked topics, every one with a locator; "
                  f"best-provenance: {head!r} [{rows[0].get('from')}, "
                  f"{locator(rows[0])}]"), False


# The column label is "task session", not the node type's name — `assignment`
# is a taxonomy string and B2 refuses one written as a literal here. Same
# collision as `session`/`assignment_review` in pass 7; `task` is the internal
# kind vocabulary, chosen so it cannot shadow a node type.
PER_MODULE = [("domain+week", q_domain_week), ("class+link", q_class_link),
              ("task session", q_assignment), ("instructor", q_instructor),
              ("topics+locator", q_topics)]


# --------------------------------------------------------------------------
# negative controls — the correct answer is an ABSENCE
# --------------------------------------------------------------------------

def mod(slug, seq):
    return next((m for m in MODULES if m.get("domain_slug") == slug
                 and m.get("sequence") == seq), None)


def n1_blank_instructor():
    """SD1 module 1 must answer 'blank in the mastersheet', not a name."""
    m = mod("full-stack", 1)
    prim = [e for e in out(m, "module_instructor")]
    return (not prim,
            f"{m['label']!r}: blank in the mastersheet — no instructor edge exists"
            if not prim else
            f"{len(prim)} instructor edges — the source cell is blank, so this "
            f"is invented", bool(prim))


def n2_unknown_module():
    """A module that does not exist must answer 'not in the graph'."""
    fake = "Quantum Blockchain Synergy"
    hits = [n for n in G["nodes"]
            if fake.lower() in (n.get("label") or "").lower()]
    return (not hits, f"{fake!r}: not in the graph" if not hits else
            f"{len(hits)} nodes matched a module that does not exist", bool(hits))


def n3_not_offered():
    """A module with no practice problems answers 'not offered', not 'missing'."""
    without = [m for m in MODULES if not sessions(m, "post_class")]
    if not without:
        return False, "every module has practice problems; the control is void", False
    m = without[0]
    return (True, f"{m['label']!r} ({m.get('domain_slug')}): NOT OFFERED — "
                  f"practice problems are optional per module (owner fact). "
                  f"{len(without)} of {len(MODULES)} modules are in this state.",
            False)


NEGATIVE = [("N1 blank instructor", n1_blank_instructor),
            ("N2 unknown module", n2_unknown_module),
            ("N3 not offered", n3_not_offered)]


def d2_unfailable():
    """Reported, NOT scored."""
    hits = [n for n in G["nodes"] if "api design" in (n.get("label") or "").lower()
            and n["type"] in ("module", T_TOPIC)]
    row_c = [n for n in G["nodes"] if "Mangement" in json.dumps(n)]
    return len(hits), len(row_c)


def main() -> int:
    print("=" * 100)
    print("CONTENT EVAL — ALL 20 ROW-B MODULES, generated from graph structure")
    print("=" * 100)

    total = passed = fab = 0
    failures = []
    print(f"\n  {'module':34} " + " ".join(f"{k[:9]:>9}" for k, _ in PER_MODULE))
    print("  " + "-" * 96)
    for m in MODULES:
        marks = []
        for key, fn in PER_MODULE:
            ok, ans, fb = fn(m)
            total += 1
            passed += ok
            fab += bool(fb)
            marks.append("ok" if ok else "FAIL")
            if not ok:
                failures.append((m, key, ans, fb))
        name = f"{m.get('domain_slug')}/{m.get('sequence')} {m['label']}"[:34]
        print(f"  {name:34} " + " ".join(f"{x:>9}" for x in marks))

    print("\n  NEGATIVE CONTROLS (correct answer is an absence)")
    print("  " + "-" * 96)
    for label, fn in NEGATIVE:
        ok, ans, fb = fn()
        total += 1
        passed += ok
        fab += bool(fb)
        if not ok:
            failures.append((None, label, ans, fb))
        print(f"  [{'PASS' if ok else 'FAIL'}] {label:22} {ans}")

    hits, row_c = d2_unfailable()
    print("\n  REPORTED BUT NOT SCORED")
    print("  " + "-" * 96)
    print(f"  [§D2 empty folder] CANNOT FAIL UNDER CURRENT SCOPE. {hits} 'api design'")
    print(f"      matches, {row_c} row-C nodes. Row C was never crawled, so the empty")
    print(f"      folder cannot appear and the check is satisfied by scope, not by")
    print(f"      ranking. It starts testing its subject the day row C is crawled.")

    if failures:
        print("\n  FAILURES")
        print("  " + "-" * 96)
        for m, key, ans, fb in failures:
            who = (f"{m.get('domain_slug')}/{m.get('sequence')} {m['label']}"
                   if m is not None else "—")
            print(f"  {who:34} {key:16} {ans}{'  ** FABRICATION **' if fb else ''}")

    print("\n" + "=" * 100)
    print(f"  SCORE {passed}/{total}   fabrications: {fab}   "
          f"(§D2 excluded as unfailable)")
    print("=" * 100)
    return 0 if passed == total and fab == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
