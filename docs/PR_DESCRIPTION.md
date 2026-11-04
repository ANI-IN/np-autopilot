# PR: the IK knowledge platform (`auto/knowledge-platform-20261102` → `main`)

**Do not merge without review.** Not opened by the agent. Rollout:
[docs/GO_LIVE.md](GO_LIVE.md).

## Summary

The knowledge base at `/kb/` becomes IK's single source of truth for programs,
courses, domains, modules, sessions, people and links. The NP Autopilot
pipeline keeps writing its old tables, and a scheduled one-way sync brings them
into the KB. Every view reads the KB, including the NP Autopilot map at `/`,
and updates live: the Graph page, Outline, Who teaches what, Program timeline
and Activity. Access is limited to IK accounts, checked on the server on every
request. Roles go from viewer to admin and are enforced in the database. The
owner-approved legacy cleanup removes 42 legacy domains and 904 legacy modules.

86 commits, 519 files; runs 2–6 (see HANDOFF.md, PROGRESS.md).

## Changes, grouped

- **Knowledge base workspace (runs 2–3):** records and relationships with
  custom record and relationship types, links, tags, owners, templates,
  approvals, saved views, Activity, Data quality, a ⌘K palette, the Guide, and
  an MCP server and Claude plugin.
- **Data from NP Autopilot (runs 4–5):**
  - The import, then a scheduled, incremental, locked one-way sync
    (`web/lib/kb/sync.py`). It never overwrites a KB edit (that becomes a
    conflict) and flags rows removed at the source.
  - Parity with NP Autopilot's own legacy and role rules (docs/PARITY_REPORT.md).
  - Owners derived from roles (P → owner, B1–B3 → co-owners).
- **One source of truth (run 6):**
  - The "/" map's routes read the KB (`web/lib/kb/npmap.py`), keeping their
    response shapes. `NP_MAP_SOURCE=old` is the rollback.
  - `GET /api/kb/graph` is the one graph API.
  - The change feed carries `kind` and `node_ids`, and every page updates
    within ~3 s. docs/run6/MATRIX.md covers 26 operations on both pages.
- **Graph (run 6):**
  - Layouts: a hierarchy by default, plus force, radial and saved positions.
  - Grouping and bundles.
  - Navigation: legend-as-filter, breadcrumbs, focus mode, search-jump,
    minimap, no overlapping labels, and a shortcut sheet.
  - Leaving the page releases its memory.
- **UI (run 6):**
  - Every screen reviewed at 1280–2560 px in both themes, with WCAG AA contrast.
  - Interview Kickstart's brand colours and logo, taken from interviewkickstart.com.
  - A one-screen dashboard.
  - Navigation fixes and bookmark aliases.
- **People and roles (run 6):**
  - Owners can be linked to real people: CSV upload with match preview, linking
    at sign-in, and "Claim this profile".
  - Members can be invited by IK e-mail before their first sign-in.
  - The last admin can't be removed.
  - Contributors' field edits go to Approvals, enforced in the database.
- **Security (run 6):**
  - The IK domain is checked on every request; security headers are set on
    every response.
  - An access sweep covers every route × 6 caller types.
  - The AI assistant's token can't grant roles or permanently delete.
  - The sync and the UI share one validation layer.
  - docs/run6/SECURITY_SWEEP.md and AUDIT_FINDINGS.md.
- **Performance (run 6):**
  - Data quality: 29 s → 0.05 s.
  - Every screen is interactive in 0.26–0.74 s on real data.
  - Graph expand: p95 48 ms.
  - Heap: bounded over 50 graph openings.
- **Legacy (run 6):**
  - Code: removals backed by evidence (docs/LEGACY_REMOVAL.md).
  - Data: permanent deletion with export and restore
    (`pipeline/kb_legacy_delete.py`). The sync exclusions (0037) stop the
    deleted records coming back.
- **Docs:** README (rewritten), ARCHITECTURE, CONTRACTS, GO_LIVE,
  VISION_AND_ROADMAP, DEV_DEPLOY, SCHEMA, DESIGN_SYSTEM.

## Migrations (production is at 0021)

| # | What | Rollback |
|---|---|---|
| 0022–0026 | kb schema, RLS, import runs, API-token resolution, course shape, link health, people | `.down.sql` each |
| 0027–0029 | custom types, palette and Realtime, Activity and relationship-type review | `.down.sql` each (refuses while dependent data exists) |
| 0030 | sync map and runs, owners by role, person accounts, legacy archive | `.down.sql` |
| 0031 | pg_cron + pg_net schedule (owner-only install/remove) | `.down.sql` |
| 0032 | contracts: type shapes, owner expected, relationship colours and line styles, change kinds | `.down.sql` |
| 0033 | data flow and people: e-mail on people, claims, contributor proposals enforced, owner expected | `.down.sql` |
| 0034 | edge-end indexes; guards (the AI cannot grant roles or delete; the last admin stays) | `.down.sql` |
| 0035 | member invitations (IK-only; the audit row has no e-mail address) | `.down.sql` |
| 0037 | sync exclusions (the deleted legacy records never come back) | `.down.sql` (refuses while in use; restore first) |

There is no migration 0036; the number was reserved and not needed. Every
migration is additive. On dev, 0032–0037 went down to 0031 and back up again;
in run 5 the whole chain did.

## Testing

- `scripts/verify_all.sh` (the full suite on the local stack): see "Final
  verification" in HANDOFF.md for the numbers of the last run. The bar is zero
  new failures against `main`'s 43 baseline failures (docs/baseline-failures.txt).
- Change-propagation matrix (browser, Graph page and "/"): 26 of 26 operations,
  slowest 2.6 s.
- Section 7 workflows on the real-data copy (`eval/kb_workflow_check.py`):
  26 of 26 steps.
- Access sweep: every route × anonymous, non-IK, viewer, contributor, editor,
  admin.
- Dashboard on one screen at 1536×730 and 1920×1080 (`eval/kb_fit_check.py`).
- Zero console errors on every screen and flow (`tests/test_kb_console_run6.py`).
- Dev rehearsal: migrations, legacy deletion, sync, parity equal to the local
  copy (`scripts/dev_db.py verify`).

## Risks

- **The "/" map now reads the KB.** Files are no longer drawn as nodes, and
  legacy domains and modules are gone from it. The rollback is
  `NP_MAP_SOURCE=old`.
- **The legacy deletion is permanent once run on production** (GO_LIVE step 6).
  Its export and restore are rehearsed.
- **The sync on Vercel is unmeasured in region.** On dev from a laptop it took
  24 s; batches resume, the budget is 10 s and `maxDuration` is 60 s.
- **The preview deploy wasn't rehearsed:** the Vercel token in `.env` was
  rejected (GO_LIVE steps 8–11 are documented, not run).
- **One known test-isolation defect:** two graph tests hang when run back to
  back in one process; each passes alone (PROGRESS.md).

## Rollout

Follow [docs/GO_LIVE.md](GO_LIVE.md): backup → migrations → first import
(operator) → legacy step → legacy deletion → sync → Production variables →
deploy → smoke tests → schedule → admins → people.
