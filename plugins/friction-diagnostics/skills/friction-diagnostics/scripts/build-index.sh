#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
. "$SCRIPT_DIR/_common.sh"

print_help() {
  cat <<'EOF'
Usage:
  sh scripts/build-index.sh --events-file /path/to/events.jsonl

Options:
  --events-file PATH
  --help
EOF
}

events_file=${FRICTION_EVENTS_FILE-}

while [ $# -gt 0 ]; do
  case "$1" in
    --events-file) events_file=${2-}; shift 2 ;;
    --help|-h) print_help; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
done

[ -n "$events_file" ] || die "--events-file is required"

if ! command -v jq >/dev/null 2>&1; then
  die "jq is required for build-index.sh"
fi

events_dir=$(dirname "$events_file")
[ -d "$events_dir" ] || mkdir -p "$events_dir"

index_file=$events_dir/INDEX.md
lock_dir=$events_dir/.build-index.lock
lock_acquired=0
index_tmp=

cleanup() {
  rm -f ${index_tmp:+"$index_tmp"}
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

if [ ! -f "$events_file" ]; then
  rm -f "$index_file"
  printf '%s\n' "$index_file"
  exit 0
fi

validate_events_jsonl_file "$events_file"
event_count=$(jq -s 'length' "$events_file") || exit $?
if [ "$event_count" -eq 0 ]; then
  rm -f "$index_file"
  printf '%s\n' "$index_file"
  exit 0
fi

index_tmp=$(mktemp "$events_dir/.index.XXXXXX.tmp")
sh "$SCRIPT_DIR/generate-report.sh" \
  --events-file "$events_file" \
  --report-type index \
  --format md >"$index_tmp"

mv -f "$index_tmp" "$index_file"
index_tmp=
printf '%s\n' "$index_file"
