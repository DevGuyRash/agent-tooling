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
