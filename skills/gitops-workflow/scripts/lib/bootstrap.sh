#!/usr/bin/env bash

GITOPS_WORKFLOW_BOOTSTRAP_ENV="GITOPS_WORKFLOW_BOOTSTRAP_ACTIVE"

_gitops_workflow_extract_repo_arg() {
  local index=1
  while [[ $index -le $# ]]; do
    local arg="${!index}"
    case "$arg" in
      --repo)
        local next_index=$((index + 1))
        if [[ $next_index -le $# ]]; then
          printf '%s\n' "${!next_index}"
          return 0
        fi
        return 0
        ;;
      --repo=*)
        printf '%s\n' "${arg#--repo=}"
        return 0
        ;;
    esac
    index=$((index + 1))
  done
  return 1
}

_gitops_workflow_repo_root_from_path() {
  local path_hint="${1:-}"
  [[ -n "$path_hint" ]] || return 1
  git -C "$path_hint" rev-parse --show-toplevel 2>/dev/null || return 1
}

_gitops_workflow_repo_root_from_cwd() {
  git rev-parse --show-toplevel 2>/dev/null || return 1
}

gitops_workflow_maybe_reexec_repo_local_copy() {
  local script_dir="$1"
  local script_name="$2"
  shift 2

  if [[ "${!GITOPS_WORKFLOW_BOOTSTRAP_ENV:-}" == "1" ]]; then
    return 0
  fi

  local current_skill_root
  current_skill_root="$(cd "$script_dir/.." && pwd -P)"
  local skill_name
  skill_name="${current_skill_root##*/}"

  local repo_hint=""
  if repo_hint="$(_gitops_workflow_extract_repo_arg "$@" 2>/dev/null)"; then
    :
  else
    repo_hint=""
  fi

  local repo_root=""
  local seen_repo_root=""
  local candidate_skill_root=""
  local candidate_script=""
  local resolver
  for resolver in "hint" "cwd"; do
    if [[ "$resolver" == "hint" ]]; then
      repo_root="$(_gitops_workflow_repo_root_from_path "$repo_hint" 2>/dev/null || true)"
    else
      repo_root="$(_gitops_workflow_repo_root_from_cwd 2>/dev/null || true)"
    fi

    [[ -n "$repo_root" ]] || continue
    if [[ "$repo_root" == "$seen_repo_root" ]]; then
      continue
    fi
    seen_repo_root="$repo_root"

    candidate_skill_root="$repo_root/skills/$skill_name"
    candidate_script="$candidate_skill_root/scripts/$script_name"
    if [[ ! -f "$candidate_skill_root/SKILL.md" || ! -f "$candidate_script" ]]; then
      continue
    fi

    candidate_skill_root="$(cd "$candidate_skill_root" && pwd -P)"
    if [[ "$candidate_skill_root" == "$current_skill_root" ]]; then
      continue
    fi

    export "$GITOPS_WORKFLOW_BOOTSTRAP_ENV=1"
    exec bash "$candidate_script" "$@"
  done
}
