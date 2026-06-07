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
  --impact VALUE
  --fingerprint VALUE
  --tag VALUE               Substring match across tags
  --tag-exact VALUE         Exact tag match
  --alias VALUE             Substring match across aliases
  --alias-exact VALUE       Exact alias match
  --text PATTERN            Case-insensitive substring search across narrative fields
  --date YYYY-MM-DD
  --date-from YYYY-MM-DD
  --date-to YYYY-MM-DD
  --after ISO-TIMESTAMP     Filter events with recorded_at > TIMESTAMP
  --source-ref PATH

Report:
  --report-type TYPE        index|cross-repo|per-repo|timeseries
  --group-by VALUE          impact|alias|tag
  --format md|json
  --output PATH
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
  ''|impact|alias|tag) ;;
  *) die "Unsupported group-by value: $group_by" ;;
esac

if [ -n "$group_by" ] && [ "$report_type" != "timeseries" ]; then
  die "--group-by is only supported with --report-type timeseries"
fi

if ! command -v jq >/dev/null 2>&1; then
  die "jq is required for generate-report.sh"
fi

resolved_events_file_count=0
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
  resolved_events_file_count=$((resolved_events_file_count + 1))
done <<EOF
$events_files
EOF
[ "$resolved_events_file_count" -gt 0 ] || die "No events files resolved"

if [ "$report_type" = "index" ] && [ "$resolved_events_file_count" -ne 1 ]; then
  die "--report-type index requires exactly one events file"
fi

# Build query command
set -- "$SCRIPT_DIR/query-friction.sh"
if [ -n "$scan_dirs" ]; then
  set -- "$@" --scan-dirs
  while IFS= read -r dir; do
    [ -n "$dir" ] || continue
    set -- "$@" "$dir"
  done <<EOF
$scan_dirs
EOF
else
  set -- "$@" --events-file "$events_file"
fi

[ -n "$impact" ] && set -- "$@" --impact "$impact"
[ -n "$fingerprint" ] && set -- "$@" --fingerprint "$fingerprint"
[ -n "$tag" ] && set -- "$@" --tag "$tag"
[ -n "$tag_exact" ] && set -- "$@" --tag-exact "$tag_exact"
[ -n "$alias_filter" ] && set -- "$@" --alias "$alias_filter"
[ -n "$alias_exact" ] && set -- "$@" --alias-exact "$alias_exact"
[ -n "$text" ] && set -- "$@" --text "$text"
[ -n "$date_exact" ] && set -- "$@" --date "$date_exact"
[ -n "$date_from" ] && set -- "$@" --date-from "$date_from"
[ -n "$date_to" ] && set -- "$@" --date-to "$date_to"
[ -n "$after" ] && set -- "$@" --after "$after"
[ -n "$source_ref" ] && set -- "$@" --source-ref "$source_ref"
set -- "$@" --format json

filtered_tmp=$(mktemp)
report_tmp=$(mktemp)
cleanup() {
  rm -f "$filtered_tmp" "$report_tmp"
}
trap cleanup EXIT HUP INT TERM

sh "$@" >"$filtered_tmp"

generated=$(date -u '+%Y-%m-%d %H:%M:%S UTC')

case "$report_type" in
  index)
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

      . as $events
      | ($events | sort_by(.recorded_at // "", .event_id // "")) as $sorted
      | ($sorted | length) as $total
      | ($sorted | map(select((.impact // "") == "blocked")) | length) as $blocked
      | {
          report_type: "index",
          index_rebuilt: $generated,
          repo_root: ($sorted[-1].repo_root // ""),
          events_file: ($sorted[-1].events_file // ""),
          entries: $total,
          blocked: $blocked,
          earliest_event: ($sorted[0].recorded_at // ""),
          latest_event: ($sorted[-1].recorded_at // ""),
          events_list: [
            $sorted[] | {
              event_id: .event_id,
              recorded_at: .recorded_at,
              title: .title,
              impact: (.impact // ""),
              aliases: (.aliases // []),
              tags: (.tags // []),
              sources: [(.sources // [])[] | {ref: .ref, line: .line, end_line: .end_line}]
            }
          ],
          recurring_patterns: (
            count_rows($sorted[] | .fingerprint // empty)
            | map(select(.count > 1))
            | map(. + {
                latest_title: ([$sorted[] | select(.fingerprint == .value)] | last | .title // ""),
                latest_impact: ([$sorted[] | select(.fingerprint == .value)] | last | .impact // "")
              })
            | .[:10]
          ),
          alias_counts: (
            [$sorted | to_entries[] | .key as $idx | (.value.aliases // [])[] | select(. != null and . != "") | {alias: ., event_idx: $idx, blocked: (if $sorted[$idx].impact == "blocked" then 1 else 0 end)}]
            | group_by(.alias)
            | map({
                value: .[0].alias,
                count: (map(.event_idx) | unique | length),
                blocked: (map(select(.blocked == 1)) | map(.event_idx) | unique | length)
              })
            | sort_by([-.count, .value])
          ),
          source_counts: (count_rows($sorted[] | (.sources // [])[]? | .ref // empty) | .[:10]),
          tag_counts: (
            [$sorted | to_entries[] | .key as $idx | (.value.tags // [])[] | select(. != null and . != "") | {tag: ., event_idx: $idx}]
            | unique_by([.tag, .event_idx])
            | group_by(.tag)
            | map({value: .[0].tag, count: length})
            | sort_by([-.count, .value])
          ),
          date_counts: ([count_rows($sorted[] | (.recorded_at // "")[0:10])[]] | sort_by(.value))
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
          impact_summary: count_rows($sorted[] | .impact // empty),
          alias_counts: count_rows_pct($sorted[] | (.aliases // [])[]? // empty; $total),
          tag_counts: count_rows_pct($sorted[] | (.tags // [])[]? // empty; $total),
          fingerprint_counts: (count_rows($sorted[] | .fingerprint // empty) | .[:10])
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
                    entries: $total,
                    earliest_event: ($repo_sorted[0].recorded_at // ""),
                    latest_event: ($repo_sorted[-1].recorded_at // ""),
                    impact_summary: count_rows($repo_sorted[] | .impact // empty),
                    alias_counts: count_rows_pct($repo_sorted[] | (.aliases // [])[]? // empty; $total),
                    tag_counts: count_rows_pct($repo_sorted[] | (.tags // [])[]? // empty; $total),
                    fingerprint_counts: (count_rows($repo_sorted[] | .fingerprint // empty) | .[:10])
                  }
              )
            | sort_by([-.entries, .repo_root, .events_file])
          )
        }
    ' "$filtered_tmp" >"$report_tmp"
    ;;
  timeseries)
    jq --arg generated "$generated" --arg group_by "$group_by" '
      def group_values($group):
        if $group == "" then ["count"]
        elif $group == "impact" then [(.impact // "")]
        elif $group == "alias" then (.aliases // [])
        elif $group == "tag" then (.tags // [])
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
          def md_table_row($cells): "| " + ($cells | join(" | ")) + " |";
          def md_table($headers; $rows; $empty_msg):
            if ($rows | length) == 0 then $empty_msg
            else
              md_table_row($headers)
              + "\n| " + ([$headers[] | gsub("."; "-")] | join(" | ")) + " |"
              + "\n" + ([$rows[] | md_table_row(.)] | join("\n"))
            end;
          def source_display:
            (.ref // "")
            + (if (.line // null) != null then
                ":" + (.line | tostring)
                + (if (.end_line // null) != null then "-" + (.end_line | tostring) else "" end)
              else "" end);
          def days_between($a; $b):
            if ($a == "" or $b == "") then null
            else
              (($b[0:10] | split("-") | map(tonumber)) as [$by, $bm, $bd] |
               ($a[0:10] | split("-") | map(tonumber)) as [$ay, $am, $ad] |
               (($by - $ay) * 365 + ($bm - $am) * 30 + ($bd - $ad)))
            end;

          (days_between(.earliest_event; .latest_event)) as $span
          |
          "# Friction Index\n\n"
          + "**Created:** \(.earliest_event // "(not available)")\n"
          + "**Last event:** \(.latest_event // "(not available)")\n"
          + "**Index rebuilt:** \(.index_rebuilt)\n"
          + "**Events:** \(.entries) | **Blocked:** \(.blocked)"
          + (if $span != null then " | **Span:** \($span) days" else "" end)
          + "\n\n## Events\n\n"
          + md_table(["ID", "Time", "Title", "Impact", "Aliases"];
              [.events_list[] | [
                .event_id,
                ((.recorded_at // "")[5:16]),
                (.title // "" | if length > 50 then .[:47] + "..." else . end),
                (.impact // ""),
                ((.aliases // []) | join(", "))
              ]];
              "_No events._")
          + "\n\n## Recurring Patterns\n\n"
          + (if (.recurring_patterns | length) == 0 then "_No recurring patterns._"
             else md_table(["Fingerprint", "Count", "Latest Title", "Impact"];
              [.recurring_patterns[] | [
                .value,
                (.count | tostring),
                (.latest_title // "" | if length > 40 then .[:37] + "..." else . end),
                (.latest_impact // "")
              ]];
              "_No recurring patterns._")
            end)
          + "\n\n## By Alias\n\n"
          + md_table(["Alias", "Events", "Blocked"];
              [.alias_counts[] | [.value, (.count | tostring), (.blocked | tostring)]];
              "_No aliases recorded._")
          + "\n\n## By Source\n\n"
          + md_table(["Source", "Events"];
              [.source_counts[] | [.value, (.count | tostring)]];
              "_No sources recorded._")
          + "\n\n## Tags\n\n"
          + md_table(["Tag", "Events"];
              [.tag_counts[] | [.value, (.count | tostring)]];
              "_No tags recorded._")
          + "\n\n## Date Distribution\n\n"
          + md_table(["Date", "Count"];
              [.date_counts[] | [.value, (.count | tostring)]];
              "_No date counts available._")
        ' "$report_tmp")
        ;;
      cross-repo)
        result=$(jq -r '
          def md_table_row($cells): "| " + ($cells | join(" | ")) + " |";
          def md_table($headers; $rows; $empty_msg):
            if ($rows | length) == 0 then $empty_msg
            else
              md_table_row($headers)
              + "\n| " + ([$headers[] | gsub("."; "-")] | join(" | ")) + " |"
              + "\n" + ([$rows[] | md_table_row(.)] | join("\n"))
            end;
          "# Cross-Repo Friction Index\n\n"
          + "**Index rebuilt:** \(.index_rebuilt)\n"
          + "**Repos scanned:** \(.repos_scanned)\n"
          + "**Total entries:** \(.total_entries)\n\n"
          + "## Repos\n\n"
          + (if (.repos | length) == 0 then "_No repos matched._"
             else ([.repos[] | "- `\((if (.repo_root // "") != "" then .repo_root else .events_file end))` — \(.entries) events"] | join("\n")) end)
          + "\n\n## Impact Summary\n\n"
          + md_table(["Impact", "Count"];
              [.impact_summary[] | [.value, (.count | tostring)]];
              "_No events._")
          + "\n\n## Aliases\n\n"
          + md_table(["Alias", "Count", "%"];
              [.alias_counts[] | [.value, (.count | tostring), .percent]];
              "_No aliases recorded._")
          + "\n\n## Tags\n\n"
          + md_table(["Tag", "Count", "%"];
              [.tag_counts[] | [.value, (.count | tostring), .percent]];
              "_No tags recorded._")
          + "\n\n## Top Fingerprints\n\n"
          + md_table(["Fingerprint", "Count"];
              [.fingerprint_counts[] | [.value, (.count | tostring)]];
              "_No fingerprints._")
        ' "$report_tmp")
        ;;
      per-repo)
        result=$(jq -r '
          def md_table_row($cells): "| " + ($cells | join(" | ")) + " |";
          def md_table($headers; $rows; $empty_msg):
            if ($rows | length) == 0 then $empty_msg
            else
              md_table_row($headers)
              + "\n| " + ([$headers[] | gsub("."; "-")] | join(" | ")) + " |"
              + "\n" + ([$rows[] | md_table_row(.)] | join("\n"))
            end;
          "# Per-Repo Friction Report\n\n"
          + "**Index rebuilt:** \(.index_rebuilt)\n"
          + "**Repos:** \(.repos) | **Total entries:** \(.total_entries)\n"
          + (if (.repo_summaries | length) == 0 then "\n_No repos matched._"
             else (
               .repo_summaries
               | map(
                   "\n---\n\n## \((if (.repo_root // "") != "" then .repo_root else .events_file end))\n"
                   + "**Entries:** \(.entries) | **Earliest:** \((.earliest_event // "")[0:10]) | **Latest:** \((.latest_event // "")[0:10])\n\n"
                   + "### Impact\n\n"
                   + md_table(["Impact", "Count"];
                       [.impact_summary[] | [.value, (.count | tostring)]];
                       "_No events._")
                   + "\n\n### Aliases\n\n"
                   + md_table(["Alias", "Count", "%"];
                       [.alias_counts[] | [.value, (.count | tostring), .percent]];
                       "_No aliases._")
                   + "\n\n### Tags\n\n"
                   + md_table(["Tag", "Count", "%"];
                       [.tag_counts[] | [.value, (.count | tostring), .percent]];
                       "_No tags._")
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
                "# Friction Time Series (by \($report.group_by))\n\n_No dated events matched._"
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
              "# Friction Time Series\n\n_No dated events matched._"
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
