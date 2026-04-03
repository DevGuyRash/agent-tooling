#!/bin/sh
set -eu

# render-summary.sh — Session friction summary renderer.
# Thin shim that encapsulates the query → flatten → render pipeline.
# Handles path resolution, terminal width detection, and smart re-query
# footer generation. Agents call this; it calls render-table.sh internally.

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname "$0")" && pwd)

print_help() {
  cat <<'EOF'
render-summary.sh — Render a friction session summary table

Usage:
  sh render-summary.sh --events-file PATH [--after TIMESTAMP] [OPTIONS]

Queries friction events, flattens source anchors, and renders a Unicode
box-drawing summary table. Produces a ready-to-paste block with header,
table, events file path, and a re-query command.

Required:
  --events-file PATH       Path to events.jsonl

Time filters (at least one recommended):
  --after ISO-TIMESTAMP    Events after this timestamp (session start)
  --before ISO-TIMESTAMP   Events before this timestamp (session end)
  --date-from YYYY-MM-DD   Events on or after this date

Display:
  --max-width N            Override terminal width detection (0 = unlimited)
  --no-fit                 Ignore terminal width; unlimited table width
  --max-col-width N        Max column content width before wrapping (default: 40)
  --help, -h               Show this help
EOF
}

# ── Argument parsing ─────────────────────────────────────────────────

events_file=
after=
before=
date_from=
max_width=
no_fit=0
max_col_width=40

while [ $# -gt 0 ]; do
  case "$1" in
    --events-file)   events_file=${2-}; shift 2 ;;
    --after)         after=${2-}; shift 2 ;;
    --before)        before=${2-}; shift 2 ;;
    --date-from)     date_from=${2-}; shift 2 ;;
    --max-width)     max_width=${2-}; shift 2 ;;
    --no-fit)        no_fit=1; shift ;;
    --max-col-width) max_col_width=${2-}; shift 2 ;;
    --help|-h)       print_help; exit 0 ;;
    *)               printf 'render-summary.sh: unknown option: %s\n' "$1" >&2; exit 1 ;;
  esac
done

if [ -z "$events_file" ]; then
  printf 'render-summary.sh: --events-file is required\n' >&2
  exit 1
fi

if [ ! -f "$events_file" ]; then
  printf 'render-summary.sh: events file not found: %s\n' "$events_file" >&2
  exit 1
fi

# ── Resolve sibling scripts ──────────────────────────────────────────

QUERY_SCRIPT="$SCRIPT_DIR/query-friction.sh"
RENDER_SCRIPT="$SCRIPT_DIR/render-table.sh"

if [ ! -f "$QUERY_SCRIPT" ]; then
  printf 'render-summary.sh: missing query-friction.sh at %s\n' "$QUERY_SCRIPT" >&2
  exit 1
fi

if [ ! -f "$RENDER_SCRIPT" ]; then
  printf 'render-summary.sh: missing render-table.sh at %s\n' "$RENDER_SCRIPT" >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  printf 'render-summary.sh: jq is required. Install: https://jqlang.github.io/jq/download/\n' >&2
  exit 1
fi

# ── Terminal width detection ─────────────────────────────────────────

detect_terminal_width() {
  if [ "$no_fit" -eq 1 ]; then
    printf '0\n'
    return
  fi
  if [ -n "$max_width" ]; then
    printf '%s\n' "$max_width"
    return
  fi
  # Only auto-detect when stdout is a TTY
  if [ -t 1 ]; then
    if [ -n "${COLUMNS-}" ]; then
      printf '%s\n' "$COLUMNS"
    elif command -v tput >/dev/null 2>&1; then
      tput cols 2>/dev/null || printf '120\n'
    else
      printf '120\n'
    fi
  else
    # Not a TTY — unlimited
    printf '0\n'
  fi
}

resolved_max_width=$(detect_terminal_width)

# ── Compute effective date-from fallback ─────────────────────────────

effective_date_from=$date_from
if [ -z "$after" ] && [ -z "$before" ] && [ -z "$date_from" ]; then
  effective_date_from=$(date -u +%Y-%m-%d)
fi

# ── Run the pipeline ─────────────────────────────────────────────────
# query → jq (flatten sources) → render-table.sh

query_tmp=$(mktemp)
flatten_tmp=$(mktemp)
cleanup() { rm -f "$query_tmp" "$flatten_tmp"; }
trap cleanup EXIT HUP INT TERM

# Build query args as a proper array via set -- to handle paths with spaces
set -- --events-file "$events_file"
[ -n "$after" ]              && set -- "$@" --after "$after"
[ -n "$before" ]             && set -- "$@" --before "$before"
[ -n "$effective_date_from" ] && set -- "$@" --date-from "$effective_date_from"
set -- "$@" --format jsonl

sh "$QUERY_SCRIPT" "$@" > "$query_tmp"

event_count=$(jq -s 'length' "$query_tmp")

if [ "$event_count" -eq 0 ]; then
  exit 0
fi

# Flatten sources array into compact anchors
jq -c '. + {sources_flat: ([.sources[]? | "\(.type):\(.ref)" + (if .line then ":\(.line)" + (if .end_line then "-\(.end_line)" else "" end) else "" end)] | join(" | "))}' "$query_tmp" > "$flatten_tmp"

# Extract last event timestamp for the re-query footer.
# --before is strict <, so bump by 1 second to include the last event.
last_event_time=$(jq -rs 'last | .recorded_at // ""' "$query_tmp")
requery_before=
if [ -n "$last_event_time" ]; then
  # Increment the last timestamp by 1 second for an inclusive upper bound.
  # Uses python3 if available (reliable); falls back to using the raw value
  # with a "Z+1s" comment hint if python3 is absent.
  if command -v python3 >/dev/null 2>&1; then
    requery_before=$(python3 -c "
from datetime import datetime, timedelta, timezone
t = datetime.fromisoformat('$last_event_time'.replace('Z', '+00:00'))
print((t + timedelta(seconds=1)).strftime('%Y-%m-%dT%H:%M:%SZ'))
" 2>/dev/null) || requery_before=
  fi
  # Fallback: use the raw timestamp (will exclude last event, but better than nothing)
  if [ -z "$requery_before" ]; then
    requery_before=$last_event_time
  fi
fi

# ── Render ───────────────────────────────────────────────────────────

# Build render args as a proper array
set -- --jsonl
set -- "$@" --fields "event_id,recorded_at,title,derived_category,tags,sources_flat"
set -- "$@" --headers "ID,Time,Title,Category,Tags,Sources"
set -- "$@" --max-col-width "$max_col_width"
set -- "$@" --fit-mode "drop-last-then-shrink"
set -- "$@" --min-columns "3"
if [ "$resolved_max_width" != "0" ]; then
  set -- "$@" --max-width "$resolved_max_width"
fi

# Header
printf 'Friction Summary \342\200\224 %d event(s) this session\n' "$event_count"

# Table
sh "$RENDER_SCRIPT" "$@" < "$flatten_tmp"

# ── Smart re-query footer ────────────────────────────────────────────

# Build footer query as a proper quoted command the user can paste.
# Use shell_quote to handle paths with spaces.
sq() { printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"; }

requery_cmd="sh $(sq "$QUERY_SCRIPT") --events-file $(sq "$events_file")"
[ -n "$after" ]              && requery_cmd="$requery_cmd --after $(sq "$after")"
[ -n "$effective_date_from" ] && requery_cmd="$requery_cmd --date-from $(sq "$effective_date_from")"
# --before: use the bumped timestamp if we computed one (from --after), or the
# original --before if passed directly, ensuring the upper bound is always preserved.
if [ -n "$requery_before" ]; then
  requery_cmd="$requery_cmd --before $(sq "$requery_before")"
elif [ -n "$before" ]; then
  requery_cmd="$requery_cmd --before $(sq "$before")"
fi
requery_cmd="$requery_cmd --format md"

printf '\nEvents: %s\n' "$events_file"
printf 'Query:  %s\n' "$requery_cmd"
