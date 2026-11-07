# Sources inventory: 2026-11-07 (redacted)

A read-only count of everything reachable from the registry Google Sheet: the sheets it links to (two levels deep) and the Drive folders it points at.
Counts only. File names, folder names, people, emails, ids and URLs are left out on purpose. The full private inventory is kept in `.measure/inventory/`, which git ignores.

## How it was gathered

- Service account, read-only scopes (`drive.readonly`, `spreadsheets.readonly`). Nothing in Google, the database or the repo was changed.
- The registry sheet id was taken from `docs/project-history/REGISTRY-INVENTORY.md` because `KB_SHEETS_ID` is empty in the local `.env`.
- The Sheets API is turned off in the service account's GCP project, so each sheet was read with the Drive API's read-only xlsx export. Cell values, formulas and cell hyperlinks were scanned for links.
- Folders were walked recursively, shared drives included, with a cap of 30,000 items. Cap reached: **no**.

## Totals

| Measure | Count |
|---|---|
| Sheets opened (registry + linked) | 3 (0 could not be read) |
| Tabs | 41 |
| Data rows (non-empty, below the header row) | 2,940 |
| Link occurrences in sheets | 64 (47 distinct targets) |
| Linked folders walked | 27 |
| Sub-folders found | 2,890 |
| Files found | 10,261 |
| Total size (as reported by Drive) | 51.3 GB |
| Modified-time range | 2021-08-10 to 2026-11-07 |
| Folders reached by more than one path | 11 |
| Access failures | 38 |

## Links by kind

| Kind | Occurrences |
|---|---|
| folder | 39 |
| presentation | 10 |
| document | 10 |
| spreadsheet | 5 |

## Link resolution

| Status | Occurrences |
|---|---|
| ok | 44 |
| 404 not found / no access (Drive hides unshared files as 404) | 20 |

## Sheets and tabs

### Sheet 1 (registry), depth 0

| Tab | Data rows | Columns | Links | Headers |
|---|---|---|---|---|
| Tab 1 | 8 | 2 | 7 | Folder, Link |

### Sheet 2, depth 1

| Tab | Data rows | Columns | Links | Headers |
|---|---|---|---|---|
| Tab 1 | 51 | 8 | 0 | Category, Task, Status, Owner, Start date, End date, Link to the document, Notes |
| Tab 2 | 41 | 8 | 0 | Upcmoing Cohort (On Uplevel), Orientation Date, (First class) Start Date, Enrollment, Merge Date, Sessions Saved in June, Floater sessions saved, Total Sessions Saved till Cohort End |
| Tab 3 | 30 | 5 | 3 | Overall Summary: Q3, Live Session, Assignment Review, NPS, NPS Master |
| Tab 4 | 17 | 26 | 31 | Module, Module Owner, Module Owner, Content Drive Folder, Assignment Review - Slides, Reviewed, Coding Notebook Folder, Reviewed {Notebook}, Instructor Aligned, Sunday Class Date, Thursday Class Date, New Ratings, Average |
| Tab 5 | 14 | 7 | 0 | Week, Focus Area, Key Concepts / Skills, Deliverable {Learning Outcome}, Pointers to think about |
| Tab 6 | 5 | 3 | 0 | Meeting, Notes |
| Tab 7 | 78 | 12 | 0 | US SME, Senior US SMEs, Indian SMEs |
| Tab 8 | 36 | 30 | 4 | Module, New Dev / Revamp, Task Distribution, US SME, Indian SME, Status, Expected ETA, Comments, Changes ( Post First Delivery ), Internal Team, Primary Module Owner, Secondary Module Owner, Budget Estimation (USD), Lesson Plan, Slides, Coding Demo, Assignment & Solution, MCQs |
| Tab 9 | 69 | 90 | 0 | Cohort, US - Early Jan Cohort, US - 2nd Mid Jan Cohort, Early Feb Cohort, Mid Feb Cohort, 2nd Mid Feb Cohort, Early Mar Cohort, 2nd Mid Mar Cohort, 2nd End Mar Cohort, Early Apr Cohort, Mid-April 2026, 2nd Mid-April 2026, Early-May 2026, Mid-May 2026, 2nd Mid-May 2026, Early June 2026, Mid-June 2026, 2nd Mid June 2026, Early-July 2026, Mid-July 2026, 2nd Mid-July 2026, Early-August 2026, 2nd Mid-August 2026, 2nd End-August 2026, Early-September 2026, Mid-September 2026, 2nd Mid-September 2026, Early-October 2026, Mid-October 2026, 2nd Mid-October 2026, Early-November 2026, Mid-November 2026, 2nd Mid-November 2026, Early-December 2026, 2nd Mid-Decemebr 2026 |
| Tab 10 | 45 | 8 | 0 | Module Name, Resource Name, Type, Resource Type, Uplevel Link, Details Present in the link, When ? (PST), Comms. |
| Tab 11 | 44 | 8 | 0 | Module Name, Resource Name, Type, Resource Type, Uplevel Link, Details Present in the link, When ? (PST), Comms. |
| Tab 12 | 59 | 50 | 0 | d, Early May Cohort, Early June Cohort, Mid July Cohort, Early August Cohort, 2nd Mid August Cohort, Early September Cohort, 2nd Mid September Cohort, Early October Cohort, 2nd Mid October Cohort, Early November Cohort, 2nd Mid November Cohort, Early December Cohort, 2nd Mid December Cohort |
| Tab 13 | 69 | 74 | 0 | US - Date, US - Early Jan Cohort, US - 2nd Mid Jan Cohort, Early Feb Cohort, Mid Feb Cohort, 2nd Mid Feb Cohort, Early Mar Cohort, 2nd Mid Mar Cohort, 2nd End Mar Cohort, Early Apr Cohort, Mid-April 2026, 2nd Mid-April 2026, Early-May 2026, Mid-May 2026, 2nd Mid-May 2026, Early June 2026, Mid-June 2026, 2nd Mid June 2026, Early-July 2026, Mid-July 2026, 2nd Mid-July 2026, Early-August 2026, 2nd Mid-August 2026, 2nd End-August 2026, Early-September 2026, 2nd Mid-September 2026, Early-October 2026, Mid-October 2026, 2nd Mid-October 2026, Early-November 2026, Mid-November 2026, 2nd Mid-November 2026, Early-December 2026, Mid-December 2026, 2nd Mid-Decemebr 2026 |
| Tab 14 | 33 | 7 | 0 | Module Name, Resource Name, Type, Resource Type, Uplevel Link, When ? (PST), Comms. |
| Tab 15 | 33 | 7 | 0 | Module Name, Resource Name, Type, Resource Type, Uplevel Link, When ? (PST), Comms. |
| Tab 16 | 34 | 7 | 0 | for, Resource Name, Type, Resource Type, Uplevel Link, When ? (PST), Comms. |
| Tab 17 | 33 | 7 | 0 | for, Resource Name, Type, Resource Type, Uplevel Link, When ? (PST), Comms. |
| Tab 18 | 70 | 42 | 0 | Date, IND - Early Jan Cohort, IND - End Jan Cohort, IND - End Feb Cohort, IND - End Mar Cohort, IND - End April Cohort, IND - End May Cohort, IND - 2nd Mid June Cohort, IND - 2nd Mid July Cohort, IND - 2nd Mid August Cohort, IND - Mid September Cohort, IND - Mid October Cohort, IND - Mid November Cohort, IND - Mid December Cohort |
| Tab 19 | 52 | 8 | 0 | (withheld: header row holds URLs) |
| Tab 20 | 14 | 8 | 0 | SWEs, Count, Tech Professionals, Count, Pathway Cohorts - SWEs, Count, Pathways Cohorts - Tech Professionals, Count |
| Tab 21 | 59 | 5 | 0 | (withheld: header row holds URLs) |
| Tab 22 | 13 | 9 | 16 | Module Name, Learning Objectives, Content Folder, Pre-Class Resources, Pre-Class Res. Link, Pre-Class Comms., Post-Class Resources, Post-Class Res. Link, Post-Class Comms. |
| Tab 23 | 50 | 6 | 0 | (withheld: header row holds URLs) |
| Tab 24 | 34 | 14 | 0 | Date, IND - Mid August Cohort, IND - Mid September Cohort, IND - End October Cohort, IND - End November Cohort, Early Jan Cohort |
| Tab 25 | 49 | 6 | 0 | (withheld: header row holds URLs) |
| Tab 26 | 20 | 1 | 0 | Short Term Plan |
| Tab 27 | 28 | 31 | 0 | Applied Agentic AI for SWEs, -, Agentic AI Tech Pathway ( SWEs Coding ), -, Week, Topic: SWEs {Coding Version}, Week, Module Name, Week, Module Name |
| Tab 28 | 22 | 13 | 0 | Applied Agentic AI for SWEs, Agentic AI Tech Pathway ( SWEs Coding ) |
| Tab 29 | 48 | 8 | 0 | Module Name, Resource Name, Type, Resource Type, Uplevel Link, Details Present in the link, When ? (PST), Comms. |
| Tab 30 | 37 | 8 | 0 | Module Name, Resource Name, Type, Resource Type, Uplevel Link, Details Present in the link, When ? (PST), Comms. |
| Tab 31 | 45 | 7 | 0 | Module Name, Resource Name, Type, Resource Type, Uplevel Link, When ? (PST), Comms. |
| Tab 32 | 33 | 7 | 0 | Module Name, Resource Name, Type, Resource Type, Uplevel Link, When ? (PST), Comms. |
| Tab 33 | 43 | 7 | 0 | for, Resource Name, Type, Resource Type, Uplevel Link, When ? (PST), Comms. |
| Tab 34 | 33 | 7 | 0 | for, Resource Name, Type, Resource Type, Uplevel Link, When ? (PST), Comms. |
| Tab 35 | 10 | 1 | 0 | Agentic IP SWE/EM |
| Tab 36 | 6 | 7 | 0 | Provider, Key Dimensions / Pillars, Strength / Output, Link |
| Tab 37 | 0 | 0 | 0 |  |

### Sheet 3, depth 1

| Tab | Data rows | Columns | Links | Headers |
|---|---|---|---|---|
| Tab 1 | 593 | 5 | 3 | Week, Module Name, Topic, Subtopics, Pre-class + Assignment + Post-class resources |
| Tab 2 | 495 | 5 | 0 | Week, Module Name, Topic, Subtopics, Pre-class + Assignment + Post-class resources |
| Tab 3 | 487 | 5 | 0 | Week, Module Name, Topic, Subtopics, Pre-class + Assignment + Post-class resources |

## Folders

37 folder links resolved to 27 distinct folders. Folder numbers follow link order; a missing number is a folder already counted (the same folder linked again, or one already inside a walked folder).

| Folder | Sub-folders | Files | Size |
|---|---|---|---|
| Folder 1 | 1,822 | 3,523 | 28.4 GB |
| Folder 2 | 814 | 6,072 | 19.6 GB |
| Folder 3 | 43 | 77 | 145.9 MB |
| Folder 4 | 36 | 74 | 148.3 MB |
| Folder 5 | 12 | 12 | 40.5 MB |
| Folder 7 | 12 | 29 | 157.8 MB |
| Folder 9 | 14 | 48 | 1.5 GB |
| Folder 11 | 22 | 53 | 112.2 MB |
| Folder 13 | 10 | 23 | 23.1 MB |
| Folder 15 | 10 | 23 | 178.4 MB |
| Folder 17 | 24 | 109 | 421.6 MB |
| Folder 19 | 28 | 103 | 266.1 MB |
| Folder 20 | 15 | 30 | 198.6 MB |
| Folder 24 | 6 | 14 | 16.2 MB |
| Folder 26 | 6 | 22 | 19.7 MB |
| Folder 28 | 12 | 45 | 69.0 MB |
| Folder 31 | 4 | 4 | 21.7 MB |

## Files by type

| Type | Files | Size |
|---|---|---|
| audio/wav | 4,004 | 1.6 GB |
| application/octet-stream | 911 | 294.1 MB |
| Google Doc | 738 | 447.9 MB |
| Word (.docx) | 543 | 292.2 MB |
| Google Slides | 492 | 1.6 GB |
| application/json | 457 | 26.7 MB |
| PDF | 420 | 792.7 MB |
| PowerPoint (.pptx) | 394 | 1.8 GB |
| text/xml | 342 | 296.7 KB |
| text/x-python | 265 | 2.3 MB |
| ZIP | 262 | 14.1 GB |
| Plain text | 210 | 4.8 MB |
| video/mp4 | 196 | 14.6 GB |
| Google Sheet | 166 | 9.5 MB |
| text/markdown | 161 | 1.7 MB |
| application/x-python-code | 107 | 274.9 KB |
| text/x-python-script | 93 | 608.7 KB |
| application/x-shellscript | 84 | 128.4 KB |
| image/png | 77 | 38.4 MB |
| audio/x-m4a | 56 | 306.2 MB |
| CSV | 55 | 1.5 GB |
| Excel (.xlsx) | 51 | 4.9 MB |
| video/quicktime | 39 | 12.9 GB |
| Colab notebook | 38 | 8.1 MB |
| Drive shortcut | 28 | 0.0 B |
| Google Form | 22 | 408.9 KB |
| text/html | 8 | 478.3 KB |
| application/x-perl | 7 | 31.8 KB |
| application/macbinary | 7 | 201.9 MB |
| image/jpeg | 6 | 580.8 KB |
| text/javascript | 4 | 798.6 KB |
| image/svg+xml | 2 | 127.5 KB |
| text/css | 2 | 1.5 MB |
| application/x-iwork-keynote-sffkey | 2 | 7.0 MB |
| application/x-gzip | 2 | 456.7 MB |
| image/gif | 2 | 1.9 MB |
| application/x-msdownload | 2 | 164.9 MB |
| video/x-matroska | 1 | 69.4 MB |
| image/x-quicktime | 1 | 1.9 KB |
| image/x-icon | 1 | 14.7 KB |
| audio/mpeg | 1 | 8.2 MB |
| text/rtf | 1 | 406.0 B |
| application/x-apple-diskimage | 1 | 40.7 MB |

## Failures by reason

| Reason | Count |
|---|---|
| 404 not found / no access (Drive hides unshared files as 404) | 20 |
| shortcut target missing (404 not found / no access (Drive hides unshared files as 404)) | 18 |
