#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname "$0")" && pwd)
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
  --expected-outcome TEXT
  --actual-outcome TEXT
  --interpretation TEXT
  --tool-name TEXT
  --command TEXT
  --stderr TEXT
  --stdout-excerpt TEXT
  --observed-surface VALUE
  --surface VALUE
  --mode VALUE
  --run-effect VALUE
  --guidance-quality VALUE
  --impact VALUE
  --evidence-type VALUE
  --confidence VALUE
  --help

Output:
  observed_surface=<value>
  surface=<value>
  mode=<value>
  run_effect=<value>
  guidance_quality=<value>
  confidence=<value>
  evidence_type=<value>
  derived_category=<surface/mode/run_effect>
  tags=<comma-separated tags>
EOF
}

instruction_source=
instruction_text=
action_taken=
expected_outcome=
actual_outcome=
interpretation=
tool_name=
command_text=
stderr_text=
stdout_excerpt=
observed_surface_override=
surface_override=
mode_override=
run_effect_override=
guidance_quality_override=
impact_override=
evidence_type_override=
confidence_override=

while [ $# -gt 0 ]; do
  case "$1" in
    --instruction-source) instruction_source=${2-}; shift 2 ;;
    --instruction-text) instruction_text=${2-}; shift 2 ;;
    --action-taken) action_taken=${2-}; shift 2 ;;
    --expected-outcome) expected_outcome=${2-}; shift 2 ;;
    --actual-outcome) actual_outcome=${2-}; shift 2 ;;
    --interpretation) interpretation=${2-}; shift 2 ;;
    --tool-name) tool_name=${2-}; shift 2 ;;
    --command) command_text=${2-}; shift 2 ;;
    --stderr) stderr_text=${2-}; shift 2 ;;
    --stdout-excerpt) stdout_excerpt=${2-}; shift 2 ;;
    --observed-surface) observed_surface_override=${2-}; shift 2 ;;
    --surface) surface_override=${2-}; shift 2 ;;
    --mode) mode_override=${2-}; shift 2 ;;
    --run-effect) run_effect_override=${2-}; shift 2 ;;
    --guidance-quality) guidance_quality_override=${2-}; shift 2 ;;
    --impact) impact_override=${2-}; shift 2 ;;
    --evidence-type) evidence_type_override=${2-}; shift 2 ;;
    --confidence) confidence_override=${2-}; shift 2 ;;
    --help|-h) print_help; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
done

observation_text=$(
  printf '%s\n%s\n%s\n%s\n%s\n' \
    "$action_taken" \
    "$actual_outcome" \
    "$tool_name" \
    "$command_text" \
    "$stderr_text"
)
observation_text=$(lower "$observation_text")

source_text=$(
  printf '%s\n%s\n%s\n%s\n%s\n' \
    "$instruction_source" \
    "$instruction_text" \
    "$expected_outcome" \
    "$interpretation" \
    "$stdout_excerpt"
)
source_text=$(lower "$source_text")

full_text=$(
  printf '%s\n%s\n' "$observation_text" "$source_text"
)

detect_surface() {
  text=$1
  case "$text" in
    *"skill.md"*|*".agents/skills"*|*" skill "*|*"skill path"*)
      printf 'skill\n'
      ;;
    *"agents.md"*|*"instruction"*|*"prompt"*|*"dispatch"*|*"runbook"*)
      printf 'instructions\n'
      ;;
    *"mcp"*|*"model context protocol"*)
      printf 'mcp\n'
      ;;
    *".ps1"*|*".sh"*|*"script "*|*"scripts/"*)
      printf 'script\n'
      ;;
    *"http"*|*"api "*|*"endpoint"*|*"server returned"*|*"rate limit"*|*"retry-after"*|*"webhook"*)
      printf 'external-service\n'
      ;;
    *"sandbox"*|*"dependency"*|*"filesystem"*|*"permission"*|*"cwd"*|*"env "*|*"environment"*)
      printf 'environment\n'
      ;;
    *"json"*|*"yaml"*|*"schema"*|*"field"*|*"csv"*|*"deserialize"*|*"serialize"*|*"payload"*|*"contract"*)
      printf 'data\n'
      ;;
    *"subagent"*|*"handoff"*|*"delegat"*|*"context window"*|*"compaction"*|*"lost context"*|*"workflow"*)
      printf 'workflow\n'
      ;;
    *"algorithm"*|*"reasoning"*|*"logic"*|*"assumption"*|*"misread"*|*"interpreted"*|*"interpretation"*)
      printf 'logic\n'
      ;;
    *"traceback"*|*"stacktrace"*|*"exception"*|*"module"*|*"compile"*|*"test "*|*"runtime"*|*"function"*|*"code "*)
      printf 'code\n'
      ;;
    *"cli"*|*"command "*|*"subcommand"*|*"flag "*|*"option "*|*"executable"*)
      printf 'tool\n'
      ;;
    *)
      printf 'unknown\n'
      ;;
  esac
}

observed_surface=$(detect_surface "$observation_text")
surface=$(detect_surface "$source_text")
if [ "$surface" = "unknown" ]; then
  surface=$observed_surface
fi
if [ "$observed_surface" = "unknown" ] && [ "$surface" != "unknown" ]; then
  observed_surface=$surface
fi

mode=other
case "$full_text" in
  *"ambiguous"*|*"unclear"*|*"underspecified"*|*"vague"*|*"not sure"*|*"uncertain"*)
    mode=ambiguity
    ;;
  *"contradict"*|*"inconsistent"*|*"does not match docs"*|*"did not match docs"*|*"differs from docs"*)
    mode=contradiction
    ;;
  *"unknown dispatch role"*|*"unknown "*|*"unrecognized"*|*"invalid choice"*|*"could not resolve"*|*"cannot resolve"*|*"no command named"*|*"no such subcommand"*)
    mode=name-resolution
    ;;
  *"lost context"*|*"missing context"*|*"lacked context"*|*"forgot"*|*"compaction"*)
    mode=context-loss
    ;;
  *"not found"*|*"no such file"*|*"missing"*|*"does not exist"*|*"absent"*)
    mode=missing
    ;;
  *"permission denied"*|*"operation not permitted"*)
    mode=permission
    ;;
  *"unauthorized"*|*"authentication"*|*"invalid token"*)
    mode=auth
    ;;
  *"timed out"*|*"timeout"*|*"deadline exceeded"*)
    mode=timeout
    ;;
  *"traceback"*|*"stacktrace"*|*"stack backtrace"*|*"panic"*|*"segmentation fault"*|*"crash"*|*"exception"*)
    mode=crash
    ;;
  *"json"*|*"yaml"*|*"schema"*|*"parse error"*|*"type mismatch"*|*"deserialize"*|*"serialize"*|*"shape mismatch"*)
    mode=schema
    ;;
  *"validation"*|*"invalid"*|*"required"*|*"assertion failed"*)
    mode=validation
    ;;
  *"wrong output"*|*"unexpected output"*|*"output mismatch"*|*"did not match"*|*"rendered incorrectly"*|*"misleading output"*)
    mode=output-mismatch
    ;;
  *"flaky"*|*"sometimes"*|*"intermittent"*|*"nondetermin"*|*"non-determin"*)
    mode=nondeterminism
    ;;
  *"slow"*|*"performance"*|*"hang"*|*"thrash"*|*"looped"*|*"repeated retries"*)
    mode=performance
    ;;
esac

run_effect=continued
case "$full_text" in
  *"rate limit"*|*"quota"*|*"too many requests"*|*"retry-after"*|*"http 403"*|*"timed out"*|*"timeout"*|*"not found"*|*"missing"*|*"permission denied"*|*"unauthorized"*|*"forbidden"*|*"traceback"*|*"stacktrace"*|*"panic"*|*"crash"*|*"error:"*|*"failed"*|*"cannot "*|*"could not "*|*"unable to "*|*"blocked"*)
    run_effect=blocked
    ;;
  *"retry"*|*"retries"*|*"thrash"*|*"looped"*|*"repeated"*|*"extra steps"*|*"flaky"*)
    run_effect=noisy
    ;;
  *"partial"*|*"workaround"*|*"fallback"*|*"degraded"*|*"succeeded but"*|*"continued"*)
    run_effect=degraded
    ;;
esac

guidance_quality=clear
case "$source_text" in
  '')
    guidance_quality=not-applicable
    ;;
  *"ambiguous"*|*"unclear"*|*"underspecified"*|*"uncertain"*)
    guidance_quality=ambiguous
    ;;
  *"contradict"*|*"inconsistent"*|*"wrong output"*|*"unexpected output"*|*"output mismatch"*|*"misleading"*|*"did not match docs"*)
    guidance_quality=misleading
    ;;
esac

case "$impact_override" in
  blocked|degraded|noisy|continued)
    run_effect_override=$impact_override
    ;;
  confusing)
    guidance_quality_override=ambiguous
    if [ -z "$run_effect_override" ]; then
      run_effect_override=continued
    fi
    ;;
  misleading)
    guidance_quality_override=misleading
    if [ -z "$run_effect_override" ]; then
      run_effect_override=degraded
    fi
    ;;
esac

if [ -n "$observed_surface_override" ]; then
  observed_surface=$observed_surface_override
fi
if [ -n "$surface_override" ]; then
  surface=$surface_override
fi
if [ -n "$mode_override" ]; then
  mode=$mode_override
fi
if [ -n "$run_effect_override" ]; then
  run_effect=$(normalize_run_effect "$run_effect_override")
fi
if [ -n "$guidance_quality_override" ]; then
  guidance_quality=$(normalize_guidance_quality "$guidance_quality_override")
fi

if [ -n "$evidence_type_override" ]; then
  case "$evidence_type_override" in
    execution|instruction|handoff|mixed) evidence_type=$evidence_type_override ;;
    *) evidence_type=mixed ;;
  esac
else
  case "$full_text" in
    *"handoff"*|*"delegat"*|*"remaining files"*)
      evidence_type=handoff
      ;;
    *)
      if [ -n "$actual_outcome$action_taken$tool_name$command_text$stderr_text" ]; then
        evidence_type=execution
      elif [ -n "$instruction_source$instruction_text$expected_outcome" ]; then
        evidence_type=instruction
      else
        evidence_type=mixed
      fi
      ;;
  esac
fi

if [ -n "$confidence_override" ]; then
  confidence=$confidence_override
else
  confidence=medium
  if [ "$surface" = "unknown" ] || [ "$observed_surface" = "unknown" ] || [ "$mode" = "other" ]; then
    confidence=low
  elif [ "$guidance_quality" = "misleading" ] || [ "$run_effect" = "blocked" ]; then
    confidence=high
  fi
fi

text_for_tags=$(
  printf '%s\n%s\n%s\n' "$full_text" "$tool_name" "$command_text"
)
tags=$(build_category_tags "$surface" "$mode" "$run_effect" "$guidance_quality" "$text_for_tags")
derived_category=$surface/$mode/$run_effect

printf 'observed_surface=%s\n' "$observed_surface"
printf 'surface=%s\n' "$surface"
printf 'mode=%s\n' "$mode"
printf 'run_effect=%s\n' "$run_effect"
printf 'guidance_quality=%s\n' "$guidance_quality"
printf 'confidence=%s\n' "$confidence"
printf 'evidence_type=%s\n' "$evidence_type"
printf 'derived_category=%s\n' "$derived_category"
printf 'tags=%s\n' "$tags"
printf 'taxonomy_version=%s\n' "$TAXONOMY_VERSION"
