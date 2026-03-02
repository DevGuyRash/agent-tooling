#!/usr/bin/env bash
set -euo pipefail

# issue-create.sh - Deterministic GitHub issue creation with body-file-safe flow.
#
# Usage:
#   bash scripts/issue-create.sh --title "<title>" [--repo owner/repo] [--body-file <path> | --body "<text>"] [--template-id <path>] [--label <name> ...] [--assignee <login> ...] [--milestone <name|number>] [--create --force-create] [--dry-run]

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

TITLE=""
REPO=""
BODY=""
BODY_FILE=""
TEMPLATE_ID=""
CREATE="false"
FORCE_CREATE="false"
DRY_RUN="false"
LABELS=()
ASSIGNEES=()
MILESTONE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --title)
      require_opt_value "--title" "${2:-}"
      TITLE="${2:-}"
      shift 2
      ;;
    --repo)
      require_opt_value "--repo" "${2:-}"
      REPO="${2:-}"
      shift 2
      ;;
    --body)
      require_opt_value "--body" "${2:-}"
      BODY="${2:-}"
      shift 2
      ;;
    --body-file)
      require_opt_value "--body-file" "${2:-}"
      BODY_FILE="${2:-}"
      shift 2
      ;;
    --template-id)
      require_opt_value "--template-id" "${2:-}"
      TEMPLATE_ID="${2:-}"
      shift 2
      ;;
    --label)
      require_opt_value "--label" "${2:-}"
      LABELS+=("${2:-}")
      shift 2
      ;;
    --assignee)
      require_opt_value "--assignee" "${2:-}"
      ASSIGNEES+=("${2:-}")
      shift 2
      ;;
    --milestone)
      require_opt_value "--milestone" "${2:-}"
      MILESTONE="${2:-}"
      shift 2
      ;;
    --create)
      CREATE="true"
      shift
      ;;
    --force-create)
      FORCE_CREATE="true"
      shift
      ;;
    --dry-run)
      DRY_RUN="true"
      shift
      ;;
    -h|--help)
      cat <<'USAGE'
Usage:
  bash scripts/issue-create.sh --title "<title>" [--repo owner/repo] [--body-file <path> | --body "<text>"] [--template-id <path>] [--label <name> ...] [--assignee <login> ...] [--milestone <name|number>] [--create --force-create] [--dry-run]

Behavior:
  - Generates a deterministic body file by default and prints next-step command.
  - Resolves remote issue templates when available via issue-template-discover.sh.
  - If multiple remote templates exist and no explicit body is provided, --template-id is required before --create.
  - Does not create an issue unless --create and --force-create are both provided.
USAGE
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

[[ -n "$TITLE" ]] || die "missing --title"
if [[ -n "$BODY" && -n "$BODY_FILE" ]]; then
  die "use either --body or --body-file, not both"
fi
if [[ -n "$REPO" ]]; then
  parse_repo "$REPO"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
ISSUE_TEMPLATE_SCRIPT="$SCRIPT_DIR/issue-template-discover.sh"
DEFAULT_ISSUE_TEMPLATE="$SKILL_ROOT/assets/templates/issue-body.md"

resolve_repo() {
  if [[ -n "$REPO" ]]; then
    echo "$REPO"
    return 0
  fi
  if ! command -v gh >/dev/null 2>&1; then
    return 0
  fi
  gh repo view --json nameWithOwner --jq '.nameWithOwner' 2>/dev/null || true
}

EFFECTIVE_REPO="$(resolve_repo)"
if [[ -n "$EFFECTIVE_REPO" ]]; then
  parse_repo "$EFFECTIVE_REPO"
fi

REMOTE_TEMPLATE_ID=""
REMOTE_TEMPLATE_CONTENT=""
if [[ -z "$BODY" && -z "$BODY_FILE" && -n "$EFFECTIVE_REPO" && -f "$ISSUE_TEMPLATE_SCRIPT" ]]; then
  TEMPLATE_DISCOVERY_JSON=""
  if ! TEMPLATE_DISCOVERY_JSON="$(bash "$ISSUE_TEMPLATE_SCRIPT" --repo "$EFFECTIVE_REPO" --format json)"; then
    if [[ "$CREATE" == "true" ]]; then
      die "issue template discovery failed for $EFFECTIVE_REPO; refusing --create"
    fi
    echo "Warning: issue template discovery failed for $EFFECTIVE_REPO; using skill fallback template." >&2
  fi

  if [[ -n "$TEMPLATE_DISCOVERY_JSON" ]] && printf '%s' "$TEMPLATE_DISCOVERY_JSON" | jq -e '.templates' >/dev/null 2>&1; then
    TEMPLATE_COUNT="$(printf '%s' "$TEMPLATE_DISCOVERY_JSON" | jq '.templates | length')"
    if [[ "$TEMPLATE_COUNT" -eq 1 ]]; then
      REMOTE_TEMPLATE_ID="$(printf '%s' "$TEMPLATE_DISCOVERY_JSON" | jq -r '.templates[0].id')"
    fi

    if [[ -n "$TEMPLATE_ID" ]]; then
      FOUND="$(printf '%s' "$TEMPLATE_DISCOVERY_JSON" | jq -r --arg id "$TEMPLATE_ID" 'any(.templates[]?; .id == $id)')"
      [[ "$FOUND" == "true" ]] || die "template id not found in $EFFECTIVE_REPO: $TEMPLATE_ID"
      REMOTE_TEMPLATE_ID="$TEMPLATE_ID"
    fi

    if [[ "$CREATE" == "true" && "$TEMPLATE_COUNT" -gt 1 && -z "$REMOTE_TEMPLATE_ID" ]]; then
      echo "Multiple remote issue templates detected. Select one with --template-id <path>."
      bash "$ISSUE_TEMPLATE_SCRIPT" --repo "$EFFECTIVE_REPO" --format text
      die "template selection required before --create"
    fi

    if [[ -n "$REMOTE_TEMPLATE_ID" ]]; then
      REMOTE_TEMPLATE_CONTENT="$(bash "$ISSUE_TEMPLATE_SCRIPT" --repo "$EFFECTIVE_REPO" --template-id "$REMOTE_TEMPLATE_ID")"
    fi
  fi
fi

if [[ -n "$BODY" ]]; then
  TMP_BODY_FILE="$(mktemp -t issue-body.XXXXXX.md)"
  BODY_NORMALIZED="${BODY//\\n/$'\n'}"
  printf '%s\n' "$BODY_NORMALIZED" > "$TMP_BODY_FILE"
  BODY_FILE="$TMP_BODY_FILE"
fi

if [[ -z "$BODY_FILE" ]]; then
  TMP_BODY_FILE="$(mktemp -t issue-body.XXXXXX.md)"
  if [[ -n "$REMOTE_TEMPLATE_CONTENT" ]]; then
    echo "<!-- Remote issue template source: $EFFECTIVE_REPO:$REMOTE_TEMPLATE_ID -->" > "$TMP_BODY_FILE"
    echo "" >> "$TMP_BODY_FILE"
    printf '%s\n' "$REMOTE_TEMPLATE_CONTENT" >> "$TMP_BODY_FILE"
  else
    [[ -f "$DEFAULT_ISSUE_TEMPLATE" ]] || die "missing fallback template: $DEFAULT_ISSUE_TEMPLATE"
    cat "$DEFAULT_ISSUE_TEMPLATE" > "$TMP_BODY_FILE"
  fi
  BODY_FILE="$TMP_BODY_FILE"
fi

[[ -f "$BODY_FILE" ]] || die "body file not found: $BODY_FILE"

# Build once so the manual preview command and create path stay in sync.
ARGS=(issue create --title "$TITLE" --body-file "$BODY_FILE")
if [[ -n "$EFFECTIVE_REPO" ]]; then
  ARGS+=(--repo "$EFFECTIVE_REPO")
fi
for label in "${LABELS[@]}"; do
  ARGS+=(--label "$label")
done
for assignee in "${ASSIGNEES[@]}"; do
  ARGS+=(--assignee "$assignee")
done
if [[ -n "$MILESTONE" ]]; then
  ARGS+=(--milestone "$MILESTONE")
fi

PREVIEW_CMD="gh"
for arg in "${ARGS[@]}"; do
  printf -v arg_quoted '%q' "$arg"
  PREVIEW_CMD+=" $arg_quoted"
done

echo "📝 Issue body file prepared: $BODY_FILE"
echo "Review/edit this file as needed, then create the issue with:"
echo "  $PREVIEW_CMD"
echo ""

if [[ "$CREATE" != "true" ]]; then
  exit 0
fi
if [[ "$FORCE_CREATE" != "true" ]]; then
  die "--create requires --force-create to avoid accidental issue creation"
fi

require_cmd gh

if [[ "$DRY_RUN" == "true" ]]; then
  echo "DRY-RUN: gh ${ARGS[*]}"
  exit 0
fi

gh "${ARGS[@]}"
echo "✅ Issue created."
