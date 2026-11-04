# History rewrite — plan for approval

**Not executed. Nothing below has been run.** DECISIONS §F.2, under your
decision to treat the collaborators as **not recruiting-cleared**.

The forward-looking split is already done and committed (`daa8496`, `d4960be`):
new builds withhold the funnel. This document is only about the **past** — the
records already in git history.

---

## 1 · What is actually in the history

Measured, not estimated.

| | |
|---|---|
| Commits in the repo | **46** |
| Commits containing `knowledge/graph.json` | 41 |
| **Commits carrying hiring-funnel records** | **38** |
| Oldest carrier | `4082d6a` — *"teaches 6 → 694; scan UpLevel; render scope"* |
| Newest carrier | `744a1f6` — the commit before the split |
| `origin/main` | `ebddfc5` — **is a carrier** |

The payload grew over time as extraction improved:

| From | rejected | in_pipeline | sensitive nodes |
|---|---:|---:|---:|
| `4082d6a` … `6f55121` (12 commits) | 255 | 1,518 | 1,773 |
| `ee321c0` … `744a1f6` (26 commits) | **277** | **1,625** | **1,902** |

**Three files carry it, not one:**

| File | What it holds |
|---|---|
| `knowledge/graph.json` | 277 rejected + 1,625 in-pipeline instructor **nodes** |
| `knowledge/resolved.json` | the same 1,902, pre-edge |
| `knowledge/candidates.json` | 369 rejected + 1,895 in-pipeline **raw rows** — the rawest form, closest to the source sheets |

**Verified clean, so out of scope:** `graph.html`, `_graph_data.json`,
`_graph_files.json` contain **0 of 1,902** withheld names. The render filter
excluded them from the day it was written. `rejections.json` holds 185
*extraction* rejections — junk strings, not people, and unrelated.

---

## 2 · What the rewrite invalidates

You asked for this explicitly. Ordered by who it affects.

### 2.1 Every commit SHA changes

All 46. `git filter-repo` rewrites every commit from `4082d6a` forward, and
because each commit's hash covers its parent, everything after it changes too.

**Consequences:**

- Every SHA in `BUILD_LOG.md`, `NEXT.md`, `docs/AUDIT.md`, `docs/DECISIONS.md`
  and in **commit messages themselves** becomes a dangling reference. This
  document's own table of SHAs becomes wrong the moment it runs.
- `config/migration-baseline.yaml` does not reference a SHA, so the frozen
  reference `0165f164e104d6ad` survives. **The graph content is untouched by the
  rewrite** — only the commits that carried it.
- Any link to a commit on GitHub 404s.

### 2.2 Clones are invalidated

**Today: one. Yours.** There are no collaborators and no plugin installs.

Anyone holding an old clone must re-clone; a `git pull` produces divergent
histories that cannot be reconciled. This is the entire cost argument: it scales
linearly with people, and right now the multiplier is 1.

### 2.3 A force-push to `main` is required

`origin/main` is at `ebddfc5`, which is a carrier. The rewritten history is not
a fast-forward, so the push must be forced.

**This is the only step that is not locally reversible**, and it is why this
document exists rather than a commit. Before it, everything is recoverable from
the backup in §3.

### 2.4 GitHub retains unreachable objects

Force-pushing does **not** immediately delete the old objects from GitHub. They
remain reachable by direct SHA until GitHub's garbage collection runs, and
GitHub does not publish a guaranteed timeline.

**So the rewrite is necessary but not sufficient.** To actually remove them you
must additionally either:

- open a GitHub support request to run GC on the repository, **or**
- delete the remote repository and re-create it from the rewritten local copy.

**Deleting and re-creating is the only option with a definite outcome**, and at
zero collaborators and zero installs it costs almost nothing: recreate a private
repo of the same name and push. I recommend it over the support request.

### 2.5 What the rewrite does NOT fix

- **The corpus itself.** `.drive-cache/` and the source folder still contain the
  payroll file and every funnel sheet. Out of scope here; that is R17.
- **Google Drive.** The originals are unchanged.
- **Anything already copied elsewhere** — a previous export, a backup, a
  screenshot. Nothing can reach those.

---

## 3 · The procedure

Every step before 3.6 is reversible.

```
# 3.1 — full mirror backup, OUTSIDE the repo, before anything
git clone --mirror . ~/np-autopilot-prerewrite-backup.git
du -sh ~/np-autopilot-prerewrite-backup.git

# 3.2 — record what we expect to change, to compare afterwards
git rev-list --all --count                      # expect 46
git log --oneline --all > /tmp/shas-before.txt

# 3.3 — install the tool (not currently present)
pipx install git-filter-repo        # or: brew install git-filter-repo

# 3.4 — strip the three files from ALL history
git filter-repo --invert-paths \
  --path knowledge/graph.json \
  --path knowledge/resolved.json \
  --path knowledge/candidates.json

# 3.5 — VERIFY BEFORE PUSHING (see §4). If anything fails, restore from 3.1.

# 3.6 — the irreversible step
git remote add origin https://github.com/ANI-IN/np-autopilot.git
git push --force --all && git push --force --tags
```

**A deliberate choice in 3.4: strip the files entirely rather than rewrite their
contents.** Rewriting each historical `graph.json` to remove sensitive nodes
would require running a filter over 38 large blobs, and any bug leaves a
partially-scrubbed file that *looks* clean. Removing the path is total and
verifiable by a single grep.

**The cost of that choice:** the repo loses the ability to check out an old
commit and inspect the graph as it was. Given `graph.json` is regenerable from
the corpus at any pinned `NP_AS_OF`, and the frozen baseline records the current
reference independently, I judge that acceptable — but it is a real loss and
your call.

**Note that 3.4 removes `graph.json` from HEAD too.** After filtering, restore
the current public graph as a fresh commit:

```
python3 pipeline/refresh.py          # regenerates both halves
git add knowledge/graph.json && git commit -m "Restore the public graph"
```

---

## 4 · Verification before the irreversible step

Run all of these. Every one must pass.

```
# 4.1 — no funnel record survives anywhere in history
python3 - <<'EOF'
import subprocess, json
bad = []
for rev in subprocess.run(["git","rev-list","--all"],
                          capture_output=True,text=True).stdout.split():
    tree = subprocess.run(["git","ls-tree","-r","--name-only",rev],
                          capture_output=True,text=True).stdout
    for f in ("knowledge/graph.json","knowledge/resolved.json",
              "knowledge/candidates.json"):
        if f in tree:
            bad.append(f"{rev[:8]} still has {f}")
print("\n".join(bad) or "CLEAN — no target file in any commit")
EOF

# 4.2 — no withheld name appears in any blob
git grep -I -l "Karthika Pai" $(git rev-list --all) -- || echo "CLEAN"

# 4.3 — the working tree still builds and verifies
python3 -m pytest tests -q
python3 pipeline/verify_migration.py      # expect 32/32 against 0165f164e104d6ad
python3 eval/run_eval.py                  # expect 25/27, 0 fabrications

# 4.4 — the repo actually shrank
git count-objects -vH
```

**4.1 and 4.2 are the ones that matter.** 4.3 proves the rewrite did not damage
anything we still need.

---

## 5 · What I recommend

1. **Do it, and do it now.** One clone, zero installs, one person to coordinate
   with. Every collaborator added multiplies the cost, and the decision to add
   them is already taken.
2. **Delete and re-create the remote** rather than filing a GC request. It is the
   only route with a definite outcome, and at this size it is a five-minute job.
3. **Take the mirror backup in 3.1 and keep it until you are satisfied** — it is
   the difference between a reversible operation and a one-way door. It contains
   the funnel, so store it where the key lives, not in a synced folder.
4. **Do not treat this as closing R17.** The payroll file is still readable by
   the service account and still lands in `.drive-cache/` on every run. Different
   problem, still open.

---

## 6 · What I need from you

- [ ] **Approve the rewrite**, or say to leave history alone.
- [ ] **Confirm the three-file scope** — stripping paths entirely, losing the
      ability to inspect a historical graph.
- [ ] **Decide remote handling** — delete-and-recreate (recommended) or a GitHub
      support request.
- [ ] Confirm nobody has cloned since this started. If someone has, tell me and
      the plan needs a coordination step.

I will not run any of §3 until all four are answered.
