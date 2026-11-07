"""Builds the full .md (private) and a redacted summary (public) from the JSON."""
import json, sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(r"C:\Users\Lenovo\Desktop\np-autopilot")
OUT = REPO / ".measure" / "inventory"
d = json.loads((OUT / "sheets_drive_inventory.json").read_text(encoding="utf-8"))
# header names approved as generic (set by reviewer); None => print headers for review
GENERIC = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")) if len(sys.argv) > 1 else None

FOLDER = "application/vnd.google-apps.folder"
SHORT = "application/vnd.google-apps.shortcut"
def h(n):
    for u in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024: return f"{n:,.1f} {u}"
        n /= 1024
    return f"{n:,.1f} PB"

items = d["items"]
files = [i for i in items if i["mimeType"] != FOLDER]
folders = [i for i in items if i["mimeType"] == FOLDER]
by_type = Counter(i["mimeType"] for i in files)
size_by_type = defaultdict(int)
for i in files: size_by_type[i["mimeType"]] += i["size"] or 0
total = sum(i["size"] or 0 for i in files)
mts = sorted(i["modifiedTime"] for i in items if i.get("modifiedTime"))
fail_by = Counter(f["reason"] for f in d["failures"])
link_kinds = Counter(l["kind"] for l in d["links"])
link_status = Counter(l.get("status", "not resolved") for l in d["links"])
uniq_targets = len({l.get("id") or l["raw"] for l in d["links"]})
per_root = defaultdict(lambda: Counter())
for i in items:
    per_root[i["root"]]["folders" if i["mimeType"] == FOLDER else "files"] += 1
    per_root[i["root"]]["bytes"] += i["size"] or 0

# ---------- full private md ----------
L = [f"# Sheets + Drive inventory (FULL, private)\n", f"Generated {d['generated']}. Registry source: {d['registry_source']}. Item cap {d['item_cap']}, capped: {d['capped']}.\n",
     f"Stats: {d['stats']}\n", "## Sheets\n"]
for s in d["sheets"]:
    L.append(f"### {s['label']} — {s.get('title')} (`{s['id']}`), depth {s['depth']}, links found {s['links_found']}" + (f", ERROR {s['error']}" if s.get("error") else ""))
    for t in s["tabs"]:
        L.append(f"- tab **{t['title']}**: grid {t.get('grid_rows')}x{t.get('grid_cols')}, non-empty rows {t['nonempty_rows']}, data rows {t['data_rows']}, links {t['links']}")
        L.append(f"  - headers (row {t.get('header_row')}): {t['headers']}")
    L.append("")
L.append("## Links found in sheets\n\n| sheet | tab | cell | via | kind | status | target name | raw |\n|---|---|---|---|---|---|---|---|")
lab = {s["id"]: s["label"] for s in d["sheets"]}
for l in d["links"]:
    L.append(f"| {lab.get(l['sheet'])} | {l['tab']} | {l['cell']} | {l['via']} | {l['kind']} | {l.get('status','')} | {(l.get('resolved') or {}).get('name','')} | {l['raw']} |")
L.append("\n## Linked folders\n")
for f in d["linked_folders"]:
    c = per_root.get(f["label"], Counter())
    L.append(f"- {f['label']}: {f['name']} (`{f['id']}`) from {f['from']} — {c['folders']} folders, {c['files']} files, {h(c['bytes'])}")
L.append("\n## Failures\n\n| reason | target | context | detail |\n|---|---|---|---|")
for f in d["failures"]:
    L.append(f"| {f['reason']} | {f['target']} | {f['context']} | {str(f['detail']).replace('|','/')[:200]} |")
L.append(f"\n## Folder repeats ({len(d['folder_repeats'])})\n")
for r in d["folder_repeats"]: L.append(f"- `{r['folder']}` first at {r['first_path']}, again at {r['again_path']}")
L.append("\n## Full tree\n\n| path | name | mimeType | size | modified | id |\n|---|---|---|---|---|---|")
for i in sorted(items, key=lambda x: (x["parent_path"], x["name"])):
    L.append(f"| {i['parent_path']} | {i['name']}{' [BROKEN SHORTCUT]' if i.get('shortcut_broken') else ''} | {i['mimeType']} | {i['size'] or ''} | {i.get('modifiedTime','')} | {i['id']} |")
(OUT / "sheets_drive_inventory.md").write_text("\n".join(L) + "\n", encoding="utf-8")

if GENERIC is None:
    for s in d["sheets"]:
        for t in s["tabs"]:
            print(s["label"], "|", t["title"], "|", t["headers"])
    sys.exit(0)

# ---------- redacted public md ----------
def mt_label(m):
    return {"application/vnd.google-apps.spreadsheet": "Google Sheet", "application/vnd.google-apps.document": "Google Doc",
            "application/vnd.google-apps.presentation": "Google Slides", "application/vnd.google-apps.form": "Form (Google)",
            "application/vnd.google-apps.shortcut": "Drive shortcut", "application/pdf": "PDF",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "Excel (.xlsx)",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "Word (.docx)",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation": "PowerPoint (.pptx)",
            "application/vnd.ms-excel": "Excel (.xls)", "application/vnd.ms-powerpoint": "PowerPoint (.ppt)", "application/msword": "Word (.doc)",
            "text/csv": "CSV", "text/plain": "Plain text", "application/zip": "ZIP", "application/x-zip-compressed": "ZIP",
            "application/vnd.google.colaboratory": "Colab notebook", "application/x-ipynb+json": "Jupyter notebook",
            "application/vnd.google-apps.jam": "Jamboard", "application/vnd.google-apps.drawing": "Google Drawing"}.get(m, m)
agg = Counter(); aggs = defaultdict(int)
for m, n in by_type.items(): agg[mt_label(m)] += n; aggs[mt_label(m)] += size_by_type[m]
nsheets = len(d["sheets"]); ntabs = sum(len(s["tabs"]) for s in d["sheets"]); nrows = sum(t["data_rows"] for s in d["sheets"] for t in s["tabs"])
P = ["# Sources inventory: 2026-11-07 (redacted)", "",
     "A read-only count of everything reachable from the registry Google Sheet: the sheets it links to (two levels deep) and the Drive folders it points at.",
     "Counts only. File names, folder names, people, emails, ids and URLs are left out on purpose. The full private inventory is kept in `.measure/inventory/`, which git ignores.", "",
     "## How it was gathered", "",
     "- Service account, read-only scopes (`drive.readonly`, `spreadsheets.readonly`). Nothing in Google, the database or the repo was changed.",
     "- The registry sheet id was taken from `docs/project-history/REGISTRY-INVENTORY.md` because `KB_SHEETS_ID` is empty in the local `.env`.",
     "- The Sheets API is turned off in the service account's GCP project, so each sheet was read with the Drive API's read-only xlsx export. Cell values, formulas and cell hyperlinks were scanned for links.",
     f"- Folders were walked recursively, shared drives included, with a cap of {d['item_cap']:,} items. Cap reached: **{'yes' if d['capped'] else 'no'}**.", "",
     "## Totals", "", "| Measure | Count |", "|---|---|",
     f"| Sheets opened (registry + linked) | {nsheets} ({sum(1 for s in d['sheets'] if s.get('error'))} could not be read) |",
     f"| Tabs | {ntabs} |", f"| Data rows (non-empty, below the header row) | {nrows:,} |",
     f"| Link occurrences in sheets | {len(d['links'])} ({uniq_targets} distinct targets) |",
     f"| Linked folders walked | {len({f['id'] for f in d['linked_folders']})} |",
     f"| Sub-folders found | {len(folders):,} |", f"| Files found | {len(files):,} |",
     f"| Total size (as reported by Drive) | {h(total)} |",
     f"| Modified-time range | {mts[0][:10] if mts else 'n/a'} to {mts[-1][:10] if mts else 'n/a'} |",
     f"| Folders reached by more than one path | {len(d['folder_repeats'])} |",
     f"| Access failures | {len(d['failures'])} |", "",
     "## Links by kind", "", "| Kind | Occurrences |", "|---|---|"] + [f"| {k} | {v} |" for k, v in link_kinds.most_common()] + [
     "", "## Link resolution", "", "| Status | Occurrences |", "|---|---|"] + [f"| {k} | {v} |" for k, v in link_status.most_common()] + [
     "", "## Sheets and tabs", ""]
for si, s in enumerate(d["sheets"], 1):
    P.append(f"### Sheet {si}{' (registry)' if s['depth'] == 0 else ''}, depth {s['depth']}" + (f": not readable ({s['error']})" if s.get("error") else ""))
    P.append("")
    if s["tabs"]:
        P += ["| Tab | Data rows | Columns | Links | Headers |", "|---|---|---|---|---|"]
        for ti, t in enumerate(s["tabs"], 1):
            key = f"{s['id']}|{t['title']}"
            hdr = ", ".join(x.strip() for x in t["headers"] if x.strip()) if GENERIC.get(key) else "(withheld: header row holds URLs)" if t["headers"] else "(empty)"
            hdr = " ".join(hdr.replace("|", "/").split())
            P.append(f"| Tab {ti} | {t['data_rows']:,} | {len(t['headers'])} | {t['links']} | {hdr} |")
        P.append("")
P += ["## Folders", "", f"{len(d['linked_folders'])} folder links resolved to {len({f['id'] for f in d['linked_folders']})} distinct folders. Folder numbers follow link order; a missing number is a folder already counted (the same folder linked again, or one already inside a walked folder).", "", "| Folder | Sub-folders | Files | Size |", "|---|---|---|---|"]
for f in d["linked_folders"]:
    c = per_root.get(f["label"])
    if c is None: continue
    P.append(f"| {f['label'].replace('Folder ', 'Folder ')} | {c['folders']:,} | {c['files']:,} | {h(c['bytes'])} |")
P += ["", "## Files by type", "", "| Type | Files | Size |", "|---|---|---|"] + [f"| {k} | {v:,} | {h(aggs[k])} |" for k, v in agg.most_common()]
P += ["", "## Failures by reason", "", "| Reason | Count |", "|---|---|"] + ([f"| {k} | {v} |" for k, v in fail_by.most_common()] or ["| none | 0 |"])
(REPO / "docs/operations/sources-inventory-2026-11-07.md").write_text("\n".join(P) + "\n", encoding="utf-8")
print("written")
print("fail_by", dict(fail_by))
