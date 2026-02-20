#!/usr/bin/env bash
set -euo pipefail

# pr-request-review.sh - Deterministically request AI reviews on a PR.
#
# Usage:
#   bash scripts/pr-request-review.sh <pr_number> [--repo owner/repo] [--note "<extra line>"]
#
# Behavior:
# - Posts a top-level PR comment via pr-comment.sh using --body-file.
# - Reviewer trigger ordering is fixed: @codex review, then @gemini-code-assist review.

die() {
  echo "Error: $*" >&2
  exit 1
}

require_opt_value() {
  local opt="$1"
  local val="${2:-}"
  if [[ -z "$val" || "$val" == --* ]]; then
    die "option '$opt' requires a value"
  fi
}

print_help() {
  cat <<'USAGE'
Usage:
  bash scripts/pr-request-review.sh <pr_number> [--repo owner/repo] [--note "<extra line>"]

Arguments:
  <pr_number>          Pull request number.

Options:
  --repo <owner/repo>  Optional repository override.
  --note <text>        Optional trailing note line.
  -h, --help           Show help.
USAGE
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PR_NUMBER="${1:-}"
if [[ "$PR_NUMBER" == "-h" || "$PR_NUMBER" == "--help" || -z "$PR_NUMBER" ]]; then
  print_help
  exit 0
fi
shift || true

REPO=""
NOTE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      require_opt_value "--repo" "${2:-}"
      REPO="${2:-}"
      shift 2
      ;;
    --note)
      require_opt_value "--note" "${2:-}"
      NOTE="${2:-}"
      shift 2
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

BODY_FILE="$(mktemp -t pr-review-request.XXXXXX.md)"
trap 'rm -f "$BODY_FILE"' EXIT

{
  echo "@codex review"
  echo "@gemini-code-assist review"
  if [[ -n "$NOTE" ]]; then
    echo ""
    echo "$NOTE"
  fi
} > "$BODY_FILE"

ARGS=("$PR_NUMBER" --body-file "$BODY_FILE")
if [[ -n "$REPO" ]]; then
  ARGS+=(--repo "$REPO")
fi

bash "$SCRIPT_DIR/pr-comment.sh" "${ARGS[@]}"
