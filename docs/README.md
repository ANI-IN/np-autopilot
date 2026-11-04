# Documentation

Everything about the IK New Programs knowledge platform, grouped by what you
want to do. New here? Read the [README](../README.md), then
[architecture/overview.md](architecture/overview.md), then
[workflows/crud-and-change-propagation.md](workflows/crud-and-change-propagation.md).

## Architecture: how it is built

| Document | What it covers |
|---|---|
| [architecture/overview.md](architecture/overview.md) | System context and components: users, the app, Supabase, Vercel, the pipeline, Google sign-in, MCP and Claude |
| [architecture/single-source-of-truth.md](architecture/single-source-of-truth.md) | The data flow: pipeline → intake tables → sync → `kb` → every UI |
| [architecture/data-model.md](architecture/data-model.md) | Entity-relationship diagrams of the `kb` schema and the intake tables, and how they map |
| [architecture/knowledge-graph.md](architecture/knowledge-graph.md) | The hierarchy, relationship types (including custom ones), current vs legacy, how the graph loads |
| [architecture/contracts.md](architecture/contracts.md) | The API contracts: `GET /api/kb/graph`, the change feed, type styles |
| [architecture/schema.md](architecture/schema.md) | The database schema in detail |
| [architecture/auth.md](architecture/auth.md) | Authentication in detail: Google, Supabase Auth, the domain hook, sessions |
| [architecture/import-mapping.md](architecture/import-mapping.md) | Every rule that maps the pipeline's tables and the sheets into `kb` |
| [architecture/design-system.md](architecture/design-system.md) | The UI's tokens, components, brand and accessibility rules |

## Workflows: how things happen

| Document | What it covers |
|---|---|
| [workflows/crud-and-change-propagation.md](workflows/crud-and-change-propagation.md) | A UI action through validation, the database, the audit log and the change feed to every open page |
| [workflows/sync.md](workflows/sync.md) | The scheduled one-way sync: lock, batches, conflicts, legacy exclusion, run log |
| [workflows/authentication-and-authorisation.md](workflows/authentication-and-authorisation.md) | Sign-in, the domain check on every request, roles, RLS, invited members |
| [workflows/approvals.md](workflows/approvals.md) | Contributor proposals, relationship-type review, profile claims |
| [workflows/owner-linking.md](workflows/owner-linking.md) | People and sign-in accounts: CSV upload, linking at sign-in, claims, owners from roles |
| [workflows/legacy-deletion-and-restore.md](workflows/legacy-deletion-and-restore.md) | The permanent legacy deletion: plan, export, delete, restore |
| [workflows/mcp-and-claude.md](workflows/mcp-and-claude.md) | A Claude tool call from the token to the service layer and the audit log |

## Operations: running it

| Document | What it covers |
|---|---|
| [operations/deployment.md](operations/deployment.md) | Deploying: local, dev and preview, production; variables, Supabase Auth, pooling, the scheduled sync |
| [operations/dev-deploy.md](operations/dev-deploy.md) | The DEV database and the Vercel preview, step by step |
| [operations/GO_LIVE.md](operations/GO_LIVE.md) | The production go-live runbook, timed on dev, with a rollback per step |
| [operations/environment-variables.md](operations/environment-variables.md) | Every variable: purpose, required or optional, where it is set (names only) |
| [operations/backups-and-restore.md](operations/backups-and-restore.md) | Backups, restores and the legacy-deletion exports |
| [operations/monitoring-and-troubleshooting.md](operations/monitoring-and-troubleshooting.md) | What to watch, and what to check for common symptoms |
| [operations/runbook.md](operations/runbook.md) | Incidents: a failing sync, a migration rollback, a token rotation, a leaked secret |
| [operations/testing.md](operations/testing.md) | The local stack, the suites, browser tests on 16 GB, production-only tests, the skip ledger |
| [operations/local-demo.md](operations/local-demo.md) | The demo server and the local real-data copy |
| [operations/legacy-removal.md](operations/legacy-removal.md) | Legacy code removed (with evidence) and what to remove after go-live |
| [operations/window-runsheet.md](operations/window-runsheet.md) | The September 2026 launch window: migrations, deploy, projection in one sitting |
| [operations/risk-register.md](operations/risk-register.md) | The risk register (the R-numbers that controls and hooks cite) |

## Security

| Document | What it covers |
|---|---|
| [security.md](security.md) | The access model, a role-by-action permission matrix, how secrets are handled |
| [../SECURITY.md](../SECURITY.md) | How to report a problem; the short policy |

## Integrations: extending it

| Document | What it covers |
|---|---|
| [integrations/connectors.md](integrations/connectors.md) | The connector framework, and how to add Google Drive, Uplevel and Atlassian |
| [integrations/mcp.md](integrations/mcp.md) | The MCP server and the Claude plugin |
| [integrations/http-api.md](integrations/http-api.md) | The HTTP API |
| [VISION_AND_ROADMAP.md](VISION_AND_ROADMAP.md) | Where the platform goes next, with the prioritised roadmap |

## The pipeline's decision records

These belong to the intake pipeline. Code and tests read several of them, so
they stay at these paths.

| Document | What it covers |
|---|---|
| [DECISIONS.md](DECISIONS.md) | The main decision record (cited by migrations and tests) |
| [PRE-CRAWL-DECISIONS.md](PRE-CRAWL-DECISIONS.md) | The content-crawl approvals; `pipeline/lib/approval.py` reads its approval block |
| [A7B.md](A7B.md) | "Silence that looks like success": the failure pattern behind the guards in the pipeline and sign-in |
| [CONTACT-DATA.md](CONTACT-DATA.md) · [CACHE-EXPOSURE.md](CACHE-EXPOSURE.md) | What personal data is kept out, and why |
| [DEFAULT-VIEW.md](DEFAULT-VIEW.md) | The map's default view (owner decisions D1–D3) |
| [ACCURACY-STANDARD.md](ACCURACY-STANDARD.md) · [ACCEPTANCE-CHECKLIST.md](ACCEPTANCE-CHECKLIST.md) | The accuracy standard and the generated acceptance checklist |
| [REVIEW-QUEUE.md](REVIEW-QUEUE.md) | The review queue of naming decisions, answered by ID |
| [baseline-failures.txt](baseline-failures.txt) | `main`'s known failing tests; `scripts/verify_all.sh` compares every run against it |
| [../pipeline/README.md](../pipeline/README.md) | Every pipeline script and its variables |

## Project history

[project-history/](project-history/README.md): the timeline, the latest
[HANDOFF](project-history/HANDOFF.md), the run log, the PR description, and
past decisions and design documents.
