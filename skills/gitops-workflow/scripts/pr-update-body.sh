#!/usr/bin/env bash
set -euo pipefail

# pr-update-body.sh - Deterministically update an existing PR body using body-file flow.
#
# Usage:
#   bash scripts/pr-update-body.sh <pr_number> [--repo owner/repo] --body-file <path> [--dry-run]
#   bash scripts/pr-update-body.sh <pr_number> [--repo owner/repo] --body "<text>" [--dry-run]

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
}

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
  parse_repo "$REPO"
fi

TMP_BODY_FILE=""
cleanup() {
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

require_cmd gh

ARGS=(pr edit "$PR_NUMBER" --body-file "$BODY_FILE")
if [[ -n "$REPO" ]]; then
  ARGS+=(--repo "$REPO")
fi

if [[ "$DRY_RUN" == "true" ]]; then
  PREVIEW_CMD="gh"
  for arg in "${ARGS[@]}"; do
    printf -v arg_quoted '%q' "$arg"
    PREVIEW_CMD+=" $arg_quoted"
  done
  echo "DRY-RUN: $PREVIEW_CMD"
  exit 0
fi

gh "${ARGS[@]}"
echo "✅ Updated PR #$PR_NUMBER body."
