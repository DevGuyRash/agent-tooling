#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"

JSON="false"
VERBOSE="false"
TOPIC="all"

print_help() {
  cat <<'USAGE'
Usage:
  bash scripts/gitops-help.sh [--json] [--verbose] [--topic <ship|sync|doctor|branch|pr|issue|governance|all>]

Behavior:
  - Prints a consolidated GitOps command catalog without mutating repository state.
  - Default output is summary-first for humans.
  - `--json` emits a stable machine-readable catalog for agents and wrappers.
  - `--verbose` appends detailed help blocks for the relevant backing scripts.
  - `--topic` narrows the catalog to a single command family.

Options:
  --json                 Emit machine-readable JSON.
  --verbose              Append detailed per-script help sections.
  --topic <name>         Limit output to one topic.
  -h, --help             Show help.
USAGE
}

require_topic() {
  case "${1:-all}" in
    all|ship|sync|doctor|branch|pr|issue|governance)
      ;;
    *)
      echo "Error: invalid --topic '${1:-}' (expected: ship, sync, doctor, branch, pr, issue, governance, or all)" >&2
      exit 1
      ;;
  esac
}

usage_line_for_script() {
  local file="$1"
  awk '
    BEGIN { found = 0 }
    /^# Usage:/ { found = 1; next }
    /^[[:space:]]*Usage:[[:space:]]*$/ { found = 1; next }
    found {
      if ($0 ~ /^[[:space:]]*$/) next
      line = $0
      sub(/^[[:space:]]*#?[[:space:]]*/, "", line)
      print line
      exit
    }
  ' "$file"
}

detail_text_for_script() {
  local rel="$1"
  local abs="$SCRIPT_DIR/$rel"
  local output=""
  if output="$(bash "$abs" --help 2>/dev/null)" && [[ -n "$output" ]]; then
    printf '%s\n' "$output"
    return 0
  fi

  local usage=""
  usage="$(usage_line_for_script "$abs")"
  if [[ -n "$usage" ]]; then
    printf 'Usage:\n  %s\n' "$usage"
    return 0
  fi
  printf 'Usage:\n  (no help text available)\n'
}

topic_label() {
  case "$1" in
    ship) echo "Ship Workflows" ;;
    sync) echo "Sync Workflows" ;;
    doctor) echo "Doctor Workflows" ;;
    branch) echo "Branch / Worktree" ;;
    pr) echo "Pull Requests" ;;
    issue) echo "Issues" ;;
    governance) echo "Governance" ;;
    *) echo "All Topics" ;;
  esac
}

entries_data() {
  cat <<'EOF'
ship-normal|ship|ship|ship|Sync current scope, move non-raw work into the branch/worktree flow, push, and stop at a draft PR.|ship.sh|true|true|true|true|false|true|ship.sh
ship-raw|ship|ship raw|ship raw,commit and push raw,push raw,raw push|Stay on the current branch, sync in place, batch Conventional Commits, and push.|ship.sh|false|false|false|true|true|true|ship.sh
ship-sync|ship|ship sync|ship sync|Run sync-only mode on the current branch and stop before commit, push, or PR stages.|ship.sh|false|false|false|true|true|true|ship.sh
ship-ready|ship|ship ready|ship ready,readiness check|Audit current-branch PR readiness without creating or mutating a PR.|ship.sh|false|false|false|true|true|true|ship.sh
sync-raw|sync|sync raw|sync raw,raw sync|Run bidirectional in-place branch sync across the current repo or related tree.|sync-raw.sh|false|false|false|true|true|true|sync-raw.sh
doctor|doctor|doctor|doctor|Report repo and related-tree health without creating commits, pushes, or PRs.|doctor.sh|false|false|false|false|true|true|doctor.sh
doctor-fix|doctor|doctor fix|doctor fix|Apply safe recovery and sync, then report remaining reconciliation work without commit, push, or PR mutations.|doctor.sh|false|false|false|true|true|true|doctor.sh
start-work|branch|start work|start work,start branch,new branch,new worktree|Create or adopt a work branch with a linked worktree by default.|start-branch.sh|true|true|false|false|false|true|start-branch.sh
continue-worktree|branch|continue worktree|continue worktree,adopt worktree,ensure worktree|Adopt the linked worktree for an existing non-raw feature branch.|ensure-worktree.sh|false|true|false|false|false|true|ensure-worktree.sh
pr-create|pr|create pr|create pr,open pr|Prepare deterministic PR metadata and create a PR when explicitly requested.|pr-create.sh|false|false|true|false|true|false|pr-create.sh
pr-update|pr|update pr body|update pr body,edit pr body|Update an existing PR body using deterministic body-file-safe flow.|pr-update-body.sh|false|false|false|false|true|false|pr-update-body.sh
pr-ready|pr|mark pr ready|mark pr ready,pr ready|Run strict readiness gates before moving a draft PR to ready.|pr-mark-ready.sh|false|false|false|false|true|false|pr-mark-ready.sh
issue-create|issue|create issue|create issue,open issue|Create deterministic GitHub issues from body-file-safe flows.|issue-create.sh|false|false|false|false|true|false|issue-create.sh
governance-check|governance|governance check|governance check,gh scope check|Check GitHub governance capabilities before applying policy changes.|gh-scope-check.sh|false|false|false|false|true|true|gh-scope-check.sh
governance-apply|governance|governance apply|governance apply,enforce governance|Run deterministic governance reconciliation in validate -> plan -> apply -> audit order.|governance-enforce.sh|false|false|false|false|true|false|governance-enforce.sh
EOF
}

details_scripts_for_topic() {
  case "$1" in
    ship) printf '%s\n' ship.sh ;;
    sync) printf '%s\n' sync-raw.sh ;;
    doctor) printf '%s\n' doctor.sh ;;
    branch) printf '%s\n' start-branch.sh ensure-worktree.sh ;;
    pr) printf '%s\n' pr-labels-list.sh pr-template-discover.sh pr-create.sh pr-update-body.sh pr-mark-ready.sh ;;
    issue) printf '%s\n' issue-template-discover.sh issue-create.sh ;;
    governance) printf '%s\n' gh-scope-check.sh governance-enforce.sh ;;
    all)
      printf '%s\n' ship.sh sync-raw.sh doctor.sh start-branch.sh ensure-worktree.sh \
        pr-labels-list.sh pr-template-discover.sh pr-create.sh pr-update-body.sh pr-mark-ready.sh \
        issue-template-discover.sh issue-create.sh gh-scope-check.sh governance-enforce.sh
      ;;
  esac
}

emit_json() {
  local topic="$1"
  local entries=""
  entries="$(entries_data)"
  TOPIC="$topic" SCRIPT_DIR="$SCRIPT_DIR" ENTRIES="$entries" python3 - <<'PY'
import json
import os
from pathlib import Path

topic = os.environ["TOPIC"]
script_dir = Path(os.environ["SCRIPT_DIR"])
raw = os.environ["ENTRIES"]

def usage_line(path: Path) -> str:
    found = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line == "# Usage:" or line.strip() == "Usage:":
            found = True
            continue
        if not found:
            continue
        if not line.strip():
            continue
        text = line.lstrip(" #")
        if text:
            return text
    return ""

entries = []
for row in raw.strip().splitlines():
    parts = row.split("|")
    item = {
        "id": parts[0],
        "topic": parts[1],
        "command": parts[2],
        "phrases": [x.strip() for x in parts[3].split(",") if x.strip()],
        "summary": parts[4],
        "script": parts[5],
        "creates_branch": parts[6] == "true",
        "creates_worktree": parts[7] == "true",
        "creates_pr": parts[8] == "true",
        "mutates_history": parts[9] == "true",
        "stays_on_current_branch": parts[10] == "true",
        "supports_json": parts[11] == "true",
        "details_source": parts[12],
        "usage": usage_line(script_dir / parts[5]),
    }
    if topic != "all" and item["topic"] != topic:
        continue
    entries.append(item)

print(json.dumps({"topic": topic, "entries": entries}, indent=2))
PY
}

render_topic_entries() {
  local topic="$1"
  local heading=""
  heading="$(topic_label "$topic")"
  echo "$heading"
  while IFS='|' read -r id item_topic command phrases summary script creates_branch creates_worktree creates_pr mutates_history stays_on_current_branch supports_json details_source; do
    if [[ "$topic" != "all" && "$item_topic" != "$topic" ]]; then
      continue
    fi
    printf '  %-18s %s [%s]\n' "$command" "$summary" "$script"
  done < <(entries_data)
}

render_default_text() {
  echo "GitOps Workflow Help"
  echo "Use --topic <name> to focus one command family or --json for agent-friendly discovery."
  echo ""
  echo "Common commands"
  while IFS='|' read -r id topic command phrases summary script creates_branch creates_worktree creates_pr mutates_history stays_on_current_branch supports_json details_source; do
    case "$id" in
      ship-normal|ship-raw|ship-sync|ship-ready|sync-raw|doctor|doctor-fix|start-work|continue-worktree)
        printf '  %-18s %s [%s]\n' "$command" "$summary" "$script"
        ;;
    esac
  done < <(entries_data)
  echo ""
  for topic in ship sync doctor branch pr issue governance; do
    render_topic_entries "$topic"
    echo ""
  done
}

render_verbose_text() {
  local topic="$1"
  local script=""
  while IFS= read -r script; do
    [[ -n "$script" ]] || continue
    echo "== $script =="
    detail_text_for_script "$script"
    echo ""
  done < <(details_scripts_for_topic "$topic")
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --json)
      JSON="true"
      shift
      ;;
    --verbose)
      VERBOSE="true"
      shift
      ;;
    --topic)
      if [[ -z "${2:-}" || "${2:-}" == --* ]]; then
        echo "Error: option '--topic' requires a value" >&2
        exit 1
      fi
      TOPIC="${2:-}"
      shift 2
      ;;
    -h|--help)
      print_help
      exit 0
      ;;
    *)
      echo "Error: unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

require_topic "$TOPIC"

if [[ "$JSON" == "true" ]]; then
  emit_json "$TOPIC"
  exit 0
fi

if [[ "$TOPIC" == "all" ]]; then
  render_default_text
else
  echo "GitOps Workflow Help"
  echo "Topic: $(topic_label "$TOPIC")"
  echo ""
  render_topic_entries "$TOPIC"
  echo ""
fi

if [[ "$VERBOSE" == "true" ]]; then
  render_verbose_text "$TOPIC"
fi
