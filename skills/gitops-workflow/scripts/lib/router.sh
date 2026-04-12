#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/common.sh"
# shellcheck source=git-state.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/git-state.sh"

gitops_scope_paths() {
  local repo="${1:-.}"
  local scope="${2:-current}"
  local order="${3:-asc}"
  if [[ "$scope" == "tree" ]]; then
    gitops_related_repos_in_order "$repo" "$order"
    return 0
  fi
  repo_root_path "$repo"
}

gitops_role_for_repo() {
  local requested_repo="${1:-.}"
  local candidate_repo="$2"
  local current_root=""
  local outer_root=""
  current_root="$(repo_root_path "$requested_repo")"
  outer_root="$(outermost_superproject_path "$requested_repo")"
  if [[ "$candidate_repo" == "$current_root" && "$candidate_repo" == "$outer_root" ]]; then
    echo "current-root"
    return 0
  fi
  if [[ "$candidate_repo" == "$current_root" ]]; then
    echo "current"
    return 0
  fi
  if [[ "$candidate_repo" == "$outer_root" ]]; then
    echo "root"
    return 0
  fi
  echo "submodule"
}

reset_gitops_fetch_state() {
  GITOPS_FETCH_STATUS="not-run"
  GITOPS_FETCH_NOTE=""
}

gitops_fetch_prune_repo() {
  local repo="${1:-.}"
  local output=""
  reset_gitops_fetch_state
  if ! repo_has_origin "$repo"; then
    GITOPS_FETCH_STATUS="skipped-no-origin"
    GITOPS_FETCH_NOTE="no origin remote configured"
    return 0
  fi
  if output="$(git -C "$repo" fetch origin --prune 2>&1)"; then
    GITOPS_FETCH_STATUS="fetched"
    return 0
  fi
  GITOPS_FETCH_STATUS="warning"
  GITOPS_FETCH_NOTE="$(compact_text "$output")"
  return 1
}

gitops_prepare_repo_for_stateful_command() {
  local repo="${1:-.}"
  local detached_mode="${2:-recover}"
  gitops_fetch_prune_repo "$repo" || true
  recover_repo_for_stateful_command "$repo" "$detached_mode"
}
