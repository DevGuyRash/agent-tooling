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
