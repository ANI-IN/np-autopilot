# np-autopilot

A knowledge graph over the New Programs corpus, packaged as a Claude Code plugin.

Status: **Part A complete, pending approval. Part B not started.**

---


## ⚠ Built from a local folder, not Drive

`pipeline/00_fetch_drive.py` **has never been run.** The graph is built from a
**hand-exported local folder**. Drive ingestion is **deferred to v2, not
cancelled**.

**The three-tab "NP Autopilot" master spreadsheet has never been located.** If it
turns out to exist in Drive, `Owner` and `Automation` may return as node types
and doc 05 is redone. Until pass 0 runs, nothing here supports any claim about
what Drive contains.

## Pipeline

Passes are separate on purpose. Each writes its output to disk and the next
reads it from disk, so any pass can be re-run without repeating the one before.

| Pass | Script | Reads | Writes |
|---|---|---|---|
| 0 | `pipeline/00_fetch_drive.py` | Google Drive | `.drive-cache/` |
| 1 | `pipeline/01_walk_corpus.py` | `.drive-cache/` | `files.json` |
| 2 | `pipeline/02_extract.py` | `files.json` | raw entities + rejection log |
| 3 | `pipeline/03_resolve.py` | raw entities | resolved entities |
| 4 | `pipeline/04_build_graph.py` | resolved entities | `knowledge/graph.json` |
| 5 | `pipeline/05_render_html.py` | `graph.json` | `graph.html` |
| — | `pipeline/validate.py` | everything | pass/fail |

**Pass 0 and Pass 1 must not be fused.** Pass 0 is the only script that touches
the network. Pass 1 only reads local files. Re-parsing must never re-download.

---

## Google Drive access

Corpus files are fetched from Drive by `pipeline/00_fetch_drive.py`, not from a
Drive-desktop sync folder. **This replaces §1.4 of the brief.**

**Why.** Two reasons, both verifiable. Neither is "the sync produced stubs" —
see the correction at the end of this section.

**1 · Tab fidelity.** A Google Sheet has no on-disk form that preserves its
tabs. Exporting it through the Drive API to `.xlsx` keeps **every tab**, which is
the only way the multi-tab workbooks this corpus depends on survive intact. The
alternative — a person opening each Sheet and choosing *File → Download* — is
per-tab-fragile and silently lossy.

**2 · Machine independence.** The current corpus was **hand-exported by someone**
onto one laptop. That makes the corpus a property of that machine: nobody else
can reproduce it, nobody can tell which files are stale, and a re-export is
manual work that will not happen on a schedule. Fetching from a folder ID makes
the corpus reproducible by anyone with read access and diffable between runs,
which is what the B10 v2 nightly job needs.

**Correction — a hypothesis I recorded as fact and have since disproved.** An
earlier version of this section said native files "sync as tiny URL stubs that no
parser can open" and called that "the most likely reason the master spreadsheet
never appeared locally." **I checked, and it is false for this folder.** There
are **zero** stub files: no `.gsheet`, `.gdoc` or `.gslides` anywhere, and no file
under 500 bytes. The eight extensionless files are full UTF-8 text extracts
ranging from 1.0 KB to 522 KB. So stub-syncing does not explain the missing
master spreadsheet, and the reason for its absence is still **unknown**. Pass 0
will settle it by enumerating what is actually in the folder.

### Setting up OAuth

1. Google Cloud Console → new project → enable the **Google Drive API**.
2. **OAuth consent screen → user type: Internal.** Not External.
3. Credentials → OAuth client ID → **Desktop app** → download JSON.
4. Save it as `config/credentials.json` (gitignored).
5. `cp config/drive.yaml.example config/drive.yaml` and set `folder_id`.
6. `python3 pipeline/00_fetch_drive.py` — a browser opens once, then
   `config/token.json` is written (gitignored, mode 600).

> **The consent screen must be user type Internal.** External + Testing issues a
> refresh token that **expires after seven days**; the pipeline then dies with
> `invalid_grant` and needs a manual re-auth every week. Internal issues a
> non-expiring refresh token and is available to us because we are a Workspace
> domain. This is the single most important setting on this page.

### Scope

`https://www.googleapis.com/auth/drive.readonly`, and nothing else. **The
pipeline must never hold write access to Drive.** If a future pass needs to
write, it gets a separate credential — do not widen this one.

### Never committed

`config/credentials.json`, `config/token.json`, `config/drive.yaml` and
`.drive-cache/` are all in `.gitignore`. The folder ID lives in
`config/drive.yaml`, never in a script.

### Nightly job (B10 v2) — not built yet

The nightly refresh should use a **service account** with the Drive folder
shared to its address, not this user OAuth flow — a headless job cannot complete
a browser consent, and a job tied to one person's account breaks when that person
leaves. Nothing in `00_fetch_drive.py` blocks this: replace `authenticate()` with
`service_account.Credentials.from_service_account_file(...)` and every other
function is unchanged, because they all take a `service` object and an account
label.

### If the folder returns nothing or 404s

`00_fetch_drive.py` **exits non-zero on an empty enumeration** and prints a
folder probe. An empty tree is never treated as success — that is the specific
failure mode a Shared Drive produces: `files.list` returns `[]` with HTTP 200,
not an error.

Shared-drive flags are set on both call sites that accept them:

| Call | Flags |
|---|---|
| `files().list()` | `supportsAllDrives=True`, `includeItemsFromAllDrives=True` |
| `files().get_media()` | `supportsAllDrives=True` |
| `files().get()` (probe) | `supportsAllDrives=True` |
| `files().export_media()` | *takes neither — the Drive v3 export endpoint has no such parameter. Correct as written.* |

**If the id 404s, check in this order:**

1. **Is it the folder id, not a file id?** Take the last path segment of the
   URL, after `/folders/`. Drop any `?usp=…` query string.
2. **Which account did you authenticate as?** The script prints it. A URL
   containing `/u/2/` means it was copied from your **third** signed-in Google
   account in that browser — the OAuth flow may have authenticated a different
   one. `/u/0/` is the first account. This mismatch is the single most common
   cause.
3. **Is it on a Shared Drive?** The probe prints `shared drive=<id>` or
   `My Drive`. If it is a Shared Drive, your account needs to be a **member of
   the drive**; folder-level sharing is not always enough.
4. **`canListChildren`.** The probe reports this explicitly. If false, you have
   view access to the folder but not permission to enumerate it.
5. **Trashed.** A trashed folder still resolves by id and returns no children.
   The probe reports it.
6. **Wrong Cloud project.** If the consent screen and the credential come from
   different projects, or the Drive API is not enabled on the project, auth
   succeeds and every call 404s. Confirm the Drive API is enabled on the same
   project that issued `credentials.json`.
7. **Stale token after changing the consent screen.** Changing user type from
   External to Internal invalidates the existing grant. Delete
   `config/token.json` and re-run.

If the probe says the folder is visible with `canListChildren` and still returns
zero children, it is genuinely empty and the id is not the one you meant.

### Every build is attributed

`00_fetch_drive.py` appends the **authenticated account** and the **folder ID**
to `BUILD_LOG.md` on every run. Different people have different Drive
visibility; a corpus that changes because someone else ran the fetch should be
visibly explained, not mysterious.

---

## Exclusions

Some corpus material is deliberately **not ingested**. This is recorded here so
the gap is a visible decision rather than a silent hole. The machine-readable
list is `excluded:` in `config/taxonomy.yaml`; `validate.py` fails the build if
an excluded file reaches `files.json` or an excluded field becomes a node
property.

**The primary reason is relevance, not privacy.** None of the material below
answers any question in the evaluation set. That it is also sensitive is the
second reason, not the first.

### Excluded file

| File | Why |
|---|---|
| `03-instructors/US Instructor Cost Analysis.xlsx` | Misnamed. It is a **Paycor HR payroll export** — employee file numbers, work and personal emails, department, employment status including `Exited (Resigned)` and `Exited (Terminated)`, and per-labour-code hourly rates for 5,387 distinct names. An HR record misfiled into a New Programs folder. 37 sheets, ~75,000 rows. |

**A cost worth stating.** This file is the only corpus source for 14 of the 25
internal `@interviewkickstart.com` addresses, and the only place that resolves
`Anshuman` → `Anshuman Bapna`. Those specific facts were extracted before the
exclusion took effect and are recorded by hand in `people.yaml`, citing this file
as out-of-corpus evidence. Nothing else is carried over.

### Excluded fields

Dropped at extraction from **every** sheet, so they never become node properties
and there is nothing to redact at render time:

`learner_email` · `Email` · `Email Address` · `Email ID` · `Personal email` ·
`Work email` · `Alternate Email ID` · `Gmail ID` · `Phone` · `Phone No.` ·
`Mobile` · `LinkedIn` · `LinkedIn Profile` · `LinkedIn Profile URL` ·
`LinkedIn Link` · `Discord ID` · `Discord Channel Link`

**Kept:** cohort counts, session titles, coach assignments, learner and student
*names* where a cohort count needs them.

Header matching is case-insensitive on the normalised header. A column with a
blank header whose values are >30% email- or phone-shaped is also dropped, and
the drop is logged — headerless contact columns exist in this corpus.

---

## Workflow owners

No file in the corpus assigns an owner to a workflow. `config/workflow-owners.yaml`
is the only source for the `Workflow → Person` edge, and that edge is the only
bridge between the two halves of the graph. Without it the graph ships as two
disconnected components.

Generate the stub with `python3 pipeline/gen_workflow_owners.py` — 92 rows, `id`,
`name`, `theme_id` and `theme` pre-filled, `owner` blank. 39 rows carry a
`suggestion` with the evidence it came from; **suggestions are guesses and the
pipeline ignores them.** To accept one, copy the name into `owner` yourself.

Every row ships `confirmed: false`. The pipeline emits an edge only where
`confirmed: true` and `owner` is non-empty, so a half-filled file is safe to
build from, and an empty `owner` is preserved as a real "no owner" answer rather
than a gap.

---

## Distribution — v1 is a single-user private repo

**`ANI-IN/np-autopilot`, private, no collaborators.**

**This deliberately overrides D10 for v1.** D10 specified a GitHub Organization
plus a team, so access is managed centrally rather than per-collaborator. That
remains the target. It is not what v1 ships.

**What this costs, stated plainly:**

- **No teammate can install anything.** Not "installs with extra steps" — a
  private repo with no collaborators is unreachable by `/plugin marketplace add`
  for everyone except the owner. Until the repo moves, this is a single-user
  tool.
- **Moving it later changes the marketplace URL**, and that **breaks
  `/plugin marketplace add` for anyone already installed.** They must remove the
  old marketplace and re-add the new one — and per the reference
  implementation's own documentation, removing a marketplace auto-uninstalls its
  plugins, so it is a remove-and-reinstall, not an update.
- **That cost scales with adoption.** One user today, so the move is nearly
  free. At ten users it is ten people doing a manual remove-and-reinstall, each
  of whom can get it wrong. **Move it before the second user, not after the
  tenth.**

The two sections below describe the **target state** under D10, not v1.

## Installing (for teammates)

Honest first-time cost — this is **not** two commands:

1. A GitHub account with access to the organisation.
2. `gh auth login` (or working SSH keys).
3. `/plugin marketplace add <org>/np-autopilot`
4. `/plugin install np-autopilot@np-autopilot`

Access is managed centrally through a **GitHub Organization + team**, not
per-collaborator invites, and the repository is **private**.

**Offboarding.** Removing someone from the org stops *future updates*. It does
**not** remove the graph snapshot already sitting in their local plugin cache.
Treat a shipped graph as shipped.

**The corpus is not bundled.** Teammates get `knowledge/`, `skills/` and
`pipeline/` — no corpus files. Every fact a skill needs must be baked into
`knowledge/graph.json` at build time; there is no fallback to reading a source
file at query time.
