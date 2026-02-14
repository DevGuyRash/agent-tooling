#!/usr/bin/env bash
set -euo pipefail

# governance-enforce.sh - Deterministic governance reconciliation sequence.
#
# Usage:
#   bash scripts/governance-enforce.sh [--policy path] [--repo owner/repo] [--no-write-codeowners]
#
# Behavior:
# - Runs validate -> plan -> apply -> audit in order.
# - Accepts plan drift exit code 3 and proceeds to apply.

die() {
  echo "Error: $*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

require_cmd python3

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_POLICY="$SCRIPT_DIR/../assets/config/github-governance-policy.v1.json"

POLICY="$DEFAULT_POLICY"
REPO=""
WRITE_CODEOWNERS="true"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --policy)
      POLICY="${2:-}"
      shift 2
      ;;
    --repo)
      REPO="${2:-}"
      shift 2
      ;;
    --no-write-codeowners)
      WRITE_CODEOWNERS="false"
      shift
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

COMMON_ARGS=(--policy "$POLICY")
if [[ -n "$REPO" ]]; then
  COMMON_ARGS+=(--repo "$REPO")
fi

echo "== validate =="
python3 "$SCRIPT_DIR/repo-governance.py" validate --policy "$POLICY"
echo ""

echo "== plan =="
PLAN_CODE=0
python3 "$SCRIPT_DIR/repo-governance.py" plan "${COMMON_ARGS[@]}" || PLAN_CODE=$?
if [[ "$PLAN_CODE" -ne 0 && "$PLAN_CODE" -ne 3 ]]; then
  exit "$PLAN_CODE"
fi
echo ""

echo "== apply =="
APPLY_ARGS=("${COMMON_ARGS[@]}")
if [[ "$WRITE_CODEOWNERS" == "true" ]]; then
  APPLY_ARGS+=(--write-codeowners)
fi
python3 "$SCRIPT_DIR/repo-governance.py" apply "${APPLY_ARGS[@]}"
echo ""

echo "== audit =="
python3 "$SCRIPT_DIR/repo-governance.py" audit "${COMMON_ARGS[@]}" --format json
