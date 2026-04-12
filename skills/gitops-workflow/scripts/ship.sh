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

print_help() {
  cat <<'USAGE'
Usage:
  bash scripts/ship.sh [raw|sync] [push|pr|ready] [--repo <path>] [--scope current|tree] [--json] [--no-detached-recovery]

Behavior:
  - `ship` defaults to the normal workflow and stops after PR create/update in draft mode.
  - `ship ready` audits the current branch PR readiness only; it does not create a PR or mark one ready.
  - `ship raw` syncs, batch-commits current repo changes, pushes the current branch in place, and reports PR readiness when one already exists.
  - `ship sync` runs sync-only mode on the current branch and stops after the bidirectional raw sync stage.
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

push_current_branch() {
  local repo="$1"
  local branch="$2"
  local out_file=""
  out_file="$(mktemp)"
  if [[ -z "$(current_upstream_ref "$repo")" ]] && repo_has_origin "$repo"; then
    if gitops_git_noninteractive "$repo" push -u origin "$branch" >"$out_file" 2>"$out_file.err"; then
      record_result "push" "ok" "pushed branch '$branch' and set upstream"
      rm -f "$out_file" "$out_file.err"
      return 0
    fi
  elif gitops_git_noninteractive "$repo" push >"$out_file" 2>"$out_file.err"; then
    record_result "push" "ok" "pushed branch '$branch'"
    rm -f "$out_file" "$out_file.err"
    return 0
  fi

  local err_text=""
  err_text="$(compact_text "$(cat "$out_file" "$out_file.err" 2>/dev/null)")"
  if printf '%s' "$err_text" | grep -qi 'non-fast-forward'; then
    record_result "push" "blocked" "push rejected as non-fast-forward; fetch and review remote drift before retrying"
  else
    record_result "push" "error" "${err_text:-git push failed}"
  fi
  rm -f "$out_file" "$out_file.err"
  return 1
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
  local sync_json=""
  local sync_status=""
  local -a sync_args=(bash "$SCRIPT_DIR/sync-raw.sh" --repo "$repo" --json)

  if [[ "$SCOPE" == "current" ]]; then
    sync_args+=(--no-recurse-related)
  fi
  if [[ "$DETACHED_MODE" == "off" ]]; then
    sync_args+=(--no-detached-recovery)
  fi

  sync_json="$(mktemp)"
  if ! "${sync_args[@]}" >"$sync_json" 2>"$sync_json.err"; then
    local err_text=""
    err_text="$(compact_file_text "$sync_json.err")"
    rm -f "$sync_json" "$sync_json.err"
    record_result "sync" "error" "${err_text:-raw sync failed}"
    return 1
  fi
  sync_status="$(python3 - "$sync_json" "$RESULTS_FILE" <<'PY'
import json
import sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
blocked = False
with open(sys.argv[2], "a", encoding="utf-8") as out:
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
print("blocked" if blocked else "ok")
PY
)"
  rm -f "$sync_json" "$sync_json.err"
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

handle_sync_only_mode() {
  local repo="$1"
  run_sync_stage "$repo"
}

handle_raw_mode() {
  local repo="$1"
  local branch=""
  local need_push="false"

  if ! run_sync_stage "$repo"; then
    return 1
  fi

  branch="$(current_branch_name "$repo" || true)"
  [[ -n "$branch" ]] || die "failed to resolve current branch after raw sync"

  if has_uncommitted_changes "$repo"; then
    if ! run_batch_commit "$repo"; then
      return 1
    fi
    need_push="true"
  elif branch_ahead_of_upstream "$repo" || [[ -z "$(current_upstream_ref "$repo")" ]]; then
    record_result "batch_commit" "ok" "no new local changes to commit; branch will still be pushed"
    need_push="true"
  else
    record_result "batch_commit" "ok" "no local changes required a commit"
  fi

  if [[ "$need_push" == "true" ]]; then
    if ! push_current_branch "$repo" "$branch"; then
      return 1
    fi
    local receipt=""
    receipt="$(receipt_note "$repo" "$branch")"
    [[ -n "$receipt" ]] && record_result "receipt" "ok" "$receipt"
  else
    record_result "push" "ok" "branch '$branch' is already in sync with its upstream"
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

  if ! run_sync_stage "$repo"; then
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
      return 1
    fi
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
