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

from pipeline.lib import ids                                          # noqa: E402
from pipeline.lib import content_model as cm                          # noqa: E402
from pipeline.lib import content_scope as scope                       # noqa: E402
from pipeline.lib import curriculum as cur                            # noqa: E402
from pipeline.lib import mastersheet as ms                            # noqa: E402
from pipeline.lib import resolve as rsv                               # noqa: E402
from pipeline.lib import taxonomy as tax                              # noqa: E402
from pipeline.lib.paths import CONFIG_DIR, KNOWLEDGE_DIR, REPO_ROOT   # noqa: E402

CACHE = REPO_ROOT / ".drive-cache" / "content-rowB"
OUT = KNOWLEDGE_DIR / "content_graph.json"
#: THE SENSITIVE HALF, GITIGNORED. Same split rule as knowledge/graph.json:
#: `sensitive: true` goes here and nowhere else. It exists because
#: docs/CONTACT-DATA.md §R approved instructor phone/email/LinkedIn on the
#: condition that they never reach a tracked file, and `content_graph.json` is
#: tracked. Caught by tests/test_no_contact_data_in_tracked_files.py on the
#: first build that produced one.
OUT_SENSITIVE = KNOWLEDGE_DIR / "content_graph-sensitive.json"
MODULE_REVIEW = CONFIG_DIR / "module-aliases-review.yaml"
TOPIC_REVIEW = CONFIG_DIR / "content-topic-review.yaml"
PEOPLE_REVIEW = CONFIG_DIR / "mastersheet-people-review.yaml"
DECK_REVIEW = CONFIG_DIR / "deck-instructor-review.yaml"

#: Roles, resolved once. A literal edge name here would be a second source of
#: truth and `tests/test_taxonomy_single_source.py` fails the build on one.
R = {r: tax.edge_for_role(r) for r in (
    "domain_curriculum", "curriculum_module", "domain_module", "module_week",
    "module_class_file", "module_assignment", "assignment_reviewed_in",
    "module_deck", "module_topic", "module_repo", "provenance",
    "module_session", "module_instructor", "contact_of")}

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
T_DECK = _tgt_of("module_deck")
T_ASSIGN = _tgt_of("module_assignment")
T_REVIEW = _tgt_of("assignment_reviewed_in")
T_TOPIC = _tgt_of("module_topic")
T_REPO = _tgt_of("module_repo")
T_FILE = _tgt_of("provenance")
T_SESSION = _tgt_of("module_session")
T_TUTOR = _tgt_of("module_instructor")
T_TUTOR_CONTACT = _tgt_of("contact_of")

MASTERSHEET = (REPO_ROOT / ".drive-cache" / "02-curriculum" /
               "Resource Collection Mastersheet (Software + System).xlsx")


#: Distinguishes row-B content ids from the label-keyed main graph.
NAMESPACE = "rowB"


def nid(ntype: str, *parts) -> str:
    """An id from the SHARED minter, prefixed and 16 hex like every other node.

    This used to be a bare sha256 hexdigest with no type prefix, so every node
    pass 7 produced failed the database's `id_shape` constraint. Callers pass
    the real NODE TYPE, not a short tag, because the type is hashed in.
    """
    # NAMESPACED. Without the marker, a content node and a main-graph node
    # that happen to share a canonical string mint the SAME id — and that is
    # not a merge, it is a merge nobody reviewed. Measured when this was
    # missing: 34 collisions, 33 instructors and one domain where the content
    # node was `Backend Engineering` and the main node was `Backend`.
    #
    # Whether a content instructor IS a main-graph instructor is exactly what
    # the INS rows ask. A hash coincidence must never answer it.
    return ids.compound(ntype, NAMESPACE, *parts)


class Graph:
    def __init__(self):
        self.nodes: dict[str, dict] = {}
        self.edges: list[dict] = []
        self.counts = Counter()

    def node(self, node_id: str, ntype: str, label: str, sources: list,
             **props) -> str:
        # LABEL HYGIENE HAPPENS HERE, not at each call site. `nodes.label` may
        # not carry a URL or an address (migration 0018); doing it centrally
        # means a node type added later cannot forget. The original always
        # survives in label_raw.
        clean, changed = cm.clean_label(label)
        if changed:
            props.setdefault("label_raw", label)
            props["label_had_link"] = True
            label = clean
        if node_id in self.nodes:
            # MERGE, do not discard. The per-module instructor block creates a
            # bare node and the instructor TABLE fills it in; returning early
            # meant whichever came first won and the table's columns were lost.
            existing = self.nodes[node_id]
            # DEDUPED. A provenance record identical on every field is the SAME
            # assertion, and `project_graph.assertion_id` is content-addressed,
            # so 28 copies of one record become 28 rows with one id and the
            # projection aborts on a collision. Measured before this: 216
            # fully-identical duplicates, from topic text that repeats down a
            # spreadsheet tab where the row is not part of the locator.
            seen = {json.dumps(s, sort_keys=True) for s in existing["sources"]}
            for s in sources:
                k = json.dumps(s, sort_keys=True)
                if k not in seen:
                    existing["sources"].append(s)
                    seen.add(k)
            for k, v in props.items():
                if v is not None and k not in ("label_raw",):
                    existing.setdefault(k, v)
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
    stats_join: Counter = Counter()
    module_labels: dict[tuple, Counter] = defaultdict(Counter)
    topic_rows: list[dict] = []
    tab_rows: list[dict] = []

    # -- domains -----------------------------------------------------------
    dom_id = {}
    for folder, slug in scope.IN_SCOPE_DOMAINS.items():
        src = [{"origin": "corpus", "file": folder}]
        dom_id[folder] = g.node(nid(T_DOMAIN, slug), T_DOMAIN,
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
        src = [{"origin": "corpus", "file": folder,
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
            wid = g.node(nid(T_WEEK, slug, wk.value), T_WEEK,
                         f"Week {wk.value}", wsrc, number=wk.value)
            g.edge(R["module_week"], key, wid, wsrc,
                   source_kind=wk.source_kind, source_file=wk.source_file)

        if len(labels) > 1:
            topic_rows.append({"kind": "module-label-variant",
                               "domain": slug, "sequence": seq,
                               "variants": dict(labels), "confirmed": False})

    # -- the mastersheet: sessions, uplevel links, instructors -------------
    #
    # STRUCTURED, so instructors come from here and only here. D1 is unchanged:
    # nothing below reads a slide, and the deck path still yields no people.
    # Every folder name seen in the crawl -> the row-B domain it sits under.
    folder_of_stated: dict = {}
    for r in man.values():
        parts = r["path"].strip("/").split("/")
        if parts and parts[0] in scope.IN_SCOPE_DOMAINS:
            for comp in parts[:-1]:
                folder_of_stated.setdefault(cur.normalise_for_join(comp), parts[0])

    sess_id: dict = {}
    sess_kinds: dict = {}
    assigns: dict = {}
    deck_proposals: list = []
    tutor_id: dict = {}
    people_review: list = []
    sheet_variants: list = []
    if MASTERSHEET.exists():
        for tab_name in ms.DOMAIN_TABS:
            tab = ms.parse_tab(MASTERSHEET, tab_name)
            # THE SHEET'S `Drive Folder` VALUE IS NOT ALWAYS THE DOMAIN FOLDER.
            # Backend states `SD3: Backend Engineering`, the domain folder
            # itself; the other three state their CONTENT REPO subfolder
            # (`IK: Full Stack: Content Repo`). So the value is looked up
            # among the folder names the crawl actually walked, and the domain
            # is whatever that path sits under — derived from the corpus rather
            # than guessed from the tab's name.
            folder = folder_of_stated.get(cur.normalise_for_join(
                tab.drive_folder or ""))
            if folder is None:
                gaps[f"mastersheet tab {tab_name}: no row-B folder match"] += 1
                continue
            slug = scope.IN_SCOPE_DOMAINS[folder]
            msrc = [{"origin": "corpus",
                     "file": "02-curriculum/Resource Collection Mastersheet "
                             "(Software + System).xlsx",
                     "sheet": tab_name}]

            for mod in tab.modules:
                key = (folder, mod.sequence)
                if key not in mod_id:
                    gaps[f"{folder}: mastersheet module not in the crawl"] += 1
                    continue
                m = mod_id[key]
                g.nodes[m]["uplevel_link"] = mod.uplevel_link or None
                if cur.normalise_for_join(mod.name) != \
                        cur.normalise_for_join(g.nodes[m]["label"]):
                    sheet_variants.append(
                        {"domain": slug, "sequence": mod.sequence,
                         "folder_label": g.nodes[m]["label"],
                         "mastersheet_label": mod.name})

                for s in mod.sessions:
                    sid = nid(T_SESSION, slug, mod.sequence, s.kind, s.uplevel_link)
                    src = [dict(msrc[0], row=s.row)]
                    g.node(sid, T_SESSION, s.name, src, label_raw=s.name,
                           session_kind=s.kind, resource_type=s.resource_type,
                           uplevel_link=s.uplevel_link)
                    g.edge(R["module_session"], m, sid, src, session_kind=s.kind)
                    sess_id[(slug, mod.sequence, s.kind)] = sid
                    sess_kinds.setdefault((slug, mod.sequence), set()).add(s.kind)

                assign = tab.assignments_by_sequence.get(mod.sequence, {})
                assigns[(slug, mod.sequence)] = assign
                for role in ("primary", "backup_1", "backup_2", "backup_3"):
                    for person in assign.get(role, []):
                        src = [dict(msrc[0], row=assign.get("row"),
                                    column=role)]
                        pid = nid(T_TUTOR, cur.normalise_for_join(person))
                        g.node(pid, T_TUTOR, person, src, label_raw=person,
                               cross_validated=False)
                        tutor_id[cur.normalise_for_join(person)] = pid
                        g.edge(R["module_instructor"], m, pid, src,
                               instructor_role=role)
                        if ms.needs_people_review(person):
                            people_review.append(
                                {"name": person, "domain": slug,
                                 "sequence": mod.sequence, "role": role,
                                 "reason": "first-name-only form"})

            # instructor table: public node, sensitive companion
            table_names = [r["name"] for r in tab.instructors]
            for row in tab.instructors:
                public, private = ms.split_instructor_row(row)
                if ms.is_unusable(public):
                    gaps["mastersheet instructor row unusable after scrub"] += 1
                    people_review.append(
                        {"name": "(none)", "domain": slug, "role": "table",
                         "reason": "row held contact data and no name; "
                                   "scrubbed and NOT ingested",
                         "sheet_row": row.get("row")})
                    continue
                src = [dict(msrc[0], row=row.get("row"))]
                pid = nid(T_TUTOR, cur.normalise_for_join(public["name"]))
                g.node(pid, T_TUTOR, public["name"], src,
                       label_raw=public["name"], cross_validated=False,
                       **{k: v for k, v in public.items() if k != "name"})
                tutor_id[cur.normalise_for_join(public["name"])] = pid
                if private:
                    cid = nid(T_TUTOR_CONTACT, cur.normalise_for_join(public["name"]))
                    g.node(cid, T_TUTOR_CONTACT, public["name"], src,
                           label_raw=public["name"], sensitive=True, **private)
                    g.nodes[cid]["sensitive"] = True
                    g.edge(R["contact_of"], pid, cid, src)

            # first-name forms proposed against the table, never merged
            for entry in people_review:
                if entry["name"] == "(none)":
                    continue
                hit = rsv.resolve(entry["name"], table_names)
                if isinstance(hit, rsv.Ambiguous):
                    entry["candidates"] = list(hit.candidates)
                elif hit:
                    entry["candidate"] = hit

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
            cid = g.node(nid(T_CURRIC, fid), T_CURRIC,
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
                g.edge(R["curriculum_module"], nid(T_CURRIC, fid),
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
                     else T_FILE)
            uid = g.node(nid(ntype, "unavailable", fid), ntype, name, src,
                         **{k: v for k, v in u.items()
                            if k not in ("label", "label_raw")})
            g.edge(R["module_class_file"] if ntype == T_FILE
                   else R["module_deck"] if ntype == T_DECK
                   else R["module_repo"], m, uid, src, revision=revision)
            gaps[f"content unavailable: {r['rule']}"] += 1
            continue

        text = (CACHE / r["text_path"]).read_text(encoding="utf-8")

        # SESSION EDGE, ONLY WHERE EVIDENCE ALLOWS. The module edge below is
        # unconditional; this one is added when the folder or the name places
        # the file on a session the module actually has, and it records which.
        skinds = sess_kinds.get((slug, ref.sequence), set())
        match = cm.session_for_file(path, name, skinds) if skinds else None
        if match:
            sid = sess_id.get((slug, ref.sequence, match.kind))
            if sid:
                g.edge(R["module_session"], m, sid, src,
                       session_kind=match.kind, match_evidence=match.evidence,
                       attached_file=name)
                stats_join[f"session ({match.evidence})"] += 1
        else:
            stats_join["module level only"] += 1

        # A deck filename ending in a first name PROPOSES an instructor now
        # that the mastersheet supplies them. D1 unchanged: a proposal is not
        # an edge, and nothing here reads slide content.
        if cm.is_deck(mime):
            prop = cm.propose_deck_instructor(name, assigns.get((slug, ref.sequence), {}))
            if prop:
                prop.update(domain=slug, sequence=ref.sequence, path=path,
                            session=match.kind if match else None)
                deck_proposals.append(prop)

        historical = cm.is_historical(path, name)

        if cm.is_repo(mime, name):
            rid = g.node(nid(T_REPO, fid), T_REPO, name, src,
                         owner_domain=r.get("owner_domain"))
            g.edge(R["module_repo"], m, rid, src, revision=revision)
        elif cm.is_deck(mime):
            did = g.node(nid(T_DECK, fid), T_DECK, name, src,
                         owner_domain=r.get("owner_domain"),
                         slide_count=r.get("slide_count"))
            # The deck hangs off the MODULE. There used to be a live_class
            # node in between, minted from this same file, and it carried no
            # fact the deck node does not — see taxonomy.yaml `delivers`.
            g.edge(R["module_deck"], m, did, src, revision=revision,
                   superseded_by=("base" if revision == "revamp" else None))
        elif role == "review":
            aid = g.node(nid(T_REVIEW, fid), T_REVIEW, name, src)
            g.edge(R["assignment_reviewed_in"], m, aid, src, revision=revision)
        elif role == "task":
            aid = g.node(nid(T_ASSIGN, fid), T_ASSIGN, name, src)
            g.edge(R["module_assignment"], m, aid, src, revision=revision)
        elif role == "class":
            # Attach the FILE NODE THAT ALREADY EXISTS rather than mint a
            # parallel one. These files were the other 443 live_class nodes.
            g.edge(R["module_class_file"], m, nid(T_FILE, fid), src,
                   revision=revision)

        # -- topics, with their locator -----------------------------------
        source_kind = "curriculum" if kind else ("deck" if cm.is_deck(mime)
                                                     else "doc")
        for t in cm.topics_from_text(text, source_kind):
            tid = nid(T_TOPIC, slug, ref.sequence,
                      cm.topic_key(slug, ref.sequence, t.label))
            tsrc = [cm.provenance(r, **{t.locator_kind: t.locator})]
            g.node(tid, T_TOPIC, t.label, tsrc, label_raw=t.label,
                   locator_kind=t.locator_kind)
            g.edge(R["module_topic"], m, tid, tsrc,
                   **{t.locator_kind: t.locator, "from": source_kind},
                   rank=cm.topic_rank(match.kind if match else source_kind),
                   historical=historical or None)

        # D1, at the point it would be violated.
        assert cm.people_from_text(text) == [], "D1: no people from content"

    # -- file nodes + provenance edges -------------------------------------
    for fid, r in man.items():
        folder = r["path"].strip("/").split("/")[0]
        if folder in scope.IN_SCOPE_DOMAINS:
            g.node(nid(T_FILE, fid), T_FILE, r["path"],
                   [cm.provenance(r)], relative_path=r["path"].lstrip("/"),
                   owner_domain=r.get("owner_domain"), mime=r["mime"])

    write_reviews(topic_rows, tab_rows, people_review, sheet_variants,
                  deck_proposals, g)
    meta = {
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "drive-cache/content-rowB",
        "scope": "registry row B, four approved domains (D2a)",
        "taxonomy_version": tax.version(),
        "nodes": len(g.nodes), "edges": len(g.edges),
        "node_counts": dict(g.counts),
        "edge_counts": dict(Counter(e["rel"] for e in g.edges)),
        "gaps": dict(gaps),
        "join": dict(stats_join),
        "caveat": ("Every count is a floor over 4 of 12 domain folders in 1 of "
                   "5 registry rows. Instructors and owners are DEFERRED and "
                   "no person node exists. D1: no people from deck content."),
    }
    # SPLIT. A node marked sensitive, and every edge touching one, goes to the
    # gitignored half. Edges are moved too: an edge to a withheld node would
    # otherwise be a dangling reference in the public file.
    sens_ids = {n["id"] for n in g.nodes.values() if n.get("sensitive")}
    pub_nodes = [n for n in g.nodes.values() if n["id"] not in sens_ids]
    sen_nodes = [n for n in g.nodes.values() if n["id"] in sens_ids]
    pub_edges = [e for e in g.edges
                 if e["source"] not in sens_ids and e["target"] not in sens_ids]
    sen_edges = [e for e in g.edges
                 if e["source"] in sens_ids or e["target"] in sens_ids]
    meta["withheld"] = {
        "file": OUT_SENSITIVE.name, "nodes": len(sen_nodes),
        "edges": len(sen_edges),
        "reason": "sensitive: true — instructor contact fields approved by "
                  "docs/CONTACT-DATA.md §R for the sensitive half only. "
                  "Gitignored; admin-only behind the recruiting RLS path.",
    }
    meta["nodes"], meta["edges"] = len(pub_nodes), len(pub_edges)
    OUT.write_text(json.dumps(
        {"meta": meta, "nodes": pub_nodes, "edges": pub_edges},
        indent=1, sort_keys=True), encoding="utf-8")
    OUT_SENSITIVE.write_text(json.dumps(
        {"meta": {"withheld_from": OUT.name, "built_at": meta["built_at"]},
         "nodes": sen_nodes, "edges": sen_edges},
        indent=1, sort_keys=True), encoding="utf-8")
    report(meta, g)
    return 0


def write_reviews(topic_rows: list, tab_rows: list, people_review: list,
                  sheet_variants: list, deck_proposals: list,
                  g: Graph) -> None:
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

    PEOPLE_REVIEW.write_text(
        f"# Instructor names from the Resource Collection Mastersheet that need\n"
        f"# a human decision. NOTHING HERE IS APPLIED.\n"
        f"#\n"
        f"# generated: {stamp}\n"
        f"# rows: {len(people_review)}\n"
        f"#\n"
        f"# A first-name-only cell (`Shelby`, `Faraaz`, `Bharath`) is a\n"
        f"# PROPOSAL against the tab's own instructor table, never a merge —\n"
        f"# lib/resolve.py returns Ambiguous by default because three shipped\n"
        f"# bugs came from picking with no signal. A row listed with no\n"
        f"# candidate matched nothing and is left alone.\n"
        f"version: 1\n"
        f"names:\n" +
        ("".join(f"  - name: {r['name']!r}\n"
                 f"    domain: {r.get('domain','')}\n"
                 f"    role: {r.get('role','')}\n"
                 f"    reason: {r['reason']!r}\n"
                 + (f"    candidates: {json.dumps(r['candidates'])}\n"
                    if r.get("candidates") else
                    f"    candidate: {r['candidate']!r}\n"
                    if r.get("candidate") else "")
                 + f"    confirmed: false\n" for r in people_review)
         or "  []\n"), encoding="utf-8")

    DECK_REVIEW.write_text(
        f"# Deck filename -> instructor proposals. NOTHING HERE IS APPLIED.\n"
        f"#\n"
        f"# generated: {stamp}\n"
        f"# rows: {len(deck_proposals)}\n"
        f"#\n"
        f"# A deck named `UI & DOM - Jakob.pptx` hints at an instructor, and the\n"
        f"# mastersheet now says who that module's instructors are — so the hint\n"
        f"# can be checked. D1 is unchanged: it forbids people from slide\n"
        f"# CONTENT, and a filename is weaker evidence than the sheet, not\n"
        f"# stronger. Ambiguous rows list every candidate rather than ranking.\n"
        f"version: 1\n"
        f"proposals:\n" +
        ("".join(f"  - deck: {r['deck']!r}\n"
                 f"    domain: {r['domain']}\n"
                 f"    sequence: {r['sequence']}\n"
                 f"    matched_token: {r['matched_token']!r}\n"
                 f"    session: {r.get('session')!r}\n"
                 + (f"    ambiguous: true\n    candidates: {json.dumps(r['candidates'])}\n"
                    if r.get("ambiguous") else
                    f"    candidate: {r['candidate']!r}\n"
                    f"    instructor_role: {r['instructor_role']}\n")
                 + f"    evidence: {r['evidence']!r}\n"
                 f"    confirmed: false\n" for r in deck_proposals) or "  []\n"),
        encoding="utf-8")

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
        f"# mastersheet label differences: {len(sheet_variants)}\n"
        f"# The Resource Collection Mastersheet names each module too. Where it\n"
        f"# disagrees with the folder, that is EVIDENCE for resolving the\n"
        f"# variant — cited here, still a proposal, never auto-applied.\n"
        f"mastersheet_labels:\n" +
        ("".join(f"  - domain: {r['domain']}\n"
                 f"    sequence: {r['sequence']}\n"
                 f"    folder_label: {r['folder_label']!r}\n"
                 f"    mastersheet_label: {r['mastersheet_label']!r}\n"
                 f"    confirmed: false\n" for r in sheet_variants) or "  []\n") +
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
    if meta.get("join"):
        print("\n  DECK/DOC ATTACHMENT")
        for k, v in sorted(meta["join"].items(), key=lambda kv: -kv[1]):
            print(f"    {k:<26}{v:>7,}")
    if meta["gaps"]:
        print("\n  GAPS (counted, not enumerated)")
        for k, v in sorted(meta["gaps"].items(), key=lambda kv: -kv[1]):
            print(f"    {v:>5}x {k}")
    print(f"\n  -> {OUT}")
    print(f"  -> {OUT_SENSITIVE}  "
          f"({meta['withheld']['nodes']} nodes, "
          f"{meta['withheld']['edges']} edges, GITIGNORED)")


if __name__ == "__main__":
    raise SystemExit(main())
