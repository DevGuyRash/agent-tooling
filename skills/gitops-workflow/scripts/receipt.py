#!/usr/bin/env python3
"""receipt.py - Generate a GitOps "commit receipt" markdown block.

A receipt summarizes what was pushed/merged on a branch.

Usage:
  python3 scripts/receipt.py
  python3 scripts/receipt.py --branch feat/add-json-output --base origin/main --pr-url https://github.com/org/repo/pull/123

Notes:
- The default base ref is detected from origin/HEAD when available.
- The receipt lists commits on <branch> since the merge-base with <base>.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import List, Optional


ALLOWED_TYPES = {
    "feat",
    "fix",
    "docs",
    "refactor",
    "test",
    "chore",
    "perf",
    "ci",
    "build",
    "style",
    "deps",
    "security",
    "revert",
    "hotfix",
}

CONVENTIONAL_RE = re.compile(
    r"^(?P<type>[a-z]+)"
    r"(?:\((?P<scope>[^)]+)\))?"
    r"(?P<breaking>!)?:\s"
    r"(?P<desc>.+)$"
)


def run(cmd: List[str]) -> str:
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        sys.stderr.write(e.output.decode("utf-8", errors="replace"))
        raise
    return out.decode("utf-8", errors="replace").strip()


def try_run(cmd: List[str]) -> Optional[str]:
    try:
        return run(cmd)
    except Exception:
        return None


@dataclass(frozen=True)
class Commit:
    sha: str
    subject: str


def detect_default_base_ref() -> str:
    # Prefer origin/HEAD (e.g. refs/remotes/origin/main)
    sym = try_run(["git", "symbolic-ref", "-q", "refs/remotes/origin/HEAD"])
    if sym:
        base = sym.replace("refs/remotes/", "")
        return base  # origin/main
    return "origin/main"


def get_current_branch() -> str:
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    return branch


def get_merge_base(branch_ref: str, base_ref: str) -> str:
    return run(["git", "merge-base", branch_ref, base_ref])


def get_commits_since(base_commit: str, branch_ref: str, max_count: int) -> List[Commit]:
    # --reverse shows oldest-first which reads nicer in receipts
    fmt = "%h\t%s"
    raw = run(
        [
            "git",
            "log",
            "--reverse",
            f"--max-count={max_count}",
            f"--pretty=format:{fmt}",
            f"{base_commit}..{branch_ref}",
        ]
    )
    if not raw:
        return []
    commits: List[Commit] = []
    for line in raw.splitlines():
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        commits.append(Commit(sha=parts[0], subject=parts[1]))
    return commits


def format_commit_line(c: Commit) -> str:
    m = CONVENTIONAL_RE.match(c.subject)
    if not m:
        return f"  - `{c.sha}` _{c.subject}_"
    typ = m.group("type")
    scope = m.group("scope")
    desc = m.group("desc")
    if typ not in ALLOWED_TYPES:
        return f"  - `{c.sha}` _{c.subject}_"
    scope_part = f"({scope})" if scope else ""
    return f"  - `{c.sha}` {typ}{scope_part}: _{desc}_"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--branch", default=None, help="Branch name for the receipt (default: current branch).")
    parser.add_argument("--base", default=None, help="Base ref to diff against (default: detect origin/HEAD).")
    parser.add_argument("--max", type=int, default=50, help="Max commits to include (default: 50).")
    parser.add_argument("--pr-url", default=None, help="Optional PR URL to include in the receipt.")
    args = parser.parse_args()

    # Basic sanity
    inside = try_run(["git", "rev-parse", "--is-inside-work-tree"])
    if inside != "true":
        sys.stderr.write("Error: not inside a git repository\n")
        return 2

    branch = args.branch or get_current_branch()
    base_ref = args.base or detect_default_base_ref()

    # Ensure branch ref resolves to a commit (local or remote ref).
    branch_commit = try_run(["git", "rev-parse", "--verify", f"{branch}^{{commit}}"])
    if not branch_commit:
        sys.stderr.write(f"Error: branch ref does not resolve to a commit: {branch}\n")
        return 2

    base_commit = get_merge_base(branch, base_ref)
    commits = get_commits_since(base_commit, branch, args.max)

    print(f"- **branch `{branch}`**")
    if not commits:
        print("  - _no commits since base_")
    else:
        for c in commits:
            print(format_commit_line(c))

    if args.pr_url:
        print(f"  - PR: {args.pr_url}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
