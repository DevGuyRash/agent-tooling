#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT_DOC_NAMES = {
    "readme",
    "changelog",
    "contributing",
    "license",
    "copying",
    "authors",
    "notice",
}
DOC_EXTENSIONS = {".md", ".mdx", ".rst", ".adoc", ".txt"}
DEP_FILENAMES = {
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "cargo.toml",
    "cargo.lock",
    "requirements.txt",
    "requirements-dev.txt",
    "poetry.lock",
    "pyproject.toml",
    "go.mod",
    "go.sum",
    "composer.json",
    "composer.lock",
    "gemfile",
    "gemfile.lock",
}
CI_PREFIXES = (
    ".github/",
    ".gitlab/",
    ".circleci/",
    ".ci/",
    "ci/",
    ".buildkite/",
)
TEST_PREFIXES = ("tests/", "test/", "__tests__/", "spec/")
DOC_PREFIXES = ("docs/", "doc/", "references/", "context/", ".local/context/")
BUCKET_ORDER = ["submodules", "docs", "tests", "ci", "deps", "chore"]
TRUTHY = {"1", "true", "yes", "on"}
HEADER_RE = re.compile(r"^[a-z][a-z0-9-]*$")
COMMIT_SIGNING_FAILURE_PATTERNS = (
    "gpg failed to sign the data",
    "failed to write commit object",
    "no secret key",
    "could not open a connection to your authentication agent",
    "error: no pinentry",
    "signing failed",
)


@dataclass(frozen=True)
class BucketSpec:
    commit_type: str
    scope: str | None
    subject: str
    bullets: tuple[str, ...]


BUCKET_SPECS = {
    "submodules": BucketSpec(
        commit_type="chore",
        scope="submodules",
        subject="update gitlinks",
        bullets=(
            "align parent gitlinks with the checked-out child repositories",
            "keep related repository pointers consistent before the next push",
        ),
    ),
    "docs": BucketSpec(
        commit_type="docs",
        scope=None,
        subject="update documentation",
        bullets=(
            "refresh the documented workflow and usage details for the current changes",
            "keep the written guidance aligned with the shipped behavior",
        ),
    ),
    "tests": BucketSpec(
        commit_type="test",
        scope=None,
        subject="refresh test coverage",
        bullets=(
            "cover the behavior touched by the current worktree changes",
            "keep the scripted contract stable for future edits",
        ),
    ),
    "ci": BucketSpec(
        commit_type="ci",
        scope=None,
        subject="update workflow automation",
        bullets=(
            "adjust repository automation for the current workflow changes",
            "keep the automation path consistent with local expectations",
        ),
    ),
    "deps": BucketSpec(
        commit_type="deps",
        scope=None,
        subject="refresh dependencies",
        bullets=(
            "capture the dependency state needed by the current changes",
            "keep the repo dependency metadata in sync with the worktree",
        ),
    ),
    "chore": BucketSpec(
        commit_type="chore",
        scope=None,
        subject="update tracked changes",
        bullets=(
            "capture the remaining tracked worktree updates in a deterministic batch",
            "keep the branch state consistent before the next workflow step",
        ),
    ),
}


def run(cmd: list[str], *, cwd: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=check,
    )


def output_text(proc: subprocess.CompletedProcess[str]) -> str:
    return ((proc.stdout or "") + (proc.stderr or "")).strip()


class BatchCommitFailure(Exception):
    def __init__(self, payload: dict[str, object]):
        super().__init__(str(payload.get("error", "batch commit failed")))
        self.payload = payload


def env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in TRUTHY


def git_success(repo: str, *args: str) -> bool:
    return run(["git", "-C", repo, *args], cwd=repo, check=False).returncode == 0


def repo_root(repo: str) -> str:
    proc = run(["git", "-C", repo, "rev-parse", "--show-toplevel"], cwd=repo, check=False)
    if proc.returncode != 0:
        raise SystemExit(output_text(proc) or f"--repo is not a git repository: {repo}")
    return str(Path(proc.stdout.strip()).resolve())


def repo_superproject_path(repo: str) -> str:
    proc = run(["git", "-C", repo, "rev-parse", "--show-superproject-working-tree"], cwd=repo, check=False)
    return (proc.stdout or "").strip()


def outermost_superproject_path(repo: str) -> str:
    current = repo_root(repo)
    while True:
        parent = repo_superproject_path(current)
        if not parent:
            return current
        current = str(Path(parent).resolve())


def list_child_submodule_paths(repo: str) -> list[str]:
    root = repo_root(repo)
    gitmodules = Path(root) / ".gitmodules"
    if not gitmodules.is_file():
        return []
    proc = run(
        ["git", "-C", root, "config", "-f", str(gitmodules), "--get-regexp", r"^submodule\..*\.path$"],
        cwd=root,
        check=False,
    )
    if proc.returncode != 0:
        return []
    paths: list[str] = []
    for line in (proc.stdout or "").splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            continue
        child = str((Path(root) / parts[1]).resolve())
        if git_success(child, "rev-parse", "--is-inside-work-tree"):
            paths.append(child)
    return paths


def list_related_repos(repo: str) -> list[tuple[int, str]]:
    root = outermost_superproject_path(repo)
    results: list[tuple[int, str]] = []

    def walk(path: str, depth: int) -> None:
        results.append((depth, path))
        for child in list_child_submodule_paths(path):
            walk(child, depth + 1)

    walk(root, 0)
    return results


def related_repos(repo: str, scope: str) -> list[tuple[int, str]]:
    current = repo_root(repo)
    if scope == "current":
        return [(0, current)]
    return sorted(list_related_repos(repo), key=lambda item: (-item[0], item[1]))


def current_branch(repo: str) -> str | None:
    proc = run(["git", "-C", repo, "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo, check=False)
    branch = (proc.stdout or "").strip()
    if proc.returncode != 0 or branch in {"", "HEAD"}:
        return None
    return branch


def current_upstream_ref(repo: str) -> str:
    proc = run(
        ["git", "-C", repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
        cwd=repo,
        check=False,
    )
    return (proc.stdout or "").strip()


def resolve_default_base(repo: str) -> str:
    proc = run(["git", "-C", repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD"], cwd=repo, check=False)
    branch = (proc.stdout or "").strip().removeprefix("origin/")
    if branch:
        return branch
    for candidate in ("main", "master", "trunk"):
        if git_success(repo, "show-ref", "--verify", "--quiet", f"refs/heads/{candidate}"):
            return candidate
    return ""


def repo_ahead_behind(repo: str, upstream: str) -> tuple[int, int]:
    if not upstream:
        return (0, 0)
    proc = run(["git", "-C", repo, "rev-list", "--left-right", "--count", f"HEAD...{upstream}"], cwd=repo, check=False)
    if proc.returncode != 0:
        return (0, 0)
    parts = (proc.stdout or "").split()
    if len(parts) != 2:
        return (0, 0)
    return (int(parts[0]), int(parts[1]))


def repo_dirty_tracked_count(repo: str) -> int:
    proc = run(["git", "-C", repo, "status", "--porcelain"], cwd=repo, check=False)
    return sum(1 for line in (proc.stdout or "").splitlines() if line[:2] != "??")


def repo_dirty_untracked_count(repo: str) -> int:
    proc = run(["git", "-C", repo, "ls-files", "--others", "--exclude-standard"], cwd=repo, check=False)
    return len([line for line in (proc.stdout or "").splitlines() if line])


def repo_sequencer_state(repo: str) -> list[str]:
    git_dir = Path(run(["git", "-C", repo, "rev-parse", "--git-dir"], cwd=repo).stdout.strip())
    states: list[str] = []
    if (git_dir / "MERGE_HEAD").exists():
        states.append("merge")
    if (git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists() or (git_dir / "REBASE_HEAD").exists():
        states.append("rebase")
    if (git_dir / "CHERRY_PICK_HEAD").exists():
        states.append("cherry-pick")
    if (git_dir / "REVERT_HEAD").exists():
        states.append("revert")
    if (git_dir / "BISECT_LOG").exists():
        states.append("bisect")
    return states


def changed_paths(repo: str) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    sources = [
        ["diff", "--cached", "--name-only", "-z", "--"],
        ["diff", "--name-only", "-z", "HEAD", "--"],
        ["ls-files", "--others", "--exclude-standard", "-z"],
    ]
    for args in sources:
        proc = run(["git", "-C", repo, *args], cwd=repo, check=False)
        raw = proc.stdout
        if not raw:
            continue
        for item in raw.split("\0"):
            if not item or item in seen:
                continue
            seen.add(item)
            paths.append(item)
    return paths


def is_submodule(repo: str, path: str) -> bool:
    proc = run(["git", "-C", repo, "ls-files", "-s", "--", path], cwd=repo, check=False)
    line = (proc.stdout or "").strip()
    return bool(line and line.split()[0] == "160000")


def bucket_for_path(repo: str, path: str) -> str:
    norm = path.lower().replace("\\", "/")
    base = os.path.basename(norm)
    stem = base.rsplit(".", 1)[0]
    if is_submodule(repo, path):
        return "submodules"
    if norm.startswith(CI_PREFIXES) or base in {"justfile", "earthfile"}:
        return "ci"
    if norm.startswith(TEST_PREFIXES) or stem.startswith("test_") or base.endswith("_test.py"):
        return "tests"
    if norm.startswith(DOC_PREFIXES) or Path(base).suffix in DOC_EXTENSIONS or stem in ROOT_DOC_NAMES:
        return "docs"
    if base in DEP_FILENAMES:
        return "deps"
    return "chore"


def path_summary(paths: list[str]) -> str:
    if not paths:
        return "this repo"
    display = sorted(paths)
    if len(display) <= 3:
        return ", ".join(display)
    return f"{', '.join(display[:3])}, and {len(display) - 3} more paths"


def role_for_repo(requested_repo: str, candidate_repo: str) -> str:
    current_root = repo_root(requested_repo)
    outer_root = outermost_superproject_path(requested_repo)
    if candidate_repo == current_root == outer_root:
        return "current-root"
    if candidate_repo == current_root:
        return "current"
    if candidate_repo == outer_root:
        return "root"
    return "submodule"


def repo_commit_safety(repo: str, mode: str) -> tuple[bool, str]:
    branch = current_branch(repo)
    sequencer = repo_sequencer_state(repo)
    if sequencer:
        return (False, f"repo is mid-{','.join(sequencer)}")
    if branch is None:
        return (False, "repo is detached")
    return (True, "ready")


def inventory_entry(requested_repo: str, repo: str, mode: str) -> dict[str, object]:
    branch = current_branch(repo)
    default_base = resolve_default_base(repo)
    upstream = current_upstream_ref(repo)
    ahead, behind = repo_ahead_behind(repo, upstream)
    changed = changed_paths(repo)
    safe_to_commit, commit_note = repo_commit_safety(repo, mode)
    entry: dict[str, object] = {
        "repo": repo,
        "role": role_for_repo(requested_repo, repo),
        "branch": branch or "DETACHED",
        "default_base": default_base,
        "upstream": upstream,
        "ahead": ahead,
        "behind": behind,
        "dirty_tracked": repo_dirty_tracked_count(repo),
        "dirty_untracked": repo_dirty_untracked_count(repo),
        "sequencer_state": repo_sequencer_state(repo),
        "changed_paths": changed,
        "changed_path_count": len(changed),
        "safe_to_commit": safe_to_commit,
        "commit_safety_note": commit_note,
    }
    if repo == outermost_superproject_path(requested_repo):
        entry["tree_order_hint"] = "push parent last after child commits and gitlink reconciliation"
    else:
        entry["tree_order_hint"] = "commit and push children before parents"
    return entry


def classify_commit_failure(text: str) -> str | None:
    lower = text.lower()
    for pattern in COMMIT_SIGNING_FAILURE_PATTERNS:
        if pattern in lower:
            return "commit-signing-unavailable"
    return None


def commit_failure_payload(
    *,
    commit_index: int | None,
    repo: str,
    paths: list[str],
    output: str,
    allow_unsigned_retry: bool,
    unsigned_retry_attempted: bool,
) -> dict[str, object]:
    failure_class = classify_commit_failure(output)
    payload: dict[str, object] = {
        "status": "blocked" if failure_class == "commit-signing-unavailable" else "error",
        "commit_index": commit_index,
        "repo": repo,
        "paths": paths,
        "error": output or "git commit failed",
        "failure_class": failure_class or "commit-failed",
        "unsigned_retry_available": failure_class == "commit-signing-unavailable",
        "unsigned_retry_enabled": allow_unsigned_retry,
        "unsigned_retry_attempted": unsigned_retry_attempted,
        "unsigned_retry_used": False,
    }
    if failure_class == "commit-signing-unavailable":
        payload["helper_text"] = (
            "Commit signing appears unavailable. If the user approves, rerun with "
            "GITOPS_ALLOW_UNSIGNED_COMMIT_RETRY=1 to allow one unsigned commit retry."
        )
        payload["next_action"] = (
            "Ask the user whether to rerun with GITOPS_ALLOW_UNSIGNED_COMMIT_RETRY=1 "
            "to allow one unsigned commit retry."
        )
    return payload


def render_commit_message(
    message_script: str,
    *,
    commit_type: str,
    scope: str | None,
    subject: str,
    bullets: list[str],
    footers: list[str],
    cwd: str,
) -> str:
    with tempfile.TemporaryDirectory() as temp_dir:
        out = Path(temp_dir) / "commit-message.txt"
        cmd = ["python3", message_script, "--type", commit_type, "--subject", subject]
        if scope:
            cmd.extend(["--scope", scope])
        for bullet in bullets:
            cmd.extend(["--bullet", bullet])
        for footer in footers:
            cmd.extend(["--footer", footer])
        cmd.extend(["--out", str(out)])
        proc = run(cmd, cwd=cwd, check=False)
        if proc.returncode != 0:
            raise SystemExit(output_text(proc) or "failed to generate commit message")
        return out.read_text(encoding="utf-8")


def stage_and_commit(
    repo: str,
    paths: list[str],
    message: str,
    sensitive_scan: str,
    signing_off: bool,
    allow_unsigned_retry: bool,
    commit_index: int | None,
) -> tuple[str, bool]:
    add_proc = run(["git", "-C", repo, "add", "--", *paths], cwd=repo, check=False)
    if add_proc.returncode != 0:
        raise SystemExit(output_text(add_proc) or "failed to stage paths")

    scan_proc = run(["bash", sensitive_scan, "--repo", repo, "--staged", "--redact"], cwd=repo, check=False)
    if scan_proc.returncode != 0:
        raise SystemExit(output_text(scan_proc) or "sensitive scan failed")

    with tempfile.TemporaryDirectory() as temp_dir:
        msg_file = Path(temp_dir) / "commit.txt"
        msg_file.write_text(message, encoding="utf-8")
        cmd = ["git", "-C", repo]
        if signing_off:
            cmd.extend(["-c", "commit.gpgsign=false"])
        cmd.extend(["commit", "--only", "-F", str(msg_file), "--", *paths])
        commit_proc = run(cmd, cwd=repo, check=False)
        if commit_proc.returncode != 0:
            commit_output = output_text(commit_proc) or "git commit failed"
            if classify_commit_failure(commit_output) == "commit-signing-unavailable" and allow_unsigned_retry:
                retry_cmd = ["git", "-C", repo, "-c", "commit.gpgsign=false", "commit", "--only", "-F", str(msg_file), "--", *paths]
                retry_proc = run(retry_cmd, cwd=repo, check=False)
                if retry_proc.returncode == 0:
                    sha_proc = run(["git", "-C", repo, "rev-parse", "--short=8", "HEAD"], cwd=repo, check=False)
                    if sha_proc.returncode != 0:
                        raise SystemExit(output_text(sha_proc) or "failed to resolve commit sha")
                    return ((sha_proc.stdout or "").strip(), True)
                raise BatchCommitFailure(
                    commit_failure_payload(
                        commit_index=commit_index,
                        repo=repo,
                        paths=paths,
                        output=output_text(retry_proc) or commit_output,
                        allow_unsigned_retry=allow_unsigned_retry,
                        unsigned_retry_attempted=True,
                    )
                )
            raise BatchCommitFailure(
                commit_failure_payload(
                    commit_index=commit_index,
                    repo=repo,
                    paths=paths,
                    output=commit_output,
                    allow_unsigned_retry=allow_unsigned_retry,
                    unsigned_retry_attempted=False,
                )
            )

    sha_proc = run(["git", "-C", repo, "rev-parse", "--short=8", "HEAD"], cwd=repo, check=False)
    if sha_proc.returncode != 0:
        raise SystemExit(output_text(sha_proc) or "failed to resolve commit sha")
    return ((sha_proc.stdout or "").strip(), False)


def normalize_repo_path(path: str, cwd: str) -> str:
    return str((Path(cwd) / path).resolve()) if not Path(path).is_absolute() else str(Path(path).resolve())


def validate_commit_spec(spec: dict[str, object]) -> None:
    if not isinstance(spec, dict):
        raise SystemExit("each commit entry must be an object")
    commit_type = str(spec.get("type", "")).strip()
    if not HEADER_RE.match(commit_type):
        raise SystemExit(f"invalid commit type '{commit_type}'")
    scope = str(spec.get("scope", "")).strip()
    if scope and not HEADER_RE.match(scope):
        raise SystemExit(f"invalid commit scope '{scope}'")
    subject = str(spec.get("subject", "")).strip()
    if not subject:
        raise SystemExit("commit subject must not be empty")
    if subject.endswith("."):
        raise SystemExit("commit subject must not end with a period")
    if subject != subject.lower():
        raise SystemExit("commit subject must be lowercase")
    bullets = spec.get("bullets", [])
    if not isinstance(bullets, list) or not bullets or not all(str(item).strip() for item in bullets):
        raise SystemExit("each commit must include at least one non-empty bullet")
    footers = spec.get("footers", [])
    if not isinstance(footers, list) or not all(str(item).strip() for item in footers):
        raise SystemExit("commit footers must be a list of non-empty strings")
    paths = spec.get("paths", [])
    if not isinstance(paths, list) or not paths or not all(str(item).strip() for item in paths):
        raise SystemExit("each commit must include at least one non-empty path")


def plan_command(args: argparse.Namespace) -> int:
    repo = repo_root(args.repo)
    entries = [inventory_entry(repo, entry_repo, args.mode) for _, entry_repo in related_repos(repo, args.scope)]
    payload = {
        "status": "no-changes" if all(item["changed_path_count"] == 0 for item in entries) else "planned",
        "mode": args.mode,
        "scope": args.scope,
        "root_repo": outermost_superproject_path(repo),
        "requested_repo": repo,
        "related_repos_detected": len(entries) > 1,
        "order_hint": "children first for commit/push; parent gitlinks last",
        "repos": entries,
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        if payload["status"] == "no-changes":
            print("No changes to plan.")
        else:
            for item in payload["repos"]:
                if item["changed_path_count"]:
                    print(f"{item['repo']}: {item['changed_path_count']} changed path(s)")
    return 0


def apply_command(args: argparse.Namespace) -> int:
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    commits = plan.get("commits", [])
    deferred = plan.get("deferred", [])
    if not isinstance(commits, list):
        raise SystemExit("plan file must contain a 'commits' list")
    if not isinstance(deferred, list):
        raise SystemExit("plan file 'deferred' field must be a list when present")

    script_dir = Path(__file__).resolve().parent
    message_script = str(script_dir / "commit-message.py")
    sensitive_scan = str(script_dir / "sensitive-scan.sh")
    cwd = os.getcwd()

    normalized_commits: list[dict[str, object]] = []
    assigned_paths: dict[str, set[str]] = defaultdict(set)
    deferred_paths: dict[str, set[str]] = defaultdict(set)
    repos_seen: set[str] = set()

    for item in deferred:
        if not isinstance(item, dict):
            raise SystemExit("each deferred entry must be an object")
        repo = normalize_repo_path(str(item.get("repo", "")), cwd)
        paths = item.get("paths", [])
        if not isinstance(paths, list):
            raise SystemExit("deferred paths must be a list")
        deferred_paths[repo].update(str(path).strip() for path in paths if str(path).strip())

    for index, spec in enumerate(commits, start=1):
        validate_commit_spec(spec)
        repo = normalize_repo_path(str(spec.get("repo", ".")), cwd)
        repos_seen.add(repo)
        paths = [str(path).strip() for path in spec["paths"]]
        if args.mode == "raw":
            safe_to_commit, note = repo_commit_safety(repo, "raw")
            if not safe_to_commit:
                payload = {
                    "status": "blocked",
                    "failure_class": "raw-commit-unsafe",
                    "commit_index": index,
                    "repo": repo,
                    "paths": paths,
                    "error": note,
                    "commits": [],
                }
                if args.json:
                    print(json.dumps(payload, indent=2))
                else:
                    print(note)
                return 1
        overlap = assigned_paths[repo].intersection(paths)
        if overlap:
            raise SystemExit(f"duplicate path assignment in repo {repo}: {', '.join(sorted(overlap))}")
        assigned_paths[repo].update(paths)
        normalized_commits.append(
            {
                "repo": repo,
                "type": str(spec["type"]).strip(),
                "scope": str(spec.get("scope", "")).strip() or None,
                "subject": str(spec["subject"]).strip(),
                "bullets": [str(item).strip() for item in spec["bullets"]],
                "footers": [str(item).strip() for item in spec.get("footers", [])],
                "paths": paths,
            }
        )

    repos_to_validate = set(repos_seen) | set(deferred_paths)
    for repo in repos_to_validate:
        actual = set(changed_paths(repo))
        assigned = assigned_paths.get(repo, set())
        deferred_repo = deferred_paths.get(repo, set())
        unknown = (assigned | deferred_repo) - actual
        if unknown:
            raise SystemExit(f"plan references paths that are not currently changed in {repo}: {', '.join(sorted(unknown))}")
        unassigned = actual - assigned - deferred_repo
        if unassigned:
            raise SystemExit(f"plan leaves changed paths unassigned in {repo}: {', '.join(sorted(unassigned))}")

    allow_unsigned_retry = args.allow_unsigned_commit_retry or env_flag("GITOPS_ALLOW_UNSIGNED_COMMIT_RETRY")
    signing_off = False
    unsigned_retry_used = False
    created: list[dict[str, object]] = []

    for index, spec in enumerate(normalized_commits, start=1):
        message = render_commit_message(
            message_script,
            commit_type=str(spec["type"]),
            scope=spec["scope"],
            subject=str(spec["subject"]),
            bullets=list(spec["bullets"]),
            footers=list(spec["footers"]),
            cwd=str(spec["repo"]),
        )
        try:
            sha, used_unsigned_retry = stage_and_commit(
                str(spec["repo"]),
                list(spec["paths"]),
                message,
                sensitive_scan,
                signing_off,
                allow_unsigned_retry,
                index,
            )
        except BatchCommitFailure as exc:
            payload = {
                "status": exc.payload["status"],
                "signing_disabled": signing_off,
                "unsigned_retry_enabled": allow_unsigned_retry,
                "unsigned_retry_used": unsigned_retry_used,
                "commits": created,
                **exc.payload,
            }
            if args.json:
                print(json.dumps(payload, indent=2))
            else:
                print(payload.get("helper_text") or payload.get("error") or "batch commit failed")
            return 1
        if used_unsigned_retry:
            signing_off = True
            unsigned_retry_used = True
        created.append(
            {
                "index": index,
                "repo": spec["repo"],
                "sha": sha,
                "subject": message.splitlines()[0],
                "paths": spec["paths"],
            }
        )

    payload = {
        "status": "committed",
        "mode": args.mode,
        "signing_disabled": signing_off,
        "unsigned_retry_enabled": allow_unsigned_retry,
        "unsigned_retry_used": unsigned_retry_used,
        "commits": created,
        "deferred": [{"repo": repo, "paths": sorted(paths)} for repo, paths in sorted(deferred_paths.items()) if paths],
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        for item in created:
            print(f"{item['sha']} {item['subject']}")
    return 0


def fallback_command(args: argparse.Namespace) -> int:
    script_dir = Path(__file__).resolve().parent
    message_script = str(script_dir / "commit-message.py")
    sensitive_scan = str(script_dir / "sensitive-scan.sh")
    allow_unsigned_retry = args.allow_unsigned_commit_retry or env_flag("GITOPS_ALLOW_UNSIGNED_COMMIT_RETRY")
    signing_off = False
    unsigned_retry_used = False
    commits: list[dict[str, object]] = []

    for _, repo in related_repos(args.repo, args.scope):
        safe_to_commit, note = repo_commit_safety(repo, args.mode)
        paths = changed_paths(repo)
        if not paths:
            continue
        if not safe_to_commit:
            payload = {
                "status": "blocked",
                "mode": args.mode,
                "scope": args.scope,
                "repo": repo,
                "failure_class": "fallback-commit-unsafe",
                "error": note,
                "commits": commits,
            }
            if args.json:
                print(json.dumps(payload, indent=2))
            else:
                print(note)
            return 1
        buckets: dict[str, list[str]] = defaultdict(list)
        for path in paths:
            buckets[bucket_for_path(repo, path)].append(path)
        for bucket in BUCKET_ORDER:
            bucket_paths = sorted(set(buckets.get(bucket, [])))
            if not bucket_paths:
                continue
            spec = BUCKET_SPECS[bucket]
            message = render_commit_message(
                message_script,
                commit_type=spec.commit_type,
                scope=spec.scope,
                subject=spec.subject,
                bullets=[*spec.bullets, f"touch the following surfaces: {path_summary(bucket_paths)}"],
                footers=[],
                cwd=repo,
            )
            try:
                sha, used_unsigned_retry = stage_and_commit(
                    repo,
                    bucket_paths,
                    message,
                    sensitive_scan,
                    signing_off,
                    allow_unsigned_retry,
                    len(commits) + 1,
                )
            except BatchCommitFailure as exc:
                payload = {
                    "status": exc.payload["status"],
                    "mode": args.mode,
                    "scope": args.scope,
                    "signing_disabled": signing_off,
                    "unsigned_retry_enabled": allow_unsigned_retry,
                    "unsigned_retry_used": unsigned_retry_used,
                    "commits": commits,
                    **exc.payload,
                }
                if args.json:
                    print(json.dumps(payload, indent=2))
                else:
                    print(payload.get("helper_text") or payload.get("error") or "batch commit failed")
                return 1
            if used_unsigned_retry:
                signing_off = True
                unsigned_retry_used = True
            commits.append(
                {
                    "repo": repo,
                    "bucket": bucket,
                    "sha": sha,
                    "subject": message.splitlines()[0],
                    "paths": bucket_paths,
                }
            )

    payload = {
        "status": "no-changes" if not commits else "committed",
        "mode": args.mode,
        "scope": args.scope,
        "signing_disabled": signing_off,
        "unsigned_retry_enabled": allow_unsigned_retry,
        "unsigned_retry_used": unsigned_retry_used,
        "commits": commits,
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        if not commits:
            print("No changes to commit.")
        else:
            for item in commits:
                print(f"{item['sha']} {item['subject']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plan, apply, or fallback Conventional Commit batching for gitops-workflow."
    )
    subparsers = parser.add_subparsers(dest="command")

    plan_parser = subparsers.add_parser("plan", help="Emit repo/path inventory for agent-authored commit planning.")
    plan_parser.add_argument("--repo", default=".", help="Repository path (default: current directory).")
    plan_parser.add_argument("--scope", choices=("current", "tree"), default="current")
    plan_parser.add_argument("--mode", choices=("normal", "raw"), default="normal")
    plan_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    plan_parser.set_defaults(handler=plan_command)

    apply_parser = subparsers.add_parser("apply", help="Apply an agent-authored batch commit plan.")
    apply_parser.add_argument("--plan", required=True, help="Path to JSON plan file.")
    apply_parser.add_argument("--mode", choices=("normal", "raw"), default="normal")
    apply_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    apply_parser.add_argument(
        "--allow-unsigned-commit-retry",
        action="store_true",
        help="Allow one unsigned retry when commit signing is unavailable.",
    )
    apply_parser.set_defaults(handler=apply_command)

    fallback_parser = subparsers.add_parser("fallback", help="Use the maintained deterministic fallback commit splitter.")
    fallback_parser.add_argument("--repo", default=".", help="Repository path (default: current directory).")
    fallback_parser.add_argument("--scope", choices=("current", "tree"), default="current")
    fallback_parser.add_argument("--mode", choices=("normal", "raw"), default="normal")
    fallback_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    fallback_parser.add_argument(
        "--allow-unsigned-commit-retry",
        action="store_true",
        help="Allow one unsigned retry when commit signing is unavailable.",
    )
    fallback_parser.set_defaults(handler=fallback_command)

    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or os.sys.argv[1:])
    if not argv or argv[0] not in {"plan", "apply", "fallback", "-h", "--help"}:
        argv = ["plan", *argv]
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        raise SystemExit("missing subcommand (expected: plan, apply, or fallback)")
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
