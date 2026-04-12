#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
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


def changed_paths(repo: str) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    sources = [
        ["diff", "--cached", "--name-only", "-z", "--"],
        ["diff", "--name-only", "-z", "HEAD", "--"],
        ["ls-files", "--others", "--exclude-standard", "-z"],
    ]
    for args in sources:
        proc = run(["git", "-C", repo, *args], cwd=repo)
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
    if not line:
        return False
    return line.split()[0] == "160000"


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


def build_message(repo: str, bucket: str, paths: list[str], message_script: str) -> str:
    spec = BUCKET_SPECS[bucket]
    with tempfile.TemporaryDirectory() as temp_dir:
        out = Path(temp_dir) / "commit-message.txt"
        cmd = [
            "python3",
            message_script,
            "--type",
            spec.commit_type,
            "--subject",
            spec.subject,
        ]
        if spec.scope:
            cmd.extend(["--scope", spec.scope])
        for bullet in spec.bullets:
            cmd.extend(["--bullet", bullet])
        cmd.extend(["--bullet", f"touch the following surfaces: {path_summary(paths)}"])
        cmd.extend(["--out", str(out)])
        proc = run(cmd, cwd=repo, check=False)
        if proc.returncode != 0:
            raise SystemExit(output_text(proc) or "failed to generate commit message")
        return out.read_text(encoding="utf-8")


def signing_disabled(repo: str, signing_script: str) -> bool:
    if not Path(signing_script).exists():
        return False
    proc = run(["bash", signing_script], cwd=repo, check=False)
    return proc.returncode == 1


def stage_and_commit(repo: str, paths: list[str], message: str, sensitive_scan: str, signing_off: bool) -> str:
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
            raise SystemExit(output_text(commit_proc) or "git commit failed")

    sha_proc = run(["git", "-C", repo, "rev-parse", "--short=8", "HEAD"], cwd=repo, check=False)
    if sha_proc.returncode != 0:
        raise SystemExit(output_text(sha_proc) or "failed to resolve commit sha")
    return (sha_proc.stdout or "").strip()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Batch current repository changes into deterministic Conventional Commit groups."
    )
    parser.add_argument("--repo", default=".", help="Repository path (default: current directory).")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args()

    repo = str(Path(args.repo).resolve())
    if run(["git", "-C", repo, "rev-parse", "--is-inside-work-tree"], cwd=repo, check=False).returncode != 0:
        raise SystemExit(f"--repo is not a git repository: {repo}")

    script_dir = Path(__file__).resolve().parent
    message_script = str(script_dir / "commit-message.py")
    sensitive_scan = str(script_dir / "sensitive-scan.sh")
    signing_script = str(script_dir / "detect-signing.sh")

    paths = changed_paths(repo)
    if not paths:
        payload = {"status": "no-changes", "commits": []}
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print("No changes to commit.")
        return 0

    buckets: dict[str, list[str]] = defaultdict(list)
    for path in paths:
        buckets[bucket_for_path(repo, path)].append(path)

    signing_off = signing_disabled(repo, signing_script)
    commits = []
    for bucket in BUCKET_ORDER:
        bucket_paths = sorted(set(buckets.get(bucket, [])))
        if not bucket_paths:
            continue
        message = build_message(repo, bucket, bucket_paths, message_script)
        sha = stage_and_commit(repo, bucket_paths, message, sensitive_scan, signing_off)
        commits.append(
            {
                "bucket": bucket,
                "sha": sha,
                "subject": message.splitlines()[0],
                "paths": bucket_paths,
            }
        )

    payload = {"status": "committed", "signing_disabled": signing_off, "commits": commits}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        for item in commits:
            print(f"{item['sha']} {item['subject']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
