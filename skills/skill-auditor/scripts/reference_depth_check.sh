#!/usr/bin/env sh
# skill-auditor — Reference depth check (D17).
#
# Usage:
#   reference_depth_check.sh <skill-directory>
#
# Checks reference file sizing, nesting, and reachability.

set -eu

extract_reference_links() {
    awk '
        {
            line = $0
            while (match(line, /references\/[a-z0-9_-]+\.md/)) {
                print substr(line, RSTART, RLENGTH)
                line = substr(line, RSTART + RLENGTH)
            }
        }
    ' "$1" 2>/dev/null | sort -u || true
}

case "${1-}" in
    -h|--help)
        echo "Usage: reference_depth_check.sh <skill-directory>"
        echo ""
        echo "Checks reference files for:"
        echo "  - Size (flag >500 lines or >30KB, warn >300 lines without TOC)"
        echo "  - Nesting (reference-to-reference links)"
        echo "  - Reachability from SKILL.md"
        echo "  - TOC presence in large files"
        exit 0
        ;;
esac

if [ $# -lt 1 ]; then
    echo "Usage: reference_depth_check.sh <skill-directory>"
    exit 1
fi

SKILL_DIR="$1"
if [ ! -d "$SKILL_DIR" ]; then
    echo "error: not a directory: $SKILL_DIR"
    exit 1
fi

DIR_NAME=$(basename "$SKILL_DIR")
printf '═══ Reference Depth: %s ═══\n\n' "$DIR_NAME"

SKILL_FILE="$SKILL_DIR/SKILL.md"
REF_DIR="$SKILL_DIR/references"

if [ ! -f "$SKILL_FILE" ]; then
    echo "  ✗ SKILL.md not found"
    echo ""
    echo "Done."
    exit 0
fi

if [ ! -d "$REF_DIR" ]; then
    echo "  ℹ No references/ directory found"
    echo ""
    echo "Done."
    exit 0
fi

echo "── Reference File Sizes ──"
printf "  %-40s %6s %8s %8s\n" "File" "Lines" "Chars" "~Tokens"
printf "  %-40s %6s %8s %8s\n" "----" "-----" "-----" "-------"

oversized=0
total_lines=0
total_chars=0

tmplist=$(mktemp)
trap 'rm -f "$tmplist"' EXIT INT TERM

find "$REF_DIR" -name '*.md' -type f 2>/dev/null | sort > "$tmplist"

while IFS= read -r reffile; do
    [ -z "$reffile" ] && continue
    relpath="${reffile#"$SKILL_DIR"/}"
    lines=$(wc -l < "$reffile" | tr -d ' ')
    chars=$(wc -c < "$reffile" | tr -d ' ')
    tokens=$((chars / 4))
    total_lines=$((total_lines + lines))
    total_chars=$((total_chars + chars))

    marker=""
    if [ "$chars" -gt 30720 ]; then
        marker=" [MAJOR >30KB]"
        oversized=$((oversized + 1))
    elif [ "$lines" -gt 500 ]; then
        marker=" [MINOR >500 lines]"
        oversized=$((oversized + 1))
    fi
    printf "  %-40s %6d %8d %8d%s\n" "$relpath" "$lines" "$chars" "$tokens" "$marker"
done < "$tmplist"

printf "  %-40s %6d %8d %8d\n" "TOTAL" "$total_lines" "$total_chars" "$((total_chars / 4))"

echo ""
echo "── TOC Check (files >300 lines) ──"

toc_issues=0
while IFS= read -r reffile; do
    [ -z "$reffile" ] && continue
    lines=$(wc -l < "$reffile" | tr -d ' ')
    if [ "$lines" -gt 300 ]; then
        relpath="${reffile#"$SKILL_DIR"/}"
        if head -30 "$reffile" | grep -i 'table of contents\|## contents\|^- \[' >/dev/null; then
            echo "  ✓ $relpath ($lines lines) — has TOC"
        else
            echo "  ⚠ $relpath ($lines lines) — missing TOC [MINOR]"
            toc_issues=$((toc_issues + 1))
        fi
    fi
done < "$tmplist"

if [ "$toc_issues" -eq 0 ]; then
    echo "  ✓ All files over 300 lines provide a TOC"
fi

echo ""
echo "── Reachability from SKILL.md ──"

orphaned=0
reachable_refs=$(mktemp)
trap 'rm -f "$tmplist" "$reachable_refs"' EXIT INT TERM

{
    extract_reference_links "$SKILL_FILE"
    while IFS= read -r direct_ref; do
        [ -z "$direct_ref" ] && continue
        direct_path="$SKILL_DIR/$direct_ref"
        [ -f "$direct_path" ] || continue
        extract_reference_links "$direct_path"
    done <<EOF
$(extract_reference_links "$SKILL_FILE")
EOF
} | sort -u > "$reachable_refs"

while IFS= read -r reffile; do
    [ -z "$reffile" ] && continue
    relpath="${reffile#"$SKILL_DIR"/}"
    basename_f=$(basename "$reffile")

    if grep -Fx "$relpath" "$reachable_refs" >/dev/null 2>&1 || grep -Fx "references/$basename_f" "$reachable_refs" >/dev/null 2>&1; then
        echo "  ✓ $relpath — reachable within 2 hops from SKILL.md"
    else
        echo "  ⚠ $relpath — ORPHANED (not reachable within 2 hops from SKILL.md) [MINOR]"
        orphaned=$((orphaned + 1))
    fi
done < "$tmplist"

echo ""
echo "── Nesting Check (max 3 hops from SKILL.md) ──"

nesting_issues=0

# Build a link map: for each reference file, record which other references it links to
# Then trace max depth from SKILL.md. D17 rule: chains >3 hops are BLOCKER,
# =3 hops are fine, any reference-to-reference link by itself is acceptable.

# Helper: resolve references linked from a given file
get_ref_links() {
    extract_reference_links "$1"
}

# Trace depth from SKILL.md (hop 0) through reference chains
# hop 1 = SKILL.md -> ref, hop 2 = ref -> ref, hop 3 = ref -> ref -> ref
max_depth=0

# First collect all direct links from SKILL.md (hop 1)
hop1_files=""
for target in $(get_ref_links "$SKILL_FILE"); do
    target_path="$SKILL_DIR/$target"
    [ -f "$target_path" ] && hop1_files="$hop1_files $target_path"
done

# Trace hop 2: references linked from hop-1 files
hop2_files=""
for h1 in $hop1_files; do
    h1_base=$(basename "$h1")
    for target in $(get_ref_links "$h1"); do
        target_path="$SKILL_DIR/$target"
        target_base=$(basename "$target_path")
        [ "$target_base" = "$h1_base" ] && continue
        [ -f "$target_path" ] || continue
        hop2_files="$hop2_files $target_path"
        [ "$max_depth" -lt 2 ] && max_depth=2
    done
done

# Trace hop 3: references linked from hop-2 files
hop3_files=""
for h2 in $hop2_files; do
    h2_base=$(basename "$h2")
    for target in $(get_ref_links "$h2"); do
        target_path="$SKILL_DIR/$target"
        target_base=$(basename "$target_path")
        [ "$target_base" = "$h2_base" ] && continue
        [ -f "$target_path" ] || continue
        hop3_files="$hop3_files $target_path"
        [ "$max_depth" -lt 3 ] && max_depth=3
    done
done

# Check for hop 4+ (exceeds the 3-hop cap)
for h3 in $hop3_files; do
    h3_base=$(basename "$h3")
    for target in $(get_ref_links "$h3"); do
        target_path="$SKILL_DIR/$target"
        target_base=$(basename "$target_path")
        [ "$target_base" = "$h3_base" ] && continue
        [ -f "$target_path" ] || continue
        h3_rel="${h3#"$SKILL_DIR"/}"
        echo "  ✗ $h3_rel links to $target (chain exceeds 3 hops from SKILL.md) [BLOCKER]"
        nesting_issues=$((nesting_issues + 1))
    done
done

if [ "$nesting_issues" -eq 0 ]; then
    echo "  ✓ No reference chains exceed 3 hops (max depth found: $max_depth)"
fi

echo ""
echo "── Summary ──"
echo "  Oversized files: $oversized"
echo "  Orphaned files: $orphaned"
echo "  Nesting issues: $nesting_issues"
echo "  TOC issues: $toc_issues"

echo ""
echo "Done."
