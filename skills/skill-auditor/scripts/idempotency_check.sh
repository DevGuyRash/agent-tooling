#!/usr/bin/env sh
# skill-auditor — Idempotency check (D23).
#
# Usage:
#   idempotency_check.sh <skill-directory>
#
# Checks that representative scripts leave no residual state and produce
# identical output on repeated runs.

set -eu

MAX_SCRIPTS=8
FULL_MODE=0

case "${1-}" in
    -h|--help)
        echo "Usage: idempotency_check.sh <skill-directory> [--full] [--max-scripts <n>]"
        echo ""
        echo "Checks script idempotency:"
        echo "  - Re-run output is byte-identical for a bounded representative set"
        echo "  - No temp files left behind after completion"
        echo "  - Trap handlers present for cleanup"
        exit 0
        ;;
esac

while [ $# -gt 0 ]; do
    case "$1" in
        --full)
            FULL_MODE=1
            ;;
        --max-scripts)
            shift
            MAX_SCRIPTS="${1-}"
            case "$MAX_SCRIPTS" in
                ''|*[!0-9]*)
                    echo "error: --max-scripts must be a positive integer"
                    exit 1
                    ;;
                0)
                    echo "error: --max-scripts must be a positive integer"
                    exit 1
                    ;;
            esac
            ;;
        --*)
            echo "error: unknown option: $1"
            exit 1
            ;;
        *)
            if [ -z "${SKILL_DIR-}" ]; then
                SKILL_DIR="$1"
            else
                echo "error: unexpected argument: $1"
                exit 1
            fi
            ;;
    esac
    shift
done

if [ -z "${SKILL_DIR-}" ]; then
    echo "Usage: idempotency_check.sh <skill-directory> [--full] [--max-scripts <n>]"
    exit 1
fi
if [ ! -d "$SKILL_DIR" ]; then
    echo "error: not a directory: $SKILL_DIR"
    exit 1
fi

DIR_NAME=$(basename "$SKILL_DIR")
printf '═══ Idempotency Check: %s ═══\n\n' "$DIR_NAME"

scripts_dir="$SKILL_DIR/scripts"
if [ ! -d "$scripts_dir" ]; then
    echo "  ℹ No scripts/ directory found"
    echo ""
    echo "Done."
    exit 0
fi

total_issues=0
scripts_checked=0
scripts_skipped=0
tmp_run1=$(mktemp)
tmp_run2=$(mktemp)
tmp_before=$(mktemp)
tmp_after=$(mktemp)
trap 'rm -f "$tmp_run1" "$tmp_run2" "$tmp_before" "$tmp_after"' EXIT INT TERM

echo "── Trap Handler Presence ──"
for script in "$scripts_dir"/*.sh; do
    [ -f "$script" ] || continue
    relpath="${script#"$SKILL_DIR"/}"
    has_trap=$(grep -c '^[[:space:]]*trap ' "$script" 2>/dev/null || true)
    creates_tmp=$(grep -cE '(mktemp|/tmp/)' "$script" 2>/dev/null || true)

    if [ "$creates_tmp" -gt 0 ] && [ "$has_trap" -eq 0 ]; then
        echo "  ✗ $relpath — creates temp files but has no trap handler [MAJOR]"
        total_issues=$((total_issues + 1))
    elif [ "$creates_tmp" -gt 0 ] && [ "$has_trap" -gt 0 ]; then
        echo "  ✓ $relpath — creates temp files, has trap handler"
    fi
done

echo ""
echo "── Output Idempotency ──"
for script in "$scripts_dir"/*.sh; do
    [ -f "$script" ] || continue
    relpath="${script#"$SKILL_DIR"/}"

    case "$(basename "$script")" in
        idempotency_check.sh|staleness_check.sh)
            echo "  $relpath                              [SKIPPED] — bounded default excludes recursive/heavy checks"
            scripts_skipped=$((scripts_skipped + 1))
            continue
            ;;
    esac

    # Only test scripts that accept a skill-directory argument and have
    # a usage line suggesting they take a directory arg.
    if ! grep -qE '(Usage:.*<skill|<skill-dir)' "$script" 2>/dev/null; then
        continue
    fi

    if [ "$FULL_MODE" -eq 0 ] && [ "$scripts_checked" -ge "$MAX_SCRIPTS" ]; then
        scripts_skipped=$((scripts_skipped + 1))
        continue
    fi

    scripts_checked=$((scripts_checked + 1))
    printf '  %-40s ' "$relpath"

    # Skip byte comparison for scripts that are inherently non-deterministic
    # (e.g., timing-based). Scripts opt out with: # idempotency: timing-dependent
    if grep -q '# idempotency: timing-dependent' "$script" 2>/dev/null; then
        echo "[SKIPPED] — timing-dependent (by declaration)"
        continue
    fi

    # Run twice, capture output
    sh "$script" "$SKILL_DIR" > "$tmp_run1" 2>&1 || true
    sh "$script" "$SKILL_DIR" > "$tmp_run2" 2>&1 || true

    if cmp -s "$tmp_run1" "$tmp_run2"; then
        echo "[IDENTICAL]"
    else
        echo "[DIFFERS] — re-run produces different output [BLOCKER]"
        total_issues=$((total_issues + 1))
    fi
done

echo ""
echo "── Residual State ──"
# Check if running scripts leaves files in /tmp/ with the skill name
skill_name=$(basename "$SKILL_DIR")
before_count=$(find /tmp -maxdepth 1 -name "*${skill_name}*" 2>/dev/null | wc -l)
echo "  Temp files matching skill name before: $before_count"

# Run a representative script if available
rep_script="$scripts_dir/surface_check.sh"
if [ -f "$rep_script" ]; then
    sh "$rep_script" "$SKILL_DIR" > /dev/null 2>&1 || true
    after_count=$(find /tmp -maxdepth 1 -name "*${skill_name}*" 2>/dev/null | wc -l)
    new_files=$((after_count - before_count))
    if [ "$new_files" -gt 0 ]; then
        echo "  ✗ $new_files new temp files after running surface_check.sh [MAJOR]"
        total_issues=$((total_issues + 1))
    else
        echo "  ✓ No residual temp files after script run"
    fi
else
    echo "  ℹ No representative script to test residual state"
fi

echo ""
echo "── Summary ──"
echo "  Scripts checked for idempotency: $scripts_checked"
echo "  Scripts skipped: $scripts_skipped"
echo "  Issues found: $total_issues"

echo ""
echo "Done."

if [ "$total_issues" -gt 0 ]; then
    exit 1
fi
