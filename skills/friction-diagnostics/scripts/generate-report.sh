#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
. "$SCRIPT_DIR/_common.sh"

print_help() {
  cat <<'EOF'
Usage:
  sh scripts/generate-report.sh [--events-file PATH | --scan-dirs DIR [DIR...]] [filters] [report options]

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
  --agent-kind VALUE
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
  --source-ref PATH

Report:
  --report-type TYPE        index|cross-repo|per-repo|timeseries
  --group-by VALUE          surface|mode|run_effect|category|tag|agent_kind
  --format md|json
  --output PATH
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
agent_kind=
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
source_ref=
report_type=index
group_by=
format=md
output_path=

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
    --agent-kind) agent_kind=${2-}; shift 2 ;;
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
    --source-ref) source_ref=${2-}; shift 2 ;;
    --report-type) report_type=${2-}; shift 2 ;;
    --group-by) group_by=${2-}; shift 2 ;;
    --format) format=${2-}; shift 2 ;;
    --output) output_path=${2-}; shift 2 ;;
    --help|-h) print_help; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
done

case "$report_type" in
  index|cross-repo|per-repo|timeseries) ;;
  *) die "Unsupported report type: $report_type" ;;
esac

case "$format" in
  md|json) ;;
  *) die "Unsupported format: $format" ;;
esac

case "$group_by" in
  ''|surface|mode|run_effect|category|tag|agent_kind) ;;
  *) die "Unsupported group-by value: $group_by" ;;
esac

if [ -n "$group_by" ] && [ "$report_type" != "timeseries" ]; then
  die "--group-by is only supported with --report-type timeseries"
fi

if ! command -v jq >/dev/null 2>&1; then
  die "jq is required for generate-report.sh"
fi

query_cmd="sh $(shell_quote "$SCRIPT_DIR/query-friction.sh")"
if [ -n "$scan_dirs" ]; then
  query_cmd="$query_cmd --scan-dirs"
  while IFS= read -r dir; do
    [ -n "$dir" ] || continue
    query_cmd="$query_cmd $(shell_quote "$dir")"
  done <<EOF
$scan_dirs
EOF
else
  if [ -n "$events_file" ]; then
    query_cmd="$query_cmd --events-file $(shell_quote "$events_file")"
  fi
fi

append_arg() {
  flag=$1
  value=$2
  if [ -n "$value" ]; then
    query_cmd="$query_cmd $flag $(shell_quote "$value")"
  fi
}

append_arg --category "$category"
append_arg --surface "$surface"
append_arg --mode "$mode"
append_arg --run-effect "$run_effect"
append_arg --fingerprint "$fingerprint"
append_arg --agent-kind "$agent_kind"
append_arg --role "$role"
append_arg --tag "$tag"
append_arg --text "$text"
append_arg --confidence-min "$confidence_min"
append_arg --confidence-max "$confidence_max"
append_arg --guidance-min "$guidance_min"
append_arg --guidance-max "$guidance_max"
append_arg --exit-code "$exit_code"
append_arg --tool-name "$tool_name"
append_arg --owner-hint "$owner_hint"
append_arg --component-hint "$component_hint"
if [ "$workaround" -eq 1 ]; then
  query_cmd="$query_cmd --workaround"
fi
append_arg --date "$date_exact"
append_arg --date-from "$date_from"
append_arg --date-to "$date_to"
append_arg --after "$after"
append_arg --source-ref "$source_ref"
query_cmd="$query_cmd --format json"

filtered_tmp=$(mktemp)
report_tmp=$(mktemp)
cleanup() {
  rm -f "$filtered_tmp" "$report_tmp"
}
trap cleanup EXIT HUP INT TERM

eval "$query_cmd" >"$filtered_tmp"

generated=$(date -u '+%Y-%m-%d %H:%M:%S UTC')

case "$report_type" in
  index)
    unique_files=$(jq '[.[].events_file // empty] | unique | length' "$filtered_tmp")
    if [ "$unique_files" -gt 1 ]; then
      die "--report-type index requires exactly one events file"
    fi
    jq --arg generated "$generated" '
      def pct($count; $total):
        if $total <= 0 then "0%"
        else (((($count * 100) / $total) + 0.5) | floor | tostring) + "%"
        end;
      def count_rows(stream):
        [stream | select(. != null and . != "")]
        | group_by(.)
        | map({value: .[0], count: length})
        | sort_by([-.count, .value]);
      def count_rows_pct(stream; $total):
        count_rows(stream) | map(. + {percent: pct(.count; $total)});
      def run_effect_value:
        (.run_effect // (((.derived_category // "") | split("/") + ["", "", ""])[2]) // "");

      . as $events
      | ($events | sort_by(.recorded_at // "", .event_id // "")) as $sorted
      | ($sorted | length) as $total
      | {
          report_type: "index",
          index_rebuilt: $generated,
          repo_root: ($sorted[-1].repo_root // ""),
          events_file: ($sorted[-1].events_file // ""),
          entries: $total,
          earliest_event: ($sorted[0].recorded_at // ""),
          latest_event: ($sorted[-1].recorded_at // ""),
          category_counts: count_rows_pct($sorted[] | .derived_category // empty; $total),
          fingerprint_counts: (count_rows($sorted[] | .fingerprint // empty) | .[:10]),
          agent_kind_counts: count_rows($sorted[] | if (.provenance_source // "") == "explicit" then (.agent_kind // empty) else empty end),
          date_counts: ([count_rows($sorted[] | (.recorded_at // "")[0:10])[]] | sort_by(.value)),
          tag_counts: count_rows_pct($sorted[] | (.tags // [])[]? // empty; $total),
          top_sources: (count_rows($sorted[] | (.sources // [])[]? | .ref // empty) | .[:10]),
          run_effect_summary: count_rows($sorted[] | run_effect_value)
        }
    ' "$filtered_tmp" >"$report_tmp"
    ;;
  cross-repo)
    jq --arg generated "$generated" '
      def pct($count; $total):
        if $total <= 0 then "0%"
        else (((($count * 100) / $total) + 0.5) | floor | tostring) + "%"
        end;
      def count_rows(stream):
        [stream | select(. != null and . != "")]
        | group_by(.)
        | map({value: .[0], count: length})
        | sort_by([-.count, .value]);
      def count_rows_pct(stream; $total):
        count_rows(stream) | map(. + {percent: pct(.count; $total)});
      def run_effect_value:
        (.run_effect // (((.derived_category // "") | split("/") + ["", "", ""])[2]) // "");

      . as $events
      | ($events | sort_by(.recorded_at // "", .event_id // "")) as $sorted
      | ($sorted | length) as $total
      | {
          report_type: "cross-repo",
          index_rebuilt: $generated,
          repos_scanned: ([ $sorted[] | .events_file // empty ] | unique | length),
          total_entries: $total,
          repos: (
            [ $sorted[]
              | {repo_root: (.repo_root // ""), events_file: (.events_file // "")}
            ]
            | group_by(.events_file)
            | map({
                repo_root: .[0].repo_root,
                events_file: .[0].events_file,
                entries: length
              })
            | sort_by([-.entries, .repo_root, .events_file])
          ),
          category_counts: count_rows_pct($sorted[] | .derived_category // empty; $total),
          fingerprint_counts: (count_rows($sorted[] | .fingerprint // empty) | .[:10]),
          run_effect_summary: count_rows($sorted[] | run_effect_value),
          tag_counts: count_rows_pct($sorted[] | (.tags // [])[]? // empty; $total)
        }
    ' "$filtered_tmp" >"$report_tmp"
    ;;
  per-repo)
    jq --arg generated "$generated" '
      def pct($count; $total):
        if $total <= 0 then "0%"
        else (((($count * 100) / $total) + 0.5) | floor | tostring) + "%"
        end;
      def count_rows(stream):
        [stream | select(. != null and . != "")]
        | group_by(.)
        | map({value: .[0], count: length})
        | sort_by([-.count, .value]);
      def count_rows_pct(stream; $total):
        count_rows(stream) | map(. + {percent: pct(.count; $total)});
      def run_effect_value:
        (.run_effect // (((.derived_category // "") | split("/") + ["", "", ""])[2]) // "");

      . as $events
      | ($events | sort_by(.recorded_at // "", .event_id // "")) as $sorted
      | {
          report_type: "per-repo",
          index_rebuilt: $generated,
          repos: ([ $sorted[] | .events_file // empty ] | unique | length),
          total_entries: ($sorted | length),
          repo_summaries: (
            [ $sorted[] ]
            | group_by(.events_file // "")
            | map(
                . as $repo_events
                | ($repo_events | sort_by(.recorded_at // "", .event_id // "")) as $repo_sorted
                | ($repo_sorted | length) as $total
                | {
                    repo_root: ($repo_sorted[-1].repo_root // ""),
                    events_file: ($repo_sorted[-1].events_file // ""),
                    events_file_display: (
                      ($repo_sorted[-1].events_file // "") as $ef
                      | ($repo_sorted[-1].repo_root // "") as $rr
                      | if $rr != "" and ($ef | startswith($rr + "/")) then ($ef | ltrimstr($rr + "/")) else $ef end
                    ),
                    entries: $total,
                    earliest_event: ($repo_sorted[0].recorded_at // ""),
                    latest_event: ($repo_sorted[-1].recorded_at // ""),
                    category_counts: count_rows_pct($repo_sorted[] | .derived_category // empty; $total),
                    fingerprint_counts: (count_rows($repo_sorted[] | .fingerprint // empty) | .[:10]),
                    tag_counts: count_rows_pct($repo_sorted[] | (.tags // [])[]? // empty; $total),
                    run_effect_summary: count_rows($repo_sorted[] | run_effect_value)
                  }
              )
            | sort_by([-.entries, .repo_root, .events_file])
          )
        }
    ' "$filtered_tmp" >"$report_tmp"
    ;;
  timeseries)
    jq --arg generated "$generated" --arg group_by "$group_by" '
      def category_parts:
        ((.derived_category // "") | split("/") + ["", "", ""])[0:3];
      def group_values($group):
        if $group == "" then ["count"]
        elif $group == "surface" then [category_parts[0]]
        elif $group == "mode" then [category_parts[1]]
        elif $group == "run_effect" then [(.run_effect // category_parts[2])]
        elif $group == "category" then [(.derived_category // "")]
        elif $group == "tag" then (.tags // [])
        elif $group == "agent_kind" then [(.agent_kind // "")]
        else []
        end
        | map(select(. != null and . != ""));

      . as $events
      | [ $events[] | select((.recorded_at // "") | length >= 10) | . + {event_date: (.recorded_at[0:10])} ] as $dated
      | if $group_by == "" then
          {
            report_type: "timeseries",
            index_rebuilt: $generated,
            group_by: "",
            columns: ["count"],
            rows: (
              [ $dated[] | .event_date ]
              | group_by(.)
              | map({date: .[0], count: length})
              | sort_by(.date)
            )
          }
        else
          (
            [ $dated[] | group_values($group_by)[] ] | unique | sort
          ) as $columns
          | {
              report_type: "timeseries",
              index_rebuilt: $generated,
              group_by: $group_by,
              columns: $columns,
              rows: (
                [ $dated[]
                  | . as $event
                  | group_values($group_by)[]
                  | {date: $event.event_date, key: ., value: 1}
                ]
                | group_by(.date)
                | map(
                    . as $date_rows
                    | {date: .[0].date}
                    + (
                        reduce $columns[] as $column
                          ({};
                           . + {
                             ($column):
                               (
                                 [$date_rows[] | select(.key == $column)]
                                 | length
                               )
                           })
                      )
                  )
                | sort_by(.date)
              )
            }
        end
    ' "$filtered_tmp" >"$report_tmp"
    ;;
esac

case "$format" in
  json)
    result=$(cat "$report_tmp")
    ;;
  md)
    case "$report_type" in
      index)
        result=$(jq -r '
          def row_pct($rows; $empty):
            if ($rows | length) == 0 then $empty else ([$rows[] | "- `\(.value)` - \(.count) (\(.percent))"] | join("\n")) end;
          def row_plain($rows; $empty; $suffix):
            if ($rows | length) == 0 then $empty else ([$rows[] | "- `\(.value)` - \(.count)\($suffix)"] | join("\n")) end;
          "# Friction Index\n\n"
          + "**Index rebuilt:** \(.index_rebuilt)\n"
          + "**Events file:** \(.events_file)\n"
          + (if (.repo_root // "") != "" then "**Repo root:** \(.repo_root)\n" else "" end)
          + "**Entries:** \(.entries)\n"
          + "**Earliest event:** \((.earliest_event // "") | if . == "" then "(not available)" else . end)\n"
          + "**Latest event:** \((.latest_event // "") | if . == "" then "(not available)" else . end)\n\n"
          + "## Category Counts\n\n"
          + ([row_pct(.category_counts; "_No categorized events._")] | join("\n"))
          + "\n\n## Top Fingerprints\n\n"
          + ([row_plain(.fingerprint_counts; "_No fingerprints yet._"; " events")] | join("\n"))
          + "\n\n## Agent Kinds\n\n"
          + ([row_plain(.agent_kind_counts; "_No explicit provenance recorded._"; "")] | join("\n"))
          + "\n\n## Date Counts\n\n"
          + ([row_plain(.date_counts; "_No date counts available._"; "")] | join("\n"))
          + "\n\n## Tags\n\n"
          + ([row_pct(.tag_counts; "_No tags recorded._")] | join("\n"))
          + "\n\n## Top Sources\n\n"
          + ([row_plain(.top_sources; "_No sources recorded._"; "")] | join("\n"))
          + "\n\n## Run Effect Summary\n\n"
          + ([row_plain(.run_effect_summary; "_No run effects recorded._"; "")] | join("\n"))
        ' "$report_tmp")
        ;;
      cross-repo)
        result=$(jq -r '
          def row_pct($rows; $empty):
            if ($rows | length) == 0 then $empty else ([$rows[] | "- `\(.value)` - \(.count) (\(.percent))"] | join("\n")) end;
          def row_plain($rows; $empty; $suffix):
            if ($rows | length) == 0 then $empty else ([$rows[] | "- `\(.value)` - \(.count)\($suffix)"] | join("\n")) end;
          "# Cross-Repo Friction Index\n\n"
          + "**Index rebuilt:** \(.index_rebuilt)\n"
          + "**Repos scanned:** \(.repos_scanned)\n"
          + "**Total entries:** \(.total_entries)\n\n"
          + "## Repos\n\n"
          + (if (.repos | length) == 0 then "_No repos matched the selected filters._"
             else ([.repos[] | "- `\((if (.repo_root // "") != "" then .repo_root else .events_file end))` - \(.entries) events"] | join("\n")) end)
          + "\n\n## Category Counts (all repos)\n\n"
          + ([row_pct(.category_counts; "_No categorized events._")] | join("\n"))
          + "\n\n## Top Fingerprints (all repos)\n\n"
          + ([row_plain(.fingerprint_counts; "_No fingerprints yet._"; " events")] | join("\n"))
          + "\n\n## Run Effect Summary\n\n"
          + ([row_plain(.run_effect_summary; "_No run effects recorded._"; "")] | join("\n"))
          + "\n\n## Tags\n\n"
          + ([row_pct(.tag_counts; "_No tags recorded._")] | join("\n"))
        ' "$report_tmp")
        ;;
      per-repo)
        result=$(jq -r '
          def row_pct($rows; $empty):
            if ($rows | length) == 0 then $empty else ([$rows[] | "- `\(.value)` - \(.count) (\(.percent))"] | join("\n")) end;
          def row_plain($rows; $empty; $suffix):
            if ($rows | length) == 0 then $empty else ([$rows[] | "- `\(.value)` - \(.count)\($suffix)"] | join("\n")) end;
          "# Per-Repo Friction Report\n\n"
          + "**Index rebuilt:** \(.index_rebuilt)\n"
          + "**Repos:** \(.repos) | **Total entries:** \(.total_entries)\n"
          + (if (.repo_summaries | length) == 0 then "\n_No repos matched the selected filters._"
             else (
               .repo_summaries
               | map(
                   "\n---\n\n## \((if (.repo_root // "") != "" then .repo_root else .events_file end))\n"
                   + "**Events file:** \(.events_file_display)\n"
                   + "**Entries:** \(.entries) | **Earliest event:** \((.earliest_event // "") | if . == "" then "(not available)" else . end) | **Latest event:** \((.latest_event // "") | if . == "" then "(not available)" else . end)\n\n"
                   + "### Category Counts\n\n"
                   + ([row_pct(.category_counts; "_No categorized events._")] | join("\n"))
                   + "\n\n### Top Fingerprints\n\n"
                   + ([row_plain(.fingerprint_counts; "_No fingerprints yet._"; " events")] | join("\n"))
                   + "\n\n### Run Effect Summary\n\n"
                   + ([row_plain(.run_effect_summary; "_No run effects recorded._"; "")] | join("\n"))
                   + "\n\n### Tags\n\n"
                   + ([row_pct(.tag_counts; "_No tags recorded._")] | join("\n"))
                 )
               | join("")
             )
            end)
        ' "$report_tmp")
        ;;
      timeseries)
        if [ -n "$group_by" ]; then
          result=$(jq -r '
            . as $report
            | if (.rows | length) == 0 then
                "# Friction Time Series (by \($report.group_by))\n\n_No dated events matched the selected filters._"
              else
                (["Date"] + $report.columns) as $headers
                | (
                    [
                      "# Friction Time Series (by \($report.group_by))",
                      "",
                      "| " + ($headers | join(" | ")) + " |",
                      "|" + ($headers | map("-" * (length + 2)) | join("|")) + "|"
                    ]
                    + (
                        $report.rows
                        | map(
                            . as $row
                            | ([$row.date] + ($report.columns | map(($row[.] // 0) | tostring))) as $cells
                            | "| " + ($cells | join(" | ")) + " |"
                          )
                      )
                  )
                | join("\n")
              end
          ' "$report_tmp")
        else
          result=$(jq -r '
            if (.rows | length) == 0 then
              "# Friction Time Series\n\n_No dated events matched the selected filters._"
            else
              (
                [
                  "# Friction Time Series",
                  "",
                  "| Date | Count |",
                  "|------|-------|"
                ]
                + (.rows | map("| \(.date) | \(.count) |"))
              )
              | join("\n")
            end
          ' "$report_tmp")
        fi
        ;;
    esac
    ;;
esac

if [ -n "$output_path" ]; then
  printf '%s\n' "$result" >"$output_path"
else
  printf '%s\n' "$result"
fi
