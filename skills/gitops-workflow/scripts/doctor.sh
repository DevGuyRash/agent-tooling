#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

REPO_PATH="$(pwd -P)"
JSON="false"
FIX="false"
SCOPE="tree"
FETCH="true"
DETACHED_MODE="recover"
RECONCILE_JSON=""
RECONCILE_ERR=""

print_help() {
  cat <<'USAGE'
Usage:
  bash scripts/doctor.sh [fix] [--repo <path>] [--scope current|tree] [--json] [--no-fetch] [--no-detached-recovery]

Behavior:
  - `doctor` reports repo and related-tree health deterministically.
  - `doctor fix` applies safe automatic recovery and sync, then reports remaining reconciliation work.
  - Commit, push, and PR mutations are never performed from doctor mode.

Options:
  --repo <path>              Repository path (default: current directory).
  --scope <scope>            tree (default) or current.
  --json                     Emit machine-readable JSON.
  --no-fetch                 Skip fetch during the report-only phase.
  --no-detached-recovery     Refuse detached HEAD instead of attempting safe recovery.
  -h, --help                 Show help.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    fix)
      FIX="true"
      shift
      ;;
    --repo)
      require_opt_value "--repo" "${2:-}"
      REPO_PATH="${2:-}"
      shift 2
      ;;
    --scope)
      require_opt_value "--scope" "${2:-}"
      SCOPE="${2:-}"
      shift 2
      ;;
    --json)
      JSON="true"
      shift
      ;;
    --no-fetch)
      FETCH="false"
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

[[ "$SCOPE" == "tree" || "$SCOPE" == "current" ]] || die "invalid --scope '$SCOPE'"
require_cmd git
require_cmd python3

if ! git -C "$REPO_PATH" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  die "--repo is not a git repository: $REPO_PATH"
fi

STATE_JSON="$(mktemp)"
STATE_ERR="$(mktemp)"
RECOVER_JSON="$(mktemp)"
RECOVER_ERR="$(mktemp)"
SYNC_JSON="$(mktemp)"
SYNC_ERR="$(mktemp)"
RECONCILE_JSON="$(mktemp)"
RECONCILE_ERR="$(mktemp)"
trap 'rm -f "$STATE_JSON" "$STATE_ERR" "$RECOVER_JSON" "$RECOVER_ERR" "$SYNC_JSON" "$SYNC_ERR" "$RECONCILE_JSON" "$RECONCILE_ERR"' EXIT

STATE_ARGS=(bash "$SCRIPT_DIR/repo-state.sh" --repo "$REPO_PATH" --json)
if [[ "$SCOPE" == "current" ]]; then
  STATE_ARGS+=(--no-recurse-related)
fi
if [[ "$FETCH" != "true" ]]; then
  STATE_ARGS+=(--no-fetch)
fi
"${STATE_ARGS[@]}" >"$STATE_JSON" 2>"$STATE_ERR" || die "$(compact_file_text "$STATE_ERR")"

if [[ "$SCOPE" == "tree" ]]; then
  RECONCILE_ARGS=(bash "$SCRIPT_DIR/reconcile-tree.sh" --repo "$REPO_PATH" --json --mode check)
  "${RECONCILE_ARGS[@]}" >"$RECONCILE_JSON" 2>"$RECONCILE_ERR" || true
fi

if [[ "$FIX" == "true" ]]; then
  RECOVER_ARGS=(bash "$SCRIPT_DIR/recover-repo-state.sh" --repo "$REPO_PATH" --json)
  if [[ "$SCOPE" == "current" ]]; then
    RECOVER_ARGS+=(--no-recurse-related)
  fi
  if [[ "$DETACHED_MODE" == "off" ]]; then
    RECOVER_ARGS+=(--no-detached-recovery)
  fi
  "${RECOVER_ARGS[@]}" >"$RECOVER_JSON" 2>"$RECOVER_ERR" || true

  SYNC_ARGS=(bash "$SCRIPT_DIR/sync-raw.sh" --repo "$REPO_PATH" --json --no-reconcile)
  if [[ "$SCOPE" == "current" ]]; then
    SYNC_ARGS+=(--no-recurse-related)
  fi
  if [[ "$DETACHED_MODE" == "off" ]]; then
    SYNC_ARGS+=(--no-detached-recovery)
  fi
  "${SYNC_ARGS[@]}" >"$SYNC_JSON" 2>"$SYNC_ERR" || true
fi

if [[ "$JSON" == "true" ]]; then
  python3 - "$STATE_JSON" "$RECOVER_JSON" "$SYNC_JSON" "$RECONCILE_JSON" "$FIX" <<'PY'
import json
import sys
from pathlib import Path

state = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
recover = {"continued": True, "results": []}
sync = {"results": []}
reconcile = {"actions": []}
if Path(sys.argv[4]).exists() and Path(sys.argv[4]).read_text(encoding="utf-8").strip():
    reconcile = json.loads(Path(sys.argv[4]).read_text(encoding="utf-8"))
if sys.argv[5] == "true":
    if Path(sys.argv[2]).exists() and Path(sys.argv[2]).read_text(encoding="utf-8").strip():
        recover = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    if Path(sys.argv[3]).exists() and Path(sys.argv[3]).read_text(encoding="utf-8").strip():
        sync = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))

sync_map = {item["repo"]: item for item in sync.get("results", [])}
recover_map = {item["repo"]: item for item in recover.get("results", [])}
reconcile_map = {}
for action in reconcile.get("actions", []):
    for repo_key in (action.get("parent"), action.get("child")):
        if not repo_key:
            continue
        reconcile_map.setdefault(repo_key, []).append(action)
results = []
for item in state.get("results", []):
    level = "clean"
    fixability = "none"
    repo_actions = reconcile_map.get(item["repo"], [])
    if item["recovery_class"].startswith("safe-") or item["gitlink_status"] in {"child-ahead", "parent-ahead"}:
        level = "warn"
        fixability = "safe-auto-fix"
    if item["recovery_class"].startswith("blocked") or "rescue" in item["recovery_class"]:
        level = "blocked"
        fixability = "manual-review"
    if item["dirty_tracked"] or item["dirty_untracked"]:
        level = "warn" if level == "clean" else level
    if item["fetch_status"] == "warning":
        level = "warn" if level == "clean" else level
    if repo_actions and level == "clean":
        level = "warn"
    if repo_actions and fixability == "none":
        fixability = "manual-review"
    if any(str(action.get("status", "")).startswith("blocked") for action in repo_actions):
        level = "blocked"
        fixability = "manual-review"

    if sys.argv[5] == "true":
        rec = recover_map.get(item["repo"])
        syn = sync_map.get(item["repo"])
        if rec and rec.get("outcome") == "recovered" and level != "blocked":
            level = "fixed"
        if syn and str(syn.get("status", "")).startswith("synced") and level != "blocked":
            level = "fixed"
        if syn and str(syn.get("status", "")).startswith("blocked"):
            level = "blocked"

    results.append(
        {
            **item,
            "level": level,
            "fixability": fixability,
            "recovery_result": recover_map.get(item["repo"]),
            "sync_result": sync_map.get(item["repo"]),
            "reconcile_actions": repo_actions,
        }
    )

print(json.dumps({
    "mode": "doctor-fix" if sys.argv[5] == "true" else "doctor",
    "scope": state["scope"],
    "root_repo": state["root_repo"],
    "reconcile_actions": reconcile.get("actions", []),
    "results": results,
}, indent=2))
PY
else
  echo "Mode: $( [[ "$FIX" == "true" ]] && printf 'doctor fix' || printf 'doctor' )"
  cat "$STATE_JSON"
  if [[ -s "$RECONCILE_JSON" ]]; then
    echo ""
    echo "Reconcile (report-only):"
    cat "$RECONCILE_JSON"
  fi
  if [[ "$FIX" == "true" ]]; then
    echo ""
    echo "Recovery:"
    cat "$RECOVER_JSON"
    echo ""
    echo "Sync:"
    cat "$SYNC_JSON"
  fi
fi
