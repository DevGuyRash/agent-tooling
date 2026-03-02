#!/usr/bin/env bash
set -euo pipefail

# pr-workflow.sh - Deterministic PR hygiene workflow runner.
#
# Usage:
#   bash scripts/pr-workflow.sh <pr_number> [--repo owner/repo] [--watch-checks]
#
# Behavior:
# - Prints concise PR metadata summary by default.
# - Optionally prints full top-level comments with --full-comments.
# - Fails on unresolved inline review threads.
# - Runs CI checks (watch optional).

die() {
  echo "Error: $*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

require_cmd gh

PR_NUMBER="${1:-}"
shift || true
[[ -n "$PR_NUMBER" ]] || die "missing <pr_number>"

REPO=""
WATCH_CHECKS="false"
FULL_COMMENTS="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      REPO="${2:-}"
      shift 2
      ;;
    --watch-checks)
      WATCH_CHECKS="true"
      shift
      ;;
    --full-comments)
      FULL_COMMENTS="true"
      shift
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

CHECK_ARGS=("$PR_NUMBER")
THREAD_ARGS=("$PR_NUMBER" --fail-on-unresolved)
META_ARGS=("$PR_NUMBER" --json number,title,state,isDraft,reviewDecision,mergeable,baseRefName,headRefName,url)
COMMENT_COUNT_ARGS=("$PR_NUMBER" --json comments --jq '.comments | length')
VIEW_ARGS=("$PR_NUMBER" --comments)

if [[ -n "$REPO" ]]; then
  CHECK_ARGS+=(--repo "$REPO")
  THREAD_ARGS+=(--repo "$REPO")
  META_ARGS+=(--repo "$REPO")
  COMMENT_COUNT_ARGS+=(--repo "$REPO")
  VIEW_ARGS+=(--repo "$REPO")
fi

echo "== PR metadata =="
gh pr view "${META_ARGS[@]}" \
  --jq '{number, title, state, isDraft, mergeable, reviewDecision, baseRefName, headRefName, url}'
echo ""

echo "== Top-level comment summary =="
COMMENT_COUNT="$(gh pr view "${COMMENT_COUNT_ARGS[@]}")"
echo "comments: $COMMENT_COUNT"
if [[ "$FULL_COMMENTS" == "true" ]]; then
  echo ""
  echo "== Top-level PR comments (full) =="
  gh pr view "${VIEW_ARGS[@]}"
else
  echo "full comments: skipped (pass --full-comments to include full bodies)"
fi
echo ""

echo "== Unresolved inline threads =="
bash "$(dirname "$0")/pr-unresolved-threads.sh" "${THREAD_ARGS[@]}"
echo ""

echo "== CI checks =="
if [[ "$WATCH_CHECKS" == "true" ]]; then
  gh pr checks "${CHECK_ARGS[@]}" --watch
else
  gh pr checks "${CHECK_ARGS[@]}"
fi
