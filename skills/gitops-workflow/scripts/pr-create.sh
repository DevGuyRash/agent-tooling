#!/usr/bin/env bash
set -euo pipefail

# pr-create.sh - Create a PR using deterministic context and repository-aware defaults.
#
# Usage:
#   bash scripts/pr-create.sh --title "feat(cli): add --json output" [--create --force-create] [--ready] [--draft] [--base main] [--head my-branch] [--repo owner/repo] [--label <name> ...] [--no-labels] [--template-id <id>]
#
# Behavior:
# - Writes a prefilled PR body with deterministic reviewer context derived from git metadata.
# - By default, does NOT create a PR; it prints the body path for human/agent review.
# - `--create` requires `--force-create` to run `gh pr create --body-file <file>`.
# - When `--create` is used, draft mode is the default; pass `--ready` to create non-draft PRs.
# - Before `--create`, labels must be explicit (`--label ...` or `--no-labels`) when labels exist.
# - For repositories with multiple discovered PR templates, `--template-id` is required before `--create`.
#
# Requirements:
# - git
# - gh/jq (required only for remote discovery/create)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

TITLE=""
CREATE="false"
FORCE_CREATE="false"
READY="false"
DRAFT_COMPAT="false"
BASE=""
HEAD=""
REPO=""
NO_LABELS="false"
TEMPLATE_ID=""
LABELS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --title)
      require_opt_value "--title" "${2:-}"
      TITLE="${2:-}"
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
    --ready)
      READY="true"
      shift
      ;;
    --draft)
      # Compatibility flag; create is draft by default now.
      DRAFT_COMPAT="true"
      shift
      ;;
    --base)
      require_opt_value "--base" "${2:-}"
      BASE="${2:-}"
      shift 2
      ;;
    --head)
      require_opt_value "--head" "${2:-}"
      HEAD="${2:-}"
      shift 2
      ;;
    --repo)
      require_opt_value "--repo" "${2:-}"
      REPO="${2:-}"
      shift 2
      ;;
    --label)
      require_opt_value "--label" "${2:-}"
      LABELS+=("${2:-}")
      shift 2
      ;;
    --no-labels)
      NO_LABELS="true"
      shift
      ;;
    --template-id)
      require_opt_value "--template-id" "${2:-}"
      TEMPLATE_ID="${2:-}"
      shift 2
      ;;
    -h|--help)
      cat <<'HELP'
Usage:
  bash scripts/pr-create.sh --title "feat(cli): add --json output" [--create --force-create] [--ready] [--draft] [--base main] [--head my-branch] [--repo owner/repo] [--label <name> ...] [--no-labels] [--template-id <id>]

Behavior:
  - Writes a deterministic PR body file from git metadata by default.
  - Does not create a PR unless --create and --force-create are both provided.
  - When creating, draft is default unless --ready is provided.
  - If labels exist in the target repository, pass --label ... or --no-labels.
  - If multiple PR templates exist, pass --template-id <id>.
HELP
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

[[ -n "$TITLE" ]] || die "missing --title"
if [[ "$READY" == "true" && "$DRAFT_COMPAT" == "true" ]]; then
  die "--ready and --draft are mutually exclusive"
fi
if [[ "$NO_LABELS" == "true" && "${#LABELS[@]}" -gt 0 ]]; then
  die "--no-labels cannot be combined with --label"
fi
if [[ "$CREATE" == "true" && "$FORCE_CREATE" != "true" ]]; then
  die "--create requires --force-create to avoid accidental PR creation"
fi

SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
PR_LABELS_SCRIPT="$SCRIPT_DIR/pr-labels-list.sh"
PR_TEMPLATE_SCRIPT="$SCRIPT_DIR/pr-template-discover.sh"
PR_BODY_RENDERER="$SCRIPT_DIR/lib/pr_body_renderer.py"
DEFAULT_PR_TEMPLATE="$SKILL_ROOT/assets/templates/pull-request-body.md"

require_cmd git

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  die "current directory is not a git repository"
fi

resolve_default_base() {
  local base
  base="$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##' || true)"
  if [[ -n "$base" ]]; then
    echo "$base"
    return 0
  fi
  if git show-ref --verify --quiet refs/heads/main; then
    echo "main"
    return 0
  fi
  if git show-ref --verify --quiet refs/heads/master; then
    echo "master"
    return 0
  fi
  echo "main"
}

resolve_repo() {
  if [[ -n "$REPO" ]]; then
    parse_repo "$REPO" >/dev/null
    echo "$REPO"
    return 0
  fi
  if ! command -v gh >/dev/null 2>&1; then
    return 0
  fi
  gh repo view --json nameWithOwner --jq '.nameWithOwner' 2>/dev/null || true
}

select_template_from_json() {
  local requested_id="${1:-}"
  local templates_json="${2:-}"
  python3 - "$requested_id" "$templates_json" <<'PY'
import json
import sys

requested = sys.argv[1]
payload = sys.argv[2]

try:
    data = json.loads(payload or "{}")
except json.JSONDecodeError as exc:
    sys.stderr.write(f"invalid template discovery json: {exc}\n")
    raise SystemExit(2)

templates = data.get("templates")
if not isinstance(templates, list):
    sys.stderr.write("template discovery payload missing templates array\n")
    raise SystemExit(2)

count = len(templates)
selected = None

logical_templates = {}
for template in templates:
    path = template.get("path")
    if not path:
        continue
    existing = logical_templates.get(path)
    if existing is None or (existing.get("source") != "local" and template.get("source") == "local"):
        logical_templates[path] = template

deduped_templates = list(logical_templates.values())

if requested:
    exact = [template for template in templates if template.get("id") == requested]
    if exact:
        selected = exact[0]
    else:
        path_matches = [template for template in deduped_templates if template.get("path") == requested]
        if len(path_matches) == 1:
            selected = path_matches[0]
        else:
            sys.stderr.write(f"template id not found in discovered templates: {requested}\n")
            raise SystemExit(3)
elif len(deduped_templates) == 1:
    selected = deduped_templates[0]
else:
    for template in deduped_templates:
        if template.get("source") == "local":
            selected = template
            break

selected_id = selected.get("id", "") if selected else ""
selected_source = selected.get("source", "") if selected else ""

print(len(deduped_templates))
print(selected_id)
print(selected_source)
PY
}

load_selected_template() {
  local templates_json="$1"
  local discovery_mode="$2"
  local selection_output=""
  local selection_error=""
  local template_fetch_args=()
  local template_fetch_error=""
  local template_count=""
  local selected_id=""
  local selected_source=""
  local selection_status=0
  local selection_message=""
  local fetch_message=""

  selection_error="$(mktemp -t pr-template-selection.XXXXXX.err)"
  if selection_output="$(select_template_from_json "$TEMPLATE_ID" "$templates_json" 2>"$selection_error")"; then
    mapfile -t _template_selection <<< "$selection_output"
    template_count="${_template_selection[0]:-0}"
    selected_id="${_template_selection[1]:-}"
    selected_source="${_template_selection[2]:-}"
  else
    selection_status=$?
    selection_message="$(tr '\n' ' ' < "$selection_error" | sed 's/[[:space:]]\+/ /g; s/^ //; s/ $//')"
    rm -f "$selection_error"
    LAST_TEMPLATE_SELECTION_ERROR="${selection_message:-template selection failed}"
    if [[ "$selection_status" -eq 3 && -n "$EFFECTIVE_REPO" && "$discovery_mode" == "local-only" ]]; then
      return 10
    fi
    if [[ "$CREATE" == "true" || -n "$TEMPLATE_ID" ]]; then
      die "${selection_message:-template selection failed}"
    fi
    echo "Warning: ${selection_message:-template selection failed}; using skill fallback template." >&2
    return 1
  fi
  rm -f "$selection_error"

  TEMPLATE_COUNT="$template_count"
  SELECTED_TEMPLATE_ID=""
  SELECTED_TEMPLATE_SOURCE=""
  SELECTED_TEMPLATE_CONTENT=""

  if [[ -z "$selected_id" ]]; then
    return 0
  fi

  template_fetch_args=(--template-id "$selected_id")
  if [[ "$discovery_mode" == "repo-aware" && -n "$EFFECTIVE_REPO" ]]; then
    template_fetch_args=(--repo "$EFFECTIVE_REPO" --template-id "$selected_id")
  fi
  template_fetch_error="$(mktemp -t pr-template-fetch.XXXXXX.err)"
  if SELECTED_TEMPLATE_CONTENT="$(bash "$PR_TEMPLATE_SCRIPT" "${template_fetch_args[@]}" 2>"$template_fetch_error")"; then
    SELECTED_TEMPLATE_ID="$selected_id"
    SELECTED_TEMPLATE_SOURCE="$selected_source"
    rm -f "$template_fetch_error"
    return 0
  fi

  fetch_message="$(tr '\n' ' ' < "$template_fetch_error" | sed 's/[[:space:]]\+/ /g; s/^ //; s/ $//')"
  rm -f "$template_fetch_error"
  LAST_TEMPLATE_SELECTION_ERROR="${fetch_message:-failed to load template content: $selected_id}"
  SELECTED_TEMPLATE_CONTENT=""
  if [[ "$CREATE" == "true" || -n "$TEMPLATE_ID" ]]; then
    die "${LAST_TEMPLATE_SELECTION_ERROR}"
  fi
  echo "Warning: ${LAST_TEMPLATE_SELECTION_ERROR}; using skill fallback template." >&2
  return 1
}

if [[ -z "$HEAD" ]]; then
  HEAD="$(git rev-parse --abbrev-ref HEAD)"
fi
if [[ -z "$BASE" ]]; then
  BASE="$(resolve_default_base)"
fi
[[ -n "$HEAD" ]] || die "unable to resolve --head branch"
[[ -n "$BASE" ]] || die "unable to resolve --base branch"

if ! git rev-parse --verify "$HEAD" >/dev/null 2>&1; then
  die "head branch/ref not found: $HEAD"
fi
if ! git rev-parse --verify "$BASE" >/dev/null 2>&1; then
  die "base branch/ref not found: $BASE"
fi

CHANGES_FILE="$(mktemp -t pr-changes.XXXXXX.txt)"
COMMITS_FILE="$(mktemp -t pr-commits.XXXXXX.txt)"
trap 'rm -f "$CHANGES_FILE" "$COMMITS_FILE"' EXIT

# Commit subjects should be head-only (PR-introduced) for deterministic summaries.
git log --pretty=format:'%s' "$BASE..$HEAD" > "$COMMITS_FILE"
git diff --name-only "$BASE...$HEAD" > "$CHANGES_FILE"

if [[ ! -s "$COMMITS_FILE" ]]; then
  die "no commits between $BASE and $HEAD; cannot create meaningful PR body"
fi

EFFECTIVE_REPO="$(resolve_repo)"
if [[ -n "$EFFECTIVE_REPO" ]]; then
  parse_repo "$EFFECTIVE_REPO" >/dev/null
fi
TEMPLATE_COUNT=0
SELECTED_TEMPLATE_ID=""
SELECTED_TEMPLATE_CONTENT=""
SELECTED_TEMPLATE_SOURCE=""
EXPLICIT_TEMPLATE_SELECTION="false"
LAST_TEMPLATE_SELECTION_ERROR=""

if [[ -n "$TEMPLATE_ID" && -z "$EFFECTIVE_REPO" ]]; then
  if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    die "--template-id requires a git checkout or --repo owner/repo"
  fi
fi

if [[ -x "$PR_TEMPLATE_SCRIPT" ]]; then
  TEMPLATE_DISCOVER_TEXT_ARGS=(--format text)
  if [[ -n "$EFFECTIVE_REPO" ]]; then
    TEMPLATE_DISCOVER_TEXT_ARGS=(--repo "$EFFECTIVE_REPO" --format text)
  fi

  if [[ "$CREATE" != "true" && -z "$REPO" ]]; then
    LOCAL_TEMPLATES_JSON=""
    if LOCAL_TEMPLATES_JSON="$(bash "$PR_TEMPLATE_SCRIPT" --format json 2>/dev/null)"; then
      if load_selected_template "$LOCAL_TEMPLATES_JSON" "local-only"; then
        :
      elif [[ $? -eq 10 ]]; then
        SELECTED_TEMPLATE_ID=""
        SELECTED_TEMPLATE_SOURCE=""
        SELECTED_TEMPLATE_CONTENT=""
      fi
    fi
  fi

  if [[ -z "$SELECTED_TEMPLATE_ID" ]]; then
    TEMPLATES_JSON=""
    TEMPLATE_DISCOVER_ARGS=(--format json)
    if [[ -n "$EFFECTIVE_REPO" ]]; then
      TEMPLATE_DISCOVER_ARGS=(--repo "$EFFECTIVE_REPO" --format json)
    fi
    if ! TEMPLATES_JSON="$(bash "$PR_TEMPLATE_SCRIPT" "${TEMPLATE_DISCOVER_ARGS[@]}")"; then
      if [[ "$CREATE" == "true" ]]; then
        die "template discovery failed${EFFECTIVE_REPO:+ for $EFFECTIVE_REPO}; refusing --create"
      fi
      echo "Warning: template discovery failed${EFFECTIVE_REPO:+ for $EFFECTIVE_REPO}; using skill fallback template." >&2
    elif [[ -n "$TEMPLATES_JSON" ]]; then
      load_selected_template "$TEMPLATES_JSON" "repo-aware"
    fi
  fi

  if [[ -n "$TEMPLATE_ID" && -n "$SELECTED_TEMPLATE_ID" ]]; then
    EXPLICIT_TEMPLATE_SELECTION="true"
  fi

  if [[ -n "$TEMPLATE_ID" && -z "$SELECTED_TEMPLATE_ID" ]]; then
    die "${LAST_TEMPLATE_SELECTION_ERROR:-template selection failed}"
  fi

  if [[ "$CREATE" == "true" && "$TEMPLATE_COUNT" -gt 1 && "$EXPLICIT_TEMPLATE_SELECTION" != "true" ]]; then
    echo "Multiple PR templates detected. Select one with --template-id <id>."
    bash "$PR_TEMPLATE_SCRIPT" "${TEMPLATE_DISCOVER_TEXT_ARGS[@]}"
    die "template selection required before --create"
  fi
fi

OUT_FILE="$(mktemp -t pr-body.XXXXXX.md)"
[[ -f "$DEFAULT_PR_TEMPLATE" ]] || die "missing fallback template: $DEFAULT_PR_TEMPLATE"
[[ -f "$PR_BODY_RENDERER" ]] || die "missing PR body renderer: $PR_BODY_RENDERER"

if [[ -n "$SELECTED_TEMPLATE_ID" ]]; then
  SELECTED_TEMPLATE_FILE="$(mktemp -t pr-template.XXXXXX.md)"
  printf '%s\n' "$SELECTED_TEMPLATE_CONTENT" > "$SELECTED_TEMPLATE_FILE"
  {
    if [[ "$SELECTED_TEMPLATE_SOURCE" == "remote" ]]; then
      echo "<!-- Remote PR template source: $EFFECTIVE_REPO:$SELECTED_TEMPLATE_ID -->"
    else
      echo "<!-- Local PR template source: $SELECTED_TEMPLATE_ID -->"
    fi
    echo
    python3 "$PR_BODY_RENDERER" \
      --mode augment \
      --title "$TITLE" \
      --base "$BASE" \
      --head "$HEAD" \
      --commits-file "$COMMITS_FILE" \
      --changes-file "$CHANGES_FILE" \
      --template-file "$SELECTED_TEMPLATE_FILE"
  } > "$OUT_FILE"
  rm -f "$SELECTED_TEMPLATE_FILE"
else
  python3 "$PR_BODY_RENDERER" \
    --mode fallback \
    --title "$TITLE" \
    --base "$BASE" \
    --head "$HEAD" \
    --commits-file "$COMMITS_FILE" \
    --changes-file "$CHANGES_FILE" \
    --template-file "$DEFAULT_PR_TEMPLATE" > "$OUT_FILE"
fi

echo "📝 PR body file created: $OUT_FILE"
if [[ -n "$SELECTED_TEMPLATE_ID" ]]; then
  if [[ "$SELECTED_TEMPLATE_SOURCE" == "remote" ]]; then
    echo "Template source: remote ($EFFECTIVE_REPO:$SELECTED_TEMPLATE_ID)"
  else
    echo "Template source: local ($SELECTED_TEMPLATE_ID)"
  fi
else
  echo "Template source: skill fallback template"
fi
echo "Review/edit this file as needed, then create the PR with:"
PREVIEW_ARGS=(pr create --title "$TITLE" --body-file "$OUT_FILE")
if [[ -n "$BASE" ]]; then
  PREVIEW_ARGS+=(--base "$BASE")
fi
if [[ -n "$HEAD" ]]; then
  PREVIEW_ARGS+=(--head "$HEAD")
fi
if [[ -n "$EFFECTIVE_REPO" ]]; then
  PREVIEW_ARGS+=(--repo "$EFFECTIVE_REPO")
fi
if [[ "$READY" != "true" ]]; then
  PREVIEW_ARGS+=(--draft)
fi
for label in "${LABELS[@]}"; do
  PREVIEW_ARGS+=(--label "$label")
done

PREVIEW_CMD="gh"
for arg in "${PREVIEW_ARGS[@]}"; do
  printf -v arg_quoted '%q' "$arg"
  PREVIEW_CMD+=" $arg_quoted"
done
echo "  $PREVIEW_CMD"
echo ""

if [[ "$CREATE" != "true" ]]; then
  exit 0
fi

require_cmd gh
require_cmd jq
[[ -x "$PR_LABELS_SCRIPT" ]] || die "missing helper script: $PR_LABELS_SCRIPT"

if [[ -z "$EFFECTIVE_REPO" ]]; then
  die "could not infer repo; pass --repo owner/repo"
fi

LABELS_JSON="$(bash "$PR_LABELS_SCRIPT" --repo "$EFFECTIVE_REPO" --format json)"
LABEL_COUNT="$(printf '%s' "$LABELS_JSON" | jq 'length')"

if [[ "$LABEL_COUNT" -gt 0 && "$NO_LABELS" != "true" && "${#LABELS[@]}" -eq 0 ]]; then
  echo "Label selection is required before PR creation. Available labels:"
  bash "$PR_LABELS_SCRIPT" --repo "$EFFECTIVE_REPO" --format text
  die "rerun with --label <name> (repeatable) or --no-labels"
fi

if [[ "${#LABELS[@]}" -gt 0 ]]; then
  for label in "${LABELS[@]}"; do
    MATCH="$(printf '%s' "$LABELS_JSON" | jq -r --arg n "$label" 'any(.[]?; .name == $n)')"
    if [[ "$MATCH" != "true" ]]; then
      echo "Available labels in $EFFECTIVE_REPO:"
      bash "$PR_LABELS_SCRIPT" --repo "$EFFECTIVE_REPO" --format text
      die "unknown --label '$label'"
    fi
  done
fi

ARGS=(pr create --title "$TITLE" --body-file "$OUT_FILE")

if [[ -n "$BASE" ]]; then
  ARGS+=(--base "$BASE")
fi
if [[ -n "$HEAD" ]]; then
  ARGS+=(--head "$HEAD")
fi
if [[ -n "$EFFECTIVE_REPO" ]]; then
  ARGS+=(--repo "$EFFECTIVE_REPO")
fi

if [[ "$READY" != "true" ]]; then
  ARGS+=(--draft)
fi

for label in "${LABELS[@]}"; do
  ARGS+=(--label "$label")
done

gh "${ARGS[@]}"

echo ""
echo "✅ PR created."
