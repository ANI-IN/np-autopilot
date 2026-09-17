# Cache exposure — what `.drive-cache/` holds and what protects it

**A decision document, not an implementation plan.** Only two things were built
(§5). Everything else is a recommendation for you to take with the real numbers
in front of you, and — given §0 — plausibly with someone in legal.

Personal-data counts are quoted from **doc 01 §Tier 0** and **doc 07 R6**, not
re-derived, so they can be traced to the scan that produced them.

---

## 0 · Read this first: the repository was PUBLIC for eight days

Found 2026-09-17 while checking the remote before the planned deletion.

```
gh api repos/ANI-IN/np-autopilot  ->  "private": false, "visibility": "PUBLIC"
created_at 2026-09-09T17:54:03Z   pushed_at 2026-09-09T20:46:25Z
forks 0 · stars 0 · watchers 0 · collaborators: ANI-IN only
```

**Every document in this project states the repo is private.** `README.md`
("`ANI-IN/np-autopilot`, private, no collaborators"), `NEXT.md`, `docs/AUDIT.md`,
`docs/DECISIONS.md` §F, and doc 07 **R16** — which flags the *reference
implementation* being public as a risk **while contrasting it against this repo
being private**. The assumption was never checked against the API until now.

**Set to private immediately on discovery.** Exposure window ≈ 8 days.

### What was publicly readable during that window

From the committed artefacts, at `ebddfc5` and earlier:

| | |
|---|---|
| Instructor names | **3,817** |
| — of whom **hiring rejections** | **277**, named external people |
| — of whom mid-pipeline candidates | **1,625** |
| Per-instructor average ratings | 39 |
| Per-instructor decline rates | 136 |
| `rejections.json` entries naming a withheld person **against an SME hiring-tracker sheet and row number** | **140** |
| Internal staff | 43, with titles and seniority |

Plus every analysis document, including **doc 01 §Tier 0**, which *describes* the
payroll file's columns and the 8,001-email finding, and **doc 07 R16**, which
names the reference implementation's client accounts and its `$940M` figure.

### What was NOT exposed

**The corpus itself was never committed.** All seven directories are gitignored,
and the git-history scan in `docs/AUDIT.md` §5 confirmed no corpus file has ever
been added. So the 8,001 email addresses, 8,074 phone numbers and 4,524 LinkedIn
URLs were **not** in the public repo — they live only in the corpus and now in
`.drive-cache/`.

That distinction is the whole reason this document separates the two.

### What this changes

1. **The history rewrite stops being hygiene and becomes remediation.** It was
   planned on the premise "collaborators are not recruiting-cleared". The actual
   premise is "this was on the public internet for eight days".
2. **Deleting the repository is now clearly right**, not merely tidier than a
   force-push. Public repositories are crawled by code-search indexes and
   mirrors regardless of stars or forks, and `git clone` needs no permission.
   Zero forks and zero stars is **not** evidence of zero copies.
3. **You should decide whether this needs disclosure**, and that is not my call.
   The subjects are named external individuals and the data includes hiring
   outcomes. That is the question for legal.
4. **Check the other repositories.** The same unverified assumption produced
   this one. Doc 07 R16 already records a *second* repo,
   `voldemortuk/acceler-presales-plugin`, as public with client names and
   pricing.

---

## 1 · What is in `.drive-cache/` today

74 files, ~80 MB, fetched read-only by the service account. This is the **whole
corpus, unredacted** — field-dropping happens at extraction, in pass 2, long
after these bytes are on disk.

| File | Personal data it carries (doc 01 §Tier 0) |
|---|---|
| `05-operations/Operational Metrics.xlsx` | **20,338 email occurrences, 14,030 phone occurrences.** Sheet `Cohort Type Wise Coaching Raw D` is **12,986 rows** of `learner \| learner_email \| Coach \| Session_Title` — every row a named learner, their personal email, their coach and their session, from 2023 onward. Sheet `Single cohort per student all w` is **9,789 rows** of `Student Name` against weekly activity. |
| `03-instructors/SME Tracker - Bullseye_IK.xlsx` | 2,252 named hiring candidates with outcomes; contact columns |
| `03-instructors/SME_Interview_Demo Audit Rubrics.xlsx` | interview records, `Reject` / `Shall proceed further` |
| `03-instructors/Instructors Directory.xlsx` | Google Form responses: name, email, phone, LinkedIn, Discord |
| `03-instructors/SME database (For Ops + NP).xlsx` | HR roster with contact fields |
| `03-instructors/AgenticAI Instructors Training Plan.xlsx` | sheets `WIP` / `Instructors` carry **free-text judgements about named people** — *"Bad ratings"*, *"Unresponsive"* |
| `00-master/IAims Setting Audit _ New Programs.xlsx` | named employees, IDs, `Manager's Ratings`, `People Effectiveness Score` |
| `06-analysis/*Poll Feedback*.xlsx` | learner poll responses |
| **`03-instructors/US Instructor Cost Analysis.xlsx`** | **NO LONGER FETCHED — see §5.** Was 23 MB: 5,387 names, work and personal email, `Employement Status` including `Exited (Resigned)` / `Exited (Terminated)`, `LWD`, per-labour-code hourly rates. |

**Corpus totals, doc 01 §Tier 0** — 8,001 distinct email addresses (7,976
external, 7,313 `gmail.com`), 8,074 distinct phone numbers, 4,524 distinct
LinkedIn URLs, across 279 email domains.

**So the clean artefact is `graph.json`. The cache is everything.** Every R17
failure mode applies at this scale, not at the scale of one payroll file.

---

## 2 · Mitigations at rest: which are meaningful, which are theatre

The test for theatre: **the service account can re-fetch the whole corpus on
demand.** Anything that protects bytes already on disk while leaving that
capability untouched narrows the window, not the blast radius.

| Mitigation | Verdict |
|---|---|
| **Delete the cache after pass 1** | **Theatre, and it breaks the design.** Pass 2 and pass 4 both read the corpus directly, not `files.json` — deleting after pass 1 breaks the build. Deleting after pass 4 would work mechanically but forces a full re-fetch for any re-parse, which is precisely the pass-0/pass-1 separation the project holds as a rule. |
| **Retention / TTL on the cache** | **Marginal.** Bounds how long a stale copy lingers, which matters for a machine that stops being used. Does nothing about the window when the pipeline is actually running, which is when a compromise is most likely. |
| **Full-disk encryption (FileVault)** | **Meaningful but already assumed.** Protects a stolen laptop, nothing else. Worth *verifying* it is on rather than assuming — this document exists because an assumption about privacy went unchecked for eight days. |
| **Per-file encryption at rest in the cache** | **Theatre.** The pipeline must decrypt to parse, so the key lives beside the data on the same machine. It defeats a casual copy and nothing with code execution. |
| **Fetching to a tmpfs / RAM disk that never touches disk** | **Meaningful, and the strongest option available.** ~80 MB fits in RAM easily. Removes the at-rest problem entirely: no file to back up, snapshot, or recover. Costs a full re-fetch per run (~4m17s measured) because nothing survives a reboot, and on macOS needs an explicit RAM disk. **This is what I would build if you want one change.** |
| **Fetch-time exclusion of known-sensitive files** | **Meaningful, built (§5), and bounded.** It is the only mitigation that reduces what is fetched rather than protecting what was. Its ceiling is the exclusion list, and today that list has one entry. |
| **Narrowing the Drive share** | **The only structural fix.** Everything above manages a copy of data the service account is entitled to read. If the account cannot see `Operational Metrics.xlsx`, no cache policy is needed for it. See §6. |

---

## 3 · What changes on shared infrastructure

D3 puts this on a worker. Four things become true that are not true on a laptop.

**1 · Backups and snapshots become copies you do not control.** A laptop's cache
is deleted when you delete it. A worker's disk is snapshotted by the platform on
a schedule you did not set, retained for a period you did not choose, and
restored into environments you will not inspect. **A 12,986-row learner table
enters a backup rotation.** This is the single largest change and it is invisible
from inside the pipeline.

**2 · The blast radius stops being one person.** Anyone with shell on the worker,
anyone who can read its volume, anyone who can restore a snapshot.

**3 · Nobody is watching the file list.** Pass 0's own output names every file it
fetches. Unattended, that scrolls into a log nobody reads — which is exactly how
`US Instructor Cost Analysis.xlsx` was downloaded on every run without anyone
noticing until R17 was written.

**4 · The failure mode becomes silent.** Covered already: the fatal
empty-enumeration path leaves no `BUILD_LOG` record (fixed in `4bf827a`), and a
partial fetch that looks successful is worse unattended than interactively.

**Recommendation for the worker: ephemeral compute, cache on tmpfs, no
persistent volume.** If the worker has no disk that survives the run, most of
this section stops applying. That is a deployment decision, not a code change.

---

## 4 · Can pass 1 consume a stream instead of a cache?

**No. Removing the cache is a rewrite, and a large one.** Stated plainly because
the answer is not "with some refactoring".

Three structural reasons:

1. **`openpyxl` needs a seekable file.** `load_workbook(read_only=True)` reads a
   ZIP container — random access over the central directory. It cannot consume a
   forward-only stream. Every `.xlsx` read in passes 1, 2 and 4 depends on this.
2. **Passes 2 and 4 re-open the corpus independently.** Pass 1 does not hand
   parsed content forward; it writes `files.json` and the later passes open the
   same files again from disk. A streaming pass 1 would require passes 2 and 4 to
   re-fetch — `New Combined Schedule.xlsx` alone is opened for the schedule
   sheets, the confirmation record and the instructor list.
3. **The pass-0/pass-1 separation is a stated project rule** — *"re-parsing must
   never re-download"*. Streaming inverts it: every re-parse becomes a re-fetch,
   and iterating on an extractor becomes an hours-long loop against the Drive API.

**What is achievable without a rewrite:** put the cache on a **tmpfs**. Pass 1
still gets a real filesystem with seekable files, passes 2 and 4 still re-open
them, the rule still holds — and nothing is ever written to persistent storage.
That gets most of the benefit of "no cache" at the cost of a re-fetch per boot,
and requires no code change beyond `cache_dir`.

---

## 5 · What was actually built

Only the two things you asked for.

**Fetch-time exclusion.** Pass 0 reads `taxonomy.yaml -> excluded.files` and
skips those entries **before downloading**, and purges any that an earlier run
left behind. Verified live: the 23 MB payroll file was present in the cache, was
purged on the next run, and was not re-fetched.

**Cache assertion.** `validate.py` now fails if an excluded file is present in
`.drive-cache/`, not merely absent from `files.json`. Verified by firing on the
real cache before the fix.

**The honest scope of "two layers".** Pass 0 and pass 1 both read the same
exclusion list, so a wrong entry defeats both. They are two layers against a bug
in *one pass*, not against a wrong list — DECISIONS §A.7a. A test pins that
caveat in place so nobody upgrades the claim by accident.

---

## 6 · Recommended, not built

Ordered by how much they reduce, rather than manage, exposure.

1. **Narrow the Drive share.** The service account currently reads the whole
   folder. It does not need `Operational Metrics.xlsx` — the graph takes nothing
   from its 12,986 learner rows. Moving learner-data files to a sibling folder
   that is not shared removes ~20,000 email occurrences from every future fetch.
   **Largest reduction available, and it is a Drive permissions change, not code.**
2. **Expand `excluded.files` to every file the graph takes nothing from**, so
   fetch-time exclusion covers them. Weaker than (1) — the account could still
   read them — but it is under our control and takes minutes.
3. **Key the exclusion on content, not path.** Today a rename un-excludes a file
   silently. A sha256 or a header-shape rule closes R17's top unmitigated item.
4. **Cache on tmpfs** on the worker, per §2 and §4.
5. **Ephemeral worker with no persistent volume**, per §3.
6. **Log the file list to something a human reads** on a schedule, so a newly
   appearing sensitive file is noticed rather than fetched quietly.

---

## 7 · What remains unsolved, and must not be claimed otherwise

**The service account can read every file in the shared folder on demand.** The
fetch-time exclusion is a client-side decision made by code we control; it is not
a permission. Anyone who can run the pipeline, or who holds the key, can fetch
the payroll file by editing one line of YAML.

The key is at `~/.config/np-autopilot/drive-sa.json`, mode 600, outside the repo,
and pass 0 refuses to read one from inside the repo. That is good hygiene. It is
not a control on what the account may read.

**Only §6.1 changes that.**
