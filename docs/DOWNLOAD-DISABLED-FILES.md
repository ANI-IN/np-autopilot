# Files the crawler is not allowed to download

**49 files, measured 2026-09-29 on the row-B content crawl.** Each one is real
curriculum inside an approved domain, and none of it reached the cache.

## What the restriction is, and what it is not

Every file below has **`copyRequiresWriterPermission: true`** and
**`capabilities.canDownload: false`** — Drive's *"Viewers and commenters cannot
download, print, or copy"* setting, applied by whoever owns the file. Requesting
its bytes returns **HTTP 403** to any reader, including the pipeline's service
account.

The separation is total and that is what makes the diagnosis safe rather than a
guess: **every file that failed has the setting, every file that succeeded does
not.** Sizes run from 226 KB to 14 MB, so it is not a size limit; the 403 is
reproducible across three full crawls, so it is not throttling.

**It is not a bug, and it is not something this repository can fix.** Only the
file's owner can lift it, per file, in Drive's share dialog.

## How they are recorded

Reason code **`download-disabled-by-owner`**, deliberately separate from
`no-text-extractor`. The distinction is the point: `no-text-extractor` means
*we read it and could not parse it* — a gap in our tooling. This means *we were
never allowed to read it* — a permission somebody can change. One code for both
would be the shape where absence and failure look identical.

In the graph each becomes a **metadata-only node** — title, path, module link —
marked *"content unavailable: download disabled by owner"*. **They are never
dropped and their content is never inferred.** A module that appears to have no
deck, because its deck is on this list, must say so rather than read as a gap in
the curriculum.


**Owner domains:** `interviewkickstart.com` (49)

**File types:** presentation (27), document (20), application/pdf (2)


## SD1: Full Stack — 16 files

| title | size | path |
|---|---:|---|
| API Design and Implementation - Robert.pptx | 132 KB | `IK: Full Stack: Content Repo/Uplevel Shared/Week 2/5 - API Design and Implementation/Slides/API Design and Implementation - Robert.pptx` |
| API Design and Implementation - Vinicius.pptx | 2,693 KB | `IK: Full Stack: Content Repo/Uplevel Shared/Week 2/5 - API Design and Implementation/Slides/API Design and Implementation - Vinicius.pptx` |
| API Design and Implementation_ Timed Test.docx | 9 KB | `IK: Full Stack: Content Repo/Uplevel Shared/Week 2/5 - API Design and Implementation/Assignment/API Design and Implementation_ Timed Test.docx` |
| Cloud Infrastructure - Alex.pptx | 2,007 KB | `IK: Full Stack: Content Repo/Uplevel Shared/Week 3/5 - Cloud Infrastructure/Slides/Cloud Infrastructure - Alex.pptx` |
| Cloud Infrastructure- Timed Assessment Review Points.pptx | 666 KB | `IK: Full Stack: Content Repo/Uplevel Shared/Week 3/5 - Cloud Infrastructure/Assignment/Cloud Infrastructure- Timed Assessment Review Points.pptx` |
| Databases - Konstantinos.pdf | 3,515 KB | `IK: Full Stack: Content Repo/Uplevel Shared/Week 1/5: Databases/Slides/Databases - Konstantinos.pdf` |
| Databases Timed Assessment.docx | 381 KB | `IK: Full Stack: Content Repo/Uplevel Shared/Week 1/5: Databases/Assignment/Databases Timed Assessment.docx` |
| Getting Started with React.docx | 1,908 KB | `IK: Full Stack: Content Repo/Uplevel Shared/Week 4/5 - JavaScript and Web Development/foundation Material/Getting Started with React.docx` |
| Interview Questions Java.docx | 619 KB | `Additional Docs/Interview Questions Java.docx` |
| Interview Questions Spring.docx | 619 KB | `Additional Docs/Interview Questions Spring.docx` |
| JavaScript and Web Development - Kevin.pptx | 1,416 KB | `IK: Full Stack: Content Repo/Uplevel Shared/Week 4/5 - JavaScript and Web Development/Slides/JavaScript and Web Development - Kevin.pptx` |
| JavaScript and Web Development_ Timed Test.docx | 221 KB | `IK: Full Stack: Content Repo/Uplevel Shared/Week 4/5 - JavaScript and Web Development/Assignment/JavaScript and Web Development_ Timed Test.docx` |
| Meta software Engineer roles.docx | 1,207 KB | `Additional Docs/Meta software Engineer roles.docx` |
| Timed Assessment Solution.docx | 249 KB | `IK: Full Stack: Content Repo/Uplevel Shared/Week 3/5 - Cloud Infrastructure/Assignment/Timed Assessment Solution.docx` |
| UI System Design - Live Class Slides - Ashish.pptx | 5,561 KB | `IK: Full Stack: Content Repo/Uplevel Shared/Week 5/5 - UI System Design/Slides/UI System Design - Live Class Slides - Ashish.pptx` |
| UI System Design_ Timed Test.docx | 313 KB | `IK: Full Stack: Content Repo/Uplevel Shared/Week 5/5 - UI System Design/Assignment/UI System Design_ Timed Test.docx` |

## SD2: Frontend — 10 files

| title | size | path |
|---|---:|---|
| By Evgeny Vinnik - IK Frontend - Module 4 - Patterns, Tools and Techniques, Updated .pptx | 8,825 KB | `IK: Frontend Content Repo/Uplevel Shared/Week 4/4 - Leveling Up with Advanced JavaScript and CSS/Slides/By Evgeny Vinnik - IK Frontend - Module 4 - Patterns, Tools and Techniques, Updated .pptx` |
| FE System Design - Timed Test.docx | 267 KB | `IK: Frontend Content Repo/Uplevel Shared/Week 3/4 - Frontend System Design/Assignment/FE System Design - Timed Test.docx` |
| Frontend System Design - Evgeny Vinnik.pptx | 5,331 KB | `IK: Frontend Content Repo/Uplevel Shared/Week 3/4 - Frontend System Design/Slides/Frontend System Design - Evgeny Vinnik.pptx` |
| Frontend System Design - by Adam.pptx | 3,030 KB | `IK: Frontend Content Repo/Uplevel Shared/Week 3/4 - Frontend System Design/Slides/Frontend System Design - by Adam.pptx` |
| JD Kilby - IK Frontend - Module 4 - Patterns, Tools and Techniques, Updated .pptx | 16,885 KB | `IK: Frontend Content Repo/Uplevel Shared/Week 4/4 - Leveling Up with Advanced JavaScript and CSS/Slides/JD Kilby - IK Frontend - Module 4 - Patterns, Tools and Techniques, Updated .pptx` |
| JS Language & Libraries - Dominique.pptx | 5,350 KB | `IK: Frontend Content Repo/Uplevel Shared/Week 1/4 - JS Language & Libraries/Slides/JS Language & Libraries - Dominique.pptx` |
| JS Language & Libraries - Evgeny Vinnik.pptx | 4,528 KB | `IK: Frontend Content Repo/Uplevel Shared/Week 1/4 - JS Language & Libraries/Slides/JS Language & Libraries - Evgeny Vinnik.pptx` |
| JS Language & Libraries_ Timed Test_ Assignment.docx | 15 KB | `IK: Frontend Content Repo/Uplevel Shared/Week 1/4 - JS Language & Libraries/Assignment/JS Language & Libraries_ Timed Test_ Assignment.docx` |
| UI & DOM - Jakob.pptx | 8,855 KB | `IK: Frontend Content Repo/Uplevel Shared/Week 2/4 - UI & DOM/Slides/UI & DOM - Jakob.pptx` |
| User Interface & DOM - By David.pptx | 14,715 KB | `IK: Frontend Content Repo/Uplevel Shared/Week 2/4 - UI & DOM/Slides/User Interface & DOM - By David.pptx` |

## SD3: Backend Engineering — 11 files

| title | size | path |
|---|---:|---|
| API Design - Robert Kreznarich.pptx | 132 KB | `Module-1: Database Design/Uplevel shared/Week 3/5 - API Design/Slides/API Design - Robert Kreznarich.pptx` |
| API Design - Shelby Cohen.pptx | 11,562 KB | `Module-1: Database Design/Uplevel shared/Week 3/5 - API Design/Slides/API Design - Shelby Cohen.pptx` |
| Assignment.docx | 260 KB | `Module-1: Database Design/Uplevel shared/Week 1/5 - Database Design/Assignment/Assignment.docx` |
| Assignment.docx | 247 KB | `Module-1: Database Design/Uplevel shared/Week 3/5 - API Design/Assignment/Assignment.docx` |
| Cloud Native Design - Jeff wisman .pptx | 2,996 KB | `Module-1: Database Design/Uplevel shared/Week 4/5 - Cloud Native Design/Slides/Cloud Native Design - Jeff wisman .pptx` |
| Cloud Native Design - Sanjay Dhar .pptx | 4,382 KB | `Module-1: Database Design/Uplevel shared/Week 4/5 - Cloud Native Design/Slides/Cloud Native Design - Sanjay Dhar .pptx` |
| Concurrency - Faraaz.pptx | 1,868 KB | `Module-1: Database Design/Uplevel shared/Week 5/5 - Concurrency/Slide/Concurrency - Faraaz.pptx` |
| Concurrency - Live Class Assignment.docx | 30 KB | `Module-1: Database Design/Uplevel shared/Week 5/5 - Concurrency/Assignment/Concurrency - Live Class Assignment.docx` |
| Concurrency - Robert Kreznarich.pdf | 167 KB | `Module-1: Database Design/Uplevel shared/Week 5/5 - Concurrency/Slide/Concurrency - Robert Kreznarich.pdf` |
| Database Design - Konstantinos.pptx | 8,898 KB | `Module-1: Database Design/Uplevel shared/Week 1/5 - Database Design/Slides/Database Design - Konstantinos.pptx` |
| Database Design - Krishnamoorty Venkatraman.pptx | 8,494 KB | `Module-1: Database Design/Uplevel shared/Week 1/5 - Database Design/Slides/Database Design - Krishnamoorty Venkatraman.pptx` |

## SD4: Test Engineering — 12 files

| title | size | path |
|---|---:|---|
|  Automation Testing_ Assignment Solutions.docx | 10 KB | `Uplevel Shared/Week 4/6 - Automation Testing/Assignment/ Automation Testing_ Assignment Solutions.docx` |
| API Testing - Rodrigo Salazar.pptx | 1,759 KB | `Uplevel Shared/Week 3/6 - API Testing/Slides/API Testing - Rodrigo Salazar.pptx` |
| API Testing Assignment.docx | 309 KB | `Uplevel Shared/Week 3/6 - API Testing/Assignment/API Testing Assignment.docx` |
| Assignment Solution | 96 KB | `Uplevel Shared/Week 2/6 - Performance Testing/Assignment/Assignment Solution` |
| Cloud Testing - Live Class - Azeem.pptx | 3,249 KB | `Uplevel Shared/Week 6/6 - Cloud Testing/Slide/Cloud Testing - Live Class - Azeem.pptx` |
| KeyToLiveClassAssignments-CloudTesting.docx | 193 KB | `Uplevel Shared/Week 6/6 - Cloud Testing/Assignment/KeyToLiveClassAssignments-CloudTesting.docx` |
| Performance, Stress and Agile Testing Live Class Slides.pptx | 2,203 KB | `Uplevel Shared/Week 2/6 - Performance Testing/Slides/Performance, Stress and Agile Testing Live Class Slides.pptx` |
| Quality Engineering Foundations - Sergey Togulev.pptx | 13,886 KB | `Uplevel Shared/Week 1/6 - Quality Engineering Foundations/Slides/Quality Engineering Foundations - Sergey Togulev.pptx` |
| Quality Engineering Foundations - William Ogden (Bill).pptx | 13,108 KB | `Uplevel Shared/Week 1/6 - Quality Engineering Foundations/Slides/Quality Engineering Foundations - William Ogden (Bill).pptx` |
| Quality Engineering Foundations Assignment solutions.docx | 242 KB | `Uplevel Shared/Week 1/6 - Quality Engineering Foundations/Assignment/Quality Engineering Foundations Assignment solutions.docx` |
| Test Automation Design Patterns - Assignment | 75 KB | `Uplevel Shared/Week 5/6 - Test Automation/Assignment/Test Automation Design Patterns - Assignment` |
| Test Automation Frameworks Live Class Slides.pptx | 1,213 KB | `Uplevel Shared/Week 4/6 - Automation Testing/Slide/Test Automation Frameworks Live Class Slides.pptx` |

---

## To lift it

Drive → right-click the file → **Share** → gear icon → untick
*"Viewers and commenters can see the option to download, print, and copy"*.
Then re-run `python3 pipeline/06_crawl_content.py`; the crawl is resumable and
will pick up only what changed.

**Nothing here is urgent and nothing is lost** — the files still exist and are
readable by a person in Drive. What is lost is the pipeline's ability to read
what they teach, so every one of them is a module with less content behind it
than the folder suggests.

