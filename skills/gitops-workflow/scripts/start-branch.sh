#!/usr/bin/env bash
set -euo pipefail

# start-branch.sh - Create a new work branch from the default branch using repo policy.
#
# Usage:
#   bash scripts/start-branch.sh <type> <slug> [--issue <id>] [--base <branch>]
#
# Examples:
#   bash scripts/start-branch.sh feat add-json-output
#   bash scripts/start-branch.sh fix handle-empty-payload --issue 123
#   bash scripts/start-branch.sh docs update-readme --base main
#
# Notes:
# - Detects default branch from origin/HEAD when possible.
# - Validates branch type and slug format.
# - Uses kebab-case for slug; spaces become hyphens.

ALLOWED_TYPES=("feat" "fix" "docs" "refactor" "test" "chore" "perf" "ci" "build" "style" "deps" "security" "revert" "hotfix")

die() {
  echo "Error: $*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

require_cmd git

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  die "not inside a git repository"
fi

TYPE="${1:-}"
SLUG="${2:-}"
shift $(( $# > 0 ? 2 : 0 )) || true

ISSUE=""
BASE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --issue)
      ISSUE="${2:-}"
      shift 2
      ;;
    --base)
      BASE="${2:-}"
      shift 2
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

[[ -n "$TYPE" ]] || die "missing <type>"
[[ -n "$SLUG" ]] || die "missing <slug>"

# Validate type
TYPE_OK="false"
for t in "${ALLOWED_TYPES[@]}"; do
  if [[ "$t" == "$TYPE" ]]; then
    TYPE_OK="true"
    break
  fi
done
[[ "$TYPE_OK" == "true" ]] || die "invalid type '$TYPE' (allowed: ${ALLOWED_TYPES[*]})"

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
if [[ -n "$ISSUE" ]]; then
  # Keep issue part lightweight; no spaces.
  ISSUE="$(echo "$ISSUE" | sed -E 's/[^A-Za-z0-9#_-]+//g')"
  BRANCH+="${ISSUE}-"
fi
BRANCH+="$SLUG"

# Ensure clean working tree
if [[ -n "$(git status --porcelain)" ]]; then
  die "working tree not clean. Commit/stash/discard changes before branching."
fi

echo "Base branch: $BASE"
echo "Creating branch: $BRANCH"

git fetch origin --prune >/dev/null 2>&1 || true

git checkout "$BASE" >/dev/null 2>&1 || die "failed to checkout base branch '$BASE' (does it exist locally?)"
git pull --ff-only || die "failed to pull base branch '$BASE' (resolve and retry)"

if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  die "branch '$BRANCH' already exists locally"
fi

git checkout -b "$BRANCH"

echo ""
echo "✅ Created and checked out: $BRANCH"
echo "Next:"
echo "  - make changes"
echo "  - commit with Conventional Commits"
echo "  - open a PR with a body file (see assets/templates/pull-request-body.md)"
