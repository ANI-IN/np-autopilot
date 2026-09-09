---
description: Who can teach a domain or module, with teaching history separated from declared expertise. Never merges evidence tiers.
argument-hint: <domain>
---

Run `python3 ${CLAUDE_PLUGIN_ROOT}/pipeline/query.py staffing "$ARGUMENTS"` and
present the JSON it returns. **The tiering is computed in that script. Do not
reorder it, do not merge tiers, and do not add names from anywhere else.**

## The rule this command exists to enforce

A staffing answer that sounds authoritative while recommending someone who ticked
a box on a form is the worst failure this system can produce. So:

**1 · Lead with what is absent.**
- `no_instructors_confirmed: true` → say **"<domain> has no instructors"**, state
  that this is confirmed by the corpus owner and is **not a data gap**, and stop.
  Do not offer declared names. Do not suggest looking for a missing file.
- `taught: []` but `declared` non-empty → open with **"No one in the corpus has a
  recorded history of teaching <domain>."** Only then offer the declared tier,
  labelled as such.
- Always give `modules_with_teaching_history` of `modules_total`.

**2 · Present the tiers separately, in this order, never interleaved.**

| tier | field | what it means |
|---|---|---|
| **Taught** | `taught[]` | Actually ran the class. **Name the source sheet.** |
| Declared — HR | `declared.hr_record` | A subject field on the HR roster. |
| Declared — form | `declared.self_declared` | **A Google Form response. Not evidence of capability.** |
| Declared — alias | `declared.*+via_alias` | Form response **plus** an alias-matched domain. Two inference steps. Weakest. |

**3 · Within Taught, rank by `last_taught` then `sessions_past`.**
`sessions_scheduled` is a **future** booking — never present it as history.

**4 · Availability, if present — and phrase it carefully.**
`declined_count` / `confirmed_count` / `decline_rate` come from the class
confirmation log. This is **scheduling friction, not performance**. Say
*"declined 9 of 22 scheduling requests"*. **Never** imply it reflects teaching
quality, reliability or willingness in any judgmental sense.

**5 · If `ambiguous` is returned, ask which domain.** Do not choose.

## Worked shape

```
Backend — 7 of 21 modules have teaching history.

TAUGHT
  Konstantinos Pappas   Database Design, Concurrency   last taught 2026-09-08
                        36 past sessions, 20 scheduled · declined 0 of 34
                        New Combined Schedule.xlsx!Combined Schedule Mastersheet

DECLARED — not evidence anyone has taught
  HR roster (8)         SME database!Master
  Google Form (50)      Instructors Directory!Responses
```
