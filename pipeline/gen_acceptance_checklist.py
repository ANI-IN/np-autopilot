#!/usr/bin/env python3
"""Generate docs/ACCEPTANCE-CHECKLIST.md — one block per module, to check.

The owner ticks each module against the mastersheet before anything is
deployed (docs/ACCURACY-STANDARD.md §4). Per module: domain,
programme week, sessions with links, instructors with roles, assignment, deck
count, the top 5 topics with locators, and every link.

GENERATED from the merged graph — graphio.load_merged, which merges graph.json,
content_graph.json and config/module-merges.yaml in memory, as the projection
does (knowledge/merged_graph.json is a gitignored local output and is not
read) — never hand-written: a hand-maintained list goes stale on the next crawl and
nobody notices until a link is dead. tests/test_acceptance_checklist.py holds
it to the graph; tests/test_source_links.py asserts the links' own properties.

NOTHING IS CAPPED SILENTLY. Where a list is long (topics) the block says how
many there are and shows the top five by the pipeline's own ranking, which
orders and never drops (content_model.topic_rank). Every other list is whole.
"""
from __future__ import annotations

import collections
import hashlib
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.lib import graphio, taxonomy as tax                     # noqa: E402
from pipeline.lib import content_model as cm                         # noqa: E402
from pipeline.lib import module_merge as mm                          # noqa: E402
from pipeline.lib.paths import REPO_ROOT                              # noqa: E402

OUT = REPO_ROOT / "docs" / "ACCEPTANCE-CHECKLIST.md"
CONFIRMATIONS = REPO_ROOT / "config" / "owner-confirmations.yaml"

KIND_ORDER = ["pre_class", "class", "alternate_class", "task", "review",
              "alternate_review", "post_class"]
KIND_LABEL = {"pre_class": "Pre-class", "class": "Class",
              "alternate_class": "Alternate Class", "task": "Assignment",
              "review": "Assignment Review", "alternate_review": "Alt. Review",
              "post_class": "Practice problems"}
DOMAIN = {"full-stack": "SD1", "frontend": "SD2", "backend": "SD3",
          "testing": "SD4"}
ROLE_ORDER = ["primary", "backup_1", "backup_2", "backup_3"]
ROLE_LABEL = {"primary": "Primary", "backup_1": "Backup 1", "backup_2": "Backup 2",
              "backup_3": "Backup 3"}
TOPICS_SHOWN = 5


def md(s) -> str:
    """Safe inside a markdown table cell or link text. NOT stripped: a leading
    or trailing space in a file name is part of the citation key (CLAUDE.md
    §1) — ' Test Engineering Design Patterns.pptx' is that file's real name."""
    return str(s or "").replace("|", "/").replace("\n", " ")


def link(label, url, view_only=False) -> str:
    text = md(label)
    out = f"[{text}]({url})" if url else f"{text} _(no link recorded)_"
    return out + (" · _view only_" if view_only else "")


def folder_links(folders, none_text: str) -> str:
    """A module's or session's Drive folder links (pipeline/list_folders.py)."""
    if not folders:
        return f"_{none_text}_"
    return " · ".join(link("Drive folder" if f.get("where") == "content"
                           else 'Drive folder: "Uplevel shared"', f.get("url"))
                      for f in folders)


def link_counts(g) -> dict:
    """(linked, total) for the link kinds a test holds to 100%."""
    ftype = tax.edge_endpoints(tax.edge_for_role("provenance"))[1]
    files = [n for n in g["nodes"] if n["type"] == ftype]
    mods = [n for n in g["nodes"] if n["type"] == "module" and n.get("domain_slug")]
    doms = [n for n in g["nodes"] if n["type"] == "domain" and n.get("uplevel_link")]
    return {"files": (sum(bool(n.get("drive_url")) for n in files), len(files)),
            "modules": (sum(bool(n.get("drive_folders")) for n in mods), len(mods)),
            "domains": (sum(bool(n.get("drive_folder_url")) for n in doms), len(doms))}


def historical_group(files) -> str:
    """Superseded files (content_model.is_historical), collapsed, all linked."""
    body = ", ".join(link(*f) for f in files)
    return f"<details><summary>Historical ({len(files)})</summary> {body}</details>"


def artefact_group(files) -> str:
    """Test-run output and recorder config (content_model.is_build_artefact),
    collapsed but EVERY ONE still linked — display only, nothing dropped."""
    body = ", ".join(link(*f) for f in files)
    return (f"<details><summary>Build/recording artefacts ({len(files)})</summary> "
            f"{body}</details>")


def mastersheet_fingerprint(m, out, N, R) -> str:
    """What the owner confirms: the block's MASTERSHEET facts — module name,
    Uplevel links, mastersheet instructor roles. A confirmation holds only
    while these are unchanged; topics and files may be re-ranked freely."""
    facts = {
        "label": m["label"], "uplevel": m.get("uplevel_link") or "",
        "sessions": sorted([N[e["target"]].get("session_kind") or "",
                            N[e["target"]].get("uplevel_link") or ""]
                           for e in out if e["rel"] == R["module_session"]
                           and not e.get("attached_file")),
        "instructors": sorted([e.get("instructor_role") or "", N[e["target"]]["label"]]
                              for e in out if e["rel"] == R["module_instructor"]
                              and e.get("tier") == "mastersheet"),
    }
    return hashlib.sha256(json.dumps(facts, sort_keys=True, ensure_ascii=False)
                          .encode("utf-8")).hexdigest()[:16]


def load_confirmations(path: Path = CONFIRMATIONS) -> dict:
    """{module tag: entry}. Every entry is an owner fact: origin hand, who, when."""
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out = {}
    for c in data.get("confirmations") or []:
        for k in ("module", "fingerprint", "origin", "asserted_by", "asserted_at", "evidence"):
            if not c.get(k):
                raise SystemExit(f"{path.name}: confirmation {c!r} has no {k}")
        if c["origin"] != "hand":
            raise SystemExit(f"{path.name}: {c['module']} origin must be hand")
        if c["module"] in out:
            raise SystemExit(f"{path.name}: {c['module']} confirmed twice")
        out[c["module"]] = c
    return out


def owner_check(tag, fp, conf) -> tuple[str, bool]:
    c = conf.get(tag)
    if not c:
        return "- [ ] **Owner check** — this block matches the mastersheet", False
    if c["fingerprint"] != fp:
        return (f"- [ ] **Owner check** — confirmed by {c['asserted_by']} on "
                f"{c['asserted_at']}, but this block's mastersheet facts have "
                f"CHANGED since (`{c['fingerprint']}` → `{fp}`): re-check"), False
    return (f"- [x] **Owner check** — confirmed by {c['asserted_by']} on "
            f"{c['asserted_at']} ({c['evidence']}; `config/owner-confirmations.yaml`)"), True


def main() -> int:
    g = graphio.load_merged(include_sensitive=False)
    N = {n["id"]: n for n in g["nodes"]}
    OUTE, INE = collections.defaultdict(list), collections.defaultdict(list)
    for e in g["edges"]:
        OUTE[e["source"]].append(e)
        INE[e["target"]].append(e)
    R = {r: tax.edge_for_role(r) for r in (
        "module_session", "domain_module", "module_week", "module_assignment",
        "module_deck", "module_topic", "assignment_reviewed_in",
        "curriculum_module", "module_repo", "module_instructor", "module_class_file")}
    ins_type = "instructor"
    # A topic cites its source by URL; name it from the node carrying that URL.
    by_url = {}
    for n in g["nodes"]:
        if n.get("drive_url"):
            by_url.setdefault(n["drive_url"], n["label"])
    dupes = {l for l, c in collections.Counter(
        n["label"] for n in g["nodes"] if n["type"] == ins_type).items() if c > 1}

    mods = sorted((n for n in g["nodes"]
                   if n["type"] == "module" and n.get("domain_slug")),
                  key=lambda m: (m["domain_slug"], m.get("sequence") or 0))

    lines = [
        "# ACCEPTANCE CHECKLIST — one block per module",
        "",
        "**Generated by `pipeline/gen_acceptance_checklist.py` from "
        "the merged graph (`graphio.load_merged`) — the graph Phase C projects. Do not edit.**",
        "",
        "Tick each module when its block matches the mastersheet. Phase D does "
        "not start until every module is confirmed (`docs/ACCURACY-STANDARD.md` §4).",
        "",
        "- Every item shows all of its direct links. The mastersheet is never an "
        "item's link — it is the citation.",
        "- Everyone at IK has view access to these Drive folders and to Uplevel "
        "(`config/out-of-corpus-facts.yaml`). _view only_ marks a download-disabled "
        "file: it still opens.",
        "- **Programme weeks are an owner fact** (`rowb-program-weeks`, origin: "
        "hand), not read from a file, and are shown as such.",
        "- **Instructors**: the mastersheet role is the reviewed tier. Legacy "
        "evidence (a `teaches` record from the older sheets) is listed separately, "
        "never merged into it. An identity the owner has not confirmed is flagged "
        "(`docs/REVIEW-QUEUE.md`).",
        "- A tick is an owner confirmation (`config/owner-confirmations.yaml`, "
        "origin: hand). It holds only while the block's mastersheet facts are "
        "unchanged; if they change, the tick comes off and says so.",
        "- Where something is absent the reason is stated; nothing falls back to "
        "the spreadsheet.",
        "",
    ]
    summary_at = len(lines)

    tot = ok = confirmed = sfold = sfold_ok = 0
    conf = load_confirmations()
    for m in mods:
        tag = f"{DOMAIN.get(m['domain_slug'], m['domain_slug'])}/{m.get('sequence')}"
        dom = next((N[e["source"]] for e in INE[m["id"]]
                    if e["rel"] == R["domain_module"]), None)
        week = next(((N[e["target"]], e) for e in OUTE[m["id"]]
                     if e["rel"] == R["module_week"]), None)
        out = OUTE[m["id"]]

        check, ticked = owner_check(tag, mastersheet_fingerprint(m, out, N, R), conf)
        confirmed += ticked
        lines += [f"## {tag} · {md(m['label'])}", "", check, ""]

        # --- facts -----------------------------------------------------------
        decks = [e for e in out if e["rel"] == R["module_deck"]]
        superseded = [e for e in decks if e.get("superseded_by")]
        all_topics = [e for e in out if e["rel"] == R["module_topic"]]
        # D1: a person's name is not a topic (module_merge.mark_person_name_topics).
        # Held back from the count and the ranking, and SAID so below.
        not_topics = [e for e in all_topics if N[e["target"]].get("not_a_topic")]
        topics = [e for e in all_topics if not N[e["target"]].get("not_a_topic")]
        current_topics = [e for e in topics if not e.get("historical")]
        if week:
            wn, we = week
            basis = (" — owner fact (`rowb-program-weeks`), not read from a file"
                     if we.get("source_kind") == "hand" else "")
            week_txt = f"{wn.get('number', wn['label'])}{basis}"
        else:
            week_txt = "_no programme week recorded_"
        folder = (dom or {}).get("drive_folder_url") or ""
        lines += ["| | |", "|---|---|",
                  f"| Domain | {md(dom['label']) if dom else '_no domain recorded_'}"
                  + (f" — {link('Uplevel domain', dom.get('uplevel_link'))}"
                     if dom and dom.get("uplevel_link") else "")
                  + (f" · {link('Drive folder', folder)}" if folder else "") + " |",
                  f"| Programme week | {week_txt} |",
                  f"| Module | {link('Uplevel module', m.get('uplevel_link'))} · "
                  + folder_links(m.get("drive_folders"), "No Drive folder recorded") + " |",
                  f"| Decks | {len(decks)}"
                  + (f" ({len(superseded)} superseded)" if superseded else "") + " |",
                  f"| Topics | {len(current_topics)} current"
                  + (f", {len(topics) - len(current_topics)} historical"
                     if len(topics) != len(current_topics) else "") + " |",
                  ""]
        tot += 1
        ok += bool(m.get("uplevel_link"))

        # --- sessions: EVERY file, by its full name --------------------------
        sessions, attached = {}, collections.defaultdict(list)
        for e in out:
            if e["rel"] != R["module_session"]:
                continue
            n = N[e["target"]]
            if e.get("attached_file"):
                attached[e.get("session_kind") or ""].append(
                    (e["attached_file"], e.get("attached_drive_url") or "",
                     bool(e.get("attached_historical"))))
            else:
                sessions[n.get("session_kind") or "?"] = n
        lines += ["**Sessions**", "", "| session | Uplevel | Folder | Drive files |",
                  "|---|---|---|---|"]
        for k in KIND_ORDER:
            n = sessions.get(k)
            if not n:
                why = ("not offered — optional per module" if k == "post_class"
                       else "not in the mastersheet for this module")
                lines.append(f"| {KIND_LABEL[k]} | _{why}_ | — | — |")
                continue
            tot += 1
            u = n.get("uplevel_link") or ""
            ok += bool(u)
            files = sorted(attached.get(k, []))
            # EVERY FILE, BY ITS FULL NAME: a cap here once listed 193 of 653.
            # Build/recording artefacts are collapsed, still linked (display only).
            # HISTORICAL files (a superseded revamp, or named Old) get their own
            # collapsed group, never mixed with current ones (owner review 2026-09-30).
            real = [f[:2] for f in files if not cm.is_build_artefact(f[0]) and not f[2]]
            old = [f[:2] for f in files if not cm.is_build_artefact(f[0]) and f[2]]
            junk = [f[:2] for f in files if cm.is_build_artefact(f[0])]
            drive = (f"**{len(files)}:** " + ", ".join(
                link(nm, url) for nm, url in real)
                + (" " + historical_group(old) if old else "")
                + (" " + artefact_group(junk) if junk else "")) \
                if files else "_no file matched at session level_"
            sfold += 1
            sfold_ok += bool(n.get("drive_folders"))
            lines.append(f"| {KIND_LABEL[k]} | "
                         f"{link('open', u) if u else '_no Uplevel link_'} | "
                         f"{folder_links(n.get('drive_folders'), 'No folder for this session')} | "
                         f"{drive} |")
        lines.append("")

        # --- instructors ------------------------------------------------------
        ms = [(e.get("instructor_role"), N[e["target"]]) for e in out
              if e["rel"] == R["module_instructor"] and e.get("tier") == "mastersheet"
              and N[e["target"]]["type"] == ins_type]
        legacy = [N[e["source"]] for e in INE[m["id"]]
                  if N[e["source"]]["type"] == ins_type and e.get("tier") == "legacy"]
        ms.sort(key=lambda r: (ROLE_ORDER.index(r[0]) if r[0] in ROLE_ORDER else 99,
                               r[1]["label"]))
        lines += ["**Instructors — mastersheet (the reviewed tier)**", ""]
        if ms:
            lines += ["| role | instructor |", "|---|---|"]
            for role, n in ms:
                flag = (" · **unconfirmed identity** (see docs/REVIEW-QUEUE.md)"
                        if n["label"] in dupes or n.get("identity_unconfirmed") else "")
                lines.append(f"| {ROLE_LABEL.get(role, md(role) or '—')} | "
                             f"{md(n['label'])}{flag} |")
        else:
            lines.append("_no mastersheet instructor for this module_")
        lines.append("")
        if legacy:
            lines += ["_Legacy evidence, shown separately — a `teaches` record from "
                      "the older sheets, not a mastersheet role:_ "
                      + ", ".join(sorted({md(n['label']) + (' (unconfirmed identity)'
                                          if n['label'] in dupes else '')
                                          for n in legacy})), ""]

        # --- assignment ----------------------------------------------------------
        asg = sorted((N[e["target"]] for e in out if e["rel"] == R["module_assignment"]),
                     key=lambda n: n["label"])
        lines += ["**Assignment**", ""]
        if asg:
            for a in asg:
                lines.append(f"- {link(a['label'], a.get('drive_url'))}")
                for e in OUTE[a["id"]]:
                    if e["rel"] == R["assignment_reviewed_in"]:
                        rv = N[e["target"]]
                        lines.append(f"  - review: {link(rv['label'], rv.get('drive_url'))}")
        else:
            lines.append("_no assignment recorded_")
        lines.append("")

        # --- decks: every one, current first ------------------------------------
        lines += [f"**Decks ({len(decks)})**", ""]
        for e in sorted(decks, key=lambda e: (bool(e.get("superseded_by")),
                                              N[e["target"]]["label"])):
            d = N[e["target"]]
            sup = " · _superseded_" if e.get("superseded_by") else ""
            lines.append(f"- {link(d['label'], d.get('drive_url'), d.get('content_available') is False)}{sup}")
        if not decks:
            lines.append("_no deck recorded_")
        lines.append("")

        # --- top topics, with locators --------------------------------------------
        def loc(e):
            for k in ("slide", "page", "tab"):
                if e.get(k) is not None:
                    return f"{k} {e[k]}"
            return "no locator"
        # one display order, shared with eval and the client (module_merge.rank_topics)
        ranked, folded = mm.rank_topics(topics, N)
        n_boiler = sum(1 for e in topics if N[e["target"]].get("boilerplate"))
        lines += [f"**Top {min(TOPICS_SHOWN, len(ranked))} of {len(topics)} topics** "
                  "_(current first, housekeeping slides last, then by source: "
                  "curriculum, class, alternate class, pre-class, assignment, review; "
                  "ordering only — every topic is in the graph)_", ""]
        for i, e in enumerate(ranked[:TOPICS_SHOWN], 1):
            t = N[e["target"]]
            # the file's own name, not its folder path: the link carries the rest
            src = str(by_url.get(e.get("deck_drive_url"), "the source file")).rsplit("/", 1)[-1]
            lines.append(f"{i}. {md(t['label'])} — {loc(e)} of "
                         f"{link(src, e.get('deck_drive_url'))}"
                         + (" · _historical_" if e.get("historical") else "")
                         + (" · _housekeeping_" if t.get("boilerplate") else ""))
        notes = []
        if folded:
            notes.append(f"{folded} repeated title(s) shown once")
        if n_boiler:
            notes.append(f"{n_boiler} housekeeping slide(s) (agenda, welcome, "
                         "introductions…) ranked last, not removed "
                         "(`config/topic-quality.yaml`)")
        if notes:
            lines += ["", "_" + "; ".join(notes) + "._"]
        if not topics:
            lines.append("_no topics extracted_")
        if not_topics:
            lines.append("")
            held = sorted({N[e["target"]]["label"] for e in not_topics})
            lines.append(f"_{len(held)} extracted title(s) ({len(not_topics)} occurrence(s)) "
                         "held back as a person's name or biography, not a topic (D1; "
                         "kept in the graph, marked `not_a_topic`): "
                         + ", ".join(md(x) for x in held) + "_")
        lines.append("")

        # --- every other link: module files, curriculum docs, repos -------------
        other = []
        for e in out:
            if e["rel"] in (R["module_class_file"], R["module_repo"]):
                other.append(N[e["target"]])
        for e in INE[m["id"]]:
            if e["rel"] == R["curriculum_module"]:
                other.append(N[e["source"]])
        lines += [f"**Other files ({len(other)})** _(module-level files, "
                  "curriculum documents, repositories)_", ""]
        def is_junk(n):
            return n["type"] == "file" and cm.is_build_artefact(
                n["label"], n.get("path") or n.get("relative_path") or "")
        for n in sorted((n for n in other if not is_junk(n)),
                        key=lambda n: (n["type"], n["label"])):
            lines.append(f"- {n['type'].replace('_', ' ')}: "
                         f"{link(n['label'], n.get('drive_url'), n.get('content_available') is False)}")
        junk = sorted(((n["label"], n.get("drive_url"), n.get("content_available") is False)
                       for n in other if is_junk(n)))
        if junk:
            # text before the tag keeps it inline, so the links inside still render
            lines.append("- generated, collapsed: " + artefact_group(junk))
        if not other:
            lines.append("_none recorded_")
        lines += ["", "---", ""]

    lines.insert(summary_at, f"**{len(mods)} modules, {confirmed} confirmed by the owner. "
                             f"{ok} of {tot} linkable items carry an Uplevel link; the "
                             "rest state a reason.**\n")
    c = link_counts(g)
    lines.insert(summary_at + 1, "\n".join([
        "**Links** _(every count from the graph this checklist is built from)_", "",
        "| | linked | of | the rest |", "|---|---:|---:|---|",
        f"| file nodes — Open link | {c['files'][0]} | {c['files'][1]} | "
        + ("—" if c['files'][0] == c['files'][1] else "**missing — a defect**") + " |",
        f"| current modules — Drive folder | {c['modules'][0]} | {c['modules'][1]} | "
        + ("—" if c['modules'][0] == c['modules'][1] else "**missing — a defect**") + " |",
        f"| current domains — Drive folder | {c['domains'][0]} | {c['domains'][1]} | "
        + ("—" if c['domains'][0] == c['domains'][1] else "**missing — a defect**") + " |",
        f"| sessions — Drive folder | {sfold_ok} | {sfold} | "
        "_No folder for this session_ (no matching subfolder in Drive) |",
        f"| modules and sessions — Uplevel link | {ok} | {tot} | "
        + ("—" if ok == tot else "stated per row") + " |", ""]))
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  -> {OUT.relative_to(REPO_ROOT)}  ({len(mods)} modules, "
          f"{ok}/{tot} items linked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
