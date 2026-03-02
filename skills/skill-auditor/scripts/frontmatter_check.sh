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

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=lib/frontmatter.sh
. "$SCRIPT_DIR/lib/frontmatter.sh"

DIR_NAME=$(basename "$SKILL_DIR")
printf '═══ Frontmatter Validity: %s ═══\n\n' "$DIR_NAME"

if ! fm_block=$(sa_load_frontmatter "$SKILL_FILE"); then
    echo "  ✗ YAML frontmatter MISSING — first line is not '---' [BLOCKER]"
    echo ""
    echo "Done."
    exit 0
fi
echo "  ✓ YAML frontmatter delimiter found"

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
    if printf '%s' "$name_value" | grep -E '^[a-z0-9]([a-z0-9-]*[a-z0-9])?$' >/dev/null; then
        echo "  ✓ name format valid (lowercase, hyphens)"
    else
        echo "  ✗ name format invalid — must be lowercase alphanumeric + hyphens [MAJOR]"
    fi
    if printf '%s' "$name_value" | grep -- '--' >/dev/null; then
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
if ! desc_text=$(sa_frontmatter_extract_description "$fm_block"); then
    echo "  ✗ description field MISSING in frontmatter [BLOCKER]"
else
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
        if printf '%s' "$desc_text" | grep -i 'use when\|use .* when\|use for\|use .* to' >/dev/null; then
            echo "  ✓ description contains trigger conditions"
        else
            echo "  ⚠ description lacks 'Use when' trigger conditions [MAJOR]"
        fi
    fi
fi

echo ""
echo "Done."
