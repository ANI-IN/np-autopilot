# THE WINDOW — Phase C + Phase D in one sitting

**Owner decision, Animesh Kumar, 2026-09-30 (origin: hand): migrations → deploy
→ projection**, so the old code never runs against the new data. Starts only
after the owner has ticked `docs/ACCEPTANCE-CHECKLIST.md` (HANDOFF §D.3).
Every command below was rehearsed on 2026-09-30 against a copy of production
(`~/.config/np-autopilot/rehearsal/`, outside both sync roots — R22). Times are
**measured** in the rehearsal (local) or by read-only probes of production.

## Figures this plan rests on

| | measured | production estimate |
|---|---:|---:|
| full `pg_dump` of production, over the network (read-only) | **22.2 s** | backup step ≈ 20–25 s |
| backup of the projection + curation tables (rehearsal, local) | 1 s | ≈ 20–25 s |
| migrations 0017–0021 up / down (rehearsal) | < 1 s / 1 s | a few seconds |
| **projection** (rehearsal, local): wall / inside the transaction | **5.4 s / 3.5 s** | **≈ 10–20 s** — its COPY payload is 17.1 MB and production took uploads at **4.5–6.1 MB/s** (three read-only probes), so +3–4 s, plus round trips |
| **restore from backup** (rehearsal, local) | **2 s** | ≈ 5–10 s |
| **reads blocked** (the projection's TRUNCATE lock) | — | **≈ 10–20 s**, once |
| old code on new data | — | **none, server side** (this order) |
| new code on old data (deploy live → projection committed) | rehearsed: every endpoint 200, page settles by simulation, no console errors | ≈ 2–3 min |

Rehearsal verdicts: migrations roll back to a schema **identical** to
production's (compared as statement sets); the restore brings back production's
content hash `eba7c479…` and every count; the deployed code (`4767d12`) answers
200 on every endpoint at 0016 and at 0021, on old and on restored data;
verification after projection: `verify_migration` 54/54, curation IN SYNC,
curation counts unchanged, `stats.json` = database = merged public graph (8,507).

## Before starting

```bash
cd ~/Desktop/NP-Autopilot-Corpus && git checkout main && git pull --ff-only
python3 pipeline/check_repo_private.py              # must say private
vercel inspect np-autopilot.vercel.app | grep -E " id|created"
#   must still be dpl_5wWZxv7ed1Bhq1fvCMSMVPgnfmxg (2026-09-19) — the ONE
#   deployment `vercel rollback` can reach on Hobby. If it is not, STOP.
set -a && . ~/.config/np-autopilot/env && set +a
export WINDOW_DSN="$SUPABASE_DB_URL_SESSION"        # never echo it
B=~/.config/np-autopilot/window-$(date +%Y%m%d-%H%M); mkdir -m 700 "$B"
```

The prebuilt artifact is `/tmp/np-deploy-<main sha>/` (built from `main`,
`public/stats.json` = the rehearsal projection of the identical graph:
8,507 nodes / 12,187 edges). The last-resort old build is
`/tmp/np-deploy-4767d12/`.

## The steps

| # | do | check | if it fails |
|---|---|---|---|
| 1 | `db/window/backup.sh "$B"` then `python3 pipeline/migrate.py status > "$B/migrate-before.txt"` | `counts-before.txt`: migration 0016, nodes 3146, edges 4021, node_sources 30658, hash `eba7c479…` | nothing has changed — stop |
| 2 | `python3 pipeline/migrate.py up` | status ends at **0021** | `python3 pipeline/migrate.py down --to 0016` (rehearsed: exact) |
| 3 | **owner signs in with Google** at np-autopilot.vercel.app (0020 changed the sign-in hook's grants) | signed in, sees the old explorer | `python3 pipeline/migrate.py down --to 0019` (reverts 0021 and 0020), then decide |
| 4 | `cd /tmp/np-deploy-<sha> && vercel deploy --prebuilt --prod` | `/api/config` 200; `/api/me`, `/api/overview`, `/api/structure` **401** unauthenticated; the six security headers; live `index.html` == the artifact's | `vercel rollback dpl_5wWZxv7ed1Bhq1fvCMSMVPgnfmxg` (Hobby: the immediately previous deployment — do not deploy anything else in between). Last resort: `cd /tmp/np-deploy-4767d12 && vercel deploy --prebuilt --prod` |
| 5 | `NP_LANDING_STATS="$B/stats.json" NP_BUILD_LOG="$B/BUILD_LOG.md" python3 pipeline/project_graph.py` | nodes 8,507, edges 12,187, sources 39,405, layout 3,307; ≈ 10–20 s | `db/window/restore_projection.sh "$B"` — the ONLY way back (the old `project_graph.py` cannot run after 0021); the new code on the old data is safe |
| 6 | `python3 pipeline/verify_migration.py --source supabase`; `python3 pipeline/curation.py check`; `psql "$WINDOW_DSN" -f db/window/counts.sql`; `cp "$B/stats.json" public/stats.json`; `NP_ALLOW_PROD_TESTS=1 python3 -m pytest tests -m production_only -rs` | 54/54; IN SYNC; curation counts == `counts-before.txt`; 7 production_only pass (read-only, verified) | `restore_projection.sh "$B"` |
| 7 | owner: open **API Design** (full chain, 13 Class decks), the **matrix**, a search; `curl -s https://np-autopilot.vercel.app/ > "$B/live.html" && node eval/drive_dom.mjs "$B/live.html"`; `python3 eval/measure_signed_in.py --phase post --wait-for-enter` (includes cold start after idle) | panels correct; harness passes; figures recorded against `docs/PERF-BASELINE.md` | step 4's rollback and/or step 5's restore |

**At step 7 the owner tells the team: reload any open explorer tab.** An open
tab keeps the old page's code until it reloads — search results it cannot
draw, expansions that look empty, "7 of 42 domains have no owner" (the old
code on the new data, assessed 2026-09-30).

## Old links that stop resolving — 38 ids, all merged

Links and bookmarks to these ids show "not found" after step 5. Nothing was
lost: each was **merged** into the node on the right (MOD-01…16, the INS bulk,
INS-05/06, PPL-11), which carries its label in `label_raw`/`merged_label_raw`
and its provenance.

| old id | type | old label | now part of |
|---|---|---|---|
| `ins_b103d22a9401822f` | instructor | Adam Toth | `ins_6ddbd76f4b6efb30` · Adam Toth |
| `ins_ed9a2409c285941e` | instructor | Ashish Kaila | `ins_1c6b316a16b31ba9` · Ashish Kaila |
| `ins_ea8b37dd1a1a1166` | instructor | Balaji Santhanam | `ins_e3edf7b011df3d55` · Balaji Santhanam |
| `ins_5f2170079e27d87e` | instructor | Balaram Velaga | `ins_0a526aa3ed6d43f0` · Balaram Velaga |
| `ins_a504e3325f7d5114` | instructor | Bharath Anand | `ins_17a0f3c40b4bf4fa` · Bharath Anand |
| `ins_dd2bf7d882b9359d` | instructor | Cathy Ma | `ins_c8317159ba08919f` · Cathy Ma |
| `ins_d9a8c2468008e3c6` | instructor | Daniel Grundel | `ins_883322ecf38c31bb` · Daniel Grundel |
| `ins_6e7add4587173a34` | instructor | David Prorok | `ins_3231ad1eb02fb068` · David Prorok |
| `ins_73e967b7d4b13926` | instructor | Evgeny Vinnik | `ins_297b39d617b13001` · Evgeny Vinnik |
| `ins_c283d464ff7f76e5` | instructor | Faraaz Sareshwala | `ins_7ac87e39682af9e0` · Faraaz Sareshwala |
| `ins_1d140745262f4c7c` | instructor | Hetal Modi | `ins_0914f216e7304361` · Hetal Modi |
| `ins_fa82122308a2f641` | instructor | Jeff Wisman | `ins_7c1961b0e4158881` · Jeff Wisman |
| `ins_97423b20b30fbc1a` | instructor | Konstantinos Pappas | `ins_3ba3964184d6332f` · Konstantinos Pappas |
| `ins_e10ae74290feeb53` | instructor | Nikhil Kolekar | `ins_300c95f7134d7361` · Nikhil Kolekar |
| `ins_745123d8291203a6` | instructor | Reginald Johnson | `ins_35544f20330c6c3e` · Reginald Johnson |
| `ins_6a63f263bd74c8c9` | instructor | Robert Kreznarich | `ins_30f246594b8e08b0` · Robert Kreznarich |
| `ins_fea798387b2c268c` | instructor | Rodrigo Salazar | `ins_94f6b3d670f9f7b8` · Rodrigo Salazar |
| `ins_f4f3a987f5bb6258` | instructor | Sergey Togulev | `ins_07fc46ceb073ed3c` · Sergey Togulev |
| `ins_d813c2ac7a4799ae` | instructor | Shelby Cohen | `ins_533023562b8a9de0` · Shelby Cohen |
| `ins_fcf1aad6762b290a` | instructor | Thong Tran | `ins_318ca9dc445306e4` · Thong Tran |
| `mod_720627d346304074` | module | API Design | `mod_150eb79c4ec6f254` · API Design |
| `mod_634b876cf02fa5b1` | module | API Design and Implementation | `mod_e5f708116a4b7fac` · API Design and Implementation |
| `mod_35b3d005d7cf83cb` | module | API testing | `mod_a036b35b54865c2a` · API Testing |
| `mod_336de92bd7833acc` | module | Automation Testing | `mod_e3865bea05ed325a` · Automation Testing |
| `mod_9126f0641fdf336a` | module | Cloud Native Design | `mod_44e86d468ffa62f5` · Cloud Native Design |
| `mod_83f6f7e2dec851c0` | module | Cloud Testing | `mod_b1feb3161efd9eaa` · Cloud Testing |
| `mod_e70fca39091d2c9a` | module | Concurrency | `mod_68672ce55043c450` · Concurrency |
| `mod_4626b0a141705837` | module | Database Design | `mod_36793b37f57c09a0` · Database Design |
| `mod_508b16ecef815eec` | module | Databases | `mod_0bc009fd274eea44` · Databases |
| `mod_d6fd916a4165de90` | module | Frontend System Design | `mod_0d3e49f1778b9090` · Frontend System Design |
| `mod_b8ddd79028eb4371` | module | Leveling Up with Advanced JavaScript and CSS | `mod_bb30095a76e9b5c6` · Leveling Up with Advanced JavaScript and CSS |
| `mod_92a2658d64f95888` | module | Object Modeling | `mod_cefc969d84e291e5` · Object Modeling |
| `mod_e751e5c1931a40aa` | module | Quality Engineering Foundations | `mod_2e4842a29bc521ba` · Quality Engineering Foundations |
| `mod_5d19862e4bb533a7` | module | Test Automation Design Patterns Assignment Review Class | `cla_0eec30ac7f4a5a09` · Test Automation Design Patterns - Assignment Review Class |
| `mod_e3dcb2d72d8960bb` | module | Test Automation Design Patterns Class | `cla_f2e029b9ee04abc6` · Test Automation Design Patterns - Class |
| `mod_09595755ccfd3591` | module | UI & DOM | `mod_50a33a8e184e6849` · UI & DOM |
| `mod_f22ff2920b64b2e2` | module | UI System Design | `mod_b591bcb07c5eb33b` · UI System Design |
| `mod_1a312401f6cfe8ac` | module | Week 5 - Test Automation | `mod_1262237b9b72b360` · Test Automation Design Patterns |

## After the window

- Commit `public/stats.json` (step 6 copied production's) and mark HANDOFF §D.4
  done with the deployment id, the timings and the `--phase post` figures.
- **Delete the rehearsal copy of production**: `rm -rf ~/.config/np-autopilot/
  rehearsal` and `psql postgresql://supabase_admin:postgres@127.0.0.1:54322/postgres
  -c "drop database rehearsal"`. Delete `/tmp/np-deploy-*`.
- Keep `$B` (the window backup — it is a copy of production) only until the
  owner accepts the live site, then delete it.
- Then HANDOFF §D.5 (R22): move the repo, remove the cloud copies, rotate the
  database password **and redeploy** — after which the rollback target is the
  new build, not `dpl_5wWZ…`.
