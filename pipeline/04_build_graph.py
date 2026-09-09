#!/usr/bin/env python3
"""Pass 4 — assemble the graph. Edges only where there is row-level evidence."""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import openpyxl                                                        # noqa: E402
import yaml                                                            # noqa: E402

from pipeline.lib import taxonomy                                      # noqa: E402
from pipeline.lib.paths import (BUILD_LOG, KNOWLEDGE_DIR, WORKFLOW_OWNERS_FILE,  # noqa: E402
                                corpus_root)

GRAPH = KNOWLEDGE_DIR / "graph.json"
AGENTIC = "03-instructors/AgenticAI Instructors Training Plan.xlsx"


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s))
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s).lower()).strip()


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
    def prog_key(label: str) -> str:
        s = label
        for token in taxonomy.doctypes() + ["Interview Preparation Program",
                                            "Engineering", "Program"]:
            s = re.sub(re.escape(token), " ", s, flags=re.I)
        s = re.sub(re.escape(taxonomy.families()[0]), " ", s, flags=re.I)
        return norm(s)
    dom_key = {norm(re.sub(r"\(.*?\)", " ", d["label"])): d["id"] for d in by_type["domain"]}
    joined = 0
    for p in by_type["program"]:
        k = prog_key(p["label"])
        did = dom_key.get(k)
        if did:
            edges.append({"source": p["id"], "target": did, "rel": R("program_domain")})
            joined += 1

    # teaches: instructor -> module, from the one sheet that pairs them on a row.
    # This is eval Q15's source and the file the `teaches` edge always named.
    wb = openpyxl.load_workbook(root / AGENTIC, read_only=True, data_only=True)
    ws = wb["Preferred SMEs for Each Topic"]
    rows = list(ws.iter_rows(values_only=True))
    taught = 0
    for block in ((0, 1, 2, 3), (5, 6, 7, 8)):
        mcol, icol, rcol, ccol = block
        current_module = None
        for rownum, row in enumerate(rows[2:], start=3):
            def c(i):
                return str(row[i]).strip() if i < len(row) and row[i] is not None else ""
            if c(mcol):
                current_module = c(mcol)
            inst = c(icol)
            if not current_module or not inst:
                continue
            mid = idx.get(("module", norm(current_module)))
            iid = idx.get(("instructor", norm(inst)))
            if mid and iid:
                e = {"source": iid, "target": mid, "rel": R("instructor_module"),
                     "provenance": {"file": AGENTIC,
                                    "sheet": "Preferred SMEs for Each Topic", "row": rownum}}
                if c(rcol):
                    e["avg_rating"] = c(rcol)
                if c(ccol):
                    e["classes"] = c(ccol)
                edges.append(e)
                taught += 1
    wb.close()

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
                         "sources": [{"origin": "corpus", "file": f}]}
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
    print(f"  teaches: {taught} instructor->module pairs from {AGENTIC.split('/')[-1]}")
    print(f"  workflow_owned_by: {len(confirmed)} confirmed rows in workflow-owners.yaml")
    print()
    print("-" * 78)
    print("FILES THAT YIELDED NO ENTITY")
    print("-" * 78)
    print(f"  {len(barren)} of {len(file_nodes)}")
    for b_ in barren:
        print(f"    {b_}")
    print()

    GRAPH.write_text(json.dumps({
        "meta": {"built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "taxonomy_version": taxonomy.version(),
                 "source": "local-folder",
                 "drive_deferred": True,
                 "nodes": len(all_nodes), "edges": len(edges),
                 "node_counts": {t: len(v) for t, v in by_type.items()},
                 "edge_counts": dict(counts)},
        "nodes": all_nodes, "edges": edges}, indent=1, sort_keys=True), encoding="utf-8")
    print(f"wrote {GRAPH.name}: {len(all_nodes)} nodes, {len(edges)} edges")

    with BUILD_LOG.open("a", encoding="utf-8") as fh:
        fh.write(f"\n## {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')} — 04_build_graph\n\n")
        fh.write(f"- Nodes {len(all_nodes)} | edges {len(edges)}\n")
        for name in taxonomy.edge_type_names():
            fh.write(f"    - {name}: {counts.get(name,0)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
