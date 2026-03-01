#!/usr/bin/env sh
# skill-auditor — Frontmatter validity check (D2).
#
# Usage:
#   frontmatter_check.sh <skill-directory>
#
# Checks SKILL.md frontmatter for spec compliance.

set -eu

case "${1-}" in
    -h|--help)
        echo "Usage: frontmatter_check.sh <skill-directory>"
        echo ""
        echo "Checks SKILL.md frontmatter for spec compliance:"
        echo "  - YAML frontmatter present and delimited"
        echo "  - name matches directory, lowercase, hyphens, <=64 chars"
        echo "  - description present, <=1024 chars, trigger conditions"
        exit 0
        ;;
esac

if [ $# -lt 1 ]; then
    echo "Usage: frontmatter_check.sh <skill-directory>"
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
printf '═══ Frontmatter Validity: %s ═══\n\n' "$DIR_NAME"

first_line=$(head -1 "$SKILL_FILE")
if [ "$first_line" != "---" ]; then
    echo "  ✗ YAML frontmatter MISSING — first line is not '---' [BLOCKER]"
    echo ""
    echo "Done."
    exit 0
fi
echo "  ✓ YAML frontmatter delimiter found"

fm_block=$(sed -n '2,/^---$/p' "$SKILL_FILE" | sed '$d')
if [ -z "$fm_block" ]; then
    echo "  ✗ Frontmatter block is empty or malformed [BLOCKER]"
    echo ""
    echo "Done."
    exit 0
fi

echo ""
echo "── Name Field ──"
name_value=$(printf '%s\n' "$fm_block" | sed -n 's/^name:[[:space:]]*//p' | head -1)
if [ -z "$name_value" ]; then
    echo "  ✗ name field MISSING in frontmatter [BLOCKER]"
else
    name_value=$(printf '%s' "$name_value" | sed "s/^['\"]//;s/['\"]$//")
    name_len=$(printf '%s' "$name_value" | wc -c | tr -d ' ')
    if [ "$name_value" = "$DIR_NAME" ]; then
        echo "  ✓ name \"$name_value\" matches directory"
    else
        echo "  ✗ name \"$name_value\" does NOT match directory \"$DIR_NAME\" [MAJOR]"
    fi
    if printf '%s' "$name_value" | grep -qE '^[a-z0-9]([a-z0-9-]*[a-z0-9])?$'; then
        echo "  ✓ name format valid (lowercase, hyphens)"
    else
        echo "  ✗ name format invalid — must be lowercase alphanumeric + hyphens [MAJOR]"
    fi
    if printf '%s' "$name_value" | grep -q -- '--'; then
        echo "  ✗ name contains consecutive hyphens (--) [MAJOR]"
    fi
    if [ "$name_len" -gt 64 ]; then
        echo "  ✗ name exceeds 64 chars ($name_len chars) [MAJOR]"
    else
        echo "  ✓ name length OK ($name_len chars)"
    fi
fi

echo ""
echo "── Description Field ──"
desc_line=$(printf '%s\n' "$fm_block" | grep -n '^description:' | head -1)
if [ -z "$desc_line" ]; then
    echo "  ✗ description field MISSING in frontmatter [BLOCKER]"
else
    desc_start=$(printf '%s' "$desc_line" | cut -d: -f1)
    desc_raw=$(printf '%s\n' "$fm_block" | sed -n "${desc_start}p" | sed 's/^description:[[:space:]]*//')
    case "$desc_raw" in
        ">-"|">"|"|"|"|-")
            desc_text=$(printf '%s\n' "$fm_block" | tail -n +"$((desc_start + 1))" | \
                while IFS= read -r cline; do
                    case "$cline" in
                        "  "*|"	"*) printf '%s ' "$(printf '%s' "$cline" | sed 's/^[[:space:]]*//')" ;;
                        *) break ;;
                    esac
                done)
            ;;
        *)
            desc_text="$desc_raw"
            ;;
    esac
    desc_text=$(printf '%s' "$desc_text" | sed "s/^['\"]//;s/['\"]$//")
    desc_chars=$(printf '%s' "$desc_text" | wc -c | tr -d ' ')
    desc_words=$(printf '%s' "$desc_text" | wc -w | tr -d ' ')
    if [ "$desc_chars" -eq 0 ]; then
        echo "  ✗ description is empty [BLOCKER]"
    else
        echo "  ✓ description present ($desc_chars chars, ~$desc_words words)"
        if [ "$desc_chars" -gt 1024 ]; then
            echo "  ✗ description exceeds 1024 chars ($desc_chars chars) [MAJOR]"
        else
            echo "  ✓ description within 1024 char limit"
        fi
        if [ "$desc_words" -lt 30 ]; then
            echo "  ⚠ description has fewer than 30 words ($desc_words) — may be too brief [MINOR]"
        fi
        if printf '%s' "$desc_text" | grep -qi 'use when\|use .* when\|use for\|use .* to'; then
            echo "  ✓ description contains trigger conditions"
        else
            echo "  ⚠ description lacks 'Use when' trigger conditions [MAJOR]"
        fi
    fi
fi

echo ""
echo "Done."
