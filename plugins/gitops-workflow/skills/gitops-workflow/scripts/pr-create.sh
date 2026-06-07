#!/usr/bin/env bash
# gitops-catalog: {"id":"pr-create","topic":"pr","command":"create pr","phrases":["create pr","open pr"],"summary":"Prepare deterministic PR metadata and create a PR when explicitly requested.","script":"pr-create.sh","creates_branch":false,"creates_worktree":false,"creates_pr":true,"mutates_history":false,"stays_on_current_branch":true,"supports_json":false}
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
PR_TEMPLATE_SELECTION="$SCRIPT_DIR/lib/pr_template_selection.py"
DEFAULT_PR_TEMPLATE="$SKILL_ROOT/assets/templates/pull-request-body.md"
SKILLS_FILE_ROOT="<skills-file-root>"
HAVE_PYTHON3="false"
CC_HEADER_RE='^([a-z]+)(\(([^)]+)\))?(!)?:[[:space:]](.+)$'

require_cmd git

if command -v python3 >/dev/null 2>&1 && python3 -V >/dev/null 2>&1; then
  HAVE_PYTHON3="true"
fi

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

resolve_checkout_repo() {
  resolve_checkout_repo_slug
}

select_template_from_json() {
  local requested_id="${1:-}"
  local templates_json="${2:-}"
  python3 "$PR_TEMPLATE_SELECTION" "$requested_id" "$templates_json"
}

resolve_remote_default_branch() {
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

collect_local_template_records() {
  local root="$1"
  local tmp_file="$2"
  local path=""

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

collect_remote_template_records() {
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

sort_unique_template_records() {
  local input_file="$1"
  local output_file="$2"
  if [[ -s "$input_file" ]]; then
    sort -u "$input_file" > "$output_file"
  else
    : > "$output_file"
  fi
}

dedupe_template_records() {
  local input_file="$1"
  local output_file="$2"

  awk -F '\t' '
    {
      source=$1
      path=$2
      current=$0
      if (!(path in order)) {
        order[path]=++count
        records[path]=current
      } else if (source == "local") {
        split(records[path], fields, "\t")
        if (fields[1] != "local") {
          records[path]=current
        }
      }
    }
    END {
      for (i = 1; i <= count; i++) {
        for (path in order) {
          if (order[path] == i) {
            print records[path]
            break
          }
        }
      }
    }
  ' "$input_file" > "$output_file"
}

print_template_records_text() {
  local records_file="$1"
  local count="0"

  echo "Repo: ${EFFECTIVE_REPO:-(none)}"
  echo "Ref:  ${DEFAULT_BRANCH:-(local checkout)}"
  count="$(sed -n '/./p' "$records_file" | wc -l | tr -d ' ')"
  echo "Templates: $count"
  if [[ "$count" -eq 0 ]]; then
    echo "- (none)"
    return 0
  fi
  awk -F '\t' '{printf("- %s (%s)\n", $3, $2)}' "$records_file"
}

print_discovered_template_choices() {
  local records_file="$1"
  local deduped_file=""

  [[ -n "$records_file" && -f "$records_file" ]] || return 1
  deduped_file="$(mktemp -t pr-template-print.XXXXXX)"
  dedupe_template_records "$records_file" "$deduped_file"
  print_template_records_text "$deduped_file"
  rm -f "$deduped_file"
}

select_template_from_records() {
  local requested_id="$1"
  local records_file="$2"
  local deduped_file=""
  local exact=""
  local path_matches=""
  local path_match_count="0"
  local selected=""
  local selection_status=0

  deduped_file="$(mktemp -t pr-template-deduped.XXXXXX)"
  dedupe_template_records "$records_file" "$deduped_file"
  TEMPLATE_COUNT="$(sed -n '/./p' "$deduped_file" | wc -l | tr -d ' ')"
  SELECTED_TEMPLATE_ID=""
  SELECTED_TEMPLATE_SOURCE=""
  SELECTED_TEMPLATE_CONTENT=""

  if [[ -n "$requested_id" ]]; then
    exact="$(awk -F '\t' -v want="$requested_id" '$3 == want { print $0; exit }' "$records_file")"
    if [[ -n "$exact" ]]; then
      selected="$exact"
    else
      path_matches="$(awk -F '\t' -v want="$requested_id" '$2 == want { print $0 }' "$deduped_file")"
      path_match_count="$(printf '%s\n' "$path_matches" | sed '/^$/d' | wc -l | tr -d ' ')"
      if [[ "$path_match_count" == "1" ]]; then
        selected="$(printf '%s\n' "$path_matches" | sed -n '1p')"
      else
        LAST_TEMPLATE_SELECTION_ERROR="template id not found in discovered templates: $requested_id"
        rm -f "$deduped_file"
        return 3
      fi
    fi
  elif [[ "$TEMPLATE_COUNT" == "1" ]]; then
    selected="$(sed -n '1p' "$deduped_file")"
  else
    selected="$(awk -F '\t' '$1 == "local" { print $0; exit }' "$deduped_file")"
  fi

  if [[ -n "$selected" ]]; then
    IFS=$'\t' read -r _selected_source _selected_path _selected_id <<< "$selected"
    SELECTED_TEMPLATE_ID="${_selected_id:-}"
    SELECTED_TEMPLATE_SOURCE="${_selected_source:-}"
  fi
  rm -f "$deduped_file"
  return "$selection_status"
}

load_selected_template_from_records() {
  local records_file="$1"
  local discovery_mode="$2"
  local template_fetch_args=()
  local template_fetch_error=""
  local selection_status=0
  local fetch_message=""

  if select_template_from_records "$TEMPLATE_ID" "$records_file"; then
    :
  else
    selection_status=$?
    if [[ "$selection_status" -eq 3 && -n "$EFFECTIVE_REPO" && "$discovery_mode" == "local-only" ]]; then
      return 10
    fi
    if [[ "$CREATE" == "true" || -n "$TEMPLATE_ID" ]]; then
      die "${LAST_TEMPLATE_SELECTION_ERROR:-template selection failed}"
    fi
    echo "Warning: ${LAST_TEMPLATE_SELECTION_ERROR:-template selection failed}; using skill fallback template." >&2
    return 1
  fi

  if [[ -z "$SELECTED_TEMPLATE_ID" ]]; then
    return 0
  fi

  template_fetch_args=(--template-id "$SELECTED_TEMPLATE_ID")
  if [[ "$SELECTED_TEMPLATE_SOURCE" == "local" ]]; then
    template_fetch_args=(--local-only --template-id "$SELECTED_TEMPLATE_ID")
  elif [[ -n "$EFFECTIVE_REPO" ]]; then
    template_fetch_args=(--repo "$EFFECTIVE_REPO" --template-id "$SELECTED_TEMPLATE_ID")
  fi

  template_fetch_error="$(mktemp -t pr-template-fetch.XXXXXX.err)"
  if SELECTED_TEMPLATE_CONTENT="$(bash "$PR_TEMPLATE_SCRIPT" "${template_fetch_args[@]}" 2>"$template_fetch_error")"; then
    rm -f "$template_fetch_error"
    return 0
  fi

  fetch_message="$(tr '\n' ' ' < "$template_fetch_error" | sed 's/[[:space:]]\+/ /g; s/^ //; s/ $//')"
  rm -f "$template_fetch_error"
  LAST_TEMPLATE_SELECTION_ERROR="${fetch_message:-failed to load template content: $SELECTED_TEMPLATE_ID}"
  SELECTED_TEMPLATE_CONTENT=""
  if [[ "$CREATE" == "true" || -n "$TEMPLATE_ID" ]]; then
    die "${LAST_TEMPLATE_SELECTION_ERROR}"
  fi
  echo "Warning: ${LAST_TEMPLATE_SELECTION_ERROR}; using skill fallback template." >&2
  return 1
}

discover_shell_template_records() {
  local mode="$1"
  local output_file="$2"
  local local_root=""
  local raw_file=""
  local owner=""
  local name=""
  local missing_remote_dependency=""

  raw_file="$(mktemp -t pr-template-records.XXXXXX)"
  : > "$raw_file"

  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    local_root="$(git rev-parse --show-toplevel)"
    if [[ "$mode" == "local-only" || -z "$REPO" || ( -n "$CHECKOUT_REPO" && "$CHECKOUT_REPO" == "$EFFECTIVE_REPO" ) ]]; then
      collect_local_template_records "$local_root" "$raw_file"
    fi
  fi

  DEFAULT_BRANCH=""
  if [[ "$mode" != "local-only" && -n "$EFFECTIVE_REPO" ]]; then
    IFS=$'\t' read -r owner name <<< "$(parse_repo "$EFFECTIVE_REPO")"
    if ! command -v gh >/dev/null 2>&1; then
      missing_remote_dependency="gh"
    elif ! command -v jq >/dev/null 2>&1; then
      missing_remote_dependency="jq"
    fi

    if [[ -n "$missing_remote_dependency" ]]; then
      if [[ ! -s "$raw_file" ]]; then
        rm -f "$raw_file"
        LAST_TEMPLATE_SELECTION_ERROR="missing required command: $missing_remote_dependency"
        return 2
      fi
      echo "Warning: continuing with local PR templates only for $EFFECTIVE_REPO (missing required command: $missing_remote_dependency)." >&2
    elif DEFAULT_BRANCH="$(resolve_remote_default_branch "$EFFECTIVE_REPO")"; then
      collect_remote_template_records "$owner" "$name" "$DEFAULT_BRANCH" "$raw_file"
    elif [[ ! -s "$raw_file" ]]; then
      rm -f "$raw_file"
      return 2
    else
      echo "Warning: continuing with local PR templates only for $EFFECTIVE_REPO." >&2
    fi
  fi

  sort_unique_template_records "$raw_file" "$output_file"
  rm -f "$raw_file"
  return 0
}

append_unique() {
  local value="$1"
  shift
  local item=""
  for item in "$@"; do
    if [[ "$item" == "$value" ]]; then
      return 1
    fi
  done
  return 0
}

join_by() {
  local delimiter="$1"
  shift
  local first="true"
  local value=""

  for value in "$@"; do
    if [[ "$first" == "true" ]]; then
      printf '%s' "$value"
      first="false"
    else
      printf '%s%s' "$delimiter" "$value"
    fi
  done
}

render_verification_path() {
  local path="$1"
  if [[ "$path" == plugins/gitops-workflow/skills/gitops-workflow/* ]]; then
    printf '%s/%s\n' "$SKILLS_FILE_ROOT" "${path#plugins/gitops-workflow/skills/gitops-workflow/}"
    return 0
  fi
  printf '%s\n' "$path"
}

build_shell_render_data() {
  COMMIT_LINES=()
  CHANGED_FILES=()
  FEATURES=()
  FIXES=()
  OTHER_CHANGES=()
  AREA_BUCKETS=()
  REVIEW_LINES=()
  TEST_COMMANDS=()
  REFS_LINES=()
  BREAKING_CHANGE="false"

  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -n "$line" ]] || continue
    COMMIT_LINES+=("$line")
  done < "$COMMITS_FILE"

  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -n "$line" ]] || continue
    CHANGED_FILES+=("$line")
  done < "$CHANGES_FILE"

  local path=""
  for path in "${CHANGED_FILES[@]}"; do
    if [[ "$path" == skills/* || "$path" == plugins/*/skills/* ]]; then
      if append_unique "skill behavior" "${AREA_BUCKETS[@]}"; then
        AREA_BUCKETS+=("skill behavior")
      fi
    fi
    if [[ "$path" == scripts/* || "$path" == */scripts/* ]]; then
      if append_unique "automation scripts" "${AREA_BUCKETS[@]}"; then
        AREA_BUCKETS+=("automation scripts")
      fi
    fi
    if [[ "$path" == tests/* || "$path" == */tests/* ]]; then
      if append_unique "test coverage" "${AREA_BUCKETS[@]}"; then
        AREA_BUCKETS+=("test coverage")
      fi
    fi
    if [[ "$path" == *.md ]]; then
      if append_unique "documentation" "${AREA_BUCKETS[@]}"; then
        AREA_BUCKETS+=("documentation")
      fi
    fi
  done
  if [[ "${#AREA_BUCKETS[@]}" -eq 0 ]]; then
    AREA_BUCKETS+=("repository files")
  elif [[ "${#AREA_BUCKETS[@]}" -gt 3 ]]; then
    AREA_BUCKETS=("${AREA_BUCKETS[@]:0:3}")
  fi

  local subject=""
  local typ=""
  local scope=""
  local desc=""
  local bullet=""
  for subject in "${COMMIT_LINES[@]}"; do
    if [[ "$subject" =~ $CC_HEADER_RE ]]; then
      typ="${BASH_REMATCH[1]}"
      scope="${BASH_REMATCH[3]:-}"
      desc="${BASH_REMATCH[5]}"
      case "$typ" in
        feat|fix|docs|refactor|test|chore|perf|ci|build|style|deps|security|revert|hotfix)
          bullet="$desc"
          if [[ -n "$scope" ]]; then
            bullet="$scope: $desc"
          fi
          case "$typ" in
            feat)
              FEATURES+=("$bullet")
              ;;
            fix|hotfix)
              FIXES+=("$bullet")
              ;;
            *)
              OTHER_CHANGES+=("$bullet")
              ;;
          esac
          if [[ -n "${BASH_REMATCH[4]:-}" ]]; then
            BREAKING_CHANGE="true"
          fi
          ;;
        *)
          OTHER_CHANGES+=("$subject")
          ;;
      esac
    else
      OTHER_CHANGES+=("$subject")
    fi
  done

  local review_added="false"
  for path in "${CHANGED_FILES[@]}"; do
    if [[ "$path" == scripts/* || "$path" == */scripts/* ]]; then
      REVIEW_LINES+=("- Validate CLI flow changes, especially template selection and body rendering behavior.")
      review_added="true"
      break
    fi
  done
  for path in "${CHANGED_FILES[@]}"; do
    if [[ "$path" == tests/* || "$path" == */tests/* ]]; then
      REVIEW_LINES+=("- Confirm automated coverage matches the new create/discovery behavior and edge cases.")
      review_added="true"
      break
    fi
  done
  for path in "${CHANGED_FILES[@]}"; do
    if [[ "$path" == *.md ]]; then
      REVIEW_LINES+=("- Check docs and templates for wording drift against the implemented behavior.")
      review_added="true"
      break
    fi
  done
  if [[ "$review_added" != "true" ]]; then
    REVIEW_LINES+=("- Focus review on the changed files and generated PR body output.")
  fi

  local python_files=()
  local shell_files=()
  for path in "${CHANGED_FILES[@]}"; do
    if [[ "$path" == *.py ]]; then
      python_files+=("$path")
    fi
    if [[ "$path" == *.sh ]]; then
      shell_files+=("$path")
    fi
  done
  for subject in "${COMMIT_LINES[@]}"; do
    local ref=""
    while IFS= read -r ref; do
      [[ -n "$ref" ]] || continue
      ref="- Related to $ref"
      if append_unique "$ref" "${REFS_LINES[@]}"; then
        REFS_LINES+=("$ref")
      fi
    done < <(grep -oE '#[0-9]+' <<< "$subject" || true)
  done
  if [[ "${#REFS_LINES[@]}" -eq 0 ]]; then
    REFS_LINES+=("- (none provided)")
  fi

  local any_gitops_python="false"
  local any_gitops_shell="false"
  for path in "${python_files[@]}"; do
    if [[ "$path" == plugins/gitops-workflow/skills/gitops-workflow/* ]]; then
      any_gitops_python="true"
      break
    fi
  done
  for path in "${shell_files[@]}"; do
    if [[ "$path" == plugins/gitops-workflow/skills/gitops-workflow/* ]]; then
      any_gitops_shell="true"
      break
    fi
  done
  if [[ "${#python_files[@]}" -gt 0 ]]; then
    if [[ "$any_gitops_python" == "true" ]]; then
      TEST_COMMANDS+=("python3 -m unittest $SKILLS_FILE_ROOT/tests/test_pr_template_discover.py $SKILLS_FILE_ROOT/tests/test_pr_create.py")
    else
      local rendered_paths=()
      for path in "${python_files[@]:0:8}"; do
        rendered_paths+=("$(render_verification_path "$path")")
      done
      TEST_COMMANDS+=("python3 -m py_compile $(join_by " " "${rendered_paths[@]}")")
    fi
  fi
  if [[ "${#shell_files[@]}" -gt 0 ]]; then
    if [[ "$any_gitops_shell" == "true" ]]; then
      TEST_COMMANDS+=("bash -n $SKILLS_FILE_ROOT/scripts/*.sh")
    else
      local rendered_shells=()
      for path in "${shell_files[@]:0:8}"; do
        rendered_shells+=("$(render_verification_path "$path")")
      done
      TEST_COMMANDS+=("bash -n $(join_by " " "${rendered_shells[@]}")")
    fi
  fi
  TEST_COMMANDS+=("git diff --stat \"$BASE...$HEAD\"")
}

build_summary_text() {
  local areas impact_bits=()
  areas="$(join_by ", " "${AREA_BUCKETS[@]}")"
  if [[ "${#FEATURES[@]}" -gt 0 ]]; then
    impact_bits+=("${#FEATURES[@]} feature-oriented change(s)")
  fi
  if [[ "${#FIXES[@]}" -gt 0 ]]; then
    impact_bits+=("${#FIXES[@]} fix(es)")
  fi
  if [[ "${#OTHER_CHANGES[@]}" -gt 0 ]]; then
    impact_bits+=("${#OTHER_CHANGES[@]} supporting update(s)")
  fi
  if [[ "${#impact_bits[@]}" -eq 0 ]]; then
    impact_bits+=("targeted branch updates")
  fi
  printf 'This PR brings `%s` into `%s` for `%s`. It primarily touches %s and packages %s for review.' \
    "$HEAD" "$BASE" "$TITLE" "$areas" "$(join_by ", " "${impact_bits[@]}")"
}

build_changes_text() {
  local out_file="$1"
  : > "$out_file"
  {
    echo "### Affected Areas"
    echo
    local area=""
    for area in "${AREA_BUCKETS[@]}"; do
      echo "- $area"
    done
    echo
    local item=""
    if [[ "${#FEATURES[@]}" -gt 0 ]]; then
      echo "### Features"
      echo
      for item in "${FEATURES[@]}"; do
        echo "- $item"
      done
      echo
    fi
    if [[ "${#FIXES[@]}" -gt 0 ]]; then
      echo "### Fixes"
      echo
      for item in "${FIXES[@]}"; do
        echo "- $item"
      done
      echo
    fi
    if [[ "${#OTHER_CHANGES[@]}" -gt 0 ]]; then
      echo "### Other Changes"
      echo
      for item in "${OTHER_CHANGES[@]}"; do
        echo "- $item"
      done
      echo
    fi
    if [[ "${#FEATURES[@]}" -eq 0 && "${#FIXES[@]}" -eq 0 && "${#OTHER_CHANGES[@]}" -eq 0 ]]; then
      echo "- Review the branch diff; no categorized commit summaries were available."
      echo
    fi
  } >> "$out_file"
}

build_risk_text() {
  printf '%s\n%s\n%s\n' \
    "- Breaking changes? **$( [[ "$BREAKING_CHANGE" == "true" ]] && printf 'Yes' || printf 'No' )**" \
    "- Rollout / monitoring:" \
    "- Rollback plan: revert the PR merge commit if follow-up fixes are not sufficient."
}

emit_file_contents() {
  local path="$1"
  if [[ -s "$path" ]]; then
    sed '$d' "$path" 2>/dev/null || true
    tail -n 1 "$path" 2>/dev/null || true
  fi
}

render_fallback_template_shell() {
  local template_file="$1"
  local summary="$2"
  local changes_file="$3"
  local risk_text="$4"
  local template_text=""
  local changes_text=""
  local review_text=""
  local test_commands_text=""
  local refs_text=""
  local rendered=""
  local shell_extglob_was_set="false"

  template_text="$(cat "$template_file")"
  changes_text="$(emit_file_contents "$changes_file")"
  review_text="$(printf '%s\n' "${REVIEW_LINES[@]}")"
  test_commands_text="$(printf '%s\n' "${TEST_COMMANDS[@]}")"
  refs_text="$(printf '%s\n' "${REFS_LINES[@]}")"

  rendered="${template_text//<!-- SUMMARY_PLACEHOLDER -->/$summary}"
  rendered="${rendered//<!-- CHANGES_PLACEHOLDER -->/$changes_text}"
  rendered="${rendered//<!-- REVIEW_FOCUS_PLACEHOLDER -->/$review_text}"
  rendered="${rendered//<!-- TEST_COMMANDS_PLACEHOLDER -->/$test_commands_text}"
  rendered="${rendered//<!-- RISK_PLACEHOLDER -->/$risk_text}"
  rendered="${rendered//<!-- REFS_PLACEHOLDER -->/$refs_text}"

  if shopt -q extglob; then
    shell_extglob_was_set="true"
  else
    shopt -s extglob
  fi
  rendered="${rendered%%+([[:space:]])}"
  if [[ "$shell_extglob_was_set" != "true" ]]; then
    shopt -u extglob
  fi

  printf '%s\n' "$rendered"
}

split_trailing_trigger_block_shell() {
  local template_file="$1"
  local prefix_file="$2"
  local suffix_file="$3"
  local lines=()
  local line=""
  local end=0
  local start=0
  local idx=0

  while IFS= read -r line || [[ -n "$line" ]]; do
    lines+=("$line")
  done < "$template_file"

  end="${#lines[@]}"
  while (( end > 0 )); do
    if [[ -n "${lines[end-1]//[[:space:]]/}" ]]; then
      break
    fi
    ((end--))
  done

  start="$end"
  while (( start > 0 )); do
    if [[ "${lines[start-1]}" =~ ^[[:space:]]*([@/])[^[:space:]] ]]; then
      ((start--))
    else
      break
    fi
  done

  : > "$prefix_file"
  : > "$suffix_file"
  if (( start == end )); then
    for ((idx=0; idx<end; idx++)); do
      printf '%s\n' "${lines[idx]}" >> "$prefix_file"
    done
    return 0
  fi

  for ((idx=0; idx<start; idx++)); do
    printf '%s\n' "${lines[idx]}" >> "$prefix_file"
  done
  for ((idx=start; idx<end; idx++)); do
    printf '%s\n' "${lines[idx]}" >> "$suffix_file"
  done
}

render_pr_body_shell() {
  local mode="$1"
  local template_file="$2"
  local output_file="$3"
  local summary=""
  local risk_text=""
  local changes_text_file=""
  local prefix_file=""
  local suffix_file=""
  local marker=""

  build_shell_render_data
  summary="$(build_summary_text)"
  risk_text="$(build_risk_text)"
  changes_text_file="$(mktemp -t pr-changes-rendered.XXXXXX)"
  build_changes_text "$changes_text_file"

  if grep -q '<!-- SUMMARY_PLACEHOLDER -->\|<!-- CHANGES_PLACEHOLDER -->\|<!-- REVIEW_FOCUS_PLACEHOLDER -->\|<!-- TEST_COMMANDS_PLACEHOLDER -->\|<!-- RISK_PLACEHOLDER -->\|<!-- REFS_PLACEHOLDER -->' "$template_file"; then
    render_fallback_template_shell "$template_file" "$summary" "$changes_text_file" "$risk_text" > "$output_file"
    rm -f "$changes_text_file"
    return 0
  fi

  if [[ "$mode" == "fallback" ]]; then
    render_fallback_template_shell "$DEFAULT_PR_TEMPLATE" "$summary" "$changes_text_file" "$risk_text" > "$output_file"
    rm -f "$changes_text_file"
    return 0
  fi

  prefix_file="$(mktemp -t pr-template-prefix.XXXXXX)"
  suffix_file="$(mktemp -t pr-template-suffix.XXXXXX)"
  split_trailing_trigger_block_shell "$template_file" "$prefix_file" "$suffix_file"
  marker="---"

  {
    if [[ -s "$prefix_file" ]]; then
      cat "$prefix_file"
    fi
    echo
    echo "$marker"
    echo
    echo "## Generated Review Context"
    echo
    echo "### Summary"
    echo
    echo "$summary"
    echo
    echo "### Changes"
    echo
    cat "$changes_text_file"
    echo
    echo "### Review Focus"
    echo
    printf '%s\n' "${REVIEW_LINES[@]}"
    echo
    echo "### Testing"
    echo
    echo '```bash'
    printf '%s\n' "${TEST_COMMANDS[@]}"
    echo '```'
    echo
    echo "### Risks / rollout"
    echo
    printf '%s\n' "$risk_text"
    echo
    echo "### Refs"
    echo
    printf '%s\n' "${REFS_LINES[@]}"
    if [[ -s "$suffix_file" ]]; then
      echo
      cat "$suffix_file"
    fi
  } > "$output_file"

  rm -f "$changes_text_file" "$prefix_file" "$suffix_file"
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
      # Special exit code: explicit template selection missed during local-only
      # discovery, so the caller should retry with repository-aware discovery.
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
  if [[ "$selected_source" == "local" ]]; then
    template_fetch_args=(--local-only --template-id "$selected_id")
  elif [[ "$discovery_mode" == "repo-aware" && -n "$EFFECTIVE_REPO" ]]; then
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
CHECKOUT_REPO="$(resolve_checkout_repo)"
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

  if [[ "$HAVE_PYTHON3" == "true" ]]; then
    if [[ -z "$REPO" || ( -n "$CHECKOUT_REPO" && "$CHECKOUT_REPO" == "$EFFECTIVE_REPO" ) ]]; then
      LOCAL_TEMPLATES_JSON=""
      LOCAL_TEMPLATES_ERROR="$(mktemp -t pr-template-local-discover.XXXXXX.err)"
      if LOCAL_TEMPLATES_JSON="$(bash "$PR_TEMPLATE_SCRIPT" --local-only --format json 2>"$LOCAL_TEMPLATES_ERROR")"; then
        if [[ -s "$LOCAL_TEMPLATES_ERROR" ]]; then
          cat "$LOCAL_TEMPLATES_ERROR" >&2
        fi
        if load_selected_template "$LOCAL_TEMPLATES_JSON" "local-only"; then
          :
        elif [[ $? -eq 10 ]]; then
          SELECTED_TEMPLATE_ID=""
          SELECTED_TEMPLATE_SOURCE=""
          SELECTED_TEMPLATE_CONTENT=""
        fi
      else
        LOCAL_DISCOVERY_MESSAGE="$(tr '\n' ' ' < "$LOCAL_TEMPLATES_ERROR" | sed 's/[[:space:]]\+/ /g; s/^ //; s/ $//')"
        if [[ -n "$LOCAL_DISCOVERY_MESSAGE" ]]; then
          echo "Warning: local template discovery failed: $LOCAL_DISCOVERY_MESSAGE" >&2
        fi
      fi
      rm -f "$LOCAL_TEMPLATES_ERROR"
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
        if load_selected_template "$TEMPLATES_JSON" "repo-aware"; then
          :
        fi
      fi
    fi
  else
    if [[ -z "$REPO" || ( -n "$CHECKOUT_REPO" && "$CHECKOUT_REPO" == "$EFFECTIVE_REPO" ) ]]; then
      LOCAL_TEMPLATE_RECORDS="$(mktemp -t pr-template-local-records.XXXXXX)"
      if discover_shell_template_records "local-only" "$LOCAL_TEMPLATE_RECORDS"; then
        if load_selected_template_from_records "$LOCAL_TEMPLATE_RECORDS" "local-only"; then
          :
        elif [[ $? -eq 10 ]]; then
          SELECTED_TEMPLATE_ID=""
          SELECTED_TEMPLATE_SOURCE=""
          SELECTED_TEMPLATE_CONTENT=""
        fi
      fi
    fi

    if [[ -z "$SELECTED_TEMPLATE_ID" ]]; then
      ALL_TEMPLATE_RECORDS="$(mktemp -t pr-template-records-all.XXXXXX)"
      if ! discover_shell_template_records "repo-aware" "$ALL_TEMPLATE_RECORDS"; then
        if [[ "$CREATE" == "true" ]]; then
          die "template discovery failed${EFFECTIVE_REPO:+ for $EFFECTIVE_REPO}; refusing --create"
        fi
        echo "Warning: template discovery failed${EFFECTIVE_REPO:+ for $EFFECTIVE_REPO}; using skill fallback template." >&2
      else
        if load_selected_template_from_records "$ALL_TEMPLATE_RECORDS" "repo-aware"; then
          :
        fi
      fi
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
    if [[ "$HAVE_PYTHON3" == "true" ]]; then
      bash "$PR_TEMPLATE_SCRIPT" "${TEMPLATE_DISCOVER_TEXT_ARGS[@]}"
    elif ! print_discovered_template_choices "${ALL_TEMPLATE_RECORDS:-}"; then
      print_discovered_template_choices "${LOCAL_TEMPLATE_RECORDS:-}" || true
    fi
    die "template selection required before --create"
  fi
fi

OUT_FILE="$(mktemp -t pr-body.XXXXXX.md)"
[[ -f "$DEFAULT_PR_TEMPLATE" ]] || die "missing fallback template: $DEFAULT_PR_TEMPLATE"
if [[ "$HAVE_PYTHON3" == "true" ]]; then
  [[ -f "$PR_BODY_RENDERER" ]] || die "missing PR body renderer: $PR_BODY_RENDERER"
fi

if [[ -n "$SELECTED_TEMPLATE_ID" ]]; then
  SELECTED_TEMPLATE_FILE="$(mktemp -t pr-template.XXXXXX.md)"
  printf '%s\n' "$SELECTED_TEMPLATE_CONTENT" > "$SELECTED_TEMPLATE_FILE"
  if [[ "$HAVE_PYTHON3" == "true" ]]; then
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
  else
    {
      if [[ "$SELECTED_TEMPLATE_SOURCE" == "remote" ]]; then
        echo "<!-- Remote PR template source: $EFFECTIVE_REPO:$SELECTED_TEMPLATE_ID -->"
      else
        echo "<!-- Local PR template source: $SELECTED_TEMPLATE_ID -->"
      fi
      echo
      RENDERED_TEMPLATE_FILE="$(mktemp -t pr-rendered-template.XXXXXX.md)"
      render_pr_body_shell "augment" "$SELECTED_TEMPLATE_FILE" "$RENDERED_TEMPLATE_FILE"
      cat "$RENDERED_TEMPLATE_FILE"
      rm -f "$RENDERED_TEMPLATE_FILE"
    } > "$OUT_FILE"
  fi
  rm -f "$SELECTED_TEMPLATE_FILE"
else
  if [[ "$HAVE_PYTHON3" == "true" ]]; then
    python3 "$PR_BODY_RENDERER" \
      --mode fallback \
      --title "$TITLE" \
      --base "$BASE" \
      --head "$HEAD" \
      --commits-file "$COMMITS_FILE" \
      --changes-file "$CHANGES_FILE" \
      --template-file "$DEFAULT_PR_TEMPLATE" > "$OUT_FILE"
  else
    render_pr_body_shell "fallback" "$DEFAULT_PR_TEMPLATE" "$OUT_FILE"
  fi
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
