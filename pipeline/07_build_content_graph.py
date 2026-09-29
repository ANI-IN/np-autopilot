#!/usr/bin/env python3
"""Pass 7 — build the row-B content graph from the pass-6 cache.

Reads `.drive-cache/content-rowB/` (manifest + redacted text) and writes
`knowledge/content_graph.json` plus two review files. It touches no network:
pass 6 fetches, pass 7 parses, which is the same separation `CLAUDE.md`
insists on between passes 0 and 1.

WHAT IT WILL NOT DO
  * create a person from anything, ever (D1, and instructors are deferred)
  * merge a row-B module into the existing 922 label-keyed `module` nodes —
    collisions go to a review file, unconfirmed
  * compute a program week from a folder sequence
  * emit a topic that cannot cite the slide, page or tab it came from
  * drop a file whose content we could not read — it becomes a marked node

Every node and every edge carries provenance. Edge names are resolved through
`lib/taxonomy.py` by ROLE, never written as literals.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.lib import content_model as cm                          # noqa: E402
from pipeline.lib import content_scope as scope                       # noqa: E402
from pipeline.lib import curriculum as cur                            # noqa: E402
from pipeline.lib import taxonomy as tax                              # noqa: E402
from pipeline.lib.paths import CONFIG_DIR, KNOWLEDGE_DIR, REPO_ROOT   # noqa: E402

CACHE = REPO_ROOT / ".drive-cache" / "content-rowB"
OUT = KNOWLEDGE_DIR / "content_graph.json"
MODULE_REVIEW = CONFIG_DIR / "module-aliases-review.yaml"
TOPIC_REVIEW = CONFIG_DIR / "content-topic-review.yaml"

#: Roles, resolved once. A literal edge name here would be a second source of
#: truth and `tests/test_taxonomy_single_source.py` fails the build on one.
R = {r: tax.edge_for_role(r) for r in (
    "domain_curriculum", "curriculum_module", "domain_module", "module_week",
    "module_live_class", "module_assignment", "assignment_reviewed_in",
    "live_class_deck", "module_topic", "module_repo", "provenance")}

#: Node types DERIVED from the edges' declared endpoints, never written as
#: literals. Renaming a type in `taxonomy.yaml` moves this code with it instead
#: of silently emptying it — the property `web/lib/data.py::_overview_spec`
#: documents, and the reason `tests/test_taxonomy_single_source.py` exists.
#: The variable names are deliberately not the type strings.
def _src_of(role: str) -> str:
    return tax.edge_endpoints(R[role])[0]


def _tgt_of(role: str) -> str:
    return tax.edge_endpoints(R[role])[1]


T_DOMAIN = _src_of("domain_module")
T_MODULE = _tgt_of("domain_module")
T_CURRIC = _tgt_of("domain_curriculum")
T_WEEK = _tgt_of("module_week")
T_LIVE = _tgt_of("module_live_class")
T_DECK = _tgt_of("live_class_deck")
T_ASSIGN = _tgt_of("module_assignment")
T_REVIEW = _tgt_of("assignment_reviewed_in")
T_TOPIC = _tgt_of("module_topic")
T_REPO = _tgt_of("module_repo")
T_FILE = _tgt_of("provenance")


def nid(kind: str, *parts) -> str:
    return hashlib.sha256(("|".join((kind,) + tuple(map(str, parts))))
                          .encode()).hexdigest()


class Graph:
    def __init__(self):
        self.nodes: dict[str, dict] = {}
        self.edges: list[dict] = []
        self.counts = Counter()

    def node(self, node_id: str, ntype: str, label: str, sources: list,
             **props) -> str:
        if node_id in self.nodes:
            self.nodes[node_id]["sources"].extend(sources)
            return node_id
        self.nodes[node_id] = {
            "id": node_id, "type": ntype, "label": label,
            "label_raw": props.pop("label_raw", label),
            "sensitive": False, "sources": list(sources),
            **{k: v for k, v in props.items() if v is not None},
        }
        self.counts[ntype] += 1
        return node_id

    def edge(self, rel: str, src: str, tgt: str, sources: list, **props):
        self.edges.append({"rel": rel, "source": src, "target": tgt,
                           "sources": list(sources),
                           **{k: v for k, v in props.items() if v is not None}})


def load_manifest() -> dict:
    p = CACHE / "manifest.json"
    if not p.exists():
        sys.exit(f"no cache at {p}. Run pipeline/06_crawl_content.py first.")
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> int:
    man = load_manifest()
    g = Graph()
    gaps: Counter = Counter()
    module_labels: dict[tuple, Counter] = defaultdict(Counter)
    topic_rows: list[dict] = []
    tab_rows: list[dict] = []

    # -- domains -----------------------------------------------------------
    dom_id = {}
    for folder, slug in scope.IN_SCOPE_DOMAINS.items():
        src = [{"origin": "corpus", "file": f"/{folder}"}]
        dom_id[folder] = g.node(nid("domain", slug), T_DOMAIN,
                                folder.split(":", 1)[1].strip(), src,
                                label_raw=folder, slug=slug)

    # -- first pass: module labels, so the commonest wins as the display -----
    for r in man.values():
        ref = cm.parse_module(r["path"])
        if ref and ref.domain in scope.IN_SCOPE_DOMAINS:
            module_labels[(ref.domain, ref.sequence)][ref.label] += 1

    mod_id = {}
    for (folder, seq), labels in sorted(module_labels.items()):
        slug = scope.IN_SCOPE_DOMAINS[folder]
        label, _ = labels.most_common(1)[0]
        key = cm.module_key(slug, seq)
        src = [{"origin": "corpus", "file": f"/{folder}",
                "evidence_kind": "folder-structure"}]
        mod_id[(folder, seq)] = g.node(
            key, T_MODULE, label, src, label_raw=label,
            sequence=seq, domain_slug=slug,
            label_variants=sorted(labels) if len(labels) > 1 else None)
        g.edge(R["domain_module"], dom_id[folder], key, src, sequence=seq)

        # program week — curriculum doc or the owner fact, never arithmetic
        wk = cm.program_week_for(slug, seq)
        if wk is None:
            gaps[f"{folder}: no program week"] += 1
        else:
            wsrc = [{"origin": "hand", "evidence": wk.source_file,
                     "establishes": ["number"]}]
            wid = g.node(nid("week", slug, wk.value), T_WEEK,
                         f"Week {wk.value}", wsrc, number=wk.value)
            g.edge(R["module_week"], key, wid, wsrc,
                   source_kind=wk.source_kind, source_file=wk.source_file)

        if len(labels) > 1:
            topic_rows.append({"kind": "module-label-variant",
                               "domain": slug, "sequence": seq,
                               "variants": dict(labels), "confirmed": False})

    # -- files -------------------------------------------------------------
    for fid, r in man.items():
        path, name, mime = r["path"], r["name"], r["mime"]
        folder = path.strip("/").split("/")[0]
        if folder not in scope.IN_SCOPE_DOMAINS:
            continue
        slug = scope.IN_SCOPE_DOMAINS[folder]
        ref = cm.parse_module(path)
        src = [cm.provenance(r)]
        revision = cm.revision_of(path)

        # curriculum documents attach to the DOMAIN
        kind = cm.curriculum_kind(name)
        if kind:
            cid = g.node(nid("cdoc", fid), T_CURRIC,
                         name, src, label_raw=name, kind=kind,
                         owner_domain=r.get("owner_domain"),
                         content_available=r["action"] == "export")
            g.edge(R["domain_curriculum"], dom_id[folder], cid, src, kind=kind)
            if ref and (folder, ref.sequence) in mod_id:
                g.edge(R["curriculum_module"], cid,
                       mod_id[(folder, ref.sequence)], src, source_kind=kind)

        # A curriculum doc at the DOMAIN root joins by its lesson-plan ordinal:
        # structural, not a name match. Its TAB names are proposed instead.
        if ref is None and kind:
            seq = cm.lesson_plan_sequence(name)
            if seq is not None and (folder, seq) in mod_id:
                ref = cm.ModuleRef(folder, seq, name)
                g.edge(R["curriculum_module"], nid("cdoc", fid),
                       mod_id[(folder, seq)], src, source_kind=kind,
                       join="lesson-plan ordinal")
            elif r["action"] == "export":
                mods = {n["label"]: n["sequence"] for n in g.nodes.values()
                        if n["type"] == T_MODULE and n.get("domain_slug") == slug}
                text0 = (CACHE / r["text_path"]).read_text(encoding="utf-8")
                for tab in sorted(set(re.findall(r"^\[tab ([^\]]+)\]", text0,
                                                 re.M))):
                    prop = cm.propose_tab_join(tab, slug, mods)
                    if prop:
                        prop["source_doc"] = name
                        tab_rows.append(prop)
                gaps[f"{folder}: curriculum doc not joined to a module"] += 1

        if not ref or (folder, ref.sequence) not in mod_id:
            continue
        m = mod_id[(folder, ref.sequence)]
        role = cm.role_of(path)

        if r["action"] != "export":
            # Marked, never dropped, never given inferred content.
            u = cm.node_for_unavailable(r)
            ntype = (T_DECK if cm.is_deck(mime)
                     else T_REPO if cm.is_repo(mime, name)
                     else T_LIVE)
            uid = g.node(nid("unavail", fid), ntype, name, src,
                         **{k: v for k, v in u.items()
                            if k not in ("label", "label_raw")})
            g.edge(R["module_live_class"] if ntype == T_LIVE
                   else R["live_class_deck"] if ntype == T_DECK
                   else R["module_repo"], m, uid, src, revision=revision)
            gaps[f"content unavailable: {r['rule']}"] += 1
            continue

        text = (CACHE / r["text_path"]).read_text(encoding="utf-8")

        if cm.is_repo(mime, name):
            rid = g.node(nid("repo", fid), T_REPO, name, src,
                         owner_domain=r.get("owner_domain"))
            g.edge(R["module_repo"], m, rid, src, revision=revision)
        elif cm.is_deck(mime):
            did = g.node(nid("deck", fid), T_DECK, name, src,
                         owner_domain=r.get("owner_domain"),
                         slide_count=r.get("slide_count"))
            lid = g.node(nid("lc", fid), T_LIVE, name, src,
                         revision=revision,
                         superseded_by=("base" if revision == "revamp" else None))
            g.edge(R["module_live_class"], m, lid, src, revision=revision)
            g.edge(R["live_class_deck"], lid, did, src)
        elif role == "review":
            aid = g.node(nid("rev", fid), T_REVIEW, name, src)
            g.edge(R["assignment_reviewed_in"], m, aid, src, revision=revision)
        elif role == "task":
            aid = g.node(nid("task", fid), T_ASSIGN, name, src)
            g.edge(R["module_assignment"], m, aid, src, revision=revision)
        elif role == "class":
            lid = g.node(nid("lc", fid), T_LIVE, name, src,
                         revision=revision)
            g.edge(R["module_live_class"], m, lid, src, revision=revision)

        # -- topics, with their locator -----------------------------------
        source_kind = "curriculum" if kind else ("deck" if cm.is_deck(mime)
                                                     else "doc")
        for t in cm.topics_from_text(text, source_kind):
            tid = nid("topic", slug, ref.sequence,
                      cm.topic_key(slug, ref.sequence, t.label))
            tsrc = [cm.provenance(r, **{t.locator_kind: t.locator})]
            g.node(tid, T_TOPIC, t.label, tsrc, label_raw=t.label,
                   locator_kind=t.locator_kind)
            g.edge(R["module_topic"], m, tid, tsrc,
                   **{t.locator_kind: t.locator, "from": source_kind})

        # D1, at the point it would be violated.
        assert cm.people_from_text(text) == [], "D1: no people from content"

    # -- file nodes + provenance edges -------------------------------------
    for fid, r in man.items():
        folder = r["path"].strip("/").split("/")[0]
        if folder in scope.IN_SCOPE_DOMAINS:
            g.node(nid("file", fid), T_FILE, r["path"],
                   [cm.provenance(r)], relative_path=r["path"],
                   owner_domain=r.get("owner_domain"), mime=r["mime"])

    write_reviews(topic_rows, tab_rows, g)
    meta = {
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "drive-cache/content-rowB",
        "scope": "registry row B, four approved domains (D2a)",
        "taxonomy_version": tax.version(),
        "nodes": len(g.nodes), "edges": len(g.edges),
        "node_counts": dict(g.counts),
        "edge_counts": dict(Counter(e["rel"] for e in g.edges)),
        "gaps": dict(gaps),
        "caveat": ("Every count is a floor over 4 of 12 domain folders in 1 of "
                   "5 registry rows. Instructors and owners are DEFERRED and "
                   "no person node exists. D1: no people from deck content."),
    }
    OUT.write_text(json.dumps(
        {"meta": meta, "nodes": list(g.nodes.values()), "edges": g.edges},
        indent=1, sort_keys=True), encoding="utf-8")
    report(meta, g)
    return 0


def write_reviews(topic_rows: list, tab_rows: list, g: Graph) -> None:
    """Review files carry a HEADER with the generation time and the count, so
    an empty file can never be mistaken for 'no collisions'."""
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    existing = set()
    graph = KNOWLEDGE_DIR / "graph.json"
    if graph.exists():
        for n in json.loads(graph.read_text(encoding="utf-8"))["nodes"]:
            if n["type"] == T_MODULE:
                existing.add(cur.normalise_for_join(n["label"]))

    collisions = []
    for n in g.nodes.values():
        if n["type"] != T_MODULE:
            continue
        if cur.normalise_for_join(n["label"]) in existing:
            collisions.append({
                "label": n["label"], "domain": n["domain_slug"],
                "sequence": n["sequence"], "module_key": n["id"],
                "collides_with": "an existing label-keyed module node",
                "confirmed": False,
            })

    MODULE_REVIEW.write_text(
        f"# Row-B modules whose LABEL collides with an existing module node.\n"
        f"#\n"
        f"# generated: {stamp}\n"
        f"# collisions: {len(collisions)}\n"
        f"#\n"
        f"# A collision is NOT a match. Row-B modules are keyed on\n"
        f"# (domain_slug, sequence); these rows exist so a human can decide\n"
        f"# whether each is the same module as the label-keyed one in the\n"
        f"# existing graph. Nothing here is applied while confirmed: false.\n"
        f"version: 1\n"
        f"collisions:\n" +
        ("".join(f"  - label: {c['label']!r}\n"
                 f"    domain: {c['domain']}\n"
                 f"    sequence: {c['sequence']}\n"
                 f"    module_key: {c['module_key']}\n"
                 f"    confirmed: false\n" for c in collisions)
         or "  []\n"), encoding="utf-8")

    TOPIC_REVIEW.write_text(
        f"# Module label variants found across folder shapes.\n"
        f"#\n"
        f"# generated: {stamp}\n"
        f"# variants: {len(topic_rows)}\n"
        f"#\n"
        f"# The module's IDENTITY is (domain_slug, sequence), so a variant is a\n"
        f"# display question, not an identity one. Recorded because normalising\n"
        f"# `JS` to `JavaScript` is a curated alias and must be confirmed one at\n"
        f"# a time, never applied implicitly.\n"
        f"version: 1\n"
        f"# tab->module proposals: {len(tab_rows)}, all unconfirmed. A tab name\n"
        f"# matching a module label is a NAME MATCH — the alias problem for the\n"
        f"# third time — so it proposes and never applies. Ambiguous rows list\n"
        f"# every candidate rather than ranking them.\n"
        f"tab_joins:\n" +
        ("".join(f"  - tab: {r['tab']!r}\n"
                 f"    domain: {r['domain']}\n"
                 f"    source_doc: {r.get('source_doc','')!r}\n"
                 + (f"    ambiguous: true\n    candidates: {json.dumps(r['candidates'])}\n"
                    if r.get("ambiguous") else
                    f"    candidate: {r['candidate']!r}\n"
                    f"    candidate_sequence: {r['candidate_sequence']}\n")
                 + f"    confirmed: false\n" for r in tab_rows) or "  []\n") +
        f"variants:\n" +
        ("".join(f"  - domain: {r['domain']}\n"
                 f"    sequence: {r['sequence']}\n"
                 f"    variants: {json.dumps(r['variants'])}\n"
                 f"    confirmed: false\n" for r in topic_rows)
         or "  []\n"), encoding="utf-8")


def report(meta: dict, g: Graph) -> None:
    print("=" * 74)
    print("PASS 7 — row B content graph")
    print("=" * 74)
    print(f"  nodes {meta['nodes']:,}   edges {meta['edges']:,}")
    print("\n  NODES")
    for k, v in sorted(meta["node_counts"].items(), key=lambda kv: -kv[1]):
        print(f"    {k:<18}{v:>7,}")
    print("\n  EDGES")
    for k, v in sorted(meta["edge_counts"].items(), key=lambda kv: -kv[1]):
        print(f"    {k:<18}{v:>7,}")
    if meta["gaps"]:
        print("\n  GAPS (counted, not enumerated)")
        for k, v in sorted(meta["gaps"].items(), key=lambda kv: -kv[1]):
            print(f"    {v:>5}x {k}")
    print(f"\n  -> {OUT}")


if __name__ == "__main__":
    raise SystemExit(main())
