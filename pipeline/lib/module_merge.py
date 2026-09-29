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

import copy
from pathlib import Path
from typing import Any

import yaml

from . import taxonomy
from .paths import CONFIG_DIR

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
        canon["label"] = ident["canonical"]
        canon.setdefault("merged_label_raw", [])
        canon.setdefault("merged_from", [])
        canon.setdefault("merge_ids", [])
        for other in group:
            if other["id"] == canon["id"]:
                continue
            ident_remap[other["id"]] = canon["id"]
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
                e[end] = ident_remap[e[end]]

    absorbed = set(remap) | set(ident_remap)
    out_nodes = [n for n in nodes if n["id"] not in absorbed]

    meta = dict(main.get("meta", {}))
    meta.update(merged=True, merges_applied=applied,
                absorbed_nodes=len(absorbed),
                nodes=len(out_nodes), edges=len(edges))
    return {"meta": meta, "nodes": out_nodes, "edges": edges}
