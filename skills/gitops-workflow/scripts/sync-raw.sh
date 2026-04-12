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
SYNC_RESTORE_KIND="none"
SYNC_RESTORE_NOTE=""
PUSH_ERROR_TEXT=""
REBASE_ERROR_TEXT=""
FAST_FORWARD_ERROR_TEXT=""

print_help() {
  cat <<'USAGE'
Usage:
  bash scripts/sync-raw.sh [--repo <path>] [--json] [--no-detached-recovery] [--no-recurse-related] [--no-reconcile]

Behavior:
  - Syncs the current branch in-place without creating branches or worktrees.
  - Fetches and integrates upstream changes, then pushes local branch commits when safe.
  - When related repositories exist, walks the full parent/submodule tree by default.
  - Runs tree reconciliation after syncing and pushes reconcile-created branch commits bottom-up.

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
    parts = line.split("\t", 4)
    repo, branch, status, note = parts[:4]
    item = {"repo": repo, "branch": branch, "status": status, "note": note}
    if len(parts) == 5 and parts[4]:
        try:
            item.update(json.loads(parts[4]))
        except json.JSONDecodeError:
            item["details_raw"] = parts[4]
    items.append(item)
print(json.dumps({"results": items}, indent=2))
PY
}

emit_text() {
  local file="$1"
  python3 - "$file" <<'PY'
import sys
from pathlib import Path

for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    repo, branch, status, note, *_ = line.split("\t", 4)
    print(f"{status}: {repo} ({branch})")
    if note:
        print(f"  note: {note}")
PY
}

record_result() {
  local repo="$1"
  local branch="$2"
  local status="$3"
  local note="$4"
  local details="${5:-}"
  printf '%s\t%s\t%s\t%s\t%s\n' "$repo" "$branch" "$status" "$note" "$details" >> "$RESULTS_FILE"
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
  SYNC_RESTORE_KIND="none"
  SYNC_RESTORE_NOTE=""
  if ! git -C "$repo" stash pop >/dev/null 2>&1; then
    git -C "$repo" reset --merge >/dev/null 2>&1 || true
    if restore_sync_snapshot "$repo"; then
      drop_sync_stash "$repo"
      SYNC_RESTORE_KIND="fallback"
      SYNC_RESTORE_NOTE="restored local dirty changes with deterministic union-merge fallback"
      return 0
    fi
    SYNC_RESTORE_KIND="blocked"
    SYNC_RESTORE_NOTE="stash replay needs manual resolution; original stash was preserved"
    return 1
  fi
  SYNC_STASHED="false"
  SYNC_STASH_REF=""
  SYNC_RESTORE_KIND="stash"
  SYNC_RESTORE_NOTE="restored local dirty changes"
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

read_ahead_behind_counts() {
  local repo="$1"
  local upstream="$2"
  local ahead="0"
  local behind="0"
  if read -r ahead behind < <(repo_ahead_behind "$repo" "$upstream" || true); then
    printf '%s\t%s\n' "${ahead:-0}" "${behind:-0}"
    return 0
  fi
  printf '0\t0\n'
}

sync_details_json() {
  python3 - "$@" <<'PY'
import json
import sys

print(json.dumps({
    "kind": sys.argv[1],
    "upstream": sys.argv[2],
    "had_dirty": sys.argv[3] == "true",
    "ahead_before": int(sys.argv[4]),
    "behind_before": int(sys.argv[5]),
    "ahead_after": int(sys.argv[6]),
    "behind_after": int(sys.argv[7]),
    "history_action": sys.argv[8],
    "push_action": sys.argv[9],
    "restore_action": sys.argv[10],
    "reconciled": sys.argv[11] == "true",
    "reconcile_commit_created": sys.argv[12] == "true",
    "fetch_status": sys.argv[13],
    "fetch_note": sys.argv[14],
}, separators=(",", ":")))
PY
}

append_restore_note() {
  local note="$1"
  local had_dirty="$2"
  local restore_note="$3"
  if [[ "$had_dirty" != "true" || -z "$restore_note" ]]; then
    printf '%s\n' "$note"
    return 0
  fi
  if [[ -n "$note" ]]; then
    printf '%s; %s\n' "$note" "$restore_note"
    return 0
  fi
  printf '%s\n' "$restore_note"
}

push_branch_noninteractive() {
  local repo="$1"
  local branch="$2"
  local mode="$3"
  local out_file=""
  out_file="$(mktemp)"
  if [[ "$mode" == "set-upstream" ]]; then
    if gitops_git_noninteractive "$repo" push -u origin "$branch" >"$out_file" 2>"$out_file.err"; then
      rm -f "$out_file" "$out_file.err"
      return 0
    fi
  else
    if gitops_git_noninteractive "$repo" push >"$out_file" 2>"$out_file.err"; then
      rm -f "$out_file" "$out_file.err"
      return 0
    fi
  fi
  PUSH_ERROR_TEXT="$(compact_text "$(cat "$out_file" "$out_file.err" 2>/dev/null)")"
  rm -f "$out_file" "$out_file.err"
  return 1
}

rebase_branch_onto_upstream() {
  local repo="$1"
  local upstream="$2"
  local out_file=""
  out_file="$(mktemp)"
  if git -C "$repo" rebase "$upstream" >"$out_file" 2>"$out_file.err"; then
    rm -f "$out_file" "$out_file.err"
    return 0
  fi
  REBASE_ERROR_TEXT="$(compact_text "$(cat "$out_file" "$out_file.err" 2>/dev/null)")"
  git -C "$repo" rebase --abort >/dev/null 2>&1 || true
  rm -f "$out_file" "$out_file.err"
  return 1
}

fast_forward_branch_to_upstream() {
  local repo="$1"
  local upstream="$2"
  local out_file=""
  out_file="$(mktemp)"
  if git -C "$repo" merge --ff-only "$upstream" >"$out_file" 2>"$out_file.err"; then
    rm -f "$out_file" "$out_file.err"
    return 0
  fi
  FAST_FORWARD_ERROR_TEXT="$(compact_text "$(cat "$out_file" "$out_file.err" 2>/dev/null)")"
  rm -f "$out_file" "$out_file.err"
  return 1
}

record_sync_outcome() {
  local repo="$1"
  local branch="$2"
  local status="$3"
  local note="$4"
  local upstream="$5"
  local had_dirty="$6"
  local ahead_before="$7"
  local behind_before="$8"
  local ahead_after="$9"
  local behind_after="${10}"
  local history_action="${11}"
  local push_action="${12}"
  local restore_action="${13}"
  local reconciled="${14}"
  local reconcile_commit_created="${15}"
  local fetch_status="${16}"
  local fetch_note="${17}"
  local details=""
  details="$(sync_details_json "sync" "$upstream" "$had_dirty" "$ahead_before" "$behind_before" "$ahead_after" "$behind_after" "$history_action" "$push_action" "$restore_action" "$reconciled" "$reconcile_commit_created" "$fetch_status" "$fetch_note")"
  record_result "$repo" "$branch" "$status" "$note" "$details"
}

sync_one_repo() {
  local repo="$1"
  local had_dirty="false"
  local branch=""
  local upstream=""
  local history_action="noop"
  local push_action="noop"
  local restore_action="noop"
  local ahead_before="0"
  local behind_before="0"
  local ahead_after="0"
  local behind_after="0"
  local status=""
  local note=""

  PUSH_ERROR_TEXT=""
  REBASE_ERROR_TEXT=""
  FAST_FORWARD_ERROR_TEXT=""
  SYNC_STASH_REF=""
  SYNC_STASHED="false"
  SYNC_RESTORE_KIND="none"
  SYNC_RESTORE_NOTE=""
  [[ -n "$SYNC_SNAPSHOT_DIR" && -d "$SYNC_SNAPSHOT_DIR" ]] && rm -rf "$SYNC_SNAPSHOT_DIR"
  SYNC_SNAPSHOT_DIR=""

  gitops_prepare_repo_for_stateful_command "$repo" "$DETACHED_MODE" || {
    local code=$?
    if [[ $code -eq 10 ]]; then
      record_sync_outcome "$repo" "$GITOPS_RECOVERED_BRANCH" "blocked-rescue" "detached HEAD recovered into rescue branch; review before syncing" "" "$had_dirty" "$ahead_before" "$behind_before" "$ahead_after" "$behind_after" "blocked" "$push_action" "$restore_action" "false" "false" "$GITOPS_FETCH_STATUS" "${GITOPS_FETCH_NOTE:-}"
      return 0
    fi
    if [[ $code -eq 20 ]]; then
      record_sync_outcome "$repo" "$(current_branch_name "$repo" || echo DETACHED)" "blocked-recovery" "$GITOPS_RECOVERY_NEXT_ACTION" "" "$had_dirty" "$ahead_before" "$behind_before" "$ahead_after" "$behind_after" "blocked" "$push_action" "$restore_action" "false" "false" "$GITOPS_FETCH_STATUS" "${GITOPS_FETCH_NOTE:-}"
      return 0
    fi
    return "$code"
  }

  branch="$GITOPS_RECOVERED_BRANCH"

  if [[ "$GITOPS_FETCH_STATUS" == "warning" ]]; then
    record_sync_outcome "$repo" "$branch" "blocked-fetch" "${GITOPS_FETCH_NOTE:-failed to fetch origin}" "" "$had_dirty" "$ahead_before" "$behind_before" "$ahead_after" "$behind_after" "blocked" "$push_action" "$restore_action" "false" "false" "$GITOPS_FETCH_STATUS" "${GITOPS_FETCH_NOTE:-}"
    return 0
  fi

  if maybe_stash_for_sync "$repo"; then
    had_dirty="true"
  fi

  if ! repo_has_origin "$repo"; then
    if [[ "$had_dirty" == "true" ]]; then
      if ! restore_sync_stash "$repo"; then
        record_sync_outcome "$repo" "$branch" "blocked-restore" "$SYNC_RESTORE_NOTE" "$upstream" "$had_dirty" "$ahead_before" "$behind_before" "$ahead_after" "$behind_after" "$history_action" "$push_action" "blocked" "false" "false" "$GITOPS_FETCH_STATUS" "${GITOPS_FETCH_NOTE:-}"
        return 0
      fi
      case "$SYNC_RESTORE_KIND" in
        stash) restore_action="stash-pop" ;;
        fallback) restore_action="snapshot-fallback" ;;
      esac
    fi
    note="$(append_restore_note "no origin remote configured" "$had_dirty" "$SYNC_RESTORE_NOTE")"
    record_sync_outcome "$repo" "$branch" "skipped-no-origin" "$note" "$upstream" "$had_dirty" "$ahead_before" "$behind_before" "$ahead_after" "$behind_after" "$history_action" "$push_action" "$restore_action" "false" "false" "$GITOPS_FETCH_STATUS" "${GITOPS_FETCH_NOTE:-}"
    return 0
  fi

  upstream="$(current_upstream_ref "$repo")"
  if [[ -z "$upstream" ]] && ensure_tracking_branch_if_remote_exists "$repo" "$branch"; then
    history_action="set-upstream"
    upstream="$(current_upstream_ref "$repo")"
  fi

  if [[ -n "$upstream" ]]; then
    read -r ahead_before behind_before < <(read_ahead_behind_counts "$repo" "$upstream")
    if [[ "$behind_before" -gt 0 && "$ahead_before" -eq 0 ]]; then
      if ! fast_forward_branch_to_upstream "$repo" "$upstream"; then
        if [[ "$had_dirty" == "true" ]] && restore_sync_stash "$repo"; then
          case "$SYNC_RESTORE_KIND" in
            stash) restore_action="stash-pop" ;;
            fallback) restore_action="snapshot-fallback" ;;
            blocked) restore_action="blocked" ;;
          esac
        elif [[ "$had_dirty" == "true" ]]; then
          restore_action="blocked"
        fi
        note="$(append_restore_note "${FAST_FORWARD_ERROR_TEXT:-failed to fast-forward from upstream}" "$had_dirty" "$SYNC_RESTORE_NOTE")"
        record_sync_outcome "$repo" "$branch" "blocked-fast-forward" "$note" "$upstream" "$had_dirty" "$ahead_before" "$behind_before" "$ahead_after" "$behind_after" "blocked" "$push_action" "$restore_action" "false" "false" "$GITOPS_FETCH_STATUS" "${GITOPS_FETCH_NOTE:-}"
        return 0
      fi
      history_action="fast-forward"
    elif [[ "$ahead_before" -gt 0 && "$behind_before" -gt 0 ]]; then
      if ! rebase_branch_onto_upstream "$repo" "$upstream"; then
        if [[ "$had_dirty" == "true" ]] && restore_sync_stash "$repo"; then
          case "$SYNC_RESTORE_KIND" in
            stash) restore_action="stash-pop" ;;
            fallback) restore_action="snapshot-fallback" ;;
            blocked) restore_action="blocked" ;;
          esac
        elif [[ "$had_dirty" == "true" ]]; then
          restore_action="blocked"
        fi
        note="$(append_restore_note "${REBASE_ERROR_TEXT:-failed to rebase onto upstream}" "$had_dirty" "$SYNC_RESTORE_NOTE")"
        record_sync_outcome "$repo" "$branch" "blocked-rebase" "$note" "$upstream" "$had_dirty" "$ahead_before" "$behind_before" "$ahead_after" "$behind_after" "blocked" "$push_action" "$restore_action" "false" "false" "$GITOPS_FETCH_STATUS" "${GITOPS_FETCH_NOTE:-}"
        return 0
      fi
      history_action="rebase"
    fi
  fi

  if [[ "$had_dirty" == "true" ]]; then
    if ! restore_sync_stash "$repo"; then
      record_sync_outcome "$repo" "$branch" "blocked-restore" "$SYNC_RESTORE_NOTE" "$upstream" "$had_dirty" "$ahead_before" "$behind_before" "$ahead_after" "$behind_after" "$history_action" "$push_action" "blocked" "false" "false" "$GITOPS_FETCH_STATUS" "${GITOPS_FETCH_NOTE:-}"
      return 0
    fi
    case "$SYNC_RESTORE_KIND" in
      stash) restore_action="stash-pop" ;;
      fallback) restore_action="snapshot-fallback" ;;
    esac
  fi

  upstream="$(current_upstream_ref "$repo")"
  if [[ -n "$upstream" ]]; then
    read -r ahead_after behind_after < <(read_ahead_behind_counts "$repo" "$upstream")
  fi

  if [[ -z "$upstream" ]]; then
    history_action="publish"
    if ! push_branch_noninteractive "$repo" "$branch" "set-upstream"; then
      note="$(append_restore_note "${PUSH_ERROR_TEXT:-failed to publish branch '$branch'}" "$had_dirty" "$SYNC_RESTORE_NOTE")"
      record_sync_outcome "$repo" "$branch" "blocked-push" "$note" "$upstream" "$had_dirty" "$ahead_before" "$behind_before" "$ahead_after" "$behind_after" "$history_action" "blocked" "$restore_action" "false" "false" "$GITOPS_FETCH_STATUS" "${GITOPS_FETCH_NOTE:-}"
      return 0
    fi
    push_action="push-set-upstream"
    upstream="$(current_upstream_ref "$repo")"
    if [[ -n "$upstream" ]]; then
      read -r ahead_after behind_after < <(read_ahead_behind_counts "$repo" "$upstream")
    fi
  elif [[ "$ahead_after" -gt 0 ]]; then
    if ! push_branch_noninteractive "$repo" "$branch" "push"; then
      note="$(append_restore_note "${PUSH_ERROR_TEXT:-failed to push branch '$branch'}" "$had_dirty" "$SYNC_RESTORE_NOTE")"
      record_sync_outcome "$repo" "$branch" "blocked-push" "$note" "$upstream" "$had_dirty" "$ahead_before" "$behind_before" "$ahead_after" "$behind_after" "$history_action" "blocked" "$restore_action" "false" "false" "$GITOPS_FETCH_STATUS" "${GITOPS_FETCH_NOTE:-}"
      return 0
    fi
    push_action="push"
    read -r ahead_after behind_after < <(read_ahead_behind_counts "$repo" "$upstream")
  fi

  if [[ "$restore_action" == "snapshot-fallback" ]]; then
    status="synced-with-fallback"
  elif [[ "$push_action" == "push-set-upstream" ]]; then
    status="published"
  elif [[ "$history_action" == "rebase" && "$push_action" == "push" ]]; then
    status="rebased-and-pushed"
  elif [[ "$history_action" == "fast-forward" && "$push_action" == "push" ]]; then
    status="pulled-and-pushed"
  elif [[ "$history_action" == "fast-forward" ]]; then
    status="pulled"
  elif [[ "$push_action" == "push" ]]; then
    status="pushed"
  else
    status="up-to-date"
  fi

  case "$status" in
    synced-with-fallback)
      if [[ "$push_action" == "push-set-upstream" ]]; then
        note="published branch '$branch' to origin and set upstream"
      elif [[ "$history_action" == "rebase" && "$push_action" == "push" ]]; then
        note="rebased onto '$upstream' and pushed branch '$branch'"
      elif [[ "$history_action" == "fast-forward" && "$push_action" == "push" ]]; then
        note="fast-forwarded from '$upstream' and pushed branch '$branch'"
      elif [[ "$history_action" == "fast-forward" ]]; then
        note="fast-forwarded from '$upstream'"
      elif [[ "$push_action" == "push" ]]; then
        note="pushed local commits for branch '$branch'"
      else
        note="branch '$branch' is in sync with its upstream"
      fi
      note="$(append_restore_note "$note" "$had_dirty" "$SYNC_RESTORE_NOTE")"
      ;;
    published)
      note="$(append_restore_note "published branch '$branch' to origin and set upstream" "$had_dirty" "$SYNC_RESTORE_NOTE")"
      ;;
    rebased-and-pushed)
      note="$(append_restore_note "rebased onto '$upstream' and pushed branch '$branch'" "$had_dirty" "$SYNC_RESTORE_NOTE")"
      ;;
    pulled-and-pushed)
      note="$(append_restore_note "fast-forwarded from '$upstream' and pushed branch '$branch'" "$had_dirty" "$SYNC_RESTORE_NOTE")"
      ;;
    pulled)
      note="$(append_restore_note "fast-forwarded from '$upstream'" "$had_dirty" "$SYNC_RESTORE_NOTE")"
      ;;
    pushed)
      note="$(append_restore_note "pushed local commits for branch '$branch'" "$had_dirty" "$SYNC_RESTORE_NOTE")"
      ;;
    up-to-date)
      if [[ "$history_action" == "set-upstream" && -n "$upstream" ]]; then
        note="$(append_restore_note "attached upstream '$upstream' for branch '$branch'; branch is already in sync" "$had_dirty" "$SYNC_RESTORE_NOTE")"
      else
        note="$(append_restore_note "branch '$branch' is already in sync with its upstream" "$had_dirty" "$SYNC_RESTORE_NOTE")"
      fi
      ;;
  esac

  record_sync_outcome "$repo" "$branch" "$status" "$note" "$upstream" "$had_dirty" "$ahead_before" "$behind_before" "$ahead_after" "$behind_after" "$history_action" "$push_action" "$restore_action" "false" "false" "$GITOPS_FETCH_STATUS" "${GITOPS_FETCH_NOTE:-}"
}

record_reconcile_result() {
  local repo="$1"
  local branch="$2"
  local status="$3"
  local note="$4"
  local reconcile_commit_created="$5"
  local push_action="noop"
  local details=""
  case "$status" in
    published|reconcile-pushed) push_action="push" ;;
  esac
  details="$(sync_details_json "reconcile-followup" "$(current_upstream_ref "$repo")" "false" "0" "0" "0" "0" "noop" "$push_action" "noop" "true" "$reconcile_commit_created" "not-run" "")"
  record_result "$repo" "$branch" "$status" "$note" "$details"
}

run_reconcile_followups() {
  local reconcile_file="$1"
  local repo=""
  local action=""
  local note=""
  local branch=""
  local upstream=""
  local ahead="0"
  local behind="0"
  local reconcile_commit_created="false"

  while IFS=$'\t' read -r repo action note; do
    [[ -n "$repo" ]] || continue
    branch="$(current_branch_name "$repo" || echo DETACHED)"
    reconcile_commit_created="false"
    [[ "$action" == "parent-gitlink-commit" ]] && reconcile_commit_created="true"

    if [[ "$action" == blocked:* ]]; then
      record_reconcile_result "$repo" "$branch" "blocked-reconcile" "$note" "$reconcile_commit_created"
      continue
    fi

    upstream="$(current_upstream_ref "$repo")"
    if [[ -z "$upstream" ]]; then
      if ! repo_has_origin "$repo"; then
        record_reconcile_result "$repo" "$branch" "reconcile-noop" "$note; no origin remote configured" "$reconcile_commit_created"
        continue
      fi
      if ! push_branch_noninteractive "$repo" "$branch" "set-upstream"; then
        record_reconcile_result "$repo" "$branch" "blocked-push" "$note; ${PUSH_ERROR_TEXT:-failed to publish reconcile follow-up changes}" "$reconcile_commit_created"
        continue
      fi
      record_reconcile_result "$repo" "$branch" "published" "$note; published reconcile follow-up changes and set upstream" "$reconcile_commit_created"
      continue
    fi

    read -r ahead behind < <(read_ahead_behind_counts "$repo" "$upstream")
    if [[ "$ahead" -gt 0 ]]; then
      if ! push_branch_noninteractive "$repo" "$branch" "push"; then
        record_reconcile_result "$repo" "$branch" "blocked-push" "$note; ${PUSH_ERROR_TEXT:-failed to push reconcile follow-up changes}" "$reconcile_commit_created"
        continue
      fi
      record_reconcile_result "$repo" "$branch" "reconcile-pushed" "$note; pushed reconcile follow-up changes" "$reconcile_commit_created"
      continue
    fi

    record_reconcile_result "$repo" "$branch" "reconcile-noop" "$note; no additional push was needed after reconciliation" "$reconcile_commit_created"
  done < <(
    python3 - "$reconcile_file" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
entries = []
seen = set()
for action in payload.get("actions", []):
    status = action.get("status", "")
    parent = action.get("parent", "")
    child = action.get("child", "")
    note = action.get("note", "")
    if status == "parent-gitlink-commit":
        key = (parent, status)
        if key not in seen:
            entries.append((parent, status, note))
            seen.add(key)
    elif status == "child-fast-forward":
        key = (child, status)
        if key not in seen:
            entries.append((child, status, note))
            seen.add(key)
    elif status.startswith("blocked"):
        target = child if child and child != "." else parent
        key = (target, status)
        if key not in seen:
            entries.append((target, f"blocked:{status}", note))
            seen.add(key)
for repo, status, note in entries:
    print(f"{repo}\t{status}\t{note}")
PY
  )
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
  RECONCILE_JSON="$(mktemp)"
  if bash "$SCRIPT_DIR/reconcile-tree.sh" --repo "$ROOT_REPO" --mode apply --json >"$RECONCILE_JSON" 2>"$RECONCILE_JSON.err"; then
    run_reconcile_followups "$RECONCILE_JSON"
  else
    RECONCILE_OUTPUT="$(compact_text "$(cat "$RECONCILE_JSON" "$RECONCILE_JSON.err" 2>/dev/null)")"
    record_reconcile_result "$ROOT_REPO" "$(current_branch_name "$ROOT_REPO" || echo DETACHED)" "reconcile-failed" "${RECONCILE_OUTPUT:-failed to reconcile the related tree}" "false"
  fi
  rm -f "$RECONCILE_JSON" "$RECONCILE_JSON.err"
fi

if [[ "$JSON" == "true" ]]; then
  emit_json "$RESULTS_FILE"
else
  emit_text "$RESULTS_FILE"
fi
