#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname "$0")" && pwd)

print_help() {
  cat <<'EOF'
Usage:
  sh scripts/report-friction-json.sh [--events-file PATH] [--repo-root PATH] [FILE]
  ... | sh scripts/report-friction-json.sh [--events-file PATH] [--repo-root PATH]

Thin helper for the safe JSON filing path. Forwards to report-friction.sh
using --from-json so callers do not need to hand-quote complex payload text.

Options:
  --events-file PATH   Override canonical events file path
  --repo-root PATH     Resolve canonical storage from a specific repo root
  --help, -h           Show this help
EOF
}

events_file=
repo_root=
payload_path=

while [ $# -gt 0 ]; do
  case "$1" in
    --events-file) events_file=${2-}; shift 2 ;;
    --repo-root) repo_root=${2-}; shift 2 ;;
    --help|-h) print_help; exit 0 ;;
    -*)
      printf 'report-friction-json.sh: unknown option: %s\n' "$1" >&2
      exit 1
      ;;
    *)
      if [ -n "$payload_path" ]; then
        printf 'report-friction-json.sh: unexpected argument: %s\n' "$1" >&2
        exit 1
      fi
      payload_path=$1
      shift
      ;;
  esac
done

set --
[ -n "$events_file" ] && set -- "$@" --events-file "$events_file"
[ -n "$repo_root" ] && set -- "$@" --repo-root "$repo_root"

if [ -n "$payload_path" ]; then
  exec sh "$SCRIPT_DIR/report-friction.sh" "$@" --from-json "$payload_path"
fi

if [ -t 0 ]; then
  print_help
  exit 0
fi

exec sh "$SCRIPT_DIR/report-friction.sh" "$@" --from-json -
