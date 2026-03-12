#!/usr/bin/env sh

set -eu

FORMAT=text
WARNING_SCRIPT_COUNT_THRESHOLD=6

usage() {
    cat <<'EOF'
Usage: script_sanity.sh <skill-directory> [--format json]

Validate the script surface structurally:
  - top-level scripts use LF line endings
  - shell launchers are executable and have shebangs
  - executable non-shell scripts have shebangs
  - large script surfaces are reported as advisories
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

requires_launcher_contract() {
    script_name="$1"
    case "$script_name" in
        *.sh) return 0 ;;
        *.*) return 1 ;;
        *) return 0 ;;
    esac
}

print_text() {
    if [ "$ISSUE_COUNT" -eq 0 ]; then
        echo "PASS script_sanity"
        echo "script_count=$SCRIPT_COUNT"
        echo "warning_count=$WARNING_COUNT"
        if [ "$WARNING_COUNT" -gt 0 ]; then
            printf '%s\n' "$TEXT_WARNINGS"
        fi
        exit 0
    fi

    echo "FAIL script_sanity"
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
    printf '"script_count":%s,' "$SCRIPT_COUNT"
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

if [ "$SCRIPT_COUNT" -gt "$WARNING_SCRIPT_COUNT_THRESHOLD" ]; then
    append_warning "script_surface_large" "MINOR" "top-level script surface is larger than typical and may deserve review"
fi

if [ -n "$TOP_LEVEL_SCRIPTS" ]; then
    while IFS= read -r script_file; do
        [ -n "$script_file" ] || continue
        script_name=$(basename "$script_file")
        executable=false
        if [ -x "$script_file" ]; then
            executable=true
        fi
        if ! is_text_like_file "$script_file"; then
            continue
        fi
        shebang=$(head -1 "$script_file" 2>/dev/null || true)

        if has_crlf "$script_file"; then
            append_issue "crlf" "BLOCKER" "script uses CRLF line endings: scripts/$script_name"
        fi

        if requires_launcher_contract "$script_name"; then
            if [ "$executable" != "true" ]; then
                append_issue "not_executable" "BLOCKER" "launcher script is not executable: scripts/$script_name"
            fi
            case "$shebang" in
                '#!'*) ;;
                *)
                    append_issue "missing_shebang" "BLOCKER" "launcher script is missing a shebang: scripts/$script_name"
                    ;;
            esac
        elif [ "$executable" = "true" ]; then
            case "$shebang" in
                '#!'*) ;;
                *)
                    append_issue "missing_shebang" "BLOCKER" "executable script is missing a shebang: scripts/$script_name"
                    ;;
            esac
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
