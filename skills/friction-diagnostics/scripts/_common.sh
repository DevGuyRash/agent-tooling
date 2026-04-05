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
schema_fields_where() {
  filter=$1
  load_schema | jq -r --arg f "$filter" \
    '[.properties | to_entries[] | select(.value | '"$filter"') | .key] | .[]'
}

schema_md_render_order() {
  load_schema | jq -r '.["x-render-md-order"][]'
}

schema_aggregate_order() {
  load_schema | jq -r '.["x-aggregate-order"][]'
}

schema_all_fields() {
  load_schema | jq -r '.properties | keys[]'
}

schema_field_prop() {
  field=$1
  prop=$2
  load_schema | jq -r --arg f "$field" --arg p "$prop" '.properties[$f][$p] // empty'
}

schema_searchable_fields_jq() {
  load_schema | jq -c '[.properties | to_entries[] | select(.value["x-searchable"] == true) | .key]'
}

# --- Core utilities ---

die() {
  printf '%s\n' "$*" >&2
  exit 1
}

lower() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]'
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

normalize_bool() {
  case "$(lower "${1:-false}")" in
    1|true|yes|y|on) printf 'true\n' ;;
    *) printf 'false\n' ;;
  esac
}

platform_name() {
  uname -s 2>/dev/null | tr '[:upper:]' '[:lower:]'
}

# --- Hashing ---

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

# --- JSON building ---

json_escape() {
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
    item=$(lower "$item")
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

shell_quote() {
  printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"
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

# --- Sanitization ---

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

# --- Impact normalization ---

normalize_impact() {
  case "$1" in
    blocked|degraded|noisy|continued) printf '%s\n' "$1" ;;
    '') printf '\n' ;;
    *) die "Unsupported impact value: $1 (expected: blocked, degraded, noisy, continued)" ;;
  esac
}

# --- Narrative validation ---

validate_required_field() {
  label=$1
  value=$2
  if [ -z "$(trim "$value")" ]; then
    die "Missing required field: $label"
  fi
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

# --- Source validation ---

VALID_SOURCE_TYPES=$(load_schema | jq -r '.properties.sources.items.properties.type.enum // [] | join(" ")' 2>/dev/null)
if [ -z "$VALID_SOURCE_TYPES" ]; then
  VALID_SOURCE_TYPES="file url conversation audio visual documentation other"
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

# --- Fingerprint ---

build_event_fingerprint() {
  source_ref=$1
  event_date=$2
  custom_key=${3:-}

  if [ -n "$custom_key" ]; then
    seed=$(lower "$custom_key")
    seed=$(printf '%s' "$seed" | sed 's/[^a-z0-9][^a-z0-9]*/ /g; s/^[[:space:]]*//; s/[[:space:]]*$//; s/[[:space:]][[:space:]]*/ /g')
  else
    source_key=$(lower "$source_ref")
    source_key=$(printf '%s' "$source_key" | sed 's/[^a-z0-9][^a-z0-9]*/ /g; s/^[[:space:]]*//; s/[[:space:]]*$//; s/[[:space:]][[:space:]]*/ /g')
    seed="${source_key}|${event_date}"
  fi
  short_hash "$seed" 12
}

extract_primary_source_ref() {
  printf '%s\n' "$1" | sed -n 's/.*"ref"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | sed -n '1p'
}

# --- JSONL extraction ---

extract_json_string() {
  line=$1
  key=$2
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

# --- Tag and alias extraction ---

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
                    tags.add(str(tag).lower())
print(", ".join(sorted(tags)))
PY
}

extract_all_aliases() {
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
aliases = set()
with Path(sys.argv[1]).open("r", encoding="utf-8") as fh:
    for raw in fh:
        raw = raw.strip()
        if not raw:
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        a = event.get("aliases")
        if isinstance(a, list):
            for alias in a:
                if alias:
                    aliases.add(str(alias).lower())
print(", ".join(sorted(aliases)))
PY
}

# --- Git and path resolution ---

git_repo_root() {
  if command -v git >/dev/null 2>&1; then
    git rev-parse --show-toplevel 2>/dev/null || true
  else
    printf '\n'
  fi
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

existing_local_dir_for_repo() {
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

friction_scratch_dir_for_repo() {
  repo_root=$1
  if [ -z "$repo_root" ]; then
    printf '\n'
    return 0
  fi

  local_dir=$(existing_local_dir_for_repo "$repo_root")
  printf '%s\n' "$local_dir/tmp/friction-diagnostics"
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

# --- Base64 ---

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

# --- Misc ---

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
