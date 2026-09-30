"""Apply the answered REVIEW-QUEUE decisions to the two graphs.

TWO POPULATIONS, ONE ANSWER SHEET. `knowledge/graph.json` keys modules on
their LABEL (922 of them) and `knowledge/content_graph.json` keys them on
(domain_slug, sequence) (20). A shared label was never identity — that is why
the MOD rows existed — so the join is a recorded human decision, read from
`config/module-merges.yaml`, and nothing here infers one.

WHAT IS PRESERVED, BECAUSE A MERGE IS THE EASIEST PLACE TO LOSE SOMETHING:

  label_raw    the absorbed node's label moves to `merged_label_raw`. §1: a
               label is the citation key back to the source, so it survives
               even when it is not the one displayed.
  provenance   `sources` are unioned. No record is dropped.
  edges        every edge is retargeted, never deleted, and each one records
               `merged_from` (the id it used to point at) and `mod_id`.
  reversal     every touched node and edge carries its `mod_id`, so one merge
               can be undone without unpicking the rest.

EVIDENCE TIERS ARE NEVER MERGED. A legacy `teaches` edge and a mastersheet
`taught_by` edge are two different claims about who staffs a module, made by
two sources that have not been reconciled. Collapsing them would manufacture
agreement. They are kept as separate edges and tagged `tier`, and staffing is
required to group by it — CLAUDE.md §4 records a staffing filter hiding the
one domain with a single instructor, and this is the same question one layer
up.
"""
from __future__ import annotations

import collections
import copy
import re
from pathlib import Path
from typing import Any

import yaml

from . import taxonomy
from .paths import CONFIG_DIR, KNOWLEDGE_DIR

MERGES_FILE = CONFIG_DIR / "module-merges.yaml"
IDENTITY_FILE = CONFIG_DIR / "instructor-identity.yaml"

TIER_LEGACY = "legacy"
TIER_MASTERSHEET = "mastersheet"


def load_spec(path: Path | None = None) -> dict:
    return yaml.safe_load((path or MERGES_FILE).read_text(encoding="utf-8"))


def load_identities(path: Path | None = None) -> dict:
    p = path or IDENTITY_FILE
    return yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}


def _module(nodes: list, slug: str, seq: int) -> dict | None:
    return next((n for n in nodes if n["type"] == "module"
                 and n.get("domain_slug") == slug and n.get("sequence") == seq), None)


def _session(nodes: list, edges: list, module_id: str, kind: str) -> dict | None:
    rel = taxonomy.edge_for_role("module_session")
    by_id = {n["id"]: n for n in nodes}
    for e in edges:
        if e["rel"] != rel or e["source"] != module_id or e.get("attached_file"):
            continue
        n = by_id.get(e["target"])
        if n is not None and n.get("session_kind") == kind:
            return n
    return None


def _tier_for(rel: str) -> str | None:
    """Which evidence tier an edge belongs to, or None if it is not staffing."""
    if rel == taxonomy.edge_for_role("instructor_module"):
        return TIER_LEGACY
    if rel == taxonomy.edge_for_role("module_instructor"):
        return TIER_MASTERSHEET
    return None


DOMAIN_FAMILIES = (
    ("full", "full-stack"), ("front", "frontend"), ("back", "backend"),
    ("test", "testing"), ("data", "data"), ("agentic", "agentic"),
    ("engineering management", "em"), ("tpm", "tpm"), ("product", "product"),
)


def _family(label: str | None) -> str:
    s = (label or "").lower()
    for needle, fam in DOMAIN_FAMILIES:
        if needle in s:
            return fam
    return re.sub(r"[^a-z]", "", s)[:12]


def conflict_for(group: list, nodes: list, edges: list,
                 all_labels: list | None = None) -> str | None:
    """Why this same-label group must NOT be bulk-merged, or None.

    WHY THE OBVIOUS CHECK DOES NOT WORK. The first version asked whether the
    two nodes share a MODULE. They almost never can: only the modules with an
    answered MOD row are one node, so for every instructor who does not teach
    one of those, "no shared module" is guaranteed by construction and says
    nothing about identity. It flagged 14 of 26 pairs and not one was a real
    conflict — a cutoff excluding correct answers, CLAUDE.md §4 exactly.

    DOMAIN REACH survives that, because a module still reaches its domain
    whether or not it was merged. Two nodes whose domains are wholly disjoint
    are evidence of two people; two nodes sharing a domain family are not.

    Absence of evidence is NOT a conflict and is not treated as one: a pair
    where either side reaches no domain at all returns None, because "I cannot
    tell" and "they differ" are different answers.
    """
    from . import resolve as _resolve
    labels = {(n.get("label") or "").strip() for n in group}
    if all_labels is not None and labels:
        one = sorted(labels)[0]
        if isinstance(_resolve.resolve(one, all_labels), _resolve.Ambiguous):
            return f"{one!r} is Ambiguous in lib/resolve.py"

    by_id = {n["id"]: n for n in nodes}
    incoming = collections.defaultdict(list)
    for e in edges:
        incoming[e["target"]].append(e)
    dom_rel = taxonomy.edge_for_role("domain_module")

    def domains(instructor_id):
        out = set()
        for e in edges:
            if not e.get("tier"):
                continue
            ends = (e["source"], e["target"])
            if instructor_id not in ends:
                continue
            other = ends[1] if ends[0] == instructor_id else ends[0]
            mod = by_id.get(other)
            if mod is None or mod["type"] != "module":
                continue
            if mod.get("domain_slug"):
                out.add(_family(mod["domain_slug"]))
            for ie in incoming[mod["id"]]:
                if ie["rel"] in (dom_rel, "covers", "contains"):
                    out.add(_family(by_id.get(ie["source"], {}).get("label")))
        return {d for d in out if d}

    sides = [domains(n["id"]) for n in group]
    if not all(sides):
        return None                       # cannot tell; not a conflict
    if not set.intersection(*sides):
        return ("domains are disjoint: "
                + " vs ".join(",".join(sorted(s)) for s in sides))
    return None


def merge(main: dict, content: dict, spec: dict | None = None,
          identities: dict | None = None) -> dict:
    """Return ONE graph with the answered merges applied. Inputs untouched."""
    spec = spec if spec is not None else load_spec()
    identities = identities if identities is not None else load_identities()

    nodes = [copy.deepcopy(n) for n in main["nodes"] + content["nodes"]]
    edges = [copy.deepcopy(e) for e in main["edges"] + content["edges"]]
    by_id = {n["id"]: n for n in nodes}

    # -- 1. tag every staffing edge with its tier BEFORE anything moves ----
    # Done first so a retargeted edge cannot lose the fact of where it came
    # from: after the merge both tiers hang off the same module.
    for e in edges:
        tier = _tier_for(e["rel"])
        if tier:
            e["tier"] = tier

    # -- 2. resolve the decisions into an id -> id map ---------------------
    remap: dict[str, str] = {}
    mod_of: dict[str, str] = {}
    unconfirmed: dict[str, set] = {}
    applied: list[dict] = []

    for m in spec.get("merges", []):
        mid = m["id"]
        tgt = _module(nodes, m["into"]["domain"], m["into"]["sequence"])
        if tgt is None:
            raise KeyError(f"{mid}: no row-B module {m['into']}")
        for legacy_id in m.get("legacy", []):
            if legacy_id not in by_id:
                raise KeyError(f"{mid}: legacy node {legacy_id} not in the graph")
            remap[legacy_id] = tgt["id"]
            mod_of[legacy_id] = mid
        for s in m.get("sessions", []):
            sess = _session(nodes, edges, tgt["id"], s["session_kind"])
            if sess is None:
                raise KeyError(f"{mid}: {m['into']} has no {s['session_kind']} session")
            remap[s["legacy"]] = sess["id"]
            mod_of[s["legacy"]] = mid
        for rel_role in m.get("mark_unconfirmed", []):
            for legacy_id in m.get("legacy", []):
                unconfirmed.setdefault(legacy_id, set()).add(rel_role)
        applied.append({"id": mid, "into": tgt["id"],
                        "absorbed": list(m.get("legacy", []))
                                    + [s["legacy"] for s in m.get("sessions", [])]})

    # -- 3. absorb: label_raw, provenance, the merge id --------------------
    for legacy_id, target_id in remap.items():
        src, tgt = by_id[legacy_id], by_id[target_id]
        tgt.setdefault("merged_label_raw", [])
        lab = src.get("label_raw") or src.get("label")
        if lab and lab not in tgt["merged_label_raw"]:
            tgt["merged_label_raw"].append(lab)
        tgt.setdefault("merged_from", []).append(legacy_id)
        tgt.setdefault("merge_ids", [])
        if mod_of[legacy_id] not in tgt["merge_ids"]:
            tgt["merge_ids"].append(mod_of[legacy_id])
        seen = {repr(s) for s in tgt.get("sources", [])}
        for s in src.get("sources", []):
            if repr(s) not in seen:
                tgt.setdefault("sources", []).append(s)
                seen.add(repr(s))

    # -- 4. retarget every edge. None is dropped. --------------------------
    for e in edges:
        for end in ("source", "target"):
            old = e[end]
            if old in remap:
                e[end] = remap[old]
                e["merged_from"] = old
                e["mod_id"] = mod_of[old]
                # KEPT, NOT ASSERTED. MOD-04: the legacy programme edges are
                # evidence of where the legacy layer filed the module, and
                # the owner neither confirmed nor deleted that.
                if e["rel"] in unconfirmed.get(old, ()):
                    e["confirmed"] = False

    # -- 5. confirmed instructor aliases -----------------------------------
    # Only `status: confirmed`. An unconfirmed identity stays two nodes, which
    # is the whole point of answering INS-08/30 with "unsure".
    # EVERY node carrying the canonical spelling OR an alias, not one per
    # label. These names occur in BOTH graphs — that is what the INS rows are
    # about — so `Balaram Velaga` is four nodes (two spellings x two graphs)
    # and collapsing one pair would leave the other, which reads as a merge
    # that worked.
    ident_remap: dict[str, str] = {}
    ident_of: dict[str, str] = {}
    for ident in (identities.get("identities") or []):
        if ident.get("status") != "confirmed":
            continue
        names = {ident["canonical"].strip().lower()}
        names |= {a.strip().lower() for a in ident.get("aliases", [])}
        group = [n for n in nodes if n["type"] == "instructor"
                 and (n.get("label") or "").strip().lower() in names]
        if len(group) < 2:
            continue
        canon = min(group, key=lambda n: n["id"])      # deterministic
        canon.setdefault("merged_label_raw", [])
        # THE CANONICAL NODE'S OWN LABEL SURVIVES TOO. `canon` is chosen by id,
        # so it is often the node carrying the ALIAS spelling — and overwriting
        # its label before recording it threw that spelling away. PPL-11 lost
        # `Bharath` exactly this way. §1: the original is the citation key.
        _own = canon.get("label_raw") or canon.get("label")
        if _own and _own != ident["canonical"] and _own not in canon["merged_label_raw"]:
            canon["merged_label_raw"].append(_own)
        canon["label"] = ident["canonical"]
        canon.setdefault("merged_from", [])
        canon.setdefault("merge_ids", [])
        for other in group:
            if other["id"] == canon["id"]:
                continue
            ident_remap[other["id"]] = canon["id"]
            ident_of[other["id"]] = ",".join(ident.get("resolves", [])) or ident["slug"]
            lab = other.get("label_raw") or other.get("label")
            if lab and lab not in canon["merged_label_raw"]:
                canon["merged_label_raw"].append(lab)
            canon["merged_from"].append(other["id"])
            seen = {repr(s) for s in canon.get("sources", [])}
            for s in other.get("sources", []):
                if repr(s) not in seen:
                    canon.setdefault("sources", []).append(s)
                    seen.add(repr(s))
        for r in ident.get("resolves", []):
            if r not in canon["merge_ids"]:
                canon["merge_ids"].append(r)
    for e in edges:
        for end in ("source", "target"):
            if e[end] in ident_remap:
                e["merged_from"] = e[end]
                if ident_of.get(e[end]):
                    e["ins_id"] = ident_of[e[end]]
                e[end] = ident_remap[e[end]]

    # -- 6. INS BULK: exact full-name pairs, each conflict-checked -------
    bulk = (identities or {}).get("bulk_confirmed") or {}
    excluded: list[dict] = []
    if bulk.get("pairs"):
        all_labels = sorted({(n.get("label") or "").strip()
                             for n in nodes if n["type"] == "instructor"})
        for pair in bulk["pairs"]:
            if pair["id"] in set(bulk.get("excludes") or ()):
                continue
            want = pair["canonical"].strip().lower()
            group = [n for n in nodes if n["type"] == "instructor"
                     and (n.get("label") or "").strip().lower() == want
                     and n["id"] not in ident_remap]
            if len(group) < 2:
                continue
            why = conflict_for(group, nodes, edges, all_labels)
            if why:
                # REPORTED, NEVER SILENT. An excluded pair is a row the owner
                # has to answer, not a thing the build decided on its own.
                excluded.append({"id": pair["id"],
                                 "canonical": pair["canonical"], "reason": why})
                continue
            canon = min(group, key=lambda n: n["id"])
            canon.setdefault("merged_label_raw", [])
            _own = canon.get("label_raw") or canon.get("label")
            if _own and _own != pair["canonical"] \
                    and _own not in canon["merged_label_raw"]:
                canon["merged_label_raw"].append(_own)
            canon["label"] = pair["canonical"]
            canon.setdefault("merged_from", [])
            canon.setdefault("merge_ids", [])
            for other in group:
                if other["id"] == canon["id"]:
                    continue
                ident_remap[other["id"]] = canon["id"]
                ident_of[other["id"]] = pair["id"]
                lab = other.get("label_raw") or other.get("label")
                if lab and lab not in canon["merged_label_raw"]:
                    canon["merged_label_raw"].append(lab)
                canon["merged_from"].append(other["id"])
                seen = {repr(s) for s in canon.get("sources", [])}
                for s in other.get("sources", []):
                    if repr(s) not in seen:
                        canon.setdefault("sources", []).append(s)
                        seen.add(repr(s))
            if pair["id"] not in canon["merge_ids"]:
                canon["merge_ids"].append(pair["id"])
        # re-point edges for the pairs merged in this step. Every one records
        # its INS id: same reversibility rule as the MOD merges.
        for e in edges:
            for end in ("source", "target"):
                if e[end] in ident_remap:
                    e["merged_from"] = e[end]
                    if ident_of.get(e[end]):
                        e["ins_id"] = ident_of[e[end]]
                    e[end] = ident_remap[e[end]]

    absorbed = set(remap) | set(ident_remap)
    out_nodes = [n for n in nodes if n["id"] not in absorbed]

    meta = dict(main.get("meta", {}))
    meta.update(merged=True, merges_applied=applied,
                absorbed_nodes=len(absorbed), excluded_pairs=excluded,
                nodes=len(out_nodes), edges=len(edges))
    out = {"meta": meta, "nodes": out_nodes, "edges": edges}
    # AN UNRESOLVED IDENTITY IS SAID ON THE NODE, not inferred from a
    # duplicated label: once the INS/PPL merges landed there were no
    # duplicates left, and `Reginald` — unresolved by owner decision — would
    # have lost his flag. status: unconfirmed in instructor-identity.yaml.
    unconf = {i["canonical"].strip().lower(): i["slug"]
              for i in (identities.get("identities") or [])
              if i.get("status") == "unconfirmed"}
    for n in out_nodes:
        if n["type"] == "instructor" and (n.get("label") or "").strip().lower() in unconf:
            n["identity_unconfirmed"] = unconf[n["label"].strip().lower()]
    # Here, not in pass 8: the projection and every reader call merge() in
    # memory (graphio.load_merged) and never read merged_graph.json.
    # THE CORPUS MASTERSHEET IS SUPERSEDED by the live sheet (owner decision
    # 2026-09-30): kept in the graph with its provenance, marked, never read
    # for row-B facts. Marked here for the same reason as the topics below.
    from pipeline.lib import mastersheet as _ms
    sup = {x["path"]: x for x in _ms.SUPERSEDED}
    meta["superseded_files"] = []
    for n in out["nodes"]:
        x = sup.get(n.get("relative_path"))
        if x and n.get("type") == taxonomy.edge_endpoints(taxonomy.edge_for_role("provenance"))[1]:
            n["superseded_by"] = _ms.LIVE_CITATION
            meta["superseded_files"].append(n["relative_path"])
    # EVERY FILE NODE GETS ITS OPEN LINK (B4 (i), 2026-09-30). The 74 corpus
    # files carry their Drive id in knowledge/files.json; it reached only the
    # provenance panel, so their own nodes had no link.
    files_json = KNOWLEDGE_DIR / "files.json"
    if files_json.exists():
        import json as _json
        rows = _json.loads(files_json.read_text(encoding="utf-8"))
        ids = {r["path"]: r.get("drive_file_id")
               for r in rows.get("files", []) + rows.get("failures", [])}
        file_type = taxonomy.edge_endpoints(taxonomy.edge_for_role("provenance"))[1]
        for n in out["nodes"]:
            if n.get("type") == file_type and not n.get("drive_url"):
                fid = ids.get(n.get("relative_path") or n.get("label"))
                if fid:
                    n["drive_url"] = f"https://drive.google.com/open?id={fid}"
    # CORROBORATION IS COUNTED AFTER THE MERGES (owner review 2026-09-30).
    # Pass 3 counted each spelling's files on its own and pass 7 wrote False,
    # and the survivor of a merge is whichever node has the lowest id — so
    # Robert Kreznarich (4 files) and Konstantinos Pappas (6) read "named in
    # one file only". Counted here over the merged sources, with the
    # superseded corpus copy of the mastersheet and the live sheet as ONE
    # source: they are the same workbook, and counting it twice would
    # corroborate a name with itself.
    same_as = {x["path"]: _ms.LIVE_CITATION for x in _ms.SUPERSEDED}
    for n in out["nodes"]:
        if n.get("type") != "instructor" or not n.get("sources"):
            continue
        files = {same_as.get(s["file"], s["file"])
                 for s in n["sources"] if s.get("file")}
        n["file_count"] = len(files)
        n["cross_validated"] = len(files) >= 2
    marks = classify_topics(out)
    meta["not_a_topic"] = len(marks[PERSON_NAME]) + len(marks[PERSON_BIO])
    meta["topic_marks"] = {k: len(v) for k, v in marks.items()}
    return out


# ---------------------------------------------------------------------------
# TOPIC QUALITY — D1 person content, and boilerplate ranked last
# ---------------------------------------------------------------------------
#
# Pass 7 takes slide titles as topics. Three kinds are not subjects:
#
#   not_a_topic: person_name  — the title IS or CONTAINS a known person's name
#       ("Robert Kreznarich", "Introduction – Mike Dolt", "…: @SURUCHI")
#   not_a_topic: person_bio   — an instructor-bio line ("Worked at Amazon…")
#   boilerplate: true         — housekeeping ("Agenda", "About Me", "If you can
#       hear me…"): still a topic, RANKED LAST, never removed (CLAUDE.md §4)
#
# MARKED, NOT DELETED: node, edge and provenance stay; every consumer says
# what it held back. Names come from the PUBLIC graph's own person and
# instructor labels (label, label_raw, merged_label_raw) — never from a slide —
# so nothing is inferred about who is a person. Containment is whole-word and
# only for MULTI-word names; a single first name counts only as an @mention,
# a trailing ": NAME" presenter tag or a possessive ("Tilo’s Introduction"),
# because 209 one-word labels would otherwise match ordinary words. Bio and
# boilerplate patterns are a reviewed list with examples,
# config/topic-quality.yaml, held by tests/test_topic_quality.py.
NOT_A_TOPIC = "not_a_topic"
PERSON_NAME = "person_name"
PERSON_BIO = "person_bio"
BOILERPLATE = "boilerplate"
TOPIC_QUALITY = CONFIG_DIR / "topic-quality.yaml"


def _fold(s: str) -> str:
    return " ".join(str(s or "").split()).casefold()


def load_topic_quality(path: Path | None = None) -> dict:
    data = yaml.safe_load((path or TOPIC_QUALITY).read_text(encoding="utf-8")) or {}
    return {kind: [(r["id"], re.compile(r["pattern"], re.I), r)
                   for r in (data.get(kind) or [])]
            for kind in ("person_bio", "boilerplate")}


def _known_names(g: dict) -> set:
    people_types = {taxonomy.edge_endpoints(taxonomy.edge_for_role("module_instructor"))[1],
                    taxonomy.edge_endpoints(taxonomy.edge_for_role("domain_primary"))[1]}
    names = set()
    # PUBLIC people only, so the marks are the same whichever scope is loaded:
    # a withheld name must never change what the public projection holds.
    for n in g["nodes"]:
        if n["type"] in people_types and not n.get("sensitive"):
            for x in [n.get("label"), n.get("label_raw"), *(n.get("merged_label_raw") or [])]:
                if _fold(x):
                    names.add(_fold(x))
    return names


def classify_topics(g: dict, rules: dict | None = None) -> dict:
    """Mark person content and boilerplate on topic nodes. Returns
    {mark: [ids]}; the graph is changed in place, nothing is removed."""
    rules = rules if rules is not None else load_topic_quality()
    topic_type = taxonomy.edge_endpoints(taxonomy.edge_for_role("module_topic"))[1]
    names = _known_names(g)
    multi = sorted((n for n in names if len(n.split()) >= 2), key=len, reverse=True)
    contains = re.compile("(?<!\\w)(" + "|".join(map(re.escape, multi)) + ")(?!\\w)") \
        if multi else None
    firsts = {n.split()[0] for n in names}
    out = {PERSON_NAME: [], PERSON_BIO: [], BOILERPLATE: []}
    for n in g["nodes"]:
        if n["type"] != topic_type:
            continue
        f = _fold(n.get("label"))
        mentions = re.findall(r"@([^\W\d_][\w.-]*)", f)
        # "Caching: BALAJI" — a lesson plan's presenter tag, the same thing as
        # an @mention without the @. Only as the LAST token after a colon.
        mentions += re.findall(r":\s*([^\W\d_][\w.-]*)\s*$", f)
        # "Tilo’s Introduction" — a POSSESSIVE first name is a person's slide,
        # the same thing again (owner review 2026-09-30). Straight or curly
        # apostrophe; only a known person's first name, so "Today's agenda"
        # and "Dijkstra's algorithm" stay topics.
        mentions += re.findall(r"(?<!\w)([^\W\d_][\w-]*)['\u2019]s(?!\w)", f)
        if f in names or (contains and contains.search(f)) or \
                any(m.rstrip(".") in firsts for m in mentions):
            n[NOT_A_TOPIC] = PERSON_NAME
            out[PERSON_NAME].append(n["id"])
        elif any(rx.search(f) for _, rx, _ in rules["person_bio"]):
            n[NOT_A_TOPIC] = PERSON_BIO
            out[PERSON_BIO].append(n["id"])
        if any(rx.search(f) for _, rx, _ in rules["boilerplate"]):
            n[BOILERPLATE] = True
            out[BOILERPLATE].append(n["id"])
    return {k: sorted(v) for k, v in out.items()}


def mark_person_name_topics(g: dict) -> list[str]:
    """The person-name part of classify_topics, kept for its callers."""
    return classify_topics(g)[PERSON_NAME]


def _locator_key(e: dict) -> tuple:
    for k in ("slide", "page"):
        if isinstance(e.get(k), (int, float)):
            return (0, e[k], "")
    return (1, 0, str(e.get("tab") or ""))


def rank_topics(edges: list, nodes: dict, limit: int | None = None) -> tuple[list, int]:
    """The ONE display order for a module's topics — checklist, eval and the
    client (public/index.html::topicLinks mirrors it) must agree.

    not_a_topic is held back. Then: current before historical, content before
    boilerplate (ranked LAST, never removed — CLAUDE.md §4), source rank,
    source file, locator, label. Identical titles (whitespace- and
    case-folded) show once; the graph keeps every one of them.

    Returns (rows, duplicates_folded) so a caller can SAY how many it folded."""
    ranked = sorted((e for e in edges if not nodes[e["target"]].get("not_a_topic")),
                    key=lambda e: (bool(e.get("historical")),
                                   bool(nodes[e["target"]].get(BOILERPLATE)),
                                   e.get("rank") if e.get("rank") is not None else 99,
                                   str(e.get("deck_drive_url") or ""),
                                   _locator_key(e), nodes[e["target"]]["label"]))
    seen, rows, folded = set(), [], 0
    for e in ranked:
        k = _fold(nodes[e["target"]]["label"])
        if k in seen:
            folded += 1
            continue
        seen.add(k)
        rows.append(e)
    return (rows if limit is None else rows[:limit]), folded
