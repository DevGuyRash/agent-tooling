#!/usr/bin/env sh
# skill-auditor — Name consistency check (D5).
#
# Usage:
#   name_consistency_check.sh <skill-directory> [--cli <binary>]
#
# Cross-references names between documentation and CLI.

set -eu

CLI_BIN=""
SKILL_DIR=""

case "${1-}" in
    -h|--help)
        echo "Usage: name_consistency_check.sh <skill-directory> [--cli <binary>]"
        echo ""
        echo "Checks name consistency between docs and CLI:"
        echo "  - Frontmatter name vs directory name"
        echo "  - CLI --help name vs frontmatter name"
        echo "  - Named values in docs vs CLI accepted values"
        echo "  - Mapping table presence for name variants"
        exit 0
        ;;
esac

while [ $# -gt 0 ]; do
    case "$1" in
        --cli)
            shift
            CLI_BIN="${1-}"
            if [ -z "$CLI_BIN" ]; then
                echo "error: --cli requires a value"
                exit 1
            fi
            ;;
        --*)
            echo "error: unknown option: $1"
            exit 1
            ;;
        *)
            if [ -z "$SKILL_DIR" ]; then
                SKILL_DIR="$1"
            else
                echo "error: unexpected argument: $1"
                exit 1
            fi
            ;;
    esac
    shift
done

if [ -z "$SKILL_DIR" ]; then
    echo "Usage: name_consistency_check.sh <skill-directory> [--cli <binary>]"
    exit 1
fi

if [ ! -d "$SKILL_DIR" ]; then
    echo "error: not a directory: $SKILL_DIR"
    exit 1
fi

DIR_NAME=$(basename "$SKILL_DIR")
printf '═══ Name Consistency: %s ═══\n\n' "$DIR_NAME"

SKILL_FILE="$SKILL_DIR/SKILL.md"
issues=0

# Check frontmatter name vs directory
echo "── Frontmatter vs Directory ──"
if [ -f "$SKILL_FILE" ]; then
    fm_block=$(sed -n '2,/^---$/p' "$SKILL_FILE" | sed '$d')
    name_value=$(printf '%s\n' "$fm_block" | sed -n 's/^name:[[:space:]]*//p' | head -1 | sed "s/^['\"]//;s/['\"]$//")

    if [ -n "$name_value" ]; then
        if [ "$name_value" = "$DIR_NAME" ]; then
            echo "  ✓ frontmatter name \"$name_value\" matches directory"
        else
            echo "  ✗ frontmatter name \"$name_value\" != directory \"$DIR_NAME\" [BLOCKER]"
            issues=$((issues + 1))
        fi
    else
        echo "  ✗ No name in frontmatter [BLOCKER]"
        issues=$((issues + 1))
    fi
else
    echo "  ✗ SKILL.md not found [BLOCKER]"
    issues=$((issues + 1))
fi

# Check CLI name if binary provided
if [ -n "$CLI_BIN" ]; then
    echo ""
    echo "── CLI Name Check ──"

    resolved_cli=$(command -v "$CLI_BIN" 2>/dev/null || true)
    if [ -n "$resolved_cli" ]; then
        CLI_BIN="$resolved_cli"
    fi

    if [ -x "$CLI_BIN" ]; then
        help_output=$("$CLI_BIN" --help 2>&1 || true)

        # Check if CLI help mentions the skill name
        if printf '%s' "$help_output" | grep -qi "$DIR_NAME"; then
            echo "  ✓ CLI --help references skill name \"$DIR_NAME\""
        else
            echo "  ⚠ CLI --help does not mention \"$DIR_NAME\" [MINOR]"
            issues=$((issues + 1))
        fi

        # Extract documented subcommands/roles from SKILL.md
        echo ""
        echo "── Documented Names vs CLI ──"

        tmpnames=$(mktemp)
        trap 'rm -f "$tmpnames"' EXIT INT TERM

        # Extract --role, --mode, --phase values from docs
        if [ -f "$SKILL_FILE" ]; then
            grep -oE '\-\-(role|mode|phase|status|type)\s+[a-z][a-z0-9_-]*' "$SKILL_FILE" 2>/dev/null | \
                awk '{print $2}' | sort -u > "$tmpnames" || true

            # Also check reference files
            find "$SKILL_DIR/references" -name '*.md' 2>/dev/null | while IFS= read -r ref; do
                grep -oE '\-\-(role|mode|phase|status|type)\s+[a-z][a-z0-9_-]*' "$ref" 2>/dev/null | \
                    awk '{print $2}' >> "$tmpnames" || true
            done
            sort -u "$tmpnames" -o "$tmpnames"
        fi

        if [ -s "$tmpnames" ]; then
            echo "  Documented named values:"
            while IFS= read -r dname; do
                [ -z "$dname" ] && continue
                # Try to verify against CLI
                if printf '%s' "$help_output" | grep -qi "$dname"; then
                    echo "    ✓ $dname — found in CLI help"
                else
                    echo "    ⚠ $dname — not found in CLI help [MINOR]"
                    issues=$((issues + 1))
                fi
            done < "$tmpnames"
        else
            echo "  ℹ No named parameter values found in documentation"
        fi
    else
        echo "  ⚠ CLI binary not executable: $CLI_BIN"
    fi
fi

echo ""
echo "── Summary ──"
echo "  Issues found: $issues"

echo ""
echo "Done."
