#!/usr/bin/env sh
# skill-auditor — Documentation/runtime staleness drift check (D21).
#
# Usage:
#   staleness_check.sh <skill-directory> [--cli <binary>] [--format text|json] [--timeout-seconds <n>]
#
# Checks whether documented examples still match current runtime behavior.

set -eu

CLI_BIN=""
FORMAT="text"
SKILL_DIR=""
TIMEOUT_SECONDS=15

usage() {
    echo "Usage: staleness_check.sh <skill-directory> [--cli <binary>] [--format text|json] [--timeout-seconds <n>]"
    echo ""
    echo "Checks documentation/runtime staleness drift:"
    echo "  - Aggressively extract command-shaped examples from SKILL.md/references"
    echo "  - Normalize multiline/continuation commands"
    echo "  - Verify examples directly or with --help fallback when safe"
    echo "  - Keep status outputs stable with richer machine detail"
}

case "${1-}" in
    -h|--help)
        usage
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
        --format)
            shift
            FORMAT="${1-}"
            case "$FORMAT" in
                text|json) ;;
                *)
                    echo "error: --format must be text or json"
                    exit 1
                    ;;
            esac
            ;;
        --timeout-seconds)
            shift
            TIMEOUT_SECONDS="${1-}"
            case "$TIMEOUT_SECONDS" in
                ''|*[!0-9]*)
                    echo "error: --timeout-seconds must be a positive integer"
                    exit 1
                    ;;
                0)
                    echo "error: --timeout-seconds must be greater than 0"
                    exit 1
                    ;;
            esac
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
    usage
    exit 1
fi

if [ ! -d "$SKILL_DIR" ]; then
    echo "error: not a directory: $SKILL_DIR"
    exit 1
fi

if [ -n "$CLI_BIN" ]; then
    resolved_cli=$(command -v "$CLI_BIN" 2>/dev/null || true)
    if [ -n "$resolved_cli" ]; then
        CLI_BIN="$resolved_cli"
    fi
    if [ ! -x "$CLI_BIN" ]; then
        echo "error: CLI binary not executable: $CLI_BIN"
        exit 1
    fi
fi

DIR_NAME=$(basename "$SKILL_DIR")
TAB=$(printf '\t')

tmp_md=$(mktemp)
tmp_candidates=$(mktemp)
tmp_results=$(mktemp)
trap 'rm -f "$tmp_md" "$tmp_candidates" "$tmp_results"' EXIT INT TERM

find "$SKILL_DIR" -name '*.md' -not -path '*/.git/*' -not -path '*/target/*' \
    -not -path "$SKILL_DIR/tests/*" -not -name 'ARCHITECTURE-PLAN.md' \
    2>/dev/null | sort > "$tmp_md"

: > "$tmp_candidates"

while IFS= read -r file; do
    [ -z "$file" ] && continue
    awk -v file="$file" '
        function trim(s) {
            gsub(/^[[:space:]]+/, "", s)
            gsub(/[[:space:]]+$/, "", s)
            return s
        }
        function clean(s) {
            gsub(/\r/, "", s)
            gsub(/\t/, " ", s)
            return trim(s)
        }
        function is_fence_open(line) {
            return (line ~ /^```[[:space:]]*(bash|sh|shell|zsh)[[:space:]]*$/)
        }
        function is_fence_close(line) {
            return (line ~ /^```[[:space:]]*$/)
        }
        function is_prose_line(line) {
            return (line !~ /^```/ && clean(line) != "")
        }
        function before_ctx(idx, out, c, k) {
            out = ""
            c = 0
            for (k = idx - 1; k >= 1 && c < 2; k--) {
                if (is_prose_line(lines[k])) {
                    if (out == "") out = clean(lines[k]); else out = clean(lines[k]) " | " out
                    c++
                }
            }
            return out
        }
        function after_ctx(idx, out, c, k) {
            out = ""
            c = 0
            for (k = idx + 1; k <= NR && c < 2; k++) {
                if (is_prose_line(lines[k])) {
                    if (out == "") out = clean(lines[k]); else out = out " | " clean(lines[k])
                    c++
                }
            }
            return out
        }
        function emit(kind, ln, cmd, raw) {
            before = before_ctx(ln)
            after = after_ctx(ln)
            cmdc = clean(cmd)
            rawc = clean(raw)
            if (cmdc != "") {
                print file "\t" ln "\t" kind "\t" cmdc "\t" before "\t" after "\t" rawc
            }
        }
        function looks_command_shaped(cmd) {
            c = clean(cmd)
            if (c == "") return 0
            if (c ~ /^-/) return 0
            if (c ~ /^[A-Z0-9_]+$/) return 0
            if (c ~ /^<[^>]+>$/) return 0
            if (c ~ /^[A-Za-z0-9_./"$<][A-Za-z0-9_./:"$<>{}\[\]@ -]*$/) return 1
            return 0
        }
        {
            lines[NR] = $0
        }
        END {
            in_fence = 0
            pending = ""
            pending_line = 0
            for (i = 1; i <= NR; i++) {
                line = lines[i]
                t = clean(line)

                if (!in_fence && is_fence_open(line)) {
                    in_fence = 1
                    pending = ""
                    pending_line = 0
                    continue
                }

                if (in_fence && is_fence_close(line)) {
                    if (pending != "") {
                        emit("fenced", pending_line, pending, pending)
                        pending = ""
                        pending_line = 0
                    }
                    in_fence = 0
                    continue
                }

                if (in_fence) {
                    cmd = t
                    sub(/^\$[[:space:]]*/, "", cmd)
                    if (cmd == "" || cmd ~ /^#/) continue

                    cont = (cmd ~ /\\$/)
                    sub(/\\$/, "", cmd)
                    cmd = trim(cmd)

                    if (pending == "") {
                        pending = cmd
                        pending_line = i
                    } else {
                        pending = pending " " cmd
                    }

                    if (!cont) {
                        emit("fenced", pending_line, pending, pending)
                        pending = ""
                        pending_line = 0
                    }
                    continue
                }

                remain = line
                while (match(remain, /`[^`]+`/)) {
                    raw = substr(remain, RSTART + 1, RLENGTH - 2)
                    if (looks_command_shaped(raw)) {
                        emit("inline", i, raw, raw)
                    }
                    remain = substr(remain, RSTART + RLENGTH)
                }
            }

            if (in_fence && pending != "") {
                emit("fenced", pending_line, pending, pending)
            }
        }
    ' "$file" >> "$tmp_candidates"
done < "$tmp_md"

normalize_command() {
    cmd="$1"
    escaped_skill_dir=$(printf '%s' "$SKILL_DIR" | sed 's/[&|]/\\&/g')
    printf '%s' "$cmd" | sed \
        -e "s|<skills-file-root>|$escaped_skill_dir|g" \
        -e "s|\${SKILL_ROOT}|$escaped_skill_dir|g" \
        -e "s|\${SKILL_DIR}|$escaped_skill_dir|g" \
        -e "s|\$SKILL_ROOT|$escaped_skill_dir|g" \
        -e "s|\$SKILL_DIR|$escaped_skill_dir|g"
}

strip_quotes() {
    val="$1"
    case "$val" in
        \"*\") val=${val#\"}; val=${val%\"} ;;
        \''*\') val=${val#\'}; val=${val%\'} ;;
    esac
    printf '%s' "$val"
}

is_assignment_token() {
    tok="$1"
    printf '%s' "$tok" | grep -E '^[A-Za-z_][A-Za-z0-9_]*=.*$' >/dev/null
}

tokenize_command() {
    input_cmd="$1"
    printf '%s\n' "$input_cmd" | awk '
        function flush() {
            if (token != "") {
                print token
                token = ""
            }
        }
        BEGIN {
            in_single = 0
            in_double = 0
            escaped = 0
            token = ""
        }
        {
            line = $0
            for (i = 1; i <= length(line); i++) {
                ch = substr(line, i, 1)
                if (escaped) {
                    token = token ch
                    escaped = 0
                    continue
                }
                if (ch == "\\") {
                    if (in_single) {
                        token = token ch
                        continue
                    }
                    token = token ch
                    escaped = 1
                    continue
                }
                if (ch == "\"" && !in_single) {
                    in_double = !in_double
                    token = token ch
                    continue
                }
                if (ch == sprintf("%c", 39) && !in_double) {
                    in_single = !in_single
                    token = token ch
                    continue
                }
                if (ch ~ /[[:space:]]/ && !in_single && !in_double) {
                    flush()
                    continue
                }
                token = token ch
            }
        }
        END {
            if (escaped) {
                token = token "\\"
            }
            flush()
        }
    '
}

has_safe_indicator() {
    input_cmd="$1"
    printf '%s' "$input_cmd" | grep -E '(^|[[:space:]])(--help|-h|--version|version|help|list)([[:space:]]|$)' >/dev/null
}

is_placeholder_command() {
    cmd="$1"
    if printf '%s' "$cmd" | grep -E '<[^>]+>' >/dev/null; then
        return 0
    fi
    if printf '%s' "$cmd" | grep -E '\[[^]]+\]' >/dev/null; then
        return 0
    fi
    if printf '%s' "$cmd" | grep -E '\{\{[^}]+\}\}' >/dev/null; then
        return 0
    fi
    if printf '%s' "$cmd" | grep -E '\$\{[A-Za-z_][A-Za-z0-9_]*\}|\$[A-Za-z_][A-Za-z0-9_]*' >/dev/null; then
        return 0
    fi
    if printf '%s' "$cmd" | grep -E '(^|[[:space:]])(path/to/|owner/repo)([[:space:]]|$)' >/dev/null; then
        return 0
    fi
    return 1
}

is_unsafe_syntax() {
    cmd="$1"
    scrubbed=$(printf '%s' "$cmd" | sed -E 's#<[^>]+>##g')
    if printf '%s' "$scrubbed" | grep -E '[|;&]' >/dev/null; then
        return 0
    fi
    if printf '%s' "$scrubbed" | grep '\$(' >/dev/null; then
        return 0
    fi
    if printf '%s' "$scrubbed" | grep '`' >/dev/null; then
        return 0
    fi
    if printf '%s' "$scrubbed" | grep -E '[[:space:]]>[[:space:]]|[[:space:]]<[[:space:]]|>>|<<' >/dev/null; then
        return 0
    fi
    return 1
}

reason_text() {
    code="$1"
    case "$code" in
        placeholder_token) echo "contains placeholder or unresolved variable" ;;
        unsafe_operator) echo "contains shell operators or unsafe syntax" ;;
        nonlocal_without_cli) echo "non-local command requires --cli for validation" ;;
        not_safe_form) echo "not safe for direct execution" ;;
        missing_local_target) echo "referenced local target does not exist" ;;
        unknown_option) echo "runtime reported unknown option/subcommand" ;;
        fragment_only) echo "command fragment or assignment-only line" ;;
        non_executable_target) echo "referenced local target is not executable" ;;
        no_command) echo "no executable command detected" ;;
        fallback_failed) echo "fallback verification failed" ;;
        timeout_exceeded) echo "command exceeded execution timeout" ;;
        *) echo "" ;;
    esac
}

is_unknown_option_error() {
    input_line="$1"
    printf '%s' "$input_line" | grep -iE 'unknown option|unknown flag|unrecognized option|invalid option|unexpected argument|unknown subcommand|unknown command' >/dev/null
}

run_command() {
    run_cmd="$1"
    run_out_file=$(mktemp)
    timeout_flag=$(mktemp)
    rm -f "$timeout_flag"
    run_pgid=""

    if command -v setsid >/dev/null 2>&1; then
        # Launch setsid directly in the background so run_pid tracks the
        # session/process-group leader and timeout cleanup can signal -run_pgid.
        setsid sh -c "$run_cmd" >"$run_out_file" 2>&1 &
        run_pid=$!
        run_pgid="$run_pid"
    else
        (
            set +e
            # Command candidates already pass placeholder and unsafe syntax filters.
            # Use a nested shell to preserve quoted argument grouping for deterministic checks.
            sh -c "$run_cmd"
        ) >"$run_out_file" 2>&1 &
        run_pid=$!
    fi

    (
        sleep "$TIMEOUT_SECONDS"
        if kill -0 "$run_pid" 2>/dev/null; then
            echo "1" > "$timeout_flag"
            if [ -n "$run_pgid" ]; then
                kill -TERM "-$run_pgid" 2>/dev/null || true
            else
                kill "$run_pid" 2>/dev/null || true
            fi
            sleep 1
            if [ -n "$run_pgid" ]; then
                kill -KILL "-$run_pgid" 2>/dev/null || true
            else
                kill -9 "$run_pid" 2>/dev/null || true
            fi
        fi
    ) &
    watchdog_pid=$!

    set +e
    wait "$run_pid"
    run_status=$?
    set -e

    kill "$watchdog_pid" 2>/dev/null || true
    wait "$watchdog_pid" 2>/dev/null || true

    run_out=$(cat "$run_out_file")
    if [ -s "$timeout_flag" ]; then
        run_status=124
        timeout_line="error: command timed out after ${TIMEOUT_SECONDS}s"
        if [ -n "$run_out" ]; then
            run_out=$(printf '%s\n%s' "$run_out" "$timeout_line")
        else
            run_out="$timeout_line"
        fi
    fi

    rm -f "$run_out_file" "$timeout_flag"

    first_line=$(printf '%s\n' "$run_out" | head -1 | tr '\t' ' ')
    printf '%s\t%s\n' "$run_status" "$first_line"
}

resolve_local_path() {
    token_raw="$1"
    token=$(strip_quotes "$token_raw")

    case "$token" in
        "$SKILL_DIR"/*)
            printf '%s' "$token"
            ;;
        scripts/*)
            printf '%s/%s' "$SKILL_DIR" "$token"
            ;;
        ./scripts/*)
            stripped=${token#./}
            printf '%s/%s' "$SKILL_DIR" "$stripped"
            ;;
        *)
            printf ''
            ;;
    esac
}

: > "$tmp_results"

while IFS= read -r candidate_row; do
    file=$(printf '%s' "$candidate_row" | awk -F '\t' '{print $1}')
    line=$(printf '%s' "$candidate_row" | awk -F '\t' '{print $2}')
    kind=$(printf '%s' "$candidate_row" | awk -F '\t' '{print $3}')
    cmd=$(printf '%s' "$candidate_row" | awk -F '\t' '{print $4}')
    before=$(printf '%s' "$candidate_row" | awk -F '\t' '{print $5}')
    after=$(printf '%s' "$candidate_row" | awk -F '\t' '{print $6}')
    raw=$(printf '%s' "$candidate_row" | awk -F '\t' '{print $7}')
    [ -z "$cmd" ] && continue

    status=""
    exit_code=""
    first_line=""
    reason_code=""
    reason=""
    verification_mode="none"

    normalized=$(normalize_command "$cmd")

    # Parse command and strip assignment prefix while preserving quoted spacing.
    set --
    while IFS= read -r tok; do
        [ -z "$tok" ] && continue
        set -- "$@" "$tok"
    done <<EOF
$(tokenize_command "$normalized")
EOF

    assign_count=0
    assignment_prefix=""
    while [ $# -gt 0 ] && is_assignment_token "$1"; do
        if [ -n "$assignment_prefix" ]; then
            assignment_prefix="$assignment_prefix $1"
        else
            assignment_prefix="$1"
        fi
        assign_count=$((assign_count + 1))
        shift
    done

    if [ $# -eq 0 ]; then
        status="unsafe-skipped"
        reason_code="fragment_only"
        reason=$(reason_text "$reason_code")
    else
        exec_bin=$(strip_quotes "$1")
        shift || true
        arg1=$(strip_quotes "${1-}")
        cli_args="$*"

        local_target=""
        invoke_prefix=""

        case "$exec_bin" in
            bash|sh|python|python3)
                if [ -n "$arg1" ]; then
                    maybe=$(resolve_local_path "$arg1")
                    if [ -n "$maybe" ]; then
                        local_target="$maybe"
                        invoke_prefix="$exec_bin"
                    fi
                fi
                ;;
            *)
                maybe=$(resolve_local_path "$exec_bin")
                if [ -n "$maybe" ]; then
                    local_target="$maybe"
                    invoke_prefix=""
                fi
                ;;
        esac

        placeholder=0
        if is_placeholder_command "$normalized"; then
            placeholder=1
        fi

        unsafe=0
        if is_unsafe_syntax "$normalized"; then
            unsafe=1
        fi

        safe_direct=0
        if has_safe_indicator "$normalized"; then
            safe_direct=1
        fi

        # Direct execution for safe commands.
        if [ "$placeholder" -eq 0 ] && [ "$unsafe" -eq 0 ] && [ "$safe_direct" -eq 1 ]; then
            direct_cmd=""

            if [ -n "$local_target" ]; then
                if [ -f "$local_target" ]; then
                    if [ -n "$invoke_prefix" ]; then
                        remaining_after_local=$(printf '%s\n' "$cli_args" | awk '{ $1=""; sub(/^ /, ""); print }')
                        if [ -n "$remaining_after_local" ]; then
                            direct_cmd="$invoke_prefix $local_target $remaining_after_local"
                        else
                            direct_cmd="$invoke_prefix $local_target"
                        fi
                    elif [ -x "$local_target" ]; then
                        if [ -n "$cli_args" ]; then
                            direct_cmd="$local_target $cli_args"
                        else
                            direct_cmd="$local_target"
                        fi
                    else
                        status="unsafe-skipped"
                        reason_code="non_executable_target"
                        reason=$(reason_text "$reason_code")
                    fi
                fi
            elif [ -n "$CLI_BIN" ]; then
                if [ -n "$cli_args" ]; then
                    direct_cmd="$CLI_BIN $cli_args"
                else
                    direct_cmd="$CLI_BIN"
                fi
            fi

            if [ -n "$direct_cmd" ]; then
                if [ -n "$assignment_prefix" ]; then
                    direct_cmd="$assignment_prefix $direct_cmd"
                fi
                run_result=$(run_command "$direct_cmd")
                exit_code=$(printf '%s' "$run_result" | awk -F '\t' '{print $1}')
                first_line=$(printf '%s' "$run_result" | awk -F '\t' '{sub(/^[^\t]*\t/, ""); print}')
                verification_mode="direct"

                if [ "$exit_code" -eq 0 ] 2>/dev/null; then
                    status="executed"
                elif [ "$exit_code" -eq 124 ] 2>/dev/null; then
                    status="runtime-failed"
                    reason_code="timeout_exceeded"
                    reason=$(reason_text "$reason_code")
                elif is_unknown_option_error "$first_line"; then
                    status="flag-drift"
                    reason_code="unknown_option"
                    reason=$(reason_text "$reason_code")
                else
                    status="runtime-failed"
                fi
            fi
        fi

        # Fallback verification path.
        if [ -z "$status" ]; then
            if [ -n "$local_target" ]; then
                if [ ! -f "$local_target" ]; then
                    status="missing-target"
                    reason_code="missing_local_target"
                    reason=$(reason_text "$reason_code")
                elif [ -z "$invoke_prefix" ] && [ ! -x "$local_target" ]; then
                    status="unsafe-skipped"
                    reason_code="non_executable_target"
                    reason=$(reason_text "$reason_code")
                else
                    if [ -n "$invoke_prefix" ]; then
                        fallback_cmd="$invoke_prefix $local_target --help"
                    else
                        fallback_cmd="$local_target --help"
                    fi
                    if [ -n "$assignment_prefix" ]; then
                        fallback_cmd="$assignment_prefix $fallback_cmd"
                    fi

                    run_result=$(run_command "$fallback_cmd")
                    exit_code=$(printf '%s' "$run_result" | awk -F '\t' '{print $1}')
                    first_line=$(printf '%s' "$run_result" | awk -F '\t' '{sub(/^[^\t]*\t/, ""); print}')
                    verification_mode="help-fallback"

                    if [ "$exit_code" -eq 0 ] 2>/dev/null; then
                        status="executed"
                    elif [ "$exit_code" -eq 124 ] 2>/dev/null; then
                        status="runtime-failed"
                        reason_code="timeout_exceeded"
                        reason=$(reason_text "$reason_code")
                    elif is_unknown_option_error "$first_line"; then
                        status="flag-drift"
                        reason_code="unknown_option"
                        reason=$(reason_text "$reason_code")
                    else
                        status="runtime-failed"
                        reason_code="fallback_failed"
                        reason=$(reason_text "$reason_code")
                    fi
                fi
            elif [ -n "$CLI_BIN" ]; then
                fallback_cmd=""
                subcmd=""
                if [ -n "$arg1" ] && ! printf '%s' "$arg1" | grep -E '^-' >/dev/null && ! is_placeholder_command "$arg1"; then
                    subcmd="$arg1"
                fi

                if [ "$placeholder" -eq 0 ] && [ "$unsafe" -eq 0 ] && [ "$safe_direct" -eq 1 ]; then
                    if [ -n "$cli_args" ]; then
                        fallback_cmd="$CLI_BIN $cli_args"
                    else
                        fallback_cmd="$CLI_BIN --help"
                    fi
                    verification_mode="direct"
                elif [ -n "$subcmd" ]; then
                    fallback_cmd="$CLI_BIN $subcmd --help"
                    verification_mode="subcommand-help"
                else
                    fallback_cmd="$CLI_BIN --help"
                    verification_mode="help-fallback"
                fi

                if [ -n "$assignment_prefix" ]; then
                    fallback_cmd="$assignment_prefix $fallback_cmd"
                fi

                run_result=$(run_command "$fallback_cmd")
                exit_code=$(printf '%s' "$run_result" | awk -F '\t' '{print $1}')
                first_line=$(printf '%s' "$run_result" | awk -F '\t' '{sub(/^[^\t]*\t/, ""); print}')

                if [ "$exit_code" -eq 0 ] 2>/dev/null; then
                    status="executed"
                elif [ "$exit_code" -eq 124 ] 2>/dev/null; then
                    status="runtime-failed"
                    reason_code="timeout_exceeded"
                    reason=$(reason_text "$reason_code")
                elif is_unknown_option_error "$first_line"; then
                    status="flag-drift"
                    reason_code="unknown_option"
                    reason=$(reason_text "$reason_code")
                else
                    status="runtime-failed"
                    reason_code="fallback_failed"
                    reason=$(reason_text "$reason_code")
                fi
            else
                if [ "$placeholder" -eq 1 ]; then
                    status="placeholder-skipped"
                    reason_code="placeholder_token"
                    reason=$(reason_text "$reason_code")
                elif [ "$unsafe" -eq 1 ]; then
                    status="unsafe-skipped"
                    reason_code="unsafe_operator"
                    reason=$(reason_text "$reason_code")
                else
                    status="unsafe-skipped"
                    reason_code="nonlocal_without_cli"
                    reason=$(reason_text "$reason_code")
                fi
            fi
        fi
    fi

    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$file" "$line" "$kind" "$status" "$exit_code" "$cmd" "$first_line" "$before" "$after" "$reason" "$reason_code" "$normalized" "$verification_mode" "$raw" >> "$tmp_results"
done < "$tmp_candidates"

count_status() {
    s="$1"
    awk -F '\t' -v status="$s" '$4 == status { c++ } END { print c + 0 }' "$tmp_results"
}

count_mode() {
    m="$1"
    awk -F '\t' -v mode="$m" '$13 == mode && $4 == "executed" { c++ } END { print c + 0 }' "$tmp_results"
}

count_kind() {
    k="$1"
    awk -F '\t' -v kind="$k" '$3 == kind { c++ } END { print c + 0 }' "$tmp_results"
}

total_examples=$(wc -l < "$tmp_results" | tr -d ' ')
executed=$(count_status "executed")
runtime_failed=$(count_status "runtime-failed")
missing_target=$(count_status "missing-target")
flag_drift=$(count_status "flag-drift")
unsafe_skipped=$(count_status "unsafe-skipped")
placeholder_skipped=$(count_status "placeholder-skipped")
claim_compare_required="$executed"

executed_direct=$(count_mode "direct")
executed_help_fallback=$(count_mode "help-fallback")
executed_subcommand_help=$(count_mode "subcommand-help")
extracted_fenced=$(count_kind "fenced")
extracted_inline=$(count_kind "inline")

if [ "$FORMAT" = "text" ]; then
    printf '═══ Staleness Drift: %s ═══\n\n' "$DIR_NAME"
    echo "── Summary ──"
    echo "  Total extracted examples: $total_examples"
    echo "  Extracted fenced: $extracted_fenced"
    echo "  Extracted inline: $extracted_inline"
    echo "  Executed successfully: $executed"
    echo "    - Direct: $executed_direct"
    echo "    - Help fallback: $executed_help_fallback"
    echo "    - Subcommand help: $executed_subcommand_help"
    echo "  Runtime failures: $runtime_failed"
    echo "  Missing targets: $missing_target"
    echo "  Flag/subcommand drift: $flag_drift"
    echo "  Unsafe skipped: $unsafe_skipped"
    echo "  Placeholder skipped: $placeholder_skipped"
    echo "  Claim comparisons required: $claim_compare_required"

    if [ "$total_examples" -gt 0 ]; then
        echo ""
        echo "── Example Outcomes ──"
        awk -F '\t' '{
            rel = $1
            sub(/^.*\/skills\//, "skills/", rel)
            if (rel == $1) rel = $1
            printf "  - %s:%s [%s] %s", rel, $2, $3, $4
            if ($13 != "none") printf " (%s)", $13
            if ($6 != "") printf " :: %s", $6
            if ($7 != "") printf " => %s", $7
            if ($10 != "") printf " [%s]", $10
            printf "\n"
        }' "$tmp_results"
    fi

    echo ""
    echo "Done."
    exit 0
fi

awk -F '\t' \
    -v total_examples="$total_examples" \
    -v executed="$executed" \
    -v runtime_failed="$runtime_failed" \
    -v missing_target="$missing_target" \
    -v flag_drift="$flag_drift" \
    -v unsafe_skipped="$unsafe_skipped" \
    -v placeholder_skipped="$placeholder_skipped" \
    -v claim_compare_required="$claim_compare_required" \
    -v executed_direct="$executed_direct" \
    -v executed_help_fallback="$executed_help_fallback" \
    -v executed_subcommand_help="$executed_subcommand_help" \
    -v extracted_fenced="$extracted_fenced" \
    -v extracted_inline="$extracted_inline" '
    function esc(str,    s) {
        s = str
        gsub(/\\/, "\\\\", s)
        gsub(/"/, "\\\"", s)
        gsub(/\t/, "\\t", s)
        gsub(/\r/, "", s)
        gsub(/\n/, "\\n", s)
        return s
    }
    BEGIN {
        printf "{"
        printf "\"summary\":{"
        printf "\"total_examples\":%d,", total_examples
        printf "\"executed\":%d,", executed
        printf "\"runtime_failed\":%d,", runtime_failed
        printf "\"missing_target\":%d,", missing_target
        printf "\"flag_drift\":%d,", flag_drift
        printf "\"unsafe_skipped\":%d,", unsafe_skipped
        printf "\"placeholder_skipped\":%d,", placeholder_skipped
        printf "\"claim_compare_required\":%d,", claim_compare_required
        printf "\"executed_direct\":%d,", executed_direct
        printf "\"executed_help_fallback\":%d,", executed_help_fallback
        printf "\"executed_subcommand_help\":%d,", executed_subcommand_help
        printf "\"extracted_fenced\":%d,", extracted_fenced
        printf "\"extracted_inline\":%d", extracted_inline
        printf "},\"examples\":["
    }
    {
        if (NR > 1) printf ","
        printf "{"
        printf "\"file\":\"%s\",", esc($1)
        printf "\"line\":%d,", $2 + 0
        printf "\"kind\":\"%s\",", esc($3)
        printf "\"status\":\"%s\",", esc($4)
        if ($5 == "") printf "\"exit_code\":null,"; else printf "\"exit_code\":%d,", $5 + 0
        printf "\"command\":\"%s\",", esc($6)
        printf "\"first_line\":\"%s\",", esc($7)
        printf "\"claim_context_before\":\"%s\",", esc($8)
        printf "\"claim_context_after\":\"%s\",", esc($9)
        printf "\"reason\":\"%s\",", esc($10)
        printf "\"reason_code\":\"%s\",", esc($11)
        printf "\"normalized_command\":\"%s\",", esc($12)
        printf "\"verification_mode\":\"%s\",", esc($13)
        printf "\"raw_command\":\"%s\"", esc($14)
        printf "}"
    }
    END {
        printf "]}"
    }
' "$tmp_results"
printf '\n'
