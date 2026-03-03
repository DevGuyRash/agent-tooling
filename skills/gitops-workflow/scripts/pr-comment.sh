#!/usr/bin/env bash
set -euo pipefail

# pr-comment.sh - Post a deterministic PR top-level comment via body file.
#
# Usage:
#   bash scripts/pr-comment.sh <pr_number> --body "<text>" [--repo owner/repo]
#   bash scripts/pr-comment.sh <pr_number> --body-file <path> [--repo owner/repo]
#
# Notes:
# - Always posts with `gh pr comment --body-file`.
# - When using --body, literal `\n` sequences are normalized to real newlines.

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
  bash scripts/pr-comment.sh <pr_number> --body "<text>" [--repo owner/repo]
  bash scripts/pr-comment.sh <pr_number> --body-file <path> [--repo owner/repo]

Arguments:
  <pr_number>          Pull request number.

Options:
  --body <text>        Comment text. Literal '\n' is normalized to real newlines.
  --body-file <path>   Path to a comment body file.
  --repo <owner/repo>  Optional repository override.
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
  die "missing comment body; pass --body or --body-file"
fi

TMP_BODY_FILE=""
cleanup() {
  if [[ -n "$TMP_BODY_FILE" && -f "$TMP_BODY_FILE" ]]; then
    rm -f "$TMP_BODY_FILE"
  fi
}
trap cleanup EXIT

if [[ -n "$BODY" ]]; then
  TMP_BODY_FILE="$(mktemp -t pr-comment.XXXXXX.md)"
  BODY_NORMALIZED="${BODY//\\n/$'\n'}"
  printf '%s\n' "$BODY_NORMALIZED" > "$TMP_BODY_FILE"
  BODY_FILE="$TMP_BODY_FILE"
fi

[[ -f "$BODY_FILE" ]] || die "body file not found: $BODY_FILE"

require_cmd gh

ARGS=(pr comment "$PR_NUMBER" --body-file "$BODY_FILE")
if [[ -n "$REPO" ]]; then
  ARGS+=(--repo "$REPO")
fi

gh "${ARGS[@]}"
