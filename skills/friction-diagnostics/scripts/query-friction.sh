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
  --source-ref PATH

Output:
  --format jsonl|json|md
  --output PATH
  --suggest-tags
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
source_ref=
format=jsonl
output_path=
suggest_tags=0

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
    --source-ref) source_ref=${2-}; shift 2 ;;
    --anchor-path) source_ref=${2-}; shift 2 ;;  # hidden backward-compat alias
    --format) format=${2-}; shift 2 ;;
    --output) output_path=${2-}; shift 2 ;;
    --suggest-tags) suggest_tags=1; shift ;;
    --help|-h) print_help; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
done

if [ -z "$events_file" ]; then
  events_file=$(default_events_file)
fi
[ -f "$events_file" ] || die "Events file not found: $events_file"

if [ "$suggest_tags" -eq 1 ]; then
  result=$(
    python3 - "$events_file" <<'PY'
import json
import sys
from pathlib import Path

events_file = sys.argv[1]
tags_seen = set()
with Path(events_file).open("r", encoding="utf-8") as fh:
    for raw in fh:
        raw = raw.strip()
        if not raw:
            continue
        event = json.loads(raw)
        # v3: tags is a JSON array
        tags_v3 = event.get("tags")
        if isinstance(tags_v3, list):
            for t in tags_v3:
                if t:
                    tags_seen.add(str(t))
        # v2: tags_csv is a comma-separated string
        tags_csv = event.get("tags_csv")
        if isinstance(tags_csv, str) and tags_csv.strip():
            for t in tags_csv.split(","):
                t = t.strip()
                if t:
                    tags_seen.add(t)
for tag in sorted(tags_seen):
    print(tag)
PY
  )
  if [ -n "$output_path" ]; then
    printf '%s\n' "$result" >"$output_path"
  else
    printf '%s\n' "$result"
  fi
  exit 0
fi

result=$(
  python3 - "$events_file" "$category" "$fingerprint" "$agent_kind" "$role" "$date_exact" "$date_from" "$date_to" "$source_ref" "$format" <<'PY'
import json
import sys
from pathlib import Path

events_file, category, fingerprint, agent_kind, role, date_exact, date_from, date_to, source_ref, out_fmt = sys.argv[1:]

def _event_tags(event):
    """Return list of tag strings, handling both v3 (array) and v2 (tags_csv string)."""
    tags_v3 = event.get("tags")
    if isinstance(tags_v3, list):
        return [str(t) for t in tags_v3 if t]
    tags_csv = event.get("tags_csv")
    if isinstance(tags_csv, str) and tags_csv.strip():
        return [t.strip() for t in tags_csv.split(",") if t.strip()]
    return []

def _matches_source_ref(event, ref):
    """Check source ref against v3 sources array, v2 anchors array, and legacy instruction_source."""
    # v3: sources[].ref
    sources = event.get("sources")
    if isinstance(sources, list):
        if any(isinstance(s, dict) and s.get("ref") == ref for s in sources):
            return True
    # v2: anchors[].path
    anchors = event.get("anchors")
    if isinstance(anchors, list):
        if any(isinstance(a, dict) and a.get("path") == ref for a in anchors):
            return True
    # legacy scalar field
    if event.get("instruction_source") == ref:
        return True
    return False

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
        if source_ref and not _matches_source_ref(event, source_ref):
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
        # Display sources (v3) or anchors (v2) if present
        sources = event.get("sources")
        if isinstance(sources, list) and sources:
            refs = [s.get("ref", "") for s in sources if isinstance(s, dict)]
            print(f"- Sources: {', '.join(r for r in refs if r)}")
        else:
            anchors = event.get("anchors")
            if isinstance(anchors, list) and anchors:
                paths = [a.get("path", "") for a in anchors if isinstance(a, dict)]
                print(f"- Sources: {', '.join(p for p in paths if p)}")
        tags = _event_tags(event)
        if tags:
            print(f"- Tags: {', '.join(tags)}")
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
