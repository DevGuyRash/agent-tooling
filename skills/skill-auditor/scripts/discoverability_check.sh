#!/usr/bin/env sh
# skill-auditor — CLI discoverability helper check (D22).
#
# Usage:
#   discoverability_check.sh <skill-directory> [--cli <binary>] [--format text|json]
#
# Evaluates whether skills provide deterministic CLI discoverability helpers for
# enum-like options (for example --role, --mode, --phase values).

set -eu

SKILL_DIR=""
CLI_BIN=""
FORMAT="text"
TAB=$(printf '\t')

extract_enum_options() {
    awk '
        function is_enum_placeholder(raw, lower) {
            lower = tolower(raw)
            if (raw ~ /[|,\/]/) return 1
            if (lower ~ /(role|mode|phase|status|type|format|level|profile|variant|provider|backend|engine|target|env|environment|strategy|policy|kind)/) return 1
            return 0
        }
        {
            line = $0
            while (match(line, /--[a-z][a-z0-9-]*[[:space:]]+<[^>]+>/)) {
                chunk = substr(line, RSTART, RLENGTH)
                split(chunk, fields, /[[:space:]]+/)
                ph = fields[2]
                gsub(/^</, "", ph)
                gsub(/>$/, "", ph)
                if (is_enum_placeholder(ph)) {
                    print fields[1]
                }
                line = substr(line, RSTART + RLENGTH)
            }
            line = $0
            while (match(line, /--(role|mode|phase|status|type)[[:space:]]+[a-z][a-z0-9_-]*/)) {
                chunk = substr(line, RSTART, RLENGTH)
                split(chunk, fields, /[[:space:]]+/)
                print fields[1]
                line = substr(line, RSTART + RLENGTH)
            }
        }
    ' "$1" 2>/dev/null || true
}

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

usage() {
    echo "Usage: discoverability_check.sh <skill-directory> [--cli <binary>] [--format text|json]"
    echo ""
    echo "Checks CLI discoverability helper coverage:"
    echo "  - enum-like option presence in docs"
    echo "  - discovery helper examples in docs (--help/--list)"
    echo "  - CLI help/list affordances when --cli is provided"
    echo "  - option coverage in aggregated CLI help corpus"
}

escape_json() {
    printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'
}

while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help)
            usage
            exit 0
            ;;
        --cli)
            require_opt_value "--cli" "${2-}"
            shift
            CLI_BIN="$1"
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
    usage
    exit 1
fi

if [ ! -d "$SKILL_DIR" ]; then
    echo "error: not a directory: $SKILL_DIR"
    exit 1
fi

case "$FORMAT" in
    text|json)
        ;;
    *)
        echo "error: invalid --format: $FORMAT (expected text|json)"
        exit 1
        ;;
esac

tmp_md=$(mktemp)
tmp_opts=$(mktemp)
tmp_help=$(mktemp)
tmp_opt_rows=$(mktemp)
cleanup() {
    rm -f "$tmp_md" "$tmp_opts" "$tmp_help" "$tmp_opt_rows"
}
trap cleanup EXIT INT TERM

find "$SKILL_DIR" -type f -name '*.md' \
    -not -path '*/tests/*' -not -path '*/.git/*' 2>/dev/null | sort > "$tmp_md"

: > "$tmp_opts"
while IFS= read -r md; do
    [ -z "$md" ] && continue
    extract_enum_options "$md" >> "$tmp_opts"
done < "$tmp_md"
sort -u "$tmp_opts" -o "$tmp_opts"

total_enum_options=$(grep -c '.' "$tmp_opts" 2>/dev/null || true)

doc_discovery_examples=0
while IFS= read -r md; do
    [ -z "$md" ] && continue
    hits=$(grep -Ec -- '(^|[[:space:]])(--help|-h|--list)([[:space:]]|$)|`[^`]*(--help|--list| help| list)[^`]*`' "$md" 2>/dev/null || true)
    doc_discovery_examples=$((doc_discovery_examples + hits))
done < "$tmp_md"

cli_help_checked=0
cli_list_like_helpers=0
option_help_coverage_failures=0
missing_doc_helper=0
missing_cli_helper=0
cli_unavailable=0

if [ "$total_enum_options" -gt 0 ] && [ "$doc_discovery_examples" -eq 0 ]; then
    missing_doc_helper=1
fi

resolved_cli=""
if [ -n "$CLI_BIN" ]; then
    resolved_cli=$(command -v "$CLI_BIN" 2>/dev/null || true)
    if [ -n "$resolved_cli" ]; then
        CLI_BIN="$resolved_cli"
    fi

    if [ -x "$CLI_BIN" ]; then
        cli_help_checked=1
        : > "$tmp_help"

        set +e
        top_help=$("$CLI_BIN" --help 2>&1)
        set -e
        printf '%s\n' "$top_help" >> "$tmp_help"

        subcmds=$(printf '%s\n' "$top_help" | awk '
            function emit(token) {
                if (token == "" || token ~ /^-/) {
                    return
                }
                if (token ~ /^[A-Za-z0-9_][A-Za-z0-9_-]*$/) {
                    print token
                }
            }
            {
                raw = $0
                if (raw ~ /^[[:space:]]+[A-Za-z0-9_][A-Za-z0-9_-]*([[:space:]][[:space:]]+|\t)/) {
                    sub(/^[[:space:]]+/, "", raw)
                    split(raw, fields, /[[:space:]]+/)
                    emit(fields[1])
                }
                while (match(raw, /\{[^{}]+\}/)) {
                    block = substr(raw, RSTART + 1, RLENGTH - 2)
                    count = split(block, values, /,/)
                    for (i = 1; i <= count; i++) {
                        gsub(/^[[:space:]]+|[[:space:]]+$/, "", values[i])
                        emit(values[i])
                    }
                    raw = substr(raw, RSTART + RLENGTH)
                }
            }
        ' | sort -u)

        for subcmd in $subcmds; do
            set +e
            sub_help=$("$CLI_BIN" "$subcmd" --help 2>&1)
            set -e
            [ -n "$sub_help" ] && printf '%s\n' "$sub_help" >> "$tmp_help"
        done

        cli_list_like_helpers=$(grep -Eic -- '(^|[[:space:]])(--list|list)([[:space:]]|$)|available values|valid values|choices|supported values' "$tmp_help" || true)
        if [ "$total_enum_options" -gt 0 ] && [ "$cli_list_like_helpers" -eq 0 ]; then
            missing_cli_helper=1
        fi
    else
        cli_unavailable=1
    fi
fi

: > "$tmp_opt_rows"
while IFS= read -r opt; do
    [ -z "$opt" ] && continue
    status="unchecked-no-cli"
    evidence="CLI binary not provided"

    if [ "$cli_unavailable" -eq 1 ]; then
        status="cli-unavailable"
        evidence="CLI binary is not executable"
    elif [ "$cli_help_checked" -eq 1 ]; then
        if grep -- "$opt" "$tmp_help" >/dev/null; then
            status="found-in-help"
            evidence="option appears in CLI help corpus"
        else
            status="missing-in-help"
            evidence="option not found in CLI help corpus"
            option_help_coverage_failures=$((option_help_coverage_failures + 1))
        fi
    fi

    printf '%s\t%s\t%s\n' "$opt" "$status" "$evidence" >> "$tmp_opt_rows"
done < "$tmp_opts"

discovery_gaps=$((missing_doc_helper + missing_cli_helper + cli_unavailable))

if [ "$FORMAT" = "json" ]; then
    printf '{'
    printf '"summary":{'
    printf '"total_enum_options":%d,' "$total_enum_options"
    printf '"doc_discovery_examples":%d,' "$doc_discovery_examples"
    printf '"cli_help_checked":%d,' "$cli_help_checked"
    printf '"cli_list_like_helpers":%d,' "$cli_list_like_helpers"
    printf '"option_help_coverage_failures":%d,' "$option_help_coverage_failures"
    printf '"discovery_gaps":%d' "$discovery_gaps"
    printf '},'
    printf '"options":['
    first=1
    while IFS="$TAB" read -r opt status evidence; do
        [ -z "$opt" ] && continue
        if [ "$first" -eq 0 ]; then
            printf ','
        fi
        first=0
        printf '{"option":"%s","status":"%s","evidence":"%s"}' \
            "$(escape_json "$opt")" "$(escape_json "$status")" "$(escape_json "$evidence")"
    done < "$tmp_opt_rows"
    printf ']'
    printf '}\n'
    exit 0
fi

DIR_NAME=$(basename "$SKILL_DIR")
printf '═══ CLI Discoverability: %s ═══\n\n' "$DIR_NAME"

echo "── Documentation Signals ──"
echo "  Enum-like options documented: $total_enum_options"
echo "  Discovery helper examples in docs: $doc_discovery_examples"
if [ "$missing_doc_helper" -eq 1 ]; then
    echo "  ✗ Enum-like options exist but docs lack --help/--list helper examples [MAJOR]"
else
    echo "  ✓ Documentation includes discoverability helper examples"
fi

echo ""
echo "── CLI Signals ──"
if [ -z "$CLI_BIN" ]; then
    echo "  ℹ No --cli provided; CLI discoverability checks skipped"
elif [ "$cli_unavailable" -eq 1 ]; then
    echo "  ✗ CLI binary not executable: $CLI_BIN [MAJOR]"
else
    echo "  CLI help checked: $cli_help_checked"
    echo "  List-like discoverability hints found: $cli_list_like_helpers"
    if [ "$missing_cli_helper" -eq 1 ]; then
        echo "  ✗ CLI help corpus lacks list-like discoverability helper hints [MAJOR]"
    else
        echo "  ✓ CLI help corpus exposes discoverability helper hints"
    fi
fi

echo ""
echo "── Option Coverage ──"
if [ "$total_enum_options" -eq 0 ]; then
    echo "  ℹ No enum-like options documented"
else
    echo "  Coverage failures: $option_help_coverage_failures"
    while IFS="$TAB" read -r opt status evidence; do
        [ -z "$opt" ] && continue
        case "$status" in
            missing-in-help)
                echo "  ✗ $opt — $evidence [MAJOR]"
                ;;
            found-in-help)
                echo "  ✓ $opt — $evidence"
                ;;
            *)
                echo "  ⚠ $opt — $evidence"
                ;;
        esac
    done < "$tmp_opt_rows"
fi

echo ""
echo "── Summary ──"
echo "  Discovery gaps: $discovery_gaps"
echo "  Option help coverage failures: $option_help_coverage_failures"

echo ""
echo "Done."
