#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"
# shellcheck source=lib/git-state.sh
source "$SCRIPT_DIR/lib/git-state.sh"
# shellcheck source=lib/router.sh
source "$SCRIPT_DIR/lib/router.sh"

REPO_PATH="$(pwd -P)"
JSON="false"
SCOPE="tree"
DETACHED_MODE="recover"
RESULTS_FILE=""

print_help() {
  cat <<'USAGE'
Usage:
  bash scripts/recover-repo-state.sh [--repo <path>] [--json] [--no-recurse-related] [--no-detached-recovery]

Behavior:
  - Detects active sequencer or detached-HEAD state.
  - Applies safe automatic recovery where supported.
  - Stops on rescue-grade or blocked states and reports exact next actions.

Options:
  --repo <path>          Repository path to inspect (default: current directory).
  --json                 Emit machine-readable JSON.
  --no-recurse-related   Recover only the current repo, not the full related tree.
  --no-detached-recovery Refuse detached HEAD instead of attempting safe recovery.
  -h, --help             Show help.
USAGE
}

emit_json() {
  local file="$1"
  local continued="$2"
  python3 - "$file" "$SCOPE" "$continued" <<'PY'
import json
import sys
from pathlib import Path

items = []
for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    repo, prior_state, recovery_action, outcome, continued, next_action, branch, fetch_status, fetch_note, fetch_transport_attempts, fetch_transport_used, fetch_fallback_reason, fetch_remote_url_kind = line.split("\t", 12)
    items.append(
        {
            "repo": repo,
            "prior_state": prior_state,
            "recovery_action": recovery_action,
            "outcome": outcome,
            "continued": continued == "true",
            "next_action": next_action,
            "branch": branch,
            "fetch_status": fetch_status,
            "fetch_note": fetch_note,
            "fetch_transport_attempts": [x for x in fetch_transport_attempts.split(",") if x],
            "fetch_transport_used": fetch_transport_used,
            "fetch_fallback_reason": fetch_fallback_reason,
            "fetch_remote_url_kind": fetch_remote_url_kind,
        }
    )
print(json.dumps({"scope": sys.argv[2], "continued": sys.argv[3] == "true", "results": items}, indent=2))
PY
}

record_result() {
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$1" "$2" "$3" "$4" "$5" "$6" "$7" "$8" "$9" "${10}" "${11}" "${12}" "${13}" >> "$RESULTS_FILE"
}

render_human() {
  local file="$1"
  local overall="$2"
  echo "Scope: $SCOPE"
  echo "Continued: $overall"
  while IFS=$'\t' read -r repo prior_state recovery_action outcome continued next_action branch fetch_status fetch_note fetch_transport_attempts fetch_transport_used fetch_fallback_reason fetch_remote_url_kind; do
    echo ""
    echo "$repo"
    echo "  prior: ${prior_state:-clean}"
    echo "  action: $recovery_action"
    echo "  outcome: $outcome"
    [[ -n "$branch" ]] && echo "  branch: $branch"
    [[ "$fetch_status" != "not-run" ]] && echo "  fetch: $fetch_status"
    [[ -n "$fetch_transport_attempts" ]] && echo "  fetch transport: ${fetch_transport_used:-none} (attempts ${fetch_transport_attempts})"
    [[ -n "$fetch_fallback_reason" ]] && echo "  fetch fallback: $fetch_fallback_reason"
    [[ -n "$fetch_note" ]] && echo "  fetch note: $fetch_note"
    echo "  next: $next_action"
  done < "$file"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      require_opt_value "--repo" "${2:-}"
      REPO_PATH="${2:-}"
      shift 2
      ;;
    --json)
      JSON="true"
      shift
      ;;
    --no-recurse-related)
      SCOPE="current"
      shift
      ;;
    --no-detached-recovery)
      DETACHED_MODE="off"
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

require_cmd git
require_cmd python3

if ! git -C "$REPO_PATH" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  die "--repo is not a git repository: $REPO_PATH"
fi

RESULTS_FILE="$(mktemp)"
trap 'rm -f "$RESULTS_FILE"' EXIT

overall_continued="true"
if [[ "$SCOPE" == "tree" ]]; then
  mapfile -t repos < <(gitops_scope_paths "$REPO_PATH" tree desc)
else
  repos=("$(repo_root_path "$REPO_PATH")")
fi

for repo in "${repos[@]}"; do
  gitops_prepare_repo_for_stateful_command "$repo" "$DETACHED_MODE" || true
  outcome="$GITOPS_RECOVERY_OUTCOME"
  continued="$GITOPS_RECOVERY_CONTINUED"
  next_action="$GITOPS_RECOVERY_NEXT_ACTION"
  branch="$GITOPS_RECOVERED_BRANCH"
  if [[ "$continued" != "true" ]]; then
    overall_continued="false"
  fi
  record_result \
    "$repo" \
    "$GITOPS_RECOVERY_PRIOR_STATE" \
    "$GITOPS_RECOVERY_ACTION" \
    "$outcome" \
    "$continued" \
    "$next_action" \
    "$branch" \
    "$GITOPS_FETCH_STATUS" \
    "$GITOPS_FETCH_NOTE" \
    "${GITOPS_FETCH_TRANSPORT_ATTEMPTS:-}" \
    "${GITOPS_FETCH_TRANSPORT_USED:-}" \
    "${GITOPS_FETCH_FALLBACK_REASON:-}" \
    "${GITOPS_FETCH_REMOTE_URL_KIND:-}"
done

if [[ "$JSON" == "true" ]]; then
  emit_json "$RESULTS_FILE" "$overall_continued"
else
  render_human "$RESULTS_FILE" "$overall_continued"
fi

if [[ "$overall_continued" != "true" ]]; then
  exit 2
fi
