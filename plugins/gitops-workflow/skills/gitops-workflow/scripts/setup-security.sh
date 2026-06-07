#!/usr/bin/env bash
set -euo pipefail

# setup-security.sh - One-shot bootstrap for sensitive-data security in a target repo.
#
# Usage:
#   bash scripts/setup-security.sh [--repo <path>] [--force] [--no-hooks] [--no-ci]
#
# Behavior:
# - Installs managed pre-commit hook via install-hooks.sh (default on).
# - Installs/updates .github/gitleaks.toml and .github/workflows/sensitive-scan.yml.
# - Refuses to overwrite existing differing files unless --force is set.

EXIT_SETUP=2

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"

REPO_PATH="$(pwd -P)"
FORCE="false"
SETUP_HOOKS="true"
SETUP_CI="true"
JSON="false"
declare -a INSTALLED_ITEMS=()

die() {
  echo "Error: $1" >&2
  exit "${2:-1}"
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1" "$EXIT_SETUP"
}

require_opt_value() {
  local opt="$1"
  local val="${2:-}"
  if [[ -z "$val" || "$val" == --* ]]; then
    die "option '$opt' requires a value" "$EXIT_SETUP"
  fi
}

print_help() {
  cat <<'USAGE'
Usage:
  bash scripts/setup-security.sh [--repo <path>] [--force] [--no-hooks] [--no-ci] [--json]

Options:
  --repo <path>  Target git repository path (default: current directory)
  --force        Overwrite existing differing files and replace non-managed hook
  --no-hooks     Skip managed pre-commit hook installation
  --no-ci        Skip .github workflow/config installation
  --json         Emit machine-readable JSON on success
  -h, --help     Show this help text
USAGE
}

emit_result() {
  local repo="$1"
  local force="$2"
  local hooks="$3"
  local ci="$4"
  if [[ "$JSON" == "true" ]]; then
    python3 - "$repo" "$force" "$hooks" "$ci" "${INSTALLED_ITEMS[@]}" <<'PY'
import json
import sys

repo, force, hooks, ci, *items = sys.argv[1:]
print(json.dumps({
    "status": "completed",
    "repo": repo,
    "force": force == "true",
    "hooks": hooks == "true",
    "ci": ci == "true",
    "items": items,
}))
PY
  else
    echo "✅ security bootstrap complete for repo: $repo"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      require_opt_value "--repo" "${2:-}"
      REPO_PATH="${2:-}"
      shift 2
      ;;
    --force)
      FORCE="true"
      shift
      ;;
    --no-hooks)
      SETUP_HOOKS="false"
      shift
      ;;
    --no-ci)
      SETUP_CI="false"
      shift
      ;;
    --json)
      JSON="true"
      shift
      ;;
    -h|--help)
      print_help
      exit 0
      ;;
    *)
      die "unknown argument: $1" "$EXIT_SETUP"
      ;;
  esac
done

require_cmd git

if ! git -C "$REPO_PATH" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  die "--repo is not a git repository: $REPO_PATH" "$EXIT_SETUP"
fi

copy_managed_file() {
  local src="$1"
  local dst="$2"
  local label="$3"

  mkdir -p "$(dirname "$dst")"
  if [[ -f "$dst" ]]; then
    if cmp -s "$src" "$dst"; then
      if [[ "$JSON" != "true" ]]; then
        echo "✓ $label already up to date: $dst"
      fi
      return 0
    fi
    if [[ "$FORCE" != "true" ]]; then
      die "$label exists and differs at $dst; rerun with --force to overwrite" "$EXIT_SETUP"
    fi
  fi

  cp "$src" "$dst"
  INSTALLED_ITEMS+=("$label:$dst")
  if [[ "$JSON" != "true" ]]; then
    echo "Installed $label: $dst"
  fi
}

if [[ "$SETUP_HOOKS" == "true" ]]; then
  HOOK_ARGS=(bash "$SKILL_ROOT/scripts/install-hooks.sh" --repo "$REPO_PATH")
  if [[ "$FORCE" == "true" ]]; then
    HOOK_ARGS+=(--force)
  fi
  if [[ "$JSON" == "true" ]]; then
    "${HOOK_ARGS[@]}" >/dev/null
  else
    "${HOOK_ARGS[@]}"
  fi
  INSTALLED_ITEMS+=("hook")
fi

if [[ "$SETUP_CI" == "true" ]]; then
  SRC_GITLEAKS="$SKILL_ROOT/assets/config/gitleaks.toml"
  SRC_WORKFLOW="$SKILL_ROOT/assets/github/workflows/sensitive-scan.yml"
  DST_GITLEAKS="$REPO_PATH/.github/gitleaks.toml"
  DST_WORKFLOW="$REPO_PATH/.github/workflows/sensitive-scan.yml"

  [[ -f "$SRC_GITLEAKS" ]] || die "missing source config: $SRC_GITLEAKS" "$EXIT_SETUP"
  [[ -f "$SRC_WORKFLOW" ]] || die "missing source workflow: $SRC_WORKFLOW" "$EXIT_SETUP"

  copy_managed_file "$SRC_GITLEAKS" "$DST_GITLEAKS" "gitleaks config"
  copy_managed_file "$SRC_WORKFLOW" "$DST_WORKFLOW" "sensitive-scan workflow"
fi

emit_result "$REPO_PATH" "$FORCE" "$SETUP_HOOKS" "$SETUP_CI"
