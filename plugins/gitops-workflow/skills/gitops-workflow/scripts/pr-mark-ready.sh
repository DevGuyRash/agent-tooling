#!/usr/bin/env bash
# gitops-catalog: {"id":"pr-ready","topic":"pr","command":"mark pr ready","phrases":["mark pr ready","pr ready"],"summary":"Run strict readiness gates before moving a draft PR to ready.","script":"pr-mark-ready.sh","creates_branch":false,"creates_worktree":false,"creates_pr":false,"mutates_history":false,"stays_on_current_branch":true,"supports_json":false}
set -euo pipefail

# pr-mark-ready.sh - Deterministically mark a draft PR as ready after a strict readiness audit.
#
# Usage:
#   bash scripts/pr-mark-ready.sh <pr_number> [--repo owner/repo] [--watch-checks]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

print_help() {
  cat <<'USAGE'
Usage:
  bash scripts/pr-mark-ready.sh <pr_number> [--repo owner/repo] [--watch-checks]
USAGE
}

PR_NUMBER="${1:-}"
if [[ -z "$PR_NUMBER" || "$PR_NUMBER" == "-h" || "$PR_NUMBER" == "--help" ]]; then
  print_help
  exit 0
fi
shift || true

REPO=""
WATCH_CHECKS="false"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      require_opt_value "--repo" "${2:-}"
      REPO="${2:-}"
      shift 2
      ;;
    --watch-checks)
      WATCH_CHECKS="true"
      shift
      ;;
    -h|--help)
      print_help
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

require_cmd gh
require_cmd python3

REPORT_JSON="$(mktemp)"
trap 'rm -f "$REPORT_JSON" "$REPORT_JSON.err"' EXIT

REPORT_ARGS=(python3 "$SCRIPT_DIR/pr-readiness-report.py" "$PR_NUMBER" --local-repo "$(pwd -P)" --scope tree --json)
if [[ -n "$REPO" ]]; then
  REPORT_ARGS+=(--repo "$REPO")
fi
if [[ "$WATCH_CHECKS" == "true" ]]; then
  REPORT_ARGS+=(--watch-checks)
fi

if ! "${REPORT_ARGS[@]}" >"$REPORT_JSON" 2>"$REPORT_JSON.err"; then
  err_text="$(compact_text "$(cat "$REPORT_JSON.err" 2>/dev/null)")"
  die "${err_text:-failed to generate readiness report}"
fi

python3 - "$REPORT_JSON" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
pr = payload["pr"]
ci = payload["ci"]
reviews = payload["reviews"]
branch = payload["branch_state"]
readiness = payload["readiness"]
print("== Readiness report ==")
print(f"PR #{pr['number']}: {pr['title']}")
print(f"draft: {'yes' if pr['is_draft'] else 'no'}")
print(
    f"checks: {ci['status']} (passed={ci['counts']['passed']}, pending={ci['counts']['pending']}, failed={ci['counts']['failed']})"
)
print(
    f"reviews: decision={reviews['decision']}, unresolved_threads={reviews['unresolved_thread_count']}, approvals={reviews['approval_count']}"
)
print(f"branch: {branch.get('status', 'unavailable')} ({branch.get('branch', 'unknown')})")
print(f"tree: {payload['tree_state']['status']} ({payload['tree_state']['scope']})")
if readiness.get("blocking_reasons"):
    print("blockers:")
    for reason in readiness["blocking_reasons"]:
        print(f"- {reason}")
elif readiness.get("attention_items"):
    print("notes:")
    for item in readiness["attention_items"]:
        print(f"- {item}")
print(f"next: {payload['next_action']}")
PY

mapfile -t report_meta < <(python3 - "$REPORT_JSON" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
pr = payload["pr"]
readiness = payload["readiness"]
print("true" if pr.get("is_draft") else "false")
print("true" if readiness.get("safe_to_mark_ready") else "false")
print(payload.get("next_action", ""))
PY
)

IS_DRAFT="${report_meta[0]:-false}"
SAFE_TO_MARK_READY="${report_meta[1]:-false}"
NEXT_ACTION="${report_meta[2]:-}"

if [[ "$IS_DRAFT" != "true" ]]; then
  echo "PR #$PR_NUMBER is already ready for review."
  exit 0
fi

if [[ "$SAFE_TO_MARK_READY" != "true" ]]; then
  echo "PR #$PR_NUMBER is not safe to mark ready." >&2
  [[ -n "$NEXT_ACTION" ]] && echo "Next: $NEXT_ACTION" >&2
  exit 3
fi

READY_ARGS=("$PR_NUMBER")
if [[ -n "$REPO" ]]; then
  READY_ARGS+=(--repo "$REPO")
fi

echo

echo "== Marking PR ready =="
gh pr ready "${READY_ARGS[@]}"
echo "PR #$PR_NUMBER marked ready for review."
