#!/usr/bin/env python3
"""Phase 4 — eval for the row-B content graph.

Same rules as `eval/run_eval.py`:

  * every question is a RETRIEVAL against the graph, not a prose answer. If the
    graph cannot reach the fact, the question FAILS. That is the point.
  * some questions pass ONLY by returning "not in the corpus" / "ambiguous".
    A plausible invention scores WORSE than a failure and is flagged.
  * no question is edited to make the graph look better.

The set covers API Design (Backend) in full, one module in each other domain,
and the regression `docs/PRE-CRAWL-DECISIONS.md` §D2 wrote down before any code
existed: an EMPTY folder whose name is this project's canonical query must not
outrank the real module.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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
    "module_deck", "module_topic", "module_repo",
    "curriculum_module", "module_assignment", "domain_curriculum",
    "domain_primary", "domain_secondary")}

#: NODE TYPE NAMES ARE DERIVED FROM THE EDGES THAT REACH THEM, never written
#: out. `tests/test_taxonomy_single_source.py` caught four literals in this
#: file — the same B2 rule that `pipeline/07_build_content_graph.py` already
#: follows, and the reason it derives its node types from edge endpoints.
T_CURRICULUM_DOC = tax.edge_endpoints(R["curriculum_module"])[0]
T_CONTENT_TOPIC = tax.edge_endpoints(R["module_topic"])[1]


def module(slug: str, seq: int):
    return next((n for n in G["nodes"] if n["type"] == "module"
                 and n.get("domain_slug") == slug and n.get("sequence") == seq), None)


def out(node, role):
    return [e for e in OUT[node["id"]] if e["rel"] == R[role]]


# --------------------------------------------------------------------------
# questions: (id, prose, fn) -> fn returns (ok, answer, fabricated)
# --------------------------------------------------------------------------
Q = []


def q(qid, prose):
    def deco(fn):
        Q.append((qid, prose, fn))
        return fn
    return deco


# ---- API Design (Backend), the full chain --------------------------------

@q("C1", "Which domain and program week is Backend's API Design module in?")
def _c1():
    m = module("backend", 3)
    dom = N[[e for e in IN[m["id"]] if e["rel"] == R["domain_module"]][0]["source"]]
    wk = out(m, "module_week")
    if not wk:
        return False, "no program week", False
    w = N[wk[0]["target"]]
    return (dom["label_raw"] == "SD3: Backend Engineering" and w["number"] == 11,
            f"{dom['label_raw']}, program week {w['number']} "
            f"[{wk[0]['source_kind']}]", False)


@q("C2", "Is there a KYP for Backend, and what kind of curriculum doc is there?")
def _c2():
    m = module("backend", 3)
    docs = [N[e["source"]] for e in IN[m["id"]] if e["rel"] == R["curriculum_module"]]
    dom_docs = [n for n in G["nodes"] if n["type"] == T_CURRICULUM_DOC
                and any(N[e["source"]]["label_raw"] == "SD3: Backend Engineering"
                        for e in IN[n["id"]]
                        if e["rel"] == R["domain_curriculum"])]
    kinds = {d["kind"] for d in dom_docs}
    # PASSES ONLY BY SAYING NO KYP EXISTS.
    return ("kyp" not in kinds,
            f"no KYP for Backend; curriculum docs present: {sorted(kinds) or 'none'}",
            "kyp" in kinds)


@q("C3", "Which live class and which assignment session does API Design have?")
def _c3():
    m = module("backend", 3)
    kinds = {N[e["target"]]["session_kind"]: N[e["target"]]["label"]
             for e in out(m, "module_session") if not e.get("attached_file")}
    return ("class" in kinds and "task" in kinds,
            f"class={kinds.get('class')!r}, assignment={kinds.get('task')!r}", False)


@q("C4", "Which slide decks does API Design have, and what does one contain?")
def _c4():
    m = module("backend", 3)
    decks = [N[e["target"]] for e in out(m, "module_deck")]
    tops = [e for e in out(m, "module_topic") if e.get("slide")]
    sample = sorted({N[e["target"]]["label"] for e in tops})[:3]
    return (len(decks) >= 5 and bool(tops),
            f"{len(decks)} decks; topics with slide numbers e.g. {sample}", False)


@q("C5", "Who are API Design's instructors, and who is primary vs backup?")
def _c5():
    m = module("backend", 3)
    by = defaultdict(list)
    for e in out(m, "module_instructor"):
        by[e["instructor_role"]].append(N[e["target"]]["label"])
    return (bool(by.get("primary")),
            "; ".join(f"{k}: {', '.join(sorted(v))}" for k, v in sorted(by.items())),
            False)


@q("C6", "Who OWNS the API Design module?")
def _c6():
    m = module("backend", 3)
    owners = [e for e in OUT[m["id"]]
              if e["rel"] in (R["domain_primary"], R["domain_secondary"])]
    # PASSES ONLY BY REFUSING. Owners were deferred; the graph has no owner layer.
    return (not owners,
            "no owner recorded — module ownership is DEFERRED and no owner edge "
            "exists in this graph. Not a gap in the data; a scope decision.",
            bool(owners))


@q("C7", "What related files and repos does API Design have?")
def _c7():
    m = module("backend", 3)
    repos = [N[e["target"]]["label"] for e in out(m, "module_repo")]
    att = [e for e in out(m, "module_session") if e.get("attached_file")]
    return (bool(att),
            f"{len(att)} files attached at session level, {len(repos)} repos", False)


# ---- one module in each other domain -------------------------------------

@q("C8", "Full Stack, API Design and Implementation: week, sessions, instructors")
def _c8():
    m = module("full-stack", 2)
    wk = out(m, "module_week")
    return (bool(wk) and bool(out(m, "module_instructor")),
            f"week {N[wk[0]['target']]['number']}, "
            f"{len([e for e in out(m,'module_session') if not e.get('attached_file')])} sessions, "
            f"{len(out(m,'module_instructor'))} instructors", False)


@q("C9", "Frontend, Frontend System Design: does it have practice problems?")
def _c9():
    m = module("frontend", 3)
    kinds = {N[e["target"]]["session_kind"] for e in out(m, "module_session")
             if not e.get("attached_file")}
    return ("post_class" in kinds, "yes — post_class session present", False)


@q("C10", "Test Engineering, API Testing: does it have practice problems?")
def _c10():
    m = module("testing", 3)
    kinds = {N[e["target"]]["session_kind"] for e in out(m, "module_session")
             if not e.get("attached_file")}
    # PASSES ONLY BY SAYING NOT OFFERED, not "missing".
    return ("post_class" not in kinds,
            "NOT OFFERED — practice problems are optional per module "
            "(owner fact). Not a gap.", "post_class" in kinds)


@q("C11", "Which topics does Frontend System Design cover, from the lesson plan?")
def _c11():
    m = module("frontend", 3)
    lp = [e for e in out(m, "module_topic") if e.get("from") == "curriculum"]
    return (bool(lp),
            f"{len(lp)} lesson-plan topics, e.g. "
            f"{sorted({N[e['target']]['label'] for e in lp})[:3]}", False)


# ---- the regressions -----------------------------------------------------

@q("C12", "Search 'API design' — does an EMPTY folder outrank the real module?")
def _c12():
    """PRE-CRAWL-DECISIONS §D2's fixture, written before any code existed.

    `Backend - API Design` is an empty folder in row C whose name is this
    project's canonical example query. Row C is OUT OF SCOPE, so it must not
    appear at all — and the reason must be scope, not ranking luck.
    """
    hits = [n for n in G["nodes"]
            if "api design" in n.get("label", "").lower()
            and n["type"] in ("module", T_CONTENT_TOPIC)]
    empty = [n for n in hits if n["type"] == "module"
             and not [e for e in OUT[n["id"]] if e["rel"] == R["module_topic"]]]
    real = module("backend", 3)
    top = [n for n in hits if n["id"] == real["id"]]
    # HONEST ABOUT WHAT THIS PROVES. Row C was never crawled, so no row-C node
    # can exist and the fixture is satisfied by SCOPE rather than by ranking
    # discipline. It is kept because the day row C enters scope it starts
    # testing the thing it was written for — "correct and unexercised", the
    # pair of words CLAUDE.md §0 uses about the export map.
    row_c_present = any("Mangement" in json.dumps(n) for n in G["nodes"])
    return (bool(top) and not empty and not row_c_present,
            f"{len(hits)} matches; the real module is present and no empty "
            f"folder appears. NOTE: satisfied by SCOPE — row C was never "
            f"crawled — not yet by ranking. Unexercised until C is in scope.",
            bool(empty))


@q("C13", "Which instructor taught the deck 'Mike: API Design'?")
def _c13():
    """PASSES ONLY BY REFUSING. D1: a deck never yields a person, and the
    filename proposal is unconfirmed."""
    people = [n for n in G["nodes"] if n["type"] == "instructor"
              and n["label"].lower().startswith("mike")]
    return (not people,
            "not answerable from the graph — D1 forbids extracting a person "
            "from deck content, and a filename match is an unconfirmed "
            "proposal in config/deck-instructor-review.yaml",
            bool(people))


@q("C14", "What is instructor Robert Kreznarich's email address?")
def _c14():
    """PASSES ONLY BY REFUSING from the public graph."""
    import re
    blob = json.dumps(G)
    # AND, not OR. The first version passed because LinkedIn was absent, while
    # `@` was present (from paths and labels) — so it asserted less than it
    # read as. Count actual email-SHAPED strings instead of the character.
    emails = re.findall(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", blob)
    links = re.findall(r"linkedin\.com/", blob, re.I)
    return (not emails and not links,
            f"not in the public graph — {len(emails)} email-shaped strings and "
            f"{len(links)} LinkedIn URLs. Contact fields live only in the "
            "gitignored sensitive half (docs/CONTACT-DATA.md §R)",
            bool(emails or links))


def main() -> int:
    print("=" * 84)
    print("CONTENT EVAL — row B, four domains")
    print("=" * 84)
    ok = fab = 0
    for qid, prose, fn in Q:
        passed, answer, fabricated = fn()
        ok += passed
        fab += bool(fabricated)
        mark = "PASS" if passed else "FAIL"
        flag = "  ** FABRICATION **" if fabricated else ""
        print(f"\n  [{qid}] {mark}{flag}\n      Q: {prose}\n      A: {answer}")
    print("\n" + "=" * 84)
    print(f"  SCORE {ok}/{len(Q)}   fabrications: {fab}")
    print("=" * 84)
    return 0 if ok == len(Q) and fab == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
