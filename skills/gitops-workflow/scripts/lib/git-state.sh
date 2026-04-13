#!/usr/bin/env bash
set -euo pipefail

: "${GITOPS_DETACHED_STATUS:=attached}"
: "${GITOPS_STASHED_REF:=}"

gitops_now_stamp() {
  date '+%Y%m%d-%H%M%S'
}

repo_has_origin() {
  local repo="${1:-.}"
  git -C "$repo" remote get-url origin >/dev/null 2>&1
}

resolve_default_base() {
  local repo="${1:-.}"
  local base=""
  base="$(git -C "$repo" symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##' || true)"
  if [[ -n "$base" ]]; then
    echo "$base"
    return 0
  fi
  local candidate
  for candidate in main master trunk; do
    if git -C "$repo" show-ref --verify --quiet "refs/heads/$candidate"; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

current_branch_name() {
  local repo="${1:-.}"
  local branch=""
  branch="$(git -C "$repo" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  if [[ "$branch" == "HEAD" || -z "$branch" ]]; then
    return 1
  fi
  echo "$branch"
}

current_upstream_ref() {
  local repo="${1:-.}"
  git -C "$repo" rev-parse --abbrev-ref --symbolic-full-name "@{upstream}" 2>/dev/null || true
}

repo_head_oid() {
  local repo="${1:-.}"
  git -C "$repo" rev-parse HEAD
}

repo_dirty_tracked_count() {
  local repo="${1:-.}"
  git -C "$repo" status --porcelain | awk 'substr($0,1,2) !~ /^\?\?/ { count++ } END { print count + 0 }'
}

repo_dirty_untracked_count() {
  local repo="${1:-.}"
  git -C "$repo" ls-files --others --exclude-standard | awk 'END { print NR + 0 }'
}

repo_ahead_behind() {
  local repo="${1:-.}"
  local upstream="${2:-}"
  [[ -n "$upstream" ]] || upstream="$(current_upstream_ref "$repo")"
  if [[ -z "$upstream" ]]; then
    printf '0\t0\n'
    return 1
  fi
  git -C "$repo" rev-list --left-right --count "HEAD...$upstream" 2>/dev/null | awk '{ print $1 "\t" $2 }'
}

repo_root_path() {
  local repo="${1:-.}"
  git -C "$repo" rev-parse --show-toplevel
}

repo_git_common_dir() {
  local repo="${1:-.}"
  git -C "$repo" rev-parse --path-format=absolute --git-common-dir
}

gitops_ship_state_path() {
  local repo="${1:-.}"
  printf '%s/gitops-workflow/ship-state.json\n' "$(repo_git_common_dir "$repo")"
}

main_checkout_path() {
  local repo="${1:-.}"
  local common_dir=""
  common_dir="$(repo_git_common_dir "$repo")"
  cd "$common_dir/.." && pwd -P
}

in_linked_worktree() {
  local repo="${1:-.}"
  local root=""
  local main_checkout=""
  root="$(repo_root_path "$repo")"
  main_checkout="$(main_checkout_path "$repo")"
  [[ "$root" != "$main_checkout" ]]
}

canonical_worktree_path() {
  local repo="${1:-.}"
  local branch="$2"
  local main_checkout=""
  main_checkout="$(main_checkout_path "$repo")"
  printf '%s.worktrees/%s\n' "$main_checkout" "$branch"
}

worktree_path_for_branch() {
  local repo="${1:-.}"
  local branch="$2"
  git -C "$repo" worktree list --porcelain | awk -v want="refs/heads/$branch" '
    $1 == "worktree" { path = substr($0, 10) }
    $1 == "branch" && $2 == want { print path; exit }
  '
}

branch_checked_out_elsewhere() {
  local repo="${1:-.}"
  local branch="$2"
  local root=""
  local path=""
  root="$(repo_root_path "$repo")"
  path="$(worktree_path_for_branch "$repo" "$branch")"
  if [[ -n "$path" && "$path" != "$root" ]]; then
    echo "$path"
  fi
}

repo_sequencer_state() {
  local repo="${1:-.}"
  local states=()
  local merge_head=""
  local rebase_merge=""
  local rebase_apply=""
  local rebase_head=""
  local cherry_pick_head=""
  local revert_head=""
  local bisect_log=""
  merge_head="$(git -C "$repo" rev-parse --path-format=absolute --git-path MERGE_HEAD)"
  rebase_merge="$(git -C "$repo" rev-parse --path-format=absolute --git-path rebase-merge)"
  rebase_apply="$(git -C "$repo" rev-parse --path-format=absolute --git-path rebase-apply)"
  rebase_head="$(git -C "$repo" rev-parse --path-format=absolute --git-path REBASE_HEAD)"
  cherry_pick_head="$(git -C "$repo" rev-parse --path-format=absolute --git-path CHERRY_PICK_HEAD)"
  revert_head="$(git -C "$repo" rev-parse --path-format=absolute --git-path REVERT_HEAD)"
  bisect_log="$(git -C "$repo" rev-parse --path-format=absolute --git-path BISECT_LOG)"
  [[ -e "$merge_head" ]] && states+=("merge")
  [[ -d "$rebase_merge" || -d "$rebase_apply" || -e "$rebase_head" ]] && states+=("rebase")
  [[ -e "$cherry_pick_head" ]] && states+=("cherry-pick")
  [[ -e "$revert_head" ]] && states+=("revert")
  [[ -e "$bisect_log" ]] && states+=("bisect")
  local IFS=,
  echo "${states[*]}"
}

require_no_sequencer_state() {
  local repo="${1:-.}"
  local label="${2:-repository}"
  local states=""
  states="$(repo_sequencer_state "$repo")"
  if [[ -n "$states" ]]; then
    die "$label is in-progress ($states); finish or abort that operation before continuing"
  fi
}

repo_superproject_path() {
  local repo="${1:-.}"
  git -C "$repo" rev-parse --show-superproject-working-tree 2>/dev/null || true
}

outermost_superproject_path() {
  local repo="${1:-.}"
  local current=""
  local parent=""
  current="$(repo_root_path "$repo")"
  while true; do
    parent="$(repo_superproject_path "$current")"
    if [[ -z "$parent" ]]; then
      echo "$current"
      return 0
    fi
    current="$(cd "$parent" && pwd -P)"
  done
}

list_child_submodule_paths() {
  local repo="${1:-.}"
  local root=""
  root="$(repo_root_path "$repo")"
  if [[ ! -f "$root/.gitmodules" ]]; then
    return 0
  fi
  git -C "$root" config -f "$root/.gitmodules" --get-regexp '^submodule\..*\.path$' 2>/dev/null | awk '{print $2}' | while IFS= read -r rel; do
    [[ -n "$rel" ]] || continue
    local abs="$root/$rel"
    if git -C "$abs" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
      cd "$abs" && pwd -P
    fi
  done
}

_list_related_repos_dfs() {
  local repo="$1"
  local depth="$2"
  printf '%s\t%s\n' "$depth" "$repo"
  while IFS= read -r child; do
    [[ -n "$child" ]] || continue
    _list_related_repos_dfs "$child" $((depth + 1))
  done < <(list_child_submodule_paths "$repo")
}

list_related_repos() {
  local repo="${1:-.}"
  local root=""
  root="$(outermost_superproject_path "$repo")"
  _list_related_repos_dfs "$root" 0
}

gitops_related_repos_in_order() {
  local repo="${1:-.}"
  local order="${2:-asc}"
  if [[ "$order" == "desc" ]]; then
    list_related_repos "$repo" | sort -r -n -k1,1 | awk -F '\t' '{print $2}'
    return 0
  fi
  list_related_repos "$repo" | sort -n -k1,1 | awk -F '\t' '{print $2}'
}

ensure_tracking_branch_if_remote_exists() {
  local repo="${1:-.}"
  local branch="$2"
  if git -C "$repo" show-ref --verify --quiet "refs/remotes/origin/$branch"; then
    git -C "$repo" branch --set-upstream-to="origin/$branch" "$branch" >/dev/null 2>&1 || true
    return 0
  fi
  return 1
}

repo_remote_branch_exists() {
  local repo="${1:-.}"
  local branch="$2"
  git -C "$repo" show-ref --verify --quiet "refs/remotes/origin/$branch"
}

gitops_noninteractive_ssh_command() {
  local ssh_cmd="${GIT_SSH_COMMAND:-ssh}"
  if [[ "$ssh_cmd" != *BatchMode=yes* ]]; then
    ssh_cmd="$ssh_cmd -oBatchMode=yes"
  fi
  printf '%s\n' "$ssh_cmd"
}

gitops_git_noninteractive() {
  local repo="${1:-.}"
  shift
  local ssh_cmd=""
  ssh_cmd="$(gitops_noninteractive_ssh_command)"
  env     GIT_TERMINAL_PROMPT=0     GIT_ASKPASS=/bin/true     SSH_ASKPASS=/bin/true     GIT_SSH_COMMAND="$ssh_cmd"     git -C "$repo" "$@"
}

_detached_candidate_branches() {
  local repo="${1:-.}"
  {
    git -C "$repo" for-each-ref --format='%(refname:short)' --points-at HEAD refs/heads 2>/dev/null || true
    git -C "$repo" for-each-ref --format='%(refname:short)' --points-at HEAD refs/remotes/origin 2>/dev/null | sed 's#^origin/##' | grep -v '^HEAD$' || true
    git -C "$repo" reflog --format='%gs' -20 2>/dev/null | sed -nE 's/^checkout: moving from ([^ ]+) to .*$/\1/p' | grep -E '^[A-Za-z0-9._/-]+$' || true
  } | awk '!seen[$0]++'
}

detached_candidate_branches() {
  local repo="${1:-.}"
  _detached_candidate_branches "$repo"
}

detached_recovery_class() {
  local repo="${1:-.}"
  local branch=""
  if branch="$(current_branch_name "$repo")"; then
    echo "attached"
    return 0
  fi

  mapfile -t candidates < <(_detached_candidate_branches "$repo")
  local filtered=()
  local candidate=""
  for candidate in "${candidates[@]}"; do
    [[ -n "$candidate" ]] || continue
    if git -C "$repo" show-ref --verify --quiet "refs/heads/$candidate" || git -C "$repo" show-ref --verify --quiet "refs/remotes/origin/$candidate"; then
      filtered+=("$candidate")
    fi
  done

  if [[ "${#filtered[@]}" -ne 1 ]]; then
    echo "rescue-detached"
    return 0
  fi

  candidate="${filtered[0]}"
  if [[ -n "$(branch_checked_out_elsewhere "$repo" "$candidate")" ]]; then
    echo "rescue-detached"
    return 0
  fi

  if git -C "$repo" show-ref --verify --quiet "refs/heads/$candidate"; then
    if git -C "$repo" merge-base --is-ancestor "refs/heads/$candidate" HEAD >/dev/null 2>&1; then
      echo "safe-detached-reattach"
      return 0
    fi
  elif git -C "$repo" show-ref --verify --quiet "refs/remotes/origin/$candidate" && git -C "$repo" merge-base --is-ancestor "refs/remotes/origin/$candidate" HEAD >/dev/null 2>&1; then
    echo "safe-detached-reattach"
    return 0
  fi

  echo "rescue-detached"
}

sequencer_recovery_class() {
  local repo="${1:-.}"
  local states=""
  states="$(repo_sequencer_state "$repo")"
  if [[ -z "$states" ]]; then
    echo "none"
    return 0
  fi
  if [[ "$states" == *,* ]]; then
    echo "blocked-multi-sequencer"
    return 0
  fi
  case "$states" in
    merge|rebase|cherry-pick|revert|bisect)
      echo "safe-sequencer-abort"
      ;;
    *)
      echo "blocked-unknown-sequencer"
      ;;
  esac
}

repo_recovery_class() {
  local repo="${1:-.}"
  local seq_class=""
  local detached_class=""
  seq_class="$(sequencer_recovery_class "$repo")"
  detached_class="$(detached_recovery_class "$repo")"

  if [[ "$seq_class" == "none" && "$detached_class" == "attached" ]]; then
    echo "none"
    return 0
  fi
  if [[ "$seq_class" == "safe-sequencer-abort" && "$detached_class" == "attached" ]]; then
    echo "safe-sequencer-abort"
    return 0
  fi
  if [[ "$seq_class" == "none" && "$detached_class" == "safe-detached-reattach" ]]; then
    echo "safe-detached-reattach"
    return 0
  fi
  if [[ "$seq_class" == "safe-sequencer-abort" && "$detached_class" == "safe-detached-reattach" ]]; then
    echo "safe-sequencer-abort+safe-detached-reattach"
    return 0
  fi
  if [[ "$seq_class" == "none" && "$detached_class" == "rescue-detached" ]]; then
    echo "rescue-detached"
    return 0
  fi
  if [[ "$seq_class" == "safe-sequencer-abort" && "$detached_class" == "rescue-detached" ]]; then
    echo "safe-sequencer-abort+rescue-detached"
    return 0
  fi
  if [[ "$seq_class" == "blocked-multi-sequencer" || "$seq_class" == "blocked-unknown-sequencer" ]]; then
    echo "$seq_class"
    return 0
  fi
  echo "blocked"
}

gitlink_status_against_parent() {
  local repo="${1:-.}"
  local parent=""
  local relpath=""
  local recorded_sha=""
  local child_head=""
  parent="$(repo_superproject_path "$repo")"
  if [[ -z "$parent" ]]; then
    echo "none"
    return 0
  fi
  parent="$(cd "$parent" && pwd -P)"
  relpath="$(python3 - "$parent" "$(repo_root_path "$repo")" <<'PY'
from pathlib import Path
import os
import sys

print(os.path.relpath(Path(sys.argv[2]), Path(sys.argv[1])))
PY
)"
  recorded_sha="$(git -C "$parent" rev-parse "HEAD:$relpath" 2>/dev/null || true)"
  if [[ -z "$recorded_sha" ]]; then
    echo "missing-gitlink"
    return 0
  fi
  child_head="$(repo_head_oid "$repo")"
  if [[ "$recorded_sha" == "$child_head" ]]; then
    echo "aligned"
    return 0
  fi
  if git -C "$repo" merge-base --is-ancestor "$recorded_sha" "$child_head" >/dev/null 2>&1; then
    echo "child-ahead"
    return 0
  fi
  if git -C "$repo" merge-base --is-ancestor "$child_head" "$recorded_sha" >/dev/null 2>&1; then
    echo "parent-ahead"
    return 0
  fi
  echo "diverged"
}

_maybe_stash_checkout_changes() {
  local repo="$1"
  local prefix="$2"
  if [[ -z "$(git -C "$repo" status --porcelain)" ]]; then
    GITOPS_STASHED_REF=""
    return 0
  fi
  local msg="${prefix}:$(gitops_now_stamp)"
  git -C "$repo" stash push --include-untracked -m "$msg" >/dev/null
  GITOPS_STASHED_REF="$msg"
}

_maybe_pop_checkout_stash() {
  local repo="$1"
  if [[ -z "${GITOPS_STASHED_REF:-}" ]]; then
    return 0
  fi
  if ! git -C "$repo" stash pop >/dev/null 2>&1; then
    die "stash restore failed after detached-head recovery; resolve manually with 'git -C \"$repo\" stash list'"
  fi
  GITOPS_STASHED_REF=""
}

create_rescue_branch() {
  local repo="${1:-.}"
  local rescue="rescue/detached-$(gitops_now_stamp)-$(git -C "$repo" rev-parse --short=8 HEAD)"
  _maybe_stash_checkout_changes "$repo" "gitops-workflow:detached-recovery"
  git -C "$repo" checkout -b "$rescue" >/dev/null 2>&1 || die "failed to create rescue branch '$rescue'"
  _maybe_pop_checkout_stash "$repo"
  echo "$rescue"
}

abort_repo_sequencer_state() {
  local repo="${1:-.}"
  local states="${2:-}"
  [[ -n "$states" ]] || states="$(repo_sequencer_state "$repo")"
  case "$states" in
    merge)
      git -C "$repo" merge --abort >/dev/null 2>&1 || die "failed to abort merge in '$repo'"
      echo "abort-merge"
      ;;
    rebase)
      git -C "$repo" rebase --abort >/dev/null 2>&1 || die "failed to abort rebase in '$repo'"
      echo "abort-rebase"
      ;;
    cherry-pick)
      git -C "$repo" cherry-pick --abort >/dev/null 2>&1 || die "failed to abort cherry-pick in '$repo'"
      echo "abort-cherry-pick"
      ;;
    revert)
      git -C "$repo" revert --abort >/dev/null 2>&1 || die "failed to abort revert in '$repo'"
      echo "abort-revert"
      ;;
    bisect)
      git -C "$repo" bisect reset >/dev/null 2>&1 || die "failed to reset bisect in '$repo'"
      echo "reset-bisect"
      ;;
    "")
      echo "none"
      ;;
    *)
      die "cannot auto-recover unsupported sequencer state '$states' in '$repo'"
      ;;
  esac
}

reset_repo_recovery_state() {
  GITOPS_RECOVERY_PRIOR_STATE="clean"
  GITOPS_RECOVERY_ACTION="none"
  GITOPS_RECOVERY_OUTCOME="unchanged"
  GITOPS_RECOVERY_CONTINUED="true"
  GITOPS_RECOVERY_NEXT_ACTION=""
  GITOPS_RECOVERED_BRANCH=""
}

recover_repo_for_stateful_command() {
  local repo="${1:-.}"
  local detached_mode="${2:-recover}"
  local states=""
  local branch_before=""
  local branch_after=""
  local action_parts=()
  reset_repo_recovery_state

  branch_before="$(current_branch_name "$repo" || true)"
  states="$(repo_sequencer_state "$repo")"
  if [[ -n "$states" ]]; then
    GITOPS_RECOVERY_PRIOR_STATE="$states"
    if [[ "$states" == *,* ]]; then
      GITOPS_RECOVERY_ACTION="blocked-multi-sequencer"
      GITOPS_RECOVERY_OUTCOME="blocked"
      GITOPS_RECOVERY_CONTINUED="false"
      GITOPS_RECOVERY_NEXT_ACTION="finish or abort the in-progress git operation manually before retrying"
      return 20
    fi
    action_parts+=("$(abort_repo_sequencer_state "$repo" "$states")")
  fi

  branch_after="$(ensure_attached_branch "$repo" "$detached_mode")" || {
    local code=$?
    if [[ $code -eq 10 ]]; then
      action_parts+=("rescue-branch")
      GITOPS_RECOVERED_BRANCH="$branch_after"
      GITOPS_RECOVERY_ACTION="$(IFS=,; echo "${action_parts[*]}")"
      GITOPS_RECOVERY_OUTCOME="rescue"
      GITOPS_RECOVERY_CONTINUED="false"
      GITOPS_RECOVERY_NEXT_ACTION="review and continue from rescue branch '$branch_after'"
      return 10
    fi
    return "$code"
  }

  if [[ -z "$branch_before" ]]; then
    action_parts+=("reattach-branch")
  fi
  GITOPS_RECOVERED_BRANCH="$branch_after"

  if [[ "${#action_parts[@]}" -eq 0 ]]; then
    GITOPS_RECOVERY_ACTION="none"
    GITOPS_RECOVERY_OUTCOME="unchanged"
    return 0
  fi

  GITOPS_RECOVERY_ACTION="$(IFS=,; echo "${action_parts[*]}")"
  GITOPS_RECOVERY_OUTCOME="recovered"
  GITOPS_RECOVERY_NEXT_ACTION="continue with the requested workflow"
}

ensure_attached_branch() {
  local repo="${1:-.}"
  local mode="${2:-recover}"
  local branch=""
  if branch="$(current_branch_name "$repo")"; then
    GITOPS_DETACHED_STATUS="attached"
    echo "$branch"
    return 0
  fi

  if [[ "$mode" == "off" ]]; then
    die "detached HEAD detected and recovery is disabled"
  fi

  mapfile -t candidates < <(_detached_candidate_branches "$repo")
  local filtered=()
  local candidate=""
  for candidate in "${candidates[@]}"; do
    [[ -n "$candidate" ]] || continue
    if git -C "$repo" show-ref --verify --quiet "refs/heads/$candidate" || git -C "$repo" show-ref --verify --quiet "refs/remotes/origin/$candidate"; then
      filtered+=("$candidate")
    fi
  done

  if [[ "${#filtered[@]}" -ne 1 ]]; then
    GITOPS_DETACHED_STATUS="rescue"
    echo "$(create_rescue_branch "$repo")"
    return 10
  fi

  candidate="${filtered[0]}"
  if [[ -n "$(branch_checked_out_elsewhere "$repo" "$candidate")" ]]; then
    GITOPS_DETACHED_STATUS="rescue"
    echo "$(create_rescue_branch "$repo")"
    return 10
  fi

  _maybe_stash_checkout_changes "$repo" "gitops-workflow:detached-recovery"
  if git -C "$repo" show-ref --verify --quiet "refs/heads/$candidate"; then
    if git -C "$repo" merge-base --is-ancestor "refs/heads/$candidate" HEAD >/dev/null 2>&1; then
      git -C "$repo" checkout -B "$candidate" HEAD >/dev/null 2>&1 || die "failed to recover detached HEAD onto '$candidate'"
    else
      _maybe_pop_checkout_stash "$repo" >/dev/null 2>&1 || true
      GITOPS_DETACHED_STATUS="rescue"
      echo "$(create_rescue_branch "$repo")"
      return 10
    fi
  else
    if git -C "$repo" show-ref --verify --quiet "refs/remotes/origin/$candidate" && git -C "$repo" merge-base --is-ancestor "refs/remotes/origin/$candidate" HEAD >/dev/null 2>&1; then
      git -C "$repo" checkout -B "$candidate" HEAD >/dev/null 2>&1 || die "failed to recover detached HEAD onto '$candidate'"
      ensure_tracking_branch_if_remote_exists "$repo" "$candidate" >/dev/null 2>&1 || true
    else
      _maybe_pop_checkout_stash "$repo" >/dev/null 2>&1 || true
      GITOPS_DETACHED_STATUS="rescue"
      echo "$(create_rescue_branch "$repo")"
      return 10
    fi
  fi
  _maybe_pop_checkout_stash "$repo"
  GITOPS_DETACHED_STATUS="recovered"
  echo "$candidate"
}
