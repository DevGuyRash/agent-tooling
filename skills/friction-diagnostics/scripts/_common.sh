#!/bin/sh

SCHEMA_VERSION=3.0.0
TAXONOMY_VERSION=2.0.0

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
    -e 's/\bgh[pousr]_[A-Za-z0-9]+\b/[REDACTED_GITHUB_TOKEN]/g' \
    -e 's/\bsk-[A-Za-z0-9_-]+\b/[REDACTED_API_TOKEN]/g' \
    -e 's/\bAKIA[0-9A-Z]{16}\b/[REDACTED_AWS_ACCESS_KEY]/g' \
    -e 's/\bxox[baprs]-[A-Za-z0-9-]+\b/[REDACTED_SLACK_TOKEN]/g' \
    -e 's/\b([Pp]assword|[Tt]oken|[Ss]ecret|[Aa][Pp][Ii][_-]?[Kk][Ee][Yy])([[:space:]]*[:=][[:space:]]*)[^[:space:]]+/\1\2[REDACTED]/g'
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
    ambiguous) printf '2\n' ;;
    misleading) printf '1\n' ;;
    not-applicable) printf '0\n' ;;
    confusing) printf '2\n' ;;
    '') printf '\n' ;;
    *) die "Unsupported guidance quality: $1 (expected 0-4 or clear/ambiguous/misleading/not-applicable)" ;;
  esac
}

normalize_confidence() {
  case "$1" in
    1|2|3|4|5) printf '%s\n' "$1" ;;
    low) printf '2\n' ;;
    medium) printf '3\n' ;;
    high) printf '4\n' ;;
    '') printf '\n' ;;
    *) die "Unsupported confidence: $1 (expected 1-5 or low/medium/high)" ;;
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
VALID_SOURCE_TYPES="file url system-instruction conversation audio visual documentation other"

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
  actual_outcome=$4
  action_taken=$5
  title=$6
  custom_key=${7:-}

  if [ -n "$custom_key" ]; then
    seed=$(normalize_fingerprint_text "$custom_key")
  else
    source_key=$(normalize_fingerprint_text "$source_ref")
    outcome_key=$(normalize_fingerprint_text "$actual_outcome")
    action_key=$(normalize_fingerprint_text "$action_taken")
    title_key=$(normalize_fingerprint_text "$title")
    seed="${root_surface}|${mode}|${source_key}|${outcome_key}|${action_key}|${title_key}"
  fi
  short_hash "$seed" 12
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

build_category_tags() {
  surface=$1
  mode=$2
  run_effect=$3
  guidance_quality=$4
  text=$5
  source_type_csv=${6:-}

  tags=
  # Tier 1: structural tags (always present)
  tags=$(append_csv "$tags" "$surface")
  tags=$(append_csv "$tags" "$mode")
  tags=$(append_csv "$tags" "$run_effect")

  # Tier 2: source-type-derived tags
  old_ifs=$IFS
  IFS=,
  for st in $source_type_csv; do
    st=$(trim "$st")
    case "$st" in
      file) tags=$(append_csv "$tags" "file-source") ;;
      url) tags=$(append_csv "$tags" "web-source") ;;
      system-instruction) tags=$(append_csv "$tags" "system-instruction") ;;
      conversation) tags=$(append_csv "$tags" "conversation-source") ;;
      audio) tags=$(append_csv "$tags" "audio-source") ;;
      visual) tags=$(append_csv "$tags" "visual-source") ;;
      documentation) tags=$(append_csv "$tags" "doc-source") ;;
    esac
  done
  IFS=$old_ifs

  # Tier 3: content-detected keyword tags (expanded vocabulary)
  # -- Reference document markers --
  case "$text" in *"dispatch"*) tags=$(append_csv "$tags" "dispatch") ;; esac
  case "$text" in *"role"*) tags=$(append_csv "$tags" "role") ;; esac
  case "$text" in *"slug"*) tags=$(append_csv "$tags" "slug") ;; esac
  case "$text" in *"agents.md"*) tags=$(append_csv "$tags" "agents-md") ;; esac
  case "$text" in *"skill.md"*) tags=$(append_csv "$tags" "skill-md") ;; esac
  case "$text" in *"mcp"*) tags=$(append_csv "$tags" "mcp") ;; esac
  case "$text" in *"server"*) tags=$(append_csv "$tags" "server") ;; esac
  # -- Tool and shell markers --
  case "$text" in *"cli"*|*"command "*) tags=$(append_csv "$tags" "cli") ;; esac
  case "$text" in *".ps1"*|*"powershell"*) tags=$(append_csv "$tags" "powershell") ;; esac
  case "$text" in *".sh"*|*"posix"*) tags=$(append_csv "$tags" "posix-sh") ;; esac
  # -- Data format markers --
  case "$text" in *"json"*) tags=$(append_csv "$tags" "json") ;; esac
  case "$text" in *"yaml"*|*"yml"*) tags=$(append_csv "$tags" "yaml") ;; esac
  case "$text" in *"toml"*) tags=$(append_csv "$tags" "toml") ;; esac
  case "$text" in *"schema"*) tags=$(append_csv "$tags" "schema") ;; esac
  # -- Security and auth markers --
  case "$text" in *"token"*|*"credential"*) tags=$(append_csv "$tags" "token") ;; esac
  case "$text" in *"permission"*) tags=$(append_csv "$tags" "permission") ;; esac
  case "$text" in *"sign"*|*"gpg"*|*"ssh-key"*) tags=$(append_csv "$tags" "signing") ;; esac
  # -- Failure mode markers --
  case "$text" in *"timeout"*) tags=$(append_csv "$tags" "timeout") ;; esac
  case "$text" in *"traceback"*|*"stacktrace"*|*"stack backtrace"*) tags=$(append_csv "$tags" "stacktrace") ;; esac
  case "$text" in *"sandbox"*) tags=$(append_csv "$tags" "sandbox") ;; esac
  case "$text" in *"filesystem"*) tags=$(append_csv "$tags" "filesystem") ;; esac
  case "$text" in *"path"*) tags=$(append_csv "$tags" "path") ;; esac
  case "$text" in *"dependency"*) tags=$(append_csv "$tags" "dependency") ;; esac
  case "$text" in *"api"*|*"endpoint"*) tags=$(append_csv "$tags" "api") ;; esac
  case "$text" in *"rate limit"*|*"quota"*) tags=$(append_csv "$tags" "rate-limit") ;; esac
  case "$text" in *"context"*) tags=$(append_csv "$tags" "context") ;; esac
  case "$text" in *"handoff"*) tags=$(append_csv "$tags" "handoff") ;; esac
  case "$text" in *"validation"*|*"required"*) tags=$(append_csv "$tags" "validation") ;; esac
  case "$text" in *"output"*) tags=$(append_csv "$tags" "output") ;; esac
  case "$text" in *"workaround"*) tags=$(append_csv "$tags" "workaround") ;; esac
  # -- Language and ecosystem markers --
  case "$text" in *"cargo"*|*"rustc"*|*"crate"*) tags=$(append_csv "$tags" "rust") ;; esac
  case "$text" in *"python"*|*"pip "*|*"pytest"*) tags=$(append_csv "$tags" "python") ;; esac
  case "$text" in *"node"*|*"npm"*|*"yarn"*|*"pnpm"*) tags=$(append_csv "$tags" "node") ;; esac
  case "$text" in *"docker"*|*"dockerfile"*|*"podman"*) tags=$(append_csv "$tags" "docker") ;; esac
  case "$text" in *"git "*|*"commit"*|*"branch"*|*"merge"*) tags=$(append_csv "$tags" "git") ;; esac
  # -- CI/CD and workflow markers --
  # Use space-padded text for short words prone to substring false positives
  _t=" $text "
  case "$_t" in *" ci "*|*"/ci/"*|*"-ci-"*|*" ci:"*|*"github actions"*|*"github-actions"*|*"circleci"*|*"travis"*|*"pipeline"*|*"github workflow"*) tags=$(append_csv "$tags" "ci") ;; esac
  case "$_t" in *" test "*|*" tests "*|*" testing "*|*"pytest"*|*"cargo test"*|*"npm test"*|*" assert"*) tags=$(append_csv "$tags" "test") ;; esac
  case "$text" in *"build"*|*"compile"*) tags=$(append_csv "$tags" "build") ;; esac
  case "$_t" in *" link "*|*"linker"*|*"linking"*) tags=$(append_csv "$tags" "link") ;; esac
  case "$text" in *"lint"*|*"clippy"*|*"eslint"*|*"rustfmt"*|*"prettier"*) tags=$(append_csv "$tags" "lint") ;; esac
  case "$text" in *"deploy"*|*"release"*|*"publish"*) tags=$(append_csv "$tags" "deploy") ;; esac
  # -- Infrastructure markers --
  case "$text" in *"config"*) tags=$(append_csv "$tags" "config") ;; esac
  case "$text" in *"migration"*|*"migrate"*|*"upgrade"*) tags=$(append_csv "$tags" "migration") ;; esac
  case "$text" in *"hook"*|*"pre-commit"*|*"post-commit"*) tags=$(append_csv "$tags" "hook") ;; esac
  case "$text" in *"systemd"*|*"systemctl"*|*"journalctl"*|*"service unit"*|*"unit file"*) tags=$(append_csv "$tags" "systemd") ;; esac

  printf '%s\n' "$tags"
}
