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
  - Blocked push receipts may expose opt-in `manual_bypass_*` helper fields for a one-off HTTPS `--no-verify` publish path.
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

catalog_json() {
  local topic="$1"
  TOPIC="$topic" SCRIPT_DIR="$SCRIPT_DIR" python3 - <<'PY'
import json
import os
import re
from pathlib import Path

topic = os.environ["TOPIC"]
script_dir = Path(os.environ["SCRIPT_DIR"])
topic_order = {"ship": 0, "sync": 1, "doctor": 2, "branch": 3, "pr": 4, "issue": 5, "governance": 6}

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
pattern = re.compile(r"^# gitops-catalog:\s*(\{.*\})\s*$")
for path in sorted(script_dir.glob("*.sh")):
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if not match:
            continue
        item = json.loads(match.group(1))
        item["usage"] = usage_line(path)
        item["details_source"] = item["script"]
        if topic != "all" and item["topic"] != topic:
            continue
        entries.append(item)

entries.sort(key=lambda item: (topic_order.get(item["topic"], 99), item["command"]))

notes = [
    {
        "id": "manual-push-bypass",
        "summary": "Blocked push receipts may include opt-in manual_bypass_* fields for a one-off HTTPS --no-verify publish path.",
        "requires_user_confirmation": True,
    }
]

print(json.dumps({"topic": topic, "notes": notes, "entries": entries}, indent=2))
PY
}

render_default_text() {
  local payload=""
  payload="$(catalog_json all)"
  CATALOG_JSON="$payload" python3 - <<'PY'
import json
import os

payload = json.loads(os.environ["CATALOG_JSON"])
entries = payload["entries"]
common_ids = {
    "ship-normal",
    "ship-raw",
    "ship-sync",
    "ship-ready",
    "sync-raw",
    "doctor",
    "doctor-fix",
    "start-work",
    "continue-worktree",
}
topic_labels = {
    "ship": "Ship Workflows",
    "sync": "Sync Workflows",
    "doctor": "Doctor Workflows",
    "branch": "Branch / Worktree",
    "pr": "Pull Requests",
    "issue": "Issues",
    "governance": "Governance",
}

print("GitOps Workflow Help")
print("Use --topic <name> to focus one command family or --json for agent-friendly discovery.")
print("Blocked push receipts may expose opt-in manual bypass guidance via manual_bypass_* fields.")
print("")
print("Common commands")
for item in entries:
    if item["id"] in common_ids:
        print(f"  {item['command']:<18} {item['summary']} [{item['script']}]")
print("")
for topic in ("ship", "sync", "doctor", "branch", "pr", "issue", "governance"):
    print(topic_labels[topic])
    for item in entries:
        if item["topic"] == topic:
            print(f"  {item['command']:<18} {item['summary']} [{item['script']}]")
    print("")
PY
}

render_verbose_text() {
  local topic="$1"
  local payload=""
  payload="$(catalog_json "$topic")"
  local script=""
  while IFS= read -r script; do
    [[ -n "$script" ]] || continue
    echo "== $script =="
    detail_text_for_script "$script"
    echo ""
  done < <(CATALOG_JSON="$payload" python3 - <<'PY'
import json
import os

payload = json.loads(os.environ["CATALOG_JSON"])
seen = set()
for item in payload["entries"]:
    script = item["script"]
    if script in seen:
        continue
    seen.add(script)
    print(script)
PY
)
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
  catalog_json "$TOPIC"
  exit 0
fi

if [[ "$TOPIC" == "all" ]]; then
  render_default_text
else
  CATALOG_JSON="$(catalog_json "$TOPIC")" TOPIC_LABEL="$(topic_label "$TOPIC")" python3 - <<'PY'
import json
import os

payload = json.loads(os.environ["CATALOG_JSON"])
print("GitOps Workflow Help")
print(f"Topic: {os.environ['TOPIC_LABEL']}")
print("")
for item in payload["entries"]:
    print(f"  {item['command']:<18} {item['summary']} [{item['script']}]")
print("")
PY
fi

if [[ "$VERBOSE" == "true" ]]; then
  render_verbose_text "$TOPIC"
fi
