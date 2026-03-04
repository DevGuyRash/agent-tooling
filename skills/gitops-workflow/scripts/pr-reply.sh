#!/usr/bin/env bash
set -euo pipefail

# pr-reply.sh - Reply to a GitHub PR review comment (inline) by comment ID.
#
# Usage:
#   bash scripts/pr-reply.sh <pr_number> <comment_id> "<reply text>" [--repo owner/repo]
#   bash scripts/pr-reply.sh <pr_number> <comment_id> --body "<text>" [--repo owner/repo]
#   bash scripts/pr-reply.sh <pr_number> <comment_id> --body-file <path> [--repo owner/repo]
#
# Requirements:
#   - gh authenticated
#
# Notes:
# - This replies to a *review comment* (inline diff comment), not a general issue comment.
# - If you don't know the comment id, reply in the GitHub UI instead.
# - Literal '\n' sequences in text-mode inputs are normalized to real newlines.

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

is_control_token() {
  case "${1:-}" in
    -h|--help|--body|--body-file|--repo|--repo=*)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

print_help() {
  cat <<'USAGE'
Usage:
  bash scripts/pr-reply.sh <pr_number> <comment_id> "<reply text>" [--repo owner/repo]
  bash scripts/pr-reply.sh <pr_number> <comment_id> --body "<text>" [--repo owner/repo]
  bash scripts/pr-reply.sh <pr_number> <comment_id> --body-file <path> [--repo owner/repo]

Arguments:
  <pr_number>          Pull request number.
  <comment_id>         Pull request review comment ID.
  <reply text>         Legacy positional reply text (kept for compatibility).

Options:
  --body <text>        Reply text (preferred for explicitness).
  --body-file <path>   Path to reply body file (safest for complex markdown text).
  --repo <owner/repo>  Optional repository override.
  -h, --help           Show help.

Notes:
  - Text-mode inputs normalize literal '\n' into real newlines.
  - Use --body-file when text contains shell metacharacters.
  - Legacy positional input takes precedence for first-token option-like text.
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
COMMENT_ID="${2:-}"
if [[ "$PR_NUMBER" == "-h" || "$PR_NUMBER" == "--help" ]]; then
  print_help
  exit 0
fi
if [[ "$COMMENT_ID" == "-h" || "$COMMENT_ID" == "--help" ]]; then
  print_help
  exit 0
fi
shift 2 || true

[[ -n "$PR_NUMBER" ]] || die "missing <pr_number>"
[[ "$PR_NUMBER" =~ ^[0-9]+$ ]] || die "invalid <pr_number>: must be numeric"
[[ -n "$COMMENT_ID" ]] || die "missing <comment_id>"
[[ "$COMMENT_ID" =~ ^[0-9]+$ ]] || die "invalid <comment_id>: must be numeric"

REPO=""
BODY=""
BODY_FILE=""
POSITIONAL_BODY=""
BODY_VALUE_SEEN=0
BODY_FILE_VALUE_SEEN=0

if [[ $# -gt 0 ]]; then
  case "${1:-}" in
    -h|--help)
      POSITIONAL_BODY="${1:-}"
      shift
      ;;
    --body=)
      die "option '--body' requires a value"
      ;;
    --body-file=)
      die "option '--body-file' requires a value"
      ;;
    --body|--body-file)
      if [[ -n "${2:-}" ]] && ! is_control_token "${2:-}"; then
        if [[ "${1:-}" == "--body" ]]; then
          BODY="${2:-}"
          BODY_VALUE_SEEN=1
        else
          BODY_FILE="${2:-}"
          BODY_FILE_VALUE_SEEN=1
        fi
        shift 2
      else
        POSITIONAL_BODY="${1:-}"
        shift
      fi
      ;;
    --repo=*)
      REPO="${1#--repo=}"
      require_opt_value "--repo" "$REPO"
      shift
      ;;
    --repo)
      if [[ -n "${2:-}" && "${2:-}" != --* ]]; then
        REPO="${2:-}"
        shift 2
      else
        POSITIONAL_BODY="${1:-}"
        shift
      fi
      ;;
    *)
      POSITIONAL_BODY="${1:-}"
      shift
      ;;
  esac
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --body=*)
      if [[ "$BODY_VALUE_SEEN" -eq 1 ]]; then
        die "option '--body' can only be provided once"
      fi
      BODY="${1#--body=}"
      require_opt_value_present "--body" "$BODY"
      BODY_VALUE_SEEN=1
      shift
      ;;
    --body)
      if [[ "$BODY_VALUE_SEEN" -eq 1 ]]; then
        die "option '--body' can only be provided once"
      fi
      if [[ -z "${2:-}" ]] || is_control_token "${2:-}"; then
        die "option '--body' requires a value"
      fi
      BODY="${2:-}"
      BODY_VALUE_SEEN=1
      shift 2
      ;;
    --body-file=*)
      if [[ "$BODY_FILE_VALUE_SEEN" -eq 1 ]]; then
        die "option '--body-file' can only be provided once"
      fi
      BODY_FILE="${1#--body-file=}"
      require_opt_value "--body-file" "$BODY_FILE"
      BODY_FILE_VALUE_SEEN=1
      shift
      ;;
    --body-file)
      if [[ "$BODY_FILE_VALUE_SEEN" -eq 1 ]]; then
        die "option '--body-file' can only be provided once"
      fi
      if [[ -z "${2:-}" ]] || is_control_token "${2:-}"; then
        die "option '--body-file' requires a value"
      fi
      BODY_FILE="${2:-}"
      BODY_FILE_VALUE_SEEN=1
      shift 2
      ;;
    --repo=*)
      REPO="${1#--repo=}"
      require_opt_value "--repo" "$REPO"
      shift
      ;;
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

BODY_SOURCE_COUNT=0
[[ -n "$POSITIONAL_BODY" ]] && BODY_SOURCE_COUNT=$((BODY_SOURCE_COUNT + 1))
[[ -n "$BODY" ]] && BODY_SOURCE_COUNT=$((BODY_SOURCE_COUNT + 1))
[[ -n "$BODY_FILE" ]] && BODY_SOURCE_COUNT=$((BODY_SOURCE_COUNT + 1))
if [[ "$BODY_SOURCE_COUNT" -gt 1 ]]; then
  die "provide exactly one body source: positional <reply text>, --body, or --body-file"
fi
if [[ "$BODY_SOURCE_COUNT" -eq 0 ]]; then
  die "missing reply text; provide positional <reply text>, --body, or --body-file"
fi

REPLY_TEXT=""
if [[ -n "$BODY_FILE" ]]; then
  [[ -f "$BODY_FILE" ]] || die "body file not found: $BODY_FILE"
elif [[ -n "$BODY" ]]; then
  REPLY_TEXT="${BODY//\\n/$'\n'}"
else
  REPLY_TEXT="${POSITIONAL_BODY//\\n/$'\n'}"
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
