#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
. "$SCRIPT_DIR/_common.sh"

RULES_FILE="${RULES_FILE:-$(CDPATH='' cd -- "$(dirname "$0")/.." && pwd)/data/categorization-rules.json}"
[ -f "$RULES_FILE" ] || die "Categorization rules file not found: $RULES_FILE"

print_help() {
  cat <<'EOF'
Usage:
  sh scripts/categorize.sh [options]

Options:
  --source-ref TEXT
  --instruction-text TEXT
  --action-taken TEXT
  --expected-outcome TEXT
  --actual-outcome TEXT
  --hindsight TEXT
  --reading TEXT
  --tool-name TEXT
  --command TEXT
  --stderr TEXT
  --stdout-excerpt TEXT
  --observed-surface VALUE
  --surface VALUE
  --mode VALUE
  --run-effect VALUE
  --guidance-quality VALUE
  --confidence VALUE
  --help

Output:
  observed_surface=<value>
  surface=<value>
  mode=<value>
  run_effect=<value>
  guidance_quality=<value>
  confidence=<value>
  derived_category=<surface/mode/run_effect>
  taxonomy_version=<value>
EOF
}

source_ref=
instruction_text=
action_taken=
expected_outcome=
actual_outcome=
hindsight=
reading=
tool_name=
command_text=
stderr_text=
stdout_excerpt=
observed_surface_override=
surface_override=
mode_override=
run_effect_override=
guidance_quality_override=
confidence_override=

while [ $# -gt 0 ]; do
  case "$1" in
    --source-ref) source_ref=${2-}; shift 2 ;;
    --instruction-text) instruction_text=${2-}; shift 2 ;;
    --action-taken) action_taken=${2-}; shift 2 ;;
    --expected-outcome) expected_outcome=${2-}; shift 2 ;;
    --actual-outcome) actual_outcome=${2-}; shift 2 ;;
    --hindsight) hindsight=${2-}; shift 2 ;;
    --reading) reading=${2-}; shift 2 ;;
    --tool-name) tool_name=${2-}; shift 2 ;;
    --command) command_text=${2-}; shift 2 ;;
    --stderr) stderr_text=${2-}; shift 2 ;;
    --stdout-excerpt) stdout_excerpt=${2-}; shift 2 ;;
    --observed-surface) observed_surface_override=${2-}; shift 2 ;;
    --surface) surface_override=${2-}; shift 2 ;;
    --mode) mode_override=${2-}; shift 2 ;;
    --run-effect) run_effect_override=${2-}; shift 2 ;;
    --guidance-quality) guidance_quality_override=${2-}; shift 2 ;;
    --confidence) confidence_override=${2-}; shift 2 ;;
    --help|-h) print_help; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
done

# Normalize error message boilerplate and synonyms before pattern matching.
# This reduces wording-dependent classification variance for the same error class.
normalize_categorizer_text() {
  printf '%s' "$1" | sed -E \
    -e 's/^(error|fatal|warning|Error|Fatal|Warning|ERROR|FATAL|WARNING)[[:space:]]*:[[:space:]]*/error: /g' \
    -e 's/\b[Nn]o such file or directory\b/file not found/g' \
    -e 's/\bENOENT\b/file not found/g' \
    -e 's/\bcannot find\b/file not found/g' \
    -e 's/\bcould not (find|locate)\b/file not found/g' \
    -e 's/\b[Pp]ermission denied\b/permission denied/g' \
    -e 's/\bEACCES\b/permission denied/g' \
    -e 's/\baccess denied\b/permission denied/g' \
    -e 's/\b[Cc]onnection refused\b/connection refused/g' \
    -e 's/\bECONNREFUSED\b/connection refused/g' \
    -e 's/\b[Tt]imed? ?out\b/timeout/g' \
    -e 's/\bETIMEDOUT\b/timeout/g' \
    -e 's/\bdeadline exceeded\b/timeout/g' \
    -e 's/\b(the|a|an) //g'
}

observation_text=$(
  printf '%s\n%s\n%s\n%s\n%s\n' \
    "$action_taken" \
    "$actual_outcome" \
    "$tool_name" \
    "$command_text" \
    "$stderr_text"
)
observation_text=$(normalize_categorizer_text "$observation_text")
observation_text=$(lower "$observation_text")

source_text=$(
  printf '%s\n%s\n%s\n%s\n%s\n%s\n' \
    "$source_ref" \
    "$instruction_text" \
    "$expected_outcome" \
    "$hindsight" \
    "$reading" \
    "$stdout_excerpt"
)
source_text=$(normalize_categorizer_text "$source_text")
source_text=$(lower "$source_text")

full_text=$(
  printf '%s\n%s\n' "$observation_text" "$source_text"
)

detect_surface() {
  text=$1
  match=$(printf '%s' "$text" | jq -Rr --slurpfile rules "$RULES_FILE" '
    . as $text
    | $rules[0].surface_patterns
    | to_entries[]
    | select(.value | any(. as $kw | $text | contains($kw)))
    | .key
  ' | head -1)
  if [ -n "$match" ]; then
    printf '%s\n' "$match"
  else
    jq -r '.defaults.surface' "$RULES_FILE"
  fi
}

observed_surface=$(detect_surface "$observation_text")
surface=$(detect_surface "$source_text")
if [ "$surface" = "unknown" ]; then
  surface=$observed_surface
fi
if [ "$observed_surface" = "unknown" ] && [ "$surface" != "unknown" ]; then
  observed_surface=$surface
fi

mode=$(printf '%s' "$full_text" | jq -Rr --slurpfile rules "$RULES_FILE" '
  . as $text
  | $rules[0].mode_patterns
  | to_entries[]
  | select(.value | any(. as $kw | $text | contains($kw)))
  | .key
' | head -1)
if [ -z "$mode" ]; then
  mode=$(jq -r '.defaults.mode' "$RULES_FILE")
fi

run_effect=$(printf '%s' "$full_text" | jq -Rr --slurpfile rules "$RULES_FILE" '
  . as $text
  | $rules[0].run_effect_patterns
  | to_entries[]
  | select(.value | any(. as $kw | $text | contains($kw)))
  | .key
' | head -1)
if [ -z "$run_effect" ]; then
  run_effect=$(jq -r '.defaults.run_effect' "$RULES_FILE")
fi

if [ -z "$source_text" ]; then
  guidance_quality=0
else
  gq_match=$(printf '%s' "$source_text" | jq -Rr --slurpfile rules "$RULES_FILE" '
    . as $text
    | $rules[0].guidance_quality_patterns
    | to_entries[]
    | select(.value | any(. as $kw | $text | contains($kw)))
    | .key
  ' | head -1)
  if [ -n "$gq_match" ]; then
    guidance_quality=$gq_match
  else
    guidance_quality=$(jq -r '.defaults.guidance_quality' "$RULES_FILE")
  fi
fi

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

if [ -n "$confidence_override" ]; then
  confidence=$(normalize_confidence "$confidence_override")
else
  confidence=3
  if [ "$surface" = "unknown" ] || [ "$mode" = "other" ]; then
    confidence=2
  elif [ "$guidance_quality" -le 1 ] && [ "$guidance_quality" -gt 0 ] || [ "$run_effect" = "blocked" ]; then
    confidence=4
  fi
fi

derived_category=$surface/$mode/$run_effect

printf 'observed_surface=%s\n' "$observed_surface"
printf 'surface=%s\n' "$surface"
printf 'mode=%s\n' "$mode"
printf 'run_effect=%s\n' "$run_effect"
printf 'guidance_quality=%s\n' "$guidance_quality"
printf 'confidence=%s\n' "$confidence"
printf 'derived_category=%s\n' "$derived_category"
printf 'taxonomy_version=%s\n' "$TAXONOMY_VERSION"
