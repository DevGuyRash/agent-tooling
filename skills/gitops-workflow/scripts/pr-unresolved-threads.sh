#!/usr/bin/env bash
set -euo pipefail

# pr-unresolved-threads.sh - List unresolved GitHub PR review threads (inline comments).
#
# Usage:
#   bash scripts/pr-unresolved-threads.sh <pr_number> [--repo owner/repo] [--fail-on-unresolved]
#
# Requirements:
#   - gh (GitHub CLI) authenticated
#
# Output:
#   Prints unresolved threads in a readable format.
#   Default exit is 0 even if threads exist; use --fail-on-unresolved to return 3.

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
FAIL_ON_UNRESOLVED="false"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      REPO="${2:-}"
      shift 2
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

if [[ -z "$REPO" ]]; then
  # best-effort: infer from current directory
  REPO="$(gh repo view --json nameWithOwner --jq '.nameWithOwner' 2>/dev/null || true)"
fi
[[ -n "$REPO" ]] || die "could not infer repo; pass --repo owner/repo"

OWNER="${REPO%%/*}"
NAME="${REPO##*/}"

QUERY='
query($owner:String!, $repo:String!, $number:Int!) {
  repository(owner:$owner, name:$repo) {
    pullRequest(number:$number) {
      reviewThreads(first:100) {
        nodes {
          isResolved
          comments(first:10) {
            nodes {
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

# Pull unresolved threads and flatten comment nodes.
# Do not suppress API errors; fail-fast is safer than false green output.
RESULT="$(gh api graphql -F owner="$OWNER" -F repo="$NAME" -F number="$PR_NUMBER" -f query="$QUERY" --jq '
  .data.repository.pullRequest.reviewThreads.nodes[]
  | select(.isResolved == false)
  | .comments.nodes[]
  | {author: .author.login, path: .path, line: .line, url: .url, body: .body}
')"

if [[ -z "$RESULT" ]]; then
  echo "✅ No unresolved inline review threads found."
  exit 0
fi

echo "⚠️ Unresolved inline review threads:"
echo "$RESULT" | while IFS= read -r line; do
  # Each line is JSON (because --jq outputs objects). Print it as-is for machine readability.
  echo "$line"
done

echo ""
echo "Tip: Copy a thread URL and reply in the original thread in GitHub UI when possible."

if [[ "$FAIL_ON_UNRESOLVED" == "true" ]]; then
  exit 3
fi
