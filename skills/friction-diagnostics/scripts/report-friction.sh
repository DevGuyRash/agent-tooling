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
  --instruction-text TEXT
  --action-taken TEXT
  --expected-outcome TEXT
  --actual-outcome TEXT
  --interpretation TEXT

Source fields (single source via CLI; use --from-json for multiple):
  --source-type TYPE     One of: file, url, system-instruction, conversation,
                         audio, visual, documentation, other
  --source-ref TEXT      Primary reference (filepath, URL, description)
  --source-line INT      Start line (for files)
  --source-end-line INT  End line (for file ranges)
  --source-symbol TEXT   Function, class, section, or heading name
  --source-excerpt TEXT  Relevant quoted text from the source
  --source-label TEXT    Human-readable description of this source's role

Identity and context:
  --agent TEXT
  --agent-kind TEXT
  --role TEXT
  --repo-root PATH

Classification overrides:
  --observed-surface VALUE
  --surface VALUE
  --mode VALUE
  --run-effect VALUE
  --guidance-quality VALUE   (0-4 integer or clear/ambiguous/misleading/not-applicable)
  --impact VALUE
  --confidence VALUE         (1-5 integer or low/medium/high)

Optional context:
  --command TEXT
  --tool-name TEXT
  --exit-code INT
  --stderr TEXT
  --stdout-excerpt TEXT
  --owner-hint TEXT
  --component-hint TEXT
  --workaround-used BOOL
  --workaround-note TEXT
  --retries-lost INT
  --minutes-lost INT
  --fingerprint-key TEXT

Tag management (run after initial event creation):
  --add-tags EVENT_ID "tag1,tag2,tag3"
                         Add tags to an existing event by event_id.
                         The report output suggests this command after each write.

Other:
  --help
EOF
}

events_file=${FRICTION_EVENTS_FILE-}
from_json=
title=
instruction_text=
action_taken=
expected_outcome=
actual_outcome=
interpretation=
agent_name=${FRICTION_AGENT_NAME-}
agent_kind=${FRICTION_AGENT_KIND-}
role=
repo_root=
observed_surface=
surface=
mode=
run_effect=
guidance_quality=
impact=
confidence=
command_text=
tool_name=
exit_code=
stderr_text=
stdout_excerpt=
owner_hint=
component_hint=
workaround_used=false
workaround_note=
retries_lost=0
minutes_lost=0
fingerprint_key=
add_tags_event_id=
add_tags_csv=
source_type=
source_ref=
source_line=
source_end_line=
source_symbol=
source_excerpt=
source_selector=
source_label=
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
  json_helper=$(mktemp "$(temp_root_dir)/friction-json-helper.XXXXXX.py")
  cat >"$json_helper" <<'PY'
import json
import shlex
import sys

path = sys.argv[1]
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
    print(hint_for(exc.msg), file=sys.stderr)
    sys.exit(2)

if not isinstance(data, dict):
    print("Invalid JSON input for --from-json", file=sys.stderr)
    print("Hint: the payload must be one JSON object.", file=sys.stderr)
    sys.exit(2)

VALID_SOURCE_TYPES = {
    "file", "url", "system-instruction", "conversation",
    "audio", "visual", "documentation", "other",
}

errors = []

# --- Build sources array (v3 native or backward-compat from v2) ---
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
    # Backward compatibility: build sources from v2 fields
    sources = []
    instr_src = data.get("instruction_source")
    if isinstance(instr_src, str) and instr_src.strip():
        sources.append({"type": "documentation", "ref": instr_src.strip()})

    anchors = data.get("anchors")
    if isinstance(anchors, list):
        for anc in anchors:
            if not isinstance(anc, dict):
                continue
            src = {}
            if anc.get("url"):
                src["type"] = "url"
                src["ref"] = anc["url"]
            elif anc.get("path"):
                src["type"] = "file"
                src["ref"] = anc["path"]
            else:
                src["type"] = "other"
                src["ref"] = anc.get("label", anc.get("section", "unknown"))
            for k in ("line", "end_line", "symbol", "section", "selector", "label"):
                if anc.get(k) is not None:
                    src[k] = anc[k]
            # Deduplicate: skip if same ref already present from instruction_source
            if not any(s.get("ref") == src.get("ref") for s in sources):
                sources.append(src)

    if not sources:
        errors.append(
            "missing sources array (or legacy instruction_source / anchors fields)"
        )

# --- Validate required narrative fields ---
required_narrative = [
    "instruction_text",
    "action_taken",
    "expected_outcome",
    "actual_outcome",
    "interpretation",
]
for key in required_narrative:
    value = data.get(key)
    if value is None:
        errors.append(f"missing required field: {key}")
    elif not isinstance(value, str):
        errors.append(f"field must be a string: {key}")
    elif value.strip() == "":
        errors.append(f"field must not be blank: {key}")

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
    ("instruction_text", "json_instruction_text"),
    ("action_taken", "json_action_taken"),
    ("expected_outcome", "json_expected_outcome"),
    ("actual_outcome", "json_actual_outcome"),
    ("interpretation", "json_interpretation"),
    ("agent_name", "json_agent_name"),
    ("agent_kind", "json_agent_kind"),
    ("role", "json_role"),
    ("repo_root", "json_repo_root"),
    ("observed_surface", "json_observed_surface"),
    ("surface", "json_surface"),
    ("mode", "json_mode"),
    ("run_effect", "json_run_effect"),
    ("guidance_quality", "json_guidance_quality"),
    ("impact", "json_impact"),
    ("confidence", "json_confidence"),
    ("command", "json_command_text"),
    ("tool_name", "json_tool_name"),
    ("exit_code", "json_exit_code"),
    ("stderr", "json_stderr_text"),
    ("stdout_excerpt", "json_stdout_excerpt"),
    ("owner_hint", "json_owner_hint"),
    ("component_hint", "json_component_hint"),
    ("workaround_used", "json_workaround_used"),
    ("workaround_note", "json_workaround_note"),
    ("retries_lost", "json_retries_lost"),
    ("minutes_lost", "json_minutes_lost"),
    ("fingerprint_key", "json_fingerprint_key"),
]

for key, var_name in keys:
    value = normalize(data.get(key))
    if value is not None:
        print(f"{var_name}={shlex.quote(value)}")

# Emit sources as JSON for shell to embed directly
print(f"json_sources_json={shlex.quote(json.dumps(sources, ensure_ascii=False))}")
PY
  json_output=$(python3 "$json_helper" "$path") || {
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

validate_required_field() {
  label=$1
  value=$2
  if [ -z "$(trim "$value")" ]; then
    die "Missing required field: $label"
  fi
}

while [ $# -gt 0 ]; do
  case "$1" in
    --events-file) events_file=${2-}; shift 2 ;;
    --from-json) from_json=${2-}; shift 2 ;;
    --title) title=${2-}; shift 2 ;;
    --instruction-text) instruction_text=${2-}; shift 2 ;;
    --action-taken) action_taken=${2-}; shift 2 ;;
    --expected-outcome) expected_outcome=${2-}; shift 2 ;;
    --actual-outcome) actual_outcome=${2-}; shift 2 ;;
    --interpretation) interpretation=${2-}; shift 2 ;;
    --agent) agent_name=${2-}; shift 2 ;;
    --agent-kind) agent_kind=${2-}; shift 2 ;;
    --role) role=${2-}; shift 2 ;;
    --repo-root) repo_root=${2-}; shift 2 ;;
    --observed-surface) observed_surface=${2-}; shift 2 ;;
    --surface) surface=${2-}; shift 2 ;;
    --mode) mode=${2-}; shift 2 ;;
    --run-effect) run_effect=${2-}; shift 2 ;;
    --guidance-quality) guidance_quality=${2-}; shift 2 ;;
    --impact) impact=${2-}; shift 2 ;;
    --confidence) confidence=${2-}; shift 2 ;;
    --command) command_text=${2-}; shift 2 ;;
    --tool-name) tool_name=${2-}; shift 2 ;;
    --exit-code) exit_code=${2-}; shift 2 ;;
    --stderr) stderr_text=${2-}; shift 2 ;;
    --stdout-excerpt) stdout_excerpt=${2-}; shift 2 ;;
    --owner-hint) owner_hint=${2-}; shift 2 ;;
    --component-hint) component_hint=${2-}; shift 2 ;;
    --workaround-used) workaround_used=${2-}; shift 2 ;;
    --workaround-note) workaround_note=${2-}; shift 2 ;;
    --retries-lost) retries_lost=${2-}; shift 2 ;;
    --minutes-lost) minutes_lost=${2-}; shift 2 ;;
    --fingerprint-key) fingerprint_key=${2-}; shift 2 ;;
    --add-tags) add_tags_event_id=${2-}; add_tags_csv=${3-}; shift 3 ;;
    --source-type) source_type=${2-}; shift 2 ;;
    --source-ref) source_ref=${2-}; shift 2 ;;
    --source-line) source_line=${2-}; shift 2 ;;
    --source-end-line) source_end_line=${2-}; shift 2 ;;
    --source-symbol) source_symbol=${2-}; shift 2 ;;
    --source-excerpt) source_excerpt=${2-}; shift 2 ;;
    --source-selector) source_selector=${2-}; shift 2 ;;
    --source-label) source_label=${2-}; shift 2 ;;
    --help|-h) print_help; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
done

if [ -n "$from_json" ]; then
  load_json_overrides "$from_json"
  title=$(load_json_field "$title" "" json_title)
  instruction_text=$(load_json_field "$instruction_text" "" json_instruction_text)
  action_taken=$(load_json_field "$action_taken" "" json_action_taken)
  expected_outcome=$(load_json_field "$expected_outcome" "" json_expected_outcome)
  actual_outcome=$(load_json_field "$actual_outcome" "" json_actual_outcome)
  interpretation=$(load_json_field "$interpretation" "" json_interpretation)
  agent_name=$(load_json_field "$agent_name" "" json_agent_name)
  agent_kind=$(load_json_field "$agent_kind" "" json_agent_kind)
  role=$(load_json_field "$role" "" json_role)
  repo_root=$(load_json_field "$repo_root" "" json_repo_root)
  observed_surface=$(load_json_field "$observed_surface" "" json_observed_surface)
  surface=$(load_json_field "$surface" "" json_surface)
  mode=$(load_json_field "$mode" "" json_mode)
  run_effect=$(load_json_field "$run_effect" "" json_run_effect)
  guidance_quality=$(load_json_field "$guidance_quality" "" json_guidance_quality)
  impact=$(load_json_field "$impact" "" json_impact)
  confidence=$(load_json_field "$confidence" "" json_confidence)
  command_text=$(load_json_field "$command_text" "" json_command_text)
  tool_name=$(load_json_field "$tool_name" "" json_tool_name)
  exit_code=$(load_json_field "$exit_code" "" json_exit_code)
  stderr_text=$(load_json_field "$stderr_text" "" json_stderr_text)
  stdout_excerpt=$(load_json_field "$stdout_excerpt" "" json_stdout_excerpt)
  owner_hint=$(load_json_field "$owner_hint" "" json_owner_hint)
  component_hint=$(load_json_field "$component_hint" "" json_component_hint)
  workaround_used=$(load_json_field "$workaround_used" "false" json_workaround_used)
  workaround_note=$(load_json_field "$workaround_note" "" json_workaround_note)
  retries_lost=$(load_json_field "$retries_lost" "0" json_retries_lost)
  minutes_lost=$(load_json_field "$minutes_lost" "0" json_minutes_lost)
  fingerprint_key=$(load_json_field "$fingerprint_key" "" json_fingerprint_key)
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
new_tags = [t.strip() for t in tags_csv.split(",") if t.strip()]
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
                existing = [t.strip() for t in existing.split(",") if t.strip()]
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

acquire_report_lock "$events_dir"

if [ -z "$repo_root" ]; then
  repo_root=$(git_repo_root)
fi

# Detect submodule context
superproject_root=$(git_superproject_root)
submodule_path=
if [ -n "$superproject_root" ] && [ -n "$repo_root" ]; then
  submodule_path=$(git_submodule_path "$superproject_root" "$repo_root")
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
    if [ -n "$source_symbol" ]; then src_fields="$src_fields,$(json_string "symbol" "$(sanitize_text "$source_symbol")")"; fi
    if [ -n "$source_excerpt" ]; then src_fields="$src_fields,$(json_string "excerpt" "$(sanitize_text "$source_excerpt")")"; fi
    if [ -n "$source_selector" ]; then src_fields="$src_fields,$(json_string "selector" "$(sanitize_text "$source_selector")")"; fi
    if [ -n "$source_label" ]; then src_fields="$src_fields,$(json_string "label" "$(sanitize_text "$source_label")")"; fi
    sources_json="[{${src_fields}}]"
  else
    die "Missing required source: provide --source-ref (and optionally --source-type) or use --from-json with a sources array"
  fi
fi

# Extract primary source ref for fingerprinting and categorizer
primary_source_ref=$(extract_primary_source_ref "$sources_json")


validate_required_field "instruction_text" "$instruction_text"
validate_required_field "action_taken" "$action_taken"
validate_required_field "expected_outcome" "$expected_outcome"
validate_required_field "actual_outcome" "$actual_outcome"
validate_required_field "interpretation" "$interpretation"

# Sanitize narrative fields
title=$(sanitize_text "$title")
instruction_text=$(sanitize_text "$instruction_text")
action_taken=$(sanitize_text "$action_taken")
expected_outcome=$(sanitize_text "$expected_outcome")
actual_outcome=$(sanitize_text "$actual_outcome")
interpretation=$(sanitize_text "$interpretation")
command_text=$(sanitize_text "$command_text")
tool_name=$(sanitize_text "$tool_name")
stderr_text=$(sanitize_excerpt "$stderr_text" 500)
stdout_excerpt=$(sanitize_excerpt "$stdout_excerpt" 500)
owner_hint=$(sanitize_text "$owner_hint")
component_hint=$(sanitize_text "$component_hint")
workaround_note=$(sanitize_text "$workaround_note")
agent_name=$(sanitize_text "$agent_name")
agent_kind=$(sanitize_text "$agent_kind")
role=$(sanitize_text "$role")

# Validate narrative depth
# Minimum lengths are spam filters, not quality enforcement.
# Quality is driven by EARS structural guidance in SKILL.md and AGENTS.md
# (multi-sentence mandates, quoting requirements, reasoning chain structure).
# These thresholds only reject obviously worthless entries.
validate_narrative_length "instruction_text" "$instruction_text" 10
validate_narrative_length "action_taken" "$action_taken" 20
validate_narrative_length "expected_outcome" "$expected_outcome" 15
validate_narrative_length "actual_outcome" "$actual_outcome" 15
validate_narrative_length "interpretation" "$interpretation" 30

provenance_source=unspecified
if [ -n "$(trim "$agent_name")$(trim "$agent_kind")$(trim "$role")" ]; then
  provenance_source=explicit
fi

# Run categorizer
cat_output=$(
  sh "$SCRIPT_DIR/categorize.sh" \
    --source-ref "$primary_source_ref" \
    --instruction-text "$instruction_text" \
    --action-taken "$action_taken" \
    --expected-outcome "$expected_outcome" \
    --actual-outcome "$actual_outcome" \
    --interpretation "$interpretation" \
    --command "$command_text" \
    --tool-name "$tool_name" \
    --stderr "$stderr_text" \
    --observed-surface "$observed_surface" \
    --surface "$surface" \
    --mode "$mode" \
    --run-effect "$run_effect" \
    --guidance-quality "$guidance_quality" \
    --impact "$impact" \
    --confidence "$confidence"
)

final_observed_surface=
final_surface=
final_mode=
final_run_effect=
final_guidance_quality=
final_confidence=
final_derived_category=
final_taxonomy_version=
while IFS='=' read -r key value; do
  case "$key" in
    observed_surface) final_observed_surface=$value ;;
    surface) final_surface=$value ;;
    mode) final_mode=$value ;;
    run_effect) final_run_effect=$value ;;
    guidance_quality) final_guidance_quality=$value ;;
    confidence) final_confidence=$value ;;
    derived_category) final_derived_category=$value ;;
    taxonomy_version) final_taxonomy_version=$value ;;
  esac
done <<EOF
$cat_output
EOF

observed_surface=$final_observed_surface
surface=$final_surface
mode=$final_mode
run_effect=$final_run_effect
guidance_quality=$final_guidance_quality
confidence=$final_confidence
derived_category=$final_derived_category
taxonomy_version=$final_taxonomy_version

# Tags are agent-curated via --add-tags after the event is written.
# Events are initially written with an empty tags array.
tags_json='[]'

# Normalize optional fields
workaround_used=$(normalize_bool "$workaround_used")
retries_lost=$(safe_int "$retries_lost")
minutes_lost=$(safe_int "$minutes_lost")
exit_code_value=$(safe_int "$exit_code")

# Auto-title: [surface/mode] prefix + actual_outcome excerpt
if [ -z "$(trim "$title")" ]; then
  title_prefix="[$surface/$mode]"
  title_body=$(truncate_line "$actual_outcome" 60)
  title="$title_prefix $title_body"
fi

event_date=$(date -u '+%Y-%m-%d')
fingerprint=$(build_event_fingerprint "$surface" "$mode" "$primary_source_ref" "$event_date" "$fingerprint_key")
incident_id=inc-$fingerprint
entry_number=0
if [ -f "$events_file" ]; then
  entry_number=$(wc -l <"$events_file" | tr -d ' ')
fi
entry_number=$((entry_number + 1))
event_id=$(printf 'evt-%04d' "$entry_number")
recorded=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
index_file=$events_dir/INDEX.md

# Emit event JSON with sparse optional fields
tmp_event=$(mktemp "$events_dir/.event.XXXXXX.tmp")
{
  printf '{'
  # Always-present metadata
  printf '%s,' "$(json_string "schema_version" "$SCHEMA_VERSION")"
  printf '%s,' "$(json_string "taxonomy_version" "$taxonomy_version")"
  printf '%s,' "$(json_string "event_id" "$event_id")"
  printf '%s,' "$(json_string "incident_id" "$incident_id")"
  printf '%s,' "$(json_string "fingerprint" "$fingerprint")"
  printf '%s,' "$(json_string "recorded_at" "$recorded")"
  printf '%s,' "$(json_string "events_file" "$events_file")"
  printf '%s,' "$(json_string "repo_root" "$repo_root")"
  json_string_if "superproject_root" "$superproject_root"
  json_string_if "submodule_path" "$submodule_path"
  # Identity (agent_name/agent_kind always present; role sparse)
  printf '%s,' "$(json_string "agent_name" "$agent_name")"
  printf '%s,' "$(json_string "agent_kind" "$agent_kind")"
  json_string_if "role" "$role"
  printf '%s,' "$(json_string "provenance_source" "$provenance_source")"
  # Core narrative (always present)
  printf '%s,' "$(json_string "title" "$title")"
  printf '%s,' "$(json_string "instruction_text" "$instruction_text")"
  printf '%s,' "$(json_string "action_taken" "$action_taken")"
  printf '%s,' "$(json_string "expected_outcome" "$expected_outcome")"
  printf '%s,' "$(json_string "actual_outcome" "$actual_outcome")"
  printf '%s,' "$(json_string "interpretation" "$interpretation")"
  # Sparse optional context
  json_string_if "command" "$command_text"
  json_string_if "tool_name" "$tool_name"
  json_string_if "stderr" "$stderr_text"
  json_string_if "stdout_excerpt" "$stdout_excerpt"
  json_string_if "owner_hint" "$owner_hint"
  json_string_if "component_hint" "$component_hint"
  json_string_if "workaround_note" "$workaround_note"
  # Classification (always present, numeric)
  printf '%s,' "$(json_string "observed_surface" "$observed_surface")"
  printf '%s,' "$(json_string "surface" "$surface")"
  printf '%s,' "$(json_string "mode" "$mode")"
  printf '%s,' "$(json_string "run_effect" "$run_effect")"
  printf '%s,' "$(json_number "guidance_quality" "$guidance_quality")"
  printf '%s,' "$(json_number "confidence" "$confidence")"
  printf '%s,' "$(json_string "derived_category" "$derived_category")"
  printf '"tags":%s,' "$tags_json"
  # Sparse impact fields
  json_bool_if "workaround_used" "$workaround_used"
  json_number_if "exit_code" "$exit_code_value"
  json_number_if "retries_lost" "$retries_lost"
  json_number_if "minutes_lost" "$minutes_lost"
  # Sources array (always present, replaces anchors + instruction_source)
  printf '"sources":%s' "$sources_json"
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

# Tag helper: show existing tags and suggest --add-tags command
existing_tags=$(extract_all_tags "$events_file")
printf '\n'
if [ -n "$existing_tags" ]; then
  printf 'All tags in this stream: %s\n' "$existing_tags"
else
  printf 'No tags in this stream yet.\n'
fi
printf 'To add tags to this event, run:\n'
printf '  sh %s/report-friction.sh --add-tags %s "tag1,tag2"\n' "$SCRIPT_DIR" "$event_id"
