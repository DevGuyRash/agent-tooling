#!/usr/bin/env bash
set -euo pipefail

# pr-template-discover.sh - Discover and extract PR templates deterministically.
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
JSON_RENDERER="$SCRIPT_DIR/lib/pr_template_discover_json.py"
LOCAL_ONLY="false"

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
    --local-only)
      LOCAL_ONLY="true"
      shift
      ;;
    -h|--help)
      cat <<'USAGE'
Usage:
  bash scripts/pr-template-discover.sh [--repo owner/repo] [--format text|json] [--local-only]
  bash scripts/pr-template-discover.sh [--repo owner/repo] --template-id <path> [--local-only]
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

if [[ "$LOCAL_ONLY" == "true" && -n "$REPO" ]]; then
  die "--local-only cannot be combined with --repo"
fi

collect_local_templates() {
  local root="$1"
  local path=""
  local tmp_file="$2"

  for path in \
    ".github/pull_request_template.md" \
    ".github/PULL_REQUEST_TEMPLATE.md" \
    "pull_request_template.md" \
    "PULL_REQUEST_TEMPLATE.md" \
    "docs/pull_request_template.md" \
    "docs/PULL_REQUEST_TEMPLATE.md"; do
    if [[ -f "$root/$path" ]]; then
      printf 'local\t%s\tlocal:%s\n' "$path" "$path" >> "$tmp_file"
    fi
  done

  for path in \
    ".github/PULL_REQUEST_TEMPLATE" \
    "PULL_REQUEST_TEMPLATE" \
    "docs/PULL_REQUEST_TEMPLATE"; do
    if [[ -d "$root/$path" ]]; then
      while IFS= read -r found_path; do
        [[ -n "$found_path" ]] || continue
        printf 'local\t%s\tlocal:%s\n' "$found_path" "$found_path" >> "$tmp_file"
      done < <(cd "$root" && find "$path" -type f | sort | awk 'tolower($0) ~ /\.md$/')
    fi
  done
}

collect_remote_templates() {
  local owner="$1"
  local name="$2"
  local ref="$3"
  local tmp_file="$4"
  local path=""
  local file_json=""
  local dir_json=""

  require_cmd gh
  require_cmd jq

  for path in \
    ".github/pull_request_template.md" \
    ".github/PULL_REQUEST_TEMPLATE.md" \
    "pull_request_template.md" \
    "PULL_REQUEST_TEMPLATE.md" \
    "docs/pull_request_template.md" \
    "docs/PULL_REQUEST_TEMPLATE.md"; do
    file_json="$(fetch_file_json "$owner" "$name" "$ref" "$path")"
    if [[ -n "$file_json" ]] && [[ "$(printf '%s' "$file_json" | jq -r '.type // empty')" == "file" ]]; then
      printf 'remote\t%s\tremote:%s\n' "$path" "$path" >> "$tmp_file"
    fi
  done

  for path in \
    ".github/PULL_REQUEST_TEMPLATE" \
    "PULL_REQUEST_TEMPLATE" \
    "docs/PULL_REQUEST_TEMPLATE"; do
    dir_json="$(fetch_dir_json "$owner" "$name" "$ref" "$path")"
    if [[ -n "$dir_json" ]] && [[ "$(printf '%s' "$dir_json" | jq -r 'type')" == "array" ]]; then
      printf '%s\n' "$dir_json" | jq -r '.[] | select(.type == "file") | .path | select(ascii_downcase | endswith(".md"))' | while IFS= read -r remote_path; do
        [[ -n "$remote_path" ]] || continue
        printf 'remote\t%s\tremote:%s\n' "$remote_path" "$remote_path" >> "$tmp_file"
      done
    fi
  done
}

resolve_template_record() {
  local requested_id="$1"
  local records_file="$2"
  local exact=""
  local raw_matches=""
  local match_count=""

  exact="$(awk -F '\t' -v want="$requested_id" '$3 == want { print $0; exit }' "$records_file")"
  if [[ -n "$exact" ]]; then
    printf '%s\n' "$exact"
    return 0
  fi

  raw_matches="$(awk -F '\t' -v want="$requested_id" '$2 == want { print $0 }' "$records_file")"
  match_count="$(printf '%s\n' "$raw_matches" | sed '/^$/d' | wc -l | tr -d ' ')"
  if [[ "$match_count" == "1" ]]; then
    printf '%s\n' "$raw_matches" | sed -n '1p'
    return 0
  fi
  if [[ "$match_count" -gt 1 ]]; then
    die "template id '$requested_id' is ambiguous; use one of: $(printf '%s\n' "$raw_matches" | awk -F '\t' '{print $3}' | paste -sd ', ' -)"
  fi
  die "template id not found: $requested_id"
}

resolve_default_branch() {
  local repo="$1"
  local err_file=""
  local out=""
  local err_text=""

  err_file="$(mktemp)"
  if out="$(gh repo view "$repo" --json defaultBranchRef --jq '.defaultBranchRef.name' 2>"$err_file")"; then
    rm -f "$err_file"
    printf '%s' "$out"
    return 0
  fi

  err_text="$(tr '\n' ' ' < "$err_file" | sed 's/[[:space:]]\+/ /g; s/^ //; s/ $//')"
  rm -f "$err_file"
  [[ -n "$err_text" ]] || err_text="unknown error"
  echo "gh repo view failed while resolving default branch for $repo: $err_text" >&2
  return 1
}

if [[ "$LOCAL_ONLY" != "true" && -z "$REPO" ]]; then
  if command -v gh >/dev/null 2>&1; then
    REPO="$(gh repo view --json nameWithOwner --jq '.nameWithOwner' 2>/dev/null || true)"
  fi
fi
OWNER=""
NAME=""
DEFAULT_BRANCH=""
CHECKOUT_REPO=""
USE_LOCAL_TEMPLATES="false"
TMP_LIST="$(mktemp)"
SORTED_LIST="$(mktemp)"
trap 'rm -f "$TMP_LIST" "$SORTED_LIST"' EXIT

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  LOCAL_ROOT="$(git rev-parse --show-toplevel)"
  if [[ -z "$REPO" ]]; then
    USE_LOCAL_TEMPLATES="true"
  elif command -v gh >/dev/null 2>&1; then
    CHECKOUT_REPO="$(gh repo view --json nameWithOwner --jq '.nameWithOwner' 2>/dev/null || true)"
    if [[ -n "$CHECKOUT_REPO" && "$CHECKOUT_REPO" == "$REPO" ]]; then
      USE_LOCAL_TEMPLATES="true"
    fi
  fi
  if [[ "$USE_LOCAL_TEMPLATES" == "true" ]]; then
    collect_local_templates "$LOCAL_ROOT" "$TMP_LIST"
  fi
fi

if [[ -n "$REPO" ]]; then
  IFS=$'\t' read -r OWNER NAME <<< "$(parse_repo "$REPO")"
  require_cmd gh
  if DEFAULT_BRANCH="$(resolve_default_branch "$REPO")"; then
    collect_remote_templates "$OWNER" "$NAME" "$DEFAULT_BRANCH" "$TMP_LIST"
  elif [[ ! -s "$TMP_LIST" ]]; then
    die "could not resolve default branch for $REPO"
  else
    echo "Warning: continuing with local PR templates only for $REPO." >&2
  fi
elif [[ ! -s "$TMP_LIST" ]]; then
  die "could not infer repo and no local PR templates were found; pass --repo owner/repo"
fi

if [[ -s "$TMP_LIST" ]]; then
  sort -u "$TMP_LIST" > "$SORTED_LIST"
else
  : > "$SORTED_LIST"
fi

if [[ -n "$TEMPLATE_ID" ]]; then
  RECORD="$(resolve_template_record "$TEMPLATE_ID" "$SORTED_LIST")"
  IFS=$'\t' read -r SOURCE MATCHED RESOLVED_ID <<< "$RECORD"
  if [[ "$SOURCE" == "local" ]]; then
    [[ -n "${LOCAL_ROOT:-}" ]] || die "local template resolution requires a git checkout"
    cat "$LOCAL_ROOT/$MATCHED"
    exit 0
  fi
  require_cmd jq
  require_cmd base64
  TEMPLATE_JSON="$(fetch_file_json "$OWNER" "$NAME" "$DEFAULT_BRANCH" "$MATCHED")"
  [[ -n "$TEMPLATE_JSON" ]] || die "failed to fetch template content for $MATCHED"
  ENCODING="$(printf '%s' "$TEMPLATE_JSON" | jq -r '.encoding // empty')"
  [[ "$ENCODING" == "base64" ]] || die "unexpected template encoding for $MATCHED"
  printf '%s' "$TEMPLATE_JSON" | jq -r '.content' | tr -d '\n' | decode_base64
  exit 0
fi

if [[ "$FORMAT" == "json" ]]; then
  python3 "$JSON_RENDERER" "$SORTED_LIST" "$REPO" "$DEFAULT_BRANCH"
  exit 0
fi

echo "Repo: ${REPO:-(none)}"
echo "Ref:  ${DEFAULT_BRANCH:-(local checkout)}"
COUNT="$(sed -n '/./p' "$SORTED_LIST" | wc -l | tr -d ' ')"
echo "Templates: $COUNT"
if [[ "$COUNT" -eq 0 ]]; then
  echo "- (none)"
  exit 0
fi

awk -F '\t' '{printf("- %s (%s)\n", $3, $2)}' "$SORTED_LIST"
