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
  --category VALUE
  --surface VALUE
  --mode VALUE
  --run-effect VALUE
  --fingerprint VALUE
  --role VALUE
  --tag VALUE               Single tag filter; repeat support is not implemented
  --text PATTERN            Case-insensitive substring search across narrative fields
  --confidence-min N
  --confidence-max N
  --guidance-min N
  --guidance-max N
  --exit-code N
  --tool-name VALUE
  --owner-hint VALUE
  --component-hint VALUE
  --workaround              Only include events with workaround_used=true
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
  --suggest-tags
  --help
EOF
}

events_file=${FRICTION_EVENTS_FILE-}
scan_dirs=
category=
surface=
mode=
run_effect=
fingerprint=
role=
tag=
text=
confidence_min=
confidence_max=
guidance_min=
guidance_max=
exit_code=
tool_name=
owner_hint=
component_hint=
workaround=0
date_exact=
date_from=
date_to=
after=
before=
source_ref=
format=jsonl
output_path=
suggest_tags=0
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
    --category) category=${2-}; shift 2 ;;
    --surface) surface=${2-}; shift 2 ;;
    --mode) mode=${2-}; shift 2 ;;
    --run-effect) run_effect=${2-}; shift 2 ;;
    --fingerprint) fingerprint=${2-}; shift 2 ;;
    --role) role=${2-}; shift 2 ;;
    --tag) tag=${2-}; shift 2 ;;
    --text) text=${2-}; shift 2 ;;
    --confidence-min) confidence_min=${2-}; shift 2 ;;
    --confidence-max) confidence_max=${2-}; shift 2 ;;
    --guidance-min) guidance_min=${2-}; shift 2 ;;
    --guidance-max) guidance_max=${2-}; shift 2 ;;
    --exit-code) exit_code=${2-}; shift 2 ;;
    --tool-name) tool_name=${2-}; shift 2 ;;
    --owner-hint) owner_hint=${2-}; shift 2 ;;
    --component-hint) component_hint=${2-}; shift 2 ;;
    --workaround) workaround=1; shift ;;
    --date) date_exact=${2-}; shift 2 ;;
    --date-from) date_from=${2-}; shift 2 ;;
    --date-to) date_to=${2-}; shift 2 ;;
    --after) after=${2-}; shift 2 ;;
    --before) before=${2-}; shift 2 ;;
    --source-ref) source_ref=${2-}; shift 2 ;;
    --format) format=${2-}; shift 2 ;;
    --output) output_path=${2-}; shift 2 ;;
    --compact) compact=1; shift ;;
    --suggest-tags) suggest_tags=1; shift ;;
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
  --arg category "$category" \
  --arg surface "$surface" \
  --arg mode "$mode" \
  --arg run_effect "$run_effect" \
  --arg fingerprint "$fingerprint" \
  --arg role "$role" \
  --arg tag "$tag" \
  --arg text "$text" \
  --arg confidence_min "$confidence_min" \
  --arg confidence_max "$confidence_max" \
  --arg guidance_min "$guidance_min" \
  --arg guidance_max "$guidance_max" \
  --arg exit_code "$exit_code" \
  --arg tool_name "$tool_name" \
  --arg owner_hint "$owner_hint" \
  --arg component_hint "$component_hint" \
  --arg workaround "$workaround" \
  --arg date_exact "$date_exact" \
  --arg date_from "$date_from" \
  --arg date_to "$date_to" \
  --arg after "$after" \
  --arg before "$before" \
  --arg source_ref "$source_ref" \
  '
  def category_parts:
    (.derived_category // "" | split("/") + ["", "", ""])[0:3];
  def as_num:
    if . == null or . == "" then null else (try (tonumber) catch null) end;
  def event_tags:
    (.tags // [] | map(tostring));
  def matches_source_ref($ref):
    if $ref == "" then true else any((.sources // [])[]?; (.ref // "") == $ref) end;
  def text_match($needle):
    if $needle == "" then true
    else
      ([.title, .actual_outcome, .action_taken, .reading, .hindsight, .instruction_text, .expected_outcome]
       | map((. // "") | ascii_downcase)
       | join("\u0000")
       | contains($needle | ascii_downcase))
    end;
  def compact_obj:
    with_entries(select(.value != null and .value != ""));

  map(
    select(
      ($category == "" or (.derived_category // "") == $category) and
      ($surface == "" or (category_parts[0] == $surface)) and
      ($mode == "" or (category_parts[1] == $mode)) and
      ($run_effect == "" or (category_parts[2] == $run_effect)) and
      ($fingerprint == "" or (.fingerprint // "") == $fingerprint) and
      ($role == "" or (.role // "") == $role) and
      ($tag == "" or (event_tags | index($tag)) != null) and
      text_match($text) and
      ($confidence_min == "" or ((.confidence | as_num) as $v | $v != null and $v >= ($confidence_min | tonumber))) and
      ($confidence_max == "" or ((.confidence | as_num) as $v | $v != null and $v <= ($confidence_max | tonumber))) and
      ($guidance_min == "" or ((.guidance_quality | as_num) as $v | $v != null and $v >= ($guidance_min | tonumber))) and
      ($guidance_max == "" or ((.guidance_quality | as_num) as $v | $v != null and $v <= ($guidance_max | tonumber))) and
      ($exit_code == "" or ((.exit_code | as_num) as $v | $v != null and $v == ($exit_code | tonumber))) and
      ($tool_name == "" or (.tool_name // "") == $tool_name) and
      ($owner_hint == "" or (.owner_hint // "") == $owner_hint) and
      ($component_hint == "" or (.component_hint // "") == $component_hint) and
      ($workaround != "1" or (.workaround_used // false) == true) and
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

if [ "$suggest_tags" -eq 1 ]; then
  result=$(jq -r '.[] | (.tags // [])[]? // empty' "$filtered_tmp" | LC_ALL=C sort -u)
  if [ -n "$output_path" ]; then
    printf '%s\n' "$result" >"$output_path"
  else
    printf '%s\n' "$result"
  fi
  exit 0
fi

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
            + "\n- Category: \(.derived_category // "")"
            + "\n- Fingerprint: \(.fingerprint // "")"
            + (if ((.incident_id // "") | length) > 0 then "\n- Incident: \(.incident_id)" else "" end)
            + (if ((.agent_name // "") | length) > 0 then "\n- Agent: \(.agent_name)" else "" end)
            + (if ((.role // "") | length) > 0 then "\n- Role: \(.role)" else "" end)
            + (if ((.confidence // 0) != 0 or (.guidance_quality // 0) != 0) then "\n- Confidence: \(.confidence // 0) | Guidance: \(.guidance_quality // 0)" else "" end)
            + (if (.exit_code // null) != null then "\n- Exit code: \(.exit_code)" else "" end)
            + (if ((.tool_name // "") | length) > 0 then "\n- Tool: \(.tool_name)" else "" end)
            + (if ((.command // "") | length) > 0 then "\n- Command: \(.command)" else "" end)
            + (if ((.owner_hint // "") | length) > 0 then "\n- Owner: \(.owner_hint)" else "" end)
            + (if ((.component_hint // "") | length) > 0 then "\n- Component: \(.component_hint)" else "" end)
            + (if (.workaround_used // false) == true then "\n- Workaround used: yes" else "" end)
            + (if ((.workaround_note // "") | length) > 0 then "\n- Workaround: \(.workaround_note)" else "" end)
            + (if ((.retries_lost // 0) | tonumber) > 0 then "\n- Retries lost: \(.retries_lost)" else "" end)
            + (if ((.minutes_lost // 0) | tonumber) > 0 then "\n- Minutes lost: \(.minutes_lost)" else "" end)
            + (if ((.superproject_root // "") | length) > 0 then "\n- Superproject: \(.superproject_root)" else "" end)
            + (if ((.submodule_path // "") | length) > 0 then "\n- Submodule: \(.submodule_path)" else "" end)
            + (if ((.sources // []) | length) > 0 then
                "\n- Sources: " + ([(.sources // [])[] |
                  (.ref // "") + (if (.line // null) != null then ":" + (.line | tostring) + (if (.end_line // null) != null then "-" + (.end_line | tostring) else "" end) else "" end)
                ] | join(", "))
              else "" end)
            + ((.tags // []) | if length > 0 then "\n- Tags: " + join(", ") else "" end)
            + (if ((.stderr // "") | length) > 0 then "\n- Stderr: \(.stderr | split("\n")[0])" else "" end)
            + (if ((.stdout_excerpt // "") | length) > 0 then "\n- Stdout excerpt: \(.stdout_excerpt | split("\n")[0])" else "" end)
            + (if ((.instruction_text // "") | length) > 0 then "\n\n**Instruction:** \(.instruction_text)" else "" end)
            + (if ((.action_taken // "") | length) > 0 then "\n\n**Action taken:** \(.action_taken)" else "" end)
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
