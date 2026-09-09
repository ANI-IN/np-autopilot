---
description: Look up a workflow by id or name — steps, effort, alerts, tools, theme.
argument-hint: <workflow id or name>
---

Read `${CLAUDE_PLUGIN_ROOT}/knowledge/graph.json`, find the workflow by
`workflow_id` (e.g. `8.2`) or by label, and return its steps, effort, alerts,
tools, theme and source row.

**This is lookup, not reasoning, and the answer must say so.** A workflow's only
edge is `belongs_to` pointing at its theme. There is **no path** from a workflow
to any person, program, module or instructor — not a long path, no path.

Always append: *ownership is domain-level; use `/domain-owner`. There is no owner
for this workflow, and that is a fact about how the team works, not a gap.*

`depends_on` is empty: the corpus contains no workflow-to-workflow dependency
evidence, so **do not answer sequencing or prerequisite questions**.

**Match clauses, not keywords.** Searching alert text for `owner` returns 12
workflows where only 3 carry the clause *"ownership is unclear"*; searching `drop`
returns 3 where 2 are about **rating** drops.
