# ROADMAP — KB knowledge platform

Ordered by value. Items marked **(owner)** need a human decision or credential.

## Next session — recommended 5

1. **Apply 0022–0026 to a dev Supabase project, then production** (owner; HANDOFF
   §Action 2), bootstrap admins with `pipeline/kb_admins.py`, smoke-test `/kb/`
   on a Vercel preview.
2. **Run the Sheets import against the real workbook** (owner supplies the sheet
   id and shares it read-only with the service account): adjust tab/header
   names in `config/kb-sheets-mapping.yaml`, dry-run, review, apply on dev.
3. **Remote MCP with per-user OAuth** for Claude.ai (docs/AI_ARCHITECTURE.md §1).
4. **Duplicate adoption flow**: for import rows flagged `duplicate`, a UI to link
   the sheet row to the existing app record (sets `external_id`) — one click per
   record, never automatic (CLAUDE.md §4: rank or warn, never silently pick).
5. **Presence indicators + Supabase Realtime** (replaces 4-second polling):
   needs `connect-src` for the Supabase realtime host in the CSP and
   supabase-js vendored; private channels per record with RLS-backed
   authorisation.

## Then

- Saved views (persist list filters per user: `kb.saved_views(user_id, name,
  route, query jsonb)`).
- Bulk edit (multi-select in the list: tag, move scope, propose archive) and CSV
  **import** (export exists) reusing the Sheets staging/validation pipeline with a
  CSV reader.
- Stored link-health results (`kb.link_checks`) so the quality page shows broken
  links without an MCP call; a nightly job (AI_ARCHITECTURE §2).
- Edge editing beyond notes (change type) and drag-to-connect in the graph.
- Projection → KB bridge: optionally seed KB programs/domains/modules from the
  pipeline's public projection (read-only source), with `external_id =
  'projection:<node id>'` and the same conflict rule.
- Windows portability of the existing suite (12 env failures) and the
  `project_graph.py` fresh-DB failure (`corpus_names_a_file`) — see AUDIT.

## Deferred to design (docs/AI_ARCHITECTURE.md)

Workflow builder, event-driven agents, multi-LLM orchestration, Graph RAG, the
remaining plugins, Drive integration beyond link storage, notifications. No code
exists for these by design.

## Broader readings of items built narrowly

- "Courses/programs as first-class" → built as container node types with their
  own pages; separate tables only if they gain fields nothing else has.
- "Realtime" → built as an RLS-scoped change feed; see item 5.
- "Hard delete" → admin-only, archived-only, API + UI; no bulk purge.
