# UI BACKLOG — B3.5 and Release 2

**Owner decisions, Animesh Kumar, 2026-09-29. origin: hand.**
Recorded here because they were specified in conversation and nothing else
holds them. None of this is built yet.

Modelled on the B2B "Delivered Programs · Curriculum Graph" explorer, whose
screenshots the owner reviewed on 2026-09-29. **Display only — no new data.**
CSP stays strict; self-hosted libraries only.

---

# B3.5 — first release AFTER launch

*Moved 2026-09-30 (owner decision, Animesh Kumar, origin: hand): fastest
accurate launch. Was "after B3, before Phase C". Specification unchanged;
see `docs/archive/HANDOFF.md` §D.6.*

## a · Header stat chips
Domains · Modules · Sessions · Instructors · Decks · Topics. Labelled as
FLOORS and naming which graph they describe (`CLAUDE.md` §2). Clicking a chip
activates that type's filter.

## b · Type filter chips
One per node type, each with a colour dot matching its node colour.
Multi-select; all on = the full graph.

## c · Single-type view
When exactly one type chip is active, show only that type — spread evenly and
legibly, **no edges, no overlapping labels** — every node still clickable.
Only Instructors shows every instructor; only Modules shows the 20 row-B
modules, with the faded legacy modules behind their toggle.

## d · Focus mode
Clicking a node highlights its neighbourhood's edges and dims everything else.
Clicking empty canvas or pressing Esc clears it.

## e · Side-panel breadcrumb
"← Back to …", keeping the navigation history.

## f · Module panel header
Title; "Domain · Program week N · X files"; the module's Drive folder ↗ and
Uplevel module ↗; "Part of" chips (domain, programme week, programmes), each
clickable.

## g · Files · Open list
Every file with a type badge (gslides, pptx, pdf, docx, gdoc, gsheet, xlsx,
txt, md, zip, mp4) and "Open ↗". Current files first; historical ones ("Old",
revamp, superseded) in a **collapsed** "Historical" group with a badge;
download-disabled files marked **"view only"**; files grouped under their
session where matched.

## h · Hint bar
"drag node · scroll = zoom · click = details · drag canvas = pan · Esc = clear".

## i · One colour legend
Consistent across chips, nodes and panel headings.

## j · Do BETTER than the B2B version — its weaknesses, named

- **No overlapping labels.** Collision avoidance; labels shown by zoom level
  and importance; full label on hover.
- **Generic names always carry parent context.** `Class`, `Alternate Class`,
  `Assignment`, `Orientation`, `Day 1`… are meaningless alone. Render as
  "Class · API Design (Backend)" in labels, tooltips AND search results.
- **Search results grouped by type**, with domain and week badges. Keyboard
  navigation: `/` focuses search, ↑↓ and Enter to pick, Esc to clear.
- **The URL holds selected node, active types and focus**, so any view is
  shareable.
- **Faded and dimmed nodes stay readable on hover** — WCAG AA contrast.

**Screenshots required:** the full graph; single-type views for Instructors and
Modules; focus on API Design; the API Design module panel with its Files · Open
list.

---

# Release 2 — after launch, each its own phase

## Topic categories
A curated vocabulary of ~30–50 categories in `config/topic-categories.yaml`.
Raw topics map to categories **only as reviewable proposals with evidence**
(keyword and lesson-plan matches), `confirmed: false` until the owner confirms
in bulk or per row. Confirmed categories become graph nodes — like the B2B
"Topics" — linked to modules, with their own chip, colour, single-type view and
panel tags.

## Tools / tech
A **closed, curated** list in `config/tools.yaml` (Postman, Selenium, JMeter,
Docker, Kubernetes, AWS, React, Kafka, …), matched in deck and document text
with slide/page locators. New node type `tool`; edge module → `uses_tool`
carrying mention count and citations. Shown like the B2B "Tools": green nodes
with their own chip, single-type view, and tags in module panels.

**D1 is unchanged: no person is ever extracted from content.**
