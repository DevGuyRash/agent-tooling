#!/usr/bin/env bash
set -euo pipefail

# pr-reply.sh - Reply to a GitHub PR review comment (inline) by comment ID.
#
# Usage:
#   bash scripts/pr-reply.sh <pr_number> <comment_id> --body "<text>" [--repo owner/repo]
#   bash scripts/pr-reply.sh <pr_number> <comment_id> --body-file <path> [--repo owner/repo]
#
# Requirements:
#   - gh authenticated
#
# Notes:
# - This replies to a *review comment* (inline diff comment), not a general issue comment.
# - If you don't know the comment id, reply in the GitHub UI instead.
# - Literal '\n' sequences in --body text are normalized to real newlines.

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

require_opt_value_present() {
  local opt="$1"
  local val="${2:-}"
  if [[ -z "$val" ]]; then
    die "option '$opt' requires a value"
  fi
}

print_help() {
  cat <<'USAGE'
Usage:
  bash scripts/pr-reply.sh <pr_number> <comment_id> --body "<text>" [--repo owner/repo]
  bash scripts/pr-reply.sh <pr_number> <comment_id> --body-file <path> [--repo owner/repo]

Arguments:
  <pr_number>          Pull request number.
  <comment_id>         Pull request review comment ID.

Options:
  --body <text>        Reply text.
  --body-file <path>   Path to reply body file.
  --repo <owner/repo>  Optional repository override.
  -h, --help           Show help.
USAGE
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

PR_NUMBER="${1:-}"
if [[ "$PR_NUMBER" == "-h" || "$PR_NUMBER" == "--help" ]]; then
  print_help
  exit 0
fi
COMMENT_ID="${2:-}"
shift 2 || true

[[ -n "$PR_NUMBER" ]] || die "missing <pr_number>"
[[ "$PR_NUMBER" =~ ^[0-9]+$ ]] || die "invalid <pr_number>: must be numeric"
[[ -n "$COMMENT_ID" ]] || die "missing <comment_id>"
[[ "$COMMENT_ID" =~ ^[0-9]+$ ]] || die "invalid <comment_id>: must be numeric"

REPO=""
BODY=""
BODY_FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --body)
      require_opt_value_present "--body" "${2:-}"
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

REPLY_TEXT=""
if [[ -n "$BODY_FILE" ]]; then
  [[ -f "$BODY_FILE" ]] || die "body file not found: $BODY_FILE"
else
  REPLY_TEXT="${BODY//\\n/$'\n'}"
fi

require_cmd gh

if [[ -z "$REPO" ]]; then
  REPO="$(gh repo view --json nameWithOwner --jq '.nameWithOwner' 2>/dev/null || true)"
fi
[[ -n "$REPO" ]] || die "could not infer repo; pass --repo owner/repo"

IFS=$'\t' read -r OWNER NAME <<< "$(parse_repo "$REPO")"

ENDPOINT="/repos/${OWNER}/${NAME}/pulls/${PR_NUMBER}/comments/${COMMENT_ID}/replies"

if [[ -n "$BODY_FILE" ]]; then
  gh api -X POST "$ENDPOINT" -F "body=@$BODY_FILE" >/dev/null
else
  gh api -X POST "$ENDPOINT" --raw-field "body=$REPLY_TEXT" >/dev/null
fi

echo "✅ Replied to comment $COMMENT_ID on PR #$PR_NUMBER in $REPO"
