# Security

## Reporting a problem

This is a private, internal Interview Kickstart repository. **Do not open an
issue, a pull request or a public message about a vulnerability.** Report it
privately to the repository owner (the New Programs team lead) with:

- what you found and where (file, route or screen);
- how to reproduce it, using synthetic data only;
- what you think the impact is.

If a secret may have leaked (in a commit, a log, a screenshot or a chat),
treat it as compromised: tell the owner, rotate it first, and investigate
afterwards. Rewriting git history does not un-leak a secret.

## The access model

- **Sign-in:** Google, restricted to the `interviewkickstart.com` Workspace. The
  domain is enforced in three places, and all must hold: the Supabase "before
  user created" hook, the Google `hd` claim at sign-in, and a server-side check
  of the session's address on **every request** (`web/lib/auth.py`). A valid
  session from another domain gets 403; no session gets 401.
- **Roles:** viewer, contributor, editor and admin, enforced in the database by
  row-level security, so they hold for the app, the MCP server and SQL alike.
  Admins can invite members by e-mail before their first sign-in; the last admin
  can't be removed.
- **AI access:** the MCP server uses a personal token (only its hash is stored;
  1–365 days; revocable) and acts with its owner's role. It can't grant roles,
  link accounts, approve, start a sync or delete permanently.
- **Headers:** every response carries a Content Security Policy, HSTS,
  `X-Content-Type-Options: nosniff`, `X-Frame-Options` and `Referrer-Policy`.
  There is no CORS.
- **The scheduled sync** is authorised by a secret of at least 24 characters,
  compared in constant time.

The role-by-action table and the details are in
[docs/security.md](docs/security.md). The route-by-role sweep is
`tests/test_kb_access_sweep.py`; a new route fails that test until it is listed.

## Secrets

- Values never go into the repository, a doc, a commit, a log or a screenshot.
  Only variable **names** are documented
  ([docs/operations/environment-variables.md](docs/operations/environment-variables.md)).
- Where values live: Vercel (per environment), Supabase Vault (`kb_sync_secret`),
  and your own shell or gitignored `.env` for local work.
- **Never set in Vercel:** the Supabase service-role key or the session-pooler
  URL. The app connects through the transaction pooler only.
- Nothing secret is sent to the browser: `/api/config` returns only the public
  Supabase URL, the anon key and the Google client id.
- CI scans every push for service-role keys, JWT literals, direct database
  connections and secrets in browser-visible files
  (`.github/workflows/ci.yml`), and `.githooks/pre-push` refuses to push to a
  public repository.

## Data protection

- The Drive corpus is read-only. Contact columns are never extracted, the
  payroll file is excluded, and the sensitive half of the graph (hiring
  records) is never projected publicly or committed.
- Real data stays out of the repository: tests, fixtures and docs use synthetic
  `kbtest-*@interviewkickstart.com` accounts. The local real-data copy and its
  exports live in the gitignored `backups/`.
- The audit log is append-only.

The risk register is [docs/operations/risk-register.md](docs/operations/risk-register.md).
