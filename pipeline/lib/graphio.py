"""Load the graph, which is split across two files.

DECISIONS §F.2. `knowledge/graph.json` is committed and ships with the plugin.
Its history therefore reaches every collaborator, and a personal repo has no
read-only tier — so adding a collaborator grants them everything in it.

The graph carried 277 hiring rejections about named external people and 1,625
in-pipeline candidates. Under the Q3 two-role decision those are `recruiting`
data, and the collaborators are not recruiting-cleared.

So the sensitive population lives in `knowledge/graph-sensitive.json`, which is
GITIGNORED. It is projected into Postgres behind the `recruiting` RLS policy and
never enters git.

The split is cheap because of a fact about the data: all 1,902 sensitive nodes
are instructors with `sensitive: true`, and they carry ONLY provenance edges —
zero `teaches`, zero `expert_in`. Withholding them removes no teaching or
expertise evidence, so `/staffing` answers identically either way. The split
would not have been free if that were not true, and a future change that gives a
rejected candidate a teaching edge makes it not free again — which is why
`split_graph` reports what it withholds rather than doing it silently.

Every consumer loads through here so "which half am I looking at?" has one
answer. A machine holding only the public file gets a correct smaller graph,
not a broken one.
"""
from __future__ import annotations

import json
from pathlib import Path

from .paths import KNOWLEDGE_DIR

PUBLIC = KNOWLEDGE_DIR / "graph.json"
SENSITIVE = KNOWLEDGE_DIR / "graph-sensitive.json"


def load_graph(path: Path | None = None, *, include_sensitive: bool = True) -> dict:
    """The graph, with the sensitive half merged in when it is present.

    On a machine that has only the public file — a collaborator's clone, or the
    plugin cache — this returns the public graph and says so in
    `meta.sensitive_loaded`. Callers that report counts must surface that.
    """
    public_path = Path(path) if path else PUBLIC
    g = json.loads(public_path.read_text(encoding="utf-8"))
    g.setdefault("meta", {})["sensitive_loaded"] = False

    sens_path = (public_path.parent / SENSITIVE.name
                 if path else SENSITIVE)
    if include_sensitive and sens_path.exists():
        s = json.loads(sens_path.read_text(encoding="utf-8"))
        g["nodes"] = g["nodes"] + s.get("nodes", [])
        g["edges"] = g["edges"] + s.get("edges", [])
        g["meta"]["sensitive_loaded"] = True
        g["meta"]["nodes"] = len(g["nodes"])
        g["meta"]["edges"] = len(g["edges"])
    return g


def split_graph(nodes: list[dict], edges: list[dict]) -> tuple[dict, dict]:
    """Partition into (public, sensitive) by the `sensitive` flag.

    An edge goes with the sensitive half if EITHER endpoint is sensitive, so the
    public file never holds a dangling reference.
    """
    sensitive_ids = {n["id"] for n in nodes if n.get("sensitive")}
    pub_nodes = [n for n in nodes if not n.get("sensitive")]
    sen_nodes = [n for n in nodes if n.get("sensitive")]
    pub_edges, sen_edges = [], []
    for e in edges:
        if e["source"] in sensitive_ids or e["target"] in sensitive_ids:
            sen_edges.append(e)
        else:
            pub_edges.append(e)
    return ({"nodes": pub_nodes, "edges": pub_edges},
            {"nodes": sen_nodes, "edges": sen_edges})


def content_hash(g: dict) -> str:
    """Hash of nodes+edges across BOTH halves. Excludes meta.

    ORDER-INDEPENDENT. The graph is now assembled from two files, so the
    concatenation order is an artefact of how it was loaded, not of what it
    contains — hashing the raw lists made an unchanged graph hash differently
    purely because the sensitive half was appended rather than interleaved.

    Nodes sort by id. Edges have no id, so they sort by their own canonical
    JSON, which is total and stable.

    The version lock has to cover the whole graph: a change confined to the
    withheld half is still a change the plugin build depends on.
    """
    import hashlib
    nodes = sorted(g["nodes"], key=lambda n: n["id"])
    edges = sorted(json.dumps(e, sort_keys=True, separators=(",", ":"))
                   for e in g["edges"])
    payload = json.dumps(
        {"nodes": [json.dumps(n, sort_keys=True, separators=(",", ":"))
                   for n in nodes],
         "edges": edges}, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()
