#!/usr/bin/env bash
set -euo pipefail

# pr-labels-list.sh - Deterministically list available PR labels.
#
# Usage:
#   bash scripts/pr-labels-list.sh [--repo owner/repo] [--format text|json]


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

REPO=""
FORMAT="text"

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
    -h|--help)
      cat <<'USAGE'
Usage:
  bash scripts/pr-labels-list.sh [--repo owner/repo] [--format text|json]
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

if [[ -z "$REPO" ]]; then
  REPO="$(gh repo view --json nameWithOwner --jq '.nameWithOwner' 2>/dev/null || true)"
fi
[[ -n "$REPO" ]] || die "could not infer repo; pass --repo owner/repo"

OWNER="${REPO%%/*}"
NAME="${REPO##*/}"

TMP_FILE="$(mktemp)"
trap 'rm -f "$TMP_FILE"' EXIT

PAGE=1
while :; do
  PAGE_JSON="$(gh api "repos/$OWNER/$NAME/labels?per_page=100&page=$PAGE")"
  COUNT="$(printf '%s' "$PAGE_JSON" | jq 'length')"
  if [[ "$COUNT" -eq 0 ]]; then
    break
  fi
  printf '%s\n' "$PAGE_JSON" >> "$TMP_FILE"
  PAGE=$((PAGE + 1))
done

if [[ ! -s "$TMP_FILE" ]]; then
  LABELS_JSON='[]'
else
  LABELS_JSON="$(jq -s '
    add
    | [ .[] | {name, color: (.color|ascii_downcase), description: (.description // "")} ]
    | sort_by(.name)
  ' "$TMP_FILE")"
fi

if [[ "$FORMAT" == "json" ]]; then
  printf '%s\n' "$LABELS_JSON"
  exit 0
fi

echo "Repo: $REPO"
COUNT="$(printf '%s' "$LABELS_JSON" | jq 'length')"
echo "Labels: $COUNT"
if [[ "$COUNT" -eq 0 ]]; then
  echo "- (none)"
  exit 0
fi

printf '%s' "$LABELS_JSON" | jq -r '.[] | if (.description|length) > 0 then "- " + .name + " :: " + .description else "- " + .name end'
