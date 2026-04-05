#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
. "$SCRIPT_DIR/_common.sh"

print_help() {
  cat <<'EOF'
Usage:
  sh scripts/report-friction.sh [--events-file PATH] --title "..." [fields]
  sh scripts/report-friction.sh [--events-file PATH] --from-json PATH|-

Canonical target resolution:
  --events-file PATH     Explicit canonical event log path.
  If omitted, the tool writes to the repo-scoped rolling log derived from the
  current git root, or to a deterministic temp-root path outside a git repo.

Structured input:
  --from-json PATH|-     Load event fields from JSON on disk or stdin.
                         Prefer stdin for shell-sensitive or multiline text.

Core fields:
  --title TEXT
  --expected-outcome TEXT
  --actual-outcome TEXT
  --reading TEXT
  --hindsight TEXT

Source fields (single source via CLI; use --from-json for multiple):
  --source-type TYPE     One of: file, url, conversation, audio, visual,
                         documentation, other
  --source-ref TEXT      Primary reference (filepath, URL, description)
  --source-line INT      Start line (for files)
  --source-end-line INT  End line (for file ranges)
  --source-excerpt TEXT  Verbatim quote from the source

Classification:
  --impact VALUE         blocked | degraded | noisy | continued
  --tags TEXT            Comma-separated specific tags (normalized to lowercase)
  --aliases TEXT         Comma-separated broader groupings (normalized to lowercase)

Identity:
  --repo-root PATH

Fingerprint:
  --fingerprint-key TEXT Override the default fingerprint seed

Tag management (run after initial event creation):
  --add-tags EVENT_ID "tag1,tag2,tag3"
                         Add tags to an existing event by event_id.
  --add-aliases EVENT_ID "alias1,alias2"
                         Add aliases to an existing event by event_id.

Other:
  --help
EOF
}

events_file=${FRICTION_EVENTS_FILE-}
from_json=
title=
expected_outcome=
actual_outcome=
reading=
hindsight=
repo_root=
impact=
tags_csv=
aliases_csv=
fingerprint_key=
add_tags_event_id=
add_tags_csv=
add_aliases_event_id=
add_aliases_csv=
source_type=
source_ref=
source_line=
source_end_line=
source_excerpt=
sources_json=
lock_dir=
report_lock_acquired=0

cleanup_report_lock() {
  if [ "${report_lock_acquired:-0}" -eq 1 ] && [ -n "${lock_dir-}" ]; then
    rm -f "$lock_dir/pid" 2>/dev/null || true
    rmdir "$lock_dir" 2>/dev/null || true
  fi
}

acquire_report_lock() {
  target_dir=$1
  lock_dir=$target_dir/.report-friction.lock
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
  report_lock_acquired=1
  printf '%s\n' "$$" >"$lock_dir/pid"
}

trap cleanup_report_lock EXIT HUP INT TERM

load_json_overrides() {
  path=$1
  if ! command -v python3 >/dev/null 2>&1; then
    die "python3 is required for --from-json"
  fi
  scratch_dir=$2
  json_helper=$(mktemp "$(temp_root_dir)/friction-json-helper.XXXXXX.py")
  cat >"$json_helper" <<'PY'
import json
import shlex
import sys
import tempfile

path = sys.argv[1]
scratch_dir = sys.argv[2]
temp_root = sys.argv[3]
if path == "-":
    raw = sys.stdin.read()
else:
    with open(path, "r", encoding="utf-8") as fh:
        raw = fh.read()

def hint_for(err_msg: str) -> str:
    msg = err_msg.lower()
    if "expecting property name enclosed in double quotes" in msg:
        return "Hint: check for trailing commas or single-quoted keys."
    if "unterminated string" in msg:
        return "Hint: a quoted string is not closed."
    if "expecting value" in msg:
        return "Hint: a value is missing or a trailing comma is present."
    return "Hint: provide one JSON object with double-quoted keys and values."

try:
    data = json.loads(raw)
except json.JSONDecodeError as exc:
    lines = raw.splitlines() or [raw]
    offending = lines[exc.lineno - 1] if 0 < exc.lineno <= len(lines) else ""
    pointer = " " * max(exc.colno - 1, 0) + "^"
    print("Invalid JSON input for --from-json", file=sys.stderr)
    print(f"Line {exc.lineno}, column {exc.colno}", file=sys.stderr)
    if offending:
        print(offending, file=sys.stderr)
        print(pointer, file=sys.stderr)
    if path == "-":
        try:
            if scratch_dir:
                target_dir = scratch_dir
            else:
                target_dir = temp_root
            import os
            os.makedirs(target_dir, exist_ok=True)
            fd, bad_path = tempfile.mkstemp(prefix="invalid-stdin.", suffix=".json", dir=target_dir)
            with open(fd, "w", encoding="utf-8", closefd=True) as bad_fh:
                bad_fh.write(raw)
            print(f"Saved invalid stdin payload to: {bad_path}", file=sys.stderr)
        except Exception as save_exc:
            print(f"Unable to save invalid stdin payload: {save_exc}", file=sys.stderr)
    print(hint_for(exc.msg), file=sys.stderr)
    sys.exit(2)

if not isinstance(data, dict):
    print("Invalid JSON input for --from-json", file=sys.stderr)
    print("Hint: the payload must be one JSON object.", file=sys.stderr)
    sys.exit(2)

VALID_SOURCE_TYPES = {
    "file", "url", "conversation",
    "audio", "visual", "documentation", "other",
}

errors = []

# --- Build sources array ---
sources = data.get("sources")
if sources is not None:
    if not isinstance(sources, list):
        errors.append("field must be an array when present: sources")
        sources = []
    for i, src in enumerate(sources):
        if not isinstance(src, dict):
            errors.append(f"sources[{i}] must be an object")
            continue
        if not src.get("type"):
            errors.append(f"sources[{i}].type is required")
        elif src["type"] not in VALID_SOURCE_TYPES:
            errors.append(
                f"sources[{i}].type must be one of: {', '.join(sorted(VALID_SOURCE_TYPES))} (got '{src['type']}')"
            )
        if not src.get("ref"):
            errors.append(f"sources[{i}].ref is required")
else:
    errors.append("missing required field: sources")

# --- Validate required narrative fields ---
required_narrative = [
    "expected_outcome",
    "actual_outcome",
    "reading",
]
for key in required_narrative:
    value = data.get(key)
    if value is None:
        errors.append(f"missing required field: {key}")
    elif not isinstance(value, str):
        errors.append(f"field must be a string: {key}")
    elif value.strip() == "":
        errors.append(f"field must not be blank: {key}")

# hindsight is optional
for key in ["hindsight"]:
    value = data.get(key)
    if value is not None and not isinstance(value, str):
        errors.append(f"field must be a string: {key}")

# Validate impact if provided
impact_val = data.get("impact")
if impact_val is not None:
    if impact_val not in ("blocked", "degraded", "noisy", "continued"):
        errors.append(f"impact must be one of: blocked, degraded, noisy, continued (got '{impact_val}')")

# Validate tags/aliases are arrays of strings if provided
for arr_key in ["tags", "aliases"]:
    arr_val = data.get(arr_key)
    if arr_val is not None:
        if not isinstance(arr_val, list):
            errors.append(f"{arr_key} must be an array")
        else:
            for i, item in enumerate(arr_val):
                if not isinstance(item, str):
                    errors.append(f"{arr_key}[{i}] must be a string")

if errors:
    print("Invalid friction payload for --from-json", file=sys.stderr)
    for item in errors:
      print(f"- {item}", file=sys.stderr)
    sys.exit(3)

# --- Emit shell variables ---
def normalize(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)

keys = [
    ("title", "json_title"),
    ("expected_outcome", "json_expected_outcome"),
    ("actual_outcome", "json_actual_outcome"),
    ("reading", "json_reading"),
    ("hindsight", "json_hindsight"),
    ("repo_root", "json_repo_root"),
    ("impact", "json_impact"),
    ("fingerprint_key", "json_fingerprint_key"),
]

for key, var_name in keys:
    value = normalize(data.get(key))
    if value is not None:
        print(f"{var_name}={shlex.quote(value)}")

# Emit tags and aliases as CSV for shell
tags = data.get("tags")
if isinstance(tags, list) and tags:
    print(f"json_tags_csv={shlex.quote(','.join(str(t) for t in tags))}")

aliases = data.get("aliases")
if isinstance(aliases, list) and aliases:
    print(f"json_aliases_csv={shlex.quote(','.join(str(a) for a in aliases))}")

# Emit sources as JSON for shell to embed directly
print(f"json_sources_json={shlex.quote(json.dumps(sources, ensure_ascii=False))}")
PY
  json_output=$(python3 "$json_helper" "$path" "$scratch_dir" "$(temp_root_dir)") || {
    status=$?
    rm -f "$json_helper"
    return "$status"
  }
  rm -f "$json_helper"
  eval "$json_output"
}

load_json_field() {
  current=$1
  default=$2
  var_name=$3
  if [ "$current" != "$default" ]; then
    printf '%s\n' "$current"
    return 0
  fi
  eval "var_is_set=\${$var_name+x}"
  if [ "$var_is_set" != "x" ]; then
    printf '%s\n' "$current"
    return 0
  fi
  eval "printf '%s\n' \"\${$var_name}\""
}

while [ $# -gt 0 ]; do
  case "$1" in
    --events-file) events_file=${2-}; shift 2 ;;
    --from-json) from_json=${2-}; shift 2 ;;
    --title) title=${2-}; shift 2 ;;
    --expected-outcome) expected_outcome=${2-}; shift 2 ;;
    --actual-outcome) actual_outcome=${2-}; shift 2 ;;
    --reading) reading=${2-}; shift 2 ;;
    --hindsight) hindsight=${2-}; shift 2 ;;
    --repo-root) repo_root=${2-}; shift 2 ;;
    --impact) impact=${2-}; shift 2 ;;
    --tags) tags_csv=${2-}; shift 2 ;;
    --aliases) aliases_csv=${2-}; shift 2 ;;
    --fingerprint-key) fingerprint_key=${2-}; shift 2 ;;
    --add-tags) add_tags_event_id=${2-}; add_tags_csv=${3-}; shift 3 ;;
    --add-aliases) add_aliases_event_id=${2-}; add_aliases_csv=${3-}; shift 3 ;;
    --source-type) source_type=${2-}; shift 2 ;;
    --source-ref) source_ref=${2-}; shift 2 ;;
    --source-line) source_line=${2-}; shift 2 ;;
    --source-end-line) source_end_line=${2-}; shift 2 ;;
    --source-excerpt) source_excerpt=${2-}; shift 2 ;;
    --help|-h) print_help; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
done

if [ -n "$from_json" ]; then
  invalid_json_scratch_dir=
  resolved_repo_root=$repo_root
  if [ -z "$resolved_repo_root" ]; then
    resolved_repo_root=$(git_repo_root)
  fi
  if [ -n "$resolved_repo_root" ]; then
    invalid_json_scratch_dir=$(friction_scratch_dir_for_repo "$resolved_repo_root")
  fi
  load_json_overrides "$from_json" "$invalid_json_scratch_dir"
  title=$(load_json_field "$title" "" json_title)
  expected_outcome=$(load_json_field "$expected_outcome" "" json_expected_outcome)
  actual_outcome=$(load_json_field "$actual_outcome" "" json_actual_outcome)
  reading=$(load_json_field "$reading" "" json_reading)
  hindsight=$(load_json_field "$hindsight" "" json_hindsight)
  repo_root=$(load_json_field "$repo_root" "" json_repo_root)
  impact=$(load_json_field "$impact" "" json_impact)
  fingerprint_key=$(load_json_field "$fingerprint_key" "" json_fingerprint_key)
  tags_csv=$(load_json_field "$tags_csv" "" json_tags_csv)
  aliases_csv=$(load_json_field "$aliases_csv" "" json_aliases_csv)
  # sources_json is set directly by the Python helper
  sources_json=$(load_json_field "$sources_json" "" json_sources_json)
fi

if [ -z "$events_file" ]; then
  events_file=$(default_events_file)
fi
events_dir=$(dirname "$events_file")
mkdir -p "$events_dir"

# --- --add-tags mode: patch tags on an existing event ---
if [ -n "$add_tags_event_id" ]; then
  if [ -z "$add_tags_csv" ]; then
    die "--add-tags requires EVENT_ID and TAGS arguments"
  fi
  if [ ! -f "$events_file" ]; then
    die "Events file not found: $events_file"
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    die "python3 is required for --add-tags"
  fi
  acquire_report_lock "$events_dir"
  tmp_tags_file=$(mktemp "$events_dir/.events-tags.XXXXXX.tmp")
  if python3 - "$events_file" "$tmp_tags_file" "$add_tags_event_id" "$add_tags_csv" <<'PY'
import json, os, sys
events_path, output_path, target_id, tags_csv = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
new_tags = [t.strip().lower() for t in tags_csv.split(",") if t.strip()]
if not new_tags:
    print("No tags provided", file=sys.stderr)
    sys.exit(1)
found = False
with open(events_path, "r", encoding="utf-8") as src, open(output_path, "w", encoding="utf-8") as dst:
    for raw in src:
        stripped = raw.strip()
        if not stripped:
            dst.write(raw)
            continue
        event = json.loads(stripped)
        if event.get("event_id") == target_id:
            found = True
            existing = event.get("tags", [])
            if isinstance(existing, str):
                existing = [t.strip().lower() for t in existing.split(",") if t.strip()]
            merged = list(dict.fromkeys(existing + new_tags))
            event["tags"] = merged
            dst.write(json.dumps(event, ensure_ascii=False) + "\n")
        else:
            dst.write(raw)
if not found:
    try:
        os.remove(output_path)
    except FileNotFoundError:
        pass
    print(f"Event not found: {target_id}", file=sys.stderr)
    sys.exit(1)
os.replace(output_path, events_path)
PY
  then
    :
  else
    status=$?
    rm -f "$tmp_tags_file"
    exit "$status"
  fi
  sh "$SCRIPT_DIR/build-index.sh" --events-file "$events_file" >/dev/null
  printf 'FRICTION_TAGS_UPDATED=%s\n' "$add_tags_event_id"
  exit 0
fi

# --- --add-aliases mode: patch aliases on an existing event ---
if [ -n "$add_aliases_event_id" ]; then
  if [ -z "$add_aliases_csv" ]; then
    die "--add-aliases requires EVENT_ID and ALIASES arguments"
  fi
  if [ ! -f "$events_file" ]; then
    die "Events file not found: $events_file"
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    die "python3 is required for --add-aliases"
  fi
  acquire_report_lock "$events_dir"
  tmp_aliases_file=$(mktemp "$events_dir/.events-aliases.XXXXXX.tmp")
  if python3 - "$events_file" "$tmp_aliases_file" "$add_aliases_event_id" "$add_aliases_csv" <<'PY'
import json, os, sys
events_path, output_path, target_id, aliases_csv = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
new_aliases = [a.strip().lower() for a in aliases_csv.split(",") if a.strip()]
if not new_aliases:
    print("No aliases provided", file=sys.stderr)
    sys.exit(1)
found = False
with open(events_path, "r", encoding="utf-8") as src, open(output_path, "w", encoding="utf-8") as dst:
    for raw in src:
        stripped = raw.strip()
        if not stripped:
            dst.write(raw)
            continue
        event = json.loads(stripped)
        if event.get("event_id") == target_id:
            found = True
            existing = event.get("aliases", [])
            if isinstance(existing, str):
                existing = [a.strip().lower() for a in existing.split(",") if a.strip()]
            merged = list(dict.fromkeys(existing + new_aliases))
            event["aliases"] = merged
            dst.write(json.dumps(event, ensure_ascii=False) + "\n")
        else:
            dst.write(raw)
if not found:
    try:
        os.remove(output_path)
    except FileNotFoundError:
        pass
    print(f"Event not found: {target_id}", file=sys.stderr)
    sys.exit(1)
os.replace(output_path, events_path)
PY
  then
    :
  else
    status=$?
    rm -f "$tmp_aliases_file"
    exit "$status"
  fi
  sh "$SCRIPT_DIR/build-index.sh" --events-file "$events_file" >/dev/null
  printf 'FRICTION_ALIASES_UPDATED=%s\n' "$add_aliases_event_id"
  exit 0
fi

acquire_report_lock "$events_dir"

if [ -z "$repo_root" ]; then
  repo_root=$(git_repo_root)
fi

# Build sources JSON from CLI flags if not already set from --from-json
if [ -z "$sources_json" ]; then
  if [ -n "$source_ref" ]; then
    if [ -z "$source_type" ]; then
      source_type=documentation
    fi
    validate_source_type "$source_type"
    src_fields="$(json_string "type" "$source_type"),$(json_string "ref" "$source_ref")"
    src_line_val=$(safe_int "$source_line")
    src_end_line_val=$(safe_int "$source_end_line")
    if [ "$src_line_val" -gt 0 ]; then src_fields="$src_fields,$(json_number "line" "$src_line_val")"; fi
    if [ "$src_end_line_val" -gt 0 ]; then src_fields="$src_fields,$(json_number "end_line" "$src_end_line_val")"; fi
    if [ -n "$source_excerpt" ]; then src_fields="$src_fields,$(json_string "excerpt" "$(sanitize_text "$source_excerpt")")"; fi
    sources_json="[{${src_fields}}]"
  else
    die "Missing required source: provide --source-ref (and optionally --source-type) or use --from-json with a sources array"
  fi
fi

# Extract primary source ref for fingerprinting
primary_source_ref=$(extract_primary_source_ref "$sources_json")

# Validate required narrative fields
validate_required_field "expected_outcome" "$expected_outcome"
validate_required_field "actual_outcome" "$actual_outcome"
validate_required_field "reading" "$reading"

# Validate impact
if [ -z "$impact" ]; then
  die "Missing required field: --impact (blocked, degraded, noisy, or continued)"
fi
impact=$(normalize_impact "$impact")

# Sanitize narrative fields
title=$(sanitize_text "$title")
expected_outcome=$(sanitize_text "$expected_outcome")
actual_outcome=$(sanitize_text "$actual_outcome")
reading=$(sanitize_text "$reading")
hindsight=$(sanitize_text "$hindsight")

# Validate narrative depth
validate_narrative_length "expected_outcome" "$expected_outcome" 15
validate_narrative_length "actual_outcome" "$actual_outcome" 15
validate_narrative_length "reading" "$reading" 30

# Build tags and aliases JSON arrays (normalized to lowercase)
tags_json=$(csv_to_json_array "$tags_csv")
aliases_json=$(csv_to_json_array "$aliases_csv")

# Auto-title from actual_outcome if not provided
if [ -z "$(trim "$title")" ]; then
  title=$(truncate_line "$actual_outcome" 80)
fi

event_date=$(date -u '+%Y-%m-%d')
fingerprint=$(build_event_fingerprint "$primary_source_ref" "$event_date" "$fingerprint_key")
entry_number=0
if [ -f "$events_file" ]; then
  entry_number=$(wc -l <"$events_file" | tr -d ' ')
fi
entry_number=$((entry_number + 1))
event_id=$(printf 'evt-%04d' "$entry_number")
recorded=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
index_file=$events_dir/INDEX.md

# Emit event JSON
tmp_event=$(mktemp "$events_dir/.event.XXXXXX.tmp")
{
  printf '{'
  printf '%s,' "$(json_string "event_id" "$event_id")"
  printf '%s,' "$(json_string "recorded_at" "$recorded")"
  printf '%s,' "$(json_string "fingerprint" "$fingerprint")"
  printf '%s,' "$(json_string "title" "$title")"
  printf '%s,' "$(json_string "events_file" "$events_file")"
  printf '%s,' "$(json_string "repo_root" "$repo_root")"
  printf '%s,' "$(json_string "expected_outcome" "$expected_outcome")"
  printf '%s,' "$(json_string "actual_outcome" "$actual_outcome")"
  printf '%s,' "$(json_string "reading" "$reading")"
  json_string_if "hindsight" "$hindsight"
  printf '"sources":%s,' "$sources_json"
  printf '%s,' "$(json_string "impact" "$impact")"
  printf '"tags":%s,' "$tags_json"
  printf '"aliases":%s' "$aliases_json"
  printf '}\n'
} >"$tmp_event"
cat "$tmp_event" >>"$events_file"
rm -f "$tmp_event"

sh "$SCRIPT_DIR/build-index.sh" --events-file "$events_file" >/dev/null

printf 'FRICTION_EVENTS_FILE=%s\n' "$events_file"
printf 'FRICTION_INDEX_FILE=%s\n' "$index_file"
printf 'FRICTION_EVENT_ID=%s\n' "$event_id"
if [ -n "$repo_root" ]; then
  printf 'FRICTION_REPO_ROOT=%s\n' "$repo_root"
fi

# Show existing tags and aliases for reference
existing_tags=$(extract_all_tags "$events_file")
existing_aliases=$(extract_all_aliases "$events_file")
printf '\n'
if [ -n "$existing_tags" ]; then
  printf 'All tags in this stream: %s\n' "$existing_tags"
fi
if [ -n "$existing_aliases" ]; then
  printf 'All aliases in this stream: %s\n' "$existing_aliases"
fi
printf 'To add tags:    sh %s/report-friction.sh --add-tags %s "tag1,tag2"\n' "$SCRIPT_DIR" "$event_id"
printf 'To add aliases: sh %s/report-friction.sh --add-aliases %s "alias1,alias2"\n' "$SCRIPT_DIR" "$event_id"
