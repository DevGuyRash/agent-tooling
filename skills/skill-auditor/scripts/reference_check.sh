#!/usr/bin/env sh

set -eu

FORMAT=text

usage() {
    cat <<'EOF'
Usage: reference_check.sh <skill-directory> [--format json]

Validate that active references:
  - exist on disk
  - are directly linked from SKILL.md
  - do not point to other reference files
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

contains_line() {
    needle="$1"
    haystack="$2"
    printf '%s\n' "$haystack" | grep -Fx -- "$needle" >/dev/null 2>&1
}

collect_skill_links() {
    skill_file="$1"
    grep -oE '(<skills-file-root>/)?references/[A-Za-z0-9._/-]+\.md' "$skill_file" 2>/dev/null | sort -u || true
}

print_text() {
    if [ "$ISSUE_COUNT" -eq 0 ]; then
        echo "PASS reference_check"
        echo "linked_references=$LINKED_COUNT"
        echo "active_references=$ACTIVE_COUNT"
        exit 0
    fi

    echo "FAIL reference_check"
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
    printf '"linked_references":%s,' "$LINKED_COUNT"
    printf '"active_references":%s,' "$ACTIVE_COUNT"
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
LINKED_COUNT=0
ACTIVE_COUNT=0
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

RAW_LINKS=$(collect_skill_links "$SKILL_FILE")
TOKENIZED_LINKS=""

if [ -n "$RAW_LINKS" ]; then
    while IFS= read -r raw_link; do
        [ -n "$raw_link" ] || continue
        case "$raw_link" in
            '<skills-file-root>'/*)
                rel_path=${raw_link#<skills-file-root>/}
                ;;
            *)
                rel_path=$raw_link
                append_issue "bare_reference_path" "MAJOR" "SKILL.md should reference active docs with <skills-file-root>/$raw_link"
                ;;
        esac

        if [ -n "$TOKENIZED_LINKS" ]; then
            TOKENIZED_LINKS="$TOKENIZED_LINKS
$rel_path"
        else
            TOKENIZED_LINKS="$rel_path"
        fi

        if [ ! -f "$SKILL_DIR/$rel_path" ]; then
            append_issue "missing_reference_file" "BLOCKER" "referenced file not found: $rel_path"
        fi
    done <<EOF
$RAW_LINKS
EOF
fi

if [ -n "$TOKENIZED_LINKS" ]; then
    LINKED_COUNT=$(printf '%s\n' "$TOKENIZED_LINKS" | sed '/^$/d' | sort -u | wc -l | tr -d ' ')
fi

REFERENCE_DIR="$SKILL_DIR/references"
if [ -d "$REFERENCE_DIR" ]; then
    ACTIVE_REFS=$(find "$REFERENCE_DIR" -maxdepth 1 -type f -name '*.md' | sort)
else
    ACTIVE_REFS=""
fi

if [ -n "$ACTIVE_REFS" ]; then
    ACTIVE_COUNT=$(printf '%s\n' "$ACTIVE_REFS" | sed '/^$/d' | wc -l | tr -d ' ')
    while IFS= read -r ref_file; do
        [ -n "$ref_file" ] || continue
        rel_ref=${ref_file#"$SKILL_DIR"/}
        if ! contains_line "$rel_ref" "$TOKENIZED_LINKS"; then
            append_issue "unlinked_reference" "MAJOR" "active reference is not directly linked from SKILL.md: $rel_ref"
        fi

        nested_links=$(grep -oE 'references/[A-Za-z0-9._/-]+\.md' "$ref_file" 2>/dev/null | sort -u || true)
        if [ -n "$nested_links" ]; then
            append_issue "nested_reference_link" "MAJOR" "reference points to another reference file: $rel_ref"
        fi
    done <<EOF
$ACTIVE_REFS
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
