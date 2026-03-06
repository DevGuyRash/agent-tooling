#!/usr/bin/env python3
"""generate-squash-message.py - Generate a structured squash-merge commit message body.

This follows the sectioned format used by this skill
(Overview → New Features → What's Changed → Bug Fixes → Breaking Changes → Commits → Refs).
Optional sections are omitted when empty; Commits and Refs are always emitted.

Usage:
  python3 scripts/generate-squash-message.py --summary "add --json output" --pr 123
  python3 scripts/generate-squash-message.py --type feat --scope cli --summary "add --json output" --refs "#123"

Defaults:
- type is inferred from branch name prefix (e.g. feat/..., fix/...) when possible.
- base is inferred from origin/HEAD when possible.

Notes:
- This is a draft generator. Edit Overview + Refs before using for an actual squash merge.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import List, Optional, Tuple


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
    out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
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
    body: str


def detect_base_ref() -> str:
    sym = try_run(["git", "symbolic-ref", "-q", "refs/remotes/origin/HEAD"])
    if sym:
        return sym.replace("refs/remotes/", "")
    return "origin/main"


def current_branch() -> str:
    return run(["git", "rev-parse", "--abbrev-ref", "HEAD"])


def infer_type_from_branch(branch: str) -> Optional[str]:
    # e.g. feat/add-thing -> feat
    prefix = branch.split("/", 1)[0].strip()
    if prefix in ALLOWED_TYPES:
        return prefix
    return None


def merge_base(base_ref: str) -> str:
    return run(["git", "merge-base", "HEAD", base_ref])


def iter_commits(range_expr: str) -> List[Commit]:
    us = "\x1f"
    rs = "\x1e"
    fmt = f"%H{us}%s{us}%B{rs}"
    raw = run(["git", "log", "--no-merges", f"--pretty=format:{fmt}", range_expr])
    commits: List[Commit] = []
    for record in raw.split(rs):
        record = record.strip()
        if not record:
            continue
        parts = record.split(us)
        if len(parts) < 3:
            continue
        sha, subject, body = parts[0].strip(), parts[1].strip(), parts[2].strip()
        commits.append(Commit(sha=sha, subject=subject, body=body))
    commits.reverse()  # oldest-first
    return commits


def parse_conventional(subject: str) -> Optional[Tuple[str, Optional[str], bool, str]]:
    m = CONVENTIONAL_RE.match(subject)
    if not m:
        return None
    typ = m.group("type")
    if typ not in ALLOWED_TYPES:
        return None
    scope = m.group("scope")
    breaking = bool(m.group("breaking"))
    desc = m.group("desc")
    return typ, scope, breaking, desc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", dest="typ", default=None, help="Commit type for squash header (feat/fix/...).")
    parser.add_argument("--scope", default=None, help="Optional scope for squash header.")
    parser.add_argument("--summary", required=True, help="Short imperative summary for squash header.")
    parser.add_argument("--base", default=None, help="Base ref to diff against (default: detect origin/HEAD).")
    parser.add_argument("--pr", default=None, help="PR number (for refs).")
    parser.add_argument("--refs", nargs="*", default=[], help="Additional refs (#123, owner/repo#123, URLs).")
    args = parser.parse_args()

    inside = try_run(["git", "rev-parse", "--is-inside-work-tree"])
    if inside != "true":
        sys.stderr.write("Error: not inside a git repository\n")
        return 2

    branch = current_branch()
    base_ref = args.base or detect_base_ref()
    base_commit = merge_base(base_ref)
    commits = iter_commits(f"{base_commit}..HEAD")

    typ = args.typ or infer_type_from_branch(branch) or "chore"
    if typ not in ALLOWED_TYPES:
        typ = "chore"

    scope = args.scope
    summary = args.summary.strip()

    new_features: List[str] = []
    bug_fixes: List[str] = []
    whats_changed: List[str] = []
    breaking_changes: List[str] = []
    commit_lines: List[str] = []

    any_breaking = False

    for c in commits:
        parsed = parse_conventional(c.subject)
        commit_lines.append(f"- `{c.sha[:7]}` {c.subject}")
        if not parsed:
            whats_changed.append(f"- {c.subject}")
            continue

        c_type, c_scope, c_breaking_header, desc = parsed
        has_breaking_footer = "BREAKING CHANGE" in c.body
        is_breaking = c_breaking_header or has_breaking_footer
        if is_breaking:
            any_breaking = True

        scope_prefix = f"{c_scope}: " if c_scope else ""
        bullet = f"- {scope_prefix}{desc}"

        if c_type == "feat":
            new_features.append(bullet)
        elif c_type in {"fix", "hotfix"}:
            bug_fixes.append(bullet)
        else:
            whats_changed.append(bullet)

        if is_breaking:
            breaking_changes.append(f"- {scope_prefix}{desc}; migration: <add steps>")

    header_scope = f"({scope})" if scope else ""
    bang = "!" if any_breaking else ""
    header = f"{typ}{header_scope}{bang}: {summary}"

    print(header)
    print("")
    print("## Overview")
    print("")
    print("Write 2–4 lines on context, intent, and impact. No refs here.")
    print("")
    if new_features:
        print("## New Features")
        print("")
        print("\n".join(new_features))
        print("")
    if whats_changed:
        print("## What's Changed")
        print("")
        print("\n".join(whats_changed))
        print("")
    if bug_fixes:
        print("## Bug Fixes")
        print("")
        print("\n".join(bug_fixes))
        print("")
    if any_breaking:
        print("## Breaking Changes")
        print("")
        if breaking_changes:
            print("\n".join(breaking_changes))
        else:
            print("- <describe breaking change>; migration: <steps>")
        print("")
    print("## Commits")
    print("")
    if commit_lines:
        print("\n".join(commit_lines))
    else:
        print("- (none)")
    print("")

    refs: List[str] = []
    if args.pr:
        refs.append(f"#{args.pr}")
    refs.extend(args.refs)

    print("## Refs")
    print("")
    if refs:
        for r in refs:
            print(f"- {r}")
    else:
        print("- (none provided)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
