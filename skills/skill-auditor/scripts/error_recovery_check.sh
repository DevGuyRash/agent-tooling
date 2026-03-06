#!/usr/bin/env sh
# skill-auditor — Error recovery check (D24).
#
# Usage:
#   error_recovery_check.sh <skill-directory>
#
# Checks that workflows document recovery paths and scripts use proper
# exit code discipline.

set -eu

case "${1-}" in
    -h|--help)
        echo "Usage: error_recovery_check.sh <skill-directory>"
        echo ""
        echo "Checks error recovery patterns:"
        echo "  - Trap handlers in scripts"
        echo "  - Exit code discipline (no exit 0 after errors)"
        echo "  - Recovery documentation in SKILL.md/references"
        echo "  - set -e / set -eu usage"
        exit 0
        ;;
esac

if [ $# -lt 1 ]; then
    echo "Usage: error_recovery_check.sh <skill-directory>"
    exit 1
fi

SKILL_DIR="$1"
if [ ! -d "$SKILL_DIR" ]; then
    echo "error: not a directory: $SKILL_DIR"
    exit 1
fi

DIR_NAME=$(basename "$SKILL_DIR")
printf '═══ Error Recovery Check: %s ═══\n\n' "$DIR_NAME"

total_issues=0
scripts_dir="$SKILL_DIR/scripts"

echo "── Exit Code Discipline ──"
if [ -d "$scripts_dir" ]; then
    for script in "$scripts_dir"/*.sh; do
        [ -f "$script" ] || continue
        relpath="${script#"$SKILL_DIR"/}"

        # Check for set -e or set -eu
        has_strict=$(grep -cE '^set -[eu]+' "$script" 2>/dev/null || true)
        if [ "$has_strict" -eq 0 ]; then
            echo "  ⚠ $relpath — missing 'set -e' or 'set -eu' [MINOR]"
            total_issues=$((total_issues + 1))
        else
            echo "  ✓ $relpath — has strict error mode"
        fi

        # Check for suspicious exit 0 patterns (exit 0 after actual error handling,
        # not in help text or usage blocks)
        suspicious_exit=$(awk '
            /^[[:space:]]*(echo|printf).*[Uu]sage/ { in_help = 1 }
            /^[[:space:]]*(exit|;;)/ { in_help = 0 }
            !in_help && /\|\|.*exit 1/ { saw_error = NR }
            !in_help && /return 1/ { saw_error = NR }
            !in_help && /^[[:space:]]*(echo|printf).*[Ee]rror:/ { saw_error = NR }
            /^[[:space:]]*exit 0/ {
                if (saw_error > 0 && NR - saw_error <= 2) {
                    print NR ": " $0
                }
                saw_error = 0
            }
        ' "$script" 2>/dev/null || true)
        if [ -n "$suspicious_exit" ]; then
            echo "  ⚠ $relpath — exit 0 near error context [MAJOR]:"
            printf '%s\n' "$suspicious_exit" | head -3 | while IFS= read -r line; do
                echo "      $line"
            done
            total_issues=$((total_issues + 1))
        fi
    done
else
    echo "  ℹ No scripts/ directory found"
fi

echo ""
echo "── Trap Handler Coverage ──"
if [ -d "$scripts_dir" ]; then
    total_scripts=0
    trap_scripts=0
    for script in "$scripts_dir"/*.sh; do
        [ -f "$script" ] || continue
        total_scripts=$((total_scripts + 1))
        if grep -q '^[[:space:]]*trap ' "$script" 2>/dev/null; then
            trap_scripts=$((trap_scripts + 1))
        fi
    done
    echo "  Scripts with trap handlers: $trap_scripts / $total_scripts"
    if [ "$total_scripts" -gt 0 ] && [ "$trap_scripts" -lt "$total_scripts" ]; then
        missing=$((total_scripts - trap_scripts))
        echo "  ℹ $missing scripts without trap handlers (check if they create temp resources)"
    fi
fi

echo ""
echo "── Recovery Documentation ──"
skill_md="$SKILL_DIR/SKILL.md"
if [ -f "$skill_md" ]; then
    recovery_mentions=$(grep -ciE '(recover|retry|restart|resume|abort|fail.*step|partial.*success|error.*recovery)' "$skill_md" 2>/dev/null || true)
    if [ "$recovery_mentions" -eq 0 ]; then
        echo "  ✗ SKILL.md has no recovery documentation [MAJOR]"
        total_issues=$((total_issues + 1))
    else
        echo "  ✓ SKILL.md mentions recovery/retry ($recovery_mentions references)"
    fi

    # Check for multi-step workflows without per-step status
    step_count=$(grep -cE '^\s*[0-9]+\.' "$skill_md" 2>/dev/null || true)
    if [ "$step_count" -ge 3 ]; then
        echo "  ℹ Multi-step workflow detected ($step_count numbered steps)"
    fi
else
    echo "  ℹ No SKILL.md found"
fi

# Check references for recovery documentation
if [ -d "$SKILL_DIR/references" ]; then
    ref_recovery=0
    for ref in "$SKILL_DIR/references"/*.md; do
        [ -f "$ref" ] || continue
        hits=$(grep -ciE '(recover|retry|restart|resume|abort|fail.*step|partial)' "$ref" 2>/dev/null || true)
        ref_recovery=$((ref_recovery + hits))
    done
    if [ "$ref_recovery" -gt 0 ]; then
        echo "  ✓ References contain recovery documentation ($ref_recovery mentions)"
    fi
fi

echo ""
echo "── Summary ──"
echo "  Issues found: $total_issues"

echo ""
echo "Done."

if [ "$total_issues" -gt 0 ]; then
    exit 1
fi
