#!/usr/bin/env sh
# skill-auditor — Output size discipline check (D10).
#
# Usage:
#   output_size_check.sh <skill-directory> [--cli <binary>]
#
# Checks that CLI/script outputs are sized for agent context.

set -eu

CLI_BIN=""
SKILL_DIR=""

case "${1-}" in
    -h|--help)
        echo "Usage: output_size_check.sh <skill-directory> [--cli <binary>]"
        echo ""
        echo "Checks output size discipline:"
        echo "  - Measure script --help output sizes"
        echo "  - Measure CLI subcommand output sizes"
        echo "  - Flag outputs >4096 chars (4KB)"
        echo "  - Check for filtering/compact flags"
        exit 0
        ;;
esac

while [ $# -gt 0 ]; do
    case "$1" in
        --cli)
            shift
            CLI_BIN="${1-}"
            if [ -z "$CLI_BIN" ]; then
                echo "error: --cli requires a value"
                exit 1
            fi
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
    echo "Usage: output_size_check.sh <skill-directory> [--cli <binary>]"
    exit 1
fi

if [ ! -d "$SKILL_DIR" ]; then
    echo "error: not a directory: $SKILL_DIR"
    exit 1
fi

DIR_NAME=$(basename "$SKILL_DIR")
printf '═══ Output Size Discipline: %s ═══\n\n' "$DIR_NAME"

issues=0

echo "── Script Output Sizes ──"
printf "  %-40s %6s %8s %6s\n" "Command" "Lines" "Chars" "Status"
printf "  %-40s %6s %8s %6s\n" "-------" "-----" "-----" "------"

scripts_dir="$SKILL_DIR/scripts"
if [ -d "$scripts_dir" ]; then
    tmplist=$(mktemp)
    trap 'rm -f "$tmplist"' EXIT INT TERM

    find "$scripts_dir" -type f \( -name '*.sh' -o -name '*.py' \) -executable 2>/dev/null | sort > "$tmplist"

    while IFS= read -r script; do
        [ -z "$script" ] && continue
        relpath="${script#"$SKILL_DIR"/}"

        output=$("$script" --help 2>&1 || true)
        lines=$(printf '%s' "$output" | wc -l | tr -d ' ')
        chars=$(printf '%s' "$output" | wc -c | tr -d ' ')

        if [ "$chars" -gt 10000 ]; then
            status="X >10K"
            issues=$((issues + 1))
        elif [ "$chars" -gt 4096 ]; then
            status="W >4K"
            issues=$((issues + 1))
        else
            status="OK"
        fi

        printf "  %-40s %6d %8d %6s\n" "$relpath --help" "$lines" "$chars" "$status"
    done < "$tmplist"
else
    echo "  (no scripts/ directory)"
fi

# Check CLI if binary provided
if [ -n "$CLI_BIN" ]; then
    echo ""
    echo "── CLI Output Sizes ──"
    printf "  %-40s %6s %8s %6s\n" "Command" "Lines" "Chars" "Status"
    printf "  %-40s %6s %8s %6s\n" "-------" "-----" "-----" "------"

    resolved_cli=$(command -v "$CLI_BIN" 2>/dev/null || true)
    if [ -n "$resolved_cli" ]; then
        CLI_BIN="$resolved_cli"
    fi

    if [ -x "$CLI_BIN" ]; then
        # Test --help
        output=$("$CLI_BIN" --help 2>&1 || true)
        lines=$(printf '%s' "$output" | wc -l | tr -d ' ')
        chars=$(printf '%s' "$output" | wc -c | tr -d ' ')

        if [ "$chars" -gt 10000 ]; then
            status="X >10K"
            issues=$((issues + 1))
        elif [ "$chars" -gt 4096 ]; then
            status="W >4K"
            issues=$((issues + 1))
        else
            status="OK"
        fi
        printf "  %-40s %6d %8d %6s\n" "$CLI_BIN --help" "$lines" "$chars" "$status"

        # Check for filtering flags
        echo ""
        echo "── Filtering Flag Check ──"
        if printf '%s' "$output" | grep -iE '\-\-summary|\-\-quiet|\-\-json|\-\-compact|\-\-fields|\-\-max-items' >/dev/null; then
            echo "  ✓ Filtering flags available"
        else
            echo "  ⚠ No filtering flags detected (--summary, --json, --compact) [MINOR]"
            issues=$((issues + 1))
        fi
    else
        echo "  ⚠ CLI binary not executable: $CLI_BIN"
    fi
fi

echo ""
echo "── Summary ──"
echo "  Issues found: $issues"

echo ""
echo "Done."
