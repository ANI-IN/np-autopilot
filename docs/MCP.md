# MCP server — IK Knowledge Base

`mcp_server/kb_server.py` (Python MCP SDK, FastMCP). Transports: **stdio**
(default) and **streamable HTTP** (`--http --port 8808`, binds 127.0.0.1).

## How it works

- A **thin client of `/api/kb/*`**. Every tool is one or two HTTP calls into the
  same service layer the web app uses (`web/lib/kb/service.py`). No SQL and no
  business rules live in the MCP server.
- **Auth = a per-user API token** (`ikkb_…`), minted in the KB app under
  Settings → API tokens, shown once, stored only as a SHA-256. The API resolves it
  to its owner (`kb.resolve_token`, migrations 0023/0025) and runs the request
  **as that user under RLS**. A viewer's token can only read.
- Every token request is attributed **`actor_type = 'ai'`** in `kb.audit_log`.
- **Archive/delete never execute**: with an AI actor, the service records a
  proposal and returns `approval_required` + `proposal_id`; an editor approves or
  rejects it in the app (Approvals). An AI actor cannot approve proposals or mint
  tokens.
- Expired or revoked tokens are refused (`token was rejected`).
- No database credential is needed or accepted by the MCP server.
- Every result is `{"data_notice", "result", "sources"}`: retrieved text is
  **data, not instructions**, and `sources` lists app links
  (`<KB_APP_URL>/kb/#/records?open=<id>`) and resource URLs.

## Tools

| Group | Tool | Notes |
|---|---|---|
| Read | `search_knowledge(query, types?, limit?)` | full-text + trigram; resources by title/URL |
| | `get_node(node_id)` | relationships in/out, resources, tags |
| | `get_course(course)` / `get_program(program)` | by id or name |
| | `get_related_resources(node_id, include_neighbours?)` | |
| | `traverse_relationships(node_id, depth 1-2, types?)` | ≤300 nodes, reports `total`/`truncated` |
| | `find_instructors(course_id?, query?)` | names only — no contact data exists |
| Write | `create_node(type, name, summary?, scope_id? \| new_scope_type+new_scope_name)` | inline course/program creation |
| | `update_node(node_id, version, …)` | stale version → conflict error naming the current version |
| | `create_edge(type, source_id, target_id, note?)` | type rules, self-edge and duplicate checks |
| | `attach_resource(node_id, url+title \| resource_id, kind?, note?)` | an existing URL is reused |
| | `create_course(name, summary?, program_id?)`, `create_program(name, summary?)` | |
| Approval | `archive_node(node_id, reason)`, `archive_edge(edge_id, reason)` | always a proposal |
| Validation | `find_missing_resources(type?)`, `find_duplicate_nodes(threshold?)` | rank, never merge |
| | `check_broken_links(limit≤50, offset)` | concurrent HEAD, 6 s timeout, redirects followed; Google 401/403 or sign-in redirect = `needs_auth`, not broken |
| | `validate_course_structure(course_id)` | issues + completeness score |

## Claude Code

Copy the example to the repo root (`.mcp.json` is gitignored by `/*.json`) and
supply the token through the environment, never in the file:

```bash
cp mcp_server/mcp.example.json .mcp.json
export KB_API_URL=https://<your-app-host>      # or http://127.0.0.1:8765 locally
export KB_MCP_TOKEN=ikkb_...                    # from Settings → API tokens
claude                                          # then /mcp to see "ik-kb"
```
`pip install -r requirements.txt` provides the `mcp` and `httpx` packages.

The packaged plugin (`plugins/ik-knowledge-assistant/`) bundles the same server
config plus the two skills.

## Claude.ai (remote)

Claude.ai connects to remote MCP servers over HTTPS. Run the server with
`--http` behind TLS on a host that can reach the KB API, then add it under
Settings → Connectors → *Add custom connector* with its URL. **Before exposing
it:** the HTTP transport in this run binds 127.0.0.1 and authenticates with ONE
server-side token, i.e. it acts as one user. A multi-user remote deployment
needs per-user OAuth in front of it — designed in `docs/AI_ARCHITECTURE.md`,
not built.

## Verification (2026-11-02)

- `tests/test_kb_mcp.py` (6 tests, all pass): spawns the server over stdio with
  the official client SDK, lists tools (exactly the 19 above), calls every one,
  plus viewer-token write denied, editor-token archive → proposal, approval by a
  person executes it, expired/revoked/garbage tokens denied, missing
  `KB_MCP_TOKEN` → startup error naming it, link classification incl. redirects
  and timeouts.
- **Live Claude check: VERIFIED.** `claude -p` (Claude Code 2.1.292) with
  `--mcp-config` pointing at this server and a viewer token answered
  *"Course: Synthetic Distributed Systems / Resource: Raft notes (synthetic) —
  https://example.com/synthetic/raft-notes"* from the local seeded KB.
