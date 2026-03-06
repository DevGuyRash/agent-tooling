#!/usr/bin/env python3
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Optional


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

CC_HEADER_RE = re.compile(
    r"^(?P<type>[a-z]+)"
    r"(?:\((?P<scope>[^)]+)\))?"
    r"(?P<breaking>!)?:\s"
    r"(?P<desc>.+)$"
)
CC_TITLE_RE = re.compile(r"^(?P<prefix>[a-z]+(?:\([^)]+\))?(?:!)?:\s)(?P<desc>.+)$")


@dataclass(frozen=True)
class CommitEntry:
    sha: str
    headline: str
    body: str = ""


@dataclass(frozen=True)
class RenderedSquashMessage:
    subject: str
    body: str


def build_subject(title: str, summary_override: str = "") -> str:
    clean_title = (title or "").strip()
    match = CC_TITLE_RE.match(clean_title)
    if not match:
        raise ValueError("PR title must follow Conventional Commits format for squash subject")
    override = (summary_override or "").strip()
    if not override:
        return clean_title
    return f"{match.group('prefix')}{override}"


def _append_unique(target: List[str], seen: set[str], bullet: str) -> None:
    if bullet in seen:
        return
    seen.add(bullet)
    target.append(bullet)


def _append_section(lines: List[str], title: str, bullets: List[str], *, always: bool = False, empty_bullet: str = "- (none)") -> None:
    if not bullets and not always:
        return
    lines.extend([f"## {title}", ""])
    if bullets:
        lines.extend(bullets)
    else:
        lines.append(empty_bullet)
    lines.append("")


def _iter_commit_entries(commits: Iterable[CommitEntry]) -> Iterable[CommitEntry]:
    for commit in commits:
        headline = (commit.headline or "").strip()
        body = commit.body or ""
        sha = commit.sha or ""
        yield CommitEntry(sha=sha, headline=headline, body=body)


def render_squash_message(*, title: str, commits: Iterable[CommitEntry], pr_ref: Optional[str] = None, refs: Optional[Iterable[str]] = None, summary_override: str = "") -> RenderedSquashMessage:
    subject = build_subject(title, summary_override=summary_override)

    features: List[str] = []
    fixes: List[str] = []
    changes: List[str] = []
    breaking: List[str] = []
    commit_lines: List[str] = []
    feature_seen: set[str] = set()
    fix_seen: set[str] = set()
    change_seen: set[str] = set()
    breaking_seen: set[str] = set()

    for commit in _iter_commit_entries(commits):
        short_sha = commit.sha[:7] if commit.sha else "unknown"
        if commit.headline:
            commit_lines.append(f"- `{short_sha}` {commit.headline}")
        else:
            commit_lines.append(f"- `{short_sha}` <no headline>")

        match = CC_HEADER_RE.match(commit.headline)
        if not match:
            if commit.headline:
                _append_unique(changes, change_seen, f"- {commit.headline}")
            continue

        typ = match.group("type")
        scope = match.group("scope")
        desc = match.group("desc")
        is_breaking = bool(match.group("breaking")) or ("BREAKING CHANGE" in commit.body)
        scope_prefix = f"{scope}: " if scope else ""
        bullet = f"- {scope_prefix}{desc}"

        if typ == "feat":
            _append_unique(features, feature_seen, bullet)
        elif typ in {"fix", "hotfix"}:
            _append_unique(fixes, fix_seen, bullet)
        else:
            _append_unique(changes, change_seen, bullet)

        if is_breaking:
            _append_unique(breaking, breaking_seen, f"- {scope_prefix}{desc}; migration: <add steps>")

    ref_lines = []
    for ref in refs or []:
        clean_ref = (ref or "").strip()
        if clean_ref:
            ref_lines.append(f"- {clean_ref}")

    lines = [
        "## Overview",
        "",
        f"Squash merge for {pr_ref}." if pr_ref else "Squash merge summary.",
        "",
    ]
    _append_section(lines, "New Features", features)
    _append_section(lines, "What's Changed", changes)
    _append_section(lines, "Bug Fixes", fixes)
    _append_section(lines, "Breaking Changes", breaking)
    _append_section(lines, "Commits", commit_lines, always=True, empty_bullet="- (none reported by API)")
    _append_section(lines, "Refs", ref_lines, always=True, empty_bullet="- (none provided)")
    if lines[-1] == "":
        lines.pop()

    return RenderedSquashMessage(subject=subject, body="\n".join(lines) + "\n")
