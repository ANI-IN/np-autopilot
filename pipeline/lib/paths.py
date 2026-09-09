"""Filesystem locations. The ONE place a corpus path is resolved.

Never hardcode the corpus root anywhere else — not in a pipeline script, not in
a skill, not in plugin.json. See CLAUDE.md rule 1.
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

CONFIG_DIR = REPO_ROOT / "config"
KNOWLEDGE_DIR = REPO_ROOT / "knowledge"
PIPELINE_DIR = REPO_ROOT / "pipeline"
BUILD_LOG = REPO_ROOT / "BUILD_LOG.md"

TAXONOMY_FILE = CONFIG_DIR / "taxonomy.yaml"
PEOPLE_FILE = CONFIG_DIR / "people.yaml"
WORKFLOW_OWNERS_FILE = CONFIG_DIR / "workflow-owners.yaml"
DRIVE_CONFIG = CONFIG_DIR / "drive.yaml"

#: Default corpus root. Overridden by NP_CORPUS_PATH.
DEFAULT_CORPUS_PATH = REPO_ROOT


def corpus_root() -> Path:
    """The corpus root, from NP_CORPUS_PATH or the documented default.

    Read-only by contract. Nothing in the pipeline may write beneath it.
    """
    return Path(os.environ.get("NP_CORPUS_PATH", DEFAULT_CORPUS_PATH)).resolve()


def relative_to_corpus(path: Path) -> str:
    """Corpus-relative citation string.

    Absolute paths must never reach files.json: they are meaningless on a
    teammate's machine and leak the maintainer's home directory (doc 08 Q7).
    """
    return str(Path(path).resolve().relative_to(corpus_root()))
