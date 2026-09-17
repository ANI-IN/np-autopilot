"""`/*.json` is deny-by-default at the repo root. Make its misses LOUD.

THE TENSION, stated because both halves are real:

  * The rule exists because a live Google service-account key was found sitting
    at the repo root, mode 0644, unignored. A blanket glob is the right defence
    against a key whose filename nobody predicted.
  * The same glob silently swallowed `vercel.json`. Vercel reads its
    configuration from the repository, so that would have deployed the app with
    no CSP, no HSTS and no frame-options — a site that comes up, looks correct,
    and is unprotected.

Measured blast radius: the glob also matches `package.json`,
`package-lock.json`, `tsconfig.json`, `turbo.json`, `now.json`, `manifest.json`,
`renovate.json`, `.eslintrc.json`, `jsconfig.json`, `components.json` and
`biome.json`. This repo already has a Node harness (`eval/drive_dom.mjs`) and a
Vercel deployment, so `package.json` is not hypothetical.

THE FIX IS NOT TO WEAKEN THE GLOB. Removing it, or pre-emptively excepting a
list of names someone guessed, both trade a loud failure for a quiet one. The
glob stays deny-by-default; this test makes a miss impossible to not notice.

So every root-level .json must be one of:
  * tracked by git — someone decided it belongs, and added the `!` exception
  * named below as deliberately ignored, with the reason

A file that is neither fails here, naming itself. A dropped key still does not
reach a commit; it just stops being invisible.

This is A.7b in a config file: a guard that fails by producing a site that looks
correct is indistinguishable from the protection it was meant to provide.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

#: Root-level .json files that SHOULD be ignored, and why. Adding a name here is
#: a decision someone made on purpose; the test is what forces it to be made.
DELIBERATELY_IGNORED: dict[str, str] = {
    # Nothing yet. A service-account key dropped here would appear as a failure
    # naming the file, which is the point — it must not sit unnoticed even
    # though .gitignore is correctly keeping it out of a commit.
}


def _tracked(rel: str) -> bool:
    return subprocess.run(["git", "ls-files", "--error-unmatch", rel],
                          cwd=REPO, capture_output=True).returncode == 0


def _ignored(rel: str) -> bool:
    return subprocess.run(["git", "check-ignore", "-q", rel],
                          cwd=REPO, capture_output=True).returncode == 0


def test_no_root_json_is_silently_ignored():
    """A root .json is tracked, or declared ignored on purpose. Never neither."""
    silent = []
    for path in sorted(REPO.glob("*.json")):
        rel = path.name
        if _tracked(rel):
            continue
        if rel in DELIBERATELY_IGNORED:
            continue
        silent.append(rel)
    assert not silent, (
        "these root-level .json files are ignored and untracked, so nothing "
        f"would notice them: {silent}\n"
        "  If it is CONFIG the deployment needs, add `!/<name>` to .gitignore "
        "and commit it — an ignored vercel.json deploys with no security "
        "headers and still looks correct.\n"
        "  If it is a CREDENTIAL, move it out of the repo (see "
        "~/.config/np-autopilot/) and do not except it.\n"
        "  If it is genuinely local scratch, add it to DELIBERATELY_IGNORED "
        "in this file with the reason.")


def test_vercel_config_is_tracked_and_the_exception_is_real():
    """Both halves: the rule no longer matches it, AND git actually has it.

    Checked separately because they fail differently. A missing `!` exception
    means git never sees the file; a present exception with the file never
    committed means git still never sees it. The deployment cannot tell those
    apart and neither could a reader.
    """
    assert not _ignored("vercel.json"), (
        "vercel.json is matched by an ignore rule — the `!/vercel.json` "
        "exception in .gitignore is missing or has been overridden by a later "
        "rule (order matters: a later match wins)")
    assert _tracked("vercel.json"), (
        "vercel.json is not tracked. Vercel reads config from the repository, "
        "so the deployment would carry no CSP, HSTS or frame-options headers "
        "and would look entirely correct.")


def test_the_glob_still_protects_against_an_unguessed_key_name():
    """The other half of the tension: the guard must still guard.

    If someone 'fixes' the blast radius by deleting `/*.json`, a service-account
    key with an unanticipated filename becomes committable again — which is the
    incident this rule was written after.
    """
    assert _ignored("some-unanticipated-credential.json"), (
        "an arbitrary root-level .json is no longer ignored. The `/*.json` rule "
        "has been removed or weakened, and a service-account key with an "
        "unguessed filename is now committable — that is the incident the rule "
        "exists for.")


def test_critical_manifests_are_tracked():
    """The files whose absence changes behaviour without failing anything."""
    for rel in (".claude-plugin/plugin.json", "vercel.json", "requirements.txt",
                ".github/workflows/ci.yml", "config/taxonomy.yaml"):
        assert _tracked(rel), f"{rel} is not tracked by git"


def test_no_tracked_file_is_shadowed_by_an_ignore_rule():
    """A rule added later can shadow a file already committed.

    Git keeps serving the tracked copy, so nothing breaks locally — but a fresh
    clone plus any tooling that respects .gitignore sees a different tree. The
    divergence is invisible until it isn't.
    """
    files = subprocess.run(["git", "ls-files"], cwd=REPO,
                           capture_output=True, text=True).stdout
    shadowed = subprocess.run(["git", "check-ignore", "--stdin", "-v"],
                              cwd=REPO, input=files,
                              capture_output=True, text=True).stdout.strip()
    # `!/vercel.json` is a negation and legitimately reports as a match.
    real = [ln for ln in shadowed.splitlines() if ln and ":!" not in ln]
    assert not real, "tracked files shadowed by an ignore rule:\n" + "\n".join(real)
