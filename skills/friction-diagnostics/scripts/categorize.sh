#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
. "$SCRIPT_DIR/_common.sh"

print_help() {
  cat <<'EOF'
Usage:
  sh scripts/categorize.sh [options]

Options:
  --instruction-source TEXT
  --instruction-text TEXT
  --action-taken TEXT
  --actual-outcome TEXT
  --interpretation TEXT
  --expected-outcome TEXT
  --surface VALUE
  --mode VALUE
  --impact VALUE
  --help

Output:
  surface=<value>
  mode=<value>
  impact=<value>
  tags=<comma-separated tags>
EOF
}

instruction_source=
instruction_text=
action_taken=
actual_outcome=
interpretation=
expected_outcome=
surface_override=
mode_override=
impact_override=

while [ $# -gt 0 ]; do
  case "$1" in
    --instruction-source) instruction_source=${2-}; shift 2 ;;
    --instruction-text) instruction_text=${2-}; shift 2 ;;
    --action-taken) action_taken=${2-}; shift 2 ;;
    --actual-outcome) actual_outcome=${2-}; shift 2 ;;
    --interpretation) interpretation=${2-}; shift 2 ;;
    --expected-outcome) expected_outcome=${2-}; shift 2 ;;
    --surface) surface_override=${2-}; shift 2 ;;
    --mode) mode_override=${2-}; shift 2 ;;
    --impact) impact_override=${2-}; shift 2 ;;
    --help|-h) print_help; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
done

text=$(
  printf '%s\n%s\n%s\n%s\n%s\n%s\n' \
    "$instruction_source" \
    "$instruction_text" \
    "$action_taken" \
    "$expected_outcome" \
    "$actual_outcome" \
    "$interpretation"
)
text=$(lower "$text")

surface=unknown
case "$text" in
  *"skill.md"*|*".agents/skills"*|*" skill "*|*"skill path"*) surface=skill ;;
  *"agents.md"*|*"instruction"*|*"prompt"*|*"dispatch"*) surface=instructions ;;
  *"mcp"*|*"model context protocol"*) surface=mcp ;;
  *".ps1"*|*".sh"*|*"script "*|*"scripts/"*) surface=script ;;
  *"http"*|*"api "*|*"endpoint"*|*"server returned"*|*"rate limit"*|*"webhook"*) surface=external-service ;;
  *"sandbox"*|*"dependency"*|*"filesystem"*|*"permission"*|*"path"*|*"cwd"*|*"env "*|*"environment"*) surface=environment ;;
  *"json"*|*"yaml"*|*"schema"*|*"field"*|*"csv"*|*"deserialize"*|*"serialize"*|*"payload"*|*"contract"*) surface=data ;;
  *"subagent"*|*"handoff"*|*"routing"*|*"delegat"*|*"context window"*|*"compaction"*|*"lost context"*|*"workflow"*) surface=workflow ;;
  *"algorithm"*|*"reasoning"*|*"logic"*|*"assumption"*|*"misread"*|*"interpreted"*|*"interpretation"*) surface=logic ;;
  *"traceback"*|*"stacktrace"*|*"exception"*|*"module"*|*"compile"*|*"test "*|*"runtime"*|*"code "*|*"function"*) surface=code ;;
  *"cli"*|*"command "*|*"executable"*|*"subcommand"*|*"flag "*|*"option "*) surface=tool ;;
esac

mode=other
case "$text" in
  *"rate limit"*|*"quota"*|*"too many requests"*|*"x-ratelimit-"*|*"retry-after"*) mode=other ;;
  *"ambiguous"*|*"unclear"*|*"underspecified"*|*"vague"*|*"not sure"*|*"uncertain"*) mode=ambiguity ;;
  *"contradict"*|*"inconsistent"*|*"does not match docs"*|*"did not match docs"*|*"differs from docs"*) mode=contradiction ;;
  *"unknown dispatch role"*|*"unknown "*|*"unrecognized"*|*"invalid choice"*|*"could not resolve"*|*"cannot resolve"*|*"no command named"*|*"no such subcommand"*) mode=name-resolution ;;
  *"lost context"*|*"missing context"*|*"lacked context"*|*"forgot"*|*"compaction"*) mode=context-loss ;;
  *"not found"*|*"no such file"*|*"missing"*|*"does not exist"*|*"absent"*) mode=missing ;;
  *"permission denied"*|*"operation not permitted"*) mode=permission ;;
  *"unauthorized"*|*"forbidden"*|*"401"*|*"403"*|*"token"*|*"credential"*|*"authentication"*) mode=auth ;;
  *"timed out"*|*"timeout"*|*"deadline exceeded"*) mode=timeout ;;
  *"traceback"*|*"stacktrace"*|*"stack backtrace"*|*"panic"*|*"segmentation fault"*|*"crash"*|*"exception"*) mode=crash ;;
  *"json"*|*"yaml"*|*"schema"*|*"parse error"*|*"type mismatch"*|*"deserialize"*|*"serialize"*|*"shape mismatch"*) mode=schema ;;
  *"validation"*|*"invalid"*|*"required"*|*"assertion failed"*|*"failed validation"*) mode=validation ;;
  *"wrong output"*|*"unexpected output"*|*"output mismatch"*|*"did not match"*|*"rendered incorrectly"*|*"misleading output"*) mode=output-mismatch ;;
  *"flaky"*|*"sometimes"*|*"intermittent"*|*"nondetermin"*|*"non-determin"*) mode=nondeterminism ;;
  *"slow"*|*"performance"*|*"hang"*|*"thrash"*|*"looped"*|*"repeated retries"*) mode=performance ;;
esac

impact=degraded
case "$text" in
  *"rate limit"*|*"quota"*|*"too many requests"*|*"x-ratelimit-"*|*"retry-after"*|*"429"*|*"http 403"*)
    impact=blocked
    ;;
  *"ambiguous"*|*"unclear"*|*"underspecified"*|*"uncertain"*|*"missing context"*|*"lacked context"*|*"lost context"*)
    impact=confusing
    ;;
  *"unknown dispatch role"*|*"timed out"*|*"timeout"*|*"not found"*|*"missing"*|*"permission denied"*|*"unauthorized"*|*"forbidden"*|*"traceback"*|*"stacktrace"*|*"panic"*|*"crash"*|*"error:"*|*"failed"*|*"cannot "*|*"could not "*|*"unable to "*|*"blocked"*)
    impact=blocked
    ;;
  *"contradict"*|*"inconsistent"*|*"wrong output"*|*"unexpected output"*|*"output mismatch"*|*"misleading"*|*"did not match docs"*)
    impact=misleading
    ;;
  *"retry"*|*"retries"*|*"thrash"*|*"looped"*|*"repeated"*|*"extra steps"*)
    impact=noisy
    ;;
  *"partial"*|*"workaround"*|*"degraded"*|*"succeeded but"*|*"continued"*)
    impact=degraded
    ;;
esac

[ -n "$surface_override" ] && surface=$surface_override
[ -n "$mode_override" ] && mode=$mode_override
[ -n "$impact_override" ] && impact=$impact_override

tags=$(build_category_tags "$surface" "$mode" "$impact" "$text")

printf 'surface=%s\n' "$surface"
printf 'mode=%s\n' "$mode"
printf 'impact=%s\n' "$impact"
printf 'tags=%s\n' "$tags"
