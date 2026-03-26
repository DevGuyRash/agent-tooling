#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
. "$SCRIPT_DIR/_common.sh"

print_help() {
  cat <<'EOF'
Usage:
  sh scripts/report-friction.sh --log-file "$FRICTION_LOG_FILE" --title "..." [fields]
  sh scripts/report-friction.sh --task-dir "$FRICTION_TASK_DIR" --from-json event.json --agent orchestrator [fields]

Required:
  --log-file PATH
  or --task-dir PATH
  or auto-init via --task-summary TEXT plus --skill-path PATH

Structured input:
  --from-json PATH|-      Load event fields from a JSON object on disk or stdin.

Core fields:
  --title TEXT
  --instruction-source TEXT
  --instruction-text TEXT
  --action-taken TEXT
  --expected-outcome TEXT
  --actual-outcome TEXT
  --interpretation TEXT

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

Task selection and auto-init:
  --task-dir PATH
  --task-summary TEXT
  --agent TEXT
  --role TEXT
  --skill-path TEXT
  --base-dir PATH
  --help
EOF
}

log_file=${FRICTION_LOG_FILE-}
task_dir=${FRICTION_TASK_DIR-}
from_json=
auto_task_summary=
auto_agent=orchestrator
auto_skill_path=
auto_role=
auto_base_dir=
title=
instruction_source=
instruction_text=
action_taken=
expected_outcome=
actual_outcome=
interpretation=
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
log_file_explicit=false
task_dir_explicit=false
task_summary_explicit=false
lock_dir=
report_lock_acquired=0

cleanup_report_lock() {
  if [ "${report_lock_acquired:-0}" -eq 1 ] && [ -n "${lock_dir-}" ]; then
    rm -f "$lock_dir/pid" 2>/dev/null || true
    rmdir "$lock_dir" 2>/dev/null || true
  fi
}

acquire_report_lock() {
  target_task_dir=$1
  lock_dir=$target_task_dir/.report-friction.lock
  missing_pid_retries=0
  invalid_pid_retries=0
  while ! mkdir "$lock_dir" 2>/dev/null; do
    if [ ! -f "$lock_dir/pid" ]; then
      missing_pid_retries=$((missing_pid_retries + 1))
      invalid_pid_retries=0
      if [ "$missing_pid_retries" -ge 2 ]; then
        rmdir "$lock_dir" 2>/dev/null || true
        missing_pid_retries=0
        continue
      fi
      sleep 1
      continue
    fi

    lock_pid=$(sed -n '1p' "$lock_dir/pid" 2>/dev/null || true)
    case "$lock_pid" in
      '')
        missing_pid_retries=$((missing_pid_retries + 1))
        invalid_pid_retries=0
        if [ "$missing_pid_retries" -ge 2 ]; then
          rm -f "$lock_dir/pid" 2>/dev/null || true
          rmdir "$lock_dir" 2>/dev/null || true
          missing_pid_retries=0
          continue
        fi
        ;;
      *[!0-9]*)
        invalid_pid_retries=$((invalid_pid_retries + 1))
        missing_pid_retries=0
        if [ "$invalid_pid_retries" -ge 2 ]; then
          rm -f "$lock_dir/pid" 2>/dev/null || true
          rmdir "$lock_dir" 2>/dev/null || true
          invalid_pid_retries=0
          continue
        fi
        ;;
      *)
        missing_pid_retries=0
        invalid_pid_retries=0
        if ! kill -0 "$lock_pid" 2>/dev/null; then
          rm -f "$lock_dir/pid" 2>/dev/null || true
          rmdir "$lock_dir" 2>/dev/null || true
          continue
        fi
        ;;
    esac
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
  eval "$(
    python3 -c '
import json
import shlex
import sys

path = sys.argv[1]
if path == "-":
    data = json.load(sys.stdin)
else:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

keys = [
    ("title", "json_title"),
    ("instruction_source", "json_instruction_source"),
    ("instruction_text", "json_instruction_text"),
    ("action_taken", "json_action_taken"),
    ("expected_outcome", "json_expected_outcome"),
    ("actual_outcome", "json_actual_outcome"),
    ("interpretation", "json_interpretation"),
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
    return str(value)

for key, var_name in keys:
    value = normalize(data.get(key))
    if value is None:
        continue
    print(f"{var_name}={shlex.quote(value)}")
' "$path"
  )"
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

materialize_agent_artifacts() {
  target_task_dir=$1
  target_agent=$2
  target_role=$3
  session_file=$target_task_dir/SESSION.txt
  [ -f "$session_file" ] || die "SESSION.txt not found for task dir: $target_task_dir"

  task_summary_file=$(read_session_value "$session_file" FRICTION_TASK_SUMMARY_FILE)
  task_json_file=$(read_session_value "$session_file" FRICTION_TASK_JSON)
  events_file=$(read_session_value "$session_file" FRICTION_EVENTS_FILE)
  incidents_file=$(read_session_value "$session_file" FRICTION_INCIDENTS_FILE)
  index_file=$(read_session_value "$session_file" FRICTION_INDEX_FILE)
  storage_mode=$(read_session_value "$session_file" FRICTION_STORAGE_MODE)
  capture_mode=$(read_session_value "$session_file" FRICTION_CAPTURE_MODE)
  privacy_tier=$(read_session_value "$session_file" FRICTION_PRIVACY_TIER)
  export_dir=$(read_session_value "$session_file" FRICTION_EXPORT_DIR)
  skill_path=$(read_session_value "$session_file" FRICTION_SKILL_PATH)
  context_path=$(read_session_value "$session_file" FRICTION_CONTEXT_PATH)
  exports_dir=$target_task_dir/exports

  mkdir -p "$exports_dir"
  [ -f "$events_file" ] || : >"$events_file"
  if [ ! -f "$incidents_file" ]; then
    stamp=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
    printf '{%s,%s,%s,%s,%s,"incidents":[]}\n' \
      "$(json_string "schema_version" "$SCHEMA_VERSION")" \
      "$(json_string "generated_at" "$stamp")" \
      "$(json_string "task_id" "$(basename "$target_task_dir")")" \
      "$(json_number "event_count" "0")" \
      "$(json_number "incident_count" "0")" \
      >"$incidents_file"
  fi

  if [ -f "$task_json_file" ]; then
    tmp_task_json=$task_json_file.tmp.$$
    sed 's/"artifacts_materialized":false/"artifacts_materialized":true/' "$task_json_file" >"$tmp_task_json"
    mv -f "$tmp_task_json" "$task_json_file"
  fi

  agent_slug=$(slugify "$target_agent")
  agent_display=$target_agent
  if [ -n "$target_role" ]; then
    role_slug=$(slugify "$target_role")
    agent_slug="${agent_slug}-${role_slug}"
    agent_display="${target_agent} (${target_role})"
  fi
  agent_slug=$(bounded_slugify "$agent_slug" 227)

  existing_log=
  find "$target_task_dir" -type f -name '*.md' ! -name 'INDEX.md' | sort | while IFS= read -r candidate; do
    [ -n "$candidate" ] || continue
    candidate_agent=$(sed -n 's/^\*\*Agent:\*\* //p' "$candidate" | sed -n '1p')
    if [ "$candidate_agent" = "$agent_display" ]; then
      printf '%s\n' "$candidate"
    fi
  done | tail -1 >"$target_task_dir/.last-agent-log.$$"
  if [ -f "$target_task_dir/.last-agent-log.$$" ]; then
    existing_log=$(sed -n '1p' "$target_task_dir/.last-agent-log.$$")
    rm -f "$target_task_dir/.last-agent-log.$$"
  fi

  if [ -n "$existing_log" ]; then
    printf '%s\n' "$existing_log"
    return 0
  fi

  date_dir=$(date -u '+%Y-%m-%d')
  time_part=$(date -u '+%H-%M-%S')
  stamp=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
  dated_dir=$target_task_dir/$date_dir
  mkdir -p "$dated_dir"

  new_log=$dated_dir/${time_part}_${agent_slug}.md
  suffix=1
  while [ -e "$new_log" ]; do
    new_log=$dated_dir/${time_part}_${agent_slug}_$(printf '%02d' "$suffix").md
    suffix=$((suffix + 1))
  done
  descriptor_file=${new_log%.md}.descriptor.json
  task_summary=$(cat "$task_summary_file")

  {
    printf '# Friction Evidence Log: %s\n' "$(basename "$target_task_dir")"
    write_md_field "Created" "$stamp"
    write_md_field "Agent" "$agent_display"
    write_md_field "Task ID" "$(basename "$target_task_dir")"
    write_md_field "Task summary" "$task_summary"
    write_md_field "Storage mode" "$storage_mode"
    write_md_field "Capture mode" "$capture_mode"
    write_md_field "Privacy tier" "$privacy_tier"
    write_md_field "Skill path" "$skill_path"
    if [ -n "$context_path" ]; then
      write_md_field "Context path" "$context_path"
    fi
    if [ -n "$export_dir" ]; then
      write_md_field "Export dir" "$export_dir"
    fi
    write_md_field "Platform" "$(platform_name)"
    write_md_field "Schema version" "$SCHEMA_VERSION"
    printf -- '---\n'
  } >"$new_log"

  {
    printf '{'
    printf '%s,' "$(json_string "schema_version" "$SCHEMA_VERSION")"
    printf '%s,' "$(json_string "task_id" "$(basename "$target_task_dir")")"
    printf '%s,' "$(json_string "task_dir" "$target_task_dir")"
    printf '%s,' "$(json_string "log_file" "$new_log")"
    printf '%s,' "$(json_string "task_json" "$task_json_file")"
    printf '%s,' "$(json_string "events_file" "$events_file")"
    printf '%s,' "$(json_string "incidents_file" "$incidents_file")"
    printf '%s,' "$(json_string "index_file" "$index_file")"
    printf '%s,' "$(json_string "task_summary_file" "$task_summary_file")"
    printf '%s,' "$(json_string "storage_mode" "$storage_mode")"
    printf '%s,' "$(json_string "capture_mode" "$capture_mode")"
    printf '%s,' "$(json_string "privacy_tier" "$privacy_tier")"
    printf '%s' "$(json_string "export_dir" "$export_dir")"
    printf '}\n'
  } >"$descriptor_file"

  printf '%s\n' "$new_log"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --log-file) log_file=${2-}; log_file_explicit=true; shift 2 ;;
    --task-dir) task_dir=${2-}; task_dir_explicit=true; shift 2 ;;
    --from-json) from_json=${2-}; shift 2 ;;
    --title) title=${2-}; shift 2 ;;
    --instruction-source) instruction_source=${2-}; shift 2 ;;
    --instruction-text) instruction_text=${2-}; shift 2 ;;
    --action-taken) action_taken=${2-}; shift 2 ;;
    --expected-outcome) expected_outcome=${2-}; shift 2 ;;
    --actual-outcome) actual_outcome=${2-}; shift 2 ;;
    --interpretation) interpretation=${2-}; shift 2 ;;
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
    --task-summary) auto_task_summary=${2-}; task_summary_explicit=true; shift 2 ;;
    --agent) auto_agent=${2-}; shift 2 ;;
    --skill-path) auto_skill_path=${2-}; shift 2 ;;
    --role) auto_role=${2-}; shift 2 ;;
    --base-dir) auto_base_dir=${2-}; shift 2 ;;
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
fi

if [ "$task_summary_explicit" = "true" ] &&
  [ "$task_dir_explicit" != "true" ] &&
  [ "$log_file_explicit" != "true" ]; then
  task_dir=
  log_file=
fi

if [ -z "$task_dir" ] && [ -n "$log_file" ]; then
  task_dir=$(dirname "$(dirname "$log_file")")
fi

if [ -z "$task_dir" ]; then
  [ -n "$auto_task_summary" ] || die "--log-file, --task-dir, or --task-summary is required"
  [ -n "$auto_skill_path" ] || die "--skill-path is required for auto-init"
  set -- --task-summary "$auto_task_summary" --agent "$auto_agent" --skill-path "$auto_skill_path"
  if [ -n "${FRICTION_TASK_ID-}" ]; then
    set -- "$@" --task-id "$FRICTION_TASK_ID"
  fi
  if [ -n "$auto_role" ]; then
    set -- "$@" --role "$auto_role"
  fi
  if [ -n "$auto_base_dir" ]; then
    set -- "$@" --base-dir "$auto_base_dir"
  fi
  eval "$(sh "$SCRIPT_DIR/init-log.sh" "$@")"
  task_dir=$FRICTION_TASK_DIR
fi

[ -n "$task_dir" ] || die "--task-dir is required"
[ -d "$task_dir" ] || die "Task directory not found: $task_dir"
acquire_report_lock "$task_dir"
session_file=$task_dir/SESSION.txt
[ -f "$session_file" ] || die "SESSION.txt not found for task dir: $task_dir"

events_file=$(read_session_value "$session_file" FRICTION_EVENTS_FILE)
incidents_file=$(read_session_value "$session_file" FRICTION_INCIDENTS_FILE)
capture_mode=$(read_session_value "$session_file" FRICTION_CAPTURE_MODE)
privacy_tier=$(read_session_value "$session_file" FRICTION_PRIVACY_TIER)
[ -n "$events_file" ] || die "FRICTION_EVENTS_FILE missing from SESSION.txt"
[ -n "$capture_mode" ] || capture_mode=explicit
[ -n "$privacy_tier" ] || privacy_tier=private

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

if [ -z "$title" ]; then
  source_title=$(first_line "$actual_outcome")
  if [ -z "$source_title" ]; then
    source_title=$mode
  fi
  title=$(truncate_line "$source_title" 72)
fi

workaround_used=$(normalize_bool "$workaround_used")
quick_capture=$(normalize_bool "$quick_capture")
force_capture=$(normalize_bool "$force_capture")
retries_lost=$(safe_int "$retries_lost")
minutes_lost=$(safe_int "$minutes_lost")
exit_code_value=$(safe_int "$exit_code")
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
repeat_count=0
if [ -f "$events_file" ]; then
  repeat_count=$(grep -c "\"fingerprint\":\"$fingerprint\"" "$events_file" 2>/dev/null || true)
fi

should_skip=false
case "$capture_mode" in
  threshold)
    if [ "$force_capture" != "true" ] &&
      [ "$repeat_count" -eq 0 ] &&
      [ "$run_effect" != "blocked" ] &&
      [ "$guidance_quality" != "misleading" ] &&
      [ "$workaround_used" != "true" ] &&
      [ "$minutes_lost" -lt 5 ] &&
      [ "$retries_lost" -le 0 ]; then
      should_skip=true
    fi
    ;;
esac

if [ "$should_skip" = "true" ]; then
  exit 0
fi

if [ -z "$log_file" ] || [ ! -f "$log_file" ]; then
  log_file=$(materialize_agent_artifacts "$task_dir" "$auto_agent" "$auto_role")
fi

entry_number=0
if [ -f "$events_file" ]; then
  entry_number=$(wc -l <"$events_file" | tr -d ' ')
fi
entry_number=$((entry_number + 1))
event_id=$(printf 'evt-%04d' "$entry_number")
recorded=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
agent_display=$(sed -n 's/^\*\*Agent:\*\* //p' "$log_file" | sed -n '1p')
relative_log_file=${log_file#"$task_dir"/}
title_line=$(truncate_line "$title" 120)

{
  printf '{'
  printf '%s,' "$(json_string "schema_version" "$SCHEMA_VERSION")"
  printf '%s,' "$(json_string "taxonomy_version" "$taxonomy_version")"
  printf '%s,' "$(json_string "event_id" "$event_id")"
  printf '%s,' "$(json_string "incident_id" "$incident_id")"
  printf '%s,' "$(json_string "fingerprint" "$fingerprint")"
  printf '%s,' "$(json_string "recorded_at" "$recorded")"
  printf '%s,' "$(json_string "agent" "$agent_display")"
  printf '%s,' "$(json_string "log_file" "$relative_log_file")"
  printf '%s,' "$(json_bool "quick_capture" "$quick_capture")"
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
  printf '%s' "$(json_string "privacy_tier" "$privacy_tier")"
  printf '}\n'
} >>"$events_file"

if [ "$capture_mode" != "synthesis" ] || [ "$force_capture" = "true" ]; then
  {
    printf '\n'
    printf '## Event %s: %s\n' "$entry_number" "$title"
    write_md_field "Incident" "$incident_id"
    write_md_field "Recorded" "$recorded"
    write_md_field "Derived category" "$derived_category"
    write_md_field "Guidance quality" "$guidance_quality"
    write_md_field "Observed surface" "$observed_surface"
    write_md_field "Confidence" "$confidence"
    write_md_field "Evidence type" "$evidence_type"
    write_md_field "Status" "$incident_status"
    write_md_field "Tags" "$tags"
    write_md_field "Instruction source" "$instruction_source"
    write_md_field "Instruction text" "$instruction_text"
    write_md_field "Action taken" "$action_taken"
    write_md_field "Expected outcome" "$expected_outcome"
    write_md_field "Actual outcome" "$actual_outcome"
    write_md_field "Interpretation" "$interpretation"
    write_md_field "Command" "$command_text"
    write_md_field "Tool name" "$tool_name"
    if [ "$exit_code_value" -ne 0 ]; then
      write_md_field "Exit code" "$exit_code_value"
    fi
    write_md_field "stderr excerpt" "$stderr_text"
    write_md_field "stdout excerpt" "$stdout_excerpt"
    write_md_field "Owner hint" "$owner_hint"
    write_md_field "Component hint" "$component_hint"
    write_md_field "Retries lost" "$retries_lost"
    write_md_field "Minutes lost" "$minutes_lost"
    write_md_field "Workaround used" "$workaround_used"
    write_md_field "Workaround note" "$workaround_note"
    write_md_field "Quick capture" "$quick_capture"
    printf -- '---\n'
  } >>"$log_file"
fi

if [ -n "$incidents_file" ] && [ -f "$events_file" ]; then
  task_id_for_incidents=$(basename "$task_dir")
  incidents_updated=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
  awk -v schema="$SCHEMA_VERSION" -v gen="$incidents_updated" -v tid="$task_id_for_incidents" '
    function extract(line, key,    start, rest, val, ch) {
      start = "\"" key "\":\""
      if ((idx = index(line, start)) == 0) return ""
      rest = substr(line, idx + length(start))
      val = ""
      while (length(rest) > 0) {
        ch = substr(rest, 1, 1)
        if (ch == "\\") {
          val = val substr(rest, 1, 2)
          rest = substr(rest, 3)
        } else if (ch == "\"") {
          break
        } else {
          val = val ch
          rest = substr(rest, 2)
        }
      }
      return val
    }
    {
      if ($0 == "") next
      total++
      iid = extract($0, "incident_id")
      if (iid == "") next
      count[iid]++
      status[iid] = extract($0, "incident_status")
      if (!(iid in title)) {
        title[iid] = extract($0, "title_line")
        category[iid] = extract($0, "derived_category")
        order[++n] = iid
      }
    }
    END {
      printf "{\"schema_version\":\"%s\",", schema
      printf "\"generated_at\":\"%s\",", gen
      printf "\"task_id\":\"%s\",", tid
      printf "\"event_count\":%d,", total
      printf "\"incident_count\":%d,", n
      printf "\"incidents\":["
      for (i = 1; i <= n; i++) {
        iid = order[i]
        if (i > 1) printf ","
        printf "{\"incident_id\":\"%s\",", iid
        printf "\"title\":\"%s\",", title[iid]
        printf "\"derived_category\":\"%s\",", category[iid]
        printf "\"status\":\"%s\",", status[iid]
        printf "\"event_count\":%d}", count[iid]
      }
      printf "]}\n"
    }
  ' "$events_file" >"$incidents_file"
fi

sh "$SCRIPT_DIR/build-index.sh" --task-dir "$task_dir" >/dev/null
