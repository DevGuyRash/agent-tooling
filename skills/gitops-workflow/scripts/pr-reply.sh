#!/usr/bin/env bash
set -euo pipefail

# pr-reply.sh - Reply to a GitHub PR review comment (inline) by comment ID.
#
# Usage:
#   bash scripts/pr-reply.sh <pr_number> <comment_id> --body "<text>" [--repo owner/repo]
#   bash scripts/pr-reply.sh <pr_number> <comment_id> --body=<text> [--repo owner/repo]
#   bash scripts/pr-reply.sh <pr_number> <comment_id> --body-file <path> [--repo owner/repo]
#
# Requirements:
#   - gh authenticated
#
# Notes:
# - This replies to a *review comment* (inline diff comment), not a general issue comment.
# - If you don't know the comment id, reply in the GitHub UI instead.
# - Literal '\n' sequences in --body text are normalized to real newlines.

case "${BASH_SOURCE[0]}" in
  */*) SCRIPT_DIR="$(cd "${BASH_SOURCE[0]%/*}" && pwd -P)" ;;
  *) SCRIPT_DIR="$(pwd -P)" ;;
esac
# shellcheck source=skills/gitops-workflow/scripts/lib/bootstrap.sh
source "$SCRIPT_DIR/lib/bootstrap.sh"
gitops_workflow_maybe_reexec_repo_local_copy "$SCRIPT_DIR" "pr-reply.sh" "$@"
# shellcheck source=skills/gitops-workflow/scripts/lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

print_help() {
  cat <<'USAGE'
Usage:
  bash scripts/pr-reply.sh <pr_number> <comment_id> --body "<text>" [--repo owner/repo]
  bash scripts/pr-reply.sh <pr_number> <comment_id> --body=<text> [--repo owner/repo]
  bash scripts/pr-reply.sh <pr_number> <comment_id> --body-file <path> [--repo owner/repo]

Arguments:
  <pr_number>          Pull request number.
  <comment_id>         Pull request review comment ID.

Options:
  --body <text>        Reply text (strict; next token must not be another option).
  --body=<text>        Reply text, including literals that start with '--'.
  --body-file <path>   Path to reply body file.
  --repo <owner/repo>  Optional repository override.
  -h, --help           Show help.
USAGE
}

PR_NUMBER="${1:-}"
if [[ "$PR_NUMBER" == "-h" || "$PR_NUMBER" == "--help" ]]; then
  print_help
  exit 0
fi
COMMENT_ID="${2:-}"
shift 2 || true

require_numeric_id "pr_number" "$PR_NUMBER"
require_numeric_id "comment_id" "$COMMENT_ID"

REPO=""
BODY=""
BODY_FILE=""
TMP_BODY_FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --body=*)
      BODY="${1#--body=}"
      require_opt_value_present "--body" "$BODY"
      shift
      ;;
    --body)
      require_opt_value "--body" "${2:-}"
      BODY="${2:-}"
      shift 2
      ;;
    --body-file)
      require_opt_value "--body-file" "${2:-}"
      BODY_FILE="${2:-}"
      shift 2
      ;;
    --repo)
      require_opt_value "--repo" "${2:-}"
      REPO="${2:-}"
      shift 2
      ;;
    --repo=*)
      REPO="${1#--repo=}"
      require_opt_value "--repo" "$REPO"
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

if [[ -n "$BODY" && -n "$BODY_FILE" ]]; then
  die "use either --body or --body-file, not both"
fi
if [[ -z "$BODY" && -z "$BODY_FILE" ]]; then
  die "missing reply text; pass --body or --body-file"
fi

cleanup() {
  if [[ -n "$TMP_BODY_FILE" && -f "$TMP_BODY_FILE" ]]; then
    rm -f "$TMP_BODY_FILE"
  fi
}
trap cleanup EXIT

if [[ -n "$BODY" ]]; then
  TMP_BODY_FILE="$(mktemp)"
  BODY_NORMALIZED="${BODY//\\n/$'\n'}"
  printf '%s' "$BODY_NORMALIZED" > "$TMP_BODY_FILE"
  BODY_FILE="$TMP_BODY_FILE"
fi
[[ -f "$BODY_FILE" ]] || die "body file not found: $BODY_FILE"

require_cmd gh

if [[ -z "$REPO" ]]; then
  REPO="$(gh repo view --json nameWithOwner --jq '.nameWithOwner' 2>/dev/null || true)"
fi
[[ -n "$REPO" ]] || die "could not infer repo; pass --repo owner/repo"

IFS=$'\t' read -r OWNER NAME <<< "$(parse_repo "$REPO")"

ENDPOINT="/repos/${OWNER}/${NAME}/pulls/${PR_NUMBER}/comments/${COMMENT_ID}/replies"

gh api -X POST "$ENDPOINT" -F "body=@$BODY_FILE" >/dev/null

echo "✅ Replied to comment $COMMENT_ID on PR #$PR_NUMBER in $REPO"
