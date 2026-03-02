#!/usr/bin/env sh
# skill-auditor — Prompt complexity analysis (D15).
#
# Usage:
#   prompt_complexity_check.sh <skill-directory>
#
# Measures cognitive load dimensions across skill files.

set -eu

case "${1-}" in
    -h|--help)
        echo "Usage: prompt_complexity_check.sh <skill-directory>"
        echo ""
        echo "Analyzes prompt complexity across skill files:"
        echo "  - Conditional density (conditionals per paragraph)"
        echo "  - Negation density (SHALL NOT / MUST NOT / do NOT)"
        echo "  - Cross-reference count"
        echo "  - Placeholder variable count"
        echo "  - Aggregate complexity score"
        exit 0
        ;;
esac

if [ $# -lt 1 ]; then
    echo "Usage: prompt_complexity_check.sh <skill-directory>"
    exit 1
fi

SKILL_DIR="$1"
if [ ! -d "$SKILL_DIR" ]; then
    echo "error: not a directory: $SKILL_DIR"
    exit 1
fi

DIR_NAME=$(basename "$SKILL_DIR")
printf '═══ Prompt Complexity: %s ═══\n\n' "$DIR_NAME"

tmplist=$(mktemp)
trap 'rm -f "$tmplist"' EXIT INT TERM

find "$SKILL_DIR" -name '*.md' -not -path '*/.git/*' -not -path '*/target/*' \
    -not -name 'ARCHITECTURE-PLAN.md' 2>/dev/null | sort > "$tmplist"

echo "── Per-File Metrics ──"
printf "  %-40s %5s %5s %5s %5s %5s %6s\n" "File" "Cond" "Para" "Neg" "Xref" "Vars" "Score"
printf "  %-40s %5s %5s %5s %5s %5s %6s\n" "----" "----" "----" "---" "----" "----" "-----"

grand_cond=0
grand_para=0
grand_neg=0
grand_xref=0
grand_vars=0

while IFS= read -r mdfile; do
    [ -z "$mdfile" ] && continue
    relpath="${mdfile#"$SKILL_DIR"/}"
    in_code=0

    cond=0
    para=1
    neg=0
    xref=0
    vars=0
    prev_blank=0

    while IFS= read -r line; do
        # Track code blocks
        case "$line" in
            '```'*)
                if [ "$in_code" -eq 0 ]; then in_code=1; else in_code=0; fi
                continue
                ;;
        esac
        [ "$in_code" -eq 1 ] && continue

        # Count paragraphs (blank line separators)
        if [ -z "$line" ]; then
            if [ "$prev_blank" -eq 0 ]; then
                para=$((para + 1))
            fi
            prev_blank=1
            continue
        fi
        prev_blank=0

        # Conditional keywords
        cond_hit=$(printf '%s\n' "$line" | awk '
            {
                c = 0
                for (i = 1; i <= NF; i++) {
                    token = $i
                    gsub(/^[^A-Za-z]+|[^A-Za-z]+$/, "", token)
                    if (token == "WHEN" || token == "IF" || token == "WHILE" || token == "UNTIL" || token == "THEN") {
                        c++
                    }
                }
                print c + 0
            }
        ')
        cond=$((cond + cond_hit))

        # Negation keywords
        neg_hit=$(printf '%s\n' "$line" | awk '
            {
                l = tolower($0)
                c = 0
                c += gsub(/shall not/, "&", l)
                c += gsub(/must not/, "&", l)
                c += gsub(/should not/, "&", l)
                c += gsub(/do not/, "&", l)
                c += gsub(/does not/, "&", l)
                c += gsub(/will not/, "&", l)
                c += gsub(/cannot/, "&", l)
                print c + 0
            }
        ')
        neg=$((neg + neg_hit))

        # Cross-references
        xref_hit=$(printf '%s\n' "$line" | awk '{ c = gsub(/<skills-file-root>/, "&"); print c + 0 }')
        xref=$((xref + xref_hit))

        # Placeholder variables
        vars_hit=$(printf '%s\n' "$line" | awk '{ c = gsub(/<[A-Z][A-Z_-]+>|\$[A-Z_][A-Z0-9_]*|\{[A-Z_]+\}/, "&"); print c + 0 }')
        vars=$((vars + vars_hit))

    done < "$mdfile"

    # Calculate score (0-100)
    if [ "$para" -gt 0 ]; then
        density=$((cond * 10 / para))
    else
        density=0
    fi

    total_directives=$((cond + neg))
    if [ "$total_directives" -gt 0 ]; then
        neg_pct=$((neg * 100 / total_directives))
    else
        neg_pct=0
    fi

    # Weighted score: higher = more complex.
    # Cross-reference counts are reported, but excluded from score because
    # <skills-file-root> usage is mandatory for compliant skills.
    score=$((density * 3 + neg_pct / 5 + vars * 3))
    if [ "$score" -gt 100 ]; then
        score=100
    fi

    printf "  %-40s %5d %5d %5d %5d %5d %5d\n" "$relpath" "$cond" "$para" "$neg" "$xref" "$vars" "$score"

    grand_cond=$((grand_cond + cond))
    grand_para=$((grand_para + para))
    grand_neg=$((grand_neg + neg))
    grand_xref=$((grand_xref + xref))
    grand_vars=$((grand_vars + vars))
done < "$tmplist"

# Aggregate
if [ "$grand_para" -gt 0 ]; then
    agg_density=$((grand_cond * 10 / grand_para))
else
    agg_density=0
fi

agg_total=$((grand_cond + grand_neg))
if [ "$agg_total" -gt 0 ]; then
    agg_neg_pct=$((grand_neg * 100 / agg_total))
else
    agg_neg_pct=0
fi

agg_score=$((agg_density * 3 + agg_neg_pct / 5 + grand_vars * 3))
if [ "$agg_score" -gt 100 ]; then
    agg_score=100
fi

echo ""
echo "── Aggregate ──"
echo "  Total conditionals: $grand_cond"
echo "  Total paragraphs: $grand_para"
printf "  Conditional density: %d.%d/para\n" "$((agg_density / 10))" "$((agg_density % 10))"
echo "  Negation density: ${agg_neg_pct}%"
echo "  Cross-references: $grand_xref"
echo "  Placeholder variables: $grand_vars"
echo "  Weighted complexity score: ${agg_score}/100"

if [ "$agg_score" -le 30 ]; then
    echo "  Rating: LOW"
elif [ "$agg_score" -le 60 ]; then
    echo "  Rating: MODERATE"
else
    echo "  Rating: HIGH [MAJOR]"
fi

echo ""
echo "Done."
