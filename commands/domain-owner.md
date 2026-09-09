---
description: Who owns a domain — primary, secondary and delivery POC, with cadence and source row.
argument-hint: <domain>
---

Read `${CLAUDE_PLUGIN_ROOT}/knowledge/graph.json`. For the named domain, follow
`owned_by` (primary), `supported_by` (secondary) and `delivered_by` (delivery
POC) to `person` nodes, and report the `cadence` plus the source row.

**Named `domain-owner`, not `owner`, deliberately.** Ownership in New Programs
attaches to domains. There is no workflow-level owner, so a command called
`owner` would promise something that does not exist. If asked who owns a
*workflow*, answer at domain level and explain why.

Some delivery POCs are first names only (`Anshuman`, `Rupali`, `Sinchana`). They
belong to the **delivery org**, not the NP team, and no NP roster resolves them —
say so rather than presenting the first name as incomplete data.

If a person carries `corpus_disagrees: true`, state that their status is
out-of-corpus and that the files lean the other way.
