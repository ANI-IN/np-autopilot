# AI architecture — designs for the next sessions

Built in this run: the MCP server (21 tools since run 6, incl. `list_types` and
`recent_activity`; list in docs/MCP.md), per-user tokens with
`actor_type='ai'` attribution, proposals for every AI archive/delete, and two
skills in a Claude Code plugin. Everything below is **design only** — no
half-built UI or code exists for it.

## 1. Remote MCP for Claude.ai with per-user OAuth

**Need:** Claude.ai connectors call a remote HTTPS MCP server; each person must act
as themselves.
**Design:** run `kb_server.py --http` behind TLS as a Vercel-adjacent service (or
a small container). Add OAuth 2.1 (authorization code + PKCE) per the MCP
authorization spec: authorization server = a `/api/kb/oauth/*` set of routes that
sign in with the existing Google flow and mint a short-lived KB token
(`kb.api_tokens` row with `name='oauth:<client>'`, 1-day expiry, refresh via the
same table). The MCP server forwards the bearer to `/api/kb` exactly as today.
**Schema:** `kb.oauth_clients(id, name, redirect_uris[], created_by)`,
`kb.oauth_codes(code_hash, client_id, user_id, pkce_challenge, expires_at)`.

## 2. Event-driven agents

**Need:** react to changes (new course → audit it; broken link found → open a
task) without polling humans.
**Design:** `kb.jobs(id, kind, payload jsonb, run_after, attempts, locked_by,
locked_at, status, last_error)` + an `AFTER INSERT` trigger on `kb.audit_log`
that enqueues jobs for subscribed event kinds (`kb.subscriptions(kind,
table_name, action, filter jsonb)`). A worker route `/api/kb/jobs/run` (Vercel
cron every 5 min; `select … for update skip locked limit 10`) dispatches each
job to an agent with a KB token of a service identity (a `kb.memberships` row
for a bot user, role `contributor`, so its archives are proposals).
**Sequence:** change → audit row → job → worker → Claude (Messages API with the
MCP tools) → writes as the bot (`actor_type='ai'`) → proposals for anything
destructive → humans approve in Approvals.

## 3. Multi-LLM orchestration

**Design:** a provider-neutral `kb.agent_runs(id, job_id, model, prompt_hash,
tools_used[], tokens_in, tokens_out, cost_usd, outcome, started_at, finished_at)`
table and a thin router module (`web/lib/kb/llm.py`) with one interface
`complete(messages, tools, model_hint)`; default to the latest Claude model,
route cheap classification (dedupe triage, tagging) to a small model. Every run
is auditable and replayable from `prompt_hash` + stored inputs.

## 4. Graph RAG / semantic search

**Need:** "what do we teach about X" beyond keywords.
**Design:** `create extension vector`; `kb.node_embeddings(node_id pk, model,
dims, embedding vector(1024), content_hash, updated_at)` refreshed by a job when
`content_hash(name||summary||body)` changes. Retrieval = hybrid: FTS + trigram
(existing) ∪ top-k vector, re-ranked, then **expanded one hop** through
`kb.edges` (the graph part), capped at 300 like the neighbourhood endpoint. New
MCP tool `semantic_search(query, k)`. Only if an embedding key is provisioned
(none existed in this run).

## 5. Guardrails that apply to all of the above

- Retrieved text is data: every tool result keeps `data_notice` and `sources`.
- No agent ever approves a proposal, mints a token or changes roles (enforced in
  the service by `actor_type`, not by prompt).
- Contact data never enters the KB: name checks in the DB (`@`, URLs), the
  import allow-list, and no contact fields in any table.
- Rate limits per token (`kb.api_tokens.last_used_at` + a `kb.token_usage`
  minute bucket) before opening remote access.
