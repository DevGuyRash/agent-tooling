#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_STATE_SCRIPT = SCRIPT_DIR / "repo-state.sh"

THREAD_QUERY = """
query($owner:String!, $repo:String!, $number:Int!, $after:String) {
  repository(owner:$owner, name:$repo) {
    pullRequest(number:$number) {
      number
      title
      url
      state
      isDraft
      baseRefName
      headRefName
      reviewDecision
      mergeable
      mergeStateStatus
      reviewRequests(first:50) {
        nodes {
          requestedReviewer {
            __typename
            ... on User {
              login
            }
            ... on Team {
              slug
              name
            }
          }
        }
      }
      latestReviews(first:50) {
        nodes {
          state
          submittedAt
          author {
            login
          }
        }
      }
      reviewThreads(first:100, after:$after) {
        pageInfo {
          hasNextPage
          endCursor
        }
        nodes {
          id
          isResolved
          comments(first:20) {
            nodes {
              author {
                login
              }
              path
              line
              url
              body
            }
          }
        }
      }
    }
  }
}
""".strip()


class CommandError(RuntimeError):
    pass


def run(cmd: list[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}"
        raise CommandError(detail)
    return proc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Report deterministic PR readiness across CI, review state, and local git tree state."
    )
    parser.add_argument("pr_number", type=int)
    parser.add_argument("--repo", help="GitHub repo slug (owner/repo). Inferred from the local checkout when omitted.")
    parser.add_argument("--local-repo", default=".", help="Local repository used for branch/tree state checks (default: current directory).")
    parser.add_argument("--scope", choices=("current", "tree"), default="current")
    parser.add_argument("--watch-checks", action="store_true", help="Wait for required checks to settle before reporting.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    return parser.parse_args()


def infer_repo_slug(local_repo: Path) -> str:
    gh_proc = run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
        cwd=local_repo,
        check=False,
    )
    slug = gh_proc.stdout.strip()
    if gh_proc.returncode == 0 and slug:
        return slug

    remote = run(["git", "remote", "get-url", "origin"], cwd=local_repo, check=False).stdout.strip()
    if remote.startswith("git@github.com:"):
        return remote.split(":", 1)[1].removesuffix(".git")
    if remote.startswith("ssh://git@github.com/"):
        return remote.split("ssh://git@github.com/", 1)[1].removesuffix(".git")
    if "github.com/" in remote:
        return remote.split("github.com/", 1)[1].removesuffix(".git").split("?", 1)[0].split("#", 1)[0]
    raise CommandError("could not infer GitHub repo slug; pass --repo owner/repo")


def normalize_reviewer(node: dict[str, Any]) -> str | None:
    reviewer = (node or {}).get("requestedReviewer") or {}
    kind = reviewer.get("__typename")
    if kind == "User":
        return reviewer.get("login")
    if kind == "Team":
        slug = reviewer.get("slug") or reviewer.get("name")
        if slug:
            return f"team:{slug}"
    return None


def fetch_pr_graph(owner: str, repo: str, pr_number: int) -> dict[str, Any]:
    after = None
    pr_payload: dict[str, Any] | None = None
    unresolved_threads: list[dict[str, Any]] = []
    resolved_thread_count = 0

    while True:
        cmd = [
            "gh",
            "api",
            "graphql",
            "-F",
            f"owner={owner}",
            "-F",
            f"repo={repo}",
            "-F",
            f"number={pr_number}",
            "-f",
            f"query={THREAD_QUERY}",
        ]
        if after:
            cmd.extend(["-F", f"after={after}"])
        proc = run(cmd)
        payload = json.loads(proc.stdout)
        pr = (((payload.get("data") or {}).get("repository") or {}).get("pullRequest"))
        if not pr:
            raise CommandError(f"pull request #{pr_number} was not found in {owner}/{repo}")
        if pr_payload is None:
            pr_payload = pr

        threads = ((pr.get("reviewThreads") or {}).get("nodes") or [])
        for thread in threads:
            comments = ((thread.get("comments") or {}).get("nodes") or [])
            last_comment = comments[-1] if comments else {}
            entry = {
                "thread_id": thread.get("id"),
                "resolved": bool(thread.get("isResolved")),
                "path": last_comment.get("path"),
                "line": last_comment.get("line"),
                "url": last_comment.get("url"),
                "author": ((last_comment.get("author") or {}).get("login")),
                "body": last_comment.get("body") or "",
            }
            if entry["resolved"]:
                resolved_thread_count += 1
            else:
                unresolved_threads.append(entry)

        page_info = (pr.get("reviewThreads") or {}).get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break
        after = page_info.get("endCursor")
        if not after:
            raise CommandError("review thread pagination reported more data without a cursor")

    assert pr_payload is not None
    requested_reviewers = [
        reviewer for reviewer in (normalize_reviewer(node) for node in ((pr_payload.get("reviewRequests") or {}).get("nodes") or [])) if reviewer
    ]
    latest_reviews = []
    for node in ((pr_payload.get("latestReviews") or {}).get("nodes") or []):
        author = (node.get("author") or {}).get("login")
        latest_reviews.append(
            {
                "author": author,
                "state": node.get("state") or "UNKNOWN",
                "submitted_at": node.get("submittedAt"),
            }
        )

    return {
        "number": pr_payload.get("number"),
        "title": pr_payload.get("title") or "",
        "url": pr_payload.get("url") or "",
        "state": pr_payload.get("state") or "UNKNOWN",
        "is_draft": bool(pr_payload.get("isDraft")),
        "base_branch": pr_payload.get("baseRefName") or "",
        "head_branch": pr_payload.get("headRefName") or "",
        "review_decision": pr_payload.get("reviewDecision") or "UNKNOWN",
        "mergeable": pr_payload.get("mergeable") or "UNKNOWN",
        "merge_state_status": pr_payload.get("mergeStateStatus") or "UNKNOWN",
        "requested_reviewers": requested_reviewers,
        "latest_reviews": latest_reviews,
        "unresolved_threads": unresolved_threads,
        "resolved_thread_count": resolved_thread_count,
    }


def fetch_required_checks(pr_number: int, repo_slug: str | None, watch_checks: bool) -> dict[str, Any]:
    cmd = [
        "gh",
        "pr",
        "checks",
        str(pr_number),
        "--required",
        "--json",
        "bucket,completedAt,description,event,link,name,startedAt,state,workflow",
    ]
    if repo_slug:
        cmd.extend(["--repo", repo_slug])
    if watch_checks:
        cmd.append("--watch")

    proc = run(cmd, check=False)
    checks: list[dict[str, Any]] = []
    error = ""
    stdout = proc.stdout.strip()
    if stdout.startswith("["):
        checks, _ = json.JSONDecoder().raw_decode(stdout)
    elif proc.returncode != 0:
        error = proc.stderr.strip() or stdout or f"gh pr checks exited {proc.returncode}"
    elif stdout:
        error = f"unexpected non-JSON gh pr checks output: {stdout}"

    passed = 0
    pending = 0
    failed = 0
    for item in checks:
        bucket = (item.get("bucket") or "").lower()
        state = str(item.get("state") or "").upper()
        if bucket == "pass" or state in {"SUCCESS", "PASSED", "PASS"}:
            passed += 1
        elif bucket in {"pending", "skipping"} or state in {"PENDING", "IN_PROGRESS", "QUEUED", "EXPECTED", "REQUESTED", "WAITING"}:
            pending += 1
        elif bucket:
            failed += 1
        elif state in {"FAILURE", "FAILED", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE"}:
            failed += 1
        else:
            pending += 1

    if error:
        status = "unavailable"
    elif not checks:
        status = "not-configured"
    elif failed:
        status = "failing"
    elif pending:
        status = "pending"
    else:
        status = "passing"

    return {
        "status": status,
        "required_checks": checks,
        "counts": {
            "total": len(checks),
            "passed": passed,
            "pending": pending,
            "failed": failed,
        },
        "blocking": status in {"pending", "failing", "unavailable"},
        "note": error,
    }


def git_toplevel(local_repo: Path) -> Path:
    proc = run(["git", "rev-parse", "--show-toplevel"], cwd=local_repo, check=False)
    if proc.returncode == 0 and proc.stdout.strip():
        return Path(proc.stdout.strip()).resolve()
    return local_repo.resolve()


def fetch_repo_state(local_repo: Path, scope: str) -> dict[str, Any]:
    cmd = ["bash", str(REPO_STATE_SCRIPT), "--repo", str(local_repo), "--json"]
    if scope == "current":
        cmd.append("--no-recurse-related")
    proc = run(cmd)
    payload = json.loads(proc.stdout)
    current_root = git_toplevel(local_repo)
    current_item = None
    for item in payload.get("results", []):
        if Path(item.get("repo", "")).resolve() == current_root:
            current_item = item
            break
    if current_item is None and payload.get("results"):
        current_item = payload["results"][0]
    issues = []
    for item in payload.get("results", []):
        problems = describe_repo_problems(item)
        if problems:
            issues.append({
                "repo": item.get("repo"),
                "role": item.get("role"),
                "problems": problems,
            })
    return {
        "scope": payload.get("scope") or scope,
        "root_repo": payload.get("root_repo") or str(current_root),
        "current_repo": current_item,
        "repos": payload.get("results", []),
        "issues": issues,
        "status": "attention" if issues else "clean",
    }


def describe_repo_problems(item: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if item.get("detached"):
        problems.append("detached HEAD")
    sequencer = item.get("sequencer_state") or ""
    if sequencer:
        problems.append(f"in-progress git operation ({sequencer})")
    dirty_tracked = int(item.get("dirty_tracked") or 0)
    dirty_untracked = int(item.get("dirty_untracked") or 0)
    if dirty_tracked or dirty_untracked:
        problems.append(f"dirty working tree (tracked={dirty_tracked}, untracked={dirty_untracked})")
    ahead = int(item.get("ahead") or 0)
    behind = int(item.get("behind") or 0)
    if ahead:
        problems.append(f"{ahead} local commit(s) not pushed")
    if behind:
        problems.append(f"{behind} upstream commit(s) not synced")
    recovery_class = item.get("recovery_class") or "none"
    if recovery_class != "none":
        problems.append(f"recovery class {recovery_class}")
    gitlink_status = item.get("gitlink_status") or "none"
    if gitlink_status not in {"none", "aligned"}:
        problems.append(f"gitlink status {gitlink_status}")
    return problems


def build_branch_state(current_repo: dict[str, Any] | None) -> dict[str, Any]:
    if not current_repo:
        return {
            "status": "unavailable",
            "note": "local git state could not be determined",
        }
    problems = describe_repo_problems(current_repo)
    return {
        "repo": current_repo.get("repo"),
        "branch": current_repo.get("branch"),
        "default_base": current_repo.get("default_base"),
        "upstream": current_repo.get("upstream"),
        "ahead": int(current_repo.get("ahead") or 0),
        "behind": int(current_repo.get("behind") or 0),
        "detached": bool(current_repo.get("detached")),
        "dirty_tracked": int(current_repo.get("dirty_tracked") or 0),
        "dirty_untracked": int(current_repo.get("dirty_untracked") or 0),
        "sequencer_state": current_repo.get("sequencer_state") or "",
        "recovery_class": current_repo.get("recovery_class") or "none",
        "gitlink_status": current_repo.get("gitlink_status") or "none",
        "status": "attention" if problems else "clean",
        "problems": problems,
    }


def build_reviews(pr: dict[str, Any]) -> dict[str, Any]:
    approval_count = sum(1 for review in pr.get("latest_reviews", []) if review.get("state") == "APPROVED")
    changes_requested_count = sum(
        1 for review in pr.get("latest_reviews", []) if review.get("state") == "CHANGES_REQUESTED"
    )
    unresolved_threads = pr.get("unresolved_threads", [])
    blocking = []
    if unresolved_threads:
        blocking.append(f"{len(unresolved_threads)} unresolved review thread(s)")
    if pr.get("review_decision") == "CHANGES_REQUESTED":
        blocking.append("changes were requested in the latest review state")
    return {
        "decision": pr.get("review_decision") or "UNKNOWN",
        "requested_reviewers": pr.get("requested_reviewers", []),
        "latest_reviews": pr.get("latest_reviews", []),
        "approval_count": approval_count,
        "changes_requested_count": changes_requested_count,
        "unresolved_thread_count": len(unresolved_threads),
        "resolved_thread_count": int(pr.get("resolved_thread_count") or 0),
        "unresolved_threads": unresolved_threads,
        "blocking_reasons": blocking,
    }


def build_readiness(pr: dict[str, Any], ci: dict[str, Any], reviews: dict[str, Any], branch_state: dict[str, Any], tree_state: dict[str, Any]) -> dict[str, Any]:
    blocking_reasons: list[str] = []
    attention_items: list[str] = []

    if ci.get("blocking"):
        note = ci.get("note") or "required checks are not green"
        if ci.get("status") == "pending":
            blocking_reasons.append("required checks are still pending")
        elif ci.get("status") == "failing":
            blocking_reasons.append("required checks are failing")
        else:
            blocking_reasons.append(f"required check status is unavailable ({note})")
    elif ci.get("status") == "not-configured":
        attention_items.append("no required GitHub checks are configured for this PR")

    blocking_reasons.extend(reviews.get("blocking_reasons", []))

    if pr.get("mergeable") == "CONFLICTING" or pr.get("merge_state_status") == "DIRTY":
        blocking_reasons.append("the PR has merge conflicts against the base branch")

    branch_problems = list(branch_state.get("problems", []))
    if branch_problems:
        blocking_reasons.extend(f"local branch state: {problem}" for problem in branch_problems)

    tree_issues = tree_state.get("issues", [])
    if tree_issues:
        current_repo = branch_state.get("repo")
        for issue in tree_issues:
            if current_repo and issue.get("repo") == current_repo:
                continue
            repo = issue.get("repo")
            role = issue.get("role") or "repo"
            for problem in issue.get("problems", []):
                message = f"{role} {repo}: {problem}" if repo else problem
                if message not in blocking_reasons:
                    blocking_reasons.append(message)

    if pr.get("review_decision") == "REVIEW_REQUIRED":
        attention_items.append("review is still required after the draft is marked ready")
    if pr.get("requested_reviewers"):
        attention_items.append(
            "outstanding review requests: " + ", ".join(pr.get("requested_reviewers", []))
        )

    is_draft = bool(pr.get("is_draft"))
    if is_draft:
        safe_to_mark_ready = not blocking_reasons
        status = "ready" if safe_to_mark_ready else "blocked"
    else:
        safe_to_mark_ready = True
        status = "already-ready"
        attention_items = blocking_reasons + attention_items
        blocking_reasons = []

    if not is_draft:
        if attention_items:
            next_action = "Address the reported PR or tree issues before merging or requesting another review cycle."
        else:
            next_action = "PR is already ready for review; keep monitoring CI and feedback."
    elif safe_to_mark_ready:
        next_action = "Run pr-mark-ready.sh when you want to move this draft PR to ready for review."
    else:
        next_action = "Resolve the blocking readiness items, push any missing local commits, and rerun the readiness check."

    return {
        "status": status,
        "safe_to_mark_ready": safe_to_mark_ready,
        "blocking_reasons": blocking_reasons,
        "attention_items": attention_items,
        "draft": is_draft,
        "next_action": next_action,
    }


def render_text(payload: dict[str, Any]) -> str:
    pr = payload["pr"]
    ci = payload["ci"]
    reviews = payload["reviews"]
    branch = payload["branch_state"]
    readiness = payload["readiness"]
    lines = [
        f"PR #{pr['number']}: {pr['title']}",
        f"URL: {pr['url']}",
        f"Draft: {'yes' if pr['is_draft'] else 'no'}",
        f"Checks: {ci['status']} (required={ci['counts']['total']}, passed={ci['counts']['passed']}, pending={ci['counts']['pending']}, failed={ci['counts']['failed']})",
        f"Reviews: decision={reviews['decision']}, unresolved_threads={reviews['unresolved_thread_count']}, approvals={reviews['approval_count']}, changes_requested={reviews['changes_requested_count']}",
        f"Branch state: {branch.get('status', 'unavailable')} ({branch.get('branch', 'unknown')})",
        f"Tree state: {payload['tree_state']['status']} ({payload['tree_state']['scope']})",
        f"Readiness: {readiness['status']}",
    ]
    for reason in readiness.get("blocking_reasons", []):
        lines.append(f"- blocker: {reason}")
    for item in readiness.get("attention_items", []):
        lines.append(f"- note: {item}")
    lines.append(f"Next: {payload['next_action']}")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    local_repo = Path(args.local_repo).resolve()
    repo_slug = args.repo or infer_repo_slug(local_repo)
    if "/" not in repo_slug:
        raise CommandError(f"invalid GitHub repo slug: {repo_slug}")
    owner, repo = repo_slug.split("/", 1)

    pr = fetch_pr_graph(owner, repo, args.pr_number)
    ci = fetch_required_checks(args.pr_number, repo_slug, args.watch_checks)
    repo_state = fetch_repo_state(local_repo, args.scope)
    branch_state = build_branch_state(repo_state.get("current_repo"))
    reviews = build_reviews(pr)
    readiness = build_readiness(pr, ci, reviews, branch_state, repo_state)

    payload = {
        "repo": repo_slug,
        "pr": pr,
        "ci": ci,
        "reviews": reviews,
        "branch_state": branch_state,
        "tree_state": {
            "scope": repo_state.get("scope") or args.scope,
            "root_repo": repo_state.get("root_repo"),
            "status": repo_state.get("status"),
            "issue_count": len(repo_state.get("issues", [])),
            "issues": repo_state.get("issues", []),
            "repos": repo_state.get("repos", []),
        },
        "local_validation": {
            "status": "not-run",
            "note": "Repo-specific local validation remains agent-driven and is not run by pr-readiness-report.py.",
        },
        "readiness": readiness,
        "next_action": readiness["next_action"],
    }

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(render_text(payload))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CommandError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
