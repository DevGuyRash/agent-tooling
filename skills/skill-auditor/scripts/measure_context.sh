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
toml_list=$(mktemp)
cleanup_lists() {
    rm -f "$doc_list" "$toml_list"
}
trap cleanup_lists EXIT INT TERM

find "$SKILL_DIR" -type f -name '*.md' \
    -not -path '*/target/*' -not -path '*/.git/*' \
    -print0 2>/dev/null | sort -z > "$doc_list"

while IFS= read -r -d '' file; do
    [ -z "$file" ] && continue
    relpath="${file#"$SKILL_DIR"/}"

    lines=$(wc -l < "$file" 2>/dev/null || echo 0)
    chars=$(wc -c < "$file" 2>/dev/null || echo 0)
    tokens=$(( chars / 4 ))

    printf "  %-45s %6d %8d %8d\n" "$relpath" "$lines" "$chars" "$tokens"
    total_chars=$((total_chars + chars))
    total_lines=$((total_lines + lines))
done < "$doc_list"

# Also measure TOML protocol files if they exist
find "$SKILL_DIR" -type f -name '*.toml' \
    -not -path '*/target/*' -not -path '*/.git/*' \
    -not -name 'Cargo.*' -print0 2>/dev/null | sort -z > "$toml_list"

while IFS= read -r -d '' file; do
    [ -z "$file" ] && continue
    relpath="${file#"$SKILL_DIR"/}"

    lines=$(wc -l < "$file" 2>/dev/null || echo 0)
    chars=$(wc -c < "$file" 2>/dev/null || echo 0)
    tokens=$(( chars / 4 ))

    printf "  %-45s %6d %8d %8d\n" "$relpath" "$lines" "$chars" "$tokens"
    total_chars=$((total_chars + chars))
    total_lines=$((total_lines + lines))
done < "$toml_list"

printf "  %-45s %6s %8s %8s\n" "" "-----" "-----" "-------"
printf "  %-45s %6d %8d %8d\n" "TOTAL (documents)" "$total_lines" "$total_chars" "$(( total_chars / 4 ))"

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
                BEGIN { in_commands = 0 }
                {
                    line = tolower($0)
                    if (line ~ /^[[:space:]]*(available[[:space:]]+)?commands?:[[:space:]]*$/ ||
                        line ~ /^[[:space:]]*(core|additional|management|utility|other)[[:space:]]+commands?:[[:space:]]*$/) {
                        in_commands = 1
                        next
                    }

                    if (in_commands && line ~ /^[[:space:]]*$/) {
                        in_commands = 0
                        next
                    }

                    if (in_commands && $0 ~ /^[[:space:]][[:space:]]+[a-z0-9][a-z0-9-]*/) {
                        sub(/^[[:space:]]+/, "", $0)
                        split($0, a, /[^a-z0-9-]/)
                        if (a[1] != "" && a[1] !~ /^-/) {
                            print a[1]
                        }
                    }
                }
            ' | sort -u
        }

        subcmds=$(printf '%s\n' "$help_output" | extract_subcommands || true)

        if [ -z "$subcmds" ]; then
            # Fallback: try the binary with no args
            subcmds=$(echo "$help_output" | \
                sed -n 's/.*{\([^}]*\)}.*/\1/p' | tr ',' '\n' | \
                sed 's/^[[:space:]]*//' | grep -v '^$' || true)
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
