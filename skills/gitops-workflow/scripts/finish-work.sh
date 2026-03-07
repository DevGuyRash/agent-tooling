#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

print_help() {
  cat <<'USAGE'
Usage:
  bash scripts/finish-work.sh [--branch <name>] [--base <branch>] [--dry-run]

Behavior:
  - Verifies the target branch is safe to clean up.
  - Requires the remote tracking branch to be gone after fetch/prune.
  - Confirms changes landed on the base branch via merged PR state or branch ancestry.
  - If invoked from a linked worktree, removes the linked worktree attached to the target branch and returns control to the main checkout.
  - If invoked from a normal branch checkout, switches to the base branch and deletes the merged branch.

Options:
  --branch <name>     Branch to clean up (default: current branch).
  --base <branch>     Base branch to verify against (default: detect origin/HEAD, fallback main).
  --dry-run           Print planned cleanup actions without mutating local git state.
  -h, --help          Show help.
USAGE
}

resolve_default_base() {
  local base=""
  base="$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##' || true)"
  if [[ -n "$base" ]]; then
    echo "$base"
    return 0
  fi
  if git show-ref --verify --quiet refs/heads/main; then
    echo "main"
    return 0
  fi
  if git show-ref --verify --quiet refs/heads/master; then
    echo "master"
    return 0
  fi
  echo "main"
}

git_path_resolves_branch() {
  local branch="$1"
  git rev-parse --verify "refs/heads/$branch" >/dev/null 2>&1
}

remote_branch_exists() {
  local branch="$1"
  git show-ref --verify --quiet "refs/remotes/origin/$branch"
}

worktree_path_for_branch() {
  local branch="$1"
  git worktree list --porcelain | awk -v want="refs/heads/$branch" '
    $1 == "worktree" { path = substr($0, 10) }
    $1 == "branch" && $2 == want { print path; exit }
  '
}

pr_merge_confirms_branch() {
  local branch="$1"
  local base="$2"
  if ! command -v gh >/dev/null 2>&1; then
    return 1
  fi
  local payload=""
  if ! payload="$(gh pr list --head "$branch" --state merged --json headRefName,baseRefName,number 2>/dev/null)"; then
    return 1
  fi
  python3 - "$branch" "$base" "$payload" <<'PY'
import json
import sys

branch = sys.argv[1]
base = sys.argv[2]
payload = json.loads(sys.argv[3] or "[]")
for item in payload:
    if item.get("headRefName") == branch and item.get("baseRefName") == base:
        raise SystemExit(0)
raise SystemExit(1)
PY
}

branch_is_merged() {
  local branch="$1"
  local base="$2"
  if git merge-base --is-ancestor "$branch" "$base" >/dev/null 2>&1; then
    return 0
  fi
  pr_merge_confirms_branch "$branch" "$base"
}

CURRENT_BRANCH="${1:-}"
if [[ "$CURRENT_BRANCH" == "-h" || "$CURRENT_BRANCH" == "--help" ]]; then
  print_help
  exit 0
fi

BRANCH=""
BASE=""
DRY_RUN="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --branch)
      require_opt_value "--branch" "${2:-}"
      BRANCH="${2:-}"
      shift 2
      ;;
    --base)
      require_opt_value "--base" "${2:-}"
      BASE="${2:-}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN="true"
      shift
      ;;
    -h|--help)
      print_help
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

require_cmd git
require_cmd python3

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  die "current directory is not a git repository"
fi

if [[ -z "$BRANCH" ]]; then
  BRANCH="$(git rev-parse --abbrev-ref HEAD)"
fi
[[ "$BRANCH" != "HEAD" ]] || die "detached HEAD cannot be cleaned up automatically; pass --branch explicitly from a branch checkout"

if [[ -z "$BASE" ]]; then
  BASE="$(resolve_default_base)"
fi

[[ "$BRANCH" != "$BASE" ]] || die "refusing to clean up the default branch '$BASE'"
git_path_resolves_branch "$BRANCH" || die "local branch not found: $BRANCH"
git rev-parse --verify "$BASE" >/dev/null 2>&1 || die "base branch/ref not found: $BASE"

if ! FETCH_OUTPUT="$(git fetch origin --prune 2>&1)"; then
  echo "Warning: git fetch origin --prune failed; continuing with local refs." >&2
  echo "Warning: git fetch details: $FETCH_OUTPUT" >&2
fi

if remote_branch_exists "$BRANCH"; then
  die "remote branch still exists at origin/$BRANCH; finish remote cleanup before removing local state"
fi

branch_is_merged "$BRANCH" "$BASE" || die "branch '$BRANCH' is not confirmed on '$BASE'; refusing cleanup"

TOPLEVEL="$(git rev-parse --show-toplevel)"
COMMON_DIR="$(git rev-parse --git-common-dir)"
MAIN_CHECKOUT="$(cd "$COMMON_DIR/.." && pwd -P)"
CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
IN_LINKED_WORKTREE="false"
if [[ "$TOPLEVEL" != "$MAIN_CHECKOUT" ]]; then
  IN_LINKED_WORKTREE="true"
fi

echo "Base branch: $BASE"
echo "Branch cleanup target: $BRANCH"

if [[ "$IN_LINKED_WORKTREE" == "true" ]]; then
  TARGET_WORKTREE="$(worktree_path_for_branch "$BRANCH")"
  TARGET_IN_MAIN_CHECKOUT="false"
  if [[ "$TARGET_WORKTREE" == "$MAIN_CHECKOUT" ]]; then
    TARGET_IN_MAIN_CHECKOUT="true"
  fi
  if [[ -z "$TARGET_WORKTREE" ]]; then
    if [[ "$BRANCH" != "$CURRENT_BRANCH" ]]; then
      die "branch '$BRANCH' is not attached to a linked worktree; rerun from the main checkout or omit --branch"
    fi
    TARGET_WORKTREE="$TOPLEVEL"
  fi
  echo "Main checkout: $MAIN_CHECKOUT"
  if [[ "$TARGET_IN_MAIN_CHECKOUT" == "true" ]]; then
    echo "Target branch is checked out in the main checkout."
    if [[ "$DRY_RUN" == "true" ]]; then
      echo "DRY-RUN: git -C \"$MAIN_CHECKOUT\" checkout \"$BASE\""
      echo "DRY-RUN: git -C \"$MAIN_CHECKOUT\" branch -D \"$BRANCH\""
    else
      git -C "$MAIN_CHECKOUT" checkout "$BASE" >/dev/null 2>&1 || die "failed to checkout '$BASE' in main checkout"
      git -C "$MAIN_CHECKOUT" branch -D "$BRANCH" >/dev/null 2>&1 || die "failed to delete branch '$BRANCH' from main checkout"
    fi
    echo ""
    echo "✅ Cleaned branch: $BRANCH"
    echo "Next workdir: $MAIN_CHECKOUT"
    echo "Next command: cd $(printf '%q' "$MAIN_CHECKOUT")"
    exit 0
  fi
  echo "Linked worktree detected: $TARGET_WORKTREE"
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "DRY-RUN: git -C \"$MAIN_CHECKOUT\" checkout \"$BASE\""
    echo "DRY-RUN: git -C \"$MAIN_CHECKOUT\" worktree remove \"$TARGET_WORKTREE\""
    echo "DRY-RUN: if git show-ref --verify --quiet \"refs/heads/$BRANCH\"; then git -C \"$MAIN_CHECKOUT\" branch -D \"$BRANCH\"; fi"
  else
    git -C "$MAIN_CHECKOUT" checkout "$BASE" >/dev/null 2>&1 || die "failed to checkout '$BASE' in main checkout"
    git -C "$MAIN_CHECKOUT" worktree remove "$TARGET_WORKTREE" || die "failed to remove linked worktree '$TARGET_WORKTREE'"
    if git -C "$MAIN_CHECKOUT" show-ref --verify --quiet "refs/heads/$BRANCH"; then
      git -C "$MAIN_CHECKOUT" branch -D "$BRANCH" >/dev/null 2>&1 || die "failed to delete branch '$BRANCH' from main checkout"
    fi
  fi
  echo ""
  echo "✅ Cleaned worktree for: $BRANCH"
  echo "Next workdir: $MAIN_CHECKOUT"
  echo "Next command: cd $(printf '%q' "$MAIN_CHECKOUT")"
  exit 0
fi

if [[ "$DRY_RUN" == "true" ]]; then
  echo "DRY-RUN: git checkout \"$BASE\""
  echo "DRY-RUN: git branch -D \"$BRANCH\""
else
  git checkout "$BASE" >/dev/null 2>&1 || die "failed to checkout '$BASE'"
  git branch -D "$BRANCH" >/dev/null 2>&1 || die "failed to delete branch '$BRANCH'"
fi

echo ""
echo "✅ Cleaned branch: $BRANCH"
echo "Next workdir: $(git rev-parse --show-toplevel)"
