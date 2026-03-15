#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
. "$SCRIPT_DIR/_common.sh"

print_help() {
  cat <<'EOF'
Usage:
  sh scripts/build-index.sh --task-dir "$FRICTION_TASK_DIR"

Options:
  --task-dir PATH
  --help
EOF
}

task_dir=${FRICTION_TASK_DIR-}

while [ $# -gt 0 ]; do
  case "$1" in
    --task-dir) task_dir=${2-}; shift 2 ;;
    --help|-h) print_help; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
done

[ -n "$task_dir" ] || die "--task-dir is required"
[ -d "$task_dir" ] || die "Task directory not found: $task_dir"

index_file=$task_dir/INDEX.md
session_file=$task_dir/SESSION.txt
lock_dir=$task_dir/.build-index.lock
lock_acquired=0
log_list_file=
category_counts_file=
log_counts_file=
index_tmp_file=

sort_count_then_name() {
  LC_ALL=C sort -t "$(printf '\t')" -k1,1nr -k2,2 "$@"
}

cleanup() {
  rm -f ${log_list_file:+"$log_list_file"} \
    ${category_counts_file:+"$category_counts_file"} \
    ${log_counts_file:+"$log_counts_file"} \
    ${index_tmp_file:+"$index_tmp_file"}
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

task_id=$(basename "$task_dir")
generated=$(date '+%Y-%m-%d %H:%M:%S %Z')
task_summary=
if [ -f "$session_file" ]; then
  task_summary_file=$(grep '^FRICTION_TASK_SUMMARY_FILE=' "$session_file" | sed 's/^FRICTION_TASK_SUMMARY_FILE=//' || true)
  if [ -n "$task_summary_file" ] && [ -f "$task_summary_file" ]; then
    task_summary=$(cat "$task_summary_file")
  else
    task_summary=$(grep '^FRICTION_TASK_SUMMARY=' "$session_file" | sed 's/^FRICTION_TASK_SUMMARY=//' || true)
  fi
fi

log_list_file=$(mktemp "$task_dir/.log-files.XXXXXX.tmp")
find "$task_dir" -type f -name '*.md' ! -name 'INDEX.md' | sort >"$log_list_file"

log_file_count=0
total_entries=0
while IFS= read -r file; do
  [ -n "$file" ] || continue
  log_file_count=$((log_file_count + 1))
  count=$(grep -c '^## Entry [0-9][0-9]*:' "$file" 2>/dev/null || true)
  total_entries=$((total_entries + count))
done <"$log_list_file"

category_counts_file=$(mktemp "$task_dir/.category-counts.XXXXXX.tmp")
log_counts_file=$(mktemp "$task_dir/.log-counts.XXXXXX.tmp")
: >"$category_counts_file"
: >"$log_counts_file"

if [ -s "$log_list_file" ]; then
  while IFS= read -r file; do
    [ -n "$file" ] || continue
    rel=${file#"$task_dir"/}
    count=$(grep -c '^## Entry [0-9][0-9]*:' "$file" 2>/dev/null || true)
    printf '%s\t%s\n' "$count" "$rel" >>"$log_counts_file"
    awk '
      /^\*\*Category:\*\*/ {
        line=$0
        sub(/^\*\*Category:\*\* /, "", line)
        counts[line]++
      }
      END {
        for (k in counts) {
          printf "%s\t%s\n", counts[k], k
        }
      }
    ' "$file" >>"$category_counts_file"
  done <"$log_list_file"
fi

if [ -s "$category_counts_file" ]; then
  category_lines=$(
    awk -F '\t' '
      { counts[$2] += $1 }
      END {
        for (k in counts) {
          printf "%s\t%s\n", counts[k], k
        }
      }
    ' "$category_counts_file" | sort_count_then_name
  )
else
  category_lines=
fi

if [ -s "$log_counts_file" ]; then
  log_lines=$(sort_count_then_name "$log_counts_file")
else
  log_lines=
fi

index_tmp_file=$(mktemp "$task_dir/.index.XXXXXX.tmp")
{
  printf '# Friction Index: %s\n' "$task_id"
  write_md_field "Generated" "$generated"
  write_md_field "Task dir" "$task_dir"
  if [ -n "$task_summary" ]; then
    write_md_field "Task summary" "$task_summary"
  fi
  write_md_field "Log files" "$log_file_count"
  write_md_field "Entries" "$total_entries"
  printf -- '\n## Category counts\n\n'
  if [ -n "$category_lines" ]; then
    printf '%s\n' "$category_lines" | awk -F '\t' '{printf "- `%s` - %s\n", $2, $1}'
  else
    printf '_No categorized entries yet._\n'
  fi
  printf -- '\n## Log files\n\n'
  if [ -n "$log_lines" ]; then
    printf '%s\n' "$log_lines" | awk -F '\t' '{printf "- `%s` - %s entries\n", $2, $1}'
  else
    printf '_No log files yet._\n'
  fi
} >"$index_tmp_file"

mv -f "$index_tmp_file" "$index_file"
index_tmp_file=
printf '%s\n' "$index_file"
