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

Recommended fields:
  --title TEXT
  --instruction-source TEXT
  --instruction-text TEXT
  --action-taken TEXT
  --expected-outcome TEXT
  --actual-outcome TEXT
  --interpretation TEXT

Optional overrides:
  --surface VALUE
  --mode VALUE
  --impact VALUE
  --tags CSV
  --help
EOF
}

log_file=${FRICTION_LOG_FILE-}
title=
instruction_source=
instruction_text=
action_taken=
expected_outcome=
actual_outcome=
interpretation=
surface=
mode=
impact=
tags=

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
    --surface) surface=${2-}; shift 2 ;;
    --mode) mode=${2-}; shift 2 ;;
    --impact) impact=${2-}; shift 2 ;;
    --tags) tags=${2-}; shift 2 ;;
    --help|-h) print_help; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
done

[ -n "$log_file" ] || die "--log-file is required"
[ -f "$log_file" ] || die "Log file not found: $log_file"

cat_output=$(
  sh "$SCRIPT_DIR/categorize.sh" \
    --instruction-source "$instruction_source" \
    --instruction-text "$instruction_text" \
    --action-taken "$action_taken" \
    --expected-outcome "$expected_outcome" \
    --actual-outcome "$actual_outcome" \
    --interpretation "$interpretation" \
    --surface "$surface" \
    --mode "$mode" \
    --impact "$impact"
)

final_surface=
final_mode=
final_impact=
final_tags=
while IFS='=' read -r key value; do
  case "$key" in
    surface) final_surface=$value ;;
    mode) final_mode=$value ;;
    impact) final_impact=$value ;;
    tags) final_tags=$value ;;
  esac
done <<EOF
$cat_output
EOF

surface=$final_surface
mode=$final_mode
impact=$final_impact

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

entry_number=$(grep -c '^## Entry [0-9][0-9]*:' "$log_file" 2>/dev/null || true)
entry_number=$((entry_number + 1))
recorded=$(date '+%Y-%m-%d %H:%M:%S %Z')

{
  printf '\n'
  printf '## Entry %s: %s\n' "$entry_number" "$title"
  write_md_field "Recorded" "$recorded"
  write_md_field "Category" "$surface/$mode/$impact"
  write_md_field "Tags" "$tags"
  write_md_field "Instruction source" "$instruction_source"
  write_md_field "Instruction text" "$instruction_text"
  write_md_field "Action taken" "$action_taken"
  write_md_field "Expected outcome" "$expected_outcome"
  write_md_field "Actual outcome" "$actual_outcome"
  write_md_field "Interpretation" "$interpretation"
  printf -- '---\n'
} >>"$log_file"

task_dir=$(dirname "$(dirname "$log_file")")
if [ -x "$SCRIPT_DIR/build-index.sh" ] || [ -f "$SCRIPT_DIR/build-index.sh" ]; then
  sh "$SCRIPT_DIR/build-index.sh" --task-dir "$task_dir" >/dev/null
fi
