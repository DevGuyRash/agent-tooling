#!/usr/bin/env sh
# skill-auditor — EARS compliance check (D14).
#
# Usage:
#   ears_check.sh <skill-directory>
#
# Analyzes EARS keyword coverage, bare imperatives, and vague directives.

set -eu

case "${1-}" in
    -h|--help)
        echo "Usage: ears_check.sh <skill-directory>"
        echo ""
        echo "Analyzes skill files for EARS compliance:"
        echo "  - Directive keywords (SHALL, SHOULD, MAY, MUST)"
        echo "  - Conditional keywords (WHEN, IF, WHILE, UNTIL, THEN)"
        echo "  - Bare imperative detection"
        echo "  - Vague directive detection"
        echo "  - Per-file and aggregate EARS coverage"
        exit 0
        ;;
esac

if [ $# -lt 1 ]; then
    echo "Usage: ears_check.sh <skill-directory>"
    exit 1
fi

SKILL_DIR="$1"
if [ ! -d "$SKILL_DIR" ]; then
    echo "error: not a directory: $SKILL_DIR"
    exit 1
fi

DIR_NAME=$(basename "$SKILL_DIR")
printf '═══ EARS Compliance: %s ═══\n\n' "$DIR_NAME"

total_directive=0
total_conditional=0
total_bare=0
total_vague=0

tmplist=$(mktemp)
tmpvague=$(mktemp)
tmpbare=$(mktemp)
trap 'rm -f "$tmplist" "$tmpvague" "$tmpbare"' EXIT INT TERM

find "$SKILL_DIR" -name '*.md' -not -path '*/.git/*' -not -path '*/target/*' \
    -not -path "$SKILL_DIR/tests/*" \
    -not -name 'ARCHITECTURE-PLAN.md' 2>/dev/null | sort > "$tmplist"

echo "── Per-File Breakdown ──"
printf "  %-40s %5s %5s %5s %5s %6s\n" "File" "Dir" "Cond" "Bare" "Vague" "Cover"
printf "  %-40s %5s %5s %5s %5s %6s\n" "----" "---" "----" "----" "-----" "-----"

while IFS= read -r mdfile; do
    [ -z "$mdfile" ] && continue
    relpath="${mdfile#"$SKILL_DIR"/}"
    in_code=0
    file_directive=0
    file_conditional=0
    file_bare=0
    file_vague=0
    line_num=0

    while IFS= read -r line; do
        line_num=$((line_num + 1))

        # Track code blocks
        case "$line" in
            '```'*)
                if [ "$in_code" -eq 0 ]; then in_code=1; else in_code=0; fi
                continue
                ;;
        esac
        [ "$in_code" -eq 1 ] && continue

        # Skip empty lines and headings
        case "$line" in
            ""|\#*|\|*|"---"*|"==="*) continue ;;
        esac

        has_directive=0
        has_conditional=0

        # Check for directive keywords (case-sensitive for EARS)
        if printf '%s' "$line" | grep -E '\bSHALL\b|\bSHOULD\b|\bMUST\b|\bMAY\b' >/dev/null; then
            has_directive=1
            file_directive=$((file_directive + 1))
        fi

        # Check for conditional keywords
        if printf '%s' "$line" | grep -E '\bWHEN\b|\bIF\b|\bWHILE\b|\bUNTIL\b|\bTHEN\b' >/dev/null; then
            has_conditional=1
            file_conditional=$((file_conditional + 1))
        fi

        # Vague directives
        if printf '%s' "$line" | grep -iE 'make sure|ensure that|try to|be careful|consider |remember to' >/dev/null; then
            file_vague=$((file_vague + 1))
            printf '%s:%d: %s\n' "$relpath" "$line_num" "$line" >> "$tmpvague"
        fi

        # Bare imperatives (starts with verb, no EARS keywords)
        if [ "$has_directive" -eq 0 ] && [ "$has_conditional" -eq 0 ]; then
            # Strip list markers
            stripped=$(printf '%s' "$line" | sed 's/^[[:space:]]*[-*0-9.]*//' | sed 's/^[[:space:]]*//')
            first_word=$(printf '%s' "$stripped" | awk '{print tolower($1)}')
            case "$first_word" in
                run|execute|check|verify|test|create|build|write|read|open|close|\
                delete|remove|add|update|set|get|find|search|scan|measure|compare|\
                evaluate|produce|generate|compile|install|configure|deploy|validate|\
                start|stop|map|list|identify|follow|record|note|use|fill|save|\
                spawn|dispatch|collect|extract|calculate|report)
                    file_bare=$((file_bare + 1))
                    printf '%s:%d: %s\n' "$relpath" "$line_num" "$stripped" >> "$tmpbare"
                    ;;
            esac
        fi

    done < "$mdfile"

    # Calculate coverage for this file
    total_ears=$((file_directive + file_conditional))
    total_all=$((total_ears + file_bare + file_vague))
    if [ "$total_all" -gt 0 ]; then
        coverage=$((total_ears * 100 / total_all))
    else
        coverage=0
    fi

    printf "  %-40s %5d %5d %5d %5d %5d%%\n" "$relpath" "$file_directive" "$file_conditional" "$file_bare" "$file_vague" "$coverage"

    total_directive=$((total_directive + file_directive))
    total_conditional=$((total_conditional + file_conditional))
    total_bare=$((total_bare + file_bare))
    total_vague=$((total_vague + file_vague))
done < "$tmplist"

# Aggregate
grand_ears=$((total_directive + total_conditional))
grand_all=$((grand_ears + total_bare + total_vague))
if [ "$grand_all" -gt 0 ]; then
    agg_coverage=$((grand_ears * 100 / grand_all))
else
    agg_coverage=0
fi

echo ""
echo "── Summary ──"
echo "  Directive lines (SHALL/SHOULD/MAY/MUST): $total_directive"
echo "  Conditional lines (WHEN/IF/WHILE/UNTIL/THEN): $total_conditional"
echo "  Bare imperatives (no EARS keyword): $total_bare"
echo "  Vague directives: $total_vague"
echo "  EARS coverage: ${agg_coverage}%"

if [ "$agg_coverage" -ge 70 ]; then
    echo "  Rating: HIGH"
elif [ "$agg_coverage" -ge 40 ]; then
    echo "  Rating: MODERATE"
else
    echo "  Rating: LOW [MAJOR]"
fi

# Top vague directives
if [ -s "$tmpvague" ]; then
    echo ""
    echo "── Top Vague Directives ──"
    head -5 "$tmpvague" | while IFS= read -r entry; do
        echo "  $entry"
    done
fi

# Top bare imperatives
if [ -s "$tmpbare" ]; then
    echo ""
    echo "── Top Bare Imperatives ──"
    head -5 "$tmpbare" | while IFS= read -r entry; do
        echo "  $entry"
    done
fi

echo ""
echo "Done."
