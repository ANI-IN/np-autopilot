---
description: What the graph is missing — programs without a domain, modules without an instructor, isolated records, unread sheets.
---

Run `python3 ${CLAUDE_PLUGIN_ROOT}/pipeline/query.py coverage` and present the result.

## Two things this command must never report

**1 · Never report 92 workflows as "missing an owner."** Workflow-level ownership
does not exist in New Programs — everyone does every kind of work, and each
person coordinates with SMEs across development, live class, ARS and RCA. There
is no per-workflow owner to record. Reporting it as a gap presents a correct
state as a defect and invites someone to fix it by inventing data. The
`workflow_ownership` field says this; pass it through.

**2 · Never report Android or iOS as lacking teaching evidence.** They have no
instructors — owner-confirmed, out-of-corpus, not a data gap. They appear in
`excluded_from_report_by_owner_confirmation` for exactly this reason.

## What to report

- `programs_without_domain` (14) — abbreviation or typo mismatches, deliberately
  unjoined rather than spell-corrected.
- `modules_without_program`, `modules_without_instructor`
- `domains_without_owner` — currently **0**, which is worth saying plainly.
- `isolated_records` — real records no file connects to anything.
- **Sheet coverage: 127 of 374 worksheets read.** The genuine blind spot is 71
  sheets / 4,572 rows; the rest is the excluded payroll file and learner data.

Always state that `person`, `instructor` and `module` counts are **floors over a
subset of sheets**, never totals.
