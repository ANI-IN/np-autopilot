"""The crawler reads D2a's approval block and refuses when it is blank.

`docs/A7B.md` question 2: *for any constraint a document asserts, what in the
program would fail if it stopped being true?* D2a is a scope decision with
privacy consequences, and until this file existed the answer was "nothing" —
the block could be blanked and the crawler would run regardless.

Modelled on `project_graph.py`'s `--scope full` refusal, which points at
`docs/INGEST-SCOPE-REVERSAL.md`. The difference worth keeping: that refusal is
DERIVED (it queries `pg_policies` for the thing it claims is missing) rather
than asserted, so it stops refusing when the condition is met and starts again
if the condition is removed. This gate has the same shape — it reads the block
every time rather than carrying a flag somebody set once.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.lib import approval                              # noqa: E402

BLANK = """
## D2a · PROPOSED

### APPROVAL — to be completed by the corpus owner

```
Approved by:            ______________________________
Date:                   ______________________________

Scope approved:         [ ] SD1 Full Stack
                        [ ] SD2 Frontend
                        [ ] SD3 Backend Engineering
                        [ ] SD4 Test Engineering

Owners/instructors remain deferred:         [ ] confirmed
```
"""

FILLED = """
## D2a · APPROVED

### APPROVAL — to be completed by the corpus owner

```
Approved by:            A Person
Date:                   2026-09-29

Scope approved:         [x] SD1 Full Stack
                        [x] SD2 Frontend
                        [ ] SD3 Backend Engineering
                        [x] SD4 Test Engineering

Owners/instructors remain deferred:         [x] confirmed
```
"""


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "PRE-CRAWL-DECISIONS.md"
    p.write_text(body, encoding="utf-8")
    return p


def test_a_blank_block_is_refused(tmp_path):
    with pytest.raises(approval.NotApproved):
        approval.require_d2a(_write(tmp_path, BLANK))


def test_the_refusal_names_the_file_to_fill_in(tmp_path):
    """A refusal that does not say what to do is a wall, not a control."""
    with pytest.raises(approval.NotApproved, match="PRE-CRAWL-DECISIONS"):
        approval.require_d2a(_write(tmp_path, BLANK))


def test_a_filled_block_returns_the_approver_and_date(tmp_path):
    got = approval.require_d2a(_write(tmp_path, FILLED))
    assert got.approved_by == "A Person"
    assert got.date == "2026-09-29"


def test_only_ticked_domains_are_in_scope(tmp_path):
    got = approval.require_d2a(_write(tmp_path, FILLED))
    assert got.domains == ["SD1: Full Stack", "SD2: Frontend", "SD4: Test Engineering"]


def test_an_unticked_domain_is_absent_rather_than_defaulted(tmp_path):
    """Negative control. A reader that returned all four whenever the block was
    signed would pass every test above and quietly widen the scope."""
    got = approval.require_d2a(_write(tmp_path, FILLED))
    assert "SD3: Backend Engineering" not in got.domains


def test_a_signature_with_no_ticked_domain_is_refused(tmp_path):
    body = FILLED.replace("[x] SD1", "[ ] SD1").replace("[x] SD2", "[ ] SD2") \
                 .replace("[x] SD4", "[ ] SD4")
    with pytest.raises(approval.NotApproved, match="no domain"):
        approval.require_d2a(_write(tmp_path, body))


def test_the_real_document_is_approved_for_the_four_domains():
    """The live check. If somebody blanks the block, this goes red here rather
    than at the moment a crawl starts fetching."""
    got = approval.require_d2a()
    assert got.approved_by
    assert len(got.domains) == 4
