"""GET /api/staffing?domain= — tiers computed in PYTHON, never by ORDER BY.

DECISIONS §C.2: the tiering is not a sort. It is a partition into named evidence
classes that must never merge, and an ORDER BY cannot express "these are
different kinds of evidence and merging them is the worst failure this system
can produce". The database returns raw rows; the partition happens here.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import data                                                   # noqa: E402
from lib.guard import serve                                            # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline.lib import teaching                                      # noqa: E402
from pipeline.lib.resolve import Ambiguous, resolve as resolve_name     # noqa: E402


def _staffing(conn, identity, params):
    query = (params.get("domain") or "").strip()
    if not query:
        return {"error": "domain is required"}, 0

    with conn.cursor() as cur:
        cur.execute("select label from nodes where type = 'domain'")
        labels = [r[0] for r in cur.fetchall()]
    # Ambiguity is RETURNED, never picked. Three bugs in this project came from
    # collapsing several plausible targets to the first one.
    match = resolve_name(query, labels)
    if isinstance(match, Ambiguous):
        return match.as_dict(), 0
    if match is None:
        return {"error": f"no domain matching {query!r}", "known": sorted(labels)}, 0

    sub = data.domain_subgraph(conn, match)
    if not sub.get("domain"):
        return {"error": "not_found"}, 0

    taught = {}
    for row in sub["taught"]:
        rec = taught.setdefault(row["label"], {"name": row["label"], "modules": set(),
                                               "past": 0, "scheduled": 0,
                                               "last_taught": None})
        rec["modules"].add(row["module"])
        counts = teaching.sessions((row["edge_props"] or {}).get("class_dates"))
        rec["past"] += counts["past"]
        rec["scheduled"] += counts["scheduled"]
        if counts["last_taught"] and (rec["last_taught"] or "") < counts["last_taught"]:
            rec["last_taught"] = counts["last_taught"]
    tier1 = sorted(taught.values(),
                   key=lambda r: (r["last_taught"] or "", r["past"]), reverse=True)
    for r in tier1:
        r["modules"] = sorted(r["modules"])

    # Declared tiers stay SEPARATE, and a name with teaching history never
    # appears in one — that is how a form response gets laundered into evidence.
    taught_names = {r["name"] for r in tier1}
    tiers: dict[str, list] = {}
    for row in sub["declared"]:
        if row["label"] in taught_names:
            continue
        props = row["edge_props"] or {}
        key = props.get("basis", "unknown") + ("+via_alias" if props.get("via_alias") else "")
        tiers.setdefault(key, []).append({"name": row["label"],
                                          "subject_raw": props.get("subject_raw")})
    return {
        "domain": sub["domain"]["label"],
        "taught": tier1,
        "declared": {k: sorted(v, key=lambda r: r["name"]) for k, v in tiers.items()},
        "tier_note": ("Taught = ran the class. Declared = a subject field, mostly "
                      "a Google Form response, and NOT evidence of capability. "
                      "These are never merged."),
    }, len(tier1)


handler = serve("staffing", _staffing)
