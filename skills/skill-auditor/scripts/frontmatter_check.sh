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
  - description presence and basic trigger quality
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
    TEXT_ISSUES="$TEXT_ISSUES
- $severity $code: $message"
}

append_warning() {
    code="$1"
    severity="$2"
    message="$3"
    if [ "$WARNING_COUNT" -gt 0 ]; then
        WARNING_JSON="$WARNING_JSON,"
    fi
    WARNING_JSON="$WARNING_JSON{\"code\":\"$(json_escape "$code")\",\"severity\":\"$(json_escape "$severity")\",\"message\":\"$(json_escape "$message")\"}"
    WARNING_COUNT=$((WARNING_COUNT + 1))
    TEXT_WARNINGS="$TEXT_WARNINGS
- $severity $code: $message"
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
    desc_full_line=$(printf '%s\n' "$fm_block" | sed -n "${desc_start}p")
    desc_raw=$(printf '%s\n' "$desc_full_line" | sed 's/^description:[[:space:]]*//')
    desc_indent=$(printf '%s\n' "$desc_full_line" | awk 'match($0, /^[[:space:]]*/){ print RLENGTH }')

    case "$desc_raw" in
        ">"|">-"|">+"|"|"|"|-"|"|+")
            desc_text=$(
                printf '%s\n' "$fm_block" | tail -n +"$((desc_start + 1))" | awk -v min_indent="$((desc_indent + 1))" '
                    function line_indent(text) {
                        match(text, /^[[:space:]]*/)
                        return RLENGTH
                    }

                    {
                        if ($0 ~ /^[[:space:]]*$/) {
                            if (seen_content) {
                                printf " "
                            }
                            next
                        }

                        if (line_indent($0) < min_indent) {
                            exit
                        }

                        seen_content = 1
                        sub(/^[[:space:]]*/, "", $0)
                        printf "%s ", $0
                    }
                '
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
        echo "warning_count=$WARNING_COUNT"
        if [ "$WARNING_COUNT" -gt 0 ]; then
            printf '%s\n' "$TEXT_WARNINGS"
        fi
        exit 0
    fi

    echo "FAIL frontmatter_check"
    echo "issues=$ISSUE_COUNT"
    printf '%s\n' "$TEXT_ISSUES"
    if [ "$WARNING_COUNT" -gt 0 ]; then
        echo "warning_count=$WARNING_COUNT"
        printf '%s\n' "$TEXT_WARNINGS"
    fi
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
    printf '"description_words":%s,' "$DESC_WORDS"
    printf '"issue_count":%s,' "$ISSUE_COUNT"
    printf '"warning_count":%s,' "$WARNING_COUNT"
    printf '"issues":[%s],' "$ISSUE_JSON"
    printf '"warnings":[%s]' "$WARNING_JSON"
    printf '}\n'

    if [ "$ISSUE_COUNT" -eq 0 ]; then
        exit 0
    fi
    exit 1
}

TEXT_ISSUES=""
TEXT_WARNINGS=""
ISSUE_JSON=""
WARNING_JSON=""
ISSUE_COUNT=0
WARNING_COUNT=0
NAME_VALUE=""
DESC_CHARS=0
DESC_WORDS=0
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
    case "$FORMAT" in
        json) print_json ;;
        text) print_text ;;
        *) echo "error: unsupported format: $FORMAT" >&2; exit 2 ;;
    esac
fi

SKILL_FILE="$SKILL_DIR/SKILL.md"
if [ ! -f "$SKILL_FILE" ]; then
    append_issue "missing_skill_md" "BLOCKER" "SKILL.md not found in $SKILL_DIR"
    case "$FORMAT" in
        json) print_json ;;
        text) print_text ;;
        *) echo "error: unsupported format: $FORMAT" >&2; exit 2 ;;
    esac
fi

if ! FRONTMATTER=$(load_frontmatter "$SKILL_FILE"); then
    append_issue "frontmatter_missing" "BLOCKER" "YAML frontmatter is missing or malformed"
    case "$FORMAT" in
        json) print_json ;;
        text) print_text ;;
        *) echo "error: unsupported format: $FORMAT" >&2; exit 2 ;;
    esac
fi

NAME_VALUE=$(printf '%s\n' "$FRONTMATTER" | sed -n 's/^name:[[:space:]]*//p' | head -1 | sed "s/^['\"]//;s/['\"]$//")
if [ -z "$NAME_VALUE" ]; then
    append_issue "name_missing" "BLOCKER" "frontmatter is missing a name field"
else
    DIR_NAME=$(basename "$SKILL_DIR")

    # Directory slug validation (lowercase, hyphens, no --, max 64)
    if ! printf '%s' "$DIR_NAME" | grep -Eq '^[a-z0-9]([a-z0-9-]*[a-z0-9])?$'; then
        append_issue "slug_format" "MAJOR" "directory slug must use lowercase letters, numbers, and single hyphens only: $DIR_NAME"
    fi
    if printf '%s' "$DIR_NAME" | grep -q -- '--'; then
        append_issue "slug_double_hyphen" "MAJOR" "directory slug must not contain consecutive hyphens: $DIR_NAME"
    fi
    SLUG_LEN=$(printf '%s' "$DIR_NAME" | wc -c | tr -d ' ')
    if [ "$SLUG_LEN" -gt 64 ]; then
        append_issue "slug_length" "MAJOR" "directory slug exceeds 64 characters: $DIR_NAME"
    fi

    # Name field must be title-cased (each word starts with uppercase)
    if ! printf '%s' "$NAME_VALUE" | grep -Eq '^[A-Z][A-Za-z0-9]*([ ][A-Z][A-Za-z0-9]*)*$'; then
        append_issue "name_not_title_case" "MAJOR" "name must be title-cased with spaces: $NAME_VALUE"
    fi

    # Name must be the title-cased equivalent of the directory slug
    EXPECTED_NAME=$(printf '%s' "$DIR_NAME" | sed 's/-/ /g' | awk '{for(i=1;i<=NF;i++) $i=toupper(substr($i,1,1)) substr($i,2)}1')
    if [ "$NAME_VALUE" != "$EXPECTED_NAME" ]; then
        append_issue "name_slug_mismatch" "MAJOR" "name is not the title-cased equivalent of directory slug: $NAME_VALUE != $EXPECTED_NAME (from $DIR_NAME)"
    fi
fi

if ! DESCRIPTION=$(extract_description "$FRONTMATTER"); then
    append_issue "description_missing" "BLOCKER" "frontmatter is missing a description field"
else
    DESC_CHARS=$(printf '%s' "$DESCRIPTION" | wc -c | tr -d ' ')
    DESC_WORDS=$(printf '%s' "$DESCRIPTION" | wc -w | tr -d ' ')
    if [ "$DESC_CHARS" -eq 0 ]; then
        append_issue "description_empty" "BLOCKER" "description must not be empty"
    fi
    if [ "$DESC_CHARS" -gt 1024 ]; then
        append_issue "description_length" "MAJOR" "description exceeds 1024 characters"
    fi
    if [ "$DESC_WORDS" -lt 4 ]; then
        append_issue "description_too_vague" "MAJOR" "description is too short to explain what the skill does and when to use it"
    elif [ "$DESC_WORDS" -lt 10 ]; then
        append_warning "description_brief" "MINOR" "description is brief and may underspecify trigger boundaries"
    fi

    desc_lower=$(printf '%s' "$DESCRIPTION" | tr '[:upper:]' '[:lower:]')
    if printf '%s' "$desc_lower" | grep -Eq '^(helps with|assists with|supports|tool for|utility for)\b'; then
        append_warning "description_trigger_weak" "MINOR" "description uses generic wording and may not describe trigger boundaries clearly"
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
