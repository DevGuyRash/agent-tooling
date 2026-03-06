#!/usr/bin/env bash
set -euo pipefail

# pr-template-discover.sh - Discover and extract remote PR templates deterministically.
#
# Usage:
#   bash scripts/pr-template-discover.sh [--repo owner/repo] [--format text|json]
#   bash scripts/pr-template-discover.sh [--repo owner/repo] --template-id <path>

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

REPO=""
FORMAT="text"
TEMPLATE_ID=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      require_opt_value "--repo" "${2:-}"
      REPO="${2:-}"
      shift 2
      ;;
    --format)
      require_opt_value "--format" "${2:-}"
      FORMAT="${2:-}"
      shift 2
      ;;
    --template-id)
      require_opt_value "--template-id" "${2:-}"
      TEMPLATE_ID="${2:-}"
      shift 2
      ;;
    -h|--help)
      cat <<'USAGE'
Usage:
  bash scripts/pr-template-discover.sh [--repo owner/repo] [--format text|json]
  bash scripts/pr-template-discover.sh [--repo owner/repo] --template-id <path>
USAGE
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

case "$FORMAT" in
  text|json)
    ;;
  *)
    die "invalid --format '$FORMAT' (expected: text or json)"
    ;;
esac

require_cmd gh
require_cmd jq
require_cmd base64

if [[ -z "$REPO" ]]; then
  REPO="$(gh repo view --json nameWithOwner --jq '.nameWithOwner' 2>/dev/null || true)"
fi
[[ -n "$REPO" ]] || die "could not infer repo; pass --repo owner/repo"

IFS=$'\t' read -r OWNER NAME <<< "$(parse_repo "$REPO")"
DEFAULT_BRANCH="$(gh repo view "$REPO" --json defaultBranchRef --jq '.defaultBranchRef.name' 2>/dev/null || true)"
[[ -n "$DEFAULT_BRANCH" ]] || die "could not resolve default branch for $REPO"

TMP_LIST="$(mktemp)"
trap 'rm -f "$TMP_LIST"' EXIT

for path in \
  ".github/pull_request_template.md" \
  ".github/PULL_REQUEST_TEMPLATE.md" \
  "pull_request_template.md" \
  "PULL_REQUEST_TEMPLATE.md" \
  "docs/pull_request_template.md" \
  "docs/PULL_REQUEST_TEMPLATE.md"; do
  FILE_JSON="$(fetch_file_json "$OWNER" "$NAME" "$DEFAULT_BRANCH" "$path")"
  if [[ -n "$FILE_JSON" ]] && [[ "$(printf '%s' "$FILE_JSON" | jq -r '.type // empty')" == "file" ]]; then
    printf '%s\n' "$path" >> "$TMP_LIST"
  fi
done

for dir_path in \
  ".github/PULL_REQUEST_TEMPLATE" \
  "PULL_REQUEST_TEMPLATE" \
  "docs/PULL_REQUEST_TEMPLATE"; do
  DIR_JSON="$(fetch_dir_json "$OWNER" "$NAME" "$DEFAULT_BRANCH" "$dir_path")"
  if [[ -n "$DIR_JSON" ]] && [[ "$(printf '%s' "$DIR_JSON" | jq -r 'type')" == "array" ]]; then
    printf '%s\n' "$DIR_JSON" | jq -r '.[] | select(.type == "file") | .path | select(ascii_downcase | endswith(".md"))' >> "$TMP_LIST"
  fi
done

if [[ -s "$TMP_LIST" ]]; then
  TEMPLATES_JSON="$(sort -u "$TMP_LIST" | jq -R -s '
    split("\n")
    | map(select(length > 0))
    | map({id: ., path: .})
  ')"
else
  TEMPLATES_JSON='[]'
fi

if [[ -n "$TEMPLATE_ID" ]]; then
  MATCHED="$(printf '%s' "$TEMPLATES_JSON" | jq -r --arg id "$TEMPLATE_ID" '.[] | select(.id == $id) | .path' | head -n1)"
  [[ -n "$MATCHED" ]] || die "template id not found: $TEMPLATE_ID"
  TEMPLATE_JSON="$(fetch_file_json "$OWNER" "$NAME" "$DEFAULT_BRANCH" "$MATCHED")"
  [[ -n "$TEMPLATE_JSON" ]] || die "failed to fetch template content for $MATCHED"
  ENCODING="$(printf '%s' "$TEMPLATE_JSON" | jq -r '.encoding // empty')"
  [[ "$ENCODING" == "base64" ]] || die "unexpected template encoding for $MATCHED"
  printf '%s' "$TEMPLATE_JSON" | jq -r '.content' | tr -d '\n' | decode_base64
  exit 0
fi

if [[ "$FORMAT" == "json" ]]; then
  printf '%s\n' "$(printf '%s' "$TEMPLATES_JSON" | jq --arg repo "$REPO" --arg ref "$DEFAULT_BRANCH" '{repo: $repo, ref: $ref, templates: .}')"
  exit 0
fi

echo "Repo: $REPO"
echo "Ref:  $DEFAULT_BRANCH"
COUNT="$(printf '%s' "$TEMPLATES_JSON" | jq 'length')"
echo "Templates: $COUNT"
if [[ "$COUNT" -eq 0 ]]; then
  echo "- (none)"
  exit 0
fi

printf '%s' "$TEMPLATES_JSON" | jq -r '.[] | "- " + .id'
