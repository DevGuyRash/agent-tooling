#!/bin/sh

# --- Schema SSOT ---
# All field definitions live in friction-event-schema.json.
# Scripts query it via jq at startup to derive field lists.
SCHEMA_FILE="${SCHEMA_FILE:-$(CDPATH='' cd -- "$(dirname "$0")/.." && pwd)/friction-event-schema.json}"
_SCHEMA_CACHE=

load_schema() {
  if [ -z "$_SCHEMA_CACHE" ]; then
    [ -f "$SCHEMA_FILE" ] || die "Schema file not found: $SCHEMA_FILE"
    _SCHEMA_CACHE=$(cat "$SCHEMA_FILE")
  fi
  printf '%s\n' "$_SCHEMA_CACHE"
}

# Return newline-separated field names matching a jq filter on field properties.
# Usage: schema_fields_where '.["x-searchable"] == true'
schema_fields_where() {
  filter=$1
  load_schema | jq -r --arg f "$filter" \
    '[.properties | to_entries[] | select(.value | '"$filter"') | .key] | .[]'
}

# Return the ordered field list for md rendering.
schema_md_render_order() {
  load_schema | jq -r '.["x-render-md-order"][]'
}

# Return the ordered field list for report aggregation.
schema_aggregate_order() {
  load_schema | jq -r '.["x-aggregate-order"][]'
}

# Return all known event field names.
schema_all_fields() {
  load_schema | jq -r '.properties | keys[]'
}

# Return a specific x- property for a given field.
# Usage: schema_field_prop "title" "x-render-md"
schema_field_prop() {
  field=$1
  prop=$2
  load_schema | jq -r --arg f "$field" --arg p "$prop" '.properties[$f][$p] // empty'
}

# Return searchable field names as a jq-compatible array string.
# Useful for injecting into jq filters at runtime.
schema_searchable_fields_jq() {
  load_schema | jq -c '[.properties | to_entries[] | select(.value["x-searchable"] == true) | .key]'
}

# Version constants derived from schema SSOT.
SCHEMA_VERSION=$(load_schema | jq -r '.["x-schema-version"] // "3.0.0"' 2>/dev/null || echo "3.0.0")
TAXONOMY_VERSION=$(load_schema | jq -r '.["x-taxonomy-version"] // "2.0.0"' 2>/dev/null || echo "2.0.0")

die() {
  printf '%s\n' "$*" >&2
  exit 1
}

lower() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]'
}

short_hash() {
  input=$1
  length=${2:-8}
  if command -v sha256sum >/dev/null 2>&1; then
    printf '%s' "$input" | sha256sum | awk -v n="$length" '{print substr($1, 1, n)}'
  elif command -v shasum >/dev/null 2>&1; then
    printf '%s' "$input" | shasum -a 256 | awk -v n="$length" '{print substr($1, 1, n)}'
  elif command -v openssl >/dev/null 2>&1; then
    printf '%s' "$input" | openssl dgst -sha256 | sed 's/^.*= //' | cut -c1-"$length"
  else
    die "short_hash: no suitable hash command found (sha256sum, shasum, openssl)"
  fi
}

slugify() {
  input=$1
  slug=$(
    printf '%s' "$input" |
      tr '[:upper:]' '[:lower:]' |
      tr '\n\r' '--' |
      sed 's/[^a-z0-9][^a-z0-9]*/-/g; s/^-//; s/-$//'
  )
  if [ -z "$slug" ]; then
    slug=friction-task
  fi
  printf '%s\n' "$slug"
}

truncate_chars() {
  value=$1
  limit=$2
  if [ "$limit" -le 0 ]; then
    printf '\n'
    return 0
  fi
  printf '%s' "$value" | cut -c1-"$limit"
  printf '\n'
}

bounded_slugify() {
  input=$1
  limit=${2:-255}
  slug=$(slugify "$input")
  length=$(printf '%s' "$slug" | wc -c | tr -d ' ')
  if [ "$length" -le "$limit" ]; then
    printf '%s\n' "$slug"
    return 0
  fi

  hash=$(short_hash "$slug")
  suffix="-$hash"
  suffix_length=$(printf '%s' "$suffix" | wc -c | tr -d ' ')
  prefix_limit=$((limit - suffix_length))
  if [ "$prefix_limit" -lt 1 ]; then
    prefix_limit=1
  fi
  prefix=$(truncate_chars "$slug" "$prefix_limit")
  prefix=$(printf '%s' "$prefix" | sed 's/-*$//')
  if [ -z "$prefix" ]; then
    prefix=friction-task
  fi
  printf '%s%s\n' "$prefix" "$suffix"
}

shell_quote() {
  printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"
}

append_csv() {
  list=$1
  item=$2
  if [ -z "$item" ]; then
    printf '%s\n' "$list"
    return 0
  fi
  case ",$list," in
    *,"$item",*)
      printf '%s\n' "$list"
      ;;
    *)
      if [ -n "$list" ]; then
        printf '%s,%s\n' "$list" "$item"
      else
        printf '%s\n' "$item"
      fi
      ;;
  esac
}

trim() {
  printf '%s' "$1" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//'
}

first_line() {
  printf '%s\n' "$1" | sed -n '1p'
}

truncate_line() {
  value=$1
  limit=${2:-80}
  line=$(first_line "$value")
  length=$(printf '%s' "$line" | wc -c | tr -d ' ')
  if [ "$length" -gt "$limit" ]; then
    prefix_len=$((limit - 3))
    if [ "$prefix_len" -lt 1 ]; then
      prefix_len=1
    fi
    printf '%s...\n' "$(printf '%s' "$line" | cut -c1-"$prefix_len")"
  else
    printf '%s\n' "$line"
  fi
}

truncate_text() {
  value=$1
  limit=${2:-600}
  length=$(printf '%s' "$value" | wc -c | tr -d ' ')
  if [ "$length" -gt "$limit" ]; then
    prefix_len=$((limit - 15))
    if [ "$prefix_len" -lt 1 ]; then
      prefix_len=1
    fi
    prefix=$(printf '%s' "$value" | cut -c1-"$prefix_len")
    printf '%s... [truncated]\n' "$prefix"
  else
    printf '%s\n' "$value"
  fi
}

platform_name() {
  uname -s 2>/dev/null | tr '[:upper:]' '[:lower:]'
}

write_md_field() {
  label=$1
  value=$2
  if [ -z "$value" ]; then
    value='(not provided)'
  fi
  case "$value" in
    *'
'*)
      printf '**%s:**\n' "$label"
      printf '%s\n' "$value" | sed 's/^/> /'
      ;;
    *)
      printf '**%s:** %s\n' "$label" "$value"
      ;;
  esac
}

json_escape() {
  # Escape a string for embedding in a JSON value. Uses awk for reliable
  # handling of backslashes, double quotes, and control characters across
  # all POSIX platforms (the previous sed approach failed on single-line
  # input where the N command silently skipped all substitutions).
  # Newline handling: print \n BEFORE each line when NR > 1 (not after via
  # getline, which silently consumed the next line and dropped it).
  printf '%s' "$1" | awk '
    BEGIN { ORS="" }
    {
      if (NR > 1) printf "\\n"
      for (i = 1; i <= length($0); i++) {
        c = substr($0, i, 1)
        if      (c == "\\") printf "\\\\"
        else if (c == "\"") printf "\\\""
        else if (c == "\t") printf "\\t"
        else if (c == "\r") printf "\\r"
        else                printf "%s", c
      }
    }
  ' -
}

json_string() {
  key=$1
  value=$2
  printf '"%s":"%s"' "$key" "$(json_escape "$value")"
}

json_number() {
  key=$1
  value=$2
  printf '"%s":%s' "$key" "$value"
}

json_bool() {
  key=$1
  value=$(normalize_bool "$2")
  printf '"%s":%s' "$key" "$value"
}

# Sparse-output helpers: emit nothing when value is default/empty.
# Each returns a trailing comma when it emits, so the caller can chain them.
json_string_if() {
  key=$1
  value=$2
  if [ -n "$value" ]; then
    printf '%s,' "$(json_string "$key" "$value")"
  fi
}

json_number_if() {
  key=$1
  value=$2
  default=${3:-0}
  if [ "$value" != "$default" ]; then
    printf '%s,' "$(json_number "$key" "$value")"
  fi
}

json_bool_if() {
  key=$1
  value=$(normalize_bool "$2")
  if [ "$value" = "true" ]; then
    printf '%s,' "$(json_bool "$key" "$value")"
  fi
}

# Convert comma-separated tags to JSON array string.
csv_to_json_array() {
  csv=$1
  if [ -z "$csv" ]; then
    printf '[]\n'
    return 0
  fi
  result=
  old_ifs=$IFS
  IFS=,
  for item in $csv; do
    item=$(trim "$item")
    if [ -z "$item" ]; then continue; fi
    if [ -n "$result" ]; then
      result="$result,\"$(json_escape "$item")\""
    else
      result="\"$(json_escape "$item")\""
    fi
  done
  IFS=$old_ifs
  printf '[%s]\n' "$result"
}

base64_encode() {
  value=$1
  if command -v base64 >/dev/null 2>&1; then
    printf '%s' "$value" | base64 | tr -d '\n'
  elif command -v openssl >/dev/null 2>&1; then
    printf '%s' "$value" | openssl base64 -A
  else
    die "base64_encode: no suitable base64 command found (base64, openssl)"
  fi
  printf '\n'
}

base64_decode() {
  value=$1
  if command -v base64 >/dev/null 2>&1; then
    if printf '%s' "$value" | base64 -d >/dev/null 2>&1; then
      printf '%s' "$value" | base64 -d
      return 0
    fi
    if printf '%s' "$value" | base64 --decode >/dev/null 2>&1; then
      printf '%s' "$value" | base64 --decode
      return 0
    fi
    if printf '%s' "$value" | base64 -D >/dev/null 2>&1; then
      printf '%s' "$value" | base64 -D
      return 0
    fi
  fi
  if command -v openssl >/dev/null 2>&1; then
    printf '%s' "$value" | openssl base64 -d -A
    return 0
  fi
  die "base64_decode: no suitable base64 command found (base64, openssl)"
}

sanitize_text() {
  printf '%s' "$1" | sed -E \
    -e 's/(Bearer[[:space:]]+)[A-Za-z0-9._-]+/\1[REDACTED]/g' \
    -e 's/(^|[^[:alnum:]_])(gh[pousr]_[A-Za-z0-9]+)([^[:alnum:]_]|$)/\1[REDACTED_GITHUB_TOKEN]\3/g' \
    -e 's/(^|[^[:alnum:]_])(sk-[A-Za-z0-9_-]+)([^[:alnum:]_]|$)/\1[REDACTED_API_TOKEN]\3/g' \
    -e 's/(^|[^[:alnum:]_])(AKIA[0-9A-Z]{16})([^[:alnum:]_]|$)/\1[REDACTED_AWS_ACCESS_KEY]\3/g' \
    -e 's/(^|[^[:alnum:]_])(xox[baprs]-[A-Za-z0-9-]+)([^[:alnum:]_]|$)/\1[REDACTED_SLACK_TOKEN]\3/g' \
    -e 's/(^|[^[:alnum:]_])([Pp]assword|[Tt]oken|[Ss]ecret|[Aa][Pp][Ii][_-]?[Kk][Ee][Yy])([[:space:]]*[:=][[:space:]]*)[^[:space:]]+/\1\2\3[REDACTED]/g'
}

sanitize_excerpt() {
  sanitized=$(sanitize_text "$1")
  truncate_text "$sanitized" "${2:-600}"
}

normalize_bool() {
  case "$(lower "${1:-false}")" in
    1|true|yes|y|on) printf 'true\n' ;;
    *) printf 'false\n' ;;
  esac
}

safe_int() {
  value=${1:-0}
  case "$value" in
    ''|*[!0-9]*)
      printf '0\n'
      ;;
    *)
      printf '%s\n' "$value"
      ;;
  esac
}

# Normalization functions: the canonical definitions live in the schema
# x-scales block. These case statements are a performance cache — they
# MUST match x-scales. The smoke tests validate consistency.
normalize_run_effect() {
  case "$1" in
    blocked|degraded|noisy|continued) printf '%s\n' "$1" ;;
    confusing) printf 'continued\n' ;;
    misleading) printf 'degraded\n' ;;
    '') printf '\n' ;;
    *) die "Unsupported run effect: $1" ;;
  esac
}

normalize_guidance_quality() {
  case "$1" in
    0|1|2|3|4) printf '%s\n' "$1" ;;
    clear) printf '4\n' ;;
    partial) printf '3\n' ;;
    ambiguous) printf '2\n' ;;
    misleading) printf '1\n' ;;
    not-applicable) printf '0\n' ;;
    confusing) printf '2\n' ;;
    '') printf '\n' ;;
    *) die "Unsupported guidance quality: $1 (expected 0-4 or clear/partial/ambiguous/misleading/not-applicable)" ;;
  esac
}

normalize_confidence() {
  case "$1" in
    1|2|3|4|5) printf '%s\n' "$1" ;;
    low) printf '2\n' ;;
    moderate|medium) printf '3\n' ;;
    high) printf '4\n' ;;
    '') printf '\n' ;;
    *) die "Unsupported confidence: $1 (expected 1-5 or low/moderate/high)" ;;
  esac
}

validate_narrative_length() {
  label=$1
  value=$2
  min_len=$3
  length=$(printf '%s' "$value" | wc -c | tr -d ' ')
  if [ "$length" -lt "$min_len" ]; then
    die "$label must be at least $min_len characters (got $length). Provide a detailed, substantive account."
  fi
}

# Allowed source types for the sources array.
VALID_SOURCE_TYPES=$(load_schema | jq -r '.properties.sources.items.properties.type.enum // [] | join(" ")' 2>/dev/null)
if [ -z "$VALID_SOURCE_TYPES" ]; then
  VALID_SOURCE_TYPES="file url system-instruction conversation audio visual documentation other"
fi

validate_source_type() {
  stype=$1
  for valid in $VALID_SOURCE_TYPES; do
    if [ "$stype" = "$valid" ]; then
      return 0
    fi
  done
  die "Unsupported source type: $stype (expected one of: $VALID_SOURCE_TYPES)"
}

normalize_fingerprint_text() {
  value=$(first_line "$1")
  value=$(lower "$value")
  printf '%s' "$value" | sed 's/[^a-z0-9][^a-z0-9]*/ /g; s/^[[:space:]]*//; s/[[:space:]]*$//; s/[[:space:]][[:space:]]*/ /g'
}

build_event_fingerprint() {
  root_surface=$1
  mode=$2
  source_ref=$3
  event_date=$4
  custom_key=${5:-}

  if [ -n "$custom_key" ]; then
    seed=$(normalize_fingerprint_text "$custom_key")
  else
    source_key=$(normalize_fingerprint_text "$source_ref")
    seed="${root_surface}|${mode}|${source_key}|${event_date}"
  fi
  short_hash "$seed" 12
}

# Extract all unique tags from an events.jsonl file as comma-separated list.
extract_all_tags() {
  events_path=$1
  if [ ! -f "$events_path" ]; then
    printf '\n'
    return 0
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    printf '\n'
    return 0
  fi
  python3 - "$events_path" <<'PY'
import json, sys
from pathlib import Path
tags = set()
with Path(sys.argv[1]).open("r", encoding="utf-8") as fh:
    for raw in fh:
        raw = raw.strip()
        if not raw:
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        t = event.get("tags")
        if isinstance(t, list):
            for tag in t:
                if tag:
                    tags.add(str(tag))
print(", ".join(sorted(tags)))
PY
}

extract_json_string() {
  line=$1
  key=$2
  # Handles escaped quotes inside values (e.g. \"hello\").
  printf '%s\n' "$line" | awk -v k="$key" '
    {
      start = "\"" k "\":\""
      idx = index($0, start)
      if (idx == 0) { print ""; next }
      rest = substr($0, idx + length(start))
      val = ""
      while (length(rest) > 0) {
        ch = substr(rest, 1, 1)
        if (ch == "\\") { val = val substr(rest, 1, 2); rest = substr(rest, 3) }
        else if (ch == "\"") { break }
        else { val = val ch; rest = substr(rest, 2) }
      }
      print val
    }'
}

extract_json_number() {
  line=$1
  key=$2
  value=$(printf '%s\n' "$line" | sed -n "s/.*\"$key\":\\([0-9][0-9]*\\).*/\\1/p")
  if [ -z "$value" ]; then
    printf '0\n'
  else
    printf '%s\n' "$value"
  fi
}

extract_json_bool() {
  line=$1
  key=$2
  value=$(printf '%s\n' "$line" | sed -n "s/.*\"$key\":\\(true\\|false\\).*/\\1/p")
  if [ -z "$value" ]; then
    printf 'false\n'
  else
    printf '%s\n' "$value"
  fi
}

read_session_value() {
  session_file=$1
  key=$2
  if [ ! -f "$session_file" ]; then
    printf '\n'
    return 0
  fi
  sed -n "s/^${key}=//p" "$session_file" | sed -n '1p'
}

git_repo_root() {
  if command -v git >/dev/null 2>&1; then
    git rev-parse --show-toplevel 2>/dev/null || true
  else
    printf '\n'
  fi
}

git_superproject_root() {
  if command -v git >/dev/null 2>&1; then
    git rev-parse --show-superproject-working-tree 2>/dev/null || true
  else
    printf '\n'
  fi
}

git_submodule_path() {
  superproject=$1
  repo_root=$2
  if [ -n "$superproject" ] && [ -n "$repo_root" ]; then
    # Relative path of submodule within the superproject
    printf '%s' "$repo_root" | sed "s|^$superproject/||"
  fi
}

extract_primary_source_ref() {
  printf '%s\n' "$1" | sed -n 's/.*"ref"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | sed -n '1p'
}

local_dir_for_repo() {
  repo_root=$1
  default_dir=$repo_root/.local
  if [ -d "$default_dir" ]; then
    printf '%s\n' "$default_dir"
    return 0
  fi

  existing=$(
    find "$repo_root" -maxdepth 1 -mindepth 1 -type d -name '.local*' 2>/dev/null |
      LC_ALL=C sort |
      sed -n '1p'
  )
  if [ -n "$existing" ]; then
    printf '%s\n' "$existing"
    return 0
  fi

  mkdir -p "$default_dir"
  printf '%s\n' "$default_dir"
}

temp_root_dir() {
  if command -v python3 >/dev/null 2>&1; then
    python3 - <<'PY'
import tempfile
print(tempfile.gettempdir())
PY
  elif [ -n "${TMPDIR-}" ]; then
    printf '%s\n' "$TMPDIR"
  elif [ -n "${TEMP-}" ]; then
    printf '%s\n' "$TEMP"
  elif [ -n "${TMP-}" ]; then
    printf '%s\n' "$TMP"
  else
    die "Unable to determine system temp path."
  fi
}

default_events_file() {
  repo_root=$(git_repo_root)
  if [ -n "$repo_root" ]; then
    local_dir=$(local_dir_for_repo "$repo_root")
    printf '%s\n' "$local_dir/reports/friction/events.jsonl"
    return 0
  fi

  cwd_hash=$(short_hash "$(pwd)" 12)
  printf '%s\n' "$(temp_root_dir)/agent-friction/$cwd_hash/events.jsonl"
}

discover_events_files() {
  if [ "$#" -eq 0 ]; then
    die "discover_events_files: at least one directory is required"
  fi
  find "$@" -path '*/.local*/reports/friction/events.jsonl' -type f 2>/dev/null | LC_ALL=C sort
}

validate_events_jsonl_file() {
  events_path=$1
  [ -f "$events_path" ] || return 0
  jq -Rn '
    def is_blank:
      test("^[[:space:]]*$");
    reduce inputs as $line
      ({line: 0};
        .line += 1
        | if ($line | is_blank) then
            .
          else
            .line as $line_number
            | try ($line | fromjson | .)
              catch error("Invalid JSON in events file at line \($line_number): " + .)
            | {line: $line_number}
          end
      )
  ' "$events_path" >/dev/null
}

default_owner_for_surface() {
  case "$1" in
    skill) printf 'skill-owner\n' ;;
    instructions) printf 'prompt-owner\n' ;;
    mcp) printf 'mcp-owner\n' ;;
    tool|script) printf 'tooling-owner\n' ;;
    code|logic) printf 'implementation-owner\n' ;;
    data) printf 'schema-owner\n' ;;
    environment) printf 'environment-owner\n' ;;
    external-service) printf 'service-owner\n' ;;
    workflow) printf 'workflow-owner\n' ;;
    *) printf 'triage-owner\n' ;;
  esac
}

priority_score() {
  recurrence=$(safe_int "$1")
  run_effect=$2
  guidance_quality=$(safe_int "$3")
  minutes_lost=$(safe_int "$4")
  retries_lost=$(safe_int "$5")
  workaround_used=$(normalize_bool "$6")

  score=$((recurrence * 2 + minutes_lost + retries_lost))
  case "$run_effect" in
    blocked) score=$((score + 6)) ;;
    degraded) score=$((score + 3)) ;;
    noisy) score=$((score + 2)) ;;
    continued) score=$((score + 1)) ;;
  esac
  # guidance_quality 0-4: lower quality = more priority points
  # 0=N/A(+0), 1=misleading(+3), 2=ambiguous(+2), 3=partial(+1), 4=clear(+0)
  if [ "$guidance_quality" -gt 0 ] && [ "$guidance_quality" -lt 4 ]; then
    score=$((score + 4 - guidance_quality))
  fi
  if [ "$workaround_used" = "true" ]; then
    score=$((score + 1))
  fi
  printf '%s\n' "$score"
}

priority_band() {
  score=$(safe_int "$1")
  if [ "$score" -ge 16 ]; then
    printf 'high\n'
  elif [ "$score" -ge 8 ]; then
    printf 'medium\n'
  else
    printf 'low\n'
  fi
}
