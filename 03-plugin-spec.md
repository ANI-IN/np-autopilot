# 03 — Claude Code Plugin Specification (verified against current docs)

**Verified:** 2026-09-09. I did not rely on training data for any claim below; every item cites the page I read.

**Sources**
- **[REF]** Plugins reference — https://code.claude.com/docs/en/plugins-reference
- **[CRE]** Create plugins — https://code.claude.com/docs/en/plugins
- **[MKT]** Plugin marketplaces — https://code.claude.com/docs/en/plugin-marketplaces
- **[DEP]** Plugin dependencies — https://code.claude.com/docs/en/plugin-dependencies
- **[SKL]** Skills — https://code.claude.com/docs/en/skills

> Note: `docs.claude.com/en/docs/claude-code/*` now **301-redirects** to `code.claude.com/docs/en/*`. Any bookmark or script using the old host needs updating.

---

## ⚠ Where the current docs contradict the brief

### 1. Plugin-to-plugin dependencies **are supported**. The brief is wrong.

The brief says:

> Whether plugin-to-plugin dependencies are supported yet. **I believe they are not, and that there is an open feature request.**

**They are fully supported, and have a dedicated documentation page.** [DEP] `plugin.json` accepts a `dependencies` array:

```json
{
  "name": "deploy-kit",
  "version": "3.1.0",
  "dependencies": [
    "audit-logger",
    { "name": "secrets-vault", "version": "~2.1.0" }
  ]
}
```

Supported today: semver range constraints (`~2.1.0`, `^2.0`, `>=1.4`, `=2.1.0`); automatic install of dependencies; range **intersection** across several dependents; cross-marketplace dependencies gated by an `allowCrossMarketplaceDependenciesOn` allowlist in `marketplace.json`; a bundle pattern where a manifest is *only* a `dependencies` array; `claude plugin prune` to remove orphans; and tag-based version resolution using the convention `{plugin-name}--v{version}` via `claude plugin tag --push`. [DEP]

Error codes are documented: `dependency-unsatisfied`, `range-conflict`, `dependency-version-unsatisfied`, `no-matching-tag`. [DEP]

**Impact on your §1.3 decision:** the "split later" cost is lower than you assumed. This does **not** change my recommendation — build one plugin — but it changes the *reason*. See §1.3 re-analysis below.

### 2. The "duplicate the knowledge folder per plugin" claim is only half right.

The brief says:

> Claude Code plugins cannot reference files outside their own plugin directory, so **every plugin needs its own duplicate copy of the knowledge folder**, its own version bump on every refresh, and its own install step.

- **"Cannot reference files outside the plugin directory"** — ✅ **Confirmed**, see §6.
- **"Every plugin needs its own duplicate copy"** — ⚠ **Not exactly.** [REF] documents an explicit exception: *"Symlinks within the same marketplace are dereferenced and copied into cache. This allows meta-plugins to link to skills from sibling plugins."* So within one marketplace you maintain **one** source copy and symlink; Claude Code copies it into cache at install. You get a duplicate on disk, but **not a duplicate to maintain**.
- **"Its own install step for every teammate"** — ⚠ **No longer true**, given `dependencies`: a bundle plugin installs the whole set in one command. [DEP]

**Verified by the reference implementation:** `acceler-presales-plugin` ships **two** plugins from **one** repo and **one** `marketplace.json` (`source: "./"` and `source: "./post-sales"`). The second plugin carries **no** `knowledge/` folder at all. Splitting cost them nothing because the second plugin does not query the graph.

### 3. `version` is optional, and so is `plugin.json` itself.

The brief's B1 layout implies both are mandatory. [REF] states **only `name` is required**. The manifest is listed as *"Optional"* if components use default locations. [REF]

I still recommend setting `version` explicitly — see §8, it is what gates updates.

---

## 1. `.claude-plugin/plugin.json` — exact structure

**Location:** `.claude-plugin/plugin.json` at the plugin root. [REF]
**Only `plugin.json` goes inside `.claude-plugin/`.** [CRE] warns explicitly: *"Don't put `commands/`, `agents/`, `skills/`, or `hooks/` inside the `.claude-plugin/` directory."*

| Field | Required | Type | Notes [REF] |
|---|---|---|---|
| `name` | **Yes** | string | Unique, kebab-case, no spaces/control chars. **Used for namespacing.** |
| `displayName` | No | string | Falls back to `name`. |
| `version` | No | string | Semver. Pins the plugin; gates updates. |
| `description` | No | string | Shown in the plugin manager. |
| `author` | No | object | `{name, email, url}` |
| `homepage`, `repository`, `license` | No | string | |
| `keywords` | No | array | |
| `metadata` | No | object | Free-form; **Claude Code ignores it**. Non-object values warn. |
| `defaultEnabled` | No | boolean | Default `true`. |
| `skills` | No | string \| array | **Adds to** `skills/`, never replaces. Paths relative, start `./`. |
| `commands` | No | string \| array | **Replaces** default `commands/`. |
| `agents` | No | string \| array | **Replaces** default `agents/`. |
| `workflows` | No | string \| array | **Replaces** `workflows/`. |
| `hooks` | No | string \| array \| object | Path(s) or inline JSON. |
| `mcpServers` | No | string \| array \| object | Path(s) or inline. |
| `outputStyles` | No | string \| array | **Replaces** `output-styles/`. |
| `lspServers` | No | string \| array \| object | |
| `experimental.themes` / `.monitors` | No | string \| array | |
| `userConfig` | No | object | Values prompted at enable time; supports `type`, `title`, `description`, `sensitive`, `required`, `default`, `multiple`, `min`/`max`. |
| `channels` | No | array | Each needs `server`. |
| `dependencies` | No | array | See §11. |

**Unrecognised top-level fields are ignored** and reported by `claude plugin validate` as **warnings, not errors**; `--strict` promotes them. Near-miss field names get a "did you mean" suggestion. [REF]

---

## 2. `.claude-plugin/marketplace.json` — exact structure

**Location:** `.claude-plugin/marketplace.json` **at the repository root**. [MKT]

**Root fields:**

| Field | Required | Type | Notes |
|---|---|---|---|
| `name` | **Yes** | string | kebab-case. Users reference it as `@marketplace-name`. |
| `owner` | **Yes** | object | `name` required; `email`, `url` optional. |
| `plugins` | **Yes** | array | Plugin entries. |
| `$schema` | No | string | `https://code.claude.com/schemas/marketplace.json`. Ignored at load. |
| `description`, `version` | No | string | |
| `metadata.pluginRoot` | No | string | Resolves bare source names (v2.1.239+). |
| `allowCrossMarketplaceDependenciesOn` | No | array | Allowlist for cross-marketplace deps. |
| `renames` | No | object | Old name → new name, or `null` for removal (v2.1.193+). |

**Plugin entry:** `name` (**required**, kebab-case) and `source` (**required**, string or object) — plus optional `displayName`, `description`, `version`, `author`, `homepage`, `repository`, `license`, `keywords`, `category`, `tags`, `strict` (default `true`), `defaultEnabled`, `skills`/`commands`/`agents`/`hooks`/`mcpServers`/`lspServers`, `headers`/`headersHelper` (v2.1.238+), `metadata`. [MKT]

**Source types** [MKT]: relative path (`"./plugins/x"`, must start `./`); `github` (`repo`, optional `ref`/`sha`); `url` (generic git); `git-subdir` (`url` + `path`, sparse checkout); `npm` (`package`, `version`, `registry`); `archive` (HTTPS zip, ≤256 MiB, optional `sha256`, v2.1.224+); `command` (v2.1.229+).

**Reserved marketplace names** that will be rejected include `claude-plugins-official`, `claude-code-plugins`, `anthropic-plugins`, `agent-skills`, and anything impersonating an official source. [MKT] `np-autopilot` is safe.

---

## 3. Where commands live, format, and namespace derivation

- **`commands/`** at the plugin root — **flat `.md` files**. [REF]
- **`skills/`** at the plugin root — `<skill-name>/SKILL.md` directories. [REF]
- [CRE] is explicit that these are now the same mechanism and recommends skills: *"`commands/` — Skills as flat Markdown files. **Use `skills/` for new plugins**."*

**Namespace:** `/<plugin-name>:<skill-or-command-name>`. The folder name (for skills) or filename (for commands) supplies the second half; `name` in `plugin.json` supplies the first. [CRE]: *"Plugin skills are always namespaced (like `/my-first-plugin:hello`) to prevent conflicts."*

So your six commands will be `/np-autopilot:setup`, `/np-autopilot:workflow`, and so on. **Worth knowing before you pick a plugin name — it is a prefix your team types every time.**

Single-skill plugins may put `SKILL.md` at the plugin root. [REF] Not our case.

---

## 4. `SKILL.md` frontmatter and activation

Frontmatter is parsed **only if the opening `---` is the file's first line**; otherwise the whole file (markers included) is treated as content. [SKL] — an easy and silent mistake.

| Field | Required | Notes [SKL] |
|---|---|---|
| `name` | No | Display name. Defaults to directory name. |
| `description` | **Recommended** | *"Claude uses this to decide when to apply the skill."* Falls back to the first paragraph. |
| `when_to_use` | No | Extra trigger phrasing; appended to `description`. |
| `argument-hint` | No | Autocomplete hint, e.g. `[issue-number]`. |
| `arguments` | No | Named positional args for `$name` substitution. |
| `disable-model-invocation` | No | `true` = manual-only; not offered to the model. |
| `user-invocable` | No | `false` = hidden from `/` menu; model may still use it. |
| `allowed-tools` / `disallowed-tools` | No | Scoped to the invoking turn only. |
| `model`, `effort` | No | Override for while the skill is active. |
| `context: fork`, `agent`, `background` | No | Run in an isolated forked subagent. |
| `paths` | No | Globs; auto-load only when working on matching files. |
| `hooks`, `metadata`, `license`, `compatibility`, `shell` | No | |

**How a skill is selected** [SKL]:
1. Skill **descriptions** are loaded into context every turn as a listing.
2. Claude matches the request against `description` + `when_to_use`.
3. **The combined text is truncated at 1,536 characters**, and the whole listing is capped at ~1% of the context window (`skillListingBudgetFraction`).

**Design consequence for us:** description quality *is* the routing logic. Put the distinguishing use case in the first sentence of each of our six skills, and keep the six descriptions mutually distinct — `workflow`, `precedent` and `coverage` will otherwise collide.

**Progressive disclosure** [SKL]: only `SKILL.md` auto-loads. Sibling files (`reference.md`, `scripts/`) load on demand when referenced. Guidance: *"Keep `SKILL.md` under 500 lines."*
**Lifecycle:** invoked skill content persists across turns; after auto-compaction, skills are re-attached keeping the first 5,000 tokens each, 25,000 total.

---

## 5. How `knowledge/` is loaded and referenced

There is **no special data-folder mechanism.** A `knowledge/` directory is just files in the plugin. Two ways to reach them:

1. **Relative reference from `SKILL.md`** — a Markdown link (`[INDEX](../../knowledge/INDEX.md)`) that Claude reads on demand. Simplest.
2. **`${CLAUDE_PLUGIN_ROOT}`** — [REF] *"Resolves to: Absolute path to the plugin's installation directory."* Substituted in skill/agent content, hook and monitor commands, MCP `command`/`args`/`env`, and LSP configs. **This is the "single configurable path variable" the brief asks for in §1.3.**

**Two warnings that change our design:**

- [REF]: *"**Changes when plugin updates.** The previous version's directory remains briefly (grace period ~14 days). **Treat it as ephemeral and don't write persistent state there.**"* → `graph.json` is *read-only bundled data*, so `${CLAUDE_PLUGIN_ROOT}` is correct. But **nothing may write back into `knowledge/` at runtime.**
- `${CLAUDE_PLUGIN_DATA}` (`~/.claude/plugins/data/{id}/`) is the documented home for persistent state across updates. If eval results or a query cache ever need to persist, they go there — **not** in `knowledge/`.

---

## 6. The rule on paths outside the plugin directory — confirmed

**You were right.** [REF] "Path Traversal Restrictions":

> **Claude Code rejects:**
> - Component paths that resolve **outside the plugin root**
> - Symlinks that lead **outside the plugin** (except within same marketplace)
> - Paths like `../shared-utils`
>
> **Error message:** `"path escapes plugin directory"`
>
> **Result:** Plugin loads without that component

**One nuance worth internalising:** the plugin **still loads** — it just silently lacks that component. It does not hard-fail. That is a quiet failure mode, and it is exactly the kind of thing `claude plugin validate` exists to catch (it checks path-traversal violations).

**Exception:** symlinks *within the same marketplace* are dereferenced and copied into cache. [REF]

Also: *"The plugin root is the individual plugin's own directory… It is never `~/.claude/`."* [CRE]

---

## 7. Directory layout that the spec actually requires

```
np-autopilot/                     ← plugin root AND marketplace root
├── .claude-plugin/
│   ├── plugin.json               ← ONLY this goes in here
│   └── marketplace.json          ← marketplace lives at repo root's .claude-plugin/
├── skills/                       ← <name>/SKILL.md  (preferred over commands/)
│   └── workflow/SKILL.md
├── knowledge/                    ← plain bundled data
├── pipeline/                     ← not a plugin concept; ignored by Claude Code
└── site/, eval/, research/       ← likewise ignored
```

**This matches the brief's B1 layout.** The only change I recommend: use **`skills/<name>/SKILL.md`** rather than `commands/*.md`, per [CRE]'s "Use `skills/` for new plugins".

---

## 8. Versioning and updates — precisely what a user must do

**Version precedence** (highest first) [REF]: `version` in `plugin.json` → `version` in the marketplace entry → git tag/commit → timestamp fallback.

> *"Setting this pins the plugin to that version string, so **users only receive updates when you bump it**"* [CRE]

**To receive an update a teammate must do one of:**
- `claude plugin update <plugin>` (then `/reload-plugins`), **or**
- `/plugin marketplace update <marketplace-name>` — refreshes the marketplace, **or**
- enable auto-update for the marketplace in `/plugin`. **Auto-update is off by default for non-Anthropic marketplaces.** [DEP]

**This validates the brief's B10 concern exactly.** If `version` is not bumped, a fixed graph never reaches anyone, and *no error is shown*. The `refresh` command must bump it automatically.

**Private repos** [MKT]: auth uses existing git credential helpers (`gh auth login`, keychain, SSH agent). Background auto-update disables credential helpers for `git pull` on private repos and falls back to re-clone, which *"may timeout on large repos."* Given `knowledge/graph.json` will be multi-MB, note this. Mitigations documented: `git config --global url."https://x-access-token:TOKEN@github.com/…".insteadOf …`, or `gh auth setup-git`.

---

## 9. Validation command and what it checks

```bash
claude plugin validate ./np-autopilot
claude plugin validate ./np-autopilot --strict     # warnings become errors — use in CI
```

Checks [REF][MKT]: manifest syntax and schema; required vs optional field types; unrecognised fields (warn) and near-miss names (suggestion); **frontmatter parsing in agent files**; **path-traversal violations**; and for a marketplace directory — JSON validity, **duplicate plugin names**, local source paths exist, and a `plugin.json` in each local entry.

Output on success: `✔ Validation passed`, or `✔ Validation passed with warnings`. [CRE]

Also available: `claude --debug` (version resolution, component discovery, why a server was skipped); `claude plugin list --json` (per-plugin `errors` field); the `/plugin` **Errors** tab.

---

## 10. Local development and install commands

```bash
claude --plugin-dir ./np-autopilot           # load without installing; also accepts a .zip
/reload-plugins                              # pick up edits without restarting
claude plugin marketplace add ./np-autopilot --scope project   # local marketplace
claude plugin marketplace add ANI-IN/np-autopilot              # from GitHub (private OK)
claude plugin install np-autopilot@np-autopilot
```

A `--plugin-dir` plugin **takes precedence** over an installed plugin of the same name for that session. [CRE]

**For the brief's "two commands" definition of done**, this is the pair:
```bash
claude plugin marketplace add ANI-IN/np-autopilot
claude plugin install np-autopilot@np-autopilot
```

---

## 11. §1.3 re-analysis — one plugin, but for corrected reasons

Your conclusion stands. Two of the three stated reasons do not.

| Brief's reason to not split early | Verdict |
|---|---|
| Cannot reference files outside plugin dir | ✅ **True** — `"path escapes plugin directory"` |
| Every plugin needs a duplicate copy of `knowledge/` to maintain | ⚠ **Overstated** — same-marketplace symlinks are dereferenced at install [REF]; and the reference implementation's second plugin needs no copy at all |
| Its own install step for every teammate | ❌ **No longer true** — `dependencies` bundles installs [DEP] |

**The real reason to stay at one plugin** is the one you already gave: we start at ~6 skills, well under the 10–15 tool-rotation threshold. And the structural advice in §1.3 is right and cheap — one folder per skill, one configurable graph path (`${CLAUDE_PLUGIN_ROOT}`), audience-grouped layout. Keep all of it.

**One amendment to your split trigger:** add *"a second plugin that does not need `knowledge/`"* to the list. That split is nearly free, as the reference implementation demonstrates.
