#!/usr/bin/env sh

set -eu

FORMAT=text

usage() {
    cat <<'EOF'
Usage: spec_check.sh <skill-directory> [--format json]

Validate AGENTS.md spec compliance for a skill:
  - Name field is title-cased display name (not slug)
  - Directory slug follows slug rules
  - Name is title-cased equivalent of directory slug
  - H1 heading in SKILL.md body matches name field
  - Description contains numbered trigger list pattern
  - SKILL.md under 500 lines
  - Reference files under 300 lines each
  - LF line endings on all text files
  - No secret-pattern files committed
  - trap handler presence in shell scripts
  - Executable permission + shebang on shell scripts
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

has_crlf() {
    file="$1"
    awk '/\r$/ { found = 1; exit 0 } END { exit(found ? 0 : 1) }' "$file"
}

is_text_like_file() {
    file="$1"
    if [ ! -s "$file" ]; then
        return 0
    fi
    LC_ALL=C grep -Iq . "$file"
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
        echo "PASS spec_check"
        echo "warning_count=$WARNING_COUNT"
        if [ "$WARNING_COUNT" -gt 0 ]; then
            printf '%s\n' "$TEXT_WARNINGS"
        fi
        exit 0
    fi

    echo "FAIL spec_check"
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

# --- Naming checks ---

FRONTMATTER=""
if load_frontmatter "$SKILL_FILE" >/dev/null 2>&1; then
    FRONTMATTER=$(load_frontmatter "$SKILL_FILE")
fi

NAME_VALUE=""
if [ -n "$FRONTMATTER" ]; then
    NAME_VALUE=$(printf '%s\n' "$FRONTMATTER" | sed -n 's/^name:[[:space:]]*//p' | head -1 | sed "s/^['\"]//;s/['\"]$//")
fi

DIR_NAME=$(basename "$SKILL_DIR")

# Directory slug validation
if ! printf '%s' "$DIR_NAME" | grep -Eq '^[a-z0-9]([a-z0-9-]*[a-z0-9])?$'; then
    append_issue "slug_format" "MAJOR" "directory slug must use lowercase letters, numbers, and single hyphens: $DIR_NAME"
fi
if printf '%s' "$DIR_NAME" | grep -q -- '--'; then
    append_issue "slug_double_hyphen" "MAJOR" "directory slug must not contain consecutive hyphens: $DIR_NAME"
fi
SLUG_LEN=$(printf '%s' "$DIR_NAME" | wc -c | tr -d ' ')
if [ "$SLUG_LEN" -gt 64 ]; then
    append_issue "slug_length" "MAJOR" "directory slug exceeds 64 characters: $DIR_NAME"
fi

# Name must be title-cased
if [ -n "$NAME_VALUE" ]; then
    if ! printf '%s' "$NAME_VALUE" | grep -Eq '^[A-Z][A-Za-z0-9]*([ ][A-Z][A-Za-z0-9]*)*$'; then
        append_issue "name_not_title_case" "MAJOR" "name must be title-cased with spaces: $NAME_VALUE"
    fi

    # Name must be title-cased equivalent of slug
    EXPECTED_NAME=$(printf '%s' "$DIR_NAME" | sed 's/-/ /g' | awk '{for(i=1;i<=NF;i++) $i=toupper(substr($i,1,1)) substr($i,2)}1')
    if [ "$NAME_VALUE" != "$EXPECTED_NAME" ]; then
        append_issue "name_slug_mismatch" "MAJOR" "name is not the title-cased equivalent of directory slug: $NAME_VALUE != $EXPECTED_NAME (from $DIR_NAME)"
    fi
fi

# --- H1 heading match ---

if [ -n "$NAME_VALUE" ]; then
    CLOSING_LINE=$(awk 'NR > 1 && $0 == "---" { print NR; exit }' "$SKILL_FILE")
    if [ -n "$CLOSING_LINE" ]; then
        H1=$(awk -v start="$CLOSING_LINE" 'NR > start && /^# / { sub(/^# /, ""); print; exit }' "$SKILL_FILE")
        if [ -n "$H1" ] && [ "$H1" != "$NAME_VALUE" ]; then
            append_issue "h1_name_mismatch" "MAJOR" "H1 heading does not match name field: \"$H1\" != \"$NAME_VALUE\""
        fi
    fi
fi

# --- Description numbered trigger list ---

if [ -n "$FRONTMATTER" ]; then
    if DESCRIPTION=$(extract_description "$FRONTMATTER"); then
        if ! printf '%s' "$DESCRIPTION" | grep -qE '\(1\).*\(2\)'; then
            append_warning "description_no_trigger_list" "MINOR" "description does not contain the numbered trigger list pattern (1)...(2)..."
        fi
    fi
fi

# --- SKILL.md line count ---

SKILL_LINES=$(wc -l < "$SKILL_FILE" | tr -d ' ')
if [ "$SKILL_LINES" -gt 500 ]; then
    append_issue "skill_md_too_long" "MAJOR" "SKILL.md exceeds 500 lines ($SKILL_LINES lines)"
fi

# --- Reference file line counts ---

REFERENCE_DIR="$SKILL_DIR/references"
if [ -d "$REFERENCE_DIR" ]; then
    REF_FILES=$(find "$REFERENCE_DIR" -type f -name '*.md' | sort)
    if [ -n "$REF_FILES" ]; then
        while IFS= read -r ref_file; do
            [ -n "$ref_file" ] || continue
            ref_lines=$(wc -l < "$ref_file" | tr -d ' ')
            ref_rel=${ref_file#"$SKILL_DIR"/}
            if [ "$ref_lines" -gt 300 ]; then
                append_warning "reference_too_long" "MINOR" "$ref_rel exceeds 300 lines ($ref_lines lines)"
            fi
        done <<EOF
$REF_FILES
EOF
    fi
fi

# --- LF line endings on all text files ---

ALL_TEXT_FILES=$(find "$SKILL_DIR" -type f \( -name '*.md' -o -name '*.sh' -o -name '*.py' -o -name '*.rs' -o -name '*.toml' -o -name '*.yml' -o -name '*.yaml' -o -name '*.json' \) -not -path '*/.git/*' -not -path '*/__pycache__/*' -not -path '*/.pytest_cache/*' | sort)
if [ -n "$ALL_TEXT_FILES" ]; then
    while IFS= read -r text_file; do
        [ -n "$text_file" ] || continue
        if has_crlf "$text_file"; then
            text_rel=${text_file#"$SKILL_DIR"/}
            append_issue "crlf_line_endings" "BLOCKER" "file uses CRLF line endings: $text_rel"
        fi
    done <<EOF
$ALL_TEXT_FILES
EOF
fi

# --- No secret-pattern files ---

SECRET_FILES=$(find "$SKILL_DIR" -type f \( -name '.env' -o -name '.env.*' -o -name 'credentials.*' -o -name '*secret*' -o -name '*token*' \) -not -path '*/.git/*' -not -path '*/__pycache__/*' -not -path '*/.pytest_cache/*' -not -name '*.py' -not -name '*.sh' -not -name '*.md' | sort)
if [ -n "$SECRET_FILES" ]; then
    while IFS= read -r secret_file; do
        [ -n "$secret_file" ] || continue
        secret_rel=${secret_file#"$SKILL_DIR"/}
        append_issue "secret_pattern_file" "BLOCKER" "file matches secret naming pattern: $secret_rel"
    done <<EOF
$SECRET_FILES
EOF
fi

# --- Shell script checks: trap handler, executable, shebang ---

SCRIPTS_DIR="$SKILL_DIR/scripts"
if [ -d "$SCRIPTS_DIR" ]; then
    SHELL_SCRIPTS=$(find "$SCRIPTS_DIR" -type f -name '*.sh' | sort)
    if [ -n "$SHELL_SCRIPTS" ]; then
        while IFS= read -r sh_file; do
            [ -n "$sh_file" ] || continue
            sh_rel=${sh_file#"$SKILL_DIR"/}

            # Executable permission
            if [ ! -x "$sh_file" ]; then
                append_issue "script_not_executable" "BLOCKER" "shell script is not executable: $sh_rel"
            fi

            # Shebang
            shebang=$(head -1 "$sh_file" 2>/dev/null || true)
            case "$shebang" in
                '#!'*) ;;
                *)
                    append_issue "script_missing_shebang" "BLOCKER" "shell script is missing a shebang: $sh_rel"
                    ;;
            esac

            # trap handler
            if ! grep -q 'trap ' "$sh_file" 2>/dev/null; then
                append_warning "script_no_trap" "MINOR" "shell script has no trap handler for cleanup: $sh_rel"
            fi
        done <<EOF
$SHELL_SCRIPTS
EOF
    fi
fi

# --- Output ---

case "$FORMAT" in
    json) print_json ;;
    text) print_text ;;
    *)
        echo "error: unsupported format: $FORMAT" >&2
        exit 2
        ;;
esac
