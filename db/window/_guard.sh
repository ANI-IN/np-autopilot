# Sourced by the window scripts. Refuses an output/input directory inside the
# repository or under a synced folder (docs/operations/risk-register.md R22): a copy of production
# must never land where iCloud or the Drive backup would carry it off.
guard_dir() {
  local d; d="$(cd "$1" 2>/dev/null && pwd -P)" || { echo "REFUSED: $1 does not exist"; exit 2; }
  local repo; repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
  for bad in "$repo" "$HOME/Desktop" "$HOME/Documents" "$HOME/Library/Mobile Documents"; do
    bad="$(cd "$bad" 2>/dev/null && pwd -P)" || continue
    case "$d/" in "$bad"/*) echo "REFUSED: $d is under $bad (repo or synced folder, R22)"; exit 2;; esac
  done
  [ "$(stat -f %Lp "$d")" = "700" ] || { echo "REFUSED: $d must be mode 700"; exit 2; }
}
need_dsn() { [ -n "${WINDOW_DSN:-}" ] || { echo "REFUSED: set WINDOW_DSN (never printed)"; exit 2; }; }
