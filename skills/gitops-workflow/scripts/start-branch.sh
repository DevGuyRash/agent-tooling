#!/usr/bin/env bash
set -euo pipefail

# start-branch.sh - Create a new work branch from the default branch using repo policy.
#
# Usage:
#   bash scripts/start-branch.sh <type> [<slug>] [--issue <id>] [--base <branch>] [--stash-name <note>]
#
# Examples:
#   bash scripts/start-branch.sh feat add-json-output
#   bash scripts/start-branch.sh fix handle-empty-payload --issue 123
#   bash scripts/start-branch.sh chore --issue 456 --stash-name "carry local wip"
#   bash scripts/start-branch.sh docs update-readme --base main
#
# Notes:
# - Detects default branch from origin/HEAD when possible.
# - Validates branch type and slug format.
# - Uses kebab-case for slug; spaces become hyphens.
# - If working tree is dirty, stashes tracked+untracked changes before switching branches
#   and restores them after branch creation.
# - Auto-installs managed pre-commit hook by default to enforce sensitive-data scans.

ALLOWED_TYPES=("feat" "fix" "docs" "refactor" "test" "chore" "perf" "ci" "build" "style" "deps" "security" "revert" "hotfix")

die() {
  echo "Error: $*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

require_opt_value() {
  local opt="$1"
  local val="${2:-}"
  if [[ -z "$val" || "$val" == --* ]]; then
    die "option '$opt' requires a value"
  fi
}

print_help() {
  cat <<'EOF'
Usage:
  bash scripts/start-branch.sh <type> [<slug>] [--issue <id>] [--base <branch>] [--stash-name <note>] [--no-install-hooks]

Arguments:
  <type>             Branch type prefix (feat, fix, docs, refactor, ...).
  <slug>             Optional short branch slug (kebab-case normalized).

Options:
  --issue <id>       Optional issue token inserted before slug.
  --base <branch>    Optional base branch; default auto-detect from origin/HEAD, fallback main.
  --stash-name <n>   Optional stash note when auto-stashing dirty worktree.
  --no-install-hooks Skip automatic managed pre-commit hook installation.
  -h, --help         Show this help text.

Deterministic defaults when <slug> is omitted:
  - With --issue: issue-<id>
  - Without --issue: wip-<YYYYMMDD-HHMMSS> (local timezone)
EOF
}

require_cmd git

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  die "not inside a git repository"
fi

TYPE="${1:-}"
if [[ "$TYPE" == "-h" || "$TYPE" == "--help" || -z "$TYPE" ]]; then
  print_help
  exit 0
fi
shift || true

SLUG=""
if [[ $# -gt 0 && "${1:-}" != --* ]]; then
  SLUG="${1:-}"
  shift || true
fi

ISSUE=""
BASE=""
STASH_NOTE=""
AUTO_SLUG_FROM_ISSUE="false"
INSTALL_HOOKS="true"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      print_help
      exit 0
      ;;
    --issue)
      require_opt_value "--issue" "${2:-}"
      ISSUE="${2:-}"
      shift 2
      ;;
    --base)
      require_opt_value "--base" "${2:-}"
      BASE="${2:-}"
      shift 2
      ;;
    --stash-name)
      require_opt_value "--stash-name" "${2:-}"
      STASH_NOTE="${2:-}"
      shift 2
      ;;
    --no-install-hooks)
      INSTALL_HOOKS="false"
      shift
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

[[ -n "$TYPE" ]] || die "missing <type>"

# Validate type
TYPE_OK="false"
for t in "${ALLOWED_TYPES[@]}"; do
  if [[ "$t" == "$TYPE" ]]; then
    TYPE_OK="true"
    break
  fi
done
[[ "$TYPE_OK" == "true" ]] || die "invalid type '$TYPE' (allowed: ${ALLOWED_TYPES[*]})"

# Normalize issue token if provided.
if [[ -n "$ISSUE" ]]; then
  ISSUE="$(echo "$ISSUE" | sed -E 's/[^A-Za-z0-9#_-]+//g')"
  [[ -n "$ISSUE" ]] || die "issue token normalized to empty value"
fi

# Determine slug if omitted.
if [[ -z "$SLUG" ]]; then
  if [[ -n "$ISSUE" ]]; then
    SLUG="issue-$ISSUE"
    AUTO_SLUG_FROM_ISSUE="true"
  else
    NOW_SLUG="$(date '+%Y%m%d-%H%M%S' 2>/dev/null || true)"
    if [[ -z "$NOW_SLUG" ]]; then
      NOW_SLUG="unknown-time"
    fi
    HEAD_SHORT="$(git rev-parse --short=8 HEAD 2>/dev/null || true)"
    if [[ -n "$HEAD_SHORT" ]]; then
      SLUG="wip-$NOW_SLUG-$HEAD_SHORT"
    else
      SLUG="wip-$NOW_SLUG"
    fi
  fi
fi

# Normalize slug: lowercase + spaces to hyphens
SLUG="$(echo "$SLUG" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//; s/-+/-/g')"
[[ -n "$SLUG" ]] || die "slug normalized to empty value; choose a more specific slug"

if [[ -z "$BASE" ]]; then
  # Try to detect default branch from origin/HEAD
  if git symbolic-ref -q refs/remotes/origin/HEAD >/dev/null 2>&1; then
    BASE="$(git symbolic-ref -q refs/remotes/origin/HEAD | sed 's@^refs/remotes/origin/@@')"
  else
    BASE="main"
  fi
fi

BRANCH="$TYPE/"
if [[ -n "$ISSUE" && "$AUTO_SLUG_FROM_ISSUE" != "true" ]]; then
  BRANCH+="${ISSUE}-"
fi
BRANCH+="$SLUG"

ORIGINAL_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
STASHED="false"

# Auto-stash tracked + untracked changes when dirty.
if [[ -n "$(git status --porcelain)" ]]; then
  LOCAL_TS="$(date '+%Y-%m-%dT%H:%M:%S%z' 2>/dev/null || true)"
  [[ -n "$LOCAL_TS" ]] || LOCAL_TS="unknown-local-time"
  NOTE="${STASH_NOTE:-auto}"
  STASH_MSG="gitops-workflow:start-branch:${LOCAL_TS}:from=${ORIGINAL_BRANCH}:to=${BRANCH}:base=${BASE}:note=${NOTE}"
  echo "Working tree dirty; stashing tracked+untracked changes."
  git stash push --include-untracked -m "$STASH_MSG" >/dev/null
  STASHED="true"
  echo "Stash created: $STASH_MSG"
fi

echo "Base branch: $BASE"
echo "Creating branch: $BRANCH"

if ! FETCH_OUTPUT="$(git fetch origin --prune 2>&1)"; then
  echo "Warning: git fetch origin --prune failed; continuing with local refs." >&2
  echo "Warning: git fetch details: $FETCH_OUTPUT" >&2
fi

git checkout "$BASE" >/dev/null 2>&1 || die "failed to checkout base branch '$BASE' (does it exist locally?)"
if git rev-parse --abbrev-ref --symbolic-full-name "@{upstream}" >/dev/null 2>&1; then
  git pull --ff-only || die "failed to pull base branch '$BASE' (resolve and retry)"
else
  echo "No upstream configured for '$BASE'; skipping pull."
fi

if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  die "branch '$BRANCH' already exists locally"
fi

git checkout -b "$BRANCH"

if [[ "$STASHED" == "true" ]]; then
  echo "Restoring stashed changes onto new branch."
  if ! git stash pop >/dev/null 2>&1; then
    echo "Error: stash restore failed; stash entry has been kept for safety." >&2
    echo "Recovery steps:" >&2
    echo "  1) git stash list" >&2
    echo "  2) git stash apply stash@{0}" >&2
    echo "  3) resolve conflicts, then optionally: git stash drop stash@{0}" >&2
    exit 3
  fi
fi

if [[ "$INSTALL_HOOKS" == "true" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
  HOOK_INSTALLER="$SCRIPT_DIR/install-hooks.sh"
  REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)"
  if [[ -x "$HOOK_INSTALLER" ]]; then
    if bash "$HOOK_INSTALLER" --repo "$REPO_ROOT" >/dev/null 2>&1; then
      echo "Managed pre-commit hook ensured for: $REPO_ROOT"
    else
      echo "Warning: failed to auto-install managed pre-commit hook; run '$HOOK_INSTALLER --repo \"$REPO_ROOT\"' manually." >&2
    fi
  else
    echo "Warning: hook installer script not found/executable at $HOOK_INSTALLER" >&2
  fi
fi

echo ""
echo "✅ Created and checked out: $BRANCH"
echo "Next:"
echo "  - make changes"
echo "  - commit with Conventional Commits"
echo "  - open a PR with a body file (see assets/templates/pull-request-body.md)"
