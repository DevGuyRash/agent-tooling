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
DETACHED_MODE="recover"
SCOPE="current"
RAW="false"
SYNC_ONLY="false"
STOP=""
RESULTS_FILE=""

RAW_SHIP_STATE_PATH=""
RAW_SHIP_RESUMED="false"
RAW_SHIP_BRANCH=""
RAW_SHIP_HEAD_BEFORE=""
RAW_SHIP_HEAD_AFTER=""
RAW_SHIP_SYNC_STATUS="not-run"
RAW_SHIP_BATCH_COMMIT_STATUS="not-run"
RAW_SHIP_LOCAL_COMMIT_CREATED="false"
RAW_SHIP_LOCAL_COMMIT_SHA=""
RAW_SHIP_PUSH_STARTED="false"
RAW_SHIP_PUSH_COMPLETED="false"
RAW_SHIP_PUSH_SUCCEEDED="false"
RAW_SHIP_RESUME_ELIGIBLE="false"
RAW_SHIP_LAST_ERROR_SUMMARY=""

RAW_SHIP_PROBE_STATE="none"
RAW_SHIP_PROBE_MODE=""
RAW_SHIP_PROBE_REPO=""
RAW_SHIP_PROBE_BRANCH=""
RAW_SHIP_PROBE_HEAD_BEFORE=""
RAW_SHIP_PROBE_HEAD_AFTER=""
RAW_SHIP_PROBE_SYNC_STATUS=""
RAW_SHIP_PROBE_BATCH_COMMIT_STATUS=""
RAW_SHIP_PROBE_LOCAL_COMMIT_CREATED="false"
RAW_SHIP_PROBE_LOCAL_COMMIT_SHA=""
RAW_SHIP_PROBE_PUSH_STARTED="false"
RAW_SHIP_PROBE_PUSH_COMPLETED="false"
RAW_SHIP_PROBE_PUSH_SUCCEEDED="false"
RAW_SHIP_PROBE_RESUME_ELIGIBLE="false"
RAW_SHIP_PROBE_LAST_ERROR_SUMMARY=""
RAW_SHIP_PROBE_NEXT_ACTION="continue with the requested workflow"

GITOPS_PUSH_LEVEL="ok"
GITOPS_PUSH_NOTE=""
GITOPS_PUSH_ACTION="noop"
GITOPS_SYNC_STAGE_STATUS="not-run"
RAW_SHIP_PUSH_TRAP_ACTIVE="false"
RAW_SHIP_PUSH_SIGNAL_REPO=""

print_help() {
  cat <<'USAGE'
Usage:
  bash scripts/ship.sh [raw|sync] [push|pr|ready] [--repo <path>] [--scope current|tree] [--json] [--no-detached-recovery]

Behavior:
  - `ship` defaults to the normal workflow and stops after PR create/update in draft mode.
  - `ship ready` audits the current branch PR readiness only; it does not create a PR or mark one ready.
  - `ship raw` integrates remote changes without publishing, batch-commits current repo changes, pushes once at the end, streams push/pre-push progress to stderr, and resumes a previously interrupted final raw push when the checkpoint is still compatible.
  - `ship sync` runs sync-only mode on the current branch, streams push/pre-push progress to stderr, and stops after the bidirectional raw sync stage.
  - `raw` or `sync` may appear before or after `ship` stop tokens when compatible; invalid combinations fail fast.

Options:
  --repo <path>              Repository path (default: current directory).
  --scope <scope>            current (default) or tree.
  --json                     Emit machine-readable JSON.
  --no-detached-recovery     Refuse detached HEAD instead of attempting safe recovery.
  -h, --help                 Show help.
USAGE
}

emit_json() {
  local file="$1"
  python3 - "$file" "$RAW" "$SYNC_ONLY" "$STOP" "$SCOPE" <<'PY'
import json
import sys
from pathlib import Path

items = []
for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    parts = line.split("\t", 3)
    stage, status, note = parts[:3]
    item = {"stage": stage, "status": status, "note": note}
    if len(parts) == 4 and parts[3]:
        try:
            item["details"] = json.loads(parts[3])
        except json.JSONDecodeError:
            item["details_raw"] = parts[3]
    items.append(item)
print(json.dumps({
    "mode": "sync" if sys.argv[3] == "true" else ("raw" if sys.argv[2] == "true" else "normal"),
    "stop": sys.argv[4],
    "scope": sys.argv[5],
    "continued": all(item["status"] not in {"blocked", "error"} for item in items),
    "results": items,
}, indent=2))
PY
}

record_result() {
  local stage="$1"
  local status="$2"
  local note="$3"
  local details="${4:-}"
  printf '%s\t%s\t%s\t%s\n' "$stage" "$status" "$note" "$details" >> "$RESULTS_FILE"
}

compact_file_text() {
  local file="$1"
  if [[ ! -f "$file" ]]; then
    return 0
  fi
  compact_text "$(cat "$file")"
}

compact_json_file() {
  local file="$1"
  python3 - "$file" <<'PY'
import json
import sys

print(json.dumps(json.load(open(sys.argv[1], encoding="utf-8")), separators=(",", ":")))
PY
}

normalize_tokens() {
  local token
  for token in "$@"; do
    case "$token" in
      raw)
        if [[ "$SYNC_ONLY" == "true" ]]; then
          die "invalid ship syntax: 'raw' and 'sync' are mutually exclusive ship modes"
        fi
        RAW="true"
        ;;
      sync)
        if [[ "$RAW" == "true" || -n "$STOP" ]]; then
          die "invalid ship syntax: 'sync' cannot be combined with raw or stop tokens"
        fi
        SYNC_ONLY="true"
        ;;
      push|pr|ready)
        if [[ "$SYNC_ONLY" == "true" ]]; then
          die "invalid ship syntax: sync-only ship does not accept additional stop tokens"
        fi
        if [[ -n "$STOP" && "$STOP" != "$token" ]]; then
          die "invalid ship syntax: conflicting stop tokens '$STOP' and '$token'"
        fi
        STOP="$token"
        ;;
      "")
        ;;
      *)
        die "unknown ship token: $token"
        ;;
    esac
  done
}

current_branch_pr_json() {
  local repo="$1"
  if ! command -v gh >/dev/null 2>&1; then
    return 1
  fi
  (cd "$repo" && gh pr view --json number,url,isDraft,baseRefName,headRefName,title 2>/dev/null)
}

parse_pr_info() {
  local payload="$1"
  python3 - "$payload" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
print(payload.get("number", ""))
print(payload.get("url", ""))
print("true" if payload.get("isDraft") else "false")
print(payload.get("title", ""))
PY
}

ensure_normal_workdir() {
  local repo="$1"
  local branch=""
  local base=""
  local temp_json=""
  local status=""
  local workdir=""

  branch="$(current_branch_name "$repo" || true)"
  base="$(resolve_default_base "$repo" || true)"
  [[ -n "$base" ]] || die "failed to resolve the default branch for '$repo'"

  if [[ -z "$branch" || "$branch" == "$base" ]]; then
    temp_json="$(mktemp)"
    if ! bash "$SCRIPT_DIR/start-branch.sh" chore --json >"$temp_json" 2>"$temp_json.err"; then
      local err_text=""
      err_text="$(compact_file_text "$temp_json.err")"
      rm -f "$temp_json" "$temp_json.err"
      die "${err_text:-failed to create a work branch}"
    fi
    workdir="$(python3 - "$temp_json" <<'PY'
import json
import sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
print(payload["path"])
PY
)"
    status="$(python3 - "$temp_json" <<'PY'
import json
import sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
print(payload["mode"])
PY
)"
    rm -f "$temp_json" "$temp_json.err"
    record_result "worktree" "ok" "prepared branch workdir at $workdir ($status)"
    if [[ "$status" == "worktree-no-checkout" ]]; then
      record_result "worktree" "blocked" "worktree checkout was skipped because repo filters blocked checkout; resolve the repo-specific checkout issue in $workdir"
      echo "$workdir"
      return 2
    fi
    echo "$workdir"
    return 0
  fi

  temp_json="$(mktemp)"
  if ! bash "$SCRIPT_DIR/ensure-worktree.sh" --repo "$repo" --json >"$temp_json" 2>"$temp_json.err"; then
    local err_text=""
    err_text="$(compact_file_text "$temp_json.err")"
    rm -f "$temp_json" "$temp_json.err"
    die "${err_text:-failed to ensure linked worktree}"
  fi
  workdir="$(python3 - "$temp_json" <<'PY'
import json
import sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
print(payload["path"])
PY
)"
  rm -f "$temp_json" "$temp_json.err"
  record_result "worktree" "ok" "using workdir $workdir"
  echo "$workdir"
}

run_batch_commit() {
  local repo="$1"
  local out_file=""
  out_file="$(mktemp)"
  if ! python3 "$SCRIPT_DIR/batch-commit.py" --repo "$repo" --json >"$out_file" 2>"$out_file.err"; then
    local err_text=""
    local details=""
    local failure_status="error"
    local failure_note=""
    if details="$(compact_json_file "$out_file" 2>/dev/null)"; then
      mapfile -t batch_failure < <(python3 - "$out_file" <<'PY'
import json
import sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
status = "blocked" if payload.get("failure_class") == "commit-signing-unavailable" else "error"
note = payload.get("helper_text") or payload.get("error") or "batch commit failed"
print(status)
print(note.replace("\t", " ").replace("\n", " "))
PY
)
      failure_status="${batch_failure[0]:-error}"
      failure_note="${batch_failure[1]:-batch commit failed}"
      rm -f "$out_file" "$out_file.err"
      record_result "batch_commit" "$failure_status" "$failure_note" "$details"
      return 1
    fi
    err_text="$(compact_file_text "$out_file.err")"
    rm -f "$out_file" "$out_file.err"
    record_result "batch_commit" "error" "${err_text:-batch commit failed}"
    return 1
  fi
  local summary=""
  summary="$(python3 - "$out_file" <<'PY'
import json
import sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
commits = payload.get("commits", [])
if not commits:
    print("no local changes required a commit")
elif payload.get("unsigned_retry_used"):
    print(f"created {len(commits)} Conventional Commit batch(es) after one unsigned retry")
else:
    print(f"created {len(commits)} Conventional Commit batch(es)")
PY
)"
  record_result "batch_commit" "ok" "$summary" "$(compact_json_file "$out_file")"
  rm -f "$out_file" "$out_file.err"
}

has_uncommitted_changes() {
  local repo="$1"
  [[ -n "$(git -C "$repo" status --porcelain)" ]]
}

branch_ahead_of_upstream() {
  local repo="$1"
  local upstream=""
  local ahead="0"
  local behind="0"
  upstream="$(current_upstream_ref "$repo")"
  [[ -n "$upstream" ]] || return 1
  if read -r ahead behind < <(repo_ahead_behind "$repo" "$upstream" || true); then
    [[ "${ahead:-0}" -gt 0 ]]
  else
    return 1
  fi
}

raw_ship_timestamp() {
  date -u '+%Y-%m-%dT%H:%M:%SZ'
}

clear_raw_ship_state() {
  local repo="$1"
  local path=""
  path="$(gitops_ship_state_path "$repo")"
  rm -f "$path"
}

persist_raw_ship_state() {
  local repo="$1"
  RAW_SHIP_STATE_PATH="$(gitops_ship_state_path "$repo")"
  mkdir -p "$(dirname "$RAW_SHIP_STATE_PATH")"
  REPO_ROOT="$(repo_root_path "$repo")" \
  UPDATED_AT="$(raw_ship_timestamp)" \
  RAW_SHIP_STATE_PATH="$RAW_SHIP_STATE_PATH" \
  RAW_SHIP_BRANCH="$RAW_SHIP_BRANCH" \
  RAW_SHIP_HEAD_BEFORE="$RAW_SHIP_HEAD_BEFORE" \
  RAW_SHIP_HEAD_AFTER="$RAW_SHIP_HEAD_AFTER" \
  RAW_SHIP_SYNC_STATUS="$RAW_SHIP_SYNC_STATUS" \
  RAW_SHIP_BATCH_COMMIT_STATUS="$RAW_SHIP_BATCH_COMMIT_STATUS" \
  RAW_SHIP_LOCAL_COMMIT_CREATED="$RAW_SHIP_LOCAL_COMMIT_CREATED" \
  RAW_SHIP_LOCAL_COMMIT_SHA="$RAW_SHIP_LOCAL_COMMIT_SHA" \
  RAW_SHIP_PUSH_STARTED="$RAW_SHIP_PUSH_STARTED" \
  RAW_SHIP_PUSH_COMPLETED="$RAW_SHIP_PUSH_COMPLETED" \
  RAW_SHIP_PUSH_SUCCEEDED="$RAW_SHIP_PUSH_SUCCEEDED" \
  RAW_SHIP_RESUME_ELIGIBLE="$RAW_SHIP_RESUME_ELIGIBLE" \
  RAW_SHIP_LAST_ERROR_SUMMARY="$RAW_SHIP_LAST_ERROR_SUMMARY" \
  python3 - <<'PY'
import json
import os
from pathlib import Path


def as_bool(value: str) -> bool:
    return value.lower() == "true"

payload = {
    "mode": "raw",
    "repo": os.environ["REPO_ROOT"],
    "branch": os.environ["RAW_SHIP_BRANCH"],
    "head_before": os.environ["RAW_SHIP_HEAD_BEFORE"],
    "head_after": os.environ["RAW_SHIP_HEAD_AFTER"],
    "sync_status": os.environ["RAW_SHIP_SYNC_STATUS"],
    "batch_commit_status": os.environ["RAW_SHIP_BATCH_COMMIT_STATUS"],
    "local_commit_created": as_bool(os.environ["RAW_SHIP_LOCAL_COMMIT_CREATED"]),
    "local_commit_sha": os.environ["RAW_SHIP_LOCAL_COMMIT_SHA"],
    "push_started": as_bool(os.environ["RAW_SHIP_PUSH_STARTED"]),
    "push_completed": as_bool(os.environ["RAW_SHIP_PUSH_COMPLETED"]),
    "push_succeeded": as_bool(os.environ["RAW_SHIP_PUSH_SUCCEEDED"]),
    "resume_eligible": as_bool(os.environ["RAW_SHIP_RESUME_ELIGIBLE"]),
    "last_error_summary": os.environ["RAW_SHIP_LAST_ERROR_SUMMARY"],
    "updated_at": os.environ["UPDATED_AT"],
}
Path(os.environ["RAW_SHIP_STATE_PATH"]).write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
PY
}

probe_raw_ship_resume_state() {
  local repo="$1"
  local path=""
  local repo_root=""
  local branch=""
  local head_oid=""
  local tracked="0"
  local untracked="0"
  local sequencer=""

  path="$(gitops_ship_state_path "$repo")"
  repo_root="$(repo_root_path "$repo")"
  branch="$(current_branch_name "$repo" || true)"
  head_oid="$(repo_head_oid "$repo" 2>/dev/null || true)"
  tracked="$(repo_dirty_tracked_count "$repo")"
  untracked="$(repo_dirty_untracked_count "$repo")"
  sequencer="$(repo_sequencer_state "$repo")"

  python3 "$SCRIPT_DIR/lib/raw_ship_state.py" probe \
    --path "$path" \
    --repo-root "$repo_root" \
    --branch "$branch" \
    --head-oid "$head_oid" \
    --tracked "$tracked" \
    --untracked "$untracked" \
    --sequencer "$sequencer" \
    --format lines
}

load_raw_ship_probe() {
  local repo="$1"
  local probe=()
  mapfile -t probe < <(probe_raw_ship_resume_state "$repo")
  RAW_SHIP_PROBE_STATE="${probe[0]:-none}"
  RAW_SHIP_PROBE_MODE="${probe[1]:-}"
  RAW_SHIP_PROBE_REPO="${probe[2]:-}"
  RAW_SHIP_PROBE_BRANCH="${probe[3]:-}"
  RAW_SHIP_PROBE_HEAD_BEFORE="${probe[4]:-}"
  RAW_SHIP_PROBE_HEAD_AFTER="${probe[5]:-}"
  RAW_SHIP_PROBE_SYNC_STATUS="${probe[6]:-}"
  RAW_SHIP_PROBE_BATCH_COMMIT_STATUS="${probe[7]:-}"
  RAW_SHIP_PROBE_LOCAL_COMMIT_CREATED="${probe[8]:-false}"
  RAW_SHIP_PROBE_LOCAL_COMMIT_SHA="${probe[9]:-}"
  RAW_SHIP_PROBE_PUSH_STARTED="${probe[10]:-false}"
  RAW_SHIP_PROBE_PUSH_COMPLETED="${probe[11]:-false}"
  RAW_SHIP_PROBE_PUSH_SUCCEEDED="${probe[12]:-false}"
  RAW_SHIP_PROBE_RESUME_ELIGIBLE="${probe[13]:-false}"
  RAW_SHIP_PROBE_LAST_ERROR_SUMMARY="${probe[14]:-}"
  RAW_SHIP_PROBE_NEXT_ACTION="${probe[15]:-continue with the requested workflow}"
}

reset_push_result() {
  GITOPS_PUSH_LEVEL="ok"
  GITOPS_PUSH_NOTE=""
  GITOPS_PUSH_ACTION="noop"
  reset_gitops_push_verify_state
}

push_current_branch() {
  local repo="$1"
  local branch="$2"
  local out_file=""
  local err_text=""
  local local_head_oid=""

  reset_push_result
  out_file="$(mktemp)"
  if [[ -z "$(current_upstream_ref "$repo")" ]] && repo_has_origin "$repo"; then
    GITOPS_PUSH_ACTION="push-set-upstream"
    if gitops_run_noninteractive_logged "$repo" "$out_file" push -u origin "$branch"; then
      local_head_oid="$(repo_head_oid "$repo")"
      if gitops_verify_remote_branch_matches_local_head "$repo" "$branch" "$local_head_oid"; then
        GITOPS_PUSH_NOTE="pushed branch '$branch' and set upstream"
        rm -f "$out_file"
        return 0
      fi
      GITOPS_PUSH_LEVEL="blocked"
      GITOPS_PUSH_NOTE="${GITOPS_PUSH_VERIFY_NOTE:-failed to verify remote branch after push}"
      rm -f "$out_file"
      return 1
    fi
  else
    GITOPS_PUSH_ACTION="push"
    if gitops_run_noninteractive_logged "$repo" "$out_file" push; then
      local_head_oid="$(repo_head_oid "$repo")"
      if gitops_verify_remote_branch_matches_local_head "$repo" "$branch" "$local_head_oid"; then
        GITOPS_PUSH_NOTE="pushed branch '$branch'"
        rm -f "$out_file"
        return 0
      fi
      GITOPS_PUSH_LEVEL="blocked"
      GITOPS_PUSH_NOTE="${GITOPS_PUSH_VERIFY_NOTE:-failed to verify remote branch after push}"
      rm -f "$out_file"
      return 1
    fi
  fi

  err_text="$GITOPS_PUSH_OUTPUT"
  if printf '%s' "$err_text" | grep -qi 'non-fast-forward'; then
    GITOPS_PUSH_LEVEL="blocked"
    GITOPS_PUSH_NOTE="push rejected as non-fast-forward; fetch and review remote drift before retrying"
  elif [[ "$GITOPS_PUSH_INTERRUPTED" == "true" ]]; then
    GITOPS_PUSH_LEVEL="blocked"
    GITOPS_PUSH_NOTE="push interrupted before completion"
  else
    GITOPS_PUSH_LEVEL="error"
    GITOPS_PUSH_NOTE="${err_text:-git push failed}"
  fi
  rm -f "$out_file"
  return 1
}

build_raw_push_details() {
  local next_action="$1"
  RAW_SHIP_RESUMED="$RAW_SHIP_RESUMED" \
  RAW_SHIP_LOCAL_COMMIT_CREATED="$RAW_SHIP_LOCAL_COMMIT_CREATED" \
  RAW_SHIP_LOCAL_COMMIT_SHA="$RAW_SHIP_LOCAL_COMMIT_SHA" \
  RAW_SHIP_PUSH_COMPLETED="$RAW_SHIP_PUSH_COMPLETED" \
  RAW_SHIP_PUSH_SUCCEEDED="$RAW_SHIP_PUSH_SUCCEEDED" \
  RAW_SHIP_RESUME_ELIGIBLE="$RAW_SHIP_RESUME_ELIGIBLE" \
  RAW_SHIP_LAST_ERROR_SUMMARY="$RAW_SHIP_LAST_ERROR_SUMMARY" \
  GITOPS_PUSH_ACTION="$GITOPS_PUSH_ACTION" \
  GITOPS_PUSH_INTERRUPTED="$GITOPS_PUSH_INTERRUPTED" \
  GITOPS_PUSH_VERIFY_MATCHED="${GITOPS_PUSH_VERIFY_MATCHED:-false}" \
  GITOPS_PUSH_VERIFY_TRANSPORT_ATTEMPTS="${GITOPS_PUSH_VERIFY_TRANSPORT_ATTEMPTS:-}" \
  GITOPS_PUSH_VERIFY_TRANSPORT_USED="${GITOPS_PUSH_VERIFY_TRANSPORT_USED:-}" \
  GITOPS_PUSH_VERIFY_NOTE="${GITOPS_PUSH_VERIFY_NOTE:-}" \
  GITOPS_PUSH_VERIFY_REMOTE_HEAD_OID="${GITOPS_PUSH_VERIFY_REMOTE_HEAD_OID:-}" \
  GITOPS_PUSH_VERIFY_LOCAL_HEAD_OID="${GITOPS_PUSH_VERIFY_LOCAL_HEAD_OID:-}" \
  NEXT_ACTION="$next_action" \
  python3 - <<'PY'
import json
import os


def as_bool(value: str) -> bool:
    return value.lower() == "true"

print(json.dumps({
    "resumed": as_bool(os.environ["RAW_SHIP_RESUMED"]),
    "local_commit_created": as_bool(os.environ["RAW_SHIP_LOCAL_COMMIT_CREATED"]),
    "local_commit_sha": os.environ["RAW_SHIP_LOCAL_COMMIT_SHA"],
    "push_completed": as_bool(os.environ["RAW_SHIP_PUSH_COMPLETED"]),
    "push_succeeded": as_bool(os.environ["RAW_SHIP_PUSH_SUCCEEDED"]),
    "resume_eligible": as_bool(os.environ["RAW_SHIP_RESUME_ELIGIBLE"]),
    "interrupted": as_bool(os.environ["GITOPS_PUSH_INTERRUPTED"]),
    "last_error_summary": os.environ["RAW_SHIP_LAST_ERROR_SUMMARY"],
    "next_action": os.environ["NEXT_ACTION"],
    "push_action": os.environ["GITOPS_PUSH_ACTION"],
    "push_verified": as_bool(os.environ["GITOPS_PUSH_VERIFY_MATCHED"]),
    "push_verification_transport_attempts": [item for item in os.environ["GITOPS_PUSH_VERIFY_TRANSPORT_ATTEMPTS"].split(",") if item],
    "push_verification_transport_used": os.environ["GITOPS_PUSH_VERIFY_TRANSPORT_USED"],
    "push_verification_note": os.environ["GITOPS_PUSH_VERIFY_NOTE"],
    "remote_head_oid": os.environ["GITOPS_PUSH_VERIFY_REMOTE_HEAD_OID"],
    "local_head_oid": os.environ["GITOPS_PUSH_VERIFY_LOCAL_HEAD_OID"],
}, separators=(",", ":")))
PY
}

receipt_note() {
  local repo="$1"
  local branch="$2"
  local base=""
  base="$(resolve_default_base "$repo" || true)"
  [[ -n "$base" ]] || base="origin/main"
  python3 "$SCRIPT_DIR/receipt.py" --branch "$branch" --base "$base" 2>/dev/null | tr '\n' ' ' | sed 's/[[:space:]]\+/ /g; s/^ //; s/ $//'
}

run_sync_stage() {
  local repo="$1"
  local mode="${2:-publish}"
  local sync_json=""
  local sync_summary=""
  local sync_status=""
  local primary_status=""
  local -a sync_args=(bash "$SCRIPT_DIR/sync-raw.sh" --repo "$repo" --json)

  GITOPS_SYNC_STAGE_STATUS="not-run"
  if [[ "$SCOPE" == "current" ]]; then
    sync_args+=(--no-recurse-related)
  fi
  if [[ "$DETACHED_MODE" == "off" ]]; then
    sync_args+=(--no-detached-recovery)
  fi
  if [[ "$mode" == "no-push" ]]; then
    sync_args+=(--no-push)
  fi

  sync_json="$(mktemp)"
  if ! "${sync_args[@]}" >"$sync_json" 2>"$sync_json.err"; then
    local err_text=""
    err_text="$(compact_file_text "$sync_json.err")"
    rm -f "$sync_json" "$sync_json.err"
    record_result "sync" "error" "${err_text:-raw sync failed}"
    GITOPS_SYNC_STAGE_STATUS="error"
    return 1
  fi
  mapfile -t sync_summary < <(python3 - "$sync_json" "$RESULTS_FILE" "$repo" <<'PY'
import json
import os
import sys
from pathlib import Path

payload = json.load(open(sys.argv[1], encoding="utf-8"))
out_path = Path(sys.argv[2])
target_repo = os.path.realpath(sys.argv[3])
blocked = False
primary_status = "not-run"
with out_path.open("a", encoding="utf-8") as out:
    for item in payload.get("results", []):
        status = item["status"]
        note = item.get("note", "")
        level = "ok"
        if status.startswith("blocked") or status == "reconcile-failed":
            level = "blocked"
            blocked = True
        elif status.endswith("warning") or status.startswith("fetch-"):
            level = "warn"
        details = json.dumps(item, separators=(",", ":"))
        out.write(f"sync\t{level}\t{status}: {note}\t{details}\n")
        repo_value = os.path.realpath(item.get("repo", ""))
        if repo_value == target_repo and primary_status == "not-run":
            primary_status = status
if primary_status == "not-run" and payload.get("results"):
    primary_status = str(payload["results"][0].get("status", "not-run"))
print("blocked" if blocked else "ok")
print(primary_status)
PY
)
  rm -f "$sync_json" "$sync_json.err"
  sync_status="${sync_summary[0]:-blocked}"
  primary_status="${sync_summary[1]:-not-run}"
  GITOPS_SYNC_STAGE_STATUS="$primary_status"
  [[ "$sync_status" != "blocked" ]]
}

record_readiness_snapshot() {
  local repo="$1"
  local pr_number="$2"
  local strict_mode="${3:-snapshot}"
  local out_file=""
  local level="warn"
  local note=""
  local details=""

  out_file="$(mktemp)"
  if ! python3 "$SCRIPT_DIR/pr-readiness-report.py" "$pr_number" --local-repo "$repo" --scope "$SCOPE" --json >"$out_file" 2>"$out_file.err"; then
    local err_text=""
    err_text="$(compact_text "$(cat "$out_file.err" 2>/dev/null)")"
    rm -f "$out_file" "$out_file.err"
    record_result "readiness" "error" "${err_text:-failed to generate readiness report}"
    return 1
  fi

  details="$(compact_json_file "$out_file")"
  mapfile -t readiness_meta < <(python3 - "$out_file" "$strict_mode" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
mode = sys.argv[2]
pr = payload.get("pr", {})
readiness = payload.get("readiness", {})
summary_items = readiness.get("blocking_reasons") or readiness.get("attention_items") or []
summary = "; ".join(summary_items[:3])
if not summary:
    summary = payload.get("next_action", "snapshot captured")

if readiness.get("safe_to_mark_ready"):
    level = "ok"
elif mode == "strict":
    level = "blocked"
else:
    level = "warn"

if pr.get("is_draft"):
    if readiness.get("safe_to_mark_ready"):
        note = f"PR #{pr.get('number')} draft readiness passed; {payload.get('next_action', 'mark it ready when you want reviewers')}"
    else:
        note = f"PR #{pr.get('number')} draft readiness snapshot: {summary}"
else:
    note = f"PR #{pr.get('number')} readiness snapshot: {summary}"

print(level)
print(note.replace("\t", " ").replace("\n", " "))
PY
)

  level="${readiness_meta[0]:-warn}"
  note="${readiness_meta[1]:-readiness snapshot recorded}"
  record_result "readiness" "$level" "$note" "$details"
  rm -f "$out_file" "$out_file.err"

  [[ "$level" != "blocked" ]]
}

record_existing_pr_snapshot() {
  local repo="$1"
  local pr_payload=""
  local pr_number=""
  local pr_url=""
  local pr_is_draft=""
  local pr_title=""

  if ! pr_payload="$(current_branch_pr_json "$repo")"; then
    return 0
  fi

  read -r pr_number pr_url pr_is_draft pr_title < <(parse_pr_info "$pr_payload" | paste -sd ' ' -)
  record_result "pr" "ok" "existing PR #$pr_number already tracks branch '$(current_branch_name "$repo" || true)' ($pr_url)"
  record_readiness_snapshot "$repo" "$pr_number" snapshot || true
}

resume_raw_ship_if_possible() {
  local repo="$1"
  load_raw_ship_probe "$repo"
  if [[ "$RAW_SHIP_PROBE_STATE" == "stale" ]]; then
    clear_raw_ship_state "$repo"
    return 1
  fi
  if [[ "$RAW_SHIP_PROBE_STATE" != "resume-eligible" ]]; then
    return 1
  fi

  RAW_SHIP_STATE_PATH="$(gitops_ship_state_path "$repo")"
  RAW_SHIP_RESUMED="true"
  RAW_SHIP_BRANCH="$RAW_SHIP_PROBE_BRANCH"
  RAW_SHIP_HEAD_BEFORE="$RAW_SHIP_PROBE_HEAD_BEFORE"
  RAW_SHIP_HEAD_AFTER="$RAW_SHIP_PROBE_HEAD_AFTER"
  RAW_SHIP_SYNC_STATUS="$RAW_SHIP_PROBE_SYNC_STATUS"
  RAW_SHIP_BATCH_COMMIT_STATUS="$RAW_SHIP_PROBE_BATCH_COMMIT_STATUS"
  RAW_SHIP_LOCAL_COMMIT_CREATED="$RAW_SHIP_PROBE_LOCAL_COMMIT_CREATED"
  RAW_SHIP_LOCAL_COMMIT_SHA="$RAW_SHIP_PROBE_LOCAL_COMMIT_SHA"
  RAW_SHIP_PUSH_STARTED="$RAW_SHIP_PROBE_PUSH_STARTED"
  RAW_SHIP_PUSH_COMPLETED="$RAW_SHIP_PROBE_PUSH_COMPLETED"
  RAW_SHIP_PUSH_SUCCEEDED="$RAW_SHIP_PROBE_PUSH_SUCCEEDED"
  RAW_SHIP_RESUME_ELIGIBLE="$RAW_SHIP_PROBE_RESUME_ELIGIBLE"
  RAW_SHIP_LAST_ERROR_SUMMARY="$RAW_SHIP_PROBE_LAST_ERROR_SUMMARY"

  record_result "sync" "ok" "resumed prior raw ship checkpoint; skipped raw sync"
  record_result "batch_commit" "ok" "reused local Conventional Commit batch at $RAW_SHIP_LOCAL_COMMIT_SHA"
  return 0
}

record_raw_push_result() {
  local next_action="$1"
  record_result "push" "$GITOPS_PUSH_LEVEL" "$GITOPS_PUSH_NOTE" "$(build_raw_push_details "$next_action")"
}

clear_raw_ship_push_trap() {
  trap - INT TERM
  RAW_SHIP_PUSH_TRAP_ACTIVE="false"
  RAW_SHIP_PUSH_SIGNAL_REPO=""
}

handle_raw_ship_push_signal() {
  local signal="$1"
  local code="143"
  if [[ "$signal" == "INT" ]]; then
    code="130"
  fi
  if [[ "$RAW_SHIP_PUSH_TRAP_ACTIVE" == "true" && -n "$RAW_SHIP_PUSH_SIGNAL_REPO" && "$RAW_SHIP_LOCAL_COMMIT_CREATED" == "true" ]]; then
    RAW_SHIP_PUSH_STARTED="true"
    RAW_SHIP_PUSH_COMPLETED="false"
    RAW_SHIP_PUSH_SUCCEEDED="false"
    RAW_SHIP_RESUME_ELIGIBLE="true"
    RAW_SHIP_LAST_ERROR_SUMMARY="push interrupted before completion"
    persist_raw_ship_state "$RAW_SHIP_PUSH_SIGNAL_REPO"
  fi
  clear_raw_ship_push_trap
  exit "$code"
}

arm_raw_ship_push_trap() {
  local repo="$1"
  RAW_SHIP_PUSH_SIGNAL_REPO="$repo"
  RAW_SHIP_PUSH_TRAP_ACTIVE="true"
  trap 'handle_raw_ship_push_signal INT' INT
  trap 'handle_raw_ship_push_signal TERM' TERM
}

handle_sync_only_mode() {
  local repo="$1"
  run_sync_stage "$repo"
}

handle_raw_mode() {
  local repo="$1"
  local branch=""
  local need_push="false"
  local receipt=""

  if ! resume_raw_ship_if_possible "$repo"; then
    if ! run_sync_stage "$repo" "no-push"; then
      return 1
    fi

    branch="$(current_branch_name "$repo" || true)"
    [[ -n "$branch" ]] || die "failed to resolve current branch after raw sync"

    RAW_SHIP_STATE_PATH="$(gitops_ship_state_path "$repo")"
    RAW_SHIP_RESUMED="false"
    RAW_SHIP_BRANCH="$branch"
    RAW_SHIP_HEAD_BEFORE="$(repo_head_oid "$repo")"
    RAW_SHIP_HEAD_AFTER="$RAW_SHIP_HEAD_BEFORE"
    RAW_SHIP_SYNC_STATUS="$GITOPS_SYNC_STAGE_STATUS"
    RAW_SHIP_BATCH_COMMIT_STATUS="no-op"
    RAW_SHIP_LOCAL_COMMIT_CREATED="false"
    RAW_SHIP_LOCAL_COMMIT_SHA=""
    RAW_SHIP_PUSH_STARTED="false"
    RAW_SHIP_PUSH_COMPLETED="false"
    RAW_SHIP_PUSH_SUCCEEDED="false"
    RAW_SHIP_RESUME_ELIGIBLE="false"
    RAW_SHIP_LAST_ERROR_SUMMARY=""

    if has_uncommitted_changes "$repo"; then
      RAW_SHIP_BATCH_COMMIT_STATUS="created"
      if ! run_batch_commit "$repo"; then
        return 1
      fi
      RAW_SHIP_HEAD_AFTER="$(repo_head_oid "$repo")"
      if [[ "$RAW_SHIP_HEAD_AFTER" != "$RAW_SHIP_HEAD_BEFORE" ]]; then
        RAW_SHIP_LOCAL_COMMIT_CREATED="true"
        RAW_SHIP_LOCAL_COMMIT_SHA="$RAW_SHIP_HEAD_AFTER"
        RAW_SHIP_RESUME_ELIGIBLE="true"
        persist_raw_ship_state "$repo"
      else
        RAW_SHIP_BATCH_COMMIT_STATUS="no-op"
      fi
      need_push="true"
    elif branch_ahead_of_upstream "$repo" || [[ -z "$(current_upstream_ref "$repo")" ]]; then
      record_result "batch_commit" "ok" "no new local changes to commit; branch will still be pushed"
      RAW_SHIP_BATCH_COMMIT_STATUS="no-op"
      need_push="true"
    else
      record_result "batch_commit" "ok" "no local changes required a commit"
      RAW_SHIP_BATCH_COMMIT_STATUS="no-op"
    fi
  else
    branch="$RAW_SHIP_BRANCH"
    need_push="true"
  fi

  [[ -n "$branch" ]] || branch="$(current_branch_name "$repo" || true)"
  [[ -n "$branch" ]] || die "failed to resolve current branch for raw ship"

  if [[ "$need_push" == "true" ]]; then
    if [[ "$RAW_SHIP_LOCAL_COMMIT_CREATED" == "true" ]]; then
      RAW_SHIP_PUSH_STARTED="true"
      RAW_SHIP_PUSH_COMPLETED="false"
      RAW_SHIP_PUSH_SUCCEEDED="false"
      RAW_SHIP_RESUME_ELIGIBLE="true"
      RAW_SHIP_LAST_ERROR_SUMMARY="push interrupted before completion"
      persist_raw_ship_state "$repo"
      arm_raw_ship_push_trap "$repo"
    fi
    if ! push_current_branch "$repo" "$branch"; then
      clear_raw_ship_push_trap
      if [[ "$GITOPS_PUSH_INTERRUPTED" == "true" ]]; then
        RAW_SHIP_PUSH_COMPLETED="false"
        RAW_SHIP_LAST_ERROR_SUMMARY="push interrupted before completion"
      else
        RAW_SHIP_PUSH_COMPLETED="true"
        RAW_SHIP_LAST_ERROR_SUMMARY="$GITOPS_PUSH_NOTE"
      fi
      RAW_SHIP_PUSH_SUCCEEDED="false"
      if [[ "$RAW_SHIP_LOCAL_COMMIT_CREATED" == "true" ]]; then
        RAW_SHIP_RESUME_ELIGIBLE="true"
        persist_raw_ship_state "$repo"
      else
        RAW_SHIP_RESUME_ELIGIBLE="false"
      fi
      if [[ "$RAW_SHIP_RESUME_ELIGIBLE" == "true" ]]; then
        record_raw_push_result "rerun 'ship raw' to resume the pending push"
      else
        record_raw_push_result "review the push failure and retry when ready"
      fi
      return 1
    fi
    clear_raw_ship_push_trap
    RAW_SHIP_PUSH_COMPLETED="true"
    RAW_SHIP_PUSH_SUCCEEDED="true"
    RAW_SHIP_RESUME_ELIGIBLE="false"
    RAW_SHIP_LAST_ERROR_SUMMARY=""
    if [[ "$RAW_SHIP_LOCAL_COMMIT_CREATED" == "true" ]]; then
      clear_raw_ship_state "$repo"
    fi
    record_raw_push_result "continue with the requested workflow"
    receipt="$(receipt_note "$repo" "$branch")"
    [[ -n "$receipt" ]] && record_result "receipt" "ok" "$receipt"
  else
    GITOPS_PUSH_LEVEL="ok"
    GITOPS_PUSH_NOTE="branch '$branch' is already in sync with its upstream"
    GITOPS_PUSH_ACTION="noop"
    RAW_SHIP_PUSH_COMPLETED="true"
    RAW_SHIP_PUSH_SUCCEEDED="true"
    RAW_SHIP_RESUME_ELIGIBLE="false"
    record_raw_push_result "continue with the requested workflow"
  fi

  record_existing_pr_snapshot "$repo"
}

handle_readiness_mode() {
  local repo="$1"
  local pr_payload=""
  local pr_number=""
  local pr_url=""
  local pr_is_draft=""
  local pr_title=""
  local branch=""

  if ! run_sync_stage "$repo"; then
    return 1
  fi

  branch="$(current_branch_name "$repo" || true)"
  if ! pr_payload="$(current_branch_pr_json "$repo")"; then
    record_result "pr" "blocked" "no pull request currently tracks branch '${branch:-DETACHED}'; ship ready audits an existing PR only"
    return 1
  fi

  read -r pr_number pr_url pr_is_draft pr_title < <(parse_pr_info "$pr_payload" | paste -sd ' ' -)
  record_result "pr" "ok" "existing PR #$pr_number already tracks branch '$branch' ($pr_url)"
  record_readiness_snapshot "$repo" "$pr_number" strict
}

handle_normal_mode() {
  local repo="$1"
  local workdir=""
  local branch=""
  local default_base=""
  local pr_payload=""
  local pr_number=""
  local pr_url=""
  local pr_is_draft=""
  local pr_title=""
  local title=""
  local pushed="false"

  if ! run_sync_stage "$repo" "no-push"; then
    return 1
  fi

  if ! workdir="$(ensure_normal_workdir "$repo")"; then
    return 1
  fi

  if ! run_batch_commit "$workdir"; then
    return 1
  fi

  branch="$(current_branch_name "$workdir" || true)"
  [[ -n "$branch" ]] || die "failed to resolve current branch in '$workdir'"
  default_base="$(resolve_default_base "$workdir" || true)"
  [[ -n "$default_base" ]] || default_base="main"

  if has_uncommitted_changes "$workdir"; then
    record_result "push" "blocked" "uncommitted changes remain after batching; review the worktree before pushing"
    return 1
  fi
  if branch_ahead_of_upstream "$workdir" || [[ -z "$(current_upstream_ref "$workdir")" ]]; then
    if ! push_current_branch "$workdir" "$branch"; then
      record_result "push" "$GITOPS_PUSH_LEVEL" "$GITOPS_PUSH_NOTE"
      return 1
    fi
    record_result "push" "$GITOPS_PUSH_LEVEL" "$GITOPS_PUSH_NOTE"
    pushed="true"
  else
    record_result "push" "ok" "branch '$branch' is already in sync with its upstream"
  fi

  if [[ "$pushed" == "true" ]]; then
    local receipt=""
    receipt="$(receipt_note "$workdir" "$branch")"
    [[ -n "$receipt" ]] && record_result "receipt" "ok" "$receipt"
  fi

  if pr_payload="$(current_branch_pr_json "$workdir")"; then
    read -r pr_number pr_url pr_is_draft pr_title < <(parse_pr_info "$pr_payload" | paste -sd ' ' -)
    record_result "pr" "ok" "existing PR #$pr_number already tracks branch '$branch' ($pr_url)"
  else
    title="$(git -C "$workdir" log -1 --pretty=%s)"
    local pr_out=""
    pr_out="$(mktemp)"
    if ! bash "$SCRIPT_DIR/pr-create.sh" --title "$title" --base "$default_base" --head "$branch" --create --force-create --no-labels >"$pr_out" 2>"$pr_out.err"; then
      local err_text=""
      err_text="$(compact_text "$(cat "$pr_out" "$pr_out.err" 2>/dev/null)")"
      rm -f "$pr_out" "$pr_out.err"
      record_result "pr" "blocked" "${err_text:-failed to create PR}"
      return 1
    fi
    rm -f "$pr_out" "$pr_out.err"
    if pr_payload="$(current_branch_pr_json "$workdir")"; then
      read -r pr_number pr_url pr_is_draft pr_title < <(parse_pr_info "$pr_payload" | paste -sd ' ' -)
      record_result "pr" "ok" "created draft PR #$pr_number for '$branch' ($pr_url)"
    else
      record_result "pr" "ok" "created draft PR for '$branch'"
    fi
  fi

  if [[ -n "$pr_number" ]]; then
    record_readiness_snapshot "$workdir" "$pr_number" snapshot || true
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
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
    --no-detached-recovery)
      DETACHED_MODE="off"
      shift
      ;;
    -h|--help)
      print_help
      exit 0
      ;;
    *)
      normalize_tokens "$1"
      shift
      ;;
  esac
done

[[ "$SCOPE" == "current" || "$SCOPE" == "tree" ]] || die "invalid --scope '$SCOPE'"
if [[ "$RAW" == "true" && "$SYNC_ONLY" == "true" ]]; then
  die "invalid ship syntax: raw and sync modes are mutually exclusive"
fi
if [[ "$RAW" == "true" ]]; then
  [[ -z "$STOP" || "$STOP" == "push" ]] || die "raw ship supports only the 'push' stop"
  STOP="push"
elif [[ "$SYNC_ONLY" == "true" ]]; then
  STOP="sync"
else
  if [[ -z "$STOP" ]]; then
    STOP="pr"
  fi
fi

require_cmd git
require_cmd python3

if ! git -C "$REPO_PATH" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  die "--repo is not a git repository: $REPO_PATH"
fi

RESULTS_FILE="$(mktemp)"
trap 'rm -f "$RESULTS_FILE"' EXIT

SHIP_MODE="normal"
if [[ "$RAW" == "true" ]]; then
  SHIP_MODE="raw"
elif [[ "$SYNC_ONLY" == "true" ]]; then
  SHIP_MODE="sync"
fi
record_result "preflight" "ok" "ship mode is $SHIP_MODE with stop '$STOP'"

if [[ "$RAW" == "true" ]]; then
  handle_raw_mode "$REPO_PATH" || true
elif [[ "$SYNC_ONLY" == "true" ]]; then
  handle_sync_only_mode "$REPO_PATH" || true
elif [[ "$STOP" == "ready" ]]; then
  handle_readiness_mode "$REPO_PATH" || true
else
  handle_normal_mode "$REPO_PATH" || true
fi

if [[ "$JSON" == "true" ]]; then
  emit_json "$RESULTS_FILE"
else
  while IFS=$'\t' read -r stage status note details; do
    echo "$status: $stage"
    [[ -n "$note" ]] && echo "  note: $note"
  done < "$RESULTS_FILE"
fi
