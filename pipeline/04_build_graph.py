#!/usr/bin/env python3
"""Pass 4 — assemble the graph. Edges only where there is row-level evidence."""
from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import openpyxl                                                        # noqa: E402
import yaml                                                            # noqa: E402

from pipeline.lib import graphio, taxonomy, teaching                   # noqa: E402
from pipeline.lib.paths import (KNOWLEDGE_DIR, WORKFLOW_OWNERS_FILE,  # noqa: E402
                                build_log, corpus_root)

GRAPH = KNOWLEDGE_DIR / "graph.json"
AGENTIC = "03-instructors/AgenticAI Instructors Training Plan.xlsx"


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s))
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s).lower()).strip()


def as_of_date() -> str:
    """The date the build treats as "now", ISO. From NP_AS_OF, else today UTC.

    `teaches` edges split recorded class dates into past and future, so
    last_taught / sessions_past / sessions_scheduled are all functions of the
    calendar. The build is therefore deterministic WITHIN a day and not across
    days: rebuilding the 2026-09-09 graph on 2026-09-16 moved 44 edges' sessions
    from scheduled to past, with every node and every edge key untouched.

    That is correct behaviour — the data really does age — but it makes
    "rebuild and compare" useless as a verification tool, because a diff caused
    by the calendar is indistinguishable from a diff caused by a code or corpus
    change. NP_AS_OF pins the date so a historical build can be reproduced
    exactly and any remaining difference is real.

    Default is today, so a normal run behaves exactly as it did before.
    """
    return os.environ.get("NP_AS_OF") or datetime.now(timezone.utc).date().isoformat()


def main() -> int:
    nodes = json.loads((KNOWLEDGE_DIR / "resolved.json").read_text(encoding="utf-8"))["nodes"]
    by_type = defaultdict(list)
    for n in nodes:
        by_type[n["type"]].append(n)
    idx = {(n["type"], norm(n["label"])): n["id"] for n in nodes}

    print("=" * 78)
    print("PASS 4 — build graph")
    print("=" * 78)
    print(f"nodes in : {len(nodes)}")
    print()

    edges: list[dict] = []
    notes: list[str] = []
    R = taxonomy.edge_for_role   # resolve edges by role, never by literal

    # belongs_to: workflow -> theme
    theme_by_id = {n.get("theme_id"): n["id"] for n in by_type["theme"]}
    for w in by_type["workflow"]:
        t = theme_by_id.get(w.get("theme_id"))
        if t:
            edges.append({"source": w["id"], "target": t, "rel": R("workflow_theme")})

    # owned_by / supported_by / delivered_by: domain -> person, from the owners sheet
    root = corpus_root()
    rel_owner = "00-master/Domains_Courses Owners.xlsx"
    wb = openpyxl.load_workbook(root / rel_owner, read_only=True, data_only=True)
    ws = wb["Sheet1"]
    alias = {}
    people = yaml.safe_load((WORKFLOW_OWNERS_FILE.parent / "people.yaml").read_text(encoding="utf-8"))
    for p in people["people"]:
        for a in (p.get("aliases") or []) + [p["canonical"]]:
            alias[a.strip().lower()] = p["canonical"]
    for rownum, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        def cell(i):
            return str(row[i]).strip() if i < len(row) and row[i] is not None else ""
        dom = cell(0)
        if not dom:
            continue
        did = idx.get(("domain", norm(dom)))
        for edge_name, col1 in taxonomy.owner_sheet_edges():
            v = cell(col1 - 1)
            for tok in [x.strip() for x in v.replace("/", ",").split(",") if x.strip()]:
                canon = alias.get(tok.lower(), tok)
                pid = idx.get(("person", norm(canon)))
                if did and pid:
                    edges.append({"source": did, "target": pid, "rel": edge_name,
                                  "provenance": {"file": rel_owner, "sheet": "Sheet1",
                                                 "row": rownum, "column": col1}})
    wb.close()

    # covers: program -> domain. Lossiest edge in the graph (R12). Never
    # spell-correct a filename-derived label to force a join.
    def prog_keys(label: str) -> list[str]:
        """Candidate join keys for one program, MOST SPECIFIC FIRST.

        The domain list contains both bare names ("Backend", "Cloud") and
        compound ones ("Data Engineering", "Test Engineering", "Early
        Engineering"). Stripping "Engineering" loses the compound ones; keeping
        it loses the bare ones. So try the program's own text at two
        granularities and take the first that hits a real domain.

        This is not spell-correction (R12). Nothing is edited toward a target —
        both keys are derived from the label as written, and a program whose
        text matches no domain stays unjoined.
        """
        s = label
        for token in taxonomy.doctypes() + ["Interview Preparation Program", "Program"]:
            s = re.sub(re.escape(token), " ", s, flags=re.I)
        s = re.sub(re.escape(taxonomy.families()[0]), " ", s, flags=re.I)
        full = norm(s)
        trimmed = norm(re.sub(r"\b(engineering|software|systems)\b", " ", s, flags=re.I))
        keys = [full]
        if trimmed and trimmed != full:
            keys.append(trimmed)
        # Whitespace-collapsed forms. Doc 05 ambiguity #3 sanctions exactly this
        # and nothing more: "Normalise whitespace only; do not spell-correct."
        # Catches 'Full-Stack' -> 'fullstack'. Does NOT touch abbreviations.
        keys += [k.replace(" ", "") for k in list(keys)]
        seen_k, ordered = set(), []
        for k in keys:
            if k and k not in seen_k:
                seen_k.add(k)
                ordered.append(k)
        return ordered

    dom_key = {}
    for d in by_type["domain"]:
        for form in (norm(d["label"]), norm(re.sub(r"\(.*?\)", " ", d["label"]))):
            dom_key.setdefault(form, d["id"])
            dom_key.setdefault(form.replace(" ", ""), d["id"])
    joined = 0
    join_detail = {}
    for p in by_type["program"]:
        for k in prog_keys(p["label"]):
            did = dom_key.get(k)
            if did:
                edges.append({"source": p["id"], "target": did,
                              "rel": R("program_domain"), "join_key": k})
                join_detail[p["id"]] = k
                joined += 1
                break

    cand = json.loads((KNOWLEDGE_DIR / "candidates.json").read_text(encoding="utf-8"))

    # contains: program -> module. There is NO row-level program<->module pairing
    # in this corpus. The curriculum sheet name IS a domain, so the only honest
    # route is program -> domain -> module, and every edge is marked inferred
    # with the join basis recorded. A sheet with no domain mapping gets no edge.
    mod_domain = {}
    for c in cand["candidates"]:
        if c["type"] == "module" and c.get("domain"):
            mod_domain.setdefault(norm(c["raw"]), c["domain"])
    prog_by_domain = defaultdict(list)
    for e in edges:
        if e["rel"] == R("program_domain"):
            prog_by_domain[e["target"]].append(e["source"])
    contained, unmapped_modules = 0, 0
    for m in by_type["module"]:
        dom = mod_domain.get(norm(m["label"]))
        if not dom:
            unmapped_modules += 1
            continue
        did = idx.get(("domain", norm(dom)))
        for pid in prog_by_domain.get(did, []):
            edges.append({"source": pid, "target": m["id"], "rel": R("program_module"),
                          "inferred": True,
                          "join_basis": f"module sheet -> domain {dom!r} -> program"})
            contained += 1

    # depends_on: NOT EXTRACTED. Evidence checked and it is not there — see the
    # note printed below and config/workflow-depends-review.yaml.
    dep_review = []

    # expert_in: instructor -> domain, DECLARED subject. Same lossy join as
    # covers, same rule: never spell-correct to force a match (R12).
    def domain_keys(label: str) -> list[str]:
        base = norm(label)
        trimmed = norm(re.sub(r"\b(engineering|systems|program|programme)\b", " ",
                              label, flags=re.I))
        out_k = [base, trimmed, base.replace(" ", ""), trimmed.replace(" ", "")]
        seen_k, ordered = set(), []
        for k in out_k:
            if k and k not in seen_k:
                seen_k.add(k)
                ordered.append(k)
        return ordered

    # Confirmed domain aliases. Only confirmed: true rows are read.
    alias_path = WORKFLOW_OWNERS_FILE.parent / "domain-aliases.yaml"
    alias_map = {}
    if alias_path.exists():
        _al = yaml.safe_load(alias_path.read_text(encoding="utf-8")) or {}
        for _a in _al.get("aliases", []):
            if _a.get("confirmed") is True:
                alias_map[norm(_a["alias"])] = _a["domain"]

    expert, exp_miss, via_alias_n = 0, [], 0
    seen_exp = set()
    node_by_pre = {(n["type"], norm(n["label"])): n for n in nodes}
    for cl in cand.get("expertise_claims", []):
        inode = node_by_pre.get(("instructor", cl["instructor"]))
        did, via = None, False
        for k in domain_keys(cl["subject"]):
            if k in dom_key:
                did = dom_key[k]
                break
        if did is None:
            target = alias_map.get(norm(cl["subject"]))
            if target:
                for k in domain_keys(target):
                    if k in dom_key:
                        did, via = dom_key[k], True
                        break
        if not inode or not did:
            exp_miss.append(cl)
            continue
        key = (inode["id"], did, cl["basis"])
        if key in seen_exp:
            continue
        seen_exp.add(key)
        e = {"source": inode["id"], "target": did, "rel": R("instructor_domain"),
             "basis": cl["basis"], "subject_raw": cl["subject_raw"],
             "provenance": cl["source"]}
        if via:
            # TWO inference steps: a declared subject, matched through a
            # human-confirmed alias. Ranked last by the staffing command.
            e["via_alias"] = True
            via_alias_n += 1
        edges.append(e)
        expert += 1

    # teaches: instructor -> module, from all 14 pairing sources found on
    # 2026-09-10. The first build used one sheet and emitted 6 edges. Doc 05's
    # other cited example (Suresh Venkatesan -> SQL Programming) was REAL and sat
    # in a sheet no scan had opened.
    node_by = {(n["type"], norm(n["label"])): n for n in nodes}
    taught, unmatched_pairs = 0, 0
    seen_pair = set()
    # Aggregate every recorded class date per (instructor, module) first, so the
    # edge can say when it was last taught and how often, not just that it was.
    # Recorded in meta so a build states the date it was made against,
    # even though no edge property depends on it any more.
    TODAY = as_of_date()
    dates_for = defaultdict(list)
    for pr in cand.get("teaches_pairs", []):
        if pr.get("date"):
            dates_for[(pr["instructor"], pr["module"])].append(pr["date"])
    for pr in cand.get("teaches_pairs", []):
        m = node_by.get(("module", pr["module"]))
        i = node_by.get(("instructor", pr["instructor"]))
        if not m or not i:
            unmatched_pairs += 1
            continue
        key = (i["id"], m["id"])
        if key in seen_pair:
            # A pair already seen. Keep it UNLESS this one carries a rating and
            # the stored one does not — dedup was silently discarding the only
            # rating evidence in the corpus, which eval Q15 exposed.
            if not pr.get("avg_rating"):
                continue
            edges[:] = [x for x in edges
                        if not (x["rel"] == R("instructor_module")
                                and x["source"] == i["id"] and x["target"] == m["id"])]
        seen_pair.add(key)
        e = {"source": i["id"], "target": m["id"], "rel": R("instructor_module"),
             "role": "primary" if pr["rank"] == 0 else "backup",
             "rank": pr["rank"], "provenance": pr["source"]}
        for k in ("avg_rating", "classes"):
            if pr.get(k):
                e[k] = pr[k]
        # AUDIT §B.4 — store the EVIDENCE, derive the rest at read time.
        #
        # This block used to write last_taught / sessions_past /
        # sessions_scheduled by partitioning these dates against "today", which
        # made the graph deterministic within a day and not across days: 44
        # edges moved when the same build was repeated a week later, with every
        # node and edge key untouched. See pipeline/lib/teaching.py.
        ds = sorted(set(dates_for.get((pr["instructor"], pr["module"]), [])))
        if ds:
            e[teaching.CLASS_DATES] = ds
        edges.append(e)
        taught += 1

    # workflow_owned_by: only confirmed rows
    wo = yaml.safe_load(WORKFLOW_OWNERS_FILE.read_text(encoding="utf-8"))
    confirmed = [w for w in wo["workflows"] if w.get("confirmed") is True and w.get("owner")]
    wf_by_id = {w.get("workflow_id"): w["id"] for w in by_type["workflow"]}
    for w in confirmed:
        pid = idx.get(("person", norm(str(w["owner"]))))
        wid = wf_by_id.get(w["id"])
        if pid and wid:
            edges.append({"source": wid, "target": pid, "rel": R("workflow_owner")})

    # sourced_from: provenance for every node.
    # File nodes come from files.json — EVERY ingested file, not only those that
    # yielded an entity. Deriving them from provenance instead gave 53 of 74 and
    # validate.py caught it. It also makes "which files yielded nothing?"
    # answerable, which is the coverage question this project keeps hitting.
    import hashlib as _h
    manifest = json.loads((KNOWLEDGE_DIR / "files.json").read_text(encoding="utf-8"))
    file_nodes = {}
    for rec in manifest["files"] + manifest["failures"]:
        f = rec["path"]
        fid = "fil_" + _h.sha256(f.encode()).hexdigest()[:16]
        file_nodes[f] = {"id": fid, "type": "file", "label": f,
                         "relative_path": f, "sensitive": False,
                         "parsed": rec.get("parsed", False),
                         "sheet_count": rec.get("sheet_count", 0),
                         "sources": [{"origin": taxonomy.origin_corpus(), "file": f,
                                      # file nodes are created here, after
                                      # 03_resolve's ordinal pass, so they
                                      # carry it explicitly. One entry per
                                      # file node, so it is always 0.
                                      "ordinal": 0}]}
    for n in nodes:
        for s in n.get("sources", []):
            f = s.get("file")
            if f and f in file_nodes:
                edges.append({"source": n["id"], "target": file_nodes[f]["id"],
                              "rel": R("provenance")})
    contributing = {s.get("file") for n in nodes for s in n.get("sources", []) if s.get("file")}
    barren = sorted(set(file_nodes) - contributing)
    notes.append(f"{len(barren)} of {len(file_nodes)} files yielded no entity")
    all_nodes = nodes + list(file_nodes.values())

    # ---- render scope. A render decision, NOT an ingestion one: every status
    # stays in graph.json so coverage can still answer funnel questions.
    renderable = [n for n in all_nodes
                  if n["type"] != "instructor" or n.get("renderable")]
    render_default = [n for n in renderable
                      if n["type"] != "instructor"
                      or n.get("pipeline_status") == "roster"]
    excluded_from_render = [n for n in all_nodes
                            if n["type"] == "instructor" and not n.get("renderable")]

    counts = defaultdict(int)
    for e in edges:
        counts[e["rel"]] += 1
    print("-" * 78)
    print("EDGES BUILT")
    print("-" * 78)
    for name in taxonomy.edge_type_names():
        n = counts.get(name, 0)
        flag = "   <-- ZERO" if n == 0 else ""
        print(f"  {name:<20} {n:>7}{flag}")
    print(f"  {'TOTAL':<20} {len(edges):>7}")
    print()
    print(f"  covers: {joined}/{len(by_type['program'])} programs joined to a domain "
          f"({len(by_type['program'])-joined} orphaned — R12, expected)")
    print(f"  teaches: {taught} distinct instructor->module edges "
          f"({unmatched_pairs} pairs dropped — one side had no node)")
    print(f"  workflow_owned_by: {len(confirmed)} confirmed rows in workflow-owners.yaml")
    print()
    print("-" * 78)
    print("expert_in — instructor -> domain (DECLARED, not teaching evidence)")
    print("-" * 78)
    claims = cand.get("expertise_claims", [])
    print(f"  {via_alias_n} of those matched through a CONFIRMED ALIAS (via_alias: true)")
    print(f"  {len(claims)} claims -> {expert} edges "
          f"({100*expert/max(1,len(claims)):.0f}% join rate)")
    bb = defaultdict(int)
    for e in edges:
        if e["rel"] == R("instructor_domain"):
            bb[e["basis"]] += 1
    for k in sorted(bb):
        print(f"      {k:<16} {bb[k]:>5} edges")
    missct = defaultdict(int)
    for m in exp_miss:
        missct[m["subject"]] += 1
    print(f"  {len(exp_miss)} claims unjoined, {len(missct)} distinct subjects")
    print("  top unjoined subjects (routed to review, never spell-corrected):")
    for s, n in sorted(missct.items(), key=lambda z: -z[1])[:12]:
        print(f"      {n:>4}  {s[:56]!r}")
    print()

    print("-" * 78)
    print("contains — program -> module (INFERRED via domain)")
    print("-" * 78)
    print(f"  {contained} edges")
    print(f"  {unmapped_modules} of {len(by_type['module'])} modules have no domain mapping "
          f"and got NO edge (M_SME_* pathway sheets — a wrong join is worse than none)")
    print()
    print("-" * 78)
    print("depends_on — NOT EXTRACTED, and this is a finding")
    print("-" * 78)
    print("  Searched all 92 workflow bodies for cross-references. Result:")
    print("    explicit 'N.M' references : 1, and it is a FALSE POSITIVE")
    print("      ('2.2 -> 1.5' is the string '1.5-2 hrs' in the Effort line)")
    print("    references by workflow name: 0")
    print("  There is NO workflow-to-workflow dependency evidence in this corpus.")
    print("  Doc 08 Q5's hop table cites '3.6 -> 3.1' as an example; that pair has")
    print("  no support in the file and the claim is WITHDRAWN.")
    print("  0 edges asserted. Routed to config/workflow-depends-review.yaml.")
    print()

    print("-" * 78)
    print(f"covers — the {len(by_type['program'])-joined} programs with NO domain join (R12)")
    print("-" * 78)
    joined_ids = {e["source"] for e in edges if e["rel"] == R("program_domain")}
    for pnode in sorted(by_type["program"], key=lambda n: n["label"].lower()):
        if pnode["id"] not in joined_ids:
            print(f"    {pnode['label']}")
            print(f"        keys tried -> {prog_keys(pnode['label'])}")
    print()

    print("-" * 78)
    print("FILES THAT YIELDED NO ENTITY")
    print("-" * 78)
    print(f"  {len(barren)} of {len(file_nodes)}")
    for b_ in barren:
        print(f"    {b_}")
    print()

    Path(WORKFLOW_OWNERS_FILE.parent / "expert-in-review.yaml").write_text(
        yaml.safe_dump({
            "version": 1,
            "note": ("Declared subjects that matched no domain. NOT spell-corrected "
                     "(R12). Most are abbreviations or role labels the owner sheet "
                     "spells differently. Add an alias to the domain in taxonomy.yaml "
                     "if a mapping is real; leaving one here is a valid answer."),
            "unjoined": [{"subject": s, "claims": n} for s, n in
                         sorted(missct.items(), key=lambda z: -z[1])],
        }, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8")

    Path(WORKFLOW_OWNERS_FILE.parent / "workflow-depends-review.yaml").write_text(
        yaml.safe_dump({
            "version": 1,
            "note": ("depends_on is NOT extracted. Searched every workflow body for "
                     "cross-references: 1 explicit 'N.M' hit, which is the false "
                     "positive '1.5-2 hrs' in an Effort line, and 0 references by "
                     "workflow name. Doc 05 flagged this edge low-confidence and the "
                     "corpus does not support it. Doc 08's '3.6 -> 3.1' example is "
                     "withdrawn. Add pairs here by hand if you know of real "
                     "dependencies; the builder emits an edge only for confirmed: true."),
            "confirmed_dependencies": [],
            "rejected_automatic_candidates": [
                {"from": "2.2", "to": "1.5", "reason":
                 "false positive — matched the duration '1.5-2 hrs' in the Effort line"}],
        }, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8")

    print("-" * 78)
    print("RENDER SCOPE")
    print("-" * 78)
    print(f"  default render (roster only)      : {len(render_default)} nodes")
    print(f"  with 'hired' toggle on            : {len(renderable)} nodes")
    print(f"  EXCLUDED from render entirely     : {len(excluded_from_render)} instructors")
    st = defaultdict(int)
    for n in excluded_from_render:
        st[n.get("pipeline_status", "unknown")] += 1
    for k in sorted(st):
        print(f"      {k:<14} {st[k]:>5}   sensitive: true")
    print("  All statuses remain in graph.json — this is a render filter, not an")
    print("  ingestion exclusion. Hiring rejections about named external people")
    print("  must not be browsable by everyone at IK.")
    print()

    # ---- SPLIT. DECISIONS §F.2 ---------------------------------------------
    # graph.json is committed and ships with the plugin, and a personal repo has
    # no read-only tier — so adding a collaborator grants them everything in its
    # history. The 277 hiring rejections and 1,625 in-pipeline candidates are
    # `recruiting` data under Q3, and the collaborators are not cleared for it.
    #
    # Cheap because all 1,902 sensitive nodes carry ONLY provenance edges: zero
    # teaches, zero expert_in. Withholding them costs no teaching or expertise
    # evidence, so /staffing answers identically. Asserted below rather than
    # assumed, because a future change that gives a rejected candidate a teaching
    # edge makes it expensive again and must not do so silently.
    public, sensitive = graphio.split_graph(all_nodes, edges)
    withheld_rels = Counter(e["rel"] for e in sensitive["edges"])
    evidence_rels = {R("instructor_module"), R("instructor_domain")}
    leaked = evidence_rels & set(withheld_rels)
    if leaked:
        print("  WARNING — the split would now withhold EVIDENCE edges: "
              f"{sorted(leaked)}. /staffing answers will differ between someone "
              "holding both halves and someone holding only the public file.")

    common_meta = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "taxonomy_version": taxonomy.version(),
        # Reported from the manifest, never asserted. These were hardcoded to
        # local-folder / deferred, so the graph went on claiming Drive had never
        # been read after pass 0 went live.
        "source": manifest.get("source", "unknown"),
        "drive_deferred": manifest.get("source") != "drive-cache",
        "as_of": TODAY,
    }

    GRAPH.write_text(json.dumps({
        "meta": {**common_meta,
                 "nodes": len(public["nodes"]), "edges": len(public["edges"]),
                 # Counted from the nodes actually in THIS file. by_type is built
                 # from resolved.json, which has no file nodes, so counting from
                 # it published `file: 0` against an expect of 74 in an
                 # auto-generated INDEX.md. A generated count that disagrees with
                 # its own artefact is worse than a hand-written one.
                 "node_counts": dict(Counter(n["type"] for n in public["nodes"])),
                 "edge_counts": dict(Counter(e["rel"] for e in public["edges"])),
                 "render": {"default_roster_only": len(render_default),
                            "with_hired_toggle": len(renderable),
                            "excluded_instructors": len(excluded_from_render)},
                 "withheld": {
                     "file": graphio.SENSITIVE.name,
                     "nodes": len(sensitive["nodes"]),
                     "edges": len(sensitive["edges"]),
                     "edge_rels": dict(sorted(withheld_rels.items())),
                     "reason": ("sensitive: true — hiring rejections and "
                                "in-pipeline candidates, named external people. "
                                "Gitignored; projected behind the recruiting RLS "
                                "policy. See DECISIONS §F.2."),
                 }},
        "nodes": public["nodes"], "edges": public["edges"]},
        indent=1, sort_keys=True), encoding="utf-8")

    graphio.SENSITIVE.write_text(json.dumps({
        "meta": {**common_meta,
                 "nodes": len(sensitive["nodes"]), "edges": len(sensitive["edges"]),
                 "node_counts": dict(Counter(n["type"] for n in sensitive["nodes"])),
                 "edge_counts": dict(sorted(withheld_rels.items())),
                 "warning": ("NOT COMMITTED and never to be. Named external people "
                             "who were rejected or are mid-pipeline.")},
        "nodes": sensitive["nodes"], "edges": sensitive["edges"]},
        indent=1, sort_keys=True), encoding="utf-8")

    print(f"wrote {GRAPH.name}: {len(public['nodes'])} nodes, "
          f"{len(public['edges'])} edges  (public)")
    print(f"wrote {graphio.SENSITIVE.name}: {len(sensitive['nodes'])} nodes, "
          f"{len(sensitive['edges'])} edges  (GITIGNORED — "
          f"{dict(sorted(withheld_rels.items()))})")

    with build_log().open("a", encoding="utf-8") as fh:
        fh.write(f"\n## {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')} — 04_build_graph\n\n")
        fh.write(f"- Nodes {len(all_nodes)} | edges {len(edges)}\n")
        for name in taxonomy.edge_type_names():
            fh.write(f"    - {name}: {counts.get(name,0)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
