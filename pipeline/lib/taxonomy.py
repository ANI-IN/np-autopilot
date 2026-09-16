"""The ONLY module permitted to read config/taxonomy.yaml.

B2 hard rule. Every node-type name, edge-type name and controlled-vocabulary
string used anywhere in the pipeline comes from here. Writing one as a literal
elsewhere fails tests/test_taxonomy_single_source.py.

The reference implementation kept its topic taxonomy in two files, documented
that they must be kept in sync by hand, and shipped with them out of sync
(doc 04). This module exists so that cannot happen here.
"""
from __future__ import annotations

import functools
from typing import Any

import yaml

from .paths import TAXONOMY_FILE


@functools.lru_cache(maxsize=1)
def _raw() -> dict[str, Any]:
    with TAXONOMY_FILE.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{TAXONOMY_FILE} did not parse to a mapping")
    return data


def version() -> int:
    return _raw()["version"]


# --------------------------------------------------------------------------
# Node types
# --------------------------------------------------------------------------

def node_types() -> list[dict[str, Any]]:
    return _raw()["node_types"]


def node_type_names() -> list[str]:
    return [n["name"] for n in node_types()]


def node_type(name: str) -> dict[str, Any]:
    for n in node_types():
        if n["name"] == name:
            return n
    raise KeyError(f"unknown node type {name!r}; known: {node_type_names()}")


def expected_count(name: str) -> int | None:
    """`expect` for a node type, or None where it is deliberately unset.

    None means "not a count" — see the coverage caveat at the top of
    taxonomy.yaml. Callers must treat None as "do not assert", never as zero.
    """
    return node_type(name).get("expect")


def tolerance(name: str) -> int | None:
    return node_type(name).get("tolerance")


# --------------------------------------------------------------------------
# Edge types
# --------------------------------------------------------------------------

WILDCARD = "*"


def edge_types() -> list[dict[str, Any]]:
    return _raw()["edge_types"]


def edge_type_names() -> list[str]:
    return [e["name"] for e in edge_types()]


def edge_type(name: str) -> dict[str, Any]:
    for e in edge_types():
        if e["name"] == name:
            return e
    raise KeyError(f"unknown edge type {name!r}; known: {edge_type_names()}")


def edge_endpoints(name: str) -> tuple[str, str]:
    e = edge_type(name)
    return e["from"], e["to"]


def wildcard_edge_names() -> list[str]:
    """Edge types whose from-type is the wildcard.

    Exposed so callers — including the single-source test — never need to write
    the edge name as a literal.
    """
    return [e["name"] for e in edge_types() if e["from"] == WILDCARD]


def edge_for_role(role: str) -> str:
    """Edge-type NAME for a stable semantic role.

    Callers resolve edges through this so no edge name is ever written as a
    literal outside taxonomy.yaml and this module. Raises rather than returning
    a default: a missing role means the taxonomy and the code have diverged,
    which is the exact failure this indirection exists to prevent.
    """
    for e in edge_types():
        if e.get("role") == role:
            return e["name"]
    known = sorted(e["role"] for e in edge_types() if e.get("role"))
    raise KeyError(f"no edge with role {role!r}; known roles: {known}")


def owner_sheet_edges() -> list[tuple[str, int]]:
    """(edge_name, 1-based column) for the Domains_Courses Owners sheet.

    Lets the extractor iterate the owner columns without writing an edge name or
    a column index as a literal.
    """
    return sorted(
        ((e["name"], e["owner_sheet_column"]) for e in edge_types()
         if "owner_sheet_column" in e),
        key=lambda pair: pair[1],
    )


def has_wildcard_source(name: str) -> bool:
    """True for the one edge whose from-type cannot be checked structurally.

    Only `sourced_from` may do this. The endpoint check skips it and a separate
    rule covers it. See taxonomy.yaml, edge_types header.
    """
    return edge_type(name)["from"] == WILDCARD


# --------------------------------------------------------------------------
# Controlled vocabulary
# --------------------------------------------------------------------------

def vocabulary(name: str) -> list[str]:
    key = name if name.endswith("_vocabulary") else f"{name}_vocabulary"
    try:
        return list(_raw()[key])
    except KeyError as exc:
        raise KeyError(f"no vocabulary {key!r} in {TAXONOMY_FILE.name}") from exc


def tools() -> list[str]:
    return vocabulary("tool")


def doctypes() -> list[str]:
    return vocabulary("doctype")


def families() -> list[str]:
    return vocabulary("family")


def cadences() -> list[str]:
    return vocabulary("cadence")


def stages() -> list[str]:
    return vocabulary("stage")


def teams() -> list[str]:
    return vocabulary("team")


def seniorities() -> list[str]:
    return vocabulary("seniority")


def origins() -> list[str]:
    return vocabulary("origin")


def origin_corpus() -> str:
    """A row in a corpus file. Emits a sourced_from edge."""
    return origins()[0]


def origin_hand() -> str:
    """Out-of-corpus, entered by a person. Emits NO edge; requires `evidence`.

    Kept distinct from origin_corpus by ORDER in taxonomy.yaml rather than by a
    literal here, so the two shapes cannot drift apart in the way that let
    `hand` be documented everywhere and present nowhere.
    """
    return origins()[1]


# --------------------------------------------------------------------------
# Exclusions and assertions
# --------------------------------------------------------------------------

def excluded_files() -> list[str]:
    return [f["path"] for f in _raw().get("excluded", {}).get("files", [])]


def excluded_field_patterns() -> list[str]:
    return list(_raw().get("excluded", {}).get("fields", {}).get("patterns", []))


def is_excluded_field(header: str) -> bool:
    """Case-insensitive match on a normalised column header."""
    h = " ".join(str(header).strip().lower().split())
    return any(h == p.strip().lower() for p in excluded_field_patterns())


def validate_rules() -> list[str]:
    return [" ".join(str(r).split()) for r in _raw()["validate"]]


def out_of_corpus_sources() -> list[str]:
    """Config files allowed to provide `origin: hand` provenance."""
    return list(node_type("person").get("out_of_corpus_sources", []))
