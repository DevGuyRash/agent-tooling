#!/usr/bin/env bash
set -euo pipefail

# required-checks-discover.sh - Discover recent check context names for policy seeding.
#
# Usage:
#   bash scripts/required-checks-discover.sh [--repo owner/repo] [--branch main]


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

require_cmd gh
require_cmd jq

REPO=""
BRANCH=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      require_opt_value "--repo" "${2:-}"
      REPO="${2:-}"
      shift 2
      ;;
    --branch)
      require_opt_value "--branch" "${2:-}"
      BRANCH="${2:-}"
      shift 2
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

if [[ -z "$REPO" ]]; then
  REPO="$(gh repo view --json nameWithOwner --jq '.nameWithOwner' 2>/dev/null || true)"
fi
[[ -n "$REPO" ]] || die "could not infer repo; pass --repo owner/repo"

IFS=$'\t' read -r OWNER NAME <<< "$(parse_repo "$REPO")"

if [[ -z "$BRANCH" ]]; then
  BRANCH="$(gh api "repos/$OWNER/$NAME" --jq '.default_branch')"
fi
[[ -n "$BRANCH" ]] || die "could not determine branch"

SHA="$(gh api "repos/$OWNER/$NAME/commits/$BRANCH" --jq '.sha')"

# Combine commit check-runs and branch protection contexts if available.
{
  gh api "repos/$OWNER/$NAME/commits/$SHA/check-runs?per_page=100" --jq '.check_runs[]?.name' || true
  gh api "repos/$OWNER/$NAME/branches/$BRANCH/protection/required_status_checks" --jq '.contexts[]?' || true
} | sed '/^$/d' | sort -u | jq -R . | jq -s '{requiredChecks: .}'
