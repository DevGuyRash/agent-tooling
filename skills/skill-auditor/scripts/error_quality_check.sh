#!/usr/bin/env sh
# skill-auditor — Error message quality check (D7).
#
# Usage:
#   error_quality_check.sh <skill-directory> [--cli <binary>]
#
# Evaluates CLI error messages for agent-friendliness.

set -eu

CLI_BIN=""
SKILL_DIR=""

case "${1-}" in
    -h|--help)
        echo "Usage: error_quality_check.sh <skill-directory> [--cli <binary>]"
        echo ""
        echo "Checks error message quality for agent consumption:"
        echo "  - Error length (flag >3 lines, warn >10)"
        echo "  - Stack backtrace detection"
        echo "  - Valid alternatives in error output"
        echo "  - Consistent error: / hint: format"
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
    echo "Usage: error_quality_check.sh <skill-directory> [--cli <binary>]"
    exit 1
fi

if [ ! -d "$SKILL_DIR" ]; then
    echo "error: not a directory: $SKILL_DIR"
    exit 1
fi

DIR_NAME=$(basename "$SKILL_DIR")
printf '═══ Error Quality: %s ═══\n\n' "$DIR_NAME"

# Check scripts' error handling
echo "── Script Error Handling ──"

scripts_dir="$SKILL_DIR/scripts"
script_issues=0

if [ -d "$scripts_dir" ]; then
    tmplist=$(mktemp)
    trap 'rm -f "$tmplist"' EXIT INT TERM

    find "$scripts_dir" -type f \( -name '*.sh' -o -name '*.py' \) 2>/dev/null | sort > "$tmplist"

    while IFS= read -r script; do
        [ -z "$script" ] && continue
        [ ! -x "$script" ] && continue
        relpath="${script#"$SKILL_DIR"/}"

        # Test with bad input
        err_output=$("$script" "/nonexistent/path/$$" 2>&1 || true)
        if [ -n "$err_output" ]; then
            err_lines=$(printf '%s\n' "$err_output" | wc -l | tr -d ' ')
        else
            err_lines=0
        fi
        err_chars=$(printf '%s' "$err_output" | wc -c | tr -d ' ')

        echo "  $relpath (bad input):"
        echo "    Lines: $err_lines, Chars: $err_chars"

        if [ "$err_lines" -gt 10 ]; then
            echo "    ✗ Error too long (>10 lines) [MAJOR]"
            script_issues=$((script_issues + 1))
        elif [ "$err_lines" -gt 3 ]; then
            echo "    ⚠ Error somewhat long (>3 lines) [MINOR]"
            script_issues=$((script_issues + 1))
        else
            echo "    ✓ Error length OK"
        fi

        # Check for backtrace patterns
        if printf '%s' "$err_output" | grep -iE 'traceback|backtrace|stack trace|at .*\.rs:|panic' >/dev/null; then
            echo "    ✗ Stack backtrace in error output [MAJOR]"
            script_issues=$((script_issues + 1))
        fi

        # Check for error:/hint: format
        if printf '%s' "$err_output" | grep '^error:' >/dev/null; then
            echo "    ✓ Uses error: prefix format"
        fi
    done < "$tmplist"
else
    echo "  ℹ No scripts/ directory"
fi

# Check CLI error handling if binary provided
if [ -n "$CLI_BIN" ]; then
    echo ""
    echo "── CLI Error Handling ──"

    resolved_cli=$(command -v "$CLI_BIN" 2>/dev/null || true)
    if [ -n "$resolved_cli" ]; then
        CLI_BIN="$resolved_cli"
    fi

    if [ -x "$CLI_BIN" ]; then
        # Test with obviously bad input
        for bad_input in "--invalid-flag-$$" "nonexistent-subcommand-$$"; do
            err_output=$("$CLI_BIN" "$bad_input" 2>&1 || true)
            if [ -n "$err_output" ]; then
                err_lines=$(printf '%s\n' "$err_output" | wc -l | tr -d ' ')
            else
                err_lines=0
            fi

            echo "  $CLI_BIN $bad_input:"
            echo "    Lines: $err_lines"

            if [ "$err_lines" -gt 10 ]; then
                echo "    ✗ Error too long (>10 lines) [MAJOR]"
            elif [ "$err_lines" -gt 3 ]; then
                echo "    ⚠ Error somewhat long [MINOR]"
            else
                echo "    ✓ Error length OK"
            fi

            if printf '%s' "$err_output" | grep -iE 'traceback|backtrace|stack trace|panic' >/dev/null; then
                echo "    ✗ Stack backtrace detected [MAJOR]"
            fi

            if printf '%s' "$err_output" | grep -iE 'valid|available|expected|try' >/dev/null; then
                echo "    ✓ Error includes guidance/alternatives"
            else
                echo "    ⚠ Error lacks valid alternatives [MINOR]"
            fi
        done
    else
        echo "  ⚠ CLI binary not executable: $CLI_BIN"
    fi
fi

echo ""
echo "── Summary ──"
echo "  Script error issues: $script_issues"

echo ""
echo "Done."
