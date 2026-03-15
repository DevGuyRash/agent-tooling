#!/bin/sh

die() {
  printf '%s\n' "$*" >&2
  exit 1
}

lower() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]'
}

short_hash() {
  input=$1
  if command -v sha256sum >/dev/null 2>&1; then
    printf '%s' "$input" | sha256sum | awk '{print substr($1, 1, 8)}'
  elif command -v shasum >/dev/null 2>&1; then
    printf '%s' "$input" | shasum -a 256 | awk '{print substr($1, 1, 8)}'
  elif command -v openssl >/dev/null 2>&1; then
    printf '%s' "$input" | openssl dgst -sha256 | sed 's/^.*= //' | cut -c1-8
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

build_category_tags() {
  surface=$1
  mode=$2
  impact=$3
  text=$4

  tags=
  tags=$(append_csv "$tags" "$surface")
  tags=$(append_csv "$tags" "$mode")
  tags=$(append_csv "$tags" "$impact")

  case "$text" in *"dispatch"*) tags=$(append_csv "$tags" "dispatch") ;; esac
  case "$text" in *"role"*) tags=$(append_csv "$tags" "role") ;; esac
  case "$text" in *"slug"*) tags=$(append_csv "$tags" "slug") ;; esac
  case "$text" in *"agents.md"*) tags=$(append_csv "$tags" "agents-md") ;; esac
  case "$text" in *"skill.md"*) tags=$(append_csv "$tags" "skill-md") ;; esac
  case "$text" in *"mcp"*) tags=$(append_csv "$tags" "mcp") ;; esac
  case "$text" in *"server"*) tags=$(append_csv "$tags" "server") ;; esac
  case "$text" in *"cli"*|*"command "*) tags=$(append_csv "$tags" "cli") ;; esac
  case "$text" in *".ps1"*|*"powershell"*) tags=$(append_csv "$tags" "powershell") ;; esac
  case "$text" in *".sh"*|*"posix"*) tags=$(append_csv "$tags" "posix-sh") ;; esac
  case "$text" in *"json"*) tags=$(append_csv "$tags" "json") ;; esac
  case "$text" in *"yaml"*) tags=$(append_csv "$tags" "yaml") ;; esac
  case "$text" in *"schema"*) tags=$(append_csv "$tags" "schema") ;; esac
  case "$text" in *"token"*|*"credential"*) tags=$(append_csv "$tags" "token") ;; esac
  case "$text" in *"permission"*) tags=$(append_csv "$tags" "permission") ;; esac
  case "$text" in *"timeout"*) tags=$(append_csv "$tags" "timeout") ;; esac
  case "$text" in *"traceback"*|*"stacktrace"*|*"stack backtrace"*) tags=$(append_csv "$tags" "stacktrace") ;; esac
  case "$text" in *"sandbox"*) tags=$(append_csv "$tags" "sandbox") ;; esac
  case "$text" in *"filesystem"*) tags=$(append_csv "$tags" "filesystem") ;; esac
  case "$text" in *"path"*) tags=$(append_csv "$tags" "path") ;; esac
  case "$text" in *"dependency"*) tags=$(append_csv "$tags" "dependency") ;; esac
  case "$text" in *"api"*|*"endpoint"*) tags=$(append_csv "$tags" "api") ;; esac
  case "$text" in *"rate limit"*) tags=$(append_csv "$tags" "rate-limit") ;; esac
  case "$text" in *"context"*) tags=$(append_csv "$tags" "context") ;; esac
  case "$text" in *"handoff"*) tags=$(append_csv "$tags" "handoff") ;; esac
  case "$text" in *"validation"*|*"required"*) tags=$(append_csv "$tags" "validation") ;; esac
  case "$text" in *"output"*) tags=$(append_csv "$tags" "output") ;; esac

  printf '%s\n' "$tags"
}
