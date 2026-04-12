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
MODE="apply"
JSON="false"

print_help() {
  cat <<'USAGE'
Usage:
  bash scripts/reconcile-tree.sh [--repo <path>] [--json] [--mode check|apply]

Behavior:
  - Discovers the related parent/submodule tree from the outermost superproject.
  - Fast-forwards clean child repositories to parent-recorded gitlinks when safe.
  - Auto-commits parent gitlink updates as isolated chore(submodules) commits when children advanced.

Options:
  --repo <path>      Repository path to inspect (default: current directory).
  --json             Emit machine-readable JSON.
  --mode <mode>      check or apply (default: apply).
  -h, --help         Show help.
USAGE
}

emit_actions() {
  local file="$1"
  if [[ "$JSON" == "true" ]]; then
    python3 - "$file" <<'PY'
import json
import sys
from pathlib import Path

actions = []
path = Path(sys.argv[1])
if path.exists():
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        status, parent, child, relpath, note = line.split("\t", 4)
        actions.append(
            {
                "status": status,
                "parent": parent,
                "child": child,
                "path": relpath,
                "note": note,
            }
        )
print(json.dumps({"actions": actions}, indent=2))
PY
  else
    if [[ ! -s "$file" ]]; then
      echo "No tree reconciliation changes needed."
      return 0
    fi
    while IFS=$'\t' read -r status parent child relpath note; do
      echo "$status: $relpath"
      echo "  parent: $parent"
      echo "  child:  $child"
      [[ -n "$note" ]] && echo "  note:   $note"
    done < "$file"
  fi
}

record_action() {
  local status="$1"
  local parent="$2"
  local child="$3"
  local relpath="$4"
  local note="$5"
  printf '%s\t%s\t%s\t%s\t%s\n' "$status" "$parent" "$child" "$relpath" "$note" >> "$ACTIONS_FILE"
}

repo_is_dirty() {
  local repo="$1"
  [[ -n "$(git -C "$repo" status --porcelain)" ]]
}

safe_fast_forward_child() {
  local child="$1"
  local target_sha="$2"
  local branch=""
  branch="$(ensure_attached_branch "$child" recover)" || {
    local code=$?
    if [[ $code -eq 10 ]]; then
      return 10
    fi
    return "$code"
  }
  if repo_is_dirty "$child"; then
    return 11
  fi
  if [[ "$(git -C "$child" rev-parse HEAD)" == "$target_sha" ]]; then
    return 0
  fi
  if git -C "$child" merge-base --is-ancestor HEAD "$target_sha" >/dev/null 2>&1; then
    if [[ "$MODE" == "apply" ]]; then
      git -C "$child" merge --ff-only "$target_sha" >/dev/null 2>&1 || return 12
    fi
    return 0
  fi
  return 13
}

commit_parent_gitlinks() {
  local parent="$1"
  shift
  local -a relpaths=("$@")
  [[ "${#relpaths[@]}" -gt 0 ]] || return 0

  local msg_file=""
  msg_file="$(mktemp)"
  trap 'rm -f "${msg_file:-}"' RETURN

  local args=(
    "$SCRIPT_DIR/commit-message.py"
    --type chore
    --scope submodules
    --subject "update gitlinks"
  )
  local rel
  for rel in "${relpaths[@]}"; do
    args+=(--bullet "update $rel to $(git -C "$parent/$rel" rev-parse --short=8 HEAD)")
  done
  python3 "${args[@]}" --out "$msg_file"

  if [[ "$MODE" == "apply" ]]; then
    git -C "$parent" add -- "${relpaths[@]}"
    git -C "$parent" commit --only -F "$msg_file" -- "${relpaths[@]}" >/dev/null 2>&1 || die "failed to commit gitlink updates in '$parent'"
  fi
  rm -f "$msg_file"
  trap - RETURN
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
    --mode)
      require_opt_value "--mode" "${2:-}"
      MODE="${2:-}"
      shift 2
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

[[ "$MODE" == "check" || "$MODE" == "apply" ]] || die "invalid --mode '$MODE'"
require_cmd git
require_cmd python3

if ! git -C "$REPO_PATH" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  die "--repo is not a git repository: $REPO_PATH"
fi

ACTIONS_FILE="$(mktemp)"
trap 'rm -f "$ACTIONS_FILE"' EXIT

ROOT_REPO="$(outermost_superproject_path "$REPO_PATH")"

mapfile -t related_entries < <(list_related_repos "$ROOT_REPO")
mapfile -t parent_entries < <(printf '%s\n' "${related_entries[@]}" | sort -r -n -k1,1)

declare -A PARENT_PATHS=()

for entry in "${parent_entries[@]}"; do
  parent="${entry#*$'\t'}"
  gitops_prepare_repo_for_stateful_command "$parent" recover || {
    code=$?
    if [[ $code -eq 10 ]]; then
      record_action "blocked-rescue" "$parent" "$parent" "." "parent recovered into rescue branch '$GITOPS_RECOVERED_BRANCH'; review before reconciliation"
      continue
    fi
    if [[ $code -eq 20 ]]; then
      record_action "blocked-recovery" "$parent" "$parent" "." "$GITOPS_RECOVERY_NEXT_ACTION"
      continue
    fi
    exit "$code"
  }
  if [[ "$GITOPS_FETCH_STATUS" == "warning" ]]; then
    record_action "fetch-warning" "$parent" "$parent" "." "$GITOPS_FETCH_NOTE"
  fi
  while IFS= read -r child; do
    [[ -n "$child" ]] || continue
    gitops_prepare_repo_for_stateful_command "$child" recover || {
      child_result=$?
      if [[ $child_result -eq 10 ]]; then
        relpath="$(python3 - "$parent" "$child" <<'PY'
from pathlib import Path
import os
import sys

print(os.path.relpath(Path(sys.argv[2]), Path(sys.argv[1])))
PY
)"
        record_action "blocked-rescue" "$parent" "$child" "$relpath" "detached child recovered into rescue branch '$GITOPS_RECOVERED_BRANCH'; rerun after review"
        continue
      fi
      if [[ $child_result -eq 20 ]]; then
        relpath="$(python3 - "$parent" "$child" <<'PY'
from pathlib import Path
import os
import sys

print(os.path.relpath(Path(sys.argv[2]), Path(sys.argv[1])))
PY
)"
        record_action "blocked-recovery" "$parent" "$child" "$relpath" "$GITOPS_RECOVERY_NEXT_ACTION"
        continue
      fi
      exit "$child_result"
    }
    if [[ "$GITOPS_FETCH_STATUS" == "warning" ]]; then
      relpath="$(python3 - "$parent" "$child" <<'PY'
from pathlib import Path
import os
import sys

print(os.path.relpath(Path(sys.argv[2]), Path(sys.argv[1])))
PY
)"
      record_action "fetch-warning" "$parent" "$child" "$relpath" "$GITOPS_FETCH_NOTE"
    fi
    relpath="$(python3 - "$parent" "$child" <<'PY'
from pathlib import Path
import os
import sys

print(os.path.relpath(Path(sys.argv[2]), Path(sys.argv[1])))
PY
)"
    recorded_sha="$(git -C "$parent" rev-parse "HEAD:$relpath" 2>/dev/null || true)"
    [[ -n "$recorded_sha" ]] || continue
    child_head="$(git -C "$child" rev-parse HEAD)"
    if [[ "$recorded_sha" == "$child_head" ]]; then
      continue
    fi
    if safe_fast_forward_child "$child" "$recorded_sha"; then
      record_action "child-fast-forward" "$parent" "$child" "$relpath" "aligned child checkout with parent gitlink"
      continue
    fi
    child_result=$?
    if [[ $child_result -eq 10 ]]; then
      record_action "blocked-rescue" "$parent" "$child" "$relpath" "detached child recovered into rescue branch; rerun after review"
      continue
    fi
    if [[ $child_result -eq 11 ]]; then
      record_action "blocked-dirty-child" "$parent" "$child" "$relpath" "child checkout is dirty and was left untouched"
      continue
    fi
    PARENT_PATHS["$parent"]+="$relpath"$'\n'
  done < <(list_child_submodule_paths "$parent")
done

for entry in "${parent_entries[@]}"; do
  parent="${entry#*$'\t'}"
  rel_list="${PARENT_PATHS[$parent]:-}"
  [[ -n "$rel_list" ]] || continue
  mapfile -t relpaths < <(printf '%s' "$rel_list" | awk 'NF && !seen[$0]++')
  if [[ "${#relpaths[@]}" -eq 0 ]]; then
    continue
  fi
  commit_parent_gitlinks "$parent" "${relpaths[@]}"
  for relpath in "${relpaths[@]}"; do
    child="$parent/$relpath"
    record_action "parent-gitlink-commit" "$parent" "$child" "$relpath" "recorded child HEAD in parent as isolated gitlink commit"
  done
done

emit_actions "$ACTIONS_FILE"
