#!/usr/bin/env bash
# gitops-catalog: {"id":"start-work","topic":"branch","command":"start work","phrases":["start work","start branch","new branch","new worktree"],"summary":"Create or adopt a work branch with a linked worktree by default.","script":"start-branch.sh","creates_branch":true,"creates_worktree":true,"creates_pr":false,"mutates_history":false,"stays_on_current_branch":false,"supports_json":true}
set -euo pipefail

# start-branch.sh - Create a new work branch or linked worktree from the default branch using repo policy.
#
# Usage:
#   bash scripts/start-branch.sh <type> [<slug>] [--issue <id>] [--base <branch>] [--stash-name <note>] [--no-worktree] [--existing] [--no-install-hooks] [--no-detached-recovery]
#
# Examples:
#   bash scripts/start-branch.sh feat add-json-output
#   bash scripts/start-branch.sh fix handle-empty-payload --issue 123
#   bash scripts/start-branch.sh chore --issue 456 --stash-name "carry local wip"
#   bash scripts/start-branch.sh docs update-readme --base main
#   bash scripts/start-branch.sh feat add-json-output --worktree
#
# Notes:
# - Detects default branch from origin/HEAD when possible.
# - Validates branch type and slug format.
# - Uses kebab-case for slug; spaces become hyphens.
# - Branch mode stashes tracked+untracked changes before switching branches and restores
#   them after branch creation.
# - Worktree mode creates a linked worktree and migrates dirty files into it.
# - Auto-installs managed pre-commit hook by default to enforce sensitive-data scans.

ALLOWED_TYPES=("feat" "fix" "docs" "refactor" "test" "chore" "perf" "ci" "build" "style" "deps" "security" "revert" "hotfix")

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"
# shellcheck source=lib/git-state.sh
source "$SCRIPT_DIR/lib/git-state.sh"
# shellcheck source=lib/router.sh
source "$SCRIPT_DIR/lib/router.sh"

print_help() {
  cat <<'EOF'
Usage:
  bash scripts/start-branch.sh <type> [<slug>] [--issue <id>] [--base <branch>] [--stash-name <note>] [--no-worktree] [--existing] [--no-install-hooks] [--no-detached-recovery] [--json]

Arguments:
  <type>             Branch type prefix (feat, fix, docs, refactor, ...).
  <slug>             Optional short branch slug (kebab-case normalized).

Options:
  --issue <id>       Optional issue token inserted before slug.
  --base <branch>    Optional base branch; default auto-detect from origin/HEAD, fallback main.
  --stash-name <n>   Optional stash note when auto-stashing dirty worktree.
  --worktree         Create a linked worktree (default; no-op for backwards compatibility).
  --no-worktree      Stay in the current checkout instead of creating a linked worktree.
  --existing         Adopt an existing branch instead of creating a new one.
  --no-install-hooks Skip automatic managed pre-commit hook installation.
  --no-detached-recovery
                      Refuse detached HEAD instead of attempting safe recovery.
  --json             Emit machine-readable JSON on success.
  -h, --help         Show this help text.

Deterministic defaults when <slug> is omitted:
  - With --issue: issue-<id>
  - Without --issue: wip-<YYYYMMDD-HHMMSS>-<HEAD8> when HEAD exists, otherwise wip-<YYYYMMDD-HHMMSS> (local timezone)
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
USE_WORKTREE="true"
USE_EXISTING="false"
DETACHED_MODE="recover"
JSON="false"
WORKTREE_MODE="worktree"

emit_result() {
  local status="$1"
  local branch="$2"
  local base="$3"
  local mode="$4"
  local path="$5"
  local recovered="$6"
  if [[ "$JSON" == "true" ]]; then
    python3 - "$status" "$branch" "$base" "$mode" "$path" "$recovered" <<'PY'
import json
import sys

print(json.dumps({
    "status": sys.argv[1],
    "branch": sys.argv[2],
    "base": sys.argv[3],
    "mode": sys.argv[4],
    "path": sys.argv[5],
    "detached_recovery": sys.argv[6],
}))
PY
  fi
}

cleanup_partial_worktree() {
  local repo="$1"
  local path="$2"
  git -C "$repo" worktree remove --force "$path" >/dev/null 2>&1 || true
  rm -rf -- "$path"
}

create_worktree_with_fallback() {
  local repo="$1"
  local path="$2"
  local branch="$3"
  local base_ref="${4:-}"
  local existing_branch="${5:-false}"
  local output=""

  local -a args=("worktree" "add")
  if [[ "$existing_branch" == "true" ]]; then
    args+=("$path" "$branch")
  else
    args+=("-b" "$branch" "$path" "$base_ref")
  fi

  if output="$(git -C "$repo" "${args[@]}" 2>&1)"; then
    WORKTREE_MODE="worktree"
    return 0
  fi

  case "$output" in
    *"already exists"*|*"pathspec"*|*"invalid reference"*|*"not a valid object name"*|*"not a commit"*|*"not a branch"*|*"is already checked out"*|*"worktree path already exists"*)
      printf '%s\n' "$output" >&2
      return 1
      ;;
  esac

  cleanup_partial_worktree "$repo" "$path"
  mkdir -p "$(dirname "$path")"

  local -a fallback_args=("worktree" "add" "--no-checkout")
  if [[ "$existing_branch" == "true" ]]; then
    fallback_args+=("$path" "$branch")
  else
    fallback_args+=("-b" "$branch" "$path" "$base_ref")
  fi

  if output="$(git -C "$repo" "${fallback_args[@]}" 2>&1)"; then
    WORKTREE_MODE="worktree-no-checkout"
    return 0
  fi

  cleanup_partial_worktree "$repo" "$path"
  printf '%s\n' "$output" >&2
  return 1
}

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
    --no-detached-recovery)
      DETACHED_MODE="off"
      shift
      ;;
    --json)
      JSON="true"
      shift
      ;;
    --worktree)
      USE_WORKTREE="true"
      shift
      ;;
    --no-worktree)
      USE_WORKTREE="false"
      shift
      ;;
    --existing)
      USE_EXISTING="true"
      shift
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

gitops_prepare_repo_for_stateful_command "." "$DETACHED_MODE" || {
  code=$?
  if [[ $code -eq 10 ]]; then
    die "detached HEAD was recovered into rescue branch '$GITOPS_RECOVERED_BRANCH'; re-run start-branch from that branch or opt out with --no-detached-recovery"
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
  BASE="$(resolve_default_base "." || true)"
  [[ -n "$BASE" ]] || die "failed to resolve the default branch; pass --base explicitly"
fi

BRANCH="$TYPE/"
if [[ -n "$ISSUE" && "$AUTO_SLUG_FROM_ISSUE" != "true" ]]; then
  BRANCH+="${ISSUE}-"
fi
BRANCH+="$SLUG"

ORIGINAL_BRANCH="$(current_branch_name "." || true)"
[[ -n "$ORIGINAL_BRANCH" ]] || die "failed to resolve current branch after detached-head recovery"
STASHED="false"
REPO_ROOT="$(repo_root_path ".")"
MAIN_CHECKOUT_ROOT="$(main_checkout_path ".")"
WORKTREE_PATH="$(canonical_worktree_path "." "$BRANCH")"

# Capture dirty files for worktree mode migration.
DIRTY_FILES_TRACKED=""
DIRTY_FILES_STAGED=""
DIRTY_FILES_UNTRACKED=""
if [[ "$USE_WORKTREE" == "true" && -n "$(git status --porcelain)" ]]; then
  DIRTY_FILES_TRACKED="$(git diff --name-only HEAD 2>/dev/null || true)"
  DIRTY_FILES_STAGED="$(git diff --cached --name-only 2>/dev/null || true)"
  DIRTY_FILES_UNTRACKED="$(git ls-files --others --exclude-standard 2>/dev/null || true)"
fi

# Auto-stash tracked + untracked changes when dirty in branch mode.
if [[ "$USE_WORKTREE" != "true" && -n "$(git status --porcelain)" ]]; then
  LOCAL_TS="$(date '+%Y-%m-%dT%H:%M:%S%z' 2>/dev/null || true)"
  [[ -n "$LOCAL_TS" ]] || LOCAL_TS="unknown-local-time"
  NOTE="${STASH_NOTE:-auto}"
  STASH_MSG="gitops-workflow:start-branch:${LOCAL_TS}:from=${ORIGINAL_BRANCH}:to=${BRANCH}:base=${BASE}:note=${NOTE}"
  if [[ "$JSON" != "true" ]]; then
    echo "Working tree dirty; stashing tracked+untracked changes."
  fi
  git stash push --include-untracked -m "$STASH_MSG" >/dev/null
  STASHED="true"
  if [[ "$JSON" != "true" ]]; then
    echo "Stash created: $STASH_MSG"
  fi
fi

if [[ "$JSON" != "true" ]]; then
  echo "Base branch: $BASE"
  if [[ "$USE_WORKTREE" == "true" ]]; then
    echo "Creating linked worktree branch: $BRANCH"
  else
    echo "Creating branch: $BRANCH"
  fi
fi

if [[ "$USE_EXISTING" == "true" ]]; then
  if ! git show-ref --verify --quiet "refs/heads/$BRANCH"; then
    if git show-ref --verify --quiet "refs/remotes/origin/$BRANCH"; then
      git branch --track "$BRANCH" "origin/$BRANCH" >/dev/null 2>&1 || die "failed to adopt remote branch 'origin/$BRANCH'"
    else
      die "branch '$BRANCH' does not exist; omit --existing to create it"
    fi
  fi
  if [[ "$USE_WORKTREE" == "true" ]]; then
    EXISTING_WT="$(worktree_path_for_branch "." "$BRANCH")"
    if [[ -n "$EXISTING_WT" ]]; then
      if [[ "$JSON" != "true" ]]; then
        echo "Worktree for branch '$BRANCH' already exists at: $EXISTING_WT"
      fi
    else
      if [[ -e "$WORKTREE_PATH" ]]; then
        die "worktree path already exists: $WORKTREE_PATH"
      fi
      mkdir -p "$(dirname "$WORKTREE_PATH")"
      create_worktree_with_fallback "." "$WORKTREE_PATH" "$BRANCH" "" "true" || die "failed to create linked worktree at '$WORKTREE_PATH'"
    fi
  else
    git checkout "$BRANCH" >/dev/null 2>&1 || die "failed to checkout existing branch '$BRANCH'"
  fi
else
  if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
    die "branch '$BRANCH' already exists locally"
  fi
  if git show-ref --verify --quiet "refs/remotes/origin/$BRANCH"; then
    die "branch '$BRANCH' already exists on origin; use --existing to adopt it instead of creating a duplicate"
  fi

  if [[ "$USE_WORKTREE" == "true" ]]; then
    BASE_REF="$BASE"
    if git show-ref --verify --quiet "refs/remotes/origin/$BASE"; then
      BASE_REF="origin/$BASE"
    elif ! git show-ref --verify --quiet "refs/heads/$BASE"; then
      die "failed to resolve base branch '$BASE' locally or on origin"
    fi
    EXISTING_WT="$(worktree_path_for_branch "." "$BRANCH")"
    if [[ -n "$EXISTING_WT" ]]; then
      die "branch '$BRANCH' is already checked out in linked worktree: $EXISTING_WT"
    fi
    if [[ -e "$WORKTREE_PATH" ]]; then
      die "worktree path already exists: $WORKTREE_PATH"
    fi
    mkdir -p "$(dirname "$WORKTREE_PATH")"
    create_worktree_with_fallback "." "$WORKTREE_PATH" "$BRANCH" "$BASE_REF" "false" || die "failed to create linked worktree at '$WORKTREE_PATH'"
  else
    git checkout "$BASE" >/dev/null 2>&1 || die "failed to checkout base branch '$BASE' (does it exist locally?)"
    if git rev-parse --abbrev-ref --symbolic-full-name "@{upstream}" >/dev/null 2>&1; then
      git pull --ff-only || die "failed to pull base branch '$BASE' (resolve and retry)"
    else
      echo "No upstream configured for '$BASE'; skipping pull."
    fi
    git checkout -b "$BRANCH"
  fi
fi

# Migrate dirty files into worktree and restore main checkout to clean state.
if [[ -n "$DIRTY_FILES_TRACKED$DIRTY_FILES_STAGED$DIRTY_FILES_UNTRACKED" && "$WORKTREE_MODE" != "worktree-no-checkout" ]]; then
  if [[ "$JSON" != "true" ]]; then
    echo "Migrating dirty files to worktree."
  fi
  ALL_DIRTY="$(printf '%s\n' "$DIRTY_FILES_TRACKED" "$DIRTY_FILES_STAGED" "$DIRTY_FILES_UNTRACKED" | sort -u | grep -v '^$')"
  while IFS= read -r f; do
    if [[ -f "$f" ]]; then
      mkdir -p "$WORKTREE_PATH/$(dirname "$f")"
      cp -- "$f" "$WORKTREE_PATH/$f"
    fi
  done <<< "$ALL_DIRTY"
  # Restore main checkout to clean state
  git checkout -- . 2>/dev/null || true
  # Remove untracked files that were copied
  if [[ -n "$DIRTY_FILES_UNTRACKED" ]]; then
    while IFS= read -r f; do
      [[ -f "$f" ]] && rm -- "$f"
    done <<< "$DIRTY_FILES_UNTRACKED"
  fi
  if [[ "$JSON" != "true" ]]; then
    echo "Dirty files migrated to worktree; main checkout restored to clean state."
  fi
elif [[ -n "$DIRTY_FILES_TRACKED$DIRTY_FILES_STAGED$DIRTY_FILES_UNTRACKED" && "$WORKTREE_MODE" == "worktree-no-checkout" && "$JSON" != "true" ]]; then
  echo "Worktree checkout fallback used; dirty-file migration was skipped until checkout issues are resolved in the new worktree."
fi

if [[ "$STASHED" == "true" ]]; then
  if [[ "$JSON" != "true" ]]; then
    echo "Restoring stashed changes onto new branch."
  fi
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
  HOOK_INSTALLER="$SCRIPT_DIR/install-hooks.sh"
  HOOK_REPO_ROOT="$REPO_ROOT"
  if [[ "$USE_WORKTREE" == "true" ]]; then
    HOOK_REPO_ROOT="$WORKTREE_PATH"
  fi
  if [[ -x "$HOOK_INSTALLER" ]]; then
    if bash "$HOOK_INSTALLER" --repo "$HOOK_REPO_ROOT" >/dev/null 2>&1; then
      if [[ "$JSON" != "true" ]]; then
        echo "Managed pre-commit hook ensured for: $HOOK_REPO_ROOT"
      fi
    else
      echo "Warning: failed to auto-install managed pre-commit hook; run '$HOOK_INSTALLER --repo \"$HOOK_REPO_ROOT\"' manually." >&2
    fi
  else
    echo "Warning: hook installer script not found/executable at $HOOK_INSTALLER" >&2
  fi
fi

if [[ "$JSON" == "true" ]]; then
  if [[ "$USE_WORKTREE" == "true" ]]; then
    emit_result "created" "$BRANCH" "$BASE" "$WORKTREE_MODE" "$WORKTREE_PATH" "$GITOPS_DETACHED_STATUS"
  else
    emit_result "created" "$BRANCH" "$BASE" "branch" "$REPO_ROOT" "$GITOPS_DETACHED_STATUS"
  fi
else
  echo ""
  if [[ "$USE_WORKTREE" == "true" ]]; then
    if [[ "$WORKTREE_MODE" == "worktree-no-checkout" ]]; then
      echo "✅ Created linked worktree without checkout: $BRANCH"
      echo "Checkout fallback: the repository blocked a normal worktree checkout, so files were not materialized yet."
    else
      echo "✅ Created linked worktree: $BRANCH"
    fi
    echo "Worktree path: $WORKTREE_PATH"
    echo "Next workdir: $WORKTREE_PATH"
    echo "Next command: cd $(printf '%q' "$WORKTREE_PATH")"
  else
    echo "✅ Created and checked out: $BRANCH"
  fi
  echo "Next:"
  echo "  - make changes"
  echo "  - commit with Conventional Commits"
  echo "  - open a PR with a body file (see assets/templates/pull-request-body.md)"
fi
