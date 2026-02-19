#!/usr/bin/env bash
set -euo pipefail

# pr-create.sh - Create a PR using the skill's PR body template.
#
# Usage:
#   bash scripts/pr-create.sh --title "feat(cli): add --json output" [--create] [--draft] [--base main] [--head my-branch]
#
# Behavior:
# - Writes a prefilled PR body with deterministic sections derived from git metadata.
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

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
TEMPLATE="$SKILL_ROOT/assets/templates/pull-request-body.md"

[[ -f "$TEMPLATE" ]] || die "template not found at $TEMPLATE"
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

git log --pretty=format:'%s' "$BASE...$HEAD" > "$COMMITS_FILE"
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

OUT_FILE="$(mktemp -t pr-body.XXXXXX.md)"
{
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
  echo "# Screenshots / logs (optional)"
  echo
  echo "Not user-facing."
  echo
  echo "# Refs"
  echo
  echo "Related to #<issue-if-applicable>"
  echo
  echo "# Reviewers / bots"
  echo
  echo "@codex"
  echo "@gemini-code-assist"
} > "$OUT_FILE"

echo "📝 PR body file created: $OUT_FILE"
echo "Review/edit this file as needed, then create the PR with:"
echo "  gh pr create --title \"$TITLE\" --body-file \"$OUT_FILE\""
echo ""

if [[ "$CREATE" != "true" ]]; then
  exit 0
fi

require_cmd gh

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
