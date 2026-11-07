# KYP structure and proposed data model (analysis, 2026-11-07)

Status: **analysis and proposal only**. Nothing has been written to any database. The pilot extraction went to local, gitignored staging files.
Related decisions: `docs/project-history/PLAN-2026-11-07.md` (decisions 7, 8, 12) and `docs/design/phase4-pilot-plan.md`.
This document is redacted: it contains no person names, emails, page IDs or URLs. Examples use generic names such as "Program A" and "Instructor 1".

## 1. What was read

The crawl was read-only (GET requests only) and covered 5 starting points in the curriculum Confluence space, 182 pages in all:

| Starting point (generic) | Pages | Shape |
|---|---|---|
| Interview Preparation domain KYPs (2026) | 20 | Flat folder: 2 overview pages and 18 domain KYPs |
| Short pro-code course KYPs | 14 | Flat folder: 14 domain pages built from included module pages |
| Applied Agentic AI KYPs (pilot) | 7 | Flat folder: 6 audience programs and 1 do-not-use page |
| Agentic AI + domain interview-prep KYPs (2026) | 18 | Flat folder: 1 comparison page and 17 domain KYPs |
| Regional KYPs and course outlines (2025 to mid-2026) | 123 | Page with sub-folders, depth 3, including an "Obsolete" folder of 36 pages |

Access:
- Page bodies, versions and labels were readable on every page.
- Listing attachment metadata works only through the older API (the newer endpoint returns 401). No attachment was downloaded.
- Search and user-name lookup returned 403 because of token scope, so page-owner accounts could not be turned into names.
- All 53 include-macro targets resolved.

## 2. The structure the pages actually support

### 2.1 The KYP template (families 1, 3 and 4: 42 pages)
The 2026 KYPs share a fixed 21-section template, each section an H2 heading:
USP · Pre-requisites · Target group · Market insights · Learning & career outcomes · Tools & tech · **Curriculum** · **Capstone projects** · **Live guided projects** · Misc projects · **Assignment projects** · Career services · Placement support · Support period · **Instructors** · Batch profile · Sample class videos · **Schedule** · Competitor benchmarking · Reviews · FAQs.

Only the bold sections carry curriculum structure. The rest is sales and positioning prose.

### 2.2 Relationships found (and where they come from)

| Relationship | Evidence (generic location) |
|---|---|
| Program = one KYP page (one audience or domain) | Page title and the H1/H2 at the top of the page |
| Program → ordered **sections** ("core", "interview preparation", "floater sessions", "bonus content") | Single-cell section rows inside the Curriculum table, or H2 sub-headings under Curriculum |
| Section → ordered **modules**, each with a week label (`0`, `1`, `8–9`, `F1`) | Curriculum table rows: `Week \| Module \| Agenda`, `Week / Module \| Detail`, `Week / Module \| Description + Topics + Project`, `Week \| Class / Module \| Agenda` |
| Module → ordered **topics** | Bullet items in the Agenda cell, or a "Topics: a; b; c" list |
| Module → one **live guided project** | The last agenda bullet, "Project: …", which matches a row in the Live guided projects table (`# \| Project \| (Week) \| Description`) |
| Program → weekly **assignments** | Assignment projects table (`Week \| Assignment \| Description`) or a list of "Week N — …" items |
| Program → **capstone options** (4–6 plus bring-your-own) | Capstone projects list or `Track \| What you build \| Tools` table |
| Program → **instructors** ("some of the instructors") | Instructors section: "Instructor 1, Title, Company: profile link", or an `Instructor \| LinkedIn` table |
| Program → **weekly cadence** (material release, live class, coaching/AMA, assignment review) | Schedule table `When \| What` |
| Program → **tools/technologies** | Tools & tech table `Category \| Tools`, or a single cell of "Category: tools" lines |
| **Reusable module content, program-specific weeks** | Short-course family: program pages include shared "Module – X" pages (78 includes), and the weeks sit in the program page's headings ("Module X (Weeks 1–3)") |
| KYP wraps a separate **course outline** | Regional family: KYP pages include the matching course-outline page (97 includes), and the outline holds the curriculum table |
| NP owner of a section (free text only) | Placeholder status notes "owned by / to be helped by Person 1" (69 notes across 35 pages in families 1 and 4) |

Things the pages do **not** support: module-level learning objectives, module-level SME assignment, explicit prerequisites between modules, explicit concepts, and a structured owner field.

## 3. Proposed mapping

```
Program ──(order, week_start, week_end)──> Course ──> Module ──> Topic ──> Concept
   │  └─(order_in_course, week_label, week_start/end, self_paced, floater)─> Module   [placement]
   ├── Resource (project, assignment, capstone, video, link)  [program-specific when the KYP says so]
   ├── instructors (role: listed instructor)                     [program level only]
   └── np_team_members (role: owner / section owner)             [needs owner confirmation]
```

| KYP element | Target entity | Notes |
|---|---|---|
| KYP page | **Program** | Prose sections stay as program attributes (raw text) |
| Curriculum section row ("Applied Agentic AI", "Interview Preparation", "Floater Sessions", "Bonus Content"); short-course "Module – DSA / Agentic AI / System Design / Domain" includes | **Course** (reusable) | The same section names recur across programs |
| Section order and week range | **Program–Course link** (order, week_start, week_end) | Derived from the min and max of module weeks; never stored on the Course |
| Curriculum row | **Module** (reusable; identity = title plus content) | |
| Row week label and order | **Program–Module placement** | Week 0 = self-paced pre-work; "8–9" = a range; floaters have no week |
| Agenda bullet or "Topics:" item | **Topic** | |
| Tools & tech entry | **Concept** (kind = tool/technology) | Real pedagogical concepts are not in KYPs and would need model-assisted derivation |
| Live project, assignment, capstone, sample video, Drive/Docs/Slides/Sheets link | **Resource** (typed) | Linked to a module where the KYP names it ("Project: …") |
| Instructors section | **instructors** | Program-level; no module mapping |
| Page owner and "owned by" notes | **np_team_members** | Names not resolvable with the current token scope |

## 4. What does not fit

1. **Same module title, different content.** Example: "Module X" has one agenda in Programs A/B and another in Programs C/D (11 titles in the pilot). The model needs either module *variants* or an owner decision on which version is canonical.
2. **Copy-paste programs.** In the pilot, one "generic" program's curriculum is byte-identical to another audience's, including audience-specific wording. Its prerequisites also contradict its stated audience. Reuse that happens by accident should not become a reuse link without review.
3. **Courses are implicit.** They exist only as section rows or headings, and the short-course family calls them "Module – X". The naming needs a mapping rule (KYP "module page" = model Course).
4. **Floater and bonus sessions** have no week. They belong to the program but are outside the weekly order.
5. **Projects, assignments and capstones** are first-class in KYPs. The model has only "Resource", so either a typed resource or a separate assignment entity is needed. Capstones are *options to choose from*, not a sequence.
6. **Career services, placement, support period, mock interviews, coaching, competitor benchmarking, market data, FAQs, reviews and batch profile** are program or product attributes that are not curriculum, and they have no home in the model.
7. **Weekly cadence** (day, time, session type) is a schedule *pattern*, not a week-by-week placement.
8. **Instructors are program-level samples** ("some of the instructors"). They are not a roster and are not mapped to modules.
9. **Owners** exist only as free-text placeholder notes and Confluence account IDs.
10. **The KYP vs course-outline split** in the regional family: the curriculum lives on another page that is pulled in by include. In 12 cases that page sits in an archived or obsolete folder while the KYP that includes it is current.
11. **Heterogeneous curriculum tables** in the regional family: 14 header variants, including a "Date" column that actually holds module names.
12. **Placeholders** ("TO BE FILLED") on 42 pages. They must be recorded as missing, not extracted as content.
13. **Attachments**: 1,635 images (about 410 MB), unreadable with the current token scope, so they are listed only.

## 5. Pilot: Applied Agentic AI (staging only)

Scope: 7 pages. 6 programs were extracted, 1 do-not-use page was skipped and listed, and 45 attachments were listed and not downloaded. Every record carries the page, page version, heading and table/row it came from.

| Entity | Count |
|---|---|
| Programs | 6 (13, 15 or 16 weeks; all 6 have a self-paced Week 0 and a 2-week capstone) |
| Courses | 4 |
| Modules | 66 variants (51 distinct titles; 28 variants shared by more than one program) |
| Topics | 337 (334 high confidence; 3 low) |
| Concepts | 102 tools/technologies (55 linked to modules by name match) |
| Resources | 205 (48 live projects, 49 assignments, 30 capstone options, 18 video titles, 6 Week-0 builds, 54 in-agenda project mentions of which 50 matched a live project) |
| People/roles | 32 instructor listings (16 distinct) and 12 owner/editor account references (3 distinct, names unavailable) |
| Schedule | 18 program→course links, 96 program→module placements, 24 weekly-cadence rows, 6 duration records |

**Clean:**
- The week/module/agenda skeleton. Extracted week ranges agree with the FAQ-stated duration (13 weeks) for 4 programs.
- Topics where the agenda is a bullet list.
- Project, assignment and schedule tables.
- Instructor entries.

**Ambiguous:**
- Module identity across programs.
- Topic granularity: one program uses short phrases, the others full sentences.
- Mixed week-label formats ("W1", "Week 1", "Module 1", "F1").
- Capstone titles split from free text.
- Tool lists that mix products, techniques and notes.

**Lost:**
- Pedagogical concepts and learning objectives (not present).
- NP owners (not present; names not resolvable).
- Module-level SMEs (not present).
- Image attachments (not read).
- Two placeholder sections per program.
