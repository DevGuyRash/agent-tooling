#!/usr/bin/env sh
# skill-auditor — Context measurement script (D8).
#
# Usage:
#   measure_context.sh <skill-directory> [--cli <binary-path>] [--cli-mode help|run] [--format text|json]
#
# Measures the character/token cost of skill documents and reports whether the
# skill follows a bounded, conditional progressive-disclosure pattern.

set -eu

SKILL_DIR=""
CLI_BIN=""
CLI_MODE="help"
FORMAT="text"

require_opt_value() {
    opt="$1"
    val="${2-}"
    case "$val" in
        ""|--*)
            echo "error: option $opt requires a value"
            exit 1
            ;;
    esac
}

probe_output=""
run_probe() {
    set +e
    probe_output=$("$@" 2>&1)
    probe_status=$?
    set -e
    [ "$probe_status" -eq 0 ]
}

while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help)
            echo "Usage: measure_context.sh <skill-directory> [--cli <binary-path>] [--cli-mode help|run] [--format text|json]"
            exit 0
            ;;
        --cli)
            require_opt_value "--cli" "${2-}"
            shift
            CLI_BIN="$1"
            ;;
        --cli-mode)
            require_opt_value "--cli-mode" "${2-}"
            shift
            CLI_MODE="$1"
            ;;
        --format)
            require_opt_value "--format" "${2-}"
            shift
            FORMAT="$1"
            ;;
        --*)
            echo "error: unknown option: $1"
            exit 1
            ;;
        *)
            if [ -z "$SKILL_DIR" ]; then
                SKILL_DIR="$1"
            else
                echo "error: unexpected argument: $1"
                exit 1
            fi
            ;;
    esac
    shift
done

if [ -z "$SKILL_DIR" ]; then
    echo "Usage: measure_context.sh <skill-directory> [--cli <binary-path>] [--cli-mode help|run] [--format text|json]"
    exit 1
fi

if [ ! -d "$SKILL_DIR" ]; then
    echo "error: not a directory: $SKILL_DIR"
    exit 1
fi

case "$CLI_MODE" in
    help|run) ;;
    *)
        echo "error: invalid --cli-mode: $CLI_MODE (expected: help|run)"
        exit 1
        ;;
esac

case "$FORMAT" in
    text|json) ;;
    *)
        echo "error: invalid --format: $FORMAT (expected: text|json)"
        exit 1
        ;;
esac

doc_list=$(mktemp)
cleanup() {
    rm -f "$doc_list"
}
trap cleanup EXIT INT TERM

find "$SKILL_DIR" -type f \
    \( -name '*.md' -o -name '*.toml' -o -name '*.yaml' -o -name '*.yml' -o -name '*.json' \) \
    -not -path '*/target/*' -not -path '*/.git/*' \
    -not -name 'Cargo.*' 2>/dev/null | sort > "$doc_list"

skill_md="$SKILL_DIR/SKILL.md"
skill_lines=0
skill_chars=0
skill_tokens=0
if [ -f "$skill_md" ]; then
    skill_lines=$(wc -l < "$skill_md" | tr -d ' ')
    skill_chars=$(wc -c < "$skill_md" | tr -d ' ')
    skill_tokens=$((skill_chars / 4))
fi

total_chars=0
total_lines=0
reference_count=0
largest_reference=""
largest_reference_chars=0
oversized_references=0

while IFS= read -r file; do
    [ -z "$file" ] && continue
    relpath="${file#"$SKILL_DIR"/}"
    lines=$(wc -l < "$file" | tr -d ' ')
    chars=$(wc -c < "$file" | tr -d ' ')
    total_lines=$((total_lines + lines))
    total_chars=$((total_chars + chars))
    case "$relpath" in
        references/*)
            reference_count=$((reference_count + 1))
            if [ "$chars" -gt "$largest_reference_chars" ]; then
                largest_reference_chars=$chars
                largest_reference="$relpath"
            fi
            if [ "$chars" -gt 15000 ]; then
                oversized_references=$((oversized_references + 1))
            fi
            ;;
    esac
done < "$doc_list"

has_reference_index=0
has_cli_router_guidance=0
has_cli_fallback=0

if [ -f "$skill_md" ]; then
    if grep -Eq '^## Reference index|^## Reference Index' "$skill_md"; then
        has_reference_index=1
    fi
    if grep -Eq 'run `[^`]+` for guidance|run `<skills-file-root>/scripts/[^`]+` for guidance|primary source: `[^`]+`' "$skill_md"; then
        has_cli_router_guidance=1
    fi
    if grep -Eqi 'IF the CLI is unavailable|fallback' "$skill_md"; then
        has_cli_fallback=1
    fi
fi

cli_help_chars=0
cli_help_lines=0
cli_help_tokens=0
cli_probed=0
if [ -n "$CLI_BIN" ]; then
    resolved_cli=$(command -v "$CLI_BIN" 2>/dev/null || true)
    if [ -n "$resolved_cli" ]; then
        CLI_BIN="$resolved_cli"
    fi
    if [ -x "$CLI_BIN" ]; then
        cli_probed=1
        if run_probe "$CLI_BIN" --help; then
            cli_help_chars=$(printf '%s\n' "$probe_output" | wc -c | tr -d ' ')
            cli_help_lines=$(printf '%s\n' "$probe_output" | wc -l | tr -d ' ')
            cli_help_tokens=$((cli_help_chars / 4))
        fi
    fi
fi

peak_chars=$skill_chars
peak_reference="$largest_reference"
if [ "$largest_reference_chars" -gt 0 ]; then
    peak_chars=$((skill_chars + largest_reference_chars))
fi
peak_tokens=$((peak_chars / 4))

violations=0
skill_body_exceeds_budget=0
peak_context_exceeds_budget=0
if [ "$skill_chars" -gt 8192 ]; then
    skill_body_exceeds_budget=1
    violations=$((violations + 1))
fi
if [ "$peak_tokens" -gt 12000 ]; then
    peak_context_exceeds_budget=1
    violations=$((violations + 1))
fi
if [ "$oversized_references" -gt 0 ]; then
    violations=$((violations + oversized_references))
fi
if [ "$reference_count" -gt 0 ] && [ "$has_reference_index" -eq 0 ] && [ "$has_cli_router_guidance" -eq 0 ]; then
    violations=$((violations + 1))
fi
if [ "$has_cli_router_guidance" -eq 1 ] && [ "$has_cli_fallback" -eq 0 ]; then
    violations=$((violations + 1))
fi

if [ "$FORMAT" = "json" ]; then
    printf '{'
    printf '"summary":{'
    printf '"skill_lines":%d,' "$skill_lines"
    printf '"skill_chars":%d,' "$skill_chars"
    printf '"skill_tokens":%d,' "$skill_tokens"
    printf '"reference_count":%d,' "$reference_count"
    printf '"largest_reference_chars":%d,' "$largest_reference_chars"
    printf '"oversized_references":%d,' "$oversized_references"
    printf '"peak_context_chars":%d,' "$peak_chars"
    printf '"peak_context_tokens":%d,' "$peak_tokens"
    printf '"skill_body_exceeds_budget":%d,' "$skill_body_exceeds_budget"
    printf '"peak_context_exceeds_budget":%d,' "$peak_context_exceeds_budget"
    printf '"has_reference_index":%d,' "$has_reference_index"
    printf '"has_cli_router_guidance":%d,' "$has_cli_router_guidance"
    printf '"has_cli_fallback":%d,' "$has_cli_fallback"
    printf ',"cli_probed":%d,"cli_help_chars":%d,"cli_help_lines":%d,"cli_help_tokens":%d' \
        "$cli_probed" "$cli_help_chars" "$cli_help_lines" "$cli_help_tokens"
    printf ',"violations":%d' "$violations"
    printf '},'
    printf '"largest_reference":"%s"' "$(printf '%s' "$largest_reference" | sed 's/\\/\\\\/g; s/"/\\"/g')"
    printf '}\n'
    exit 0
fi

echo "═══ Context Measurement: $(basename "$SKILL_DIR") ═══"
echo ""
echo "── D8 Budget Summary ──"
printf "  %-30s %s\n" "SKILL.md:" "$skill_chars chars (~$skill_tokens tokens, $skill_lines lines)"
printf "  %-30s %s\n" "Largest reference:" "${largest_reference:-none} (${largest_reference_chars} chars)"
printf "  %-30s %s\n" "Peak context:" "$peak_chars chars (~$peak_tokens tokens)"
printf "  %-30s %s\n" "Reference count:" "$reference_count"
printf "  %-30s %s\n" "Oversized references (>15KB):" "$oversized_references"
echo ""
echo "── Routing Signals ──"
printf "  %-30s %s\n" "Reference index present:" "$has_reference_index"
printf "  %-30s %s\n" "CLI router guidance present:" "$has_cli_router_guidance"
printf "  %-30s %s\n" "CLI fallback present:" "$has_cli_fallback"
if [ "$cli_probed" -eq 1 ]; then
    printf "  %-30s %s\n" "CLI --help output:" "$cli_help_chars chars (~$cli_help_tokens tokens, $cli_help_lines lines)"
fi
echo ""
echo "── Summary ──"
echo "  Violations found: $violations"
echo ""
echo "Done."
