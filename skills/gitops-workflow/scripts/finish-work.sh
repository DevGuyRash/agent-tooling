#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"
# shellcheck source=lib/git-state.sh
source "$SCRIPT_DIR/lib/git-state.sh"
# shellcheck source=lib/router.sh
source "$SCRIPT_DIR/lib/router.sh"

print_help() {
  cat <<'USAGE'
Usage:
  bash scripts/finish-work.sh [--branch <name>] [--base <branch>] [--dry-run] [--no-detached-recovery] [--json]

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
  --no-detached-recovery
                      Refuse detached HEAD instead of attempting safe recovery.
  --json              Emit machine-readable JSON on success.
  -h, --help          Show help.
USAGE
}

emit_result() {
  local status="$1"
  local branch="$2"
  local base="$3"
  local next_workdir="$4"
  local mode="$5"
  local dry_run="$6"
  local detached="$7"
  if [[ "$JSON" == "true" ]]; then
    python3 - "$status" "$branch" "$base" "$next_workdir" "$mode" "$dry_run" "$detached" <<'PY'
import json
import sys

print(json.dumps({
    "status": sys.argv[1],
    "branch": sys.argv[2],
    "base": sys.argv[3],
    "next_workdir": sys.argv[4],
    "mode": sys.argv[5],
    "dry_run": sys.argv[6] == "true",
    "detached_recovery": sys.argv[7],
}))
PY
  fi
}

git_path_resolves_branch() {
  local branch="$1"
  git rev-parse --verify "refs/heads/$branch" >/dev/null 2>&1
}

remote_branch_exists() {
  local branch="$1"
  git show-ref --verify --quiet "refs/remotes/origin/$branch"
}

require_clean_checkout() {
  local path="$1"
  local label="$2"
  if [[ -n "$(git -C "$path" status --porcelain)" ]]; then
    die "$label has uncommitted changes; commit, stash, or discard them before cleanup"
  fi
}

worktree_path_for_branch() {
  local branch="$1"
  git worktree list --porcelain | awk -v want="refs/heads/$branch" '
    $1 == "worktree" { path = substr($0, 10) }
    $1 == "branch" && $2 == want { print path; exit }
  '
}

branch_diff_applied_to_base() {
  local branch="$1"
  local base="$2"
  local merge_base=""
  merge_base="$(git merge-base "$branch" "$base" 2>/dev/null || true)"
  [[ -n "$merge_base" ]] || return 1

  if git diff --quiet "$merge_base" "$branch" --; then
    return 0
  fi

  local scratch=""
  scratch="$(mktemp -d)"
  trap 'rm -rf "$scratch"' RETURN

  git archive "$base" | tar -x -C "$scratch"
  if git diff --binary "$merge_base" "$branch" | git -C "$scratch" apply --check --reverse >/dev/null 2>&1; then
    rm -rf "$scratch"
    trap - RETURN
    return 0
  fi

  rm -rf "$scratch"
  trap - RETURN
  return 1
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
  if branch_diff_applied_to_base "$branch" "$base"; then
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
DETACHED_MODE="recover"
JSON="false"

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
    --no-detached-recovery)
      DETACHED_MODE="off"
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
      die "unknown argument: $1"
      ;;
  esac
done

require_cmd git
require_cmd python3

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  die "current directory is not a git repository"
fi

gitops_prepare_repo_for_stateful_command "." "$DETACHED_MODE" || {
  code=$?
  if [[ $code -eq 10 ]]; then
    die "detached HEAD was recovered into rescue branch '$GITOPS_RECOVERED_BRANCH'; re-run finish-work from that branch or pass --no-detached-recovery to opt out"
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

if [[ -z "$BASE" ]]; then
  BASE="$(resolve_default_base "." || true)"
fi
[[ -n "$BASE" ]] || die "failed to resolve the default branch; pass --base explicitly"

[[ "$BRANCH" != "$BASE" ]] || die "refusing to clean up the default branch '$BASE'"
git_path_resolves_branch "$BRANCH" || die "local branch not found: $BRANCH"
git rev-parse --verify "$BASE" >/dev/null 2>&1 || die "base branch/ref not found: $BASE"

if remote_branch_exists "$BRANCH"; then
  die "remote branch still exists at origin/$BRANCH; finish remote cleanup before removing local state"
fi

branch_is_merged "$BRANCH" "$BASE" || die "branch '$BRANCH' is not confirmed on '$BASE'; refusing cleanup"

TOPLEVEL="$(repo_root_path ".")"
MAIN_CHECKOUT="$(main_checkout_path ".")"
CURRENT_BRANCH="$(current_branch_name "." || true)"
IN_LINKED_WORKTREE="false"
if [[ "$TOPLEVEL" != "$MAIN_CHECKOUT" ]]; then
  IN_LINKED_WORKTREE="true"
fi

if [[ "$JSON" != "true" ]]; then
  echo "Base branch: $BASE"
  echo "Branch cleanup target: $BRANCH"
fi

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
  if [[ "$JSON" != "true" ]]; then
    echo "Main checkout: $MAIN_CHECKOUT"
  fi
  if [[ "$TARGET_IN_MAIN_CHECKOUT" == "true" ]]; then
    recover_repo_for_stateful_command "$MAIN_CHECKOUT" "$DETACHED_MODE" || {
      code=$?
      if [[ $code -eq 10 ]]; then
        die "main checkout recovered into rescue branch '$GITOPS_RECOVERED_BRANCH'; review it before cleanup"
      fi
      if [[ $code -eq 20 ]]; then
        die "$GITOPS_RECOVERY_NEXT_ACTION"
      fi
      exit "$code"
    }
    require_clean_checkout "$MAIN_CHECKOUT" "main checkout '$MAIN_CHECKOUT'"
    if [[ "$JSON" != "true" ]]; then
      echo "Target branch is checked out in the main checkout."
    fi
    if [[ "$DRY_RUN" == "true" ]]; then
      if [[ "$JSON" != "true" ]]; then
        echo "DRY-RUN: git -C \"$MAIN_CHECKOUT\" checkout \"$BASE\""
        echo "DRY-RUN: git -C \"$MAIN_CHECKOUT\" branch -D \"$BRANCH\""
      fi
    else
      git -C "$MAIN_CHECKOUT" checkout "$BASE" >/dev/null 2>&1 || die "failed to checkout '$BASE' in main checkout"
      git -C "$MAIN_CHECKOUT" branch -D "$BRANCH" >/dev/null 2>&1 || die "failed to delete branch '$BRANCH' from main checkout"
    fi
    if [[ "$JSON" == "true" ]]; then
      emit_result "cleaned" "$BRANCH" "$BASE" "$MAIN_CHECKOUT" "main-checkout" "$DRY_RUN" "$GITOPS_DETACHED_STATUS"
    else
      echo ""
      echo "✅ Cleaned branch: $BRANCH"
      echo "Next workdir: $MAIN_CHECKOUT"
      echo "Next command: cd $(printf '%q' "$MAIN_CHECKOUT")"
    fi
    exit 0
  fi
  recover_repo_for_stateful_command "$TARGET_WORKTREE" "$DETACHED_MODE" || {
    code=$?
    if [[ $code -eq 10 ]]; then
      die "linked worktree recovered into rescue branch '$GITOPS_RECOVERED_BRANCH'; review it before cleanup"
    fi
    if [[ $code -eq 20 ]]; then
      die "$GITOPS_RECOVERY_NEXT_ACTION"
    fi
    exit "$code"
  }
  require_clean_checkout "$TARGET_WORKTREE" "linked worktree '$TARGET_WORKTREE'"
  if [[ "$JSON" != "true" ]]; then
    echo "Linked worktree detected: $TARGET_WORKTREE"
  fi
  if [[ "$DRY_RUN" == "true" ]]; then
    if [[ "$JSON" != "true" ]]; then
      echo "DRY-RUN: git -C \"$MAIN_CHECKOUT\" checkout \"$BASE\""
      echo "DRY-RUN: git -C \"$MAIN_CHECKOUT\" worktree remove \"$TARGET_WORKTREE\""
      echo "DRY-RUN: if git show-ref --verify --quiet \"refs/heads/$BRANCH\"; then git -C \"$MAIN_CHECKOUT\" branch -D \"$BRANCH\"; fi"
    fi
  else
    git -C "$MAIN_CHECKOUT" checkout "$BASE" >/dev/null 2>&1 || die "failed to checkout '$BASE' in main checkout"
    git -C "$MAIN_CHECKOUT" worktree remove "$TARGET_WORKTREE" || die "failed to remove linked worktree '$TARGET_WORKTREE'"
    if git -C "$MAIN_CHECKOUT" show-ref --verify --quiet "refs/heads/$BRANCH"; then
      git -C "$MAIN_CHECKOUT" branch -D "$BRANCH" >/dev/null 2>&1 || die "failed to delete branch '$BRANCH' from main checkout"
    fi
  fi
  if [[ "$JSON" == "true" ]]; then
    emit_result "cleaned" "$BRANCH" "$BASE" "$MAIN_CHECKOUT" "linked-worktree" "$DRY_RUN" "$GITOPS_DETACHED_STATUS"
  else
    echo ""
    echo "✅ Cleaned worktree for: $BRANCH"
    echo "Next workdir: $MAIN_CHECKOUT"
    echo "Next command: cd $(printf '%q' "$MAIN_CHECKOUT")"
  fi
  exit 0
fi

if [[ "$CURRENT_BRANCH" == "$BASE" && "$BRANCH" != "$BASE" ]]; then
  if [[ "$DRY_RUN" == "true" ]]; then
    if [[ "$JSON" != "true" ]]; then
      echo "DRY-RUN: git branch -D \"$BRANCH\""
    fi
  else
    git branch -D "$BRANCH" >/dev/null 2>&1 || die "failed to delete branch '$BRANCH'"
  fi
elif [[ "$CURRENT_BRANCH" == "$BRANCH" ]]; then
  require_clean_checkout "$TOPLEVEL" "current checkout '$TOPLEVEL'"
  if [[ "$DRY_RUN" == "true" ]]; then
    if [[ "$JSON" != "true" ]]; then
      echo "DRY-RUN: git checkout \"$BASE\""
      echo "DRY-RUN: git branch -D \"$BRANCH\""
    fi
  else
    git checkout "$BASE" >/dev/null 2>&1 || die "failed to checkout '$BASE'"
    git branch -D "$BRANCH" >/dev/null 2>&1 || die "failed to delete branch '$BRANCH'"
  fi
else
  die "current checkout '$CURRENT_BRANCH' is neither '$BASE' nor '$BRANCH'; rerun from the base branch or the target branch"
fi

if [[ "$JSON" == "true" ]]; then
  emit_result "cleaned" "$BRANCH" "$BASE" "$TOPLEVEL" "branch" "$DRY_RUN" "$GITOPS_DETACHED_STATUS"
else
  echo ""
  echo "✅ Cleaned branch: $BRANCH"
  echo "Next workdir: $(git rev-parse --show-toplevel)"
fi
