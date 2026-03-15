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
  --role TEXT            Optional. Used mainly for subagents.
  --skill-path TEXT      Required in normal use.
  --base-dir PATH        Defaults to $FRICTION_BASE_DIR or /tmp/agent-friction.
  --context-path PATH    Optional workspace or repo path to record in the header.
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

while [ $# -gt 0 ]; do
  case "$1" in
    --task-summary) task_summary=${2-}; shift 2 ;;
    --task-id) task_id=${2-}; shift 2 ;;
    --agent) agent=${2-}; shift 2 ;;
    --role) role=${2-}; shift 2 ;;
    --skill-path) skill_path=${2-}; shift 2 ;;
    --base-dir) base_dir=${2-}; shift 2 ;;
    --context-path) context_path=${2-}; shift 2 ;;
    --help|-h) print_help; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
done

[ -n "$task_summary" ] || die "--task-summary is required"
[ -n "$skill_path" ] || die "--skill-path is required"

date_dir=$(date '+%Y-%m-%d')
time_part=$(date '+%H-%M-%S')
stamp=$(date '+%Y-%m-%d %H:%M:%S %Z')
task_auto_slug_limit=232
task_id_limit=255
log_slug_limit=240
mkdir -p "$base_dir"

if [ -z "$task_id" ]; then
  slug=$(bounded_slugify "$task_summary" "$task_auto_slug_limit")
  timestamp=$(date '+%Y%m%d-%H%M%S')
  task_dir=$(mktemp -d "$base_dir/${slug}-${timestamp}.XXXXXX")
  task_id=$(basename "$task_dir")
else
  task_id=$(bounded_slugify "$task_id" "$task_id_limit")
  task_dir=$base_dir/$task_id
fi

agent_slug=$(slugify "$agent")
agent_display=$agent
if [ -n "$role" ]; then
  role_slug=$(slugify "$role")
  agent_slug="${agent_slug}-${role_slug}"
  agent_display="${agent} (${role})"
fi
agent_slug=$(bounded_slugify "$agent_slug" "$log_slug_limit")

dated_dir=$task_dir/$date_dir
mkdir -p "$dated_dir"

log_file=$dated_dir/${time_part}_${agent_slug}.md
suffix=1
while [ -e "$log_file" ]; do
  log_file=$dated_dir/${time_part}_${agent_slug}_$(printf '%02d' "$suffix").md
  suffix=$((suffix + 1))
done

index_file=$task_dir/INDEX.md
session_file=$task_dir/SESSION.txt
task_summary_file=$task_dir/TASK_SUMMARY.txt

{
  printf '# Friction Log: %s\n' "$task_id"
  write_md_field "Date" "$stamp"
  write_md_field "Agent" "$agent_display"
  write_md_field "Skill path" "$skill_path"
  write_md_field "Task ID" "$task_id"
  write_md_field "Task summary" "$task_summary"
  if [ -n "$context_path" ]; then
    write_md_field "Context path" "$context_path"
  fi
  write_md_field "Platform" "$(platform_name)"
  write_md_field "Convention version" "1.0.0"
  printf -- '---\n'
} >"$log_file"

if [ ! -f "$session_file" ]; then
  printf '%s' "$task_summary" >"$task_summary_file"
  {
    printf 'FRICTION_BASE_DIR=%s\n' "$base_dir"
    printf 'FRICTION_TASK_ID=%s\n' "$task_id"
    printf 'FRICTION_TASK_DIR=%s\n' "$task_dir"
    printf 'FRICTION_TASK_SUMMARY_FILE=%s\n' "$task_summary_file"
    printf 'FRICTION_INDEX_FILE=%s\n' "$index_file"
  } >"$session_file"
fi

if [ -x "$SCRIPT_DIR/build-index.sh" ] || [ -f "$SCRIPT_DIR/build-index.sh" ]; then
  sh "$SCRIPT_DIR/build-index.sh" --task-dir "$task_dir" >/dev/null
fi

printf 'FRICTION_BASE_DIR=%s\n' "$(shell_quote "$base_dir")"
printf 'export FRICTION_BASE_DIR\n'
printf 'FRICTION_TASK_ID=%s\n' "$(shell_quote "$task_id")"
printf 'export FRICTION_TASK_ID\n'
printf 'FRICTION_TASK_DIR=%s\n' "$(shell_quote "$task_dir")"
printf 'export FRICTION_TASK_DIR\n'
printf 'FRICTION_TASK_SUMMARY=%s\n' "$(shell_quote "$task_summary")"
printf 'export FRICTION_TASK_SUMMARY\n'
printf 'FRICTION_TASK_SUMMARY_FILE=%s\n' "$(shell_quote "$task_summary_file")"
printf 'export FRICTION_TASK_SUMMARY_FILE\n'
printf 'FRICTION_LOG_FILE=%s\n' "$(shell_quote "$log_file")"
printf 'export FRICTION_LOG_FILE\n'
printf 'FRICTION_INDEX_FILE=%s\n' "$(shell_quote "$index_file")"
printf 'export FRICTION_INDEX_FILE\n'
