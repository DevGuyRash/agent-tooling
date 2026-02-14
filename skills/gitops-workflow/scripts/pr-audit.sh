#!/usr/bin/env bash
set -euo pipefail

# pr-audit.sh - Quick PR hygiene audit: metadata + checks + unresolved threads.
#
# Usage:
#   bash scripts/pr-audit.sh <pr_number>
#
# Requirements:
#   - gh authenticated

die() {
  echo "Error: $*" >&2
  exit 1
}

command -v gh >/dev/null 2>&1 || die "missing required command: gh"

PR="${1:-}"
[[ -n "$PR" ]] || die "missing <pr_number>"

echo "== PR metadata =="
gh pr view "$PR" --json number,title,state,isDraft,url,baseRefName,headRefName,mergeable,reviewDecision \
  --jq '{number, title, state, isDraft, mergeable, reviewDecision, baseRefName, headRefName, url}'
echo ""

echo "== CI checks =="
gh pr checks "$PR" || true
echo ""

echo "== Unresolved inline threads =="
bash "$(dirname "$0")/pr-unresolved-threads.sh" "$PR" || true
