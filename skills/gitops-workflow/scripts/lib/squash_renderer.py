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


class SquashRenderError(ValueError):
    """User-facing squash rendering error."""


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
        raise SquashRenderError("PR title must follow Conventional Commits format for squash subject")
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


_CLOSING_KEYWORD_RE = re.compile(
    r"(?:^|\s)(?P<keyword>(?:Fix(?:es)?|Close[sd]?|Resolve[sd]?))\s+(?P<ref>#\d+|[A-Za-z0-9._-]+/[A-Za-z0-9._-]+#\d+)",
    re.IGNORECASE,
)
_BARE_REF_RE = re.compile(r"(?:^|[\s(])(?P<ref>#\d+|[A-Za-z0-9._-]+/[A-Za-z0-9._-]+#\d+)")
_GITHUB_URL_RE = re.compile(
    r"https://github\.com/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+/(?:issues|pull)/(?P<num>\d+)"
)


def extract_refs_from_commits(commits: Iterable[CommitEntry]) -> List[str]:
    """Scan commit headlines and bodies for issue/PR references.

    Returns deduplicated ref lines preserving closing keywords when found.
    """
    seen: set[str] = set()
    refs: List[str] = []

    for commit in commits:
        for text in (commit.headline, commit.body):
            if not text:
                continue
            # Closing keywords first (Fixes #123, Closes owner/repo#456)
            for m in _CLOSING_KEYWORD_RE.finditer(text):
                keyword = m.group("keyword").capitalize()
                if keyword.endswith("d"):
                    keyword = keyword[:-1]
                if keyword.endswith("e"):
                    keyword = keyword + "s"
                elif not keyword.endswith("s"):
                    keyword = keyword + "es"
                ref = m.group("ref")
                bullet = f"- {keyword} {ref}"
                if bullet not in seen:
                    seen.add(bullet)
                    refs.append(bullet)
                seen.add(ref)
            # Bare refs (#123, owner/repo#123)
            for m in _BARE_REF_RE.finditer(text):
                ref = m.group("ref")
                if ref not in seen:
                    seen.add(ref)
                    refs.append(f"- {ref}")
            # GitHub URLs
            for m in _GITHUB_URL_RE.finditer(text):
                url = m.group(0)
                if url not in seen:
                    seen.add(url)
                    refs.append(f"- {url}")

    return refs


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


def render_squash_skeleton(
    *,
    title: str,
    commits: Iterable[CommitEntry],
    pr_ref: Optional[str] = None,
    refs: Optional[Iterable[str]] = None,
    summary_override: str = "",
) -> RenderedSquashMessage:
    """Generate a squash message skeleton with deterministic Commits/Refs and agent placeholders.

    Prose sections (Overview, New Features, What's Changed, Bug Fixes, Breaking Changes)
    contain placeholder markers for the agent to fill with natural language.
    Commits and Refs sections are filled deterministically.
    Placeholder sections are only included when relevant commits exist.
    """
    subject = build_subject(title, summary_override=summary_override)

    has_features = False
    has_fixes = False
    has_changes = False
    has_breaking = False
    commit_lines: List[str] = []
    all_commits: List[CommitEntry] = []

    for commit in _iter_commit_entries(commits):
        all_commits.append(commit)
        short_sha = commit.sha[:7] if commit.sha else "unknown"
        if commit.headline:
            commit_lines.append(f"- `{short_sha}` {commit.headline}")
        else:
            commit_lines.append(f"- `{short_sha}` <no headline>")

        match = CC_HEADER_RE.match(commit.headline)
        if not match:
            if commit.headline:
                has_changes = True
            continue

        typ = match.group("type")
        is_breaking = bool(match.group("breaking")) or ("BREAKING CHANGE" in commit.body)

        if typ == "feat":
            has_features = True
        elif typ in {"fix", "hotfix"}:
            has_fixes = True
        else:
            has_changes = True

        if is_breaking:
            has_breaking = True

    # Build refs: merge explicit refs with extracted refs from commits
    ref_lines: List[str] = []
    ref_seen: set[str] = set()
    for ref in refs or []:
        clean_ref = (ref or "").strip()
        if clean_ref and clean_ref not in ref_seen:
            ref_seen.add(clean_ref)
            ref_lines.append(f"- {clean_ref}")
    for extracted in extract_refs_from_commits(all_commits):
        if extracted not in ref_seen:
            ref_seen.add(extracted)
            ref_lines.append(extracted)

    pr_context = f" for {pr_ref}" if pr_ref else ""
    lines = [
        "## Overview",
        "",
        f"<!-- AGENT: Write 1-2 sentences summarizing what this PR{pr_context} achieves and why. -->",
        "",
    ]

    if has_features:
        lines.extend([
            "## New Features",
            "",
            "<!-- AGENT: Describe new features in natural prose bullets. Remove this section if not applicable. -->",
            "",
        ])

    if has_changes:
        lines.extend([
            "## What's Changed",
            "",
            "<!-- AGENT: Describe non-feature changes in natural prose bullets. Remove this section if not applicable. -->",
            "",
        ])

    if has_fixes:
        lines.extend([
            "## Bug Fixes",
            "",
            "<!-- AGENT: Describe bug fixes in natural prose bullets. Remove this section if not applicable. -->",
            "",
        ])

    if has_breaking:
        lines.extend([
            "## Breaking Changes",
            "",
            "<!-- AGENT: Describe breaking changes and migration steps. Remove this section if not applicable. -->",
            "",
        ])

    _append_section(lines, "Commits", commit_lines, always=True, empty_bullet="- (none reported by API)")
    _append_section(lines, "Refs", ref_lines, always=True, empty_bullet="- (none provided)")
    if lines[-1] == "":
        lines.pop()

    return RenderedSquashMessage(subject=subject, body="\n".join(lines) + "\n")
