#!/usr/bin/env sh
# skill-auditor — Surface check script.
#
# Usage:
#   surface_check.sh <skill-directory>
#
# Performs mechanical checks on a skill directory:
#   - CRLF line ending detection
#   - Script permission and shebang validation
#   - Skill anatomy verification (SKILL.md, frontmatter)
#   - File size inventory
#
# Output is structured for direct inclusion in audit reports.

set -eu

if [ $# -lt 1 ]; then
    echo "Usage: surface_check.sh <skill-directory>"
    exit 1
fi

case "$1" in
    -h|--help)
        echo "Usage: surface_check.sh <skill-directory>"
        echo ""
        echo "Performs mechanical checks on a skill directory:"
        echo "  - CRLF line ending detection"
        echo "  - Script permission and shebang validation"
        echo "  - Skill anatomy verification (SKILL.md, frontmatter)"
        echo "  - File size inventory"
        exit 0
        ;;
    --*)
        echo "error: unknown option: $1"
        exit 1
        ;;
esac

if [ $# -gt 1 ]; then
    echo "error: unexpected argument: $2"
    exit 1
fi

SKILL_DIR="$1"

if [ ! -d "$SKILL_DIR" ]; then
    echo "error: not a directory: $SKILL_DIR"
    exit 1
fi

echo "═══ Surface Check: $(basename "$SKILL_DIR") ═══"
echo ""

# ---------------------------------------------------------------------------
# 1. Skill anatomy
# ---------------------------------------------------------------------------
echo "── 1. Skill Anatomy ──"

if [ -f "$SKILL_DIR/SKILL.md" ]; then
    echo "  ✓ SKILL.md exists"
    lines=$(wc -l < "$SKILL_DIR/SKILL.md")
    chars=$(wc -c < "$SKILL_DIR/SKILL.md")
    echo "    Size: $lines lines, $chars chars (~$(( chars / 4 )) tokens)"

    if [ "$lines" -gt 500 ]; then
        echo "    ⚠ SKILL.md exceeds 500 line guideline ($lines lines)"
    fi

    # Check for YAML frontmatter
    if head -1 "$SKILL_DIR/SKILL.md" | grep -q '^---'; then
        echo "  ✓ YAML frontmatter present"

        # Check for required fields
        if head -20 "$SKILL_DIR/SKILL.md" | grep -q '^name:'; then
            echo "  ✓ name field present"
        else
            echo "  ✗ name field MISSING in frontmatter"
        fi

        if head -30 "$SKILL_DIR/SKILL.md" | grep -q '^description:'; then
            echo "  ✓ description field present"
        else
            echo "  ✗ description field MISSING in frontmatter"
        fi
    else
        echo "  ✗ YAML frontmatter MISSING (first line is not '---')"
    fi
else
    echo "  ✗ SKILL.md NOT FOUND (required)"
fi

echo ""

# ---------------------------------------------------------------------------
# 2. Directory structure
# ---------------------------------------------------------------------------
echo "── 2. Directory Structure ──"
echo ""

# Show tree (2 levels, with sizes)
if command -v find >/dev/null 2>&1; then
    find "$SKILL_DIR" -maxdepth 3 -not -path '*/target/*' -not -path '*/.git/*' \
        -not -path '*/node_modules/*' -type f 2>/dev/null | \
        while IFS= read -r f; do
            size=$(wc -c < "$f")
            rel="${f#"$SKILL_DIR"/}"
            printf "  %8d  %s\n" "$size" "$rel"
        done | sort -k2 || true
fi

echo ""

# ---------------------------------------------------------------------------
# 3. CRLF detection
# ---------------------------------------------------------------------------
echo "── 3. CRLF Line Ending Check ──"

crlf_count=0
crlf_critical=0
binary_skipped_count=0

# Keep CRLF candidate filters in one place so scan and fix guidance stay aligned.
CRLF_FIND_EXCLUDES="-not -path */target/* -not -path */.git/* -not -name *.lock -not -name *.png -not -name *.jpg -not -name *.woff -not -name *.ttf"

crlf_list=$(mktemp)
script_list=$(mktemp)
shebang_list=$(mktemp)
cleanup_lists() {
    rm -f "$crlf_list" "$script_list" "$shebang_list"
}
trap cleanup_lists EXIT INT TERM

set -f
# Intentionally expand static exclusion flags.
find "$SKILL_DIR" -type f $CRLF_FIND_EXCLUDES 2>/dev/null > "$crlf_list"
set +f

while IFS= read -r file; do
    if [ -s "$file" ] && ! LC_ALL=C grep -Iq . "$file" 2>/dev/null; then
        binary_skipped_count=$((binary_skipped_count + 1))
        continue
    fi

    if tr -d '\r' < "$file" | cmp -s - "$file"; then
        :
    else
        lines_with_cr=$(tr -cd '\r' < "$file" | wc -c)
        basename_f=$(basename "$file")
        relpath="${file#"$SKILL_DIR"/}"

        # Determine severity based on file type
        case "$basename_f" in
            *.sh|*.py)
                echo "  ✗ CRLF [BLOCKER - script]: $relpath ($lines_with_cr lines)"
                crlf_critical=$((crlf_critical + 1))
                ;;
            *)
                # Check if file has a shebang (executable script without extension).
                # Exclude .rs files: Rust's #![...] inner attributes look like shebangs.
                case "$basename_f" in
                    *.rs|*.toml|*.yml|*.yaml|*.json|*.md|*.txt|*.html|*.css|*.js|*.ts)
                        echo "  ⚠ CRLF [MINOR]: $relpath ($lines_with_cr lines)"
                        ;;
                    *)
                        if head -1 "$file" 2>/dev/null | grep -q '^#!/'; then
                            echo "  ✗ CRLF [BLOCKER - script]: $relpath ($lines_with_cr lines)"
                            crlf_critical=$((crlf_critical + 1))
                        else
                            echo "  ⚠ CRLF [MINOR]: $relpath ($lines_with_cr lines)"
                        fi
                        ;;
                esac
                ;;
        esac
        crlf_count=$((crlf_count + 1))
    fi
done < "$crlf_list"

if [ "$crlf_count" -eq 0 ]; then
    echo "  ✓ No CRLF line endings detected"
    if [ "$binary_skipped_count" -gt 0 ]; then
        echo "  ℹ Skipped probable binary files: $binary_skipped_count"
    fi
else
    echo ""
    echo "  Total files with CRLF: $crlf_count ($crlf_critical critical/scripts)"
    if [ "$binary_skipped_count" -gt 0 ]; then
        echo "  Skipped probable binary files: $binary_skipped_count"
    fi
    echo "  Fix (GNU sed):    find \"$SKILL_DIR\" -type f $CRLF_FIND_EXCLUDES -exec sh -c 'for f do LC_ALL=C grep -Iq . \"\$f\" 2>/dev/null || continue; sed -i \"s/\\r\\\$//\" \"\$f\"; done' sh {} +"
    echo "  Fix (BSD/macOS):  find \"$SKILL_DIR\" -type f $CRLF_FIND_EXCLUDES -exec sh -c 'for f do LC_ALL=C grep -Iq . \"\$f\" 2>/dev/null || continue; sed -i \"\" \"s/\\r\\\$//\" \"\$f\"; done' sh {} +"
fi

echo ""

# ---------------------------------------------------------------------------
# 4. Script permissions and shebangs
# ---------------------------------------------------------------------------
echo "── 4. Script Permissions & Shebangs ──"

script_count=0
perm_issues=0

find "$SKILL_DIR" -type f \( -name '*.sh' -o -name '*.py' \) \
    -not -path '*/target/*' -not -path '*/.git/*' \
    2>/dev/null > "$script_list"

while IFS= read -r file; do
    [ -z "$file" ] && continue
    relpath="${file#"$SKILL_DIR"/}"
    script_count=$((script_count + 1))

    # Check execute permission
    if [ ! -x "$file" ]; then
        echo "  ⚠ Not executable: $relpath"
        perm_issues=$((perm_issues + 1))
    fi

    # Check shebang
    shebang=$(head -1 "$file" 2>/dev/null || true)
    if echo "$shebang" | grep -q '^#!/'; then
        # Check for \r in shebang
        if printf '%s' "$shebang" | grep -q "$(printf '\r')"; then
            echo "  ✗ CRLF in shebang [BLOCKER]: $relpath"
        else
            echo "  ✓ $relpath: $shebang"
        fi
    else
        echo "  ⚠ No shebang: $relpath"
    fi
done < "$script_list"

# Also check files without extensions that have shebangs (recursive).
find "$SKILL_DIR" -type f ! -name '*.*' \
    -not -path '*/target/*' -not -path '*/.git/*' -not -path '*/node_modules/*' \
    2>/dev/null > "$shebang_list"

while IFS= read -r file; do
    [ -z "$file" ] && continue
    if head -1 "$file" 2>/dev/null | grep -q '^#!/'; then
        relpath="${file#"$SKILL_DIR"/}"
        script_count=$((script_count + 1))

        if [ ! -x "$file" ]; then
            echo "  ⚠ Not executable: $relpath"
            perm_issues=$((perm_issues + 1))
        fi

        shebang=$(head -1 "$file" 2>/dev/null || true)
        if printf '%s' "$shebang" | grep -q "$(printf '\r')"; then
            echo "  ✗ CRLF in shebang [BLOCKER]: $relpath"
        else
            echo "  ✓ $relpath: $shebang"
        fi
    fi
done < "$shebang_list"

if [ "$script_count" -eq 0 ]; then
    echo "  (no scripts found)"
fi

echo ""

# ---------------------------------------------------------------------------
# 5. Summary
# ---------------------------------------------------------------------------
echo "── Summary ──"
echo "  CRLF files: $crlf_count ($crlf_critical critical)"
echo "  Permission issues: $perm_issues"

if [ "$crlf_critical" -gt 0 ]; then
    echo "  ⚠ BLOCKERS FOUND: $crlf_critical script(s) with CRLF will fail on Linux"
fi

echo ""
echo "Done."
