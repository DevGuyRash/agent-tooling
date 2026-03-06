#!/usr/bin/env sh
# skill-auditor — Credential safety check (D25).
#
# Usage:
#   credential_check.sh <skill-directory>
#
# Scans for committed secret files, credential leakage in error output,
# eval on user input, and set -x near credential handling.

set -eu

case "${1-}" in
    -h|--help)
        echo "Usage: credential_check.sh <skill-directory>"
        echo ""
        echo "Checks credential safety:"
        echo "  - Committed secret files (.env, credentials.*, etc.)"
        echo "  - eval on user-provided input"
        echo "  - set -x near credential handling"
        echo "  - Credential patterns in error message strings"
        exit 0
        ;;
esac

if [ $# -lt 1 ]; then
    echo "Usage: credential_check.sh <skill-directory>"
    exit 1
fi

SKILL_DIR="$1"
if [ ! -d "$SKILL_DIR" ]; then
    echo "error: not a directory: $SKILL_DIR"
    exit 1
fi

DIR_NAME=$(basename "$SKILL_DIR")
printf '═══ Credential Safety Check: %s ═══\n\n' "$DIR_NAME"

total_issues=0

echo "── Secret File Detection ──"
secret_patterns=".env credentials.* *.secret* *.token* *.key *.pem *.p12 *.pfx"
found_secrets=0
for pattern in $secret_patterns; do
    matches=$(find "$SKILL_DIR" -name "$pattern" -not -path '*/.git/*' -not -path '*/node_modules/*' 2>/dev/null || true)
    if [ -n "$matches" ]; then
        printf '%s\n' "$matches" | while IFS= read -r f; do
            [ -z "$f" ] && continue
            relpath="${f#"$SKILL_DIR"/}"
            # Check if in .gitignore
            gitignore="$SKILL_DIR/.gitignore"
            if [ -f "$gitignore" ] && grep -qF "$relpath" "$gitignore" 2>/dev/null; then
                echo "  ✓ $relpath — in .gitignore"
            else
                echo "  ✗ $relpath — potential secret file not in .gitignore [BLOCKER]"
                found_secrets=1
            fi
        done
    fi
done
if [ "$found_secrets" -gt 0 ]; then
    total_issues=$((total_issues + 1))
else
    echo "  ✓ No committed secret files detected"
fi

echo ""
echo "── Eval Usage ──"
scripts_dir="$SKILL_DIR/scripts"
if [ -d "$scripts_dir" ]; then
    eval_found=0
    for script in "$scripts_dir"/*.sh; do
        [ -f "$script" ] || continue
        relpath="${script#"$SKILL_DIR"/}"

        # Check for actual eval statements on executable lines (not comments or strings)
        eval_hits=$(awk '
            /^[[:space:]]*#/ { next }
            /^[[:space:]]*echo / { next }
            /^[[:space:]]*printf / { next }
            /(^|[[:space:]])eval[[:space:]]/ { print NR ": " $0 }
        ' "$script" 2>/dev/null | head -3 || true)
        if [ -n "$eval_hits" ]; then
            echo "  ✗ $relpath — uses eval [MAJOR]:"
            printf '%s\n' "$eval_hits" | while IFS= read -r line; do
                echo "      $line"
            done
            eval_found=1
            total_issues=$((total_issues + 1))
        fi
    done
    if [ "$eval_found" -eq 0 ]; then
        echo "  ✓ No eval usage detected in scripts"
    fi
else
    echo "  ℹ No scripts/ directory found"
fi

echo ""
echo "── Debug Tracing (set -x) ──"
if [ -d "$scripts_dir" ]; then
    setx_found=0
    for script in "$scripts_dir"/*.sh; do
        [ -f "$script" ] || continue
        relpath="${script#"$SKILL_DIR"/}"

        # Check for actual set -x on executable lines (not in comments/strings)
        setx_hits=$(awk '
            /^[[:space:]]*#/ { next }
            /^[[:space:]]*echo / { next }
            /^[[:space:]]*printf / { next }
            /(^|[[:space:]])set[[:space:]]+-[a-z]*x/ { print NR ": " $0 }
        ' "$script" 2>/dev/null | head -3 || true)
        if [ -n "$setx_hits" ]; then
            echo "  ⚠ $relpath — uses set -x (debug tracing) [MINOR]:"
            printf '%s\n' "$setx_hits" | head -3 | while IFS= read -r line; do
                echo "      $line"
            done
            setx_found=1
            total_issues=$((total_issues + 1))
        fi
    done
    if [ "$setx_found" -eq 0 ]; then
        echo "  ✓ No set -x debug tracing in shipped scripts"
    fi
fi

echo ""
echo "── Credential Pattern in Error Strings ──"
if [ -d "$scripts_dir" ]; then
    cred_leak=0
    for script in "$scripts_dir"/*.sh; do
        [ -f "$script" ] || continue
        relpath="${script#"$SKILL_DIR"/}"

        # Skip self to avoid matching our own detection patterns
        case "$(basename "$script")" in credential_check.sh) continue ;; esac

        # Check for credential-like patterns in echo/printf output.
        # Use narrow patterns to avoid false positives on "tokens" (token counting)
        # and "credentials" (in documentation strings describing checks).
        cred_hits=$(awk '
            /^[[:space:]]*#/ { next }
            /(echo|printf)/ && /(password|api.key|bearer|authorization|secret.key)/ {
                print NR ": " $0
            }
        ' "$script" 2>/dev/null | head -3 || true)
        if [ -n "$cred_hits" ]; then
            echo "  ⚠ $relpath — potential credential leak in output [MAJOR]:"
            printf '%s\n' "$cred_hits" | while IFS= read -r line; do
                echo "      $line"
            done
            cred_leak=1
            total_issues=$((total_issues + 1))
        fi
    done
    if [ "$cred_leak" -eq 0 ]; then
        echo "  ✓ No credential patterns in error output strings"
    fi
fi

echo ""
echo "── Summary ──"
echo "  Issues found: $total_issues"

echo ""
echo "Done."

if [ "$total_issues" -gt 0 ]; then
    exit 1
fi
