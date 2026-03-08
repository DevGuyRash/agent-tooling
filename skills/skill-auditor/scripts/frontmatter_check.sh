#!/usr/bin/env sh

set -eu

FORMAT=text

usage() {
    cat <<'EOF'
Usage: frontmatter_check.sh <skill-directory> [--format json]

Validate SKILL.md frontmatter for:
  - YAML frontmatter delimiters
  - name presence and directory match
  - name format constraints
  - description presence and trigger wording
EOF
}

json_escape() {
    printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'
}

append_issue() {
    code="$1"
    severity="$2"
    message="$3"
    if [ "$ISSUE_COUNT" -gt 0 ]; then
        ISSUE_JSON="$ISSUE_JSON,"
    fi
    ISSUE_JSON="$ISSUE_JSON{\"code\":\"$(json_escape "$code")\",\"severity\":\"$(json_escape "$severity")\",\"message\":\"$(json_escape "$message")\"}"
    ISSUE_COUNT=$((ISSUE_COUNT + 1))
}

load_frontmatter() {
    skill_file="$1"
    first_line=$(head -1 "$skill_file" 2>/dev/null || true)
    if [ "$first_line" != "---" ]; then
        return 1
    fi

    closing_line=$(awk 'NR > 1 && $0 == "---" { print NR; exit }' "$skill_file")
    [ -n "$closing_line" ] || return 1
    sed -n "2,$((closing_line - 1))p" "$skill_file"
}

extract_description() {
    fm_block="$1"
    desc_line=$(printf '%s\n' "$fm_block" | grep -n '^description:' | head -1 || true)
    [ -n "$desc_line" ] || return 1

    desc_start=$(printf '%s' "$desc_line" | cut -d: -f1)
    desc_raw=$(printf '%s\n' "$fm_block" | sed -n "${desc_start}p" | sed 's/^description:[[:space:]]*//')

    case "$desc_raw" in
        ">-"|">"|"|"|"|-")
            desc_text=$(
                printf '%s\n' "$fm_block" | tail -n +"$((desc_start + 1))" | while IFS= read -r line; do
                    case "$line" in
                        "  "*|"	"*) printf '%s ' "$(printf '%s' "$line" | sed 's/^[[:space:]]*//')" ;;
                        *) break ;;
                    esac
                done
            )
            ;;
        *)
            desc_text="$desc_raw"
            ;;
    esac

    printf '%s' "$desc_text" | sed "s/^['\"]//;s/['\"]$//"
}

print_text() {
    if [ "$ISSUE_COUNT" -eq 0 ]; then
        echo "PASS frontmatter_check"
        echo "name=$NAME_VALUE"
        echo "description_chars=$DESC_CHARS"
        exit 0
    fi

    echo "FAIL frontmatter_check"
    echo "issues=$ISSUE_COUNT"
    printf '%s\n' "$TEXT_ISSUES"
    exit 1
}

print_json() {
    ok=true
    if [ "$ISSUE_COUNT" -ne 0 ]; then
        ok=false
    fi

    printf '{'
    printf '"ok":%s,' "$ok"
    printf '"skill_dir":"%s",' "$(json_escape "$SKILL_DIR")"
    printf '"name":"%s",' "$(json_escape "$NAME_VALUE")"
    printf '"description_chars":%s,' "$DESC_CHARS"
    printf '"issue_count":%s,' "$ISSUE_COUNT"
    printf '"issues":[%s]' "$ISSUE_JSON"
    printf '}\n'

    if [ "$ISSUE_COUNT" -eq 0 ]; then
        exit 0
    fi
    exit 1
}

TEXT_ISSUES=""
ISSUE_JSON=""
ISSUE_COUNT=0
NAME_VALUE=""
DESC_CHARS=0

SKILL_DIR=""

while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help)
            usage
            exit 0
            ;;
        --format)
            FORMAT="${2-}"
            shift 2
            ;;
        --format=*)
            FORMAT=${1#*=}
            shift
            ;;
        -*)
            echo "error: unknown flag: $1" >&2
            exit 2
            ;;
        *)
            if [ -n "$SKILL_DIR" ]; then
                echo "error: only one skill directory may be provided" >&2
                exit 2
            fi
            SKILL_DIR="$1"
            shift
            ;;
    esac
done

if [ -z "$SKILL_DIR" ]; then
    usage >&2
    exit 2
fi

if [ ! -d "$SKILL_DIR" ]; then
    append_issue "missing_directory" "BLOCKER" "skill directory not found: $SKILL_DIR"
    TEXT_ISSUES="- BLOCKER missing_directory: skill directory not found: $SKILL_DIR"
    if [ "$FORMAT" = "json" ]; then
        print_json
    fi
    print_text
fi

SKILL_FILE="$SKILL_DIR/SKILL.md"
if [ ! -f "$SKILL_FILE" ]; then
    append_issue "missing_skill_md" "BLOCKER" "SKILL.md not found in $SKILL_DIR"
    TEXT_ISSUES="- BLOCKER missing_skill_md: SKILL.md not found in $SKILL_DIR"
    if [ "$FORMAT" = "json" ]; then
        print_json
    fi
    print_text
fi

if ! FRONTMATTER=$(load_frontmatter "$SKILL_FILE"); then
    append_issue "frontmatter_missing" "BLOCKER" "YAML frontmatter is missing or malformed"
    TEXT_ISSUES="- BLOCKER frontmatter_missing: YAML frontmatter is missing or malformed"
    if [ "$FORMAT" = "json" ]; then
        print_json
    fi
    print_text
fi

NAME_VALUE=$(printf '%s\n' "$FRONTMATTER" | sed -n 's/^name:[[:space:]]*//p' | head -1 | sed "s/^['\"]//;s/['\"]$//")
if [ -z "$NAME_VALUE" ]; then
    append_issue "name_missing" "BLOCKER" "frontmatter is missing a name field"
    TEXT_ISSUES="$TEXT_ISSUES
- BLOCKER name_missing: frontmatter is missing a name field"
else
    DIR_NAME=$(basename "$SKILL_DIR")
    if [ "$NAME_VALUE" != "$DIR_NAME" ]; then
        append_issue "name_mismatch" "MAJOR" "name does not match directory: $NAME_VALUE != $DIR_NAME"
        TEXT_ISSUES="$TEXT_ISSUES
- MAJOR name_mismatch: name does not match directory: $NAME_VALUE != $DIR_NAME"
    fi
    if ! printf '%s' "$NAME_VALUE" | grep -Eq '^[a-z0-9]([a-z0-9-]*[a-z0-9])?$'; then
        append_issue "name_format" "MAJOR" "name must use lowercase letters, numbers, and single hyphens only"
        TEXT_ISSUES="$TEXT_ISSUES
- MAJOR name_format: name must use lowercase letters, numbers, and single hyphens only"
    fi
    if printf '%s' "$NAME_VALUE" | grep -q -- '--'; then
        append_issue "name_double_hyphen" "MAJOR" "name must not contain consecutive hyphens"
        TEXT_ISSUES="$TEXT_ISSUES
- MAJOR name_double_hyphen: name must not contain consecutive hyphens"
    fi
    NAME_LEN=$(printf '%s' "$NAME_VALUE" | wc -c | tr -d ' ')
    if [ "$NAME_LEN" -gt 64 ]; then
        append_issue "name_length" "MAJOR" "name exceeds 64 characters"
        TEXT_ISSUES="$TEXT_ISSUES
- MAJOR name_length: name exceeds 64 characters"
    fi
fi

if ! DESCRIPTION=$(extract_description "$FRONTMATTER"); then
    append_issue "description_missing" "BLOCKER" "frontmatter is missing a description field"
    TEXT_ISSUES="$TEXT_ISSUES
- BLOCKER description_missing: frontmatter is missing a description field"
else
    DESC_CHARS=$(printf '%s' "$DESCRIPTION" | wc -c | tr -d ' ')
    if [ "$DESC_CHARS" -eq 0 ]; then
        append_issue "description_empty" "BLOCKER" "description must not be empty"
        TEXT_ISSUES="$TEXT_ISSUES
- BLOCKER description_empty: description must not be empty"
    fi
    if [ "$DESC_CHARS" -gt 1024 ]; then
        append_issue "description_length" "MAJOR" "description exceeds 1024 characters"
        TEXT_ISSUES="$TEXT_ISSUES
- MAJOR description_length: description exceeds 1024 characters"
    fi
    if ! printf '%s' "$DESCRIPTION" | grep -qi 'use when'; then
        append_issue "description_trigger" "MAJOR" "description should include a clear 'Use when' trigger phrase"
        TEXT_ISSUES="$TEXT_ISSUES
- MAJOR description_trigger: description should include a clear 'Use when' trigger phrase"
    fi
fi

case "$FORMAT" in
    json) print_json ;;
    text) print_text ;;
    *)
        echo "error: unsupported format: $FORMAT" >&2
        exit 2
        ;;
esac
