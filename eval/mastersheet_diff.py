"""Diff every mastersheet-derived fact between two copies of the sheet.

    python3 eval/mastersheet_diff.py OLD.xlsx NEW.xlsx

Owner request (2026-09-30, checklist review part 3 §4): before the live sheet
replaces the corpus copy, show EVERY fact that would change — modules,
sessions, Uplevel links, instructors and roles, red-highlighted instructor
cells, the instructor table, the four Uplevel Resources rows.

CONTACT FIELDS ARE COUNTED, NEVER PRINTED: per column, how many people's
value was added, removed or changed. A red cell outside the role columns is
counted too, not shown — the instructor table below the role block holds
contact columns.

Read-only: both files are opened read_only through pipeline/lib/mastersheet.py,
so only the declared tabs are ever read (config/mastersheet-scope.yaml).
"""
from __future__ import annotations

import collections
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.lib import mastersheet as ms                            # noqa: E402

TAG = {"Full Stack Engineering": "SD1", "Frontend Engineering": "SD2",
       "Backend Engineering": "SD3", "Test Engineering": "SD4"}


def facts(path: Path) -> dict:
    out = {"excluded": [t for t, _ in ms.check_workbook_scope(ms.sheetnames(path))],
           "uplevel_resources": ms.uplevel_resources(path)}
    for tab in ms.DOMAIN_TABS:
        t = ms.parse_tab(path, tab)
        red = ms.red_cells(path, tab)
        block_rows = {v["row"]: seq for seq, v in t.assignments_by_sequence.items()}
        red_roles, red_other = set(), 0
        for (r, c), val in red.items():
            if r in block_rows and c in ms.ROLE_COLUMNS:
                red_roles.add((block_rows[r], ms.ROLE_COLUMNS[c], val.strip()))
            else:
                red_other += 1
        people_pub, people_priv, unusable = {}, {}, 0
        for rec in t.instructors:
            pub, priv = ms.split_instructor_row(rec)
            if ms.is_unusable(pub):
                unusable += 1
                continue
            key = pub["name"].strip()
            people_pub[key] = {k: str(v).strip() for k, v in pub.items() if k != "name"}
            people_priv[key] = {k: str(priv.get(k) or "").strip() for k in ms.SENSITIVE_FIELDS}
        out[tab] = {
            "drive_folder": (t.drive_folder, t.drive_folder_url),
            "modules": {m.sequence: (m.name, m.uplevel_link) for m in t.modules},
            "sessions": {(m.sequence, s.kind, s.name): (s.resource_type, s.uplevel_link)
                         for m in t.modules for s in m.sessions},
            "session_counts": collections.Counter((m.sequence, s.kind, s.name)
                                                  for m in t.modules for s in m.sessions),
            "roles": {(seq, role, p) for seq, v in t.assignments_by_sequence.items()
                      for role in ms.ROLE_COLUMNS.values() for p in v[role]},
            "red_roles": red_roles, "red_other": red_other,
            "people": people_pub, "contact": people_priv, "unusable": unusable,
        }
    return out


def main(argv) -> int:
    old, new = facts(Path(argv[1])), facts(Path(argv[2]))
    n = 0

    def say(line):
        nonlocal n
        n += 1
        print("  " + line)

    print("=" * 96)
    print(f"MASTERSHEET DIFF\n  old: {argv[1]}\n  new: {argv[2]}")
    print("=" * 96)
    if old["excluded"] != new["excluded"]:
        say(f"excluded tabs: {old['excluded']} -> {new['excluded']}")
    for dom in sorted(set(old["uplevel_resources"]) | set(new["uplevel_resources"])):
        a, b = old["uplevel_resources"].get(dom), new["uplevel_resources"].get(dom)
        if a != b:
            say(f"Uplevel Resources · {dom}: {a} -> {b}")

    for tab in ms.DOMAIN_TABS:
        o, w, tag = old[tab], new[tab], TAG[tab]
        print(f"\n--- {tab} ({tag}) " + "-" * (80 - len(tab)))
        if o["drive_folder"] != w["drive_folder"]:
            say(f"drive folder: {o['drive_folder']} -> {w['drive_folder']}")
        for seq in sorted(set(o["modules"]) | set(w["modules"])):
            a, b = o["modules"].get(seq), w["modules"].get(seq)
            if a is None or b is None:
                say(f"{tag}/{seq} module {'ADDED' if a is None else 'REMOVED'}: {b or a}")
            else:
                if a[0] != b[0]:
                    say(f"{tag}/{seq} module name: {a[0]!r} -> {b[0]!r}")
                if a[1] != b[1]:
                    say(f"{tag}/{seq} module Uplevel link: {a[1]} -> {b[1]}")
        for k in sorted(set(o["sessions"]) | set(w["sessions"])):
            a, b = o["sessions"].get(k), w["sessions"].get(k)
            seq, kind, name = k
            if a is None:
                say(f"{tag}/{seq} session ADDED [{kind}] {name!r} -> {b[1]}")
            elif b is None:
                say(f"{tag}/{seq} session REMOVED [{kind}] {name!r} (was {a[1]})")
            elif a != b:
                if a[0] != b[0]:
                    say(f"{tag}/{seq} session [{kind}] {name!r} type: {a[0]!r} -> {b[0]!r}")
                if a[1] != b[1]:
                    say(f"{tag}/{seq} session [{kind}] {name!r} link: {a[1]} -> {b[1]}")
        for k in sorted(set(o["session_counts"]) | set(w["session_counts"])):
            if o["session_counts"][k] != w["session_counts"][k]:
                say(f"{tag}/{k[0]} session [{k[1]}] {k[2]!r} occurs "
                    f"{o['session_counts'][k]} -> {w['session_counts'][k]} times")
        for seq, role, p in sorted(o["roles"] - w["roles"]):
            say(f"{tag}/{seq} {role}: - {p}")
        for seq, role, p in sorted(w["roles"] - o["roles"]):
            say(f"{tag}/{seq} {role}: + {p}")
        for seq, role, p in sorted(o["red_roles"] - w["red_roles"]):
            say(f"{tag}/{seq} {role} {p}: no longer red")
        for seq, role, p in sorted(w["red_roles"] - o["red_roles"]):
            say(f"{tag}/{seq} {role} {p}: now RED")
        if o["red_other"] != w["red_other"]:
            say(f"red cells outside the role columns (not shown): "
                f"{o['red_other']} -> {w['red_other']}")
        for name in sorted(set(o["people"]) | set(w["people"])):
            a, b = o["people"].get(name), w["people"].get(name)
            if a is None or b is None:
                say(f"instructor table: {name!r} {'ADDED' if a is None else 'REMOVED'}")
                continue
            for f in sorted(set(a) | set(b)):
                if a.get(f, "") != b.get(f, ""):
                    say(f"instructor table: {name!r} {f}: {a.get(f, '')!r} -> {b.get(f, '')!r}")
        if o["unusable"] != w["unusable"]:
            say(f"instructor-table rows with no usable name: {o['unusable']} -> {w['unusable']}")
        # CONTACT: counts only, per column. Never a value.
        counts = collections.Counter()
        for name in set(o["contact"]) & set(w["contact"]):
            for f in ms.SENSITIVE_FIELDS:
                a, b = o["contact"][name][f], w["contact"][name][f]
                if a != b:
                    counts[(f, "added" if not a else "removed" if not b else "changed")] += 1
        for (f, how), c in sorted(counts.items()):
            say(f"contact column {f}: {c} value(s) {how} (values not shown)")
        if not counts:
            print("  contact columns: 0 changes among people present in both")

    print("\n" + "=" * 96)
    print(f"  {n} changed fact(s)")
    print("=" * 96)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
