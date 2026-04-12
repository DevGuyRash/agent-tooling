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
JSON="false"
DETACHED_MODE="recover"
RECURSE_RELATED="true"
NO_RECONCILE="false"
RESULTS_FILE=""
SYNC_STASH_REF=""
SYNC_SNAPSHOT_DIR=""
SYNC_STASHED="false"
SYNC_RESTORE_KIND=""

print_help() {
  cat <<'USAGE'
Usage:
  bash scripts/sync-raw.sh [--repo <path>] [--json] [--no-detached-recovery] [--no-recurse-related] [--no-reconcile]

Behavior:
  - Syncs the current branch in-place without creating branches or worktrees.
  - When related repositories exist, walks the full parent/submodule tree by default.
  - Runs tree reconciliation after syncing.

Options:
  --repo <path>              Repository path to inspect (default: current directory).
  --json                     Emit machine-readable JSON.
  --no-detached-recovery     Refuse detached HEAD instead of attempting safe recovery.
  --no-recurse-related       Only sync the specified repo, not the related tree.
  --no-reconcile             Skip the final reconcile-tree apply step.
  -h, --help                 Show help.
USAGE
}

emit_json() {
  local file="$1"
  python3 - "$file" <<'PY'
import json
import sys
from pathlib import Path

items = []
for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    repo, branch, status, note = line.split("\t", 3)
    items.append({"repo": repo, "branch": branch, "status": status, "note": note})
print(json.dumps({"results": items}, indent=2))
PY
}

log_result() {
  printf '%s\t%s\t%s\t%s\n' "$1" "$2" "$3" "$4" >> "$RESULTS_FILE"
}

cleanup_sync_state() {
  [[ -n "$RESULTS_FILE" && -f "$RESULTS_FILE" ]] && rm -f "$RESULTS_FILE"
  [[ -n "$SYNC_SNAPSHOT_DIR" && -d "$SYNC_SNAPSHOT_DIR" ]] && rm -rf "$SYNC_SNAPSHOT_DIR"
  return 0
}

copy_snapshot_file() {
  local src="$1"
  local dst="$2"
  mkdir -p "$(dirname "$dst")"
  cp -a -- "$src" "$dst"
}

create_sync_snapshot() {
  local repo="$1"
  local path=""
  SYNC_SNAPSHOT_DIR="$(mktemp -d)"
  git -C "$repo" rev-parse HEAD > "$SYNC_SNAPSHOT_DIR/base-head"
  git -C "$repo" diff --name-only -z HEAD -- > "$SYNC_SNAPSHOT_DIR/tracked.list"
  git -C "$repo" ls-files --others --exclude-standard -z > "$SYNC_SNAPSHOT_DIR/untracked.list"

  while IFS= read -r -d '' path; do
    [[ -n "$path" ]] || continue
    if git -C "$repo" cat-file -e "HEAD:$path" >/dev/null 2>&1; then
      mkdir -p "$(dirname "$SYNC_SNAPSHOT_DIR/base/$path")"
      git -C "$repo" show "HEAD:$path" > "$SYNC_SNAPSHOT_DIR/base/$path"
    else
      mkdir -p "$(dirname "$SYNC_SNAPSHOT_DIR/meta/base-missing/$path")"
      : > "$SYNC_SNAPSHOT_DIR/meta/base-missing/$path"
    fi
    if [[ -e "$repo/$path" || -L "$repo/$path" ]]; then
      copy_snapshot_file "$repo/$path" "$SYNC_SNAPSHOT_DIR/local/$path"
    else
      mkdir -p "$(dirname "$SYNC_SNAPSHOT_DIR/meta/deleted/$path")"
      : > "$SYNC_SNAPSHOT_DIR/meta/deleted/$path"
    fi
  done < "$SYNC_SNAPSHOT_DIR/tracked.list"

  while IFS= read -r -d '' path; do
    [[ -n "$path" ]] || continue
    [[ -e "$repo/$path" || -L "$repo/$path" ]] || continue
    copy_snapshot_file "$repo/$path" "$SYNC_SNAPSHOT_DIR/untracked/$path"
  done < "$SYNC_SNAPSHOT_DIR/untracked.list"
}

drop_sync_stash() {
  if [[ "$SYNC_STASHED" == "true" ]]; then
    git -C "$1" stash drop "$SYNC_STASH_REF" >/dev/null 2>&1 || true
    SYNC_STASHED="false"
    SYNC_STASH_REF=""
  fi
}

merge_snapshot_into_file() {
  local local_file="$1"
  local base_file="$2"
  local current_file="$3"
  local dest_file="$4"
  local temp_out=""
  temp_out="$(mktemp)"
  if git merge-file --union -p "$local_file" "$base_file" "$current_file" > "$temp_out" 2>/dev/null; then
    mkdir -p "$(dirname "$dest_file")"
    mv "$temp_out" "$dest_file"
    return 0
  fi
  rm -f "$temp_out"
  return 1
}

restore_sync_snapshot() {
  local repo="$1"
  local path=""
  local empty_base=""
  local temp_current=""
  [[ -n "$SYNC_SNAPSHOT_DIR" && -d "$SYNC_SNAPSHOT_DIR" ]] || return 1

  empty_base="$(mktemp)"
  temp_current="$(mktemp)"
  trap 'rm -f "$empty_base" "$temp_current"' RETURN

  while IFS= read -r -d '' path; do
    [[ -n "$path" ]] || continue
    local base_path="$SYNC_SNAPSHOT_DIR/base/$path"
    local local_path="$SYNC_SNAPSHOT_DIR/local/$path"
    local base_missing_marker="$SYNC_SNAPSHOT_DIR/meta/base-missing/$path"
    local deleted_marker="$SYNC_SNAPSHOT_DIR/meta/deleted/$path"
    local repo_path="$repo/$path"
    local current_exists="false"
    local base_exists="false"
    local local_exists="false"

    [[ -e "$repo_path" || -L "$repo_path" ]] && current_exists="true"
    [[ -e "$base_path" ]] && base_exists="true"
    [[ -e "$local_path" || -L "$local_path" ]] && local_exists="true"

    if [[ -e "$deleted_marker" ]]; then
      if [[ "$current_exists" == "true" && "$base_exists" == "true" ]] && ! cmp -s -- "$base_path" "$repo_path"; then
        trap - RETURN
        rm -f "$empty_base" "$temp_current"
        return 1
      fi
      rm -f -- "$repo_path"
      continue
    fi

    if [[ "$local_exists" != "true" ]]; then
      trap - RETURN
      rm -f "$empty_base" "$temp_current"
      return 1
    fi

    if [[ "$base_exists" == "true" && "$current_exists" == "true" ]]; then
      if cmp -s -- "$repo_path" "$base_path"; then
        mkdir -p "$(dirname "$repo_path")"
        cp -a -- "$local_path" "$repo_path"
      elif cmp -s -- "$local_path" "$base_path"; then
        :
      elif ! merge_snapshot_into_file "$local_path" "$base_path" "$repo_path" "$repo_path"; then
        trap - RETURN
        rm -f "$empty_base" "$temp_current"
        return 1
      fi
      continue
    fi

    if [[ -e "$base_missing_marker" ]]; then
      if [[ "$current_exists" == "true" ]]; then
        cp -a -- "$repo_path" "$temp_current"
        if ! merge_snapshot_into_file "$local_path" "$empty_base" "$temp_current" "$repo_path"; then
          trap - RETURN
          rm -f "$empty_base" "$temp_current"
          return 1
        fi
      else
        mkdir -p "$(dirname "$repo_path")"
        cp -a -- "$local_path" "$repo_path"
      fi
      continue
    fi

    if [[ "$base_exists" == "true" && "$current_exists" != "true" ]]; then
      mkdir -p "$(dirname "$repo_path")"
      cp -a -- "$local_path" "$repo_path"
      continue
    fi

    trap - RETURN
    rm -f "$empty_base" "$temp_current"
    return 1
  done < "$SYNC_SNAPSHOT_DIR/tracked.list"

  while IFS= read -r -d '' path; do
    [[ -n "$path" ]] || continue
    local source_path="$SYNC_SNAPSHOT_DIR/untracked/$path"
    local repo_path="$repo/$path"
    if [[ -e "$repo_path" || -L "$repo_path" ]]; then
      cp -a -- "$repo_path" "$temp_current"
      if ! merge_snapshot_into_file "$source_path" "$empty_base" "$temp_current" "$repo_path"; then
        trap - RETURN
        rm -f "$empty_base" "$temp_current"
        return 1
      fi
    else
      mkdir -p "$(dirname "$repo_path")"
      cp -a -- "$source_path" "$repo_path"
    fi
  done < "$SYNC_SNAPSHOT_DIR/untracked.list"

  trap - RETURN
  rm -f "$empty_base" "$temp_current"
  return 0
}

restore_sync_stash() {
  local repo="$1"
  if ! git -C "$repo" stash pop >/dev/null 2>&1; then
    git -C "$repo" reset --merge >/dev/null 2>&1 || true
    if restore_sync_snapshot "$repo"; then
      drop_sync_stash "$repo"
      SYNC_RESTORE_KIND="fallback"
      log_result "$repo" "$(current_branch_name "$repo" || echo DETACHED)" "synced-with-fallback" "stashed local changes, fast-forwarded from upstream, and restored the dirty tree with deterministic union-merge fallback"
      return 0
    fi
    SYNC_RESTORE_KIND="blocked"
    log_result "$repo" "$(current_branch_name "$repo" || echo DETACHED)" "blocked-stash-pop" "sync updated refs but stash replay needs manual resolution; original stash was preserved"
    return 1
  fi
  SYNC_STASHED="false"
  SYNC_STASH_REF=""
  SYNC_RESTORE_KIND="stash"
  return 0
}

maybe_stash_for_sync() {
  local repo="$1"
  if [[ -z "$(git -C "$repo" status --porcelain)" ]]; then
    return 1
  fi
  create_sync_snapshot "$repo"
  git -C "$repo" stash push --include-untracked -m "gitops-workflow:sync-raw:$(gitops_now_stamp)" >/dev/null || die "failed to stash dirty worktree before raw sync"
  SYNC_STASH_REF="stash@{0}"
  SYNC_STASHED="true"
  return 0
}

sync_one_repo() {
  local repo="$1"
  local had_dirty="false"
  local branch=""
  SYNC_STASH_REF=""
  SYNC_STASHED="false"
  SYNC_RESTORE_KIND=""
  [[ -n "$SYNC_SNAPSHOT_DIR" && -d "$SYNC_SNAPSHOT_DIR" ]] && rm -rf "$SYNC_SNAPSHOT_DIR"
  SYNC_SNAPSHOT_DIR=""
  gitops_prepare_repo_for_stateful_command "$repo" "$DETACHED_MODE" || {
    local code=$?
    if [[ $code -eq 10 ]]; then
      log_result "$repo" "$GITOPS_RECOVERED_BRANCH" "blocked-rescue" "detached HEAD recovered into rescue branch; review before syncing"
      return 0
    fi
    if [[ $code -eq 20 ]]; then
      log_result "$repo" "$(current_branch_name "$repo" || echo DETACHED)" "blocked-recovery" "$GITOPS_RECOVERY_NEXT_ACTION"
      return 0
    fi
    return "$code"
  }
  if [[ "$GITOPS_FETCH_STATUS" == "warning" ]]; then
    log_result "$repo" "$(current_branch_name "$repo" || echo DETACHED)" "fetch-warning" "$GITOPS_FETCH_NOTE"
  fi
  if maybe_stash_for_sync "$repo"; then
    had_dirty="true"
  fi

  branch="$GITOPS_RECOVERED_BRANCH"

  if ! repo_has_origin "$repo"; then
    if [[ "$had_dirty" == "true" ]]; then
      restore_sync_stash "$repo" || true
    fi
    log_result "$repo" "$branch" "skipped-no-origin" "no origin remote configured"
    return 0
  fi

  upstream="$(current_upstream_ref "$repo")"
  if [[ -z "$upstream" ]]; then
    if ensure_tracking_branch_if_remote_exists "$repo" "$branch"; then
      upstream="$(current_upstream_ref "$repo")"
    fi
  fi
  if [[ -z "$upstream" ]]; then
    if [[ "$had_dirty" == "true" ]]; then
      restore_sync_stash "$repo" || true
    fi
    log_result "$repo" "$branch" "blocked-no-upstream" "no upstream configured for current branch"
    return 0
  fi

  if git -C "$repo" pull --ff-only >/dev/null 2>&1; then
    if [[ "$had_dirty" == "true" ]]; then
      if restore_sync_stash "$repo"; then
        if [[ "$SYNC_RESTORE_KIND" == "stash" ]]; then
          log_result "$repo" "$branch" "synced-with-stash" "stashed local changes, fast-forwarded from upstream, then restored the stash"
        fi
      fi
    else
      log_result "$repo" "$branch" "synced" "fast-forwarded from upstream"
    fi
  else
    if [[ "$had_dirty" == "true" ]]; then
      restore_sync_stash "$repo" || true
    fi
    log_result "$repo" "$branch" "blocked-non-ff" "git pull --ff-only failed"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      require_opt_value "--repo" "${2:-}"
      REPO_PATH="${2:-}"
      shift 2
      ;;
    --json)
      JSON="true"
      shift
      ;;
    --no-detached-recovery)
      DETACHED_MODE="off"
      shift
      ;;
    --no-recurse-related)
      RECURSE_RELATED="false"
      shift
      ;;
    --no-reconcile)
      NO_RECONCILE="true"
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

if ! git -C "$REPO_PATH" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  die "--repo is not a git repository: $REPO_PATH"
fi

RESULTS_FILE="$(mktemp)"
trap cleanup_sync_state EXIT

if [[ "$RECURSE_RELATED" == "true" ]]; then
  mapfile -t repos < <(list_related_repos "$REPO_PATH" | sort -r -n -k1,1 | awk -F '\t' '{print $2}')
else
  repos=("$(repo_root_path "$REPO_PATH")")
fi

for repo in "${repos[@]}"; do
  sync_one_repo "$repo"
done

ROOT_REPO="$(outermost_superproject_path "$REPO_PATH")"
if [[ "$RECURSE_RELATED" == "true" && "$NO_RECONCILE" != "true" ]]; then
  RECONCILE_ARGS=(bash "$SCRIPT_DIR/reconcile-tree.sh" --repo "$ROOT_REPO" --mode apply)
  if [[ "$JSON" == "true" ]]; then
    RECONCILE_ARGS+=(--json)
  fi
  RECONCILE_OUTPUT="$("${RECONCILE_ARGS[@]}" 2>&1)" || {
    log_result "$ROOT_REPO" "$(current_branch_name "$ROOT_REPO" || echo DETACHED)" "reconcile-failed" "$RECONCILE_OUTPUT"
  }
fi

if [[ "$JSON" == "true" ]]; then
  emit_json "$RESULTS_FILE"
else
  while IFS=$'\t' read -r repo branch status note; do
    echo "$status: $repo ($branch)"
    [[ -n "$note" ]] && echo "  note: $note"
  done < "$RESULTS_FILE"
fi
