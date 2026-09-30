"""NAM rows: malformed instructor labels are REPORTED, and real names are not.

The owner's three examples must be caught. The shapes CLAUDE.md §4 names as
the bias of the retired filters — credentials, bracketed nicknames, initials,
long multi-part names — must never be.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.lib import name_review                                    # noqa: E402

OWNER_EXAMPLES = ["2- Prateek", "Agentic IP Instructors", "Amrita Ray, Hemanth Pugaliya"]
REAL_NAMES = [
    "Joseph Babcock, PhD", "Kenneth Ezirim, Ph.D", "Kul Subedi, PhD, RHCE, OSCP",
    "Arushi Prakash, Ph.D.", "Dr. Raju Penmatcha", "Chuhong Mai, PhD",
    "Chetan (Chet) Kunar", "Jayaprakasam (JP) Thirunavukkarasu",
    "A. Sindhuja", "J.L.Bismarck Fuentes", "Will Yao", "Usha",
    "Venkata Satya Sai Ramakrishna Prasad",
]


@pytest.mark.parametrize("label", OWNER_EXAMPLES)
def test_the_owners_examples_are_reported(label):
    assert name_review.reasons(label), label


@pytest.mark.parametrize("label", REAL_NAMES)
def test_a_real_name_is_never_reported(label):
    assert name_review.reasons(label) == [], label


def test_the_queue_holds_them_and_changes_nothing():
    doc = yaml.safe_load((REPO / "config" / "instructor-name-review.yaml").read_text())
    labels = {r["label"] for r in doc["rows"]}
    assert set(OWNER_EXAMPLES) <= labels
    assert all(r["answer"] is None for r in doc["rows"]), "an answered row needs applying code"
    queue = (REPO / "docs" / "REVIEW-QUEUE.md").read_text(encoding="utf-8")
    for r in doc["rows"]:
        assert f"| {r['id']} | `{r['label']}` |" in queue, f"{r['id']} missing from REVIEW-QUEUE"
