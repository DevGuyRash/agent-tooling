#!/usr/bin/env bash
# gitops-catalog: {"id":"pr-update","topic":"pr","command":"update pr body","phrases":["update pr body","edit pr body"],"summary":"Update an existing PR body using deterministic body-file-safe flow.","script":"pr-update-body.sh","creates_branch":false,"creates_worktree":false,"creates_pr":false,"mutates_history":false,"stays_on_current_branch":true,"supports_json":false}
set -euo pipefail

# pr-update-body.sh - Deterministically update an existing PR body using body-file flow.
#
# Usage:
#   bash scripts/pr-update-body.sh <pr_number> [--repo owner/repo] --body-file <path> [--dry-run]
#   bash scripts/pr-update-body.sh <pr_number> [--repo owner/repo] --body "<text>" [--dry-run]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

print_help() {
  cat <<'USAGE'
Usage:
  bash scripts/pr-update-body.sh <pr_number> [--repo owner/repo] --body-file <path> [--dry-run]
  bash scripts/pr-update-body.sh <pr_number> [--repo owner/repo] --body "<text>" [--dry-run]

Options:
  --repo <owner/repo>  Optional repository override.
  --body-file <path>   Path to file used as PR body.
  --body "<text>"      Inline body text. Literal '\n' is normalized.
  --dry-run            Print command path but do not mutate PR.
  -h, --help           Show help.
USAGE
}

PR_NUMBER="${1:-}"
if [[ "$PR_NUMBER" == "-h" || "$PR_NUMBER" == "--help" || -z "$PR_NUMBER" ]]; then
  print_help
  exit 0
fi
shift || true

REPO=""
BODY=""
BODY_FILE=""
DRY_RUN="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      require_opt_value "--repo" "${2:-}"
      REPO="${2:-}"
      shift 2
      ;;
    --body-file)
      require_opt_value "--body-file" "${2:-}"
      BODY_FILE="${2:-}"
      shift 2
      ;;
    --body)
      require_opt_value "--body" "${2:-}"
      BODY="${2:-}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN="true"
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
  die "missing body content; pass --body or --body-file"
fi
if [[ -n "$REPO" ]]; then
  parse_repo "$REPO" >/dev/null
fi

TMP_BODY_FILE=""
KEEP_TMP_BODY_FILE="false"
cleanup() {
  if [[ "$KEEP_TMP_BODY_FILE" == "true" ]]; then
    return 0
  fi
  if [[ -n "$TMP_BODY_FILE" && -f "$TMP_BODY_FILE" ]]; then
    rm -f "$TMP_BODY_FILE"
  fi
}
trap cleanup EXIT

if [[ -n "$BODY" ]]; then
  TMP_BODY_FILE="$(mktemp -t pr-update-body.XXXXXX.md)"
  BODY_NORMALIZED="${BODY//\\n/$'\n'}"
  printf '%s\n' "$BODY_NORMALIZED" > "$TMP_BODY_FILE"
  BODY_FILE="$TMP_BODY_FILE"
fi

[[ -f "$BODY_FILE" ]] || die "body file not found: $BODY_FILE"

ARGS=(pr edit "$PR_NUMBER" --body-file "$BODY_FILE")
if [[ -n "$REPO" ]]; then
  ARGS+=(--repo "$REPO")
fi

if [[ "$DRY_RUN" == "true" ]]; then
  if [[ -n "$TMP_BODY_FILE" ]]; then
    KEEP_TMP_BODY_FILE="true"
  fi
  PREVIEW_CMD="gh"
  for arg in "${ARGS[@]}"; do
    printf -v arg_quoted '%q' "$arg"
    PREVIEW_CMD+=" $arg_quoted"
  done
  echo "DRY-RUN: $PREVIEW_CMD"
  if [[ "$KEEP_TMP_BODY_FILE" == "true" ]]; then
    echo "DRY-RUN: retained generated body file for reuse: $TMP_BODY_FILE"
  fi
  exit 0
fi

require_cmd gh
gh "${ARGS[@]}"
echo "✅ Updated PR #$PR_NUMBER body."
