#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
. "$SCRIPT_DIR/_common.sh"

print_help() {
  cat <<'EOF'
Usage:
  sh scripts/report-friction.sh --log-file "$FRICTION_LOG_FILE" --title "..." [fields]

Required:
  --log-file PATH

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
  --impact VALUE              Legacy alias.
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
  --incident-status VALUE     open | mitigated | resolved | stale
  --workaround-used BOOL
  --workaround-note TEXT
  --retries-lost INT
  --minutes-lost INT
  --fingerprint-key TEXT
  --tags CSV
  --quick
  --force

Auto-init (used when --log-file is not set):
  --task-summary TEXT    Passed to init-log.sh for auto-initialization.
  --agent TEXT           Passed to init-log.sh. Defaults to orchestrator.
  --skill-path TEXT      Passed to init-log.sh.
  --role TEXT            Passed to init-log.sh.
  --base-dir PATH        Passed to init-log.sh.
  --help
EOF
}

log_file=${FRICTION_LOG_FILE-}
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

while [ $# -gt 0 ]; do
  case "$1" in
    --log-file) log_file=${2-}; shift 2 ;;
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
    --task-summary) auto_task_summary=${2-}; shift 2 ;;
    --agent) auto_agent=${2-}; shift 2 ;;
    --skill-path) auto_skill_path=${2-}; shift 2 ;;
    --role) auto_role=${2-}; shift 2 ;;
    --base-dir) auto_base_dir=${2-}; shift 2 ;;
    --help|-h) print_help; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
done

# Auto-init: if no log file is set, bootstrap a session via init-log.sh
if [ -z "$log_file" ]; then
  [ -n "$auto_task_summary" ] || die "--log-file or --task-summary is required"
  [ -n "$auto_skill_path" ] || die "--skill-path is required for auto-init"
  set -- --task-summary "$auto_task_summary" --agent "$auto_agent" --skill-path "$auto_skill_path"
  if [ -n "$auto_role" ]; then
    set -- "$@" --role "$auto_role"
  fi
  if [ -n "$auto_base_dir" ]; then
    set -- "$@" --base-dir "$auto_base_dir"
  fi
  eval "$(sh "$SCRIPT_DIR/init-log.sh" "$@")"
  log_file=$FRICTION_LOG_FILE
fi

[ -n "$log_file" ] || die "--log-file is required"
[ -f "$log_file" ] || die "Log file not found: $log_file"

task_dir=$(dirname "$(dirname "$log_file")")
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
repeat_count=$(grep -c "\"fingerprint\":\"$fingerprint\"" "$events_file" 2>/dev/null || true)

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

# NOTE: event_id is a display sequence number, not a unique identity key.
# Concurrent report calls may assign the same number. The fingerprint field
# is the true unique identifier for deduplication and cross-referencing.
entry_number=$(wc -l <"$events_file" | tr -d ' ')
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
  printf '%s,' "$(json_string "title_b64" "$(base64_encode "$title")")"
  printf '%s,' "$(json_string "title_line" "$title_line")"
  printf '%s,' "$(json_string "instruction_source_b64" "$(base64_encode "$instruction_source")")"
  printf '%s,' "$(json_string "instruction_text_b64" "$(base64_encode "$instruction_text")")"
  printf '%s,' "$(json_string "action_taken_b64" "$(base64_encode "$action_taken")")"
  printf '%s,' "$(json_string "expected_outcome_b64" "$(base64_encode "$expected_outcome")")"
  printf '%s,' "$(json_string "actual_outcome_b64" "$(base64_encode "$actual_outcome")")"
  printf '%s,' "$(json_string "interpretation_b64" "$(base64_encode "$interpretation")")"
  printf '%s,' "$(json_string "command_b64" "$(base64_encode "$command_text")")"
  printf '%s,' "$(json_string "tool_name_b64" "$(base64_encode "$tool_name")")"
  printf '%s,' "$(json_string "stderr_b64" "$(base64_encode "$stderr_text")")"
  printf '%s,' "$(json_string "stdout_excerpt_b64" "$(base64_encode "$stdout_excerpt")")"
  printf '%s,' "$(json_string "owner_hint_b64" "$(base64_encode "$owner_hint")")"
  printf '%s,' "$(json_string "component_hint_b64" "$(base64_encode "$component_hint")")"
  printf '%s,' "$(json_string "workaround_note_b64" "$(base64_encode "$workaround_note")")"
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

# ── Update incidents.json with current event/incident counts ─────────
# Single-pass awk over events.jsonl: O(n) instead of O(n*m) nested shell loops.
if [ -n "$incidents_file" ] && [ -f "$events_file" ]; then
  task_id_for_incidents=$(basename "$(dirname "$(dirname "$log_file")")")
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
