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
events_jsonl=$task_dir/events.jsonl
lock_dir=$task_dir/.build-index.lock
lock_acquired=0
category_counts_file=
log_counts_file=
index_tmp_file=

sort_count_then_name() {
  LC_ALL=C sort -t "$(printf '\t')" -k1,1nr -k2,2 "$@"
}

cleanup() {
  rm -f ${category_counts_file:+"$category_counts_file"} \
    ${log_counts_file:+"$log_counts_file"} \
    ${index_tmp_file:+"$index_tmp_file"}
  if [ "${lock_acquired:-0}" -eq 1 ] && [ -n "${lock_dir-}" ]; then
    rm -f "$lock_dir/pid" 2>/dev/null || true
    rmdir "$lock_dir" 2>/dev/null || true
  fi
}

acquire_lock() {
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
  lock_acquired=1
  printf '%s\n' "$$" >"$lock_dir/pid"
}

trap cleanup EXIT HUP INT TERM
acquire_lock

task_id=$(basename "$task_dir")
generated=$(date -u '+%Y-%m-%d %H:%M:%S %Z')
task_summary=
if [ -f "$session_file" ]; then
  task_summary_file=$(grep '^FRICTION_TASK_SUMMARY_FILE=' "$session_file" | sed 's/^FRICTION_TASK_SUMMARY_FILE=//' || true)
  if [ -n "$task_summary_file" ] && [ -f "$task_summary_file" ]; then
    task_summary=$(cat "$task_summary_file")
  else
    task_summary=$(grep '^FRICTION_TASK_SUMMARY=' "$session_file" | sed 's/^FRICTION_TASK_SUMMARY=//' || true)
  fi
fi

total_entries=0
if [ -f "$events_jsonl" ]; then
  total_entries=$(wc -l <"$events_jsonl" | tr -d ' ')
fi

if [ "$total_entries" -eq 0 ]; then
  rm -f "$index_file"
  printf '%s\n' "$index_file"
  exit 0
fi

category_counts_file=$(mktemp "$task_dir/.category-counts.XXXXXX.tmp")
log_counts_file=$(mktemp "$task_dir/.log-counts.XXXXXX.tmp")

awk '
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
    category = extract($0, "derived_category")
    log_file = extract($0, "log_file")
    if (category != "") category_count[category]++
    if (log_file != "") log_count[log_file]++
  }
  END {
    for (k in category_count) {
      printf "C\t%d\t%s\n", category_count[k], k
    }
    for (k in log_count) {
      printf "L\t%d\t%s\n", log_count[k], k
    }
  }
' "$events_jsonl" |
  while IFS="$(printf '\t')" read -r kind count value; do
    case "$kind" in
      C) printf '%s\t%s\n' "$count" "$value" >>"$category_counts_file" ;;
      L) printf '%s\t%s\n' "$count" "$value" >>"$log_counts_file" ;;
    esac
  done

if [ -s "$category_counts_file" ]; then
  category_lines=$(sort_count_then_name "$category_counts_file")
else
  category_lines=
fi

if [ -s "$log_counts_file" ]; then
  log_lines=$(sort_count_then_name "$log_counts_file")
  log_file_count=$(wc -l <"$log_counts_file" | tr -d ' ')
else
  log_lines=
  log_file_count=0
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
