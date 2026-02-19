#!/usr/bin/env bash
set -euo pipefail

# pr-create.sh - Create a PR using the skill's PR body template.
#
# Usage:
#   bash scripts/pr-create.sh --title "feat(cli): add --json output" [--create] [--draft] [--base main] [--head my-branch]
#
# Behavior:
# - Always writes a PR body file from assets/templates/pull-request-body.md.
# - If --create is provided, runs `gh pr create --body-file <file>`.
# - If --create is not provided, prints the file path so you can edit it first.
#
# Requirements:
# - gh authenticated (only needed with --create)

die() {
  echo "Error: $*" >&2
  exit 1
}

TITLE=""
CREATE="false"
DRAFT="false"
BASE=""
HEAD=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --title)
      TITLE="${2:-}"
      shift 2
      ;;
    --create)
      CREATE="true"
      shift
      ;;
    --draft)
      DRAFT="true"
      shift
      ;;
    --base)
      BASE="${2:-}"
      shift 2
      ;;
    --head)
      HEAD="${2:-}"
      shift 2
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

[[ -n "$TITLE" ]] || die "missing --title"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE="$SCRIPT_DIR/../assets/templates/pull-request-body.md"

[[ -f "$TEMPLATE" ]] || die "template not found at $TEMPLATE"

OUT_FILE="$(mktemp -t pr-body.XXXXXX.md)"
cp "$TEMPLATE" "$OUT_FILE"

echo "📝 PR body file created: $OUT_FILE"
echo "Edit this file to fill placeholders, then create the PR with:"
echo "  gh pr create --title \"$TITLE\" --body-file \"$OUT_FILE\""
echo ""

if [[ "$CREATE" != "true" ]]; then
  exit 0
fi

command -v gh >/dev/null 2>&1 || die "missing required command: gh"

ARGS=(pr create --title "$TITLE" --body-file "$OUT_FILE")

if [[ -n "$BASE" ]]; then
  ARGS+=(--base "$BASE")
fi
if [[ -n "$HEAD" ]]; then
  ARGS+=(--head "$HEAD")
fi
if [[ "$DRAFT" == "true" ]]; then
  ARGS+=(--draft)
fi

gh "${ARGS[@]}"

echo ""
echo "✅ PR created."
