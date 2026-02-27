#!/usr/bin/env sh
# skill-auditor — Context measurement script.
#
# Usage:
#   measure_context.sh <skill-directory> [--cli <binary-path>] [--cli-mode help|run]
#
# Measures the character/token cost of every document in a skill directory.
# If --cli is provided, also measures CLI outputs.
#
# Safety:
#   - Default `--cli-mode help` only calls `--help` on discovered commands.
#   - `--cli-mode run` executes discovered subcommands without `--help` and may
#     have side effects for some CLIs. Use only when auditing a known-safe CLI.
#
# Output is a structured table for direct inclusion in audit reports.

set -eu

SKILL_DIR=""
CLI_BIN=""
CLI_MODE="help"

# Parse arguments
while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help)
            echo "Usage: measure_context.sh <skill-directory> [--cli <binary-path>] [--cli-mode help|run]"
            echo ""
            echo "Measures the character/token cost of every document in a skill directory."
            echo "If --cli is provided, also measures CLI outputs."
            echo ""
            echo "Options:"
            echo "  --cli <path>           CLI binary to probe"
            echo "  --cli-mode help|run    help (default): only run '--help' for safety"
            echo "                         run: execute discovered subcommands (may have side effects)"
            exit 0
            ;;
        --cli)
            shift
            CLI_BIN="$1"
            ;;
        --cli-mode)
            shift
            CLI_MODE="$1"
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
    echo "Usage: measure_context.sh <skill-directory> [--cli <binary-path>] [--cli-mode help|run]"
    exit 1
fi

if [ ! -d "$SKILL_DIR" ]; then
    echo "error: not a directory: $SKILL_DIR"
    exit 1
fi

echo "═══ Context Measurement: $(basename "$SKILL_DIR") ═══"
echo ""

# ---------------------------------------------------------------------------
# 1. Document measurements
# ---------------------------------------------------------------------------
echo "── 1. Document Sizes ──"
echo ""
printf "  %-45s %6s %8s %8s\n" "File" "Lines" "Chars" "~Tokens"
printf "  %-45s %6s %8s %8s\n" "----" "-----" "-----" "-------"

total_chars=0
total_lines=0

doc_list=$(mktemp)
cleanup_lists() {
    rm -f "$doc_list"
}
trap cleanup_lists EXIT INT TERM

find "$SKILL_DIR" -type f \
    \( -name '*.md' -o -name '*.toml' -o -name '*.yaml' -o -name '*.yml' -o -name '*.json' \) \
    -not -path '*/target/*' -not -path '*/.git/*' \
    -not -name 'Cargo.*' 2>/dev/null | sort > "$doc_list"

while IFS= read -r file; do
    [ -z "$file" ] && continue
    relpath="${file#"$SKILL_DIR"/}"

    lines=$(wc -l < "$file" 2>/dev/null || echo 0)
    chars=$(wc -c < "$file" 2>/dev/null || echo 0)
    tokens=$(( chars / 4 ))

    printf "  %-45s %6d %8d %8d\n" "$relpath" "$lines" "$chars" "$tokens"
    total_chars=$((total_chars + chars))
    total_lines=$((total_lines + lines))
done < "$doc_list"

printf "  %-45s %6s %8s %8s\n" "" "-----" "-----" "-------"
printf "  %-45s %6d %8d %8d\n" "TOTAL (documents/config)" "$total_lines" "$total_chars" "$(( total_chars / 4 ))"

echo ""

# ---------------------------------------------------------------------------
# 2. CLI protocol output measurements (if CLI provided)
# ---------------------------------------------------------------------------
if [ -n "$CLI_BIN" ]; then
    resolved_cli=$(command -v "$CLI_BIN" 2>/dev/null || true)
    if [ -n "$resolved_cli" ]; then
        CLI_BIN="$resolved_cli"
    fi

    if [ ! -x "$CLI_BIN" ]; then
        echo "── 2. CLI Protocol Outputs ──"
        echo "  ⚠ CLI binary not executable: $CLI_BIN"
        echo ""
    else
        case "$CLI_MODE" in
            help|run)
                ;;
            *)
                echo "error: invalid --cli-mode: $CLI_MODE (expected: help|run)"
                exit 1
                ;;
        esac

        echo "── 2. CLI Protocol Outputs ──"
        echo ""
        printf "  %-50s %6s %8s %8s\n" "Command" "Lines" "Chars" "~Tokens"
        printf "  %-50s %6s %8s %8s\n" "-------" "-----" "-----" "-------"

        cli_total_chars=0

        # Discover available subcommands from --help output.
        # This is generic — works with any CLI, not just mpcr.
        help_output=$("$CLI_BIN" --help 2>&1 || true)

        extract_subcommands() {
            awk '
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

                    # Parse table-style command rows seen in many help formats:
                    #   "  add      Add file contents..."
                    #   "    status   Show status"
                    if (raw ~ /^[[:space:]]+[A-Za-z0-9_][A-Za-z0-9_-]*([[:space:]][[:space:]]+|\t)/) {
                        sub(/^[[:space:]]+/, "", raw)
                        split(raw, fields, /[[:space:]]+/)
                        emit(fields[1])
                    }

                    # Parse brace lists such as "{build,test,lint}".
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
            ' | sort -u
        }

        subcmds=$(printf '%s\n' "$help_output" | extract_subcommands || true)

        if [ -z "$subcmds" ]; then
            # In run mode, fallback to no-arg invocation (may have side effects).
            # Help mode must stay side-effect-safe and never invoke default command.
            if [ "$CLI_MODE" = "run" ]; then
                noarg_output=$("$CLI_BIN" 2>&1 || true)
                subcmds=$(printf '%s\n' "$noarg_output" | \
                    sed -n 's/.*{\([^}]*\)}.*/\1/p' | tr ',' '\n' | \
                    sed 's/^[[:space:]]*//' | grep -v '^$' | sort -u || true)
            fi

        fi

        if [ -z "$subcmds" ]; then
            echo "  ℹ No subcommands discovered; skipping CLI subcommand probing."
        fi

        # Measure each discovered subcommand
        for subcmd in $subcmds; do
            case "$CLI_MODE" in
                help)
                    output=$("$CLI_BIN" "$subcmd" --help 2>&1 || true)
                    ;;
                run)
                    output=$("$CLI_BIN" "$subcmd" 2>&1 || true)
                    ;;
            esac
            exit_word=$(echo "$output" | head -1)

            # Skip commands that produce errors or empty output
            case "$exit_word" in
                *error*|*Error*|*unknown*|*Unknown*|"")
                    continue
                    ;;
            esac

            lines=$(echo "$output" | wc -l)
            chars=$(echo "$output" | wc -c)
            # Skip trivially small outputs (likely error/usage messages)
            if [ "$chars" -lt 50 ]; then
                continue
            fi
            tokens=$(( chars / 4 ))
            printf "  %-50s %6d %8d %8d\n" "$subcmd" "$lines" "$chars" "$tokens"
            cli_total_chars=$((cli_total_chars + chars))

            # Probe one level deeper: try subcommand --help for sub-subcommands
            sub_help=$("$CLI_BIN" "$subcmd" --help 2>&1 || true)
            sub_subcmds=$(printf '%s\n' "$sub_help" | extract_subcommands || true)

            for sub in $sub_subcmds; do
                case "$CLI_MODE" in
                    help)
                        sub_output=$("$CLI_BIN" "$subcmd" "$sub" --help 2>&1 || true)
                        ;;
                    run)
                        sub_output=$("$CLI_BIN" "$subcmd" "$sub" 2>&1 || true)
                        ;;
                esac
                sub_first=$(echo "$sub_output" | head -1)
                case "$sub_first" in
                    *error*|*Error*|*unknown*|*Unknown*|"")
                        continue
                        ;;
                esac
                sub_chars=$(echo "$sub_output" | wc -c)
                if [ "$sub_chars" -lt 50 ]; then
                    continue
                fi
                sub_lines=$(echo "$sub_output" | wc -l)
                sub_tokens=$(( sub_chars / 4 ))
                printf "  %-50s %6d %8d %8d\n" "$subcmd $sub" "$sub_lines" "$sub_chars" "$sub_tokens"
                cli_total_chars=$((cli_total_chars + sub_chars))
            done
        done

        echo ""
        printf "  %-50s %20s\n" "CLI TOTAL:" "$cli_total_chars chars (~$(( cli_total_chars / 4 )) tokens)"
        echo ""

        # Grand total
        grand_total=$((total_chars + cli_total_chars))
        echo "── Grand Total ──"
        printf "  %-50s %20s\n" "Documents:" "$total_chars chars (~$(( total_chars / 4 )) tokens)"
        printf "  %-50s %20s\n" "CLI outputs:" "$cli_total_chars chars (~$(( cli_total_chars / 4 )) tokens)"
        printf "  %-50s %20s\n" "GRAND TOTAL:" "$grand_total chars (~$(( grand_total / 4 )) tokens)"
    fi
fi

echo ""
echo "Done."
