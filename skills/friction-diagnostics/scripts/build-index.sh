#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
. "$SCRIPT_DIR/_common.sh"

print_help() {
  cat <<'EOF'
Usage:
  sh scripts/build-index.sh --events-file /path/to/events.jsonl

Options:
  --events-file PATH
  --help
EOF
}

events_file=${FRICTION_EVENTS_FILE-}

while [ $# -gt 0 ]; do
  case "$1" in
    --events-file) events_file=${2-}; shift 2 ;;
    --help|-h) print_help; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
done

[ -n "$events_file" ] || die "--events-file is required"
events_dir=$(dirname "$events_file")
[ -d "$events_dir" ] || mkdir -p "$events_dir"

index_file=$events_dir/INDEX.md
lock_dir=$events_dir/.build-index.lock
lock_acquired=0
summary_tmp=

cleanup() {
  rm -f ${summary_tmp:+"$summary_tmp"}
  if [ "${lock_acquired:-0}" -eq 1 ] && [ -n "${lock_dir-}" ]; then
    rm -f "$lock_dir/pid" 2>/dev/null || true
    rmdir "$lock_dir" 2>/dev/null || true
  fi
}

acquire_lock() {
  while ! mkdir "$lock_dir" 2>/dev/null; do
    if [ -f "$lock_dir/pid" ]; then
      lock_pid=$(sed -n '1p' "$lock_dir/pid" 2>/dev/null || true)
      case "$lock_pid" in
        ''|*[!0-9]*) ;;
        *)
          if ! kill -0 "$lock_pid" 2>/dev/null; then
            rm -f "$lock_dir/pid" 2>/dev/null || true
            rmdir "$lock_dir" 2>/dev/null || true
            continue
          fi
          ;;
      esac
    fi
    sleep 1
  done
  lock_acquired=1
  printf '%s\n' "$$" >"$lock_dir/pid"
}

trap cleanup EXIT HUP INT TERM
acquire_lock

if [ ! -f "$events_file" ]; then
  rm -f "$index_file"
  printf '%s\n' "$index_file"
  exit 0
fi

summary_tmp=$(mktemp "$events_dir/.index-summary.XXXXXX.tmp")
python3 - "$events_file" >"$summary_tmp" <<'PY'
import json
import sys
from collections import Counter
from pathlib import Path

events_path = Path(sys.argv[1])
lines = []
with events_path.open("r", encoding="utf-8") as fh:
    for raw in fh:
        raw = raw.strip()
        if not raw:
            continue
        lines.append(json.loads(raw))

if not lines:
    sys.exit(10)

categories = Counter()
fingerprints = Counter()
agent_kinds = Counter()
dates = Counter()
tags_counter = Counter()

def _event_tags(event):
    """Return list of tag strings from the tags array."""
    tags = event.get("tags")
    if isinstance(tags, list):
        return [str(t) for t in tags if t]
    return []

for event in lines:
    if event.get("derived_category"):
        categories[event["derived_category"]] += 1
    if event.get("fingerprint"):
        fingerprints[event["fingerprint"]] += 1
    if event.get("provenance_source") == "explicit" and event.get("agent_kind"):
        agent_kinds[event["agent_kind"]] += 1
    ts = event.get("recorded_at", "")
    if len(ts) >= 10:
        dates[ts[:10]] += 1
    for tag in _event_tags(event):
        tags_counter[tag] += 1

def write_count_block(prefix, counter):
    for key, count in sorted(counter.items(), key=lambda item: (-item[1], item[0])):
        print(f"{prefix}\t{count}\t{key}")

print(f"META\ttotal\t{len(lines)}")
print(f"META\tfirst\t{lines[0].get('recorded_at', '')}")
print(f"META\tlast\t{lines[-1].get('recorded_at', '')}")
print(f"META\trepo_root\t{lines[-1].get('repo_root', '')}")
print(f"META\tevents_file\t{events_path}")
write_count_block("CATEGORY", categories)
write_count_block("FINGERPRINT", fingerprints)
write_count_block("AGENT_KIND", agent_kinds)
write_count_block("DATE", dates)
write_count_block("TAG", tags_counter)
PY
status=$?
if [ "$status" -eq 10 ]; then
  rm -f "$index_file"
  printf '%s\n' "$index_file"
  exit 0
fi
[ "$status" -eq 0 ] || exit "$status"

generated=$(date -u '+%Y-%m-%d %H:%M:%S %Z')
total_entries=$(awk -F '\t' '$1=="META" && $2=="total" {print $3}' "$summary_tmp")
first_recorded=$(awk -F '\t' '$1=="META" && $2=="first" {print $3}' "$summary_tmp")
last_recorded=$(awk -F '\t' '$1=="META" && $2=="last" {print $3}' "$summary_tmp")
repo_root=$(awk -F '\t' '$1=="META" && $2=="repo_root" {print $3}' "$summary_tmp")

index_tmp=$(mktemp "$events_dir/.index.XXXXXX.tmp")
{
  printf '# Friction Index\n'
  write_md_field "Generated" "$generated"
  write_md_field "Events file" "$events_file"
  if [ -n "$repo_root" ]; then
    write_md_field "Repo root" "$repo_root"
  fi
  write_md_field "Entries" "$total_entries"
  write_md_field "First recorded" "$first_recorded"
  write_md_field "Last recorded" "$last_recorded"
  printf '\n## Category Counts\n\n'
  if grep -q '^CATEGORY	' "$summary_tmp"; then
    awk -F '\t' '$1=="CATEGORY" {printf "- `%s` - %s\n", $3, $2}' "$summary_tmp"
  else
    printf '_No categorized events._\n'
  fi
  printf '\n## Top Fingerprints\n\n'
  if grep -q '^FINGERPRINT	' "$summary_tmp"; then
    awk -F '\t' '$1=="FINGERPRINT" {printf "- `%s` - %s events\n", $3, $2}' "$summary_tmp" | sed -n '1,10p'
  else
    printf '_No fingerprints yet._\n'
  fi
  printf '\n## Agent Kinds\n\n'
  if grep -q '^AGENT_KIND	' "$summary_tmp"; then
    awk -F '\t' '$1=="AGENT_KIND" {printf "- `%s` - %s\n", $3, $2}' "$summary_tmp"
  else
    printf '_No explicit provenance recorded._\n'
  fi
  printf '\n## Date Counts\n\n'
  if grep -q '^DATE	' "$summary_tmp"; then
    awk -F '\t' '$1=="DATE" {printf "- `%s` - %s\n", $3, $2}' "$summary_tmp"
  else
    printf '_No date counts available._\n'
  fi
  printf '\n## Tags\n\n'
  if grep -q '^TAG	' "$summary_tmp"; then
    awk -F '\t' '$1=="TAG" {printf "- `%s` - %s\n", $3, $2}' "$summary_tmp"
  else
    printf '_No tags recorded._\n'
  fi
} >"$index_tmp"

mv -f "$index_tmp" "$index_file"
printf '%s\n' "$index_file"
