#!/usr/bin/env bash
set -euo pipefail

# labels-export.sh - Export deterministic labels JSON fragment for policy.
#
# Usage:
#   bash scripts/labels-export.sh [--repo owner/repo]


die() {
  echo "Error: $*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

require_cmd gh
require_cmd jq

REPO=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      REPO="${2:-}"
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

OWNER="${REPO%%/*}"
NAME="${REPO##*/}"

gh api "repos/$OWNER/$NAME/labels?per_page=100" \
  --jq '[ .[] | {name, color: (.color|ascii_downcase), description: (.description // "")} ] | sort_by(.name)'
