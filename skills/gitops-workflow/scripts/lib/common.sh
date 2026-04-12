#!/usr/bin/env bash
set -euo pipefail

die() {
  echo "Error: $*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

require_opt_value() {
  local opt="$1"
  local val="${2:-}"
  if [[ -z "$val" || "$val" == --* ]]; then
    die "option '$opt' requires a value"
  fi
}

require_opt_value_present() {
  local opt="$1"
  local val="${2:-}"
  if [[ -z "$val" ]]; then
    die "option '$opt' requires a value"
  fi
}

require_numeric_id() {
  local label="$1"
  local val="${2:-}"
  [[ -n "$val" ]] || die "missing <$label>"
  [[ "$val" =~ ^[0-9]+$ ]] || die "invalid <$label>: must be numeric"
}

compact_text() {
  local text="${1:-}"
  printf '%s' "$text" | tr '\t\r\n' '   ' | sed 's/[[:space:]]\+/ /g; s/^ //; s/ $//'
}

decode_base64() {
  if printf '' | base64 --decode >/dev/null 2>&1; then
    base64 --decode
    return
  fi
  if printf '' | base64 -D >/dev/null 2>&1; then
    base64 -D
    return
  fi
  die "base64 decode is unsupported on this platform"
}

gh_contents_fetch_json() {
  local owner="$1"
  local name="$2"
  local ref="$3"
  local path="$4"
  local mode="$5"
  local endpoint="repos/$owner/$name/contents/$path?ref=$ref"
  local out=""
  local err_file=""
  err_file="$(mktemp)"
  trap 'rm -f "${err_file:-}"; trap - RETURN' RETURN

  if out="$(gh api "$endpoint" 2>"$err_file")"; then
    printf '%s' "$out"
    return 0
  fi
  if [[ ! -s "$err_file" ]]; then
    return 0
  fi
  if grep -qi 'HTTP 404' "$err_file"; then
    return 0
  fi
  local err_text=""
  err_text="$(tr '\n' ' ' < "$err_file" | sed 's/[[:space:]]\\+/ /g; s/^ //; s/ $//')"
  die "gh api failed while ${mode} '$path' from $owner/$name@$ref: ${err_text:-unknown error}"
}

fetch_file_json() {
  gh_contents_fetch_json "$1" "$2" "$3" "$4" "fetching"
}

fetch_dir_json() {
  gh_contents_fetch_json "$1" "$2" "$3" "$4" "listing"
}

parse_repo() {
  local repo="$1"
  local owner name
  if [[ ! "$repo" =~ ^[^/]+/[^/]+$ ]]; then
    die "invalid --repo '$repo' (expected owner/repo)"
  fi
  owner="${repo%%/*}"
  name="${repo##*/}"
  if [[ ! "$owner" =~ ^[A-Za-z0-9][A-Za-z0-9-]{0,38}$ ]]; then
    die "invalid --repo owner '$owner' (expected GitHub owner slug)"
  fi
  if [[ ! "$name" =~ ^[A-Za-z0-9._-]+$ ]]; then
    die "invalid --repo name '$name' (allowed: letters, digits, ., _, -)"
  fi
  if [[ "$name" == "." || "$name" == ".." || "$name" == *".."* ]]; then
    die "invalid --repo name '$name' (path-like segments are not allowed)"
  fi
  printf '%s\t%s\n' "$owner" "$name"
}

resolve_checkout_repo_slug() {
  local repo=""
  local remote_url=""
  local repo_path=""

  if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    return 0
  fi

  if command -v gh >/dev/null 2>&1; then
    repo="$(gh repo view --json nameWithOwner --jq '.nameWithOwner' 2>/dev/null || true)"
    if [[ -n "$repo" ]]; then
      printf '%s\n' "$repo"
      return 0
    fi
  fi

  remote_url="$(git remote get-url origin 2>/dev/null || true)"
  if [[ "$remote_url" =~ ^https://([^/@]+(:[^/@]*)?@)?github\.com/(.+)$ ]]; then
    repo_path="${BASH_REMATCH[3]%.git}"
    if [[ "$repo_path" =~ ^[^/]+/[^/]+$ ]]; then
      printf '%s\n' "$repo_path"
      return 0
    fi
  fi

  case "$remote_url" in
    git@github.com:*)
      repo_path="${remote_url#git@github.com:}"
      printf '%s\n' "${repo_path%.git}"
      return 0
      ;;
    ssh://git@github.com/*/*)
      repo_path="${remote_url#ssh://git@github.com/}"
      printf '%s\n' "${repo_path%.git}"
      return 0
      ;;
  esac
}
