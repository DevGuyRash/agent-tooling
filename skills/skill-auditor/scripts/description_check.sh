#!/usr/bin/env sh
# skill-auditor — Description quality check (D3).
#
# Usage:
#   description_check.sh <skill-directory>
#
# Deterministic portion of description quality analysis.

set -eu

case "${1-}" in
    -h|--help)
        echo "Usage: description_check.sh <skill-directory>"
        echo ""
        echo "Checks SKILL.md description field for quality signals:"
        echo "  - Trigger conditions (Use when ...)"
        echo "  - Action verb count"
        echo "  - Word count range (30-120)"
        echo "  - Vague filler detection"
        exit 0
        ;;
esac

if [ $# -lt 1 ]; then
    echo "Usage: description_check.sh <skill-directory>"
    exit 1
fi

SKILL_DIR="$1"
if [ ! -d "$SKILL_DIR" ]; then
    echo "error: not a directory: $SKILL_DIR"
    exit 1
fi

SKILL_FILE="$SKILL_DIR/SKILL.md"
if [ ! -f "$SKILL_FILE" ]; then
    echo "error: SKILL.md not found in $SKILL_DIR"
    exit 1
fi

DIR_NAME=$(basename "$SKILL_DIR")
printf '═══ Description Quality: %s ═══\n\n' "$DIR_NAME"

# Extract frontmatter
fm_block=$(sed -n '2,/^---$/p' "$SKILL_FILE" | sed '$d')
if [ -z "$fm_block" ]; then
    echo "  ✗ No frontmatter found [BLOCKER]"
    echo ""
    echo "Done."
    exit 0
fi

# Extract description text
desc_line=$(printf '%s\n' "$fm_block" | grep -n '^description:' | head -1)
if [ -z "$desc_line" ]; then
    echo "  ✗ description field MISSING [BLOCKER]"
    echo ""
    echo "Done."
    exit 0
fi

desc_start=$(printf '%s' "$desc_line" | cut -d: -f1)
desc_raw=$(printf '%s\n' "$fm_block" | sed -n "${desc_start}p" | sed 's/^description:[[:space:]]*//')
case "$desc_raw" in
    ">-"|">"|"|"|"|-")
        desc_text=$(printf '%s\n' "$fm_block" | tail -n +"$((desc_start + 1))" | \
            while IFS= read -r cline; do
                case "$cline" in
                    "  "*) printf '%s ' "$(printf '%s' "$cline" | sed 's/^[[:space:]]*//')" ;;
                    *) break ;;
                esac
            done)
        ;;
    *)
        desc_text="$desc_raw"
        ;;
esac
desc_text=$(printf '%s' "$desc_text" | sed "s/^['\"]//;s/['\"]$//")

if [ -z "$desc_text" ]; then
    echo "  ✗ description is empty [BLOCKER]"
    echo ""
    echo "Done."
    exit 0
fi

desc_words=$(printf '%s' "$desc_text" | wc -w | tr -d ' ')
desc_chars=$(printf '%s' "$desc_text" | wc -c | tr -d ' ')

echo "── Metrics ──"
echo "  Words: $desc_words"
echo "  Characters: $desc_chars"

# Word count range
if [ "$desc_words" -lt 30 ]; then
    echo "  ✗ Too brief (< 30 words) [MAJOR]"
elif [ "$desc_words" -gt 120 ]; then
    echo "  ⚠ Verbose (> 120 words) — may overwhelm trigger matching [MINOR]"
else
    echo "  ✓ Word count in range (30-120)"
fi

echo ""
echo "── Trigger Conditions ──"

# Count trigger patterns like (1), (2), etc.
trigger_count=$(printf '%s' "$desc_text" | grep -oE '\([0-9]+\)' | wc -l | tr -d ' ')
if printf '%s' "$desc_text" | grep -qi 'use when\|use .* when'; then
    echo "  ✓ Contains 'Use when' trigger phrase"
else
    echo "  ✗ Missing 'Use when' trigger phrase [MAJOR]"
fi

if [ "$trigger_count" -ge 2 ]; then
    echo "  ✓ Contains $trigger_count numbered trigger conditions"
else
    echo "  ⚠ Few or no numbered trigger conditions ($trigger_count found) [MINOR]"
fi

echo ""
echo "── Action Verbs ──"

verb_count=0
for verb in generate validate create build review test analyze audit check deploy configure scaffold measure evaluate produce extract install; do
    if printf '%s' "$desc_text" | grep -qi "\b${verb}"; then
        verb_count=$((verb_count + 1))
    fi
done

if [ "$verb_count" -ge 3 ]; then
    echo "  ✓ $verb_count distinct action verbs found"
elif [ "$verb_count" -ge 1 ]; then
    echo "  ⚠ Only $verb_count action verb(s) — consider adding more [MINOR]"
else
    echo "  ✗ No action verbs detected [MAJOR]"
fi

echo ""
echo "── Vague Filler ──"

vague_count=0
for phrase in "helps with" "various tasks" "and more" "etc" "things" "stuff"; do
    if printf '%s' "$desc_text" | grep -qi "$phrase"; then
        echo "  ⚠ Vague filler: \"$phrase\" [MINOR]"
        vague_count=$((vague_count + 1))
    fi
done

if [ "$vague_count" -eq 0 ]; then
    echo "  ✓ No vague filler detected"
fi

echo ""
echo "Done."
