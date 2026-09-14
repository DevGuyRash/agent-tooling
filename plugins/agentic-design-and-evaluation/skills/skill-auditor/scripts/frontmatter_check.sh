#!/usr/bin/env sh

set -eu

FORMAT=text

usage() {
    cat <<'EOF'
Usage: frontmatter_check.sh <skill-directory> [--format json]

Report what is true of SKILL.md frontmatter, in two kinds.

Errors concern the required-metadata contract checked here: unreadable
frontmatter or a missing/empty required field. The extractor is not a full
YAML or host parser; confirm unsupported forms at the actual consumer.

Observations are portable frontmatter facts whose significance depends on the
target — for example slug shape and name/directory mismatch. Description
bytes measure the lightweight extractor output, not parsed Unicode characters;
they do not establish the portable character-limit property. Observations never fail.

Description quality is not assessed. A word count cannot tell whether a
description discriminates, so judging that is left to the reader.

Exit: 0 no errors, 1 errors found, 2 the arguments or the target were unusable.
EOF
}

json_escape() {
    printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'
}

fail_usage() {
    echo "error: $1" >&2
    [ -z "${2-}" ] || echo "hint: $2" >&2
    exit 2
}

# Required metadata under this reporter's supported extraction contract.
error() {
    if [ "$ERR_COUNT" -gt 0 ]; then ERR_JSON="$ERR_JSON,"; fi
    ERR_JSON="$ERR_JSON{\"code\":\"$(json_escape "$1")\",\"subject\":\"$(json_escape "$2")\",\"fact\":\"$(json_escape "$3")\"}"
    ERR_COUNT=$((ERR_COUNT + 1))
    TEXT_ERRORS="$TEXT_ERRORS
ERROR $1: $2
  $3"
}

# A fact whose significance depends on the target, carrying the rule it bears
# on so the reader can decide rather than obey.
observe() {
    source_ref="${4-}"
    if [ "$OBS_COUNT" -gt 0 ]; then OBS_JSON="$OBS_JSON,"; fi
    OBS_JSON="$OBS_JSON{\"code\":\"$(json_escape "$1")\",\"subject\":\"$(json_escape "$2")\",\"fact\":\"$(json_escape "$3")\""
    [ -z "$source_ref" ] || OBS_JSON="$OBS_JSON,\"source\":\"$(json_escape "$source_ref")\""
    OBS_JSON="$OBS_JSON}"
    OBS_COUNT=$((OBS_COUNT + 1))
    TEXT_OBS="$TEXT_OBS
$1: $2
  $3"
    [ -z "$source_ref" ] || TEXT_OBS="$TEXT_OBS
  source: $source_ref"
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

                        if (seen_content) printf " "
                        seen_content = 1
                        sub(/^[[:space:]]*/, "", $0)
                        printf "%s", $0
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
    echo "REPORT frontmatter_check"
    echo "skill_dir=$SKILL_DIR"
    echo "name=$NAME_VALUE"
    echo "description_bytes=$DESC_BYTES"
    echo "errors=$ERR_COUNT"
    echo "observations=$OBS_COUNT"
    [ "$ERR_COUNT" -eq 0 ] || printf '%s\n' "$TEXT_ERRORS"
    [ "$OBS_COUNT" -eq 0 ] || printf '%s\n' "$TEXT_OBS"
    [ "$ERR_COUNT" -eq 0 ] || exit 1
    exit 0
}

print_json() {
    printf '{'
    printf '"script":"frontmatter_check",'
    printf '"skill_dir":"%s",' "$(json_escape "$SKILL_DIR")"
    printf '"name":"%s",' "$(json_escape "$NAME_VALUE")"
    printf '"description_bytes":%s,' "$DESC_BYTES"
    printf '"error_count":%s,' "$ERR_COUNT"
    printf '"errors":[%s],' "$ERR_JSON"
    printf '"observation_count":%s,' "$OBS_COUNT"
    printf '"observations":[%s]' "$OBS_JSON"
    printf '}\n'
    [ "$ERR_COUNT" -eq 0 ] || exit 1
    exit 0
}

TEXT_ERRORS=""
TEXT_OBS=""
ERR_JSON=""
OBS_JSON=""
ERR_COUNT=0
OBS_COUNT=0
NAME_VALUE=""
DESC_BYTES=0
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
        -*) fail_usage "unknown flag: $1" ;;
        *)
            [ -z "$SKILL_DIR" ] || fail_usage "only one skill directory may be provided"
            SKILL_DIR="$1"
            shift
            ;;
    esac
done

[ -n "$SKILL_DIR" ] || { usage >&2; exit 2; }

case "$FORMAT" in
    text|json) ;;
    *) fail_usage "unsupported format: $FORMAT" "use text or json" ;;
esac

# Not findings about the target: the script could not run.
[ -d "$SKILL_DIR" ] || fail_usage "skill directory not found: $SKILL_DIR"
RESOLVED_SKILL_DIR=$(unset CDPATH; cd -- "$SKILL_DIR" 2>/dev/null && pwd -L) || \
    fail_usage "skill directory could not be resolved: $SKILL_DIR"

SKILL_FILE="$RESOLVED_SKILL_DIR/SKILL.md"
[ -f "$SKILL_FILE" ] || fail_usage "SKILL.md not found in $SKILL_DIR"

if ! FRONTMATTER=$(load_frontmatter "$SKILL_FILE"); then
    error "frontmatter_missing" "SKILL.md" \
        "no readable YAML frontmatter; the skill exposes no metadata to match against"
    case "$FORMAT" in
        json) print_json ;;
        text) print_text ;;
    esac
fi

NAME_VALUE=$(printf '%s\n' "$FRONTMATTER" | sed -n 's/^name:[[:space:]]*//p' | head -1 | sed "s/^['\"]//;s/['\"]$//")
if [ -z "$NAME_VALUE" ]; then
    error "name_missing" "frontmatter" "no name field found by the lightweight extractor"
else
    DIR_NAME=$(basename "$RESOLVED_SKILL_DIR")

    # These are deterministic observations. The auditor decides whether the
    # target adopted the portable standard or a host/profile exception.
    if ! printf '%s' "$DIR_NAME" | grep -Eq '^[a-z0-9]([a-z0-9-]*[a-z0-9])?$'; then
        observe "slug_format" "$DIR_NAME" \
            "the directory slug is not lowercase alphanumeric with single hyphens" \
            "open-standard"
    fi
    if printf '%s' "$DIR_NAME" | grep -q -- '--'; then
        observe "slug_double_hyphen" "$DIR_NAME" \
            "the directory slug contains consecutive hyphens" \
            "open-standard"
    fi
    SLUG_LEN=$(printf '%s' "$DIR_NAME" | wc -c | tr -d ' ')
    if [ "$SLUG_LEN" -gt 64 ]; then
        observe "slug_length" "$DIR_NAME" \
            "the directory slug occupies $SLUG_LEN bytes; confirm parsed length if non-ASCII" \
            "open-standard"
    fi

    if [ "$NAME_VALUE" != "$DIR_NAME" ]; then
        observe "name_directory_mismatch" "$NAME_VALUE" \
            "the name field does not match the parent skill directory \"$DIR_NAME\"" \
            "open-standard"
    fi
fi

if ! DESCRIPTION=$(extract_description "$FRONTMATTER"); then
    error "description_missing" "frontmatter" \
        "no description field found by the lightweight extractor"
else
    DESC_BYTES=$(printf '%s' "$DESCRIPTION" | wc -c | tr -d ' ')
    if [ "$DESC_BYTES" -eq 0 ]; then
        error "description_empty" "frontmatter" \
            "the extracted description is empty"
    fi
    # This lightweight YAML extractor measures bytes, not parsed Unicode
    # characters. It cannot establish the portable character-limit property.
fi

case "$FORMAT" in
    json) print_json ;;
    text) print_text ;;
    *)
        echo "error: unsupported format: $FORMAT" >&2
        exit 2
        ;;
esac
