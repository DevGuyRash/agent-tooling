#!/usr/bin/env sh

set -eu

FORMAT=text
ALLOWED_SCRIPTS="frontmatter_check.sh
reference_check.sh
script_sanity.sh
capture_eval.sh"

usage() {
    cat <<'EOF'
Usage: script_sanity.sh <skill-directory> [--format json]

Validate that the active script surface is small and structurally sound:
  - only approved top-level scripts are present
  - required scripts exist
  - scripts are executable, use LF line endings, and have shebangs
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

is_allowed() {
    candidate="$1"
    printf '%s\n' "$ALLOWED_SCRIPTS" | grep -Fx -- "$candidate" >/dev/null 2>&1
}

has_crlf() {
    file="$1"
    awk '/\r$/ { found = 1; exit 0 } END { exit(found ? 0 : 1) }' "$file"
}

print_text() {
    if [ "$ISSUE_COUNT" -eq 0 ]; then
        echo "PASS script_sanity"
        echo "script_count=$SCRIPT_COUNT"
        exit 0
    fi

    echo "FAIL script_sanity"
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
    printf '"script_count":%s,' "$SCRIPT_COUNT"
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
SCRIPT_COUNT=0
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

SCRIPTS_DIR="$SKILL_DIR/scripts"
if [ ! -d "$SCRIPTS_DIR" ]; then
    append_issue "missing_scripts_dir" "BLOCKER" "scripts directory not found: $SCRIPTS_DIR"
    case "$FORMAT" in
        json) print_json ;;
        text) print_text ;;
        *) echo "error: unsupported format: $FORMAT" >&2; exit 2 ;;
    esac
fi

TOP_LEVEL_SCRIPTS=$(find "$SCRIPTS_DIR" -maxdepth 1 -type f | sort)

if [ -n "$TOP_LEVEL_SCRIPTS" ]; then
    SCRIPT_COUNT=$(printf '%s\n' "$TOP_LEVEL_SCRIPTS" | sed '/^$/d' | wc -l | tr -d ' ')
fi

if [ "$SCRIPT_COUNT" -gt 4 ]; then
    append_issue "script_count" "MAJOR" "active script surface exceeds four top-level scripts"
fi

for required in frontmatter_check.sh reference_check.sh script_sanity.sh; do
    if [ ! -f "$SCRIPTS_DIR/$required" ]; then
        append_issue "missing_required_script" "BLOCKER" "required script missing: scripts/$required"
    fi
done

if [ -n "$TOP_LEVEL_SCRIPTS" ]; then
    while IFS= read -r script_file; do
        [ -n "$script_file" ] || continue
        script_name=$(basename "$script_file")
        if ! is_allowed "$script_name"; then
            append_issue "unexpected_script" "MAJOR" "unexpected active script: scripts/$script_name"
        fi
        if [ ! -x "$script_file" ]; then
            append_issue "not_executable" "BLOCKER" "script is not executable: scripts/$script_name"
        fi
        shebang=$(head -1 "$script_file" 2>/dev/null || true)
        case "$shebang" in
            '#!'*) ;;
            *)
                append_issue "missing_shebang" "BLOCKER" "script is missing a shebang: scripts/$script_name"
                ;;
        esac
        if has_crlf "$script_file"; then
            append_issue "crlf" "BLOCKER" "script uses CRLF line endings: scripts/$script_name"
        fi
    done <<EOF
$TOP_LEVEL_SCRIPTS
EOF
fi

case "$FORMAT" in
    json) print_json ;;
    text) print_text ;;
    *)
        echo "error: unsupported format: $FORMAT" >&2
        exit 2
        ;;
esac
