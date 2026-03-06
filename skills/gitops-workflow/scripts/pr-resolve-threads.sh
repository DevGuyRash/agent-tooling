#!/usr/bin/env bash
set -euo pipefail

# pr-resolve-threads.sh - Resolve unresolved PR review threads deterministically.
#
# Usage:
#   bash scripts/pr-resolve-threads.sh <pr_number> [--repo owner/repo] --all [--author <login>] [--dry-run]
#   bash scripts/pr-resolve-threads.sh <pr_number> [--repo owner/repo] --thread-id <id> [--thread-id <id> ...] [--dry-run]
#
# Notes:
# - Requires explicit selector: either --all or one/more --thread-id.
# - Uses paginated GraphQL query for unresolved threads.
# - Exit 0 when selected threads are resolved (or none matched with --all).

case "${BASH_SOURCE[0]}" in
  */*) SCRIPT_DIR="$(cd "${BASH_SOURCE[0]%/*}" && pwd -P)" ;;
  *) SCRIPT_DIR="$(pwd -P)" ;;
esac
# shellcheck source=skills/gitops-workflow/scripts/lib/bootstrap.sh
source "$SCRIPT_DIR/lib/bootstrap.sh"
gitops_workflow_maybe_reexec_repo_local_copy "$SCRIPT_DIR" "pr-resolve-threads.sh" "$@"

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
shift || true
[[ -n "$PR_NUMBER" ]] || die "missing <pr_number>"

REPO=""
SELECT_ALL="false"
DRY_RUN="false"
AUTHOR_FILTER=""
THREAD_IDS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      require_opt_value "--repo" "${2:-}"
      REPO="${2:-}"
      shift 2
      ;;
    --all)
      SELECT_ALL="true"
      shift
      ;;
    --thread-id)
      require_opt_value "--thread-id" "${2:-}"
      THREAD_IDS+=("${2:-}")
      shift 2
      ;;
    --author)
      require_opt_value "--author" "${2:-}"
      AUTHOR_FILTER="${2:-}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN="true"
      shift
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

if [[ "$SELECT_ALL" != "true" && ${#THREAD_IDS[@]} -eq 0 ]]; then
  die "select threads with --all or --thread-id <id>"
fi

if [[ "$SELECT_ALL" == "true" && ${#THREAD_IDS[@]} -gt 0 ]]; then
  die "use either --all or --thread-id, not both"
fi

if [[ -z "$REPO" ]]; then
  REPO="$(gh repo view --json nameWithOwner --jq '.nameWithOwner' 2>/dev/null || true)"
fi
[[ -n "$REPO" ]] || die "could not infer repo; pass --repo owner/repo"

IFS=$'\t' read -r OWNER NAME <<< "$(parse_repo "$REPO")"

QUERY='query($owner:String!, $repo:String!, $number:Int!, $after:String) {
  repository(owner:$owner, name:$repo) {
    pullRequest(number:$number) {
      reviewThreads(first:100, after:$after) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          isResolved
          comments(first:1) {
            nodes {
              author { login }
              path
              url
            }
          }
        }
      }
    }
  }
}'

unresolved_rows=()
AFTER=""
while :; do
  GH_ARGS=(
    api graphql
    -F owner="$OWNER"
    -F repo="$NAME"
    -F number="$PR_NUMBER"
    -f query="$QUERY"
  )
  if [[ -n "$AFTER" ]]; then
    GH_ARGS+=( -F after="$AFTER" )
  fi

  mapfile -t PAGE_ROWS < <(gh "${GH_ARGS[@]}" --jq '
    .data.repository.pullRequest.reviewThreads.nodes[]
    | select(.isResolved == false)
    | [ .id, (.comments.nodes[0].author.login // ""), (.comments.nodes[0].path // ""), (.comments.nodes[0].url // "") ]
    | @tsv
  ')

  if [[ ${#PAGE_ROWS[@]} -gt 0 ]]; then
    unresolved_rows+=("${PAGE_ROWS[@]}")
  fi

  HAS_NEXT="$(gh "${GH_ARGS[@]}" --jq '.data.repository.pullRequest.reviewThreads.pageInfo.hasNextPage')"
  if [[ "$HAS_NEXT" != "true" ]]; then
    break
  fi
  AFTER="$(gh "${GH_ARGS[@]}" --jq '.data.repository.pullRequest.reviewThreads.pageInfo.endCursor')"
  [[ -n "$AFTER" && "$AFTER" != "null" ]] || die "pagination cursor missing while hasNextPage=true"
done

# Build lookup: thread_id -> row
selected_ids=()
if [[ "$SELECT_ALL" == "true" ]]; then
  for row in "${unresolved_rows[@]}"; do
    IFS=$'\t' read -r tid author path url <<< "$row"
    if [[ -n "$AUTHOR_FILTER" && "$author" != "$AUTHOR_FILTER" ]]; then
      continue
    fi
    selected_ids+=("$tid")
  done
else
  # Resolve only explicitly selected unresolved threads.
  for requested in "${THREAD_IDS[@]}"; do
    found="false"
    for row in "${unresolved_rows[@]}"; do
      IFS=$'\t' read -r tid author path url <<< "$row"
      if [[ "$tid" == "$requested" ]]; then
        found="true"
        selected_ids+=("$tid")
        break
      fi
    done
    if [[ "$found" != "true" ]]; then
      die "thread id not currently unresolved or not found: $requested"
    fi
  done
fi

# De-dupe selected ids while preserving order.
unique_selected=()
seen_ids=""
for tid in "${selected_ids[@]}"; do
  if [[ " $seen_ids " == *" $tid "* ]]; then
    continue
  fi
  unique_selected+=("$tid")
  seen_ids+=" $tid"
done

if [[ ${#unique_selected[@]} -eq 0 ]]; then
  echo "✅ No unresolved threads matched selection."
  exit 0
fi

echo "Repo: $REPO"
echo "PR:   #$PR_NUMBER"
echo "Selected unresolved threads: ${#unique_selected[@]}"

if [[ "$DRY_RUN" == "true" ]]; then
  for tid in "${unique_selected[@]}"; do
    echo "DRY-RUN resolve thread: $tid"
  done
  exit 0
fi

for tid in "${unique_selected[@]}"; do
  resolved="$(gh api graphql -F threadId="$tid" -f query='mutation($threadId:ID!){ resolveReviewThread(input:{threadId:$threadId}) { thread { isResolved } } }' --jq '.data.resolveReviewThread.thread.isResolved')"
  if [[ "$resolved" != "true" ]]; then
    die "failed to resolve thread: $tid"
  fi
  echo "✅ Resolved thread: $tid"
done
