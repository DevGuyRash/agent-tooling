#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
. "$SCRIPT_DIR/_common.sh"

print_help() {
  cat <<'EOF'
Usage:
  sh scripts/query-friction.sh [--events-file PATH | --scan-dirs DIR [DIR...]] [filters]

Input:
  --events-file PATH        Single events file (default: auto-detected)
  --scan-dirs DIR [DIR...]  Recursively discover all events.jsonl files under
                            the given directories matching
                            */.local*/reports/friction/events.jsonl

Filters:
  --category VALUE
  --fingerprint VALUE
  --agent-kind VALUE
  --role VALUE
  --date YYYY-MM-DD
  --date-from YYYY-MM-DD
  --date-to YYYY-MM-DD
  --after ISO-TIMESTAMP     Filter events with recorded_at > TIMESTAMP
  --source-ref PATH

Output:
  --format jsonl|json|md
  --output PATH
  --compact                 Strip empty-string and null fields (json/jsonl only)
  --suggest-tags
  --help
EOF
}

events_file=${FRICTION_EVENTS_FILE-}
scan_dirs=""
category=
fingerprint=
agent_kind=
role=
date_exact=
date_from=
date_to=
after=
source_ref=
format=jsonl
output_path=
suggest_tags=0
compact=0

while [ $# -gt 0 ]; do
  case "$1" in
    --events-file) events_file=${2-}; shift 2 ;;
    --scan-dirs)
      shift
      while [ $# -gt 0 ]; do
        case "$1" in
          --*) break ;;
          *) scan_dirs="$scan_dirs $1"; shift ;;
        esac
      done
      ;;
    --category) category=${2-}; shift 2 ;;
    --fingerprint) fingerprint=${2-}; shift 2 ;;
    --agent-kind) agent_kind=${2-}; shift 2 ;;
    --role) role=${2-}; shift 2 ;;
    --date) date_exact=${2-}; shift 2 ;;
    --date-from) date_from=${2-}; shift 2 ;;
    --date-to) date_to=${2-}; shift 2 ;;
    --after) after=${2-}; shift 2 ;;
    --source-ref) source_ref=${2-}; shift 2 ;;
    --format) format=${2-}; shift 2 ;;
    --output) output_path=${2-}; shift 2 ;;
    --compact) compact=1; shift ;;
    --suggest-tags) suggest_tags=1; shift ;;
    --help|-h) print_help; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
done

# Resolve input: --scan-dirs, --events-file, or default
if [ -n "$scan_dirs" ]; then
  # shellcheck disable=SC2086
  discovered=$(find $scan_dirs -path '*/.local*/reports/friction/events.jsonl' -type f 2>/dev/null || true)
  if [ -z "$discovered" ]; then
    die "No events.jsonl files found under: $scan_dirs"
  fi
  events_files="$discovered"
else
  if [ -z "$events_file" ]; then
    events_file=$(default_events_file)
  fi
  [ -f "$events_file" ] || die "Events file not found: $events_file"
  events_files="$events_file"
fi

if [ "$suggest_tags" -eq 1 ]; then
  result=$(
    python3 - "$events_files" <<'PY'
import json
import sys
from pathlib import Path

files_arg = sys.argv[1]
file_paths = [p for p in files_arg.splitlines() if p.strip()]

tags_seen = set()
for events_file in file_paths:
    try:
        with Path(events_file).open("r", encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                event = json.loads(raw)
                tags = event.get("tags")
                if isinstance(tags, list):
                    for t in tags:
                        if t:
                            tags_seen.add(str(t))
    except OSError:
        pass
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
  python3 - "$events_files" "$category" "$fingerprint" "$agent_kind" "$role" "$date_exact" "$date_from" "$date_to" "$after" "$source_ref" "$format" "$compact" <<'PY'
import json
import sys
from pathlib import Path

files_arg, category, fingerprint, agent_kind, role, date_exact, date_from, date_to, after, source_ref, out_fmt, compact_str = sys.argv[1:]
compact = compact_str == "1"

def _event_tags(event):
    """Return list of tag strings from the tags array."""
    tags = event.get("tags")
    if isinstance(tags, list):
        return [str(t) for t in tags if t]
    return []

def _matches_source_ref(event, ref):
    """Check source ref against sources array."""
    sources = event.get("sources")
    if isinstance(sources, list):
        if any(isinstance(s, dict) and s.get("ref") == ref for s in sources):
            return True
    return False

file_paths = [p for p in files_arg.splitlines() if p.strip()]

events = []
for events_file in file_paths:
    try:
        with Path(events_file).open("r", encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                events.append(json.loads(raw))
    except OSError:
        pass

events.sort(key=lambda e: e.get("recorded_at", ""))

filtered = []
for event in events:
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
    if after and ts and ts <= after:
        continue
    if source_ref and not _matches_source_ref(event, source_ref):
        continue
    filtered.append(event)

def _maybe_compact(event):
    if compact:
        return {k: v for k, v in event.items() if v is not None and v != ""}
    return event

if out_fmt == "jsonl":
    for event in filtered:
        print(json.dumps(_maybe_compact(event), ensure_ascii=False))
elif out_fmt == "json":
    print(json.dumps([_maybe_compact(e) for e in filtered], ensure_ascii=False, indent=2))
elif out_fmt == "md":
    print("# Friction Query Results")
    print()
    print(f"- Entries: {len(filtered)}")
    print()
    for event in filtered:
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
        sources = event.get("sources")
        if isinstance(sources, list) and sources:
            refs = [s.get("ref", "") for s in sources if isinstance(s, dict)]
            print(f"- Sources: {', '.join(r for r in refs if r)}")
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
