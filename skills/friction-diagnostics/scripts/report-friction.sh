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
  --instruction-source TEXT
  --instruction-text TEXT
  --action-taken TEXT
  --expected-outcome TEXT
  --actual-outcome TEXT
  --interpretation TEXT

Identity and context:
  --agent TEXT
  --agent-kind TEXT
  --role TEXT
  --repo-root PATH
  --privacy-tier VALUE

Classification overrides:
  --observed-surface VALUE
  --surface VALUE
  --mode VALUE
  --run-effect VALUE
  --guidance-quality VALUE
  --impact VALUE
  --confidence VALUE
  --evidence-type VALUE

Optional context:
  --command TEXT
  --tool-name TEXT
  --exit-code INT
  --stderr TEXT
  --stdout-excerpt TEXT
  --owner-hint TEXT
  --component-hint TEXT
  --incident-status VALUE
  --workaround-used BOOL
  --workaround-note TEXT
  --retries-lost INT
  --minutes-lost INT
  --fingerprint-key TEXT
  --tags CSV
  --quick
  --force

Anchor fields:
  --anchor-kind TEXT
  --anchor-path TEXT
  --anchor-line INT
  --anchor-end-line INT
  --anchor-symbol TEXT
  --anchor-section TEXT
  --anchor-url TEXT
  --anchor-selector TEXT
  --anchor-label TEXT

Other:
  --help
EOF
}

events_file=${FRICTION_EVENTS_FILE-}
from_json=
title=
instruction_source=
instruction_text=
action_taken=
expected_outcome=
actual_outcome=
interpretation=
agent_name=${FRICTION_AGENT_NAME-}
agent_kind=${FRICTION_AGENT_KIND-}
role=
repo_root=
privacy_tier=${FRICTION_PRIVACY_TIER-private}
observed_surface=
surface=
mode=
run_effect=
guidance_quality=
impact=
confidence=
evidence_type=
command_text=
tool_name=
exit_code=
stderr_text=
stdout_excerpt=
owner_hint=
component_hint=
incident_status=
workaround_used=false
workaround_note=
retries_lost=0
minutes_lost=0
fingerprint_key=
tags=
quick_capture=false
force_capture=false
anchor_kind=
anchor_path=
anchor_line=
anchor_end_line=
anchor_symbol=
anchor_section=
anchor_url=
anchor_selector=
anchor_label=
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
  json_helper=$(mktemp "${TMPDIR:-/tmp}/friction-json-helper.XXXXXX.py")
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

required = [
    "instruction_source",
    "instruction_text",
    "action_taken",
    "expected_outcome",
    "actual_outcome",
    "interpretation",
]
errors = []
for key in required:
    value = data.get(key)
    if value is None:
        errors.append(f"missing required field: {key}")
    elif not isinstance(value, str):
        errors.append(f"field must be a string: {key}")
    elif value.strip() == "":
        errors.append(f"field must not be blank: {key}")

anchors = data.get("anchors")
anchor = None
if anchors is not None:
    if not isinstance(anchors, list):
        errors.append("field must be an array when present: anchors")
    elif anchors:
        if not isinstance(anchors[0], dict):
            errors.append("anchors[0] must be an object")
        else:
            anchor = anchors[0]

if errors:
    print("Invalid friction payload for --from-json", file=sys.stderr)
    for item in errors:
      print(f"- {item}", file=sys.stderr)
    sys.exit(3)

keys = [
    ("title", "json_title"),
    ("instruction_source", "json_instruction_source"),
    ("instruction_text", "json_instruction_text"),
    ("action_taken", "json_action_taken"),
    ("expected_outcome", "json_expected_outcome"),
    ("actual_outcome", "json_actual_outcome"),
    ("interpretation", "json_interpretation"),
    ("agent_name", "json_agent_name"),
    ("agent_kind", "json_agent_kind"),
    ("role", "json_role"),
    ("repo_root", "json_repo_root"),
    ("privacy_tier", "json_privacy_tier"),
    ("observed_surface", "json_observed_surface"),
    ("surface", "json_surface"),
    ("mode", "json_mode"),
    ("run_effect", "json_run_effect"),
    ("guidance_quality", "json_guidance_quality"),
    ("impact", "json_impact"),
    ("confidence", "json_confidence"),
    ("evidence_type", "json_evidence_type"),
    ("command", "json_command_text"),
    ("tool_name", "json_tool_name"),
    ("exit_code", "json_exit_code"),
    ("stderr", "json_stderr_text"),
    ("stdout_excerpt", "json_stdout_excerpt"),
    ("owner_hint", "json_owner_hint"),
    ("component_hint", "json_component_hint"),
    ("incident_status", "json_incident_status"),
    ("workaround_used", "json_workaround_used"),
    ("workaround_note", "json_workaround_note"),
    ("retries_lost", "json_retries_lost"),
    ("minutes_lost", "json_minutes_lost"),
    ("fingerprint_key", "json_fingerprint_key"),
    ("tags", "json_tags"),
    ("quick", "json_quick_capture"),
    ("force", "json_force_capture"),
]

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

for key, var_name in keys:
    value = normalize(data.get(key))
    if value is not None:
        print(f"{var_name}={shlex.quote(value)}")

if anchor:
    for key, var_name in [
        ("kind", "json_anchor_kind"),
        ("path", "json_anchor_path"),
        ("line", "json_anchor_line"),
        ("end_line", "json_anchor_end_line"),
        ("symbol", "json_anchor_symbol"),
        ("section", "json_anchor_section"),
        ("url", "json_anchor_url"),
        ("selector", "json_anchor_selector"),
        ("label", "json_anchor_label"),
    ]:
        value = normalize(anchor.get(key))
        if value is not None:
            print(f"{var_name}={shlex.quote(value)}")
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
    --instruction-source) instruction_source=${2-}; shift 2 ;;
    --instruction-text) instruction_text=${2-}; shift 2 ;;
    --action-taken) action_taken=${2-}; shift 2 ;;
    --expected-outcome) expected_outcome=${2-}; shift 2 ;;
    --actual-outcome) actual_outcome=${2-}; shift 2 ;;
    --interpretation) interpretation=${2-}; shift 2 ;;
    --agent) agent_name=${2-}; shift 2 ;;
    --agent-kind) agent_kind=${2-}; shift 2 ;;
    --role) role=${2-}; shift 2 ;;
    --repo-root) repo_root=${2-}; shift 2 ;;
    --privacy-tier) privacy_tier=${2-}; shift 2 ;;
    --observed-surface) observed_surface=${2-}; shift 2 ;;
    --surface) surface=${2-}; shift 2 ;;
    --mode) mode=${2-}; shift 2 ;;
    --run-effect) run_effect=${2-}; shift 2 ;;
    --guidance-quality) guidance_quality=${2-}; shift 2 ;;
    --impact) impact=${2-}; shift 2 ;;
    --confidence) confidence=${2-}; shift 2 ;;
    --evidence-type) evidence_type=${2-}; shift 2 ;;
    --command) command_text=${2-}; shift 2 ;;
    --tool-name) tool_name=${2-}; shift 2 ;;
    --exit-code) exit_code=${2-}; shift 2 ;;
    --stderr) stderr_text=${2-}; shift 2 ;;
    --stdout-excerpt) stdout_excerpt=${2-}; shift 2 ;;
    --owner-hint) owner_hint=${2-}; shift 2 ;;
    --component-hint) component_hint=${2-}; shift 2 ;;
    --incident-status) incident_status=${2-}; shift 2 ;;
    --workaround-used) workaround_used=${2-}; shift 2 ;;
    --workaround-note) workaround_note=${2-}; shift 2 ;;
    --retries-lost) retries_lost=${2-}; shift 2 ;;
    --minutes-lost) minutes_lost=${2-}; shift 2 ;;
    --fingerprint-key) fingerprint_key=${2-}; shift 2 ;;
    --tags) tags=${2-}; shift 2 ;;
    --quick) quick_capture=true; shift ;;
    --force) force_capture=true; shift ;;
    --anchor-kind) anchor_kind=${2-}; shift 2 ;;
    --anchor-path) anchor_path=${2-}; shift 2 ;;
    --anchor-line) anchor_line=${2-}; shift 2 ;;
    --anchor-end-line) anchor_end_line=${2-}; shift 2 ;;
    --anchor-symbol) anchor_symbol=${2-}; shift 2 ;;
    --anchor-section) anchor_section=${2-}; shift 2 ;;
    --anchor-url) anchor_url=${2-}; shift 2 ;;
    --anchor-selector) anchor_selector=${2-}; shift 2 ;;
    --anchor-label) anchor_label=${2-}; shift 2 ;;
    --help|-h) print_help; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
done

if [ -n "$from_json" ]; then
  load_json_overrides "$from_json"
  title=$(load_json_field "$title" "" json_title)
  instruction_source=$(load_json_field "$instruction_source" "" json_instruction_source)
  instruction_text=$(load_json_field "$instruction_text" "" json_instruction_text)
  action_taken=$(load_json_field "$action_taken" "" json_action_taken)
  expected_outcome=$(load_json_field "$expected_outcome" "" json_expected_outcome)
  actual_outcome=$(load_json_field "$actual_outcome" "" json_actual_outcome)
  interpretation=$(load_json_field "$interpretation" "" json_interpretation)
  agent_name=$(load_json_field "$agent_name" "" json_agent_name)
  agent_kind=$(load_json_field "$agent_kind" "" json_agent_kind)
  role=$(load_json_field "$role" "" json_role)
  repo_root=$(load_json_field "$repo_root" "" json_repo_root)
  privacy_tier=$(load_json_field "$privacy_tier" "private" json_privacy_tier)
  observed_surface=$(load_json_field "$observed_surface" "" json_observed_surface)
  surface=$(load_json_field "$surface" "" json_surface)
  mode=$(load_json_field "$mode" "" json_mode)
  run_effect=$(load_json_field "$run_effect" "" json_run_effect)
  guidance_quality=$(load_json_field "$guidance_quality" "" json_guidance_quality)
  impact=$(load_json_field "$impact" "" json_impact)
  confidence=$(load_json_field "$confidence" "" json_confidence)
  evidence_type=$(load_json_field "$evidence_type" "" json_evidence_type)
  command_text=$(load_json_field "$command_text" "" json_command_text)
  tool_name=$(load_json_field "$tool_name" "" json_tool_name)
  exit_code=$(load_json_field "$exit_code" "" json_exit_code)
  stderr_text=$(load_json_field "$stderr_text" "" json_stderr_text)
  stdout_excerpt=$(load_json_field "$stdout_excerpt" "" json_stdout_excerpt)
  owner_hint=$(load_json_field "$owner_hint" "" json_owner_hint)
  component_hint=$(load_json_field "$component_hint" "" json_component_hint)
  incident_status=$(load_json_field "$incident_status" "" json_incident_status)
  workaround_used=$(load_json_field "$workaround_used" "false" json_workaround_used)
  workaround_note=$(load_json_field "$workaround_note" "" json_workaround_note)
  retries_lost=$(load_json_field "$retries_lost" "0" json_retries_lost)
  minutes_lost=$(load_json_field "$minutes_lost" "0" json_minutes_lost)
  fingerprint_key=$(load_json_field "$fingerprint_key" "" json_fingerprint_key)
  tags=$(load_json_field "$tags" "" json_tags)
  quick_capture=$(load_json_field "$quick_capture" "false" json_quick_capture)
  force_capture=$(load_json_field "$force_capture" "false" json_force_capture)
  anchor_kind=$(load_json_field "$anchor_kind" "" json_anchor_kind)
  anchor_path=$(load_json_field "$anchor_path" "" json_anchor_path)
  anchor_line=$(load_json_field "$anchor_line" "" json_anchor_line)
  anchor_end_line=$(load_json_field "$anchor_end_line" "" json_anchor_end_line)
  anchor_symbol=$(load_json_field "$anchor_symbol" "" json_anchor_symbol)
  anchor_section=$(load_json_field "$anchor_section" "" json_anchor_section)
  anchor_url=$(load_json_field "$anchor_url" "" json_anchor_url)
  anchor_selector=$(load_json_field "$anchor_selector" "" json_anchor_selector)
  anchor_label=$(load_json_field "$anchor_label" "" json_anchor_label)
fi

if [ -z "$events_file" ]; then
  events_file=$(default_events_file)
fi
events_dir=$(dirname "$events_file")
mkdir -p "$events_dir"
acquire_report_lock "$events_dir"

if [ -z "$repo_root" ]; then
  repo_root=$(git_repo_root)
fi

validate_required_field "instruction_source" "$instruction_source"
validate_required_field "instruction_text" "$instruction_text"
validate_required_field "action_taken" "$action_taken"
validate_required_field "expected_outcome" "$expected_outcome"
validate_required_field "actual_outcome" "$actual_outcome"
validate_required_field "interpretation" "$interpretation"

title_original=$title
instruction_source_original=$instruction_source
instruction_text_original=$instruction_text
action_taken_original=$action_taken
expected_outcome_original=$expected_outcome
actual_outcome_original=$actual_outcome
interpretation_original=$interpretation
command_original=$command_text
tool_name_original=$tool_name
stderr_original=$stderr_text
stdout_original=$stdout_excerpt
owner_hint_original=$owner_hint
component_hint_original=$component_hint
workaround_note_original=$workaround_note

title=$(sanitize_text "$title")
instruction_source=$(sanitize_text "$instruction_source")
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
anchor_kind=$(sanitize_text "$anchor_kind")
anchor_path=$(sanitize_text "$anchor_path")
anchor_symbol=$(sanitize_text "$anchor_symbol")
anchor_section=$(sanitize_text "$anchor_section")
anchor_url=$(sanitize_text "$anchor_url")
anchor_selector=$(sanitize_text "$anchor_selector")
anchor_label=$(sanitize_text "$anchor_label")

redaction_applied=false
if [ "$title" != "$title_original" ] ||
  [ "$instruction_source" != "$instruction_source_original" ] ||
  [ "$instruction_text" != "$instruction_text_original" ] ||
  [ "$action_taken" != "$action_taken_original" ] ||
  [ "$expected_outcome" != "$expected_outcome_original" ] ||
  [ "$actual_outcome" != "$actual_outcome_original" ] ||
  [ "$interpretation" != "$interpretation_original" ] ||
  [ "$command_text" != "$command_original" ] ||
  [ "$tool_name" != "$tool_name_original" ] ||
  [ "$stderr_text" != "$stderr_original" ] ||
  [ "$stdout_excerpt" != "$stdout_original" ] ||
  [ "$owner_hint" != "$owner_hint_original" ] ||
  [ "$component_hint" != "$component_hint_original" ] ||
  [ "$workaround_note" != "$workaround_note_original" ]; then
  redaction_applied=true
fi

provenance_source=unspecified
if [ -n "$(trim "$agent_name")$(trim "$agent_kind")$(trim "$role")" ]; then
  provenance_source=explicit
fi

if [ -z "$(trim "$title")" ]; then
  title=$(truncate_line "$actual_outcome" 72)
fi

cat_output=$(
  sh "$SCRIPT_DIR/categorize.sh" \
    --instruction-source "$instruction_source" \
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
    --confidence "$confidence" \
    --evidence-type "$evidence_type"
)

final_observed_surface=
final_surface=
final_mode=
final_run_effect=
final_guidance_quality=
final_confidence=
final_evidence_type=
final_derived_category=
final_taxonomy_version=
final_tags=
while IFS='=' read -r key value; do
  case "$key" in
    observed_surface) final_observed_surface=$value ;;
    surface) final_surface=$value ;;
    mode) final_mode=$value ;;
    run_effect) final_run_effect=$value ;;
    guidance_quality) final_guidance_quality=$value ;;
    confidence) final_confidence=$value ;;
    evidence_type) final_evidence_type=$value ;;
    derived_category) final_derived_category=$value ;;
    taxonomy_version) final_taxonomy_version=$value ;;
    tags) final_tags=$value ;;
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
evidence_type=$final_evidence_type
derived_category=$final_derived_category
taxonomy_version=$final_taxonomy_version

merged_tags=$final_tags
if [ -n "$tags" ]; then
  normalized=$(printf '%s' "$tags" | sed 's/[[:space:]]*,[[:space:]]*/,/g')
  old_ifs=$IFS
  IFS=,
  for item in $normalized; do
    item=$(trim "$item")
    merged_tags=$(append_csv "$merged_tags" "$item")
  done
  IFS=$old_ifs
fi
tags=$merged_tags

workaround_used=$(normalize_bool "$workaround_used")
quick_capture=$(normalize_bool "$quick_capture")
force_capture=$(normalize_bool "$force_capture")
retries_lost=$(safe_int "$retries_lost")
minutes_lost=$(safe_int "$minutes_lost")
exit_code_value=$(safe_int "$exit_code")
privacy_tier=$(normalize_privacy_tier "$privacy_tier")
if [ -z "$incident_status" ]; then
  if [ "$workaround_used" = "true" ]; then
    incident_status=mitigated
  else
    incident_status=open
  fi
fi
case "$incident_status" in
  open|mitigated|resolved|stale) ;;
  *) die "Unsupported incident status: $incident_status" ;;
esac

fingerprint=$(build_event_fingerprint "$surface" "$mode" "$instruction_source" "$actual_outcome" "$action_taken" "$title" "$fingerprint_key")
incident_id=inc-$fingerprint
entry_number=0
if [ -f "$events_file" ]; then
  entry_number=$(wc -l <"$events_file" | tr -d ' ')
fi
entry_number=$((entry_number + 1))
event_id=$(printf 'evt-%04d' "$entry_number")
recorded=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
index_file=$events_dir/INDEX.md
title_line=$(truncate_line "$title" 120)

anchor_line_value=$(safe_int "$anchor_line")
anchor_end_line_value=$(safe_int "$anchor_end_line")
anchors_json='[]'
if [ -n "$anchor_kind$anchor_path$anchor_symbol$anchor_section$anchor_url$anchor_selector$anchor_label" ] || [ "$anchor_line_value" -gt 0 ] || [ "$anchor_end_line_value" -gt 0 ]; then
  anchor_fields=
  if [ -n "$anchor_kind" ]; then anchor_fields=$(append_csv "$anchor_fields" "$(json_string "kind" "$anchor_kind")"); fi
  if [ -n "$anchor_path" ]; then anchor_fields=$(append_csv "$anchor_fields" "$(json_string "path" "$anchor_path")"); fi
  if [ "$anchor_line_value" -gt 0 ]; then anchor_fields=$(append_csv "$anchor_fields" "$(json_number "line" "$anchor_line_value")"); fi
  if [ "$anchor_end_line_value" -gt 0 ]; then anchor_fields=$(append_csv "$anchor_fields" "$(json_number "end_line" "$anchor_end_line_value")"); fi
  if [ -n "$anchor_symbol" ]; then anchor_fields=$(append_csv "$anchor_fields" "$(json_string "symbol" "$anchor_symbol")"); fi
  if [ -n "$anchor_section" ]; then anchor_fields=$(append_csv "$anchor_fields" "$(json_string "section" "$anchor_section")"); fi
  if [ -n "$anchor_url" ]; then anchor_fields=$(append_csv "$anchor_fields" "$(json_string "url" "$anchor_url")"); fi
  if [ -n "$anchor_selector" ]; then anchor_fields=$(append_csv "$anchor_fields" "$(json_string "selector" "$anchor_selector")"); fi
  if [ -n "$anchor_label" ]; then anchor_fields=$(append_csv "$anchor_fields" "$(json_string "label" "$anchor_label")"); fi
  anchors_json="[{${anchor_fields}}]"
fi

tmp_event=$(mktemp "$events_dir/.event.XXXXXX.tmp")
{
  printf '{'
  printf '%s,' "$(json_string "schema_version" "$SCHEMA_VERSION")"
  printf '%s,' "$(json_string "taxonomy_version" "$taxonomy_version")"
  printf '%s,' "$(json_string "event_id" "$event_id")"
  printf '%s,' "$(json_string "incident_id" "$incident_id")"
  printf '%s,' "$(json_string "fingerprint" "$fingerprint")"
  printf '%s,' "$(json_string "recorded_at" "$recorded")"
  printf '%s,' "$(json_string "events_file" "$events_file")"
  printf '%s,' "$(json_string "repo_root" "$repo_root")"
  printf '%s,' "$(json_string "agent_name" "$agent_name")"
  printf '%s,' "$(json_string "agent_kind" "$agent_kind")"
  printf '%s,' "$(json_string "role" "$role")"
  printf '%s,' "$(json_string "provenance_source" "$provenance_source")"
  printf '%s,' "$(json_bool "quick_capture" "$quick_capture")"
  printf '%s,' "$(json_bool "force_capture" "$force_capture")"
  printf '%s,' "$(json_bool "redaction_applied" "$redaction_applied")"
  printf '%s,' "$(json_string "title" "$title")"
  printf '%s,' "$(json_string "title_line" "$title_line")"
  printf '%s,' "$(json_string "instruction_source" "$instruction_source")"
  printf '%s,' "$(json_string "instruction_text" "$instruction_text")"
  printf '%s,' "$(json_string "action_taken" "$action_taken")"
  printf '%s,' "$(json_string "expected_outcome" "$expected_outcome")"
  printf '%s,' "$(json_string "actual_outcome" "$actual_outcome")"
  printf '%s,' "$(json_string "interpretation" "$interpretation")"
  printf '%s,' "$(json_string "command" "$command_text")"
  printf '%s,' "$(json_string "tool_name" "$tool_name")"
  printf '%s,' "$(json_string "stderr" "$stderr_text")"
  printf '%s,' "$(json_string "stdout_excerpt" "$stdout_excerpt")"
  printf '%s,' "$(json_string "owner_hint" "$owner_hint")"
  printf '%s,' "$(json_string "component_hint" "$component_hint")"
  printf '%s,' "$(json_string "workaround_note" "$workaround_note")"
  printf '%s,' "$(json_string "observed_surface" "$observed_surface")"
  printf '%s,' "$(json_string "surface" "$surface")"
  printf '%s,' "$(json_string "mode" "$mode")"
  printf '%s,' "$(json_string "run_effect" "$run_effect")"
  printf '%s,' "$(json_string "guidance_quality" "$guidance_quality")"
  printf '%s,' "$(json_string "confidence" "$confidence")"
  printf '%s,' "$(json_string "evidence_type" "$evidence_type")"
  printf '%s,' "$(json_string "derived_category" "$derived_category")"
  printf '%s,' "$(json_string "tags_csv" "$tags")"
  printf '%s,' "$(json_string "incident_status" "$incident_status")"
  printf '%s,' "$(json_bool "workaround_used" "$workaround_used")"
  printf '%s,' "$(json_number "exit_code" "$exit_code_value")"
  printf '%s,' "$(json_number "retries_lost" "$retries_lost")"
  printf '%s,' "$(json_number "minutes_lost" "$minutes_lost")"
  printf '%s,' "$(json_string "privacy_tier" "$privacy_tier")"
  printf '"anchors":%s' "$anchors_json"
  printf '}\n'
} >"$tmp_event"
cat "$tmp_event" >>"$events_file"
rm -f "$tmp_event"

sh "$SCRIPT_DIR/build-index.sh" --events-file "$events_file" >/dev/null

printf 'FRICTION_EVENTS_FILE=%s\n' "$events_file"
printf 'FRICTION_INDEX_FILE=%s\n' "$index_file"
if [ -n "$repo_root" ]; then
  printf 'FRICTION_REPO_ROOT=%s\n' "$repo_root"
fi
