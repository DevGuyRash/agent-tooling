#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
. "$SCRIPT_DIR/_common.sh"

print_help() {
  cat <<'EOF'
Usage:
  sh scripts/query-friction.sh [--events-file PATH] [filters]

Filters:
  --category VALUE
  --fingerprint VALUE
  --agent-kind VALUE
  --role VALUE
  --date YYYY-MM-DD
  --date-from YYYY-MM-DD
  --date-to YYYY-MM-DD
  --anchor-path PATH

Output:
  --format jsonl|json|md
  --output PATH
  --help
EOF
}

events_file=${FRICTION_EVENTS_FILE-}
category=
fingerprint=
agent_kind=
role=
date_exact=
date_from=
date_to=
anchor_path=
format=jsonl
output_path=

while [ $# -gt 0 ]; do
  case "$1" in
    --events-file) events_file=${2-}; shift 2 ;;
    --category) category=${2-}; shift 2 ;;
    --fingerprint) fingerprint=${2-}; shift 2 ;;
    --agent-kind) agent_kind=${2-}; shift 2 ;;
    --role) role=${2-}; shift 2 ;;
    --date) date_exact=${2-}; shift 2 ;;
    --date-from) date_from=${2-}; shift 2 ;;
    --date-to) date_to=${2-}; shift 2 ;;
    --anchor-path) anchor_path=${2-}; shift 2 ;;
    --format) format=${2-}; shift 2 ;;
    --output) output_path=${2-}; shift 2 ;;
    --help|-h) print_help; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
done

if [ -z "$events_file" ]; then
  events_file=$(default_events_file)
fi
[ -f "$events_file" ] || die "Events file not found: $events_file"

result=$(
  python3 - "$events_file" "$category" "$fingerprint" "$agent_kind" "$role" "$date_exact" "$date_from" "$date_to" "$anchor_path" "$format" <<'PY'
import json
import sys
from pathlib import Path

events_file, category, fingerprint, agent_kind, role, date_exact, date_from, date_to, anchor_path, out_fmt = sys.argv[1:]

events = []
with Path(events_file).open("r", encoding="utf-8") as fh:
    for raw in fh:
        raw = raw.strip()
        if not raw:
            continue
        event = json.loads(raw)
        ts = event.get("recorded_at", "")
        event_date = ts[:10] if len(ts) >= 10 else ""
        if category and event.get("derived_category") != category:
            continue
        if fingerprint and event.get("fingerprint") != fingerprint:
            continue
        if agent_kind and event.get("agent_kind") != agent_kind:
            continue
        if role and event.get("role") != role:
            continue
        if date_exact and event_date != date_exact:
            continue
        if date_from and event_date and event_date < date_from:
            continue
        if date_to and event_date and event_date > date_to:
            continue
        if anchor_path:
            anchors = event.get("anchors") or []
            if not any(isinstance(anchor, dict) and anchor.get("path") == anchor_path for anchor in anchors):
                continue
        events.append(event)

if out_fmt == "jsonl":
    for event in events:
        print(json.dumps(event, ensure_ascii=False))
elif out_fmt == "json":
    print(json.dumps(events, ensure_ascii=False, indent=2))
elif out_fmt == "md":
    print("# Friction Query Results")
    print()
    print(f"- Entries: {len(events)}")
    print()
    for event in events:
        explicit_provenance = event.get("provenance_source") == "explicit"
        print(f"## {event.get('event_id', '')}: {event.get('title', '')}")
        print()
        print(f"- Recorded: {event.get('recorded_at', '')}")
        print(f"- Category: {event.get('derived_category', '')}")
        print(f"- Fingerprint: {event.get('fingerprint', '')}")
        if explicit_provenance:
            print(f"- Agent: {event.get('agent_name', '')}")
            print(f"- Agent kind: {event.get('agent_kind', '')}")
            print(f"- Role: {event.get('role', '')}")
        print(f"- Source: {event.get('instruction_source', '')}")
        print(f"- Actual outcome: {event.get('actual_outcome', '')}")
        print()
else:
    print(f"Unsupported format: {out_fmt}", file=sys.stderr)
    sys.exit(2)
PY
)

if [ -n "$output_path" ]; then
  printf '%s\n' "$result" >"$output_path"
else
  printf '%s\n' "$result"
fi
