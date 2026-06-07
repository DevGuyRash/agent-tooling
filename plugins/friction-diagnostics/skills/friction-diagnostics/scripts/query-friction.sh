#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
. "$SCRIPT_DIR/_common.sh"

print_help() {
  cat <<'EOF'
Usage:
  sh scripts/query-friction.sh [--events-file PATH | --scan-dirs DIR [DIR...]] [filters]

Input:
  --events-file PATH        Single events file (default: auto-detected)
  --scan-dirs DIR [DIR...]  Recursively discover all events.jsonl files under
                            the given directories matching
                            */.local*/reports/friction/events.jsonl

Filters:
  --impact VALUE            blocked | degraded | noisy | continued
  --fingerprint VALUE
  --tag VALUE               Substring match across tags (e.g. "auth" matches "ssh-auth-sock")
  --tag-exact VALUE         Exact tag match
  --alias VALUE             Substring match across aliases
  --alias-exact VALUE       Exact alias match
  --text PATTERN            Case-insensitive substring search across narrative fields
  --date YYYY-MM-DD
  --date-from YYYY-MM-DD
  --date-to YYYY-MM-DD
  --after ISO-TIMESTAMP     Filter events with recorded_at > TIMESTAMP
  --before ISO-TIMESTAMP    Filter events with recorded_at < TIMESTAMP
  --source-ref PATH

Output:
  --format jsonl|json|md
  --output PATH
  --compact                 Strip empty-string and null fields (json/jsonl only)
  --help
EOF
}

events_file=${FRICTION_EVENTS_FILE-}
scan_dirs=
impact=
fingerprint=
tag=
tag_exact=
alias_filter=
alias_exact=
text=
date_exact=
date_from=
date_to=
after=
before=
source_ref=
format=jsonl
output_path=
compact=0

append_multiline() {
  current=$1
  value=$2
  if [ -n "$current" ]; then
    printf '%s\n%s\n' "$current" "$value"
  else
    printf '%s\n' "$value"
  fi
}

while [ $# -gt 0 ]; do
  case "$1" in
    --events-file) events_file=${2-}; shift 2 ;;
    --scan-dirs)
      shift
      while [ $# -gt 0 ]; do
        case "$1" in
          --*) break ;;
          *)
            scan_dirs=$(append_multiline "$scan_dirs" "$1")
            shift
            ;;
        esac
      done
      ;;
    --impact) impact=${2-}; shift 2 ;;
    --fingerprint) fingerprint=${2-}; shift 2 ;;
    --tag) tag=${2-}; shift 2 ;;
    --tag-exact) tag_exact=${2-}; shift 2 ;;
    --alias) alias_filter=${2-}; shift 2 ;;
    --alias-exact) alias_exact=${2-}; shift 2 ;;
    --text) text=${2-}; shift 2 ;;
    --date) date_exact=${2-}; shift 2 ;;
    --date-from) date_from=${2-}; shift 2 ;;
    --date-to) date_to=${2-}; shift 2 ;;
    --after) after=${2-}; shift 2 ;;
    --before) before=${2-}; shift 2 ;;
    --source-ref) source_ref=${2-}; shift 2 ;;
    --format) format=${2-}; shift 2 ;;
    --output) output_path=${2-}; shift 2 ;;
    --compact) compact=1; shift ;;
    --help|-h) print_help; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
done

case "$format" in
  jsonl|json|md) ;;
  *) die "Unsupported format: $format" ;;
esac

if ! command -v jq >/dev/null 2>&1; then
  die "jq is required for query-friction.sh"
fi

if [ -n "$scan_dirs" ]; then
  set --
  while IFS= read -r dir; do
    [ -n "$dir" ] || continue
    set -- "$@" "$dir"
  done <<EOF
$scan_dirs
EOF
  [ "$#" -gt 0 ] || die "--scan-dirs requires at least one directory"
  discovered=$(discover_events_files "$@" || true)
  if [ -z "$discovered" ]; then
    die "No events.jsonl files found under the provided scan dirs"
  fi
  events_files=$discovered
else
  if [ -z "$events_file" ]; then
    events_file=$(default_events_file)
  fi
  [ -f "$events_file" ] || die "Events file not found: $events_file"
  events_files=$events_file
fi

set --
while IFS= read -r file; do
  [ -n "$file" ] || continue
  set -- "$@" "$file"
done <<EOF
$events_files
EOF
[ "$#" -gt 0 ] || die "No events files resolved"

for resolved_events_file in "$@"; do
  validate_events_jsonl_file "$resolved_events_file"
done

filtered_tmp=$(mktemp)
cleanup() {
  rm -f "$filtered_tmp"
}
trap cleanup EXIT HUP INT TERM

jq -s \
  --arg impact "$impact" \
  --arg fingerprint "$fingerprint" \
  --arg tag "$tag" \
  --arg tag_exact "$tag_exact" \
  --arg alias_filter "$alias_filter" \
  --arg alias_exact "$alias_exact" \
  --arg text "$text" \
  --arg date_exact "$date_exact" \
  --arg date_from "$date_from" \
  --arg date_to "$date_to" \
  --arg after "$after" \
  --arg before "$before" \
  --arg source_ref "$source_ref" \
  '
  def event_tags:
    (.tags // [] | map(tostring | ascii_downcase));
  def event_aliases:
    (.aliases // [] | map(tostring | ascii_downcase));
  def matches_tag_fuzzy($needle):
    if $needle == "" then true
    else ($needle | ascii_downcase) as $n | any(event_tags[]; contains($n)) end;
  def matches_tag_exact($needle):
    if $needle == "" then true
    else ($needle | ascii_downcase) as $n | any(event_tags[]; . == $n) end;
  def matches_alias_fuzzy($needle):
    if $needle == "" then true
    else ($needle | ascii_downcase) as $n | any(event_aliases[]; contains($n)) end;
  def matches_alias_exact($needle):
    if $needle == "" then true
    else ($needle | ascii_downcase) as $n | any(event_aliases[]; . == $n) end;
  def matches_source_ref($ref):
    if $ref == "" then true else any((.sources // [])[]?; (.ref // "") == $ref) end;
  def text_match($needle):
    if $needle == "" then true
    else
      ([.title, .actual_outcome, .reading, .hindsight, .expected_outcome]
       | map((. // "") | ascii_downcase)
       | join("\u0000")
       | contains($needle | ascii_downcase))
    end;

  map(
    select(
      ($impact == "" or (.impact // "") == $impact) and
      ($fingerprint == "" or (.fingerprint // "") == $fingerprint) and
      matches_tag_fuzzy($tag) and
      matches_tag_exact($tag_exact) and
      matches_alias_fuzzy($alias_filter) and
      matches_alias_exact($alias_exact) and
      text_match($text) and
      (($date_exact == "") or (((.recorded_at // "")[0:10]) == $date_exact)) and
      (($date_from == "") or (((.recorded_at // "")[0:10]) >= $date_from)) and
      (($date_to == "") or (((.recorded_at // "")[0:10]) <= $date_to)) and
      (($after == "") or ((.recorded_at // "") > $after)) and
      (($before == "") or ((.recorded_at // "") < $before)) and
      matches_source_ref($source_ref)
    )
  )
  | sort_by(.recorded_at // "", .event_id // "")
  ' "$@" >"$filtered_tmp"

case "$format" in
  jsonl)
    if [ "$compact" -eq 1 ]; then
      result=$(jq -c '
        def compact_obj: with_entries(select(.value != null and .value != ""));
        .[] | compact_obj
      ' "$filtered_tmp")
    else
      result=$(jq -c '.[]' "$filtered_tmp")
    fi
    ;;
  json)
    if [ "$compact" -eq 1 ]; then
      result=$(jq '
        def compact_obj: with_entries(select(.value != null and .value != ""));
        map(compact_obj)
      ' "$filtered_tmp")
    else
      result=$(cat "$filtered_tmp")
    fi
    ;;
  md)
    result=$(
      {
        printf '# Friction Query Results\n\n'
        printf -- '- Entries: %s\n\n' "$(jq 'length' "$filtered_tmp")"
        jq -r '
          .[]
          | "## \(.event_id // ""): \(.title // "")\n"
            + "\n- Recorded: \(.recorded_at // "")"
            + "\n- Impact: \(.impact // "")"
            + "\n- Fingerprint: \(.fingerprint // "")"
            + (if ((.sources // []) | length) > 0 then
                "\n- Sources: " + ([(.sources // [])[] |
                  (.ref // "") + (if (.line // null) != null then ":" + (.line | tostring) + (if (.end_line // null) != null then "-" + (.end_line | tostring) else "" end) else "" end)
                ] | join(", "))
              else "" end)
            + ((.tags // []) | if length > 0 then "\n- Tags: " + join(", ") else "" end)
            + ((.aliases // []) | if length > 0 then "\n- Aliases: " + join(", ") else "" end)
            + (if ((.expected_outcome // "") | length) > 0 then "\n\n**Expected:** \(.expected_outcome)" else "" end)
            + (if ((.actual_outcome // "") | length) > 0 then "\n\n**Actual:** \(.actual_outcome)" else "" end)
            + (if ((.reading // "") | length) > 0 then "\n\n**Reading:** \(.reading)" else "" end)
            + (if ((.hindsight // "") | length) > 0 then "\n\n**Hindsight:** \(.hindsight)" else "" end)
            + "\n"
        ' "$filtered_tmp"
      }
    )
    ;;
esac

if [ -n "$output_path" ]; then
  printf '%s\n' "$result" >"$output_path"
else
  printf '%s\n' "$result"
fi
