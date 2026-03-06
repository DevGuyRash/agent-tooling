#!/usr/bin/env python3
"""generate-release-notes.py - Generate a release notes skeleton from git history.

This script is intentionally conservative: it generates a structured *draft* that you can edit.
Optional sections are omitted when empty.

Usage:
  python3 scripts/generate-release-notes.py --version v1.2.3
  python3 scripts/generate-release-notes.py --since v1.2.2 --version v1.2.3
  python3 scripts/generate-release-notes.py --include-commits

Notes:
- Parses Conventional Commits subjects from `git log`.
- Maps commit types to sections:
  - feat -> New Features
  - fix/hotfix -> Bug Fixes
  - everything else -> What's Changed
- Detects breaking changes via `!` in header or "BREAKING CHANGE" in body.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

LIB_DIR = Path(__file__).resolve().parent / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

from bootstrap import maybe_reexec_repo_local_copy


maybe_reexec_repo_local_copy(Path(__file__).resolve(), sys.argv)


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
    return out.decode("utf-8", errors="replace")


def try_run(cmd: List[str]) -> Optional[str]:
    try:
        return run(cmd).strip()
    except Exception:
        return None


@dataclass(frozen=True)
class Commit:
    sha: str
    subject: str
    body: str


def get_last_tag() -> Optional[str]:
    # Last annotated/lightweight tag reachable from HEAD
    tag = try_run(["git", "describe", "--tags", "--abbrev=0"])
    return tag or None


def iter_commits(range_expr: Optional[str]) -> List[Commit]:
    # Record format: sha<US>subject<US>body<RS>
    us = "\x1f"
    rs = "\x1e"
    fmt = f"%H{us}%s{us}%B{rs}"
    cmd = ["git", "log", "--no-merges", f"--pretty=format:{fmt}"]
    if range_expr:
        cmd.append(range_expr)
    raw = run(cmd)
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
    # Oldest-first reads better in notes
    commits.reverse()
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
    parser.add_argument("--since", default=None, help="Tag/SHA to start from (exclusive). Default: last tag.")
    parser.add_argument("--version", default=None, help="Version string for header (e.g., v1.2.3).")
    parser.add_argument(
        "--include-commits",
        action="store_true",
        help="Include commit bullets in ## Commits (section is always emitted).",
    )
    args = parser.parse_args()

    inside = try_run(["git", "rev-parse", "--is-inside-work-tree"])
    if inside != "true":
        sys.stderr.write("Error: not inside a git repository\n")
        return 2

    since = args.since or get_last_tag()
    range_expr = f"{since}..HEAD" if since else None

    commits = iter_commits(range_expr)

    new_features: List[str] = []
    bug_fixes: List[str] = []
    whats_changed: List[str] = []
    breaking: List[str] = []
    commit_lines: List[str] = []

    for c in commits:
        parsed = parse_conventional(c.subject)
        if not parsed:
            # Non-conventional commit: treat as What's Changed
            whats_changed.append(f"- {c.subject}")
            if args.include_commits:
                commit_lines.append(f"- `{c.sha[:7]}` {c.subject}")
            continue

        typ, scope, is_breaking_header, desc = parsed
        has_breaking_footer = "BREAKING CHANGE" in c.body
        is_breaking = is_breaking_header or has_breaking_footer

        scope_prefix = f"{scope}: " if scope else ""
        bullet = f"- {scope_prefix}{desc}"

        if typ == "feat":
            new_features.append(bullet)
        elif typ in {"fix", "hotfix"}:
            bug_fixes.append(bullet)
        else:
            whats_changed.append(bullet)

        if is_breaking:
            breaking.append(f"- {scope_prefix}{desc}; migration: <add steps>")

        if args.include_commits:
            commit_lines.append(f"- `{c.sha[:7]}` {c.subject}")

    version = args.version or "<version>"
    header = f"chore(release): publish {version}"

    print(header)
    print("")
    print("## Overview")
    print("")
    print("Summarize the context, intent, and impact of this release in 2–4 lines.")
    print("Keep it prose (no refs here). Focus on what changed for users and why.")
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
    if breaking:
        print("## Breaking Changes")
        print("")
        print("\n".join(breaking))
        print("")
    print("## Commits")
    print("")
    if commit_lines:
        print("\n".join(commit_lines))
    else:
        print("- (none)")
    print("")
    print("## Refs")
    print("")
    refs: List[str] = []
    if since:
        refs.append(since)
    if refs:
        for ref in refs:
            print(f"- {ref}")
    else:
        print("- (none provided)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
