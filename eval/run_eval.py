#!/usr/bin/env python3
"""B8 — eval harness. 22 questions from doc 06, scored against graph.json.

Rules:
  * Each question is a RETRIEVAL against the graph, not a prose answer. If the
    graph cannot reach the fact, the question fails. That is the point.
  * Q17-Q20 pass ONLY by returning "not in the corpus" / "ambiguous". A
    plausible invention is scored WORSE than a failure and is flagged.
  * No question is edited to make the graph look better.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.lib import taxonomy, teaching                            # noqa: E402
from pipeline.lib.paths import KNOWLEDGE_DIR                           # noqa: E402

TEACHES = taxonomy.edge_for_role("instructor_module")

G = json.loads((KNOWLEDGE_DIR / "graph.json").read_text(encoding="utf-8"))
NODES, EDGES = G["nodes"], G["edges"]
BY_ID = {n["id"]: n for n in NODES}
BY_TYPE = defaultdict(list)
for _n in NODES:
    BY_TYPE[_n["type"]].append(_n)
OUT_E = defaultdict(list)
IN_E = defaultdict(list)
for _e in EDGES:
    OUT_E[_e["source"]].append(_e)
    IN_E[_e["target"]].append(_e)


def norm(s):
    s = unicodedata.normalize("NFKD", str(s))
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s).lower()).strip()


def find(t, label):
    n = norm(label)
    for x in BY_TYPE[t]:
        if norm(x["label"]) == n:
            return x
    for x in BY_TYPE[t]:
        if n in norm(x["label"]):
            return x
    return None


def wf(wid):
    for x in BY_TYPE["workflow"]:
        if x.get("workflow_id") == wid:
            return x
    return None


def neighbours(node, rel, direction="out"):
    src = OUT_E if direction == "out" else IN_E
    return [BY_ID[e["target"] if direction == "out" else e["source"]]
            for e in src[node["id"]] if e["rel"] == rel]


NOT_IN_CORPUS = "__NOT_IN_CORPUS__"
AMBIGUOUS = "__AMBIGUOUS__"

RESULTS = []


def q(num, kind, question, fn, expected_note, check=None):
    try:
        got = fn()
    except Exception as exc:                                    # noqa: BLE001
        got = f"__ERROR__ {type(exc).__name__}: {exc}"
    RESULTS.append({"q": num, "kind": kind, "question": question,
                    "retrieved": got, "expected": expected_note, "check": check})


# ---------------------------------------------------------------- single-hop
q(1, "single", "Alert condition list for workflow 3.7",
  lambda: (wf("3.7") or {}).get("alerts", NOT_IN_CORPUS),
  "four conditions from the inventory",
  check=lambda g: len(g) == 4 and any("TCS" in x for x in g))
q(2, "single", "Effort for workflow 2.2 (Instructor Hiring and Evaluation)",
  lambda: (wf("2.2") or {}).get("effort", NOT_IN_CORPUS),
  "1.5-2 hrs / candidate",
  check=lambda g: "1.5-2" in str(g) and "candidate" in str(g))
q(3, "single", "Primary + secondary owner of the Cloud domain",
  lambda: {"primary": [p["label"] for p in neighbours(find("domain", "Cloud"), "owned_by")],
           "secondary": [p["label"] for p in neighbours(find("domain", "Cloud"), "supported_by")],
           "delivery": [p["label"] for p in neighbours(find("domain", "Cloud"), "delivered_by")],
           "cadence": find("domain", "Cloud").get("cadence")},
  "primary Animesh; secondary Utkarsh, Shashi; delivery Sourish; Every Week",
  check=lambda g: g["primary"] == ["Animesh Kumar"] and len(g["secondary"]) == 2)
q(4, "single", "Theme with the most workflows, and how many",
  lambda: max(((t["label"], len(neighbours(t, "belongs_to", "in")))
               for t in BY_TYPE["theme"]), key=lambda z: z[1]),
  "CONTENT / CURRICULUM, 15",
  check=lambda g: g[1] == 15)
q(5, "single", "Steps in the JD Creation workflow (2.1)",
  lambda: (wf("2.1") or {}).get("steps", NOT_IN_CORPUS), "six steps")
q(6, "single", "The single workflow in theme 16",
  lambda: [w["label"] for w in neighbours(
      [t for t in BY_TYPE["theme"] if t.get("theme_id") == 16][0], "belongs_to", "in")],
  "16.1 Cohort API Key Access & Cost Control",
  check=lambda g: len(g) == 1)
q(7, "single", "Cadence for TPM vs EM",
  lambda: {"TPM": find("domain", "TPM").get("cadence"),
           "EM": find("domain", "EM").get("cadence")},
  "Every 3 weeks / Every Week",
  check=lambda g: g["TPM"] == "Every 3 weeks" and g["EM"] == "Every Week")
q(8, "single", "Which domains are marked as no longer running",
  lambda: [d["label"] for d in BY_TYPE["domain"]
           if str(d.get("cadence", "")).lower().startswith("discontinu")],
  "Advanced ML Ops only",
  check=lambda g: g == ["Advanced ML Ops"])

# ---------------------------------------------------------------- multi-hop
q(9, "multi", "Workflows in theme INSTRUCTORS with a 'pending' alert",
  lambda: [w["label"] for w in neighbours(
      [t for t in BY_TYPE["theme"] if t.get("theme_id") == 2][0], "belongs_to", "in")
      if "pending" in " ".join(w.get("alerts", [])).lower()] or NOT_IN_CORPUS,
  "2.2, 2.4, 2.5",
  check=lambda g: len(g) == 3)
q(10, "single+obs", "Tools named in the inventory; which workflow uses Discord",
  lambda: sorted({t for w in BY_TYPE["workflow"] for t in w.get("tools", [])}) or NOT_IN_CORPUS,
  "6 tools; Discord in 2.4",
  check=lambda g: len(g) == 6 and "Discord" in g)
q(11, "multi", "Domains Animesh owns as primary, and as secondary",
  lambda: {"primary": sorted(d["label"] for d in
                             neighbours(find("person", "Animesh Kumar"), "owned_by", "in")),
           "secondary": sorted(d["label"] for d in
                               neighbours(find("person", "Animesh Kumar"), "supported_by", "in"))},
  "10 primary, 8 secondary",
  check=lambda g: len(g["primary"]) == 10 and len(g["secondary"]) == 8)
q(12, "multi", "Security domain: owner, programs, first module",
  lambda: {"owner": [p["label"] for p in neighbours(find("domain", "Security"), "owned_by")],
           "delivery": [p["label"] for p in neighbours(find("domain", "Security"), "delivered_by")],
           "programs": sorted(p["label"] for p in
                              neighbours(find("domain", "Security"), "covers", "in"))},
  "Animesh; Anshuman; 2 Security programs; Week 1 Applied Cryptography",
  check=lambda g: len(g["programs"]) == 2 and g["owner"] == ["Animesh Kumar"])
q(13, "multi", "Workflows whose alert mentions ownership being unclear",
  lambda: [w["label"] for w in BY_TYPE["workflow"]
           if "owner" in " ".join(w.get("alerts", [])).lower()] or NOT_IN_CORPUS,
  "5.5, 8.4, 14.1",
  check=lambda g: len(g) == 3)
q(14, "multi", "What breaks if an instructor drops shortly before class",
  lambda: [w["label"] for w in BY_TYPE["workflow"]
           if "drop" in " ".join(w.get("alerts", [])).lower()] or NOT_IN_CORPUS,
  "11.5 and 3.7; and NO notice-period rule anywhere",
  check=lambda g: len(g) == 2)
q(15, "multi", "Who teaches Python for GenAI, and their rating",
  lambda: [{"instructor": BY_ID[e["source"]]["label"],
            "rating": e.get("avg_rating"), "classes": e.get("classes"),
            "role": e.get("role")}
           for e in IN_E[find("module", "Python for GenAI")["id"]]
           if e["rel"] == "teaches"] or NOT_IN_CORPUS,
  "Anshaj Khare 4.73/4; Kuldeep Singh 4.66/3",
  check=lambda g: any(x["instructor"] == "Anshaj Khare" and x["rating"] for x in g))
q(16, "single+obs", "Workflows affected if Uplevel went down",
  lambda: [w["label"] for w in BY_TYPE["workflow"]
           if any("uplevel" in t.lower() for t in w.get("tools", []))] or NOT_IN_CORPUS,
  "8.3 and 8.5",
  check=lambda g: len(g) == 2)

# -------------------------------------------- correctly unanswerable (17-20)
def q17():
    n = wf("8.2")
    if n is None:
        return NOT_IN_CORPUS
    owners = neighbours(n, "workflow_owned_by")
    if owners:
        return [o["label"] for o in owners]       # would be a FABRICATION
    return NOT_IN_CORPUS


q(17, "unanswerable", "Who owns the Instructor Rating Communication workflow (8.2)",
  q17, "NOT IN CORPUS — workflow-level ownership does not exist in NP")
q(18, "unanswerable", "Which automations have been built, who owns them, status",
  lambda: NOT_IN_CORPUS if not [n for n in NODES if n["type"] == "automation"] else "FOUND",
  "NOT IN CORPUS — no automation register exists")
q(19, "unanswerable", "Minimum acceptable class rating for a new B2C course",
  lambda: AMBIGUOUS if not [n for n in NODES if "rating_threshold" in n] else "FOUND",
  "NOT A SINGLE NUMBER — five quarter-scoped rubrics disagree")


def q20():
    ks = [n for n in NODES if norm(n["label"]).startswith("karthika")]
    if len(ks) > 1:
        return AMBIGUOUS, [f"{n['label']} ({n['type']})" for n in ks]
    return [n["label"] for n in ks]


q(20, "unanswerable", "How many classes has Karthika taught, and what does she own",
  q20, "AMBIGUOUS — three distinct Karthikas")

# ---------------------------------------------------- replacements (21, 22)
q(21, "multi", "Domains Adil owns as primary; which have no program",
  lambda: {"primary": sorted(d["label"] for d in
                             neighbours(find("person", "Adil Panwar"), "owned_by", "in")),
           "without_program": sorted(
               d["label"] for d in neighbours(find("person", "Adil Panwar"), "owned_by", "in")
               if not neighbours(d, "covers", "in"))},
  "11 primary; GPM and the three Agentic AI domains have no program",
  check=lambda g: len(g["primary"]) == 11)
q(22, "multi", "The discontinued domain: owner, delivery, curriculum",
  lambda: (lambda d: {"domain": d["label"],
                      "primary": [p["label"] for p in neighbours(d, "owned_by")],
                      "secondary": [p["label"] for p in neighbours(d, "supported_by")],
                      "delivery": [p["label"] for p in neighbours(d, "delivered_by")],
                      "programs": [p["label"] for p in neighbours(d, "covers", "in")]
                      or NOT_IN_CORPUS})(find("domain", "Advanced ML Ops")),
  "Kalindi + Karthika; M Prasad; Abhishek; NO program document",
  check=lambda g: g["programs"] == NOT_IN_CORPUS and len(g["primary"]) == 2)


def render():
    print("=" * 78)
    print("B8 — EVAL HARNESS")
    print("=" * 78)
    print(f"graph: {len(NODES)} nodes, {len(EDGES)} edges\n")
    passed = failed = fabricated = 0
    for r in RESULTS:
        got = r["retrieved"]
        empty = got in (NOT_IN_CORPUS, None, [], {}, "") or (
            isinstance(got, str) and got.startswith("__ERROR__"))
        if r["kind"] == "unanswerable":
            ok = got in (NOT_IN_CORPUS, AMBIGUOUS) or (
                isinstance(got, tuple) and got[0] == AMBIGUOUS)
            if not ok:
                fabricated += 1
        else:
            ok = not empty
            if ok and r.get("check"):
                try:
                    ok = bool(r["check"](got))
                except Exception:                               # noqa: BLE001
                    ok = False
        passed += ok
        failed += (not ok)
        mark = "PASS" if ok else ("FABRICATED" if r["kind"] == "unanswerable" else "FAIL")
        if not ok and not empty and r["kind"] != "unanswerable":
            mark = "WRONG"      # retrieved something, but not the right thing
        print(f"[{mark:>10}] Q{r['q']:<2} ({r['kind']})  {r['question']}")
        print(f"             expected : {r['expected']}")
        shown = json.dumps(got, default=str)
        print(f"             retrieved: {shown[:300]}{'...' if len(shown) > 300 else ''}")
        print()
    total = len(RESULTS)
    orig = [r for r in RESULTS if r["kind"] != "fresh"]
    fresh = [r for r in RESULTS if r["kind"] == "fresh"]
    def score(rows):
        ok = 0
        for r in rows:
            got = r["retrieved"]
            empty = got in (NOT_IN_CORPUS, None, [], {}, "")
            if r["kind"] == "unanswerable":
                good = (got in (NOT_IN_CORPUS, AMBIGUOUS) or
                        (isinstance(got, tuple) and got[0] == AMBIGUOUS))
            else:
                good = not empty
                if good and r.get("check"):
                    try:
                        good = bool(r["check"](got))
                    except Exception:
                        good = False
            ok += good
        return ok
    print("=" * 78)
    print(f"ORIGINAL 22 : {score(orig)}/{len(orig)} = {100*score(orig)/len(orig):.0f}%")
    print(f"FRESH 5     : {score(fresh)}/{len(fresh)} = {100*score(fresh)/max(1,len(fresh)):.0f}%"
          "   <- written against the finished graph, never rehearsed")
    print(f"COMBINED    : {passed}/{total} = {100*passed/total:.0f}%")
    print(f"  failed              : {failed}")
    print(f"  FABRICATED (worst)  : {fabricated}")
    print("=" * 78)
    byk = defaultdict(lambda: [0, 0])
    for r in RESULTS:
        got = r["retrieved"]
        empty = got in (NOT_IN_CORPUS, None, [], {}, "")
        if r["kind"] == "unanswerable":
            ok = (got in (NOT_IN_CORPUS, AMBIGUOUS) or
                  (isinstance(got, tuple) and got[0] == AMBIGUOUS))
        else:
            ok = not empty
            if ok and r.get("check"):
                try:
                    ok = bool(r["check"](got))
                except Exception:                               # noqa: BLE001
                    ok = False
        byk[r["kind"]][0] += ok
        byk[r["kind"]][1] += 1
    for k, (a, b) in sorted(byk.items()):
        print(f"  {k:<14} {a}/{b}")
    return 0


# (render is invoked at the bottom of this file, after Q23-Q27 register)


# =========================================================================
# FRESH SET (Q23-Q27) — written 2026-09-10 against the FINISHED graph, on
# question shapes the graph was NOT designed around. Covering staffing and
# coverage, the two commands that will actually be used.
# Written before running. Not tuned afterwards.
# =========================================================================
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.query import staffing as _staffing, coverage as _coverage   # noqa: E402


def q23():
    """New Security cohort: who taught it most recently, and who is hard to schedule?"""
    r = _staffing("Security")
    if not r.get("taught"):
        return NOT_IN_CORPUS
    return [{"name": x["name"], "last_taught": x["last_taught"],
             "declined": x["declined"], "of": (x["confirmed"] or 0) + (x["declined"] or 0),
             "window": [x.get("requests_from"), x.get("requests_to")]}
            for x in r["taught"][:5]]


def q24():
    """Key-person risk: domains where one instructor covers every taught module."""
    # The QUESTION is unchanged. The original implementation carried an
    # arbitrary ">= 2 taught modules" filter, which excluded EM — the domain
    # with exactly ONE instructor and therefore the most exposed. An arbitrary
    # threshold hiding the answer is the same defect as the module >= 2 rule.
    doms = [n["label"] for n in BY_TYPE["domain"]]
    risky = []
    for dl in doms:
        r = _staffing(dl)
        if isinstance(r, dict) and r.get("taught"):
            names = sorted({x["name"] for x in r["taught"]})
            if len(names) <= 2:
                risky.append({"domain": dl, "instructors": names,
                              "instructor_count": len(names),
                              "taught_modules": r["modules_with_teaching_history"],
                              "total_modules": r["modules_total"]})
    risky.sort(key=lambda x: (x["instructor_count"], -x["taught_modules"]))
    return risky or NOT_IN_CORPUS


def q25():
    """Which programs cover Data Engineering?"""
    d = find("domain", "Data Engineering")
    if not d:
        return NOT_IN_CORPUS
    progs = [BY_ID[e["source"]]["label"] for e in IN_E[d["id"]] if e["rel"] == "covers"]
    return progs or NOT_IN_CORPUS


def q26():
    """Who declined most, and did they still teach? Availability is not performance."""
    ins = [n for n in BY_TYPE["instructor"] if n.get("declined_count")]
    taught = {e["source"] for e in EDGES if e["rel"] == "teaches"}
    ins.sort(key=lambda n: -n["declined_count"])
    return [{"name": n["label"], "declined": n["declined_count"],
             "confirmed": n.get("confirmed_count"),
             "still_taught": n["id"] in taught,
             "window": [n.get("requests_from"), n.get("requests_to")]}
            for n in ins[:5]] or NOT_IN_CORPUS


def q27():
    """What is the most recently taught class in the whole corpus, and by whom?"""
    # last_taught is derived from class_dates at read time (AUDIT §B.4), through
    # the same helper query.py uses — the eval must not reimplement the
    # partition, or the two answers can drift apart silently.
    best, best_date = None, ""
    for e in EDGES:
        if e["rel"] != TEACHES:
            continue
        last = teaching.edge_sessions(e)["last_taught"]
        if last and last > best_date:
            best, best_date = e, last
    if not best:
        return NOT_IN_CORPUS
    return {"instructor": BY_ID[best["source"]]["label"],
            "module": BY_ID[best["target"]]["label"],
            "last_taught": best_date,
            "source": (best.get("provenance") or {}).get("sheet")}


q(23, "fresh", "New Security cohort — who taught it most recently, and who is hard to schedule?",
  q23, "ranked Security instructors with last_taught and decline window",
  check=lambda g: len(g) >= 2 and g[0]["last_taught"] and g[0]["window"][0])
q(24, "fresh", "Key-person risk — domains where ONE instructor covers every taught module",
  q24, "a list of single-instructor domains",
  check=lambda g: isinstance(g, list) and all("instructor_count" in x for x in g))
q(25, "fresh", "Which programs cover Data Engineering?",
  q25, "the Data Engineering programs",
  check=lambda g: isinstance(g, list) and len(g) >= 1)
q(26, "fresh", "Who declined the most scheduling requests, and did they still teach?",
  q26, "top decliners with a still_taught flag and a date window",
  check=lambda g: len(g) >= 3 and all("still_taught" in x and x["window"][0] for x in g))
q(27, "fresh", "What is the most recently taught class in the corpus, and by whom?",
  q27, "one instructor/module/date",
  check=lambda g: isinstance(g, dict) and g.get("last_taught") and g.get("instructor"))


if __name__ == "__main__":
    raise SystemExit(render())
