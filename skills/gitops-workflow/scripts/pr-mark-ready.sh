#!/usr/bin/env bash
set -euo pipefail

# pr-mark-ready.sh - Deterministically mark a draft PR as ready after strict gates.
#
# Usage:
#   bash scripts/pr-mark-ready.sh <pr_number> [--repo owner/repo] [--watch-checks]

case "${BASH_SOURCE[0]}" in
  */*) SCRIPT_DIR="$(cd "${BASH_SOURCE[0]%/*}" && pwd -P)" ;;
  *) SCRIPT_DIR="$(pwd -P)" ;;
esac
# shellcheck source=skills/gitops-workflow/scripts/lib/bootstrap.sh
source "$SCRIPT_DIR/lib/bootstrap.sh"
gitops_workflow_maybe_reexec_repo_local_copy "$SCRIPT_DIR" "pr-mark-ready.sh" "$@"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

print_help() {
  cat <<'USAGE'
Usage:
  bash scripts/pr-mark-ready.sh <pr_number> [--repo owner/repo] [--watch-checks]
USAGE
}

PR_NUMBER="${1:-}"
if [[ -z "$PR_NUMBER" || "$PR_NUMBER" == "-h" || "$PR_NUMBER" == "--help" ]]; then
  print_help
  exit 0
fi
shift || true

REPO=""
WATCH_CHECKS="false"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      require_opt_value "--repo" "${2:-}"
      REPO="${2:-}"
      shift 2
      ;;
    --watch-checks)
      WATCH_CHECKS="true"
      shift
      ;;
    -h|--help)
      print_help
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

require_cmd gh

VIEW_ARGS=("$PR_NUMBER")
CHECK_ARGS=("$PR_NUMBER")
THREAD_ARGS=("$PR_NUMBER" --fail-on-unresolved)
READY_ARGS=("$PR_NUMBER")
if [[ -n "$REPO" ]]; then
  VIEW_ARGS+=(--repo "$REPO")
  CHECK_ARGS+=(--repo "$REPO")
  THREAD_ARGS+=(--repo "$REPO")
  READY_ARGS+=(--repo "$REPO")
fi

IS_DRAFT="$(gh pr view "${VIEW_ARGS[@]}" --json isDraft --jq '.isDraft')"
if [[ "$IS_DRAFT" != "true" ]]; then
  echo "PR #$PR_NUMBER is already ready for review."
  exit 0
fi

echo "== Unresolved inline threads gate =="
bash "$(dirname "$0")/pr-unresolved-threads.sh" "${THREAD_ARGS[@]}"

echo
echo "== CI checks gate =="
if [[ "$WATCH_CHECKS" == "true" ]]; then
  gh pr checks "${CHECK_ARGS[@]}" --watch
else
  gh pr checks "${CHECK_ARGS[@]}"
fi

echo
echo "== Marking PR ready =="
gh pr ready "${READY_ARGS[@]}"
echo "✅ PR #$PR_NUMBER marked ready for review."
