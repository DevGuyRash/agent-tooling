#!/usr/bin/env bash
set -euo pipefail

# pr-unresolved-threads.sh - List unresolved GitHub PR review threads (inline comments).
#
# Usage:
#   bash scripts/pr-unresolved-threads.sh <pr_number> [--repo owner/repo] [--state unresolved|resolved|all] [--include-resolved] [--fail-on-unresolved]
#
# Requirements:
#   - gh (GitHub CLI) authenticated
#   - jq (for response shaping)
#
# Output:
#   Prints matching threads in a readable format.
#   Default exit is 0 even if threads exist; use --fail-on-unresolved to return 3.

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
require_cmd jq

PR_NUMBER="${1:-}"
shift || true
[[ -n "$PR_NUMBER" ]] || die "missing <pr_number>"

REPO=""
FAIL_ON_UNRESOLVED="false"
THREAD_STATE="unresolved"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      require_opt_value "--repo" "${2:-}"
      REPO="${2:-}"
      shift 2
      ;;
    --state)
      require_opt_value "--state" "${2:-}"
      THREAD_STATE="${2:-}"
      shift 2
      ;;
    --include-resolved)
      THREAD_STATE="all"
      shift
      ;;
    --fail-on-unresolved)
      FAIL_ON_UNRESOLVED="true"
      shift
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

case "$THREAD_STATE" in
  unresolved|resolved|all)
    ;;
  *)
    die "invalid --state '$THREAD_STATE' (expected: unresolved, resolved, or all)"
    ;;
esac

if [[ -z "$REPO" ]]; then
  # best-effort: infer from current directory
  REPO="$(gh repo view --json nameWithOwner --jq '.nameWithOwner' 2>/dev/null || true)"
fi
[[ -n "$REPO" ]] || die "could not infer repo; pass --repo owner/repo"

IFS=$'\t' read -r OWNER NAME <<< "$(parse_repo "$REPO")"

QUERY='
query($owner:String!, $repo:String!, $number:Int!, $after:String) {
  repository(owner:$owner, name:$repo) {
    pullRequest(number:$number) {
      reviewThreads(first:100, after:$after) {
        pageInfo {
          hasNextPage
          endCursor
        }
        nodes {
          id
          isResolved
          comments(first:10) {
            nodes {
              id
              databaseId
              author { login }
              body
              path
              line
              url
            }
          }
        }
      }
    }
  }
}
'

echo "Repo: $REPO"
echo "PR:   #$PR_NUMBER"
echo ""

# Pull matching threads and flatten comment nodes with pagination.
# Do not suppress API errors; fail-fast is safer than false green output.
RESULT=""
AFTER=""
FOUND_UNRESOLVED="false"
while :; do
  GH_ARGS=(
    api graphql
    -F owner="$OWNER"
    -F repo="$NAME"
    -F number="$PR_NUMBER"
    -f query="$QUERY"
  )
  if [[ -n "$AFTER" ]]; then
    GH_ARGS+=(-F after="$AFTER")
  fi

  PAGE_JSON="$(gh "${GH_ARGS[@]}" --jq '.data.repository.pullRequest.reviewThreads')"
  [[ -n "$PAGE_JSON" ]] || die "empty response from GitHub API"

  PAGE_HAS_UNRESOLVED="$(printf '%s' "$PAGE_JSON" | jq -r 'if any(.nodes[]?; .isResolved == false) then "true" else "false" end')"
  if [[ "$PAGE_HAS_UNRESOLVED" == "true" ]]; then
    FOUND_UNRESOLVED="true"
  fi

  PAGE_RESULT="$(printf '%s' "$PAGE_JSON" | jq -c --arg state "$THREAD_STATE" '
    .nodes[]
    | select(
        ($state == "unresolved" and .isResolved == false)
        or ($state == "resolved" and .isResolved == true)
        or ($state == "all")
      )
    | . as $thread
    | .comments.nodes[]
    | {
        resolved: $thread.isResolved,
        threadId: $thread.id,
        commentNodeId: .id,
        commentId: .databaseId,
        author: .author.login,
        path: .path,
        line: .line,
        url: .url,
        body: .body
      }
  ')"
  if [[ -n "$PAGE_RESULT" ]]; then
    if [[ -n "$RESULT" ]]; then
      RESULT+=$'\n'
    fi
    RESULT+="$PAGE_RESULT"
  fi

  HAS_NEXT="$(printf '%s' "$PAGE_JSON" | jq -r '.pageInfo.hasNextPage')"
  if [[ "$HAS_NEXT" != "true" ]]; then
    break
  fi
  AFTER="$(printf '%s' "$PAGE_JSON" | jq -r '.pageInfo.endCursor')"
  [[ -n "$AFTER" && "$AFTER" != "null" ]] || die "pagination cursor missing while hasNextPage=true"
done

if [[ -z "$RESULT" ]]; then
  case "$THREAD_STATE" in
    unresolved)
      echo "✅ No unresolved inline review threads found."
      ;;
    resolved)
      echo "✅ No resolved inline review threads found."
      ;;
    all)
      echo "✅ No inline review threads found."
      ;;
  esac
  exit 0
fi

case "$THREAD_STATE" in
  unresolved)
    echo "⚠️ Unresolved inline review threads:"
    ;;
  resolved)
    echo "ℹ️ Resolved inline review threads:"
    ;;
  all)
    echo "ℹ️ Inline review threads (all states):"
    ;;
esac
echo "$RESULT" | while IFS= read -r line; do
  # Each line is JSON (because --jq outputs objects). Print it as-is for machine readability.
  echo "$line"
done

echo ""
echo "Tip: Copy a thread URL and reply in the original thread in GitHub UI when possible."

if [[ "$FAIL_ON_UNRESOLVED" == "true" && "$FOUND_UNRESOLVED" == "true" ]]; then
  exit 3
fi
