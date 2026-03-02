#!/usr/bin/env bash
set -euo pipefail

# pr-reply.sh - Reply to a GitHub PR review comment (inline) by comment ID.
#
# Usage:
#   bash scripts/pr-reply.sh <pr_number> <comment_id> "<reply text>" [--repo owner/repo]
#
# Requirements:
#   - gh authenticated
#
# Notes:
# - This replies to a *review comment* (inline diff comment), not a general issue comment.
# - If you don't know the comment id, reply in the GitHub UI instead.
# - Literal '\n' sequences in <reply text> are normalized to real newlines.

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

PR_NUMBER="${1:-}"
COMMENT_ID="${2:-}"
REPLY_TEXT="${3:-}"
shift 3 || true

[[ -n "$PR_NUMBER" ]] || die "missing <pr_number>"
[[ -n "$COMMENT_ID" ]] || die "missing <comment_id>"
[[ -n "$REPLY_TEXT" ]] || die "missing reply text"

REPO=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      require_opt_value "--repo" "${2:-}"
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

IFS=$'\t' read -r OWNER NAME <<< "$(parse_repo "$REPO")"

ENDPOINT="/repos/${OWNER}/${NAME}/pulls/${PR_NUMBER}/comments/${COMMENT_ID}/replies"

REPLY_TEXT_NORMALIZED="${REPLY_TEXT//\\n/$'\n'}"
gh api -X POST "$ENDPOINT" -f body="$REPLY_TEXT_NORMALIZED" >/dev/null

echo "✅ Replied to comment $COMMENT_ID on PR #$PR_NUMBER in $REPO"
