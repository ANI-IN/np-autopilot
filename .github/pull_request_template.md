## What and why

<!-- What changes, and the problem it solves. Link the issue if there is one. -->

## How it was tested

<!-- Commands run and their results. Browser tests: which files, one at a time. -->

## Rollback

<!-- How to undo this in production: a revert, a .down.sql, a variable such as NP_MAP_SOURCE=old or KB_SYNC_ENABLED=false. "Revert the merge" is fine when that is all it takes. -->

## Checklist

- [ ] `bash scripts/verify_all.sh` passes: no new failures against `docs/baseline-failures.txt`
- [ ] Browser tests run one file at a time, if the UI changed
- [ ] New or changed behaviour has a test
- [ ] Every migration has a `.down.sql`, and both were applied locally
- [ ] Docs updated (README, `docs/`, the in-app Guide `public/kb/guide.md`); `python scripts/check_md_links.py` passes
- [ ] No secrets, real data, `backups/` or generated files in the diff
- [ ] Nothing here connects to production or changes Production settings
