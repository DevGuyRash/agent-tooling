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
SCOPE="tree"
FETCH="true"
RESULTS_FILE=""

print_help() {
  cat <<'USAGE'
Usage:
  bash scripts/repo-state.sh [--repo <path>] [--json] [--no-recurse-related] [--no-fetch]

Behavior:
  - Reports repo state for the current repo or the full related tree.
  - Fetch/prune preflight runs by default when origin exists.
  - Human output stays concise; JSON output includes machine-readable per-repo state.

Options:
  --repo <path>          Repository path to inspect (default: current directory).
  --json                 Emit machine-readable JSON.
  --no-recurse-related   Inspect only the current repo, not the full related tree.
  --no-fetch             Skip fetch/prune preflight.
  -h, --help             Show help.
USAGE
}

emit_json() {
  local file="$1"
  python3 - "$file" "$SCOPE" "$ROOT_REPO" <<'PY'
import json
import sys
from pathlib import Path

items = []
for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    (
        repo,
        role,
        branch,
        head_oid,
        detached,
        detached_candidates,
        default_base,
        upstream,
        ahead,
        behind,
        dirty_tracked,
        dirty_untracked,
        sequencer_state,
        in_linked_worktree,
        main_checkout,
        worktree_path,
        superproject,
        gitlink_status,
        recovery_class,
        next_action,
        fetch_status,
        fetch_note,
    ) = line.split("\t", 21)
    items.append(
        {
            "repo": repo,
            "role": role,
            "branch": branch,
            "head_oid": head_oid,
            "detached": detached == "true",
            "detached_candidates": [x for x in detached_candidates.split(",") if x],
            "default_base": default_base,
            "upstream": upstream,
            "ahead": int(ahead),
            "behind": int(behind),
            "dirty_tracked": int(dirty_tracked),
            "dirty_untracked": int(dirty_untracked),
            "sequencer_state": sequencer_state,
            "in_linked_worktree": in_linked_worktree == "true",
            "main_checkout": main_checkout,
            "worktree_path": worktree_path,
            "superproject": superproject,
            "gitlink_status": gitlink_status,
            "recovery_class": recovery_class,
            "next_action": next_action,
            "fetch_status": fetch_status,
            "fetch_note": fetch_note,
        }
    )
print(json.dumps({"scope": sys.argv[2], "root_repo": sys.argv[3], "results": items}, indent=2))
PY
}

record_result() {
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$1" "$2" "$3" "$4" "$5" "$6" "$7" "$8" "$9" "${10}" "${11}" "${12}" "${13}" "${14}" "${15}" "${16}" "${17}" "${18}" "${19}" "${20}" "${21}" "${22}" >> "$RESULTS_FILE"
}

render_human() {
  local file="$1"
  echo "Scope: $SCOPE"
  echo "Root repo: $ROOT_REPO"
  while IFS=$'\t' read -r repo role branch head_oid detached detached_candidates default_base upstream ahead behind dirty_tracked dirty_untracked sequencer_state in_linked_worktree main_checkout worktree_path superproject gitlink_status recovery_class next_action fetch_status fetch_note; do
    echo ""
    echo "$role: $repo"
    echo "  branch: $branch"
    echo "  default base: ${default_base:-none}"
    [[ -n "$upstream" ]] && echo "  upstream: $upstream (ahead $ahead / behind $behind)"
    [[ "$detached" == "true" ]] && echo "  detached candidates: ${detached_candidates:-none}"
    echo "  dirty: tracked=$dirty_tracked untracked=$dirty_untracked"
    echo "  sequencer: ${sequencer_state:-none}"
    echo "  gitlink: $gitlink_status"
    echo "  recovery: $recovery_class"
    echo "  next: $next_action"
    [[ "$fetch_status" != "not-run" ]] && echo "  fetch: $fetch_status"
    [[ -n "$fetch_note" ]] && echo "  fetch note: $fetch_note"
  done < "$file"
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
    --no-recurse-related)
      SCOPE="current"
      shift
      ;;
    --no-fetch)
      FETCH="false"
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

ROOT_REPO="$(outermost_superproject_path "$REPO_PATH")"
RESULTS_FILE="$(mktemp)"
trap 'rm -f "$RESULTS_FILE"' EXIT

if [[ "$SCOPE" == "tree" ]]; then
  mapfile -t repos < <(gitops_scope_paths "$REPO_PATH" tree asc)
else
  repos=("$(repo_root_path "$REPO_PATH")")
fi

for repo in "${repos[@]}"; do
  fetch_status="not-run"
  fetch_note=""
  if [[ "$FETCH" == "true" ]]; then
    gitops_fetch_prune_repo "$repo" || true
    fetch_status="$GITOPS_FETCH_STATUS"
    fetch_note="$GITOPS_FETCH_NOTE"
  fi
  branch="$(current_branch_name "$repo" || true)"
  detached="false"
  if [[ -z "$branch" ]]; then
    branch="DETACHED"
    detached="true"
  fi
  candidates="$(detached_candidate_branches "$repo" | paste -sd ',' -)"
  default_base="$(resolve_default_base "$repo" || true)"
  upstream="$(current_upstream_ref "$repo")"
  ahead="0"
  behind="0"
  if read -r ahead behind < <(repo_ahead_behind "$repo" "$upstream" || true); then
    :
  fi
  tracked="$(repo_dirty_tracked_count "$repo")"
  untracked="$(repo_dirty_untracked_count "$repo")"
  sequencer="$(repo_sequencer_state "$repo")"
  in_worktree="false"
  if in_linked_worktree "$repo"; then
    in_worktree="true"
  fi
  main_checkout="$(main_checkout_path "$repo")"
  worktree_path="$(repo_root_path "$repo")"
  superproject="$(repo_superproject_path "$repo")"
  gitlink_status="$(gitlink_status_against_parent "$repo")"
  recovery_class="$(repo_recovery_class "$repo")"
  next_action="continue with the requested workflow"
  if [[ "$recovery_class" == safe-sequencer-abort* || "$recovery_class" == "safe-detached-reattach" ]]; then
    next_action="safe automatic recovery is available"
  elif [[ "$recovery_class" == *rescue-detached* ]]; then
    next_action="run recover-repo-state or review detached work before continuing"
  elif [[ "$recovery_class" == blocked-* ]]; then
    next_action="finish or abort the in-progress git operation before continuing"
  elif [[ "$gitlink_status" == "child-ahead" ]]; then
    next_action="run reconcile-tree after validating the child repo changes"
  elif [[ "$gitlink_status" == "parent-ahead" ]]; then
    next_action="sync or reconcile the child checkout to the recorded gitlink"
  fi
  record_result \
    "$repo" \
    "$(gitops_role_for_repo "$REPO_PATH" "$repo")" \
    "$branch" \
    "$(repo_head_oid "$repo")" \
    "$detached" \
    "$candidates" \
    "$default_base" \
    "$upstream" \
    "$ahead" \
    "$behind" \
    "$tracked" \
    "$untracked" \
    "$sequencer" \
    "$in_worktree" \
    "$main_checkout" \
    "$worktree_path" \
    "$superproject" \
    "$gitlink_status" \
    "$recovery_class" \
    "$next_action" \
    "$fetch_status" \
    "$fetch_note"
done

if [[ "$JSON" == "true" ]]; then
  emit_json "$RESULTS_FILE"
else
  render_human "$RESULTS_FILE"
fi
