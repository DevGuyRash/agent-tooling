#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"
# shellcheck source=lib/git-state.sh
source "$SCRIPT_DIR/lib/git-state.sh"
# shellcheck source=lib/router.sh
source "$SCRIPT_DIR/lib/router.sh"

REPO_PATH="$(pwd -P)"
BRANCH=""
JSON="false"
ADOPT_EXISTING="true"

print_help() {
  cat <<'USAGE'
Usage:
  bash scripts/ensure-worktree.sh [--repo <path>] [--branch <name>] [--json] [--adopt-existing]

Behavior:
  - Raw workflows should not use this helper.
  - When the current branch is a feature branch in the main checkout, create or reuse its linked worktree.
  - If already in the branch's linked worktree, return the current path unchanged.

Options:
  --repo <path>      Repository path to inspect (default: current directory).
  --branch <name>    Branch to enforce (default: current branch).
  --json             Emit machine-readable JSON.
  --adopt-existing   Reuse an already-existing linked worktree for the branch (default).
  -h, --help         Show help.
USAGE
}

emit_result() {
  local status="$1"
  local branch="$2"
  local path="$3"
  local note="${4:-}"
  if [[ "$JSON" == "true" ]]; then
    python3 - "$status" "$branch" "$path" "$note" <<'PY'
import json
import sys

print(json.dumps({
    "status": sys.argv[1],
    "branch": sys.argv[2],
    "path": sys.argv[3],
    "note": sys.argv[4],
}))
PY
  else
    echo "status: $status"
    echo "branch: $branch"
    echo "path: $path"
    [[ -n "$note" ]] && echo "note: $note"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      require_opt_value "--repo" "${2:-}"
      REPO_PATH="${2:-}"
      shift 2
      ;;
    --branch)
      require_opt_value "--branch" "${2:-}"
      BRANCH="${2:-}"
      shift 2
      ;;
    --json)
      JSON="true"
      shift
      ;;
    --adopt-existing)
      ADOPT_EXISTING="true"
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

if ! git -C "$REPO_PATH" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  die "--repo is not a git repository: $REPO_PATH"
fi

gitops_prepare_repo_for_stateful_command "$REPO_PATH" recover || {
    code=$?
    if [[ $code -eq 10 ]]; then
      die "detached HEAD recovered into rescue branch '$GITOPS_RECOVERED_BRANCH'; re-run the workflow from that branch explicitly"
    fi
    if [[ $code -eq 20 ]]; then
      die "$GITOPS_RECOVERY_NEXT_ACTION"
    fi
    exit "$code"
}
if [[ "$GITOPS_FETCH_STATUS" == "warning" ]]; then
  echo "Warning: git fetch origin --prune failed; continuing with local refs." >&2
  echo "Warning: git fetch details: $GITOPS_FETCH_NOTE" >&2
fi

if [[ -z "$BRANCH" ]]; then
  BRANCH="$GITOPS_RECOVERED_BRANCH"
fi

BASE_BRANCH="$(resolve_default_base "$REPO_PATH" || true)"
[[ -n "$BASE_BRANCH" ]] || die "failed to resolve the default branch for '$REPO_PATH'"
[[ "$BRANCH" != "$BASE_BRANCH" ]] || die "branch '$BRANCH' is the default branch; create a work branch before running non-raw workflows"

ROOT="$(repo_root_path "$REPO_PATH")"
MAIN_CHECKOUT="$(main_checkout_path "$REPO_PATH")"

if in_linked_worktree "$REPO_PATH"; then
  emit_result "ready" "$BRANCH" "$ROOT" "already in linked worktree"
  exit 0
fi

EXISTING_WORKTREE="$(worktree_path_for_branch "$REPO_PATH" "$BRANCH")"
if [[ -n "$EXISTING_WORKTREE" && "$EXISTING_WORKTREE" != "$ROOT" && "$ADOPT_EXISTING" == "true" ]]; then
  emit_result "adopted" "$BRANCH" "$EXISTING_WORKTREE" "linked worktree already exists"
  exit 0
fi

TARGET_PATH="$(canonical_worktree_path "$REPO_PATH" "$BRANCH")"
[[ ! -e "$TARGET_PATH" ]] || die "canonical worktree path already exists: $TARGET_PATH"

STASHED="false"
if [[ -n "$(git -C "$REPO_PATH" status --porcelain)" ]]; then
  STASHED="true"
  git -C "$REPO_PATH" stash push --include-untracked -m "gitops-workflow:ensure-worktree:$(gitops_now_stamp):branch=$BRANCH" >/dev/null
fi

git -C "$MAIN_CHECKOUT" checkout "$BASE_BRANCH" >/dev/null 2>&1 || die "failed to move main checkout to '$BASE_BRANCH' before worktree adoption"
mkdir -p "$(dirname "$TARGET_PATH")"
git -C "$MAIN_CHECKOUT" worktree add "$TARGET_PATH" "$BRANCH" >/dev/null 2>&1 || die "failed to create linked worktree at '$TARGET_PATH'"

if [[ "$STASHED" == "true" ]]; then
  if ! git -C "$TARGET_PATH" stash pop >/dev/null 2>&1; then
    die "worktree adoption restored branch checkout but stash replay failed; resolve manually with 'git -C \"$TARGET_PATH\" stash list'"
  fi
fi

if [[ -x "$SCRIPT_DIR/install-hooks.sh" ]]; then
  bash "$SCRIPT_DIR/install-hooks.sh" --repo "$TARGET_PATH" >/dev/null 2>&1 || true
fi

emit_result "created" "$BRANCH" "$TARGET_PATH" "linked worktree created"
