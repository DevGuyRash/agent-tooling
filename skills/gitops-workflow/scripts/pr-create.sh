#!/usr/bin/env bash
set -euo pipefail

# pr-create.sh - Create a PR using deterministic context and repository-aware defaults.
#
# Usage:
#   bash scripts/pr-create.sh --title "feat(cli): add --json output" [--create --force-create] [--ready] [--draft] [--base main] [--head my-branch] [--repo owner/repo] [--label <name> ...] [--no-labels] [--template-id <path>]
#
# Behavior:
# - Writes a prefilled PR body with deterministic sections derived from git metadata.
# - By default, does NOT create a PR; it prints the body path for human/agent review.
# - `--create` requires `--force-create` to run `gh pr create --body-file <file>`.
# - When `--create` is used, draft mode is the default; pass `--ready` to create non-draft PRs.
# - Before `--create`, labels must be explicit (`--label ...` or `--no-labels`) when labels exist.
# - For repositories with multiple remote PR templates, `--template-id` is required before `--create`.
#
# Requirements:
# - git
# - gh/jq (required only with --create)

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
  bash scripts/pr-create.sh --title "feat(cli): add --json output" [--create --force-create] [--ready] [--draft] [--base main] [--head my-branch] [--repo owner/repo] [--label <name> ...] [--no-labels] [--template-id <path>]

Behavior:
  - Writes a deterministic PR body file from git metadata by default.
  - Does not create a PR unless --create and --force-create are both provided.
  - When creating, draft is default unless --ready is provided.
  - If labels exist in the target repository, pass --label ... or --no-labels.
  - If multiple remote PR templates exist, pass --template-id <path>.
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

SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
PR_LABELS_SCRIPT="$SCRIPT_DIR/pr-labels-list.sh"
PR_TEMPLATE_SCRIPT="$SCRIPT_DIR/pr-template-discover.sh"

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

render_changes_section() {
  local count=0
  while IFS= read -r subject || [[ -n "$subject" ]]; do
    [[ -z "$subject" ]] && continue
    printf -- "- %s\n" "$subject"
    count=$((count + 1))
    if [[ "$count" -ge 12 ]]; then
      break
    fi
  done < "$COMMITS_FILE"
  if [[ "$count" -eq 0 ]]; then
    printf -- "- Changes present between %s and %s\n" "$BASE" "$HEAD"
  fi
}

render_test_commands() {
  local py_changed sh_changed
  py_changed="$(grep -E '\.py$' "$CHANGES_FILE" || true)"
  sh_changed="$(grep -E '\.sh$' "$CHANGES_FILE" || true)"

  if [[ -n "$py_changed" ]]; then
    echo "python3 -m unittest"
  fi
  if [[ -n "$sh_changed" ]]; then
    echo "bash -n scripts/*.sh"
  fi
  echo "git diff --stat \"$BASE...$HEAD\""
}

render_refs_section() {
  local refs=()
  mapfile -t refs < <(grep -Eo '#[0-9]+' "$COMMITS_FILE" | awk '!seen[$0]++' || true)

  if [[ "${#refs[@]}" -eq 0 ]]; then
    echo "- (none provided)"
    return 0
  fi

  local ref
  for ref in "${refs[@]}"; do
    echo "- Related to $ref"
  done
}

EFFECTIVE_REPO="$(resolve_repo)"
if [[ -n "$EFFECTIVE_REPO" ]]; then
  parse_repo "$EFFECTIVE_REPO" >/dev/null
fi
REMOTE_TEMPLATE_ID=""
REMOTE_TEMPLATE_CONTENT=""

if [[ -n "$TEMPLATE_ID" && -z "$EFFECTIVE_REPO" ]]; then
  die "--template-id requires --repo or an inferable gh repo context"
fi

if [[ -n "$EFFECTIVE_REPO" && -f "$PR_TEMPLATE_SCRIPT" ]]; then
  TEMPLATES_JSON=""
  if ! TEMPLATES_JSON="$(bash "$PR_TEMPLATE_SCRIPT" --repo "$EFFECTIVE_REPO" --format json)"; then
    if [[ "$CREATE" == "true" ]]; then
      die "template discovery failed for $EFFECTIVE_REPO; refusing --create"
    fi
    echo "Warning: template discovery failed for $EFFECTIVE_REPO; using deterministic fallback body." >&2
  fi
  if [[ -n "$TEMPLATES_JSON" ]] && printf '%s' "$TEMPLATES_JSON" | jq -e '.templates' >/dev/null 2>&1; then
    TEMPLATE_COUNT="$(printf '%s' "$TEMPLATES_JSON" | jq '.templates | length')"
    if [[ "$TEMPLATE_COUNT" -eq 1 ]]; then
      REMOTE_TEMPLATE_ID="$(printf '%s' "$TEMPLATES_JSON" | jq -r '.templates[0].id')"
    fi

    if [[ -n "$TEMPLATE_ID" ]]; then
      FOUND="$(printf '%s' "$TEMPLATES_JSON" | jq -r --arg id "$TEMPLATE_ID" 'any(.templates[]?; .id == $id)')"
      [[ "$FOUND" == "true" ]] || die "template id not found in $EFFECTIVE_REPO: $TEMPLATE_ID"
      REMOTE_TEMPLATE_ID="$TEMPLATE_ID"
    fi

    if [[ "$CREATE" == "true" && "$TEMPLATE_COUNT" -gt 1 && -z "$REMOTE_TEMPLATE_ID" ]]; then
      echo "Multiple remote PR templates detected. Select one with --template-id <path>."
      bash "$PR_TEMPLATE_SCRIPT" --repo "$EFFECTIVE_REPO" --format text
      die "template selection required before --create"
    fi

    if [[ -n "$REMOTE_TEMPLATE_ID" ]]; then
      REMOTE_TEMPLATE_CONTENT="$(bash "$PR_TEMPLATE_SCRIPT" --repo "$EFFECTIVE_REPO" --template-id "$REMOTE_TEMPLATE_ID")"
    fi
  fi
fi

OUT_FILE="$(mktemp -t pr-body.XXXXXX.md)"
{
  if [[ -n "$REMOTE_TEMPLATE_CONTENT" ]]; then
    echo "<!-- Remote PR template source: $EFFECTIVE_REPO:$REMOTE_TEMPLATE_ID -->"
    echo
    printf '%s\n' "$REMOTE_TEMPLATE_CONTENT"
  else
    echo "# Summary"
    echo
    echo "This PR introduces changes from \`$HEAD\` into \`$BASE\` for: $TITLE."
    echo "It is prefilled from git history to avoid empty PR sections and improve reviewer context."
    echo
    echo "# Changes"
    echo
    render_changes_section
    echo
    echo "# Testing"
    echo
    echo "- [x] Unit tests"
    echo "- [ ] Integration tests"
    echo "- [x] Manual testing"
    echo
    echo "Describe how you tested:"
    echo
    echo '```bash'
    render_test_commands
    echo '```'
    echo
    echo "# Risk"
    echo
    echo "- Breaking changes? **No**"
    echo "- Rollback plan (if risky): Revert the PR merge commit."
    echo
    echo "# Refs"
    echo
    render_refs_section
    echo
    echo "# Reviewers / bots"
    echo
    echo "@codex review"
    echo "/gemini review"
  fi
} > "$OUT_FILE"

echo "📝 PR body file created: $OUT_FILE"
if [[ -n "$REMOTE_TEMPLATE_ID" ]]; then
  echo "Template source: remote ($EFFECTIVE_REPO:$REMOTE_TEMPLATE_ID)"
else
  echo "Template source: local deterministic defaults"
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

if [[ "$FORCE_CREATE" != "true" ]]; then
  die "--create requires --force-create to avoid accidental PR creation"
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
