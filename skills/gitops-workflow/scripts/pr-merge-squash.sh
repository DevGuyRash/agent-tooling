#!/usr/bin/env bash
set -euo pipefail

# pr-merge-squash.sh - Deterministic Squash & Merge runner for GitHub PRs.
#
# Usage:
#   bash scripts/pr-merge-squash.sh <pr_number> [--repo owner/repo] [--summary "<desc override>"] [--admin] [--dry-run]
#
# Behavior:
# - Enforces unresolved-thread gate.
# - Enforces CI required checks and approval gate by default.
# - Generates deterministic squash message body (omits empty optional sections).
# - Always keeps Overview + Commits + Refs sections.
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

print_help() {
  cat <<'USAGE'
Usage:
  bash scripts/pr-merge-squash.sh <pr_number> [--repo owner/repo] [--summary "<desc override>"] [--admin] [--dry-run]

Arguments:
  <pr_number>          Pull request number.

Options:
  --repo <owner/repo>  Optional repository override.
  --summary <text>     Optional replacement for Conventional Commit description segment.
  --admin              Admin override: pass --admin to gh merge and relax pre-merge approval/check gates.
  --dry-run            Print subject/body and merge command without executing merge.
  -h, --help           Show help.
USAGE
}

require_cmd gh
require_cmd python3

case "${BASH_SOURCE[0]}" in
  */*) SCRIPT_DIR="$(cd "${BASH_SOURCE[0]%/*}" && pwd -P)" ;;
  *) SCRIPT_DIR="$(pwd -P)" ;;
esac
# shellcheck source=skills/gitops-workflow/scripts/lib/bootstrap.sh
source "$SCRIPT_DIR/lib/bootstrap.sh"
gitops_workflow_maybe_reexec_repo_local_copy "$SCRIPT_DIR" "pr-merge-squash.sh" "$@"
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
  if ! gh pr checks "${CHECK_ARGS[@]}"; then
    echo "Admin override enabled; continuing despite required-check failures."
  fi
else
  gh pr checks "${CHECK_ARGS[@]}"
fi

PR_JSON="$(gh pr view "${VIEW_ARGS[@]}" --json number,title,isDraft,url,reviewDecision,mergeStateStatus,headRefOid,commits)"

BODY_FILE="$(mktemp -t squash-body.XXXXXX.md)"
META_FILE="$(mktemp -t squash-meta.XXXXXX.json)"
trap 'rm -f "$BODY_FILE" "$META_FILE"' EXIT

python3 - "$SUMMARY_OVERRIDE" "$BODY_FILE" "$META_FILE" "$PR_JSON" <<'PY'
import json
import re
import sys

summary_override = (sys.argv[1] or "").strip()
body_file = sys.argv[2]
meta_file = sys.argv[3]
data = json.loads(sys.argv[4])
title = (data.get("title") or "").strip()

cc = re.compile(r"^(?P<prefix>[a-z]+(?:\([^)]+\))?(?:!)?:\s)(?P<desc>.+)$")
m = cc.match(title)
if not m:
    sys.stderr.write("Error: PR title must follow Conventional Commits format for squash subject\n")
    raise SystemExit(2)

subject = title
if summary_override:
    subject = f"{m.group('prefix')}{summary_override}"

commits_raw = data.get("commits") or []
if isinstance(commits_raw, dict):
    commits = commits_raw.get("nodes") or []
elif isinstance(commits_raw, list):
    commits = commits_raw
else:
    commits = []

feat = []
fixes = []
changes = []
breaking = []
commit_lines = []

cc_subject = re.compile(r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]+)\))?(?P<bang>!)?:\s(?P<desc>.+)$")

for c in commits:
    if isinstance(c, dict) and "commit" in c and isinstance(c["commit"], dict):
        node = c["commit"]
    else:
        node = c if isinstance(c, dict) else {}

    oid = str(node.get("oid") or "")
    headline = (node.get("messageHeadline") or node.get("message") or "").splitlines()[0].strip()
    body = str(node.get("messageBody") or node.get("body") or "")

    short = oid[:7] if oid else "unknown"
    if headline:
        commit_lines.append(f"- `{short}` {headline}")
    else:
        commit_lines.append(f"- `{short}` <no headline>")

    parsed = cc_subject.match(headline)
    if not parsed:
        if headline:
            changes.append(f"- {headline}")
        continue

    typ = parsed.group("type")
    scope = parsed.group("scope")
    desc = parsed.group("desc")
    is_breaking = bool(parsed.group("bang")) or ("BREAKING CHANGE" in body)

    scope_prefix = f"{scope}: " if scope else ""
    bullet = f"- {scope_prefix}{desc}"

    if typ == "feat":
        feat.append(bullet)
    elif typ in {"fix", "hotfix"}:
        fixes.append(bullet)
    else:
        changes.append(bullet)

    if is_breaking:
        breaking.append(f"- {scope_prefix}{desc}; migration: <add steps>")

number = data.get("number")
pr_ref = f"#{number}" if number is not None else "<pr>"

def append_section(lines, title, bullets, always=False, empty_bullet="- (none)"):
    if not bullets and not always:
        return
    lines.extend([f"## {title}", ""])
    if bullets:
        lines.extend(bullets)
    else:
        lines.append(empty_bullet)
    lines.append("")

lines = [
    "## Overview",
    "",
    f"Squash merge for PR {pr_ref}.",
    "",
]

append_section(lines, "New Features", feat)
append_section(lines, "What's Changed", changes)
append_section(lines, "Bug Fixes", fixes)
append_section(lines, "Breaking Changes", breaking)
append_section(
    lines,
    "Commits",
    commit_lines,
    always=True,
    empty_bullet="- (none reported by API)",
)

ref_lines = []
if number is not None:
    ref_lines.append(f"- #{number}")
append_section(lines, "Refs", ref_lines, always=True, empty_bullet="- (none provided)")

if lines and lines[-1] == "":
    lines.pop()

with open(body_file, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")

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
