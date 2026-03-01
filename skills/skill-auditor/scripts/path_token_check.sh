#!/usr/bin/env sh
# skill-auditor — Path token usage check (D4).
#
# Usage:
#   path_token_check.sh <skill-directory>
#
# Checks that internal file references use <skills-file-root>.

set -eu

case "${1-}" in
    -h|--help)
        echo "Usage: path_token_check.sh <skill-directory>"
        echo ""
        echo "Checks that SKILL.md and references use <skills-file-root>"
        echo "instead of hardcoded paths for internal file references."
        exit 0
        ;;
esac

if [ $# -lt 1 ]; then
    echo "Usage: path_token_check.sh <skill-directory>"
    exit 1
fi

SKILL_DIR="$1"
if [ ! -d "$SKILL_DIR" ]; then
    echo "error: not a directory: $SKILL_DIR"
    exit 1
fi

DIR_NAME=$(basename "$SKILL_DIR")
printf '═══ Path Token Usage: %s ═══\n\n' "$DIR_NAME"

issues=0
checked=0
in_code_block=0

tmpfile=$(mktemp)
trap 'rm -f "$tmpfile"' EXIT INT TERM

extract_refs() {
    line="$1"
    root="$2"
    simple_pat="(^|[[:space:]\"])(<skills-file-root>/)?${root}/[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*"
    link_pat="\\]\\((<skills-file-root>/)?${root}/[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*\\)"

    simple_matches=$(printf '%s\n' "$line" | grep -oE "$simple_pat" | sed -E 's/^[[:space:]\"]//' || true)
    link_matches=$(printf '%s\n' "$line" | grep -oE "$link_pat" | sed -E 's/^\]\(//' | sed -E 's/\)$//' || true)

    {
        printf '%s\n' "$simple_matches"
        printf '%s\n' "$link_matches"
    } | sed '/^$/d'
}

find_bare_match() {
    line="$1"
    root="$2"
    bare_match=""
    matches=$(extract_refs "$line" "$root")
    while IFS= read -r match; do
        [ -z "$match" ] && continue
        case "$match" in
            '<skills-file-root>/'*) continue ;;
        esac
        token=${match#'<skills-file-root>/'}
        [ -e "$SKILL_DIR/$token" ] || continue
        bare_match="$token"
        break
    done <<EOF
$matches
EOF
    printf '%s' "$bare_match"
}

find "$SKILL_DIR" -name '*.md' -not -path '*/.git/*' -not -path '*/target/*' \
    -not -path "$SKILL_DIR/tests/*" \
    -not -name 'ARCHITECTURE-PLAN.md' 2>/dev/null | sort > "$tmpfile"

while IFS= read -r mdfile; do
    [ -z "$mdfile" ] && continue
    relpath="${mdfile#"$SKILL_DIR"/}"
    line_num=0
    in_code_block=0

    while IFS= read -r line; do
        line_num=$((line_num + 1))

        # Track fenced code blocks
        case "$line" in
            '```'*) 
                if [ "$in_code_block" -eq 0 ]; then
                    in_code_block=1
                else
                    in_code_block=0
                fi
                continue
                ;;
        esac

        checked=$((checked + 1))

        # Check for bare relative paths to scripts/
        bare_match=$(find_bare_match "$line" "scripts")
        if [ -n "$bare_match" ]; then
            echo "  ⚠ $relpath:$line_num — bare path \"$bare_match\" (missing <skills-file-root> prefix) [MINOR]"
            issues=$((issues + 1))
        fi

        case "$line" in
            '['*) ref_scan=0 ;;
            *) ref_scan=1 ;;
        esac

        if [ "$ref_scan" -eq 1 ]; then
            bare_match=$(find_bare_match "$line" "references")
            if [ -n "$bare_match" ]; then
                echo "  ⚠ $relpath:$line_num — bare path \"$bare_match\" (missing <skills-file-root> prefix) [MINOR]"
                issues=$((issues + 1))
            fi
        fi

        # Check for hardcoded absolute paths
        if printf '%s' "$line" | grep -qE '/(home|Users|opt|usr/local)/.*SKILL\.md'; then
            abs_match=$(printf '%s' "$line" | grep -oE '/[^ ]*SKILL\.md' | head -1)
            echo "  ✗ $relpath:$line_num — hardcoded absolute path \"$abs_match\" [MAJOR]"
            issues=$((issues + 1))
        fi

        # Check for ../ escaping skill dir
        if printf '%s' "$line" | grep -qE '\.\./[a-z]'; then
            if ! printf '%s' "$line" | grep -q 'example\|e\.g\.\|such as'; then
                dot_match=$(printf '%s' "$line" | grep -oE '\.\./[^ )`]*' | head -1)
                echo "  ⚠ $relpath:$line_num — parent traversal \"$dot_match\" [MINOR]"
                issues=$((issues + 1))
            fi
        fi

    done < "$mdfile"
done < "$tmpfile"

echo ""
echo "── Summary ──"
if [ "$issues" -eq 0 ]; then
    echo "  ✓ All path references use <skills-file-root> correctly"
else
    echo "  Issues found: $issues"
fi

echo ""
echo "Done."
