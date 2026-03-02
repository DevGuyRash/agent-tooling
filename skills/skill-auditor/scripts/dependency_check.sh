#!/usr/bin/env sh
# skill-auditor — Script self-containment / dependency check (D12).
#
# Usage:
#   dependency_check.sh <skill-directory>
#
# Checks scripts for undocumented external dependencies.

set -eu

case "${1-}" in
    -h|--help)
        echo "Usage: dependency_check.sh <skill-directory>"
        echo ""
        echo "Checks scripts for self-containment:"
        echo "  - External command usage in .sh scripts"
        echo "  - Import statements in .py scripts"
        echo "  - POSIX compliance (bashism detection)"
        echo "  - Dependency documentation"
        exit 0
        ;;
esac

if [ $# -lt 1 ]; then
    echo "Usage: dependency_check.sh <skill-directory>"
    exit 1
fi

SKILL_DIR="$1"
if [ ! -d "$SKILL_DIR" ]; then
    echo "error: not a directory: $SKILL_DIR"
    exit 1
fi

DIR_NAME=$(basename "$SKILL_DIR")
printf '═══ Dependency Check: %s ═══\n\n' "$DIR_NAME"

# POSIX-standard commands that are always available
POSIX_CMDS="awk basename cat cd chmod cmp comm cp cut date dd df diff dirname du echo env expr false find fold grep head id kill ln ls mkdir mktemp mv od paste printf pwd read rm rmdir sed sh sleep sort split tail tee test touch tr true tty umask uname uniq wc xargs"

tmplist=$(mktemp)
trap 'rm -f "$tmplist"' EXIT INT TERM

scripts_dir="$SKILL_DIR/scripts"
if [ ! -d "$scripts_dir" ]; then
    echo "  ℹ No scripts/ directory found"
    echo ""
    echo "Done."
    exit 0
fi

find "$scripts_dir" -type f \( -name '*.sh' -o -name '*.py' \) 2>/dev/null | sort > "$tmplist"

echo "── Shell Script Analysis ──"

total_issues=0

while IFS= read -r script; do
    [ -z "$script" ] && continue
    relpath="${script#"$SKILL_DIR"/}"

    case "$script" in
        *.sh)
            echo ""
            echo "  File: $relpath"

            # Check shebang
            shebang=$(head -1 "$script")
            case "$shebang" in
                *bash*|*zsh*)
                    echo "    ⚠ Non-POSIX shebang: $shebang [MINOR]"
                    total_issues=$((total_issues + 1))
                    ;;
                *sh*)
                    echo "    ✓ POSIX shebang: $shebang"
                    ;;
                *)
                    echo "    ⚠ Unusual shebang: $shebang [MINOR]"
                    total_issues=$((total_issues + 1))
                    ;;
            esac

            # Detect bashisms. Inspect executable lines only so comments and
            # help text do not produce false positives.
            bashisms=$(awk '
                function strip_shell_strings(src,    out, i, ch, nextch, in_squote, in_dquote) {
                    out = ""
                    in_squote = 0
                    in_dquote = 0
                    for (i = 1; i <= length(src); i++) {
                        ch = substr(src, i, 1)
                        nextch = (i < length(src) ? substr(src, i + 1, 1) : "")
                        if (in_squote) {
                            if (ch == "'\''") in_squote = 0
                            continue
                        }
                        if (in_dquote) {
                            if (ch == "\\" && nextch != "") {
                                i++
                                continue
                            }
                            if (ch == "\"") in_dquote = 0
                            continue
                        }
                        if (ch == "'\''") {
                            in_squote = 1
                            continue
                        }
                        if (ch == "\"") {
                            in_dquote = 1
                            continue
                        }
                        out = out ch
                    }
                    return out
                }
                function awk_open_on_line(src, idx, tail) {
                    if (src !~ /(^|[^[:alnum:]_])awk([[:space:]]|$)/) return 0
                    if (src ~ /'\''[[:space:]]*$/) return 1
                    idx = index(src, "'\''")
                    if (idx == 0) return 0
                    tail = substr(src, idx + 1)
                    if (tail ~ /'\''/) return 2
                    return 1
                }
                function awk_close_on_line(src) {
                    return (src ~ /^[[:space:]]*'\''[[:space:]]*($|[;|&)]|[<>]|["$])/)
                }
                in_awk_pending {
                    idx = index($0, "'\''")
                    if (idx > 0) {
                        tail = substr($0, idx + 1)
                        in_awk_pending = 0
                        if (tail ~ /'\''/) {
                            next
                        }
                        in_awk = 1
                        next
                    }
                    if ($0 ~ /^[[:space:]]*$/) {
                        next
                    }
                    if ($0 ~ /\\[[:space:]]*$/) {
                        next
                    }
                    in_awk_pending = 0
                }
                in_awk {
                    if (awk_close_on_line($0)) {
                        in_awk = 0
                    }
                    next
                }
                {
                    awk_mode = awk_open_on_line($0)
                    if (awk_mode == 1) {
                        in_awk = 1
                        next
                    }
                    if (awk_mode == 2) {
                        next
                    }
                    if ($0 ~ /(^|[^[:alnum:]_])awk([[:space:]]|$)/ && $0 ~ /\\[[:space:]]*$/) {
                        in_awk_pending = 1
                        next
                    }
                }
                /^[[:space:]]*#/ { next }
                /^[[:space:]]*$/ { next }
                {
                    line = strip_shell_strings($0)
                }
                line ~ /\[\[/ ||
                line ~ /(^|[;&|[:space:]])source[[:space:]]/ ||
                line ~ /(^|[;&|[:space:]])(declare|typeset|select)[[:space:]]/ ||
                line ~ /^[[:space:]]*function[[:space:]]+[A-Za-z_]/ {
                    print NR ":" $0
                }
            ' "$script" 2>/dev/null | head -3 || true)
            if [ -n "$bashisms" ]; then
                echo "    ⚠ Bashisms detected [MINOR]:"
                printf '%s\n' "$bashisms" | while IFS= read -r bline; do
                    echo "      $bline"
                done
                total_issues=$((total_issues + 1))
            fi

            # Detect non-POSIX command dependencies using likely command
            # positions only. This avoids matching words inside comments,
            # strings, and embedded awk/sed programs.
            func_names=$(awk '
                /^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*[[:space:]]*\(\)[[:space:]]*\{/ {
                    line = $0
                    sub(/^[[:space:]]*/, "", line)
                    sub(/[[:space:]]*\(\).*/, "", line)
                    print line
                }
            ' "$script" 2>/dev/null | sort -u)

            ext_cmds=$(awk '
                function protect_quoted_spaces(src,    out, i, ch, nextch, in_squote, in_dquote) {
                    out = ""
                    in_squote = 0
                    in_dquote = 0
                    for (i = 1; i <= length(src); i++) {
                        ch = substr(src, i, 1)
                        nextch = (i < length(src) ? substr(src, i + 1, 1) : "")
                        if (in_squote) {
                            if (ch == sprintf("%c", 39)) {
                                in_squote = 0
                            }
                            if (ch ~ /[[:space:]]/) {
                                out = out "\034"
                            } else {
                                out = out ch
                            }
                            continue
                        }
                        if (in_dquote) {
                            if (ch == "\\" && nextch != "") {
                                out = out ch nextch
                                i++
                                continue
                            }
                            if (ch == "\"") {
                                in_dquote = 0
                            }
                            if (ch ~ /[[:space:]]/) {
                                out = out "\034"
                            } else {
                                out = out ch
                            }
                            continue
                        }
                        if (ch == sprintf("%c", 39)) {
                            in_squote = 1
                            out = out ch
                            continue
                        }
                        if (ch == "\"") {
                            in_dquote = 1
                            out = out ch
                            continue
                        }
                        out = out ch
                    }
                    return out
                }
                function awk_open_on_line(src, idx, tail) {
                    if (src !~ /(^|[^[:alnum:]_])awk([[:space:]]|$)/) return 0
                    if (src ~ /'\''[[:space:]]*$/) return 1
                    idx = index(src, "'\''")
                    if (idx == 0) return 0
                    tail = substr(src, idx + 1)
                    if (tail ~ /'\''/) return 2
                    return 1
                }
                function awk_close_on_line(src) {
                    return (src ~ /^[[:space:]]*'\''[[:space:]]*($|[;|&)]|[<>]|["$])/)
                }
                in_awk_pending {
                    idx = index($0, "'\''")
                    if (idx > 0) {
                        tail = substr($0, idx + 1)
                        in_awk_pending = 0
                        if (tail ~ /'\''/) {
                            next
                        }
                        in_awk = 1
                        next
                    }
                    if ($0 ~ /^[[:space:]]*$/) {
                        next
                    }
                    if ($0 ~ /\\[[:space:]]*$/) {
                        next
                    }
                    in_awk_pending = 0
                }
                in_awk {
                    if (awk_close_on_line($0)) {
                        in_awk = 0
                    }
                    next
                }
                {
                    awk_mode = awk_open_on_line($0)
                    if (awk_mode == 1) {
                        in_awk = 1
                        next
                    }
                    if (awk_mode == 2) {
                        next
                    }
                    if ($0 ~ /(^|[^[:alnum:]_])awk([[:space:]]|$)/ && $0 ~ /\\[[:space:]]*$/) {
                        in_awk_pending = 1
                        next
                    }
                }
                /^[[:space:]]*#/ { next }
                /^[[:space:]]*$/ { next }
                {
                    line = $0
                    sub(/[[:space:]]*#.*/, "", line)
                    gsub(/^[[:space:]]+/, "", line)
                    line = protect_quoted_spaces(line)

                    while (line ~ /^[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]+[[:space:]]+/) {
                        sub(/^[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]+[[:space:]]+/, "", line)
                    }
                    if (line ~ /^[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*$/) next
                    if (line ~ /^[[:space:]]*$/) next

                    if (line ~ /^if[[:space:]]+/) {
                        sub(/^if[[:space:]]+/, "", line)
                    } else if (line ~ /^while[[:space:]]+/) {
                        sub(/^while[[:space:]]+/, "", line)
                    } else if (line ~ /^!+[[:space:]]*/) {
                        sub(/^!+[[:space:]]*/, "", line)
                    }

                    split(line, fields, /[[:space:]]+/)
                    idx = 1

                    while (idx in fields && fields[idx] == "env") {
                        idx++
                        while (idx in fields && fields[idx] ~ /^-[A-Za-z-]+$/) idx++
                        while (idx in fields && fields[idx] ~ /^[A-Za-z_][A-Za-z0-9_]*=.*$/) idx++
                    }

                    cmd = fields[idx]
                    if (cmd ~ /^[a-z][a-z0-9_-]*$/) {
                        print cmd
                    }
                }
            ' "$script" 2>/dev/null | sort -u | while IFS= read -r cmd; do
                case "$cmd" in
                    ""|if|then|else|elif|fi|do|done|while|for|case|esac|in|return|exit|shift|set|unset|export|trap|continue|break|eval|exec|command|type|readonly)
                        continue
                        ;;
                esac

                is_posix=0
                for pcmd in $POSIX_CMDS; do
                    if [ "$cmd" = "$pcmd" ]; then
                        is_posix=1
                        break
                    fi
                done

                if printf '%s\n' "$func_names" | grep -Fx "$cmd" >/dev/null; then
                    continue
                fi

                if [ "$is_posix" -eq 0 ]; then
                    echo "$cmd"
                fi
            done | sort -u || true)

            if [ -n "$ext_cmds" ]; then
                echo "    External commands used (non-POSIX candidates):"
                # shellcheck disable=SC2086
                for ecmd in $(printf '%s\n' "$ext_cmds" | tr ' ' '\n' | sed '/^$/d' | sort -u); do
                    echo "      - $ecmd"
                done
            else
                echo "    ✓ No non-POSIX command dependencies detected"
            fi
            ;;

        *.py)
            echo ""
            echo "  File: $relpath"

            # Extract imports
            imports=$(grep -E '^\s*(import |from .* import )' "$script" 2>/dev/null | sort -u || true)
            if [ -n "$imports" ]; then
                echo "    Imports:"
                py_tmp=$(mktemp)
                printf '%s\n' "$imports" > "$py_tmp"
                while IFS= read -r imp; do
                    # Check if stdlib
                    mod=$(printf '%s' "$imp" | sed 's/^[[:space:]]*import //; s/^[[:space:]]*from //; s/ .*//; s/\..*//')
                    case "$mod" in
                        os|sys|json|re|pathlib|subprocess|shutil|argparse|collections|itertools|functools|typing|io|math|string|textwrap|datetime|time|hashlib|base64|urllib|http|tempfile|glob|fnmatch|csv|configparser|logging|unittest|dataclasses|enum|abc|contextlib|copy|operator|pprint|statistics)
                            echo "      ✓ $imp (stdlib)"
                            ;;
                        *)
                            echo "      ⚠ $imp (external — document in SKILL.md) [MINOR]"
                            total_issues=$((total_issues + 1))
                            ;;
                    esac
                done < "$py_tmp"
                rm -f "$py_tmp"
            else
                echo "    ✓ No imports"
            fi
            ;;
    esac
done < "$tmplist"

echo ""
echo "── Summary ──"
echo "  Issues found: $total_issues"

echo ""
echo "Done."
