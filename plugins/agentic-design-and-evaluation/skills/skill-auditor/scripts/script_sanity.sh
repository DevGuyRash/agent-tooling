#!/usr/bin/env sh

set -eu

FORMAT=text

usage() {
    cat <<'EOF'
Usage: script_sanity.sh <skill-directory> [--format json]

Report executable and line-ending facts for a skill's files.

The reporter flags a missing interpreter directive or a carriage return in
an executable shebang. These are structural facts to reconcile with the actual
host invocation. A CR elsewhere in the body does not establish shebang failure.

Non-executable shell files and CRLF outside an executable shebang are observations.
Whether a shell file is sourced, passed to an interpreter, or intended as a
launcher belongs to the target instructions and repository contract. This
script does not infer that responsibility, cleanup, credentials, or semantic
policy from filenames or keyword patterns.

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

error() {
    if [ "$ERR_COUNT" -gt 0 ]; then ERR_JSON="$ERR_JSON,"; fi
    ERR_JSON="$ERR_JSON{\"code\":\"$(json_escape "$1")\",\"subject\":\"$(json_escape "$2")\",\"fact\":\"$(json_escape "$3")\"}"
    ERR_COUNT=$((ERR_COUNT + 1))
    TEXT_ERRORS="$TEXT_ERRORS
ERROR $1: $2
  $3"
}

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

has_crlf() {
    awk '/\r$/ { found = 1; exit 0 } END { exit(found ? 0 : 1) }' "$1"
}

shebang_has_crlf() {
    awk 'NR == 1 { found = ($0 ~ /^#!.*\r$/); exit } END { exit(found ? 0 : 1) }' "$1"
}

is_text_like_file() {
    [ -s "$1" ] || return 0
    LC_ALL=C grep -Iq . "$1"
}

print_text() {
    echo "REPORT script_sanity"
    echo "skill_dir=$SKILL_DIR"
    echo "script_count=$SCRIPT_COUNT"
    echo "errors=$ERR_COUNT"
    echo "observations=$OBS_COUNT"
    [ "$ERR_COUNT" -eq 0 ] || printf '%s\n' "$TEXT_ERRORS"
    [ "$OBS_COUNT" -eq 0 ] || printf '%s\n' "$TEXT_OBS"
    [ "$ERR_COUNT" -eq 0 ] || exit 1
    exit 0
}

print_json() {
    printf '{'
    printf '"script":"script_sanity",'
    printf '"skill_dir":"%s",' "$(json_escape "$SKILL_DIR")"
    printf '"script_count":%s,' "$SCRIPT_COUNT"
    printf '"error_count":%s,' "$ERR_COUNT"
    printf '"errors":[%s],' "$ERR_JSON"
    printf '"observation_count":%s,' "$OBS_COUNT"
    printf '"observations":[%s]' "$OBS_JSON"
    printf '}\n'
    [ "$ERR_COUNT" -eq 0 ] || exit 1
    exit 0
}

TEXT_ERRORS=""; TEXT_OBS=""
ERR_JSON=""; OBS_JSON=""
ERR_COUNT=0; OBS_COUNT=0
SCRIPT_COUNT=0
SKILL_DIR=""

while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help) usage; exit 0 ;;
        --format) FORMAT="${2-}"; shift 2 ;;
        --format=*) FORMAT=${1#*=}; shift ;;
        -*) fail_usage "unknown flag: $1" ;;
        *)
            [ -z "$SKILL_DIR" ] || fail_usage "only one skill directory may be provided"
            SKILL_DIR="$1"; shift ;;
    esac
done

[ -n "$SKILL_DIR" ] || { usage >&2; exit 2; }

case "$FORMAT" in
    text|json) ;;
    *) fail_usage "unsupported format: $FORMAT" "use text or json" ;;
esac

[ -d "$SKILL_DIR" ] || fail_usage "skill directory not found: $SKILL_DIR"

SCRATCH_DIR=$(mktemp -d "${TMPDIR:-/tmp}/scriptsanity.XXXXXXXXXX") || fail_usage "cannot create private scratch directory"
trap 'rm -rf -- "$SCRATCH_DIR"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
CRLF_FILE="$SCRATCH_DIR/crlf-files"
SCRIPTS_DIR="$SKILL_DIR/scripts"

# Gather CRLF facts before the scripts/ early return. Only a CR in the
# interpreter directive can affect shebang parsing; body line endings alone
# do not establish a direct-execution failure.
find "$SKILL_DIR" -type f \
    \( -name '*.md' -o -name '*.py' -o -name '*.rs' -o -name '*.toml' \
       -o -name '*.yml' -o -name '*.yaml' -o -name '*.json' -o -name '*.sh' \) \
    -not -path '*/.git/*' -not -path '*/__pycache__/*' -not -path '*/.pytest_cache/*' \
    -exec grep -lI "$(printf '\r')$" {} + 2>/dev/null | sort -u >"$CRLF_FILE" || true
while IFS= read -r crlf_file; do
    [ -n "$crlf_file" ] || continue
    # Files under scripts/ are handled by the per-script loop below; reporting
    # them here too would double-count. Outside scripts/, inspect the actual
    # shebang rather than treating every CRLF line as an interpreter defect.
    case "$crlf_file" in
        "$SCRIPTS_DIR"/*) continue ;;
    esac
    if [ -x "$crlf_file" ] && shebang_has_crlf "$crlf_file"; then
        error "crlf_in_executable" "${crlf_file#"$SKILL_DIR"/}" \
            "the executable has a carriage return in its shebang, not merely in its body; verify the intended host interpreter boundary"
    else
        observe "crlf" "${crlf_file#"$SKILL_DIR"/}" \
            "the file uses CRLF line endings" \
            "repo-overlay"
    fi
done <"$CRLF_FILE"

if [ ! -d "$SCRIPTS_DIR" ]; then
    case "$FORMAT" in json) print_json ;; text) print_text ;; esac
fi

TOP_LEVEL_SCRIPTS=$(find "$SCRIPTS_DIR" -type f \
    -not -path '*/__pycache__/*' -not -path '*/.pytest_cache/*' | sort)
if [ -n "$TOP_LEVEL_SCRIPTS" ]; then
    SCRIPT_COUNT=$(printf '%s\n' "$TOP_LEVEL_SCRIPTS" | sed '/^$/d' | wc -l | tr -d ' ')
fi

if [ -n "$TOP_LEVEL_SCRIPTS" ]; then
    while IFS= read -r script_file; do
        [ -n "$script_file" ] || continue
        script_name=$(basename "$script_file")
        script_rel=${script_file#"$SKILL_DIR"/}
        is_text_like_file "$script_file" || continue

        executable=false
        [ ! -x "$script_file" ] || executable=true
        shebang=$(head -1 "$script_file" 2>/dev/null || true)

        # A carriage return lands inside the interpreter path, so the shell
        # cannot find it when the file is directly executed. Otherwise retain
        # the line-ending fact without guessing how the target consumes it.
        if has_crlf "$script_file"; then
            if [ "$executable" = true ] && shebang_has_crlf "$script_file"; then
                error "crlf_in_executable" "$script_rel" \
                    "the executable has a carriage return in its shebang, not merely in its body; verify the intended host interpreter boundary"
            else
                observe "crlf" "$script_rel" \
                    "the file uses CRLF line endings" \
                    "repo-overlay"
            fi
        fi

        if [ "$executable" = true ]; then
            case "$shebang" in
                '#!'*) ;;
                *) error "missing_shebang" "$script_rel" \
                       "the file is executable but has no interpreter shebang" ;;
            esac
        else
            case "$script_name" in
                *.sh) observe "not_executable" "$script_rel" \
                          "the shell file has no executable bit; inspect whether the target sources it, invokes an interpreter, or expects direct execution" \
                          "repo-overlay" ;;
            esac
        fi
    done <<EOF
$TOP_LEVEL_SCRIPTS
EOF
fi

case "$FORMAT" in
    json) print_json ;;
    text) print_text ;;
esac
