#!/usr/bin/env sh
# skill-auditor — Cold-start readiness check (D11).
#
# Usage:
#   cold_start_check.sh <skill-directory>
#
# Checks that a skill can run without compilation or installation.

set -eu

case "${1-}" in
    -h|--help)
        echo "Usage: cold_start_check.sh <skill-directory>"
        echo ""
        echo "Checks cold-start readiness:"
        echo "  - Scripts run without compilation"
        echo "  - Time first execution of each script"
        echo "  - Check for pre-built binaries"
        echo "  - Check compatibility field for deps"
        exit 0
        ;;
esac

if [ $# -lt 1 ]; then
    echo "Usage: cold_start_check.sh <skill-directory>"
    exit 1
fi

SKILL_DIR="$1"
if [ ! -d "$SKILL_DIR" ]; then
    echo "error: not a directory: $SKILL_DIR"
    exit 1
fi

DIR_NAME=$(basename "$SKILL_DIR")
printf '═══ Cold-Start Readiness: %s ═══\n\n' "$DIR_NAME"

echo "── Build Requirements ──"

# Check for compiled source directories
has_build=0
for builddir in Cargo.toml package.json go.mod setup.py pyproject.toml; do
    if [ -f "$SKILL_DIR/$builddir" ]; then
        echo "  ⚠ Build manifest found: $builddir"
        has_build=1
    fi
done

if [ -d "$SKILL_DIR/src" ] && [ -f "$SKILL_DIR/Cargo.toml" ]; then
    echo "  ⚠ Rust source directory found — build step required"
    # Check for pre-built binary
    if find "$SKILL_DIR" -type f -executable -not -name '*.sh' -not -name '*.py' \
        -not -path '*/target/*' -not -path '*/.git/*' 2>/dev/null | grep -q .; then
        echo "  ✓ Pre-built binary found alongside source"
    else
        echo "  ✗ No pre-built binary — agents must compile from source [MAJOR]"
    fi
fi

if [ "$has_build" -eq 0 ]; then
    echo "  ✓ No build manifests — interpreted scripts only"
fi

echo ""
echo "── Script Execution Timing ──"

script_count=0
slow_count=0

tmplist=$(mktemp)
trap 'rm -f "$tmplist"' EXIT INT TERM

find "$SKILL_DIR/scripts" -type f \( -name '*.sh' -o -name '*.py' \) 2>/dev/null | sort > "$tmplist" 2>/dev/null || true

while IFS= read -r script; do
    [ -z "$script" ] && continue
    relpath="${script#"$SKILL_DIR"/}"
    script_count=$((script_count + 1))

    if [ ! -x "$script" ]; then
        echo "  ⚠ $relpath — not executable, cannot time [MINOR]"
        continue
    fi

    # Time --help execution
    start_ms=$(date +%s%N 2>/dev/null || date +%s)
    "$script" --help >/dev/null 2>&1 || true
    end_ms=$(date +%s%N 2>/dev/null || date +%s)

    # Calculate duration (handle systems without %N)
    if [ ${#start_ms} -gt 10 ]; then
        duration_ms=$(( (end_ms - start_ms) / 1000000 ))
        printf "  ✓ %-40s %dms\n" "$relpath" "$duration_ms"
        if [ "$duration_ms" -gt 5000 ]; then
            echo "    ✗ Exceeds 5s cold-start threshold [MAJOR]"
            slow_count=$((slow_count + 1))
        fi
    else
        duration_s=$((end_ms - start_ms))
        printf "  ✓ %-40s %ds\n" "$relpath" "$duration_s"
        if [ "$duration_s" -gt 5 ]; then
            echo "    ✗ Exceeds 5s cold-start threshold [MAJOR]"
            slow_count=$((slow_count + 1))
        fi
    fi
done < "$tmplist"

if [ "$script_count" -eq 0 ]; then
    echo "  (no scripts found in scripts/)"
fi

echo ""
echo "── Compatibility Field ──"

SKILL_FILE="$SKILL_DIR/SKILL.md"
if [ -f "$SKILL_FILE" ]; then
    fm_block=$(sed -n '2,/^---$/p' "$SKILL_FILE" | sed '$d')
    if printf '%s\n' "$fm_block" | grep -q '^compatibility:'; then
        echo "  ✓ compatibility field present in frontmatter"
    else
        if [ "$has_build" -eq 1 ]; then
            echo "  ⚠ No compatibility field but build deps exist [MINOR]"
        else
            echo "  ℹ No compatibility field (OK if no external deps)"
        fi
    fi
fi

echo ""
echo "── Summary ──"
echo "  Scripts timed: $script_count"
echo "  Slow scripts (>5s): $slow_count"
echo "  Build required: $([ "$has_build" -eq 1 ] && echo "yes" || echo "no")"

echo ""
echo "Done."
