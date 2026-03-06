#!/usr/bin/env sh
# skill-auditor — AGENTS adherence coverage check (D20).
#
# Usage:
#   adherence_check.sh <skill-directory>
#
# Verifies that AGENTS-inspired progressive disclosure guidance is absorbed
# into the auditor's own docs and check surface.

set -eu

case "${1-}" in
    -h|--help)
        echo "Usage: adherence_check.sh <skill-directory>"
        echo ""
        echo "Checks AGENTS.md rule absorption for:"
        echo "  - CLI-served self-documentation coverage"
        echo "  - Router CLI + fallback documentation"
        echo "  - Manifest/script coverage for D20 and D22"
        exit 0
        ;;
esac

if [ $# -lt 1 ]; then
    echo "Usage: adherence_check.sh <skill-directory>"
    exit 1
fi

SKILL_DIR="${1%/}"
if [ ! -d "$SKILL_DIR" ]; then
    echo "error: not a directory: $SKILL_DIR"
    exit 1
fi

ROOT_DIR=$(cd "$SKILL_DIR/../.." && pwd)
AGENTS_FILE="$ROOT_DIR/AGENTS.md"
SKILL_FILE="$SKILL_DIR/SKILL.md"
MANIFEST_FILE="$SKILL_DIR/scripts/audit-skill.toml"
DOMAINS_FILE="$SKILL_DIR/references/domains-analysis.md"

issues=0

echo "═══ Adherence Check: $(basename "$SKILL_DIR") ═══"
echo ""

echo "── AGENTS Absorption ──"
if [ ! -f "$AGENTS_FILE" ]; then
    echo "  ⚠ AGENTS.md not found at repo root: $AGENTS_FILE [MINOR]"
    issues=$((issues + 1))
else
    if grep -q 'CLI-served self-documentation' "$AGENTS_FILE"; then
        echo "  ✓ AGENTS.md documents CLI-served self-documentation"
    else
        echo "  ✗ AGENTS.md lacks the CLI-served self-documentation section [MAJOR]"
        issues=$((issues + 1))
    fi
fi

echo ""
echo "── Skill Router Contract ──"
if grep -q 'audit-skill next-steps' "$SKILL_FILE" && grep -q 'audit-skill step <N>' "$SKILL_FILE"; then
    echo "  ✓ SKILL.md documents next-steps and step guidance"
else
    echo "  ✗ SKILL.md does not document both next-steps and step guidance [MAJOR]"
    issues=$((issues + 1))
fi

if grep -Eqi 'IF the CLI is unavailable|fallback' "$SKILL_FILE"; then
    echo "  ✓ SKILL.md documents fallback guidance when the CLI is unavailable"
else
    echo "  ✗ SKILL.md lacks CLI fallback guidance [MAJOR]"
    issues=$((issues + 1))
fi

echo ""
echo "── Auditor Coverage ──"
if grep -q 'script = "scripts/adherence_check.sh"' "$MANIFEST_FILE"; then
    echo "  ✓ D20 uses adherence_check.sh"
else
    echo "  ✗ D20 does not map to adherence_check.sh in the manifest [MAJOR]"
    issues=$((issues + 1))
fi

if grep -Eqi 'next-step guidance|step-level guidance|step <N>' "$DOMAINS_FILE" \
    && { grep -Eqi 'CLI with no args prints usage|print usage showing available commands' "$DOMAINS_FILE" \
         || grep -Eqi 'CLI with no args prints usage|next-step guidance' "$MANIFEST_FILE"; }; then
    echo "  ✓ D22 documentation covers no-arg usage and next-step guidance"
else
    echo "  ✗ D22 documentation is missing CLI router guidance requirements [MINOR]"
    issues=$((issues + 1))
fi

echo ""
echo "── Summary ──"
echo "  Issues found: $issues"
echo ""
echo "Done."

if [ "$issues" -gt 0 ]; then
    exit 1
fi
