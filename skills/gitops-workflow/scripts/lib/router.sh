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

reset_gitops_remote_read_state() {
  GITOPS_REMOTE_READ_OUTPUT=""
  GITOPS_REMOTE_READ_EXIT_CODE=0
  GITOPS_REMOTE_READ_TRANSPORT_ATTEMPTS=""
  GITOPS_REMOTE_READ_TRANSPORT_USED=""
  GITOPS_REMOTE_READ_FALLBACK_REASON=""
  GITOPS_REMOTE_READ_REMOTE_URL_KIND=""
  GITOPS_REMOTE_READ_REMOTE_URL=""
}

gitops_remote_url_kind() {
  local remote_url="$1"
  case "$remote_url" in
    git@*:*|ssh://*)
      echo "ssh"
      ;;
    https://*)
      echo "https"
      ;;
    *)
      echo "other"
      ;;
  esac
}

gitops_https_fallback_url() {
  local remote_url="$1"
  local host=""
  local path=""
  if [[ "$remote_url" =~ ^[^@]+@([^:]+):(.+)$ ]]; then
    host="${BASH_REMATCH[1]}"
    path="${BASH_REMATCH[2]}"
  elif [[ "$remote_url" =~ ^ssh://([^@/]+@)?([^/:]+)/(.*)$ ]]; then
    host="${BASH_REMATCH[2]}"
    path="${BASH_REMATCH[3]}"
  else
    return 1
  fi
  [[ -n "$host" && -n "$path" ]] || return 1
  printf 'https://%s/%s
' "$host" "$path"
}

gitops_classify_ssh_read_failure() {
  local output="$1"
  local exit_code="${2:-1}"
  local lower=""
  if [[ "$exit_code" -eq 124 ]]; then
    echo "fallback:ssh-connection-timeout"
    return 0
  fi
  lower="$(printf '%s' "$output" | tr '[:upper:]' '[:lower:]')"
  case "$lower" in
    *"remote host identification has changed"*|*"host key verification failed"*|*"possible dns spoofing detected"*)
      echo "blocked:ssh-host-verification-failed"
      ;;
    *"permission denied (publickey)"*)
      echo "fallback:ssh-publickey-auth-failed"
      ;;
    *"sign_and_send_pubkey:"*|*"agent refused operation"*|*"could not open a connection to your authentication agent"*)
      echo "fallback:ssh-agent-auth-failed"
      ;;
    *"could not resolve hostname"*)
      echo "fallback:ssh-hostname-resolution-failed"
      ;;
    *"connection timed out"*|*"operation timed out"*|*"timed out"*)
      echo "fallback:ssh-connection-timeout"
      ;;
    *"connection refused"*)
      echo "fallback:ssh-connection-refused"
      ;;
    *"connection reset by peer"*)
      echo "fallback:ssh-connection-reset"
      ;;
    *"no route to host"*|*"network is unreachable"*)
      echo "fallback:ssh-network-unreachable"
      ;;
    *"kex_exchange_identification:"*)
      echo "fallback:ssh-transport-failed"
      ;;
    *)
      echo "none"
      ;;
  esac
}

gitops_run_git_read_capture() {
  local repo="$1"
  local timeout_seconds="$2"
  local override_url="$3"
  shift 3
  local -a cmd=(git -C "$repo")
  local -a read_args=()
  local output_file=""
  local ssh_cmd=""
  local exit_code=0
  output_file="$(mktemp)"
  ssh_cmd="$(gitops_noninteractive_ssh_command)"
  if [[ -n "$override_url" && "$#" -ge 2 && "$1" == "fetch" && "$2" == "origin" ]]; then
    shift 2
    read_args=(fetch "$@" "$override_url" "+refs/heads/*:refs/remotes/origin/*")
  else
    read_args=("$@")
  fi
  cmd+=("${read_args[@]}")
  if command -v timeout >/dev/null 2>&1 && [[ "$timeout_seconds" =~ ^[1-9][0-9]*$ ]]; then
    if env GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/bin/true SSH_ASKPASS=/bin/true GIT_SSH_COMMAND="$ssh_cmd" timeout --foreground "$timeout_seconds" "${cmd[@]}" >"$output_file" 2>&1; then
      exit_code=0
    else
      exit_code=$?
    fi
  else
    if env GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/bin/true SSH_ASKPASS=/bin/true GIT_SSH_COMMAND="$ssh_cmd" "${cmd[@]}" >"$output_file" 2>&1; then
      exit_code=0
    else
      exit_code=$?
    fi
  fi
  GITOPS_REMOTE_READ_OUTPUT="$(compact_text "$(cat "$output_file" 2>/dev/null)")"
  rm -f "$output_file"
  if [[ "$exit_code" -eq 124 && -z "$GITOPS_REMOTE_READ_OUTPUT" ]]; then
    GITOPS_REMOTE_READ_OUTPUT="remote read command timed out after ${timeout_seconds}s"
  fi
  GITOPS_REMOTE_READ_EXIT_CODE="$exit_code"
  return "$exit_code"
}

gitops_run_origin_read_command() {
  local repo="$1"
  local timeout_seconds="${2:-20}"
  shift 2
  local origin_url=""
  local remote_kind=""
  local fallback_url=""
  local classification=""
  local ssh_output=""
  local https_output=""
  reset_gitops_remote_read_state
  origin_url="$(git -C "$repo" remote get-url origin 2>/dev/null || true)"
  GITOPS_REMOTE_READ_REMOTE_URL="$origin_url"
  remote_kind="$(gitops_remote_url_kind "$origin_url")"
  GITOPS_REMOTE_READ_REMOTE_URL_KIND="$remote_kind"
  case "$remote_kind" in
    ssh)
      GITOPS_REMOTE_READ_TRANSPORT_ATTEMPTS="ssh"
      if gitops_run_git_read_capture "$repo" "$timeout_seconds" "" "$@"; then
        GITOPS_REMOTE_READ_TRANSPORT_USED="ssh"
        return 0
      fi
      ssh_output="$GITOPS_REMOTE_READ_OUTPUT"
      classification="$(gitops_classify_ssh_read_failure "$ssh_output" "$GITOPS_REMOTE_READ_EXIT_CODE")"
      case "$classification" in
        blocked:*)
          GITOPS_REMOTE_READ_FALLBACK_REASON="${classification#blocked:}"
          return "$GITOPS_REMOTE_READ_EXIT_CODE"
          ;;
        fallback:*)
          fallback_url="$(gitops_https_fallback_url "$origin_url" || true)"
          if [[ -z "$fallback_url" ]]; then
            GITOPS_REMOTE_READ_FALLBACK_REASON="ssh-fallback-unsupported-remote"
            return "$GITOPS_REMOTE_READ_EXIT_CODE"
          fi
          GITOPS_REMOTE_READ_FALLBACK_REASON="${classification#fallback:}"
          GITOPS_REMOTE_READ_TRANSPORT_ATTEMPTS="ssh,https"
          if gitops_run_git_read_capture "$repo" "$timeout_seconds" "$fallback_url" "$@"; then
            GITOPS_REMOTE_READ_TRANSPORT_USED="https"
            return 0
          fi
          https_output="$GITOPS_REMOTE_READ_OUTPUT"
          GITOPS_REMOTE_READ_OUTPUT="$(compact_text "ssh attempt failed: ${ssh_output:-unknown failure}; https fallback failed: ${https_output:-unknown failure}")"
          return "$GITOPS_REMOTE_READ_EXIT_CODE"
          ;;
        *)
          return "$GITOPS_REMOTE_READ_EXIT_CODE"
          ;;
      esac
      ;;
    https)
      GITOPS_REMOTE_READ_TRANSPORT_ATTEMPTS="https"
      if gitops_run_git_read_capture "$repo" "$timeout_seconds" "" "$@"; then
        GITOPS_REMOTE_READ_TRANSPORT_USED="https"
        return 0
      fi
      return "$GITOPS_REMOTE_READ_EXIT_CODE"
      ;;
    *)
      GITOPS_REMOTE_READ_TRANSPORT_ATTEMPTS="other"
      if gitops_run_git_read_capture "$repo" "$timeout_seconds" "" "$@"; then
        GITOPS_REMOTE_READ_TRANSPORT_USED="other"
        return 0
      fi
      return "$GITOPS_REMOTE_READ_EXIT_CODE"
      ;;
  esac
}

reset_gitops_fetch_state() {
  GITOPS_FETCH_STATUS="not-run"
  GITOPS_FETCH_NOTE=""
  GITOPS_FETCH_TRANSPORT_ATTEMPTS=""
  GITOPS_FETCH_TRANSPORT_USED=""
  GITOPS_FETCH_FALLBACK_REASON=""
  GITOPS_FETCH_REMOTE_URL_KIND=""
}

gitops_fetch_prune_repo() {
  local repo="${1:-.}"
  local timeout_seconds="${GITOPS_FETCH_TIMEOUT_SECONDS:-20}"
  reset_gitops_fetch_state
  if ! repo_has_origin "$repo"; then
    GITOPS_FETCH_STATUS="skipped-no-origin"
    GITOPS_FETCH_NOTE="no origin remote configured"
    return 0
  fi
  if gitops_run_origin_read_command "$repo" "$timeout_seconds" fetch origin --prune; then
    GITOPS_FETCH_STATUS="fetched"
  else
    GITOPS_FETCH_STATUS="warning"
    GITOPS_FETCH_NOTE="$GITOPS_REMOTE_READ_OUTPUT"
    GITOPS_FETCH_TRANSPORT_ATTEMPTS="$GITOPS_REMOTE_READ_TRANSPORT_ATTEMPTS"
    GITOPS_FETCH_TRANSPORT_USED="$GITOPS_REMOTE_READ_TRANSPORT_USED"
    GITOPS_FETCH_FALLBACK_REASON="$GITOPS_REMOTE_READ_FALLBACK_REASON"
    GITOPS_FETCH_REMOTE_URL_KIND="$GITOPS_REMOTE_READ_REMOTE_URL_KIND"
    return 1
  fi
  GITOPS_FETCH_TRANSPORT_ATTEMPTS="$GITOPS_REMOTE_READ_TRANSPORT_ATTEMPTS"
  GITOPS_FETCH_TRANSPORT_USED="$GITOPS_REMOTE_READ_TRANSPORT_USED"
  GITOPS_FETCH_FALLBACK_REASON="$GITOPS_REMOTE_READ_FALLBACK_REASON"
  GITOPS_FETCH_REMOTE_URL_KIND="$GITOPS_REMOTE_READ_REMOTE_URL_KIND"
  return 0
}

gitops_prepare_repo_for_stateful_command() {
  local repo="${1:-.}"
  local detached_mode="${2:-recover}"
  gitops_fetch_prune_repo "$repo" || true
  recover_repo_for_stateful_command "$repo" "$detached_mode"
}
