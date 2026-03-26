#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
. "$SCRIPT_DIR/_common.sh"

print_help() {
  cat <<'EOF'
Usage:
  eval "$(sh scripts/init-log.sh --task-summary "..." --agent orchestrator --skill-path "$(pwd)")"

Options:
  --task-summary TEXT    Required unless FRICTION_TASK_SUMMARY is already set.
  --task-id TEXT         Optional. Reuse for subagents.
  --agent TEXT           Defaults to orchestrator.
  --role TEXT            Optional. Recorded only in shell output for the caller.
  --skill-path TEXT      Required in normal use.
  --base-dir PATH        Defaults to $FRICTION_BASE_DIR or /tmp/agent-friction.
  --context-path PATH    Optional workspace or repo path to record in the manifest.
  --storage-mode MODE    handoff | artifact | telemetry. Defaults to handoff.
  --capture-mode MODE    explicit | threshold | synthesis. Defaults to explicit.
  --privacy-tier TIER    private | shared. Defaults to private.
  --export-dir PATH      Optional. Used for sanitized exports and telemetry fan-out.
  --no-reuse             Always create a new session even if one with the same slug exists.
  --help
EOF
}

task_summary=${FRICTION_TASK_SUMMARY-}
task_id=
agent=orchestrator
role=
skill_path=
base_dir=${FRICTION_BASE_DIR-/tmp/agent-friction}
context_path=
storage_mode=handoff
capture_mode=explicit
privacy_tier=private
export_dir=
no_reuse=false

while [ $# -gt 0 ]; do
  case "$1" in
    --task-summary) task_summary=${2-}; shift 2 ;;
    --task-id) task_id=${2-}; shift 2 ;;
    --agent) agent=${2-}; shift 2 ;;
    --role) role=${2-}; shift 2 ;;
    --skill-path) skill_path=${2-}; shift 2 ;;
    --base-dir) base_dir=${2-}; shift 2 ;;
    --context-path) context_path=${2-}; shift 2 ;;
    --storage-mode) storage_mode=${2-}; shift 2 ;;
    --capture-mode) capture_mode=${2-}; shift 2 ;;
    --privacy-tier) privacy_tier=${2-}; shift 2 ;;
    --export-dir) export_dir=${2-}; shift 2 ;;
    --no-reuse) no_reuse=true; shift ;;
    --help|-h) print_help; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
done

[ -n "$task_summary" ] || die "--task-summary is required"
[ -n "$skill_path" ] || die "--skill-path is required"

storage_mode=$(normalize_storage_mode "$storage_mode")
capture_mode=$(normalize_capture_mode "$capture_mode")
privacy_tier=$(normalize_privacy_tier "$privacy_tier")

if [ -z "$export_dir" ] && [ "$storage_mode" = "telemetry" ]; then
  export_dir=$base_dir/telemetry
fi

stamp=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
task_auto_slug_limit=80
task_id_limit=255
mkdir -p "$base_dir"

if [ -z "$task_id" ]; then
  slug=$(bounded_slugify "$task_summary" "$task_auto_slug_limit")
  today=$(date -u '+%Y%m%d')

  existing_dir=
  if [ "$no_reuse" != "true" ] && [ -d "$base_dir" ]; then
    existing_dir=$(
      find "$base_dir" -maxdepth 1 -type d -name "${slug}-${today}-*" 2>/dev/null |
        sort | tail -1
    )
  fi

  if [ -n "$existing_dir" ] && [ -f "$existing_dir/SESSION.txt" ]; then
    task_dir=$existing_dir
    task_id=$(basename "$task_dir")
  else
    lock_dir="$base_dir/.create-lock-${slug}"
    if [ -d "$lock_dir" ]; then
      lock_age=$(find "$lock_dir" -maxdepth 0 -mmin +1 2>/dev/null | head -1)
      if [ -n "$lock_age" ]; then
        rmdir "$lock_dir" 2>/dev/null || true
      fi
    fi
    if mkdir "$lock_dir" 2>/dev/null; then
      timestamp=$(date -u '+%Y%m%d-%H%M%S')
      task_dir=$(mktemp -d "$base_dir/${slug}-${timestamp}.XXXXXX")
      task_id=$(basename "$task_dir")
      rmdir "$lock_dir" 2>/dev/null || true
    else
      sleep 1
      existing_dir=$(
        find "$base_dir" -maxdepth 1 -type d -name "${slug}-${today}-*" 2>/dev/null |
          sort | tail -1
      )
      if [ -n "$existing_dir" ] && [ -f "$existing_dir/SESSION.txt" ]; then
        task_dir=$existing_dir
        task_id=$(basename "$task_dir")
      else
        timestamp=$(date -u '+%Y%m%d-%H%M%S')
        task_dir=$(mktemp -d "$base_dir/${slug}-${timestamp}.XXXXXX")
        task_id=$(basename "$task_dir")
      fi
      rmdir "$lock_dir" 2>/dev/null || true
    fi
  fi
else
  if [ -d "$base_dir/$task_id" ]; then
    task_dir=$base_dir/$task_id
  else
    task_id=$(bounded_slugify "$task_id" "$task_id_limit")
    task_dir=$base_dir/$task_id
    mkdir -p "$task_dir"
  fi
fi

session_file=$task_dir/SESSION.txt
task_summary_file=$task_dir/TASK_SUMMARY.txt
task_json_file=$task_dir/task.json
events_file=$task_dir/events.jsonl
incidents_file=$task_dir/incidents.json
index_file=$task_dir/INDEX.md
exports_dir=$task_dir/exports
sanitized_export_file=$exports_dir/sanitized-incidents.json

if [ ! -f "$task_summary_file" ]; then
  printf '%s' "$task_summary" >"$task_summary_file"
fi

{
  printf '{'
  printf '%s,' "$(json_string "schema_version" "$SCHEMA_VERSION")"
  printf '%s,' "$(json_string "task_id" "$task_id")"
  printf '%s,' "$(json_string "created_at" "$stamp")"
  printf '%s,' "$(json_string "task_summary" "$task_summary")"
  printf '%s,' "$(json_string "task_summary_first_line" "$(truncate_line "$task_summary" 120)")"
  printf '%s,' "$(json_string "storage_mode" "$storage_mode")"
  printf '%s,' "$(json_string "capture_mode" "$capture_mode")"
  printf '%s,' "$(json_string "privacy_tier" "$privacy_tier")"
  printf '%s,' "$(json_string "platform" "$(platform_name)")"
  printf '%s,' "$(json_string "skill_path" "$skill_path")"
  printf '%s,' "$(json_string "task_dir" "$task_dir")"
  printf '%s,' "$(json_bool "artifacts_materialized" "false")"
  printf '%s' "$(json_string "export_dir" "$export_dir")"
  if [ -n "$context_path" ]; then
    printf ',%s' "$(json_string "context_path" "$context_path")"
  fi
  printf '}\n'
} >"$task_json_file"

{
  printf 'FRICTION_BASE_DIR=%s\n' "$base_dir"
  printf 'FRICTION_TASK_ID=%s\n' "$task_id"
  printf 'FRICTION_TASK_DIR=%s\n' "$task_dir"
  printf 'FRICTION_TASK_SUMMARY_FILE=%s\n' "$task_summary_file"
  printf 'FRICTION_INDEX_FILE=%s\n' "$index_file"
  printf 'FRICTION_TASK_JSON=%s\n' "$task_json_file"
  printf 'FRICTION_EVENTS_FILE=%s\n' "$events_file"
  printf 'FRICTION_INCIDENTS_FILE=%s\n' "$incidents_file"
  printf 'FRICTION_STORAGE_MODE=%s\n' "$storage_mode"
  printf 'FRICTION_CAPTURE_MODE=%s\n' "$capture_mode"
  printf 'FRICTION_PRIVACY_TIER=%s\n' "$privacy_tier"
  printf 'FRICTION_EXPORT_DIR=%s\n' "$export_dir"
  printf 'FRICTION_SANITIZED_EXPORT=%s\n' "$sanitized_export_file"
  printf 'FRICTION_SKILL_PATH=%s\n' "$skill_path"
  printf 'FRICTION_CONTEXT_PATH=%s\n' "$context_path"
} >"$session_file"

printf 'FRICTION_BASE_DIR=%s\n' "$(shell_quote "$base_dir")"
printf 'export FRICTION_BASE_DIR\n'
printf 'FRICTION_TASK_ID=%s\n' "$(shell_quote "$task_id")"
printf 'export FRICTION_TASK_ID\n'
printf 'FRICTION_TASK_DIR=%s\n' "$(shell_quote "$task_dir")"
printf 'export FRICTION_TASK_DIR\n'
printf 'FRICTION_TASK_SUMMARY=%s\n' "$(shell_quote "$(first_line "$task_summary")")"
printf 'export FRICTION_TASK_SUMMARY\n'
printf 'FRICTION_TASK_SUMMARY_FILE=%s\n' "$(shell_quote "$task_summary_file")"
printf 'export FRICTION_TASK_SUMMARY_FILE\n'
printf 'FRICTION_LOG_FILE=%s\n' "$(shell_quote "")"
printf 'FRICTION_INDEX_FILE=%s\n' "$(shell_quote "$index_file")"
printf 'FRICTION_TASK_DESCRIPTOR=%s\n' "$(shell_quote "")"
printf 'FRICTION_TASK_JSON=%s\n' "$(shell_quote "$task_json_file")"
printf 'export FRICTION_TASK_JSON\n'
printf 'FRICTION_EVENTS_FILE=%s\n' "$(shell_quote "$events_file")"
printf 'export FRICTION_EVENTS_FILE\n'
printf 'FRICTION_INCIDENTS_FILE=%s\n' "$(shell_quote "$incidents_file")"
printf 'export FRICTION_INCIDENTS_FILE\n'
printf 'FRICTION_SKILL_PATH=%s\n' "$(shell_quote "$skill_path")"
printf 'export FRICTION_SKILL_PATH\n'
printf 'FRICTION_CONTEXT_PATH=%s\n' "$(shell_quote "$context_path")"
printf 'export FRICTION_CONTEXT_PATH\n'
printf 'FRICTION_STORAGE_MODE=%s\n' "$(shell_quote "$storage_mode")"
printf 'export FRICTION_STORAGE_MODE\n'
printf 'FRICTION_CAPTURE_MODE=%s\n' "$(shell_quote "$capture_mode")"
printf 'export FRICTION_CAPTURE_MODE\n'
printf 'FRICTION_PRIVACY_TIER=%s\n' "$(shell_quote "$privacy_tier")"
printf 'export FRICTION_PRIVACY_TIER\n'
printf 'FRICTION_EXPORT_DIR=%s\n' "$(shell_quote "$export_dir")"
printf 'export FRICTION_EXPORT_DIR\n'
printf 'FRICTION_SANITIZED_EXPORT=%s\n' "$(shell_quote "$sanitized_export_file")"
printf 'export FRICTION_SANITIZED_EXPORT\n'
