#!/usr/bin/env bash
set -euo pipefail

# pr-workflow.sh - Deterministic PR hygiene workflow runner.
#
# Usage:
#   bash scripts/pr-workflow.sh <pr_number> [--repo owner/repo] [--watch-checks]
#
# Behavior:
# - Reads top-level comments.
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
    *)
      die "unknown argument: $1"
      ;;
  esac
done

VIEW_ARGS=("$PR_NUMBER" --comments)
CHECK_ARGS=("$PR_NUMBER")
THREAD_ARGS=("$PR_NUMBER" --fail-on-unresolved)

if [[ -n "$REPO" ]]; then
  VIEW_ARGS+=(--repo "$REPO")
  CHECK_ARGS+=(--repo "$REPO")
  THREAD_ARGS+=(--repo "$REPO")
fi

echo "== Top-level PR comments =="
gh pr view "${VIEW_ARGS[@]}"
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
