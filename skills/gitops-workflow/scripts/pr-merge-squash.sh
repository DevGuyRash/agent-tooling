#!/usr/bin/env bash
set -euo pipefail

# pr-merge-squash.sh - Deterministic Squash & Merge runner for GitHub PRs.
#
# Usage:
#   bash scripts/pr-merge-squash.sh <pr_number> [--repo owner/repo] [--summary "<desc override>"] [--body-file <path> | --body-out <path>] [--admin] [--dry-run]
#
# Behavior:
# - Enforces unresolved-thread gate.
# - Enforces CI required checks and approval gate by default.
# - Generates deterministic squash message body (omits empty optional sections).
# - Always keeps Overview + Commits + Refs sections.
# - Optional --body-file uses an explicitly edited squash body for the merge.
# - Optional --body-out writes the deterministic draft body to a stable path for review/editing.
# - Merges with: gh pr merge --squash --subject --body-file --match-head-commit --delete-branch
# - Deletes the source branch after successful merge.
# - Optional --admin override relaxes approval/check gating and adds --admin to merge command.

die() {
  echo "Error: $*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

run_required_checks_gate() {
  local output=""
  if output="$(gh pr checks "${CHECK_ARGS[@]}" 2>&1)"; then
    printf '%s\n' "$output"
    return 0
  fi

  if printf '%s' "$output" | grep -Eqi 'no required checks|no checks reported|no status checks'; then
    printf '%s\n' "$output"
    echo "No required checks are configured for this PR; continuing."
    return 0
  fi

  printf '%s\n' "$output" >&2
  return 1
}

print_help() {
  cat <<'USAGE'
Usage:
  bash scripts/pr-merge-squash.sh <pr_number> [--repo owner/repo] [--summary "<desc override>"] [--body-file <path> | --body-out <path>] [--admin] [--dry-run]

Arguments:
  <pr_number>          Pull request number.

Options:
  --repo <owner/repo>  Optional repository override.
  --summary <text>     Optional replacement for Conventional Commit description segment.
  --body-file <path>   Use an explicitly prepared squash body file instead of the generated draft.
  --body-out <path>    Write the deterministic generated draft body to this path before merge/dry-run.
  --admin              Admin override: pass --admin to gh merge and relax pre-merge approval/check gates.
  --dry-run            Print subject/body and merge command without executing merge.
  -h, --help           Show help.
USAGE
}

require_cmd gh
require_cmd python3

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PR_NUMBER="${1:-}"
if [[ "$PR_NUMBER" == "-h" || "$PR_NUMBER" == "--help" || -z "$PR_NUMBER" ]]; then
  print_help
  exit 0
fi
shift || true

REPO=""
SUMMARY_OVERRIDE=""
DRY_RUN="false"
ADMIN_OVERRIDE="false"
BODY_FILE_INPUT=""
BODY_OUT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      REPO="${2:-}"
      shift 2
      ;;
    --summary)
      SUMMARY_OVERRIDE="${2:-}"
      shift 2
      ;;
    --body-file)
      BODY_FILE_INPUT="${2:-}"
      shift 2
      ;;
    --body-out)
      BODY_OUT="${2:-}"
      shift 2
      ;;
    --admin)
      ADMIN_OVERRIDE="true"
      shift
      ;;
    --dry-run)
      DRY_RUN="true"
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

if [[ -n "$BODY_FILE_INPUT" && -n "$BODY_OUT" ]]; then
  die "--body-file and --body-out cannot be combined"
fi

VIEW_ARGS=("$PR_NUMBER")
CHECK_ARGS=("$PR_NUMBER" --required)
THREAD_ARGS=("$PR_NUMBER" --fail-on-unresolved)
if [[ -n "$REPO" ]]; then
  VIEW_ARGS+=(--repo "$REPO")
  CHECK_ARGS+=(--repo "$REPO")
  THREAD_ARGS+=(--repo "$REPO")
fi

echo "== Unresolved inline threads gate =="
bash "$(dirname "$0")/pr-unresolved-threads.sh" "${THREAD_ARGS[@]}"

echo ""
echo "== Required CI checks gate =="
if [[ "$ADMIN_OVERRIDE" == "true" ]]; then
  if ! run_required_checks_gate; then
    echo "Admin override enabled; continuing despite required-check failures."
  fi
else
  run_required_checks_gate
fi

PR_JSON="$(gh pr view "${VIEW_ARGS[@]}" --json number,title,isDraft,url,reviewDecision,mergeStateStatus,headRefOid,commits)"

BODY_FILE=""
GENERATED_BODY_FILE=""
META_FILE="$(mktemp -t squash-meta.XXXXXX.json)"
trap 'rm -f "$GENERATED_BODY_FILE" "$META_FILE"' EXIT

if [[ -n "$BODY_FILE_INPUT" ]]; then
  [[ -f "$BODY_FILE_INPUT" ]] || die "body file not found: $BODY_FILE_INPUT"
  BODY_FILE="$BODY_FILE_INPUT"
  python3 - "$SUMMARY_OVERRIDE" "$META_FILE" "$PR_JSON" "$SCRIPT_DIR" <<'PY'
import json
import sys
from pathlib import Path

summary_override = (sys.argv[1] or "").strip()
meta_file = sys.argv[2]
data = json.loads(sys.argv[3])
script_dir = Path(sys.argv[4])
sys.path.insert(0, str(script_dir / "lib"))

from squash_renderer import build_subject  # noqa: E402

title = (data.get("title") or "").strip()
subject = build_subject(title, summary_override=summary_override)
meta = {
    "subject": subject,
    "headRefOid": data.get("headRefOid") or "",
    "reviewDecision": data.get("reviewDecision") or "",
    "isDraft": bool(data.get("isDraft", False)),
    "mergeStateStatus": data.get("mergeStateStatus") or "",
    "url": data.get("url") or "",
}
with open(meta_file, "w", encoding="utf-8") as f:
    json.dump(meta, f)
PY
else
  if [[ -n "$BODY_OUT" ]]; then
    BODY_FILE="$BODY_OUT"
  else
    GENERATED_BODY_FILE="$(mktemp -t squash-body.XXXXXX.md)"
    BODY_FILE="$GENERATED_BODY_FILE"
  fi

  python3 - "$SUMMARY_OVERRIDE" "$BODY_FILE" "$META_FILE" "$PR_JSON" "$SCRIPT_DIR" <<'PY'
import json
import sys
from pathlib import Path

summary_override = (sys.argv[1] or "").strip()
body_file = sys.argv[2]
meta_file = sys.argv[3]
data = json.loads(sys.argv[4])
script_dir = Path(sys.argv[5])
sys.path.insert(0, str(script_dir / "lib"))

from squash_renderer import CommitEntry, render_squash_message  # noqa: E402

title = (data.get("title") or "").strip()
commits_raw = data.get("commits") or []
if isinstance(commits_raw, dict):
    commits_raw = commits_raw.get("nodes") or []
elif not isinstance(commits_raw, list):
    commits_raw = []

commits = []
for item in commits_raw:
    if isinstance(item, dict) and "commit" in item and isinstance(item["commit"], dict):
        node = item["commit"]
    else:
        node = item if isinstance(item, dict) else {}
    commits.append(
        CommitEntry(
            sha=str(node.get("oid") or ""),
            headline=(node.get("messageHeadline") or node.get("message") or "").splitlines()[0].strip(),
            body=str(node.get("messageBody") or node.get("body") or ""),
        )
    )

number = data.get("number")
refs = [f"#{number}"] if number is not None else []
rendered = render_squash_message(
    title=title,
    commits=commits,
    pr_ref=f"PR #{number}" if number is not None else None,
    refs=refs,
    summary_override=summary_override,
)

with open(body_file, "w", encoding="utf-8") as f:
    f.write(rendered.body)

meta = {
    "subject": rendered.subject,
    "headRefOid": data.get("headRefOid") or "",
    "reviewDecision": data.get("reviewDecision") or "",
    "isDraft": bool(data.get("isDraft", False)),
    "mergeStateStatus": data.get("mergeStateStatus") or "",
    "url": data.get("url") or "",
}
with open(meta_file, "w", encoding="utf-8") as f:
    json.dump(meta, f)
PY
fi

SUBJECT="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["subject"])' "$META_FILE")"
HEAD_SHA="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["headRefOid"])' "$META_FILE")"
REVIEW_DECISION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["reviewDecision"])' "$META_FILE")"
IS_DRAFT="$(python3 -c 'import json,sys; print("true" if json.load(open(sys.argv[1], encoding="utf-8"))["isDraft"] else "false")' "$META_FILE")"
MERGE_STATE="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["mergeStateStatus"])' "$META_FILE")"
PR_URL="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["url"])' "$META_FILE")"

[[ -n "$HEAD_SHA" ]] || die "missing headRefOid for --match-head-commit"
[[ "$IS_DRAFT" == "false" ]] || die "PR is draft; mark ready for review before merge"

case "$MERGE_STATE" in
  CLEAN|HAS_HOOKS|UNSTABLE)
    ;;
  *)
    if [[ "$ADMIN_OVERRIDE" == "true" ]]; then
      echo "Admin override enabled; continuing despite mergeStateStatus=$MERGE_STATE"
    else
      die "merge state is not mergeable enough: $MERGE_STATE"
    fi
    ;;
esac

if [[ "$ADMIN_OVERRIDE" != "true" && "$REVIEW_DECISION" != "APPROVED" ]]; then
  die "missing approving review (reviewDecision=$REVIEW_DECISION)"
fi

echo ""
echo "== Deterministic squash subject =="
echo "$SUBJECT"
echo ""
echo "== Deterministic squash body =="
cat "$BODY_FILE"

MERGE_ARGS=(pr merge "$PR_NUMBER" --squash --subject "$SUBJECT" --body-file "$BODY_FILE" --match-head-commit "$HEAD_SHA" --delete-branch)
if [[ -n "$REPO" ]]; then
  MERGE_ARGS+=(--repo "$REPO")
fi
if [[ "$ADMIN_OVERRIDE" == "true" ]]; then
  MERGE_ARGS+=(--admin)
fi

if [[ "$DRY_RUN" == "true" ]]; then
  echo ""
  echo "DRY-RUN: gh ${MERGE_ARGS[*]}"
  exit 0
fi

gh "${MERGE_ARGS[@]}"

echo ""
echo "✅ Squash merge complete: $PR_URL"
echo "Receipt helper:"
echo "  python3 \"$SKILL_ROOT/scripts/receipt.py\" --branch \"\$(git rev-parse --abbrev-ref HEAD)\" --base origin/main --pr-url \"$PR_URL\""
