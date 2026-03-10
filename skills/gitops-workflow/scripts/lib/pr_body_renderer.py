#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


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


def read_lines(path: str) -> list[str]:
    return Path(path).read_text(encoding="utf-8").splitlines()


def categorize_commits(commit_lines: list[str]) -> tuple[list[str], list[str], list[str], bool]:
    features: list[str] = []
    fixes: list[str] = []
    changes: list[str] = []
    breaking = False

    for line in commit_lines:
        subject = line.strip()
        if not subject:
            continue
        match = CC_HEADER_RE.match(subject)
        if not match or match.group("type") not in ALLOWED_TYPES:
            changes.append(subject)
            continue

        typ = match.group("type")
        scope = match.group("scope")
        desc = match.group("desc")
        bullet = f"{scope}: {desc}" if scope else desc

        if typ == "feat":
            features.append(bullet)
        elif typ in {"fix", "hotfix"}:
            fixes.append(bullet)
        else:
            changes.append(bullet)

        if match.group("breaking"):
            breaking = True

    return features, fixes, changes, breaking


def summarize_areas(changed_files: list[str]) -> list[str]:
    buckets: list[str] = []
    if any(path.startswith("skills/") for path in changed_files):
        buckets.append("skill behavior")
    if any("/scripts/" in path or path.startswith("scripts/") for path in changed_files):
        buckets.append("automation scripts")
    if any("/tests/" in path or path.startswith("tests/") for path in changed_files):
        buckets.append("test coverage")
    if any(path.endswith(".md") for path in changed_files):
        buckets.append("documentation")
    if not buckets:
        buckets.append("repository files")
    return buckets[:3]


def build_overview(*, head: str, base: str, title: str, changed_files: list[str], features: list[str], fixes: list[str], changes: list[str]) -> str:
    areas = ", ".join(summarize_areas(changed_files))
    impact_bits: list[str] = []
    if features:
        impact_bits.append(f"{len(features)} feature-oriented change(s)")
    if fixes:
        impact_bits.append(f"{len(fixes)} fix(es)")
    if changes:
        impact_bits.append(f"{len(changes)} supporting update(s)")
    if not impact_bits:
        impact_bits.append("targeted branch updates")
    impact = ", ".join(impact_bits)
    return (
        f"This PR brings `{head}` into `{base}` for `{title}`. "
        f"It primarily touches {areas} and packages {impact} for review."
    )


def build_key_changes(features: list[str], fixes: list[str], changes: list[str]) -> list[str]:
    bullets: list[str] = []
    for value in features[:3]:
        bullets.append(f"- Feature: {value}")
    for value in fixes[:3]:
        bullets.append(f"- Fix: {value}")
    for value in changes[:4]:
        bullets.append(f"- Change: {value}")
    return bullets or ["- Review the branch diff; no categorized commit summaries were available."]


def build_review_guide(changed_files: list[str]) -> list[str]:
    guide: list[str] = []
    if any("/scripts/" in path or path.startswith("scripts/") for path in changed_files):
        guide.append("- Validate CLI flow changes, especially template selection and body rendering behavior.")
    if any("/tests/" in path or path.startswith("tests/") for path in changed_files):
        guide.append("- Confirm automated coverage matches the new create/discovery behavior and edge cases.")
    if any(path.endswith(".md") for path in changed_files):
        guide.append("- Check docs and templates for wording drift against the implemented behavior.")
    return guide or ["- Focus review on the changed files and generated PR body output."]


def build_verification(base: str, head: str, changed_files: list[str]) -> list[str]:
    commands: list[str] = []
    if any(path.endswith(".py") for path in changed_files):
        commands.append("python3 -m unittest skills/gitops-workflow/tests/test_pr_template_discover.py skills/gitops-workflow/tests/test_pr_create.py")
    if any(path.endswith(".sh") for path in changed_files):
        commands.append("bash -n skills/gitops-workflow/scripts/*.sh")
    commands.append(f'git diff --stat "{base}...{head}"')
    return commands


def build_refs(commit_lines: list[str]) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for subject in commit_lines:
        for ref in re.findall(r"#[0-9]+", subject):
            bullet = f"- Related to {ref}"
            if bullet not in seen:
                seen.add(bullet)
                refs.append(bullet)
    return refs or ["- (none provided)"]


def build_area_bullets(changed_files: list[str]) -> list[str]:
    areas = summarize_areas(changed_files)
    return [f"- {area}" for area in areas] or ["- repository files"]


def build_summary(*, title: str, base: str, head: str, changed_files: list[str], features: list[str], fixes: list[str], changes: list[str]) -> str:
    return build_overview(
        head=head,
        base=base,
        title=title,
        changed_files=changed_files,
        features=features,
        fixes=fixes,
        changes=changes,
    )


def build_changes(features: list[str], fixes: list[str], changes: list[str], changed_files: list[str]) -> str:
    lines = ["### Affected Areas", "", *build_area_bullets(changed_files), ""]
    if features:
        lines.extend(["### Features", "", *[f"- {value}" for value in features], ""])
    if fixes:
        lines.extend(["### Fixes", "", *[f"- {value}" for value in fixes], ""])
    if changes:
        lines.extend(["### Other Changes", "", *[f"- {value}" for value in changes], ""])
    if not any((features, fixes, changes)):
        lines.extend(["- Review the branch diff; no categorized commit summaries were available.", ""])
    return "\n".join(lines).rstrip()


def build_risk_lines(breaking: bool) -> str:
    lines = [
        f"- Breaking changes? **{'Yes' if breaking else 'No'}**",
        "- Rollout / monitoring:",
        "- Rollback plan: revert the PR merge commit if follow-up fixes are not sufficient.",
    ]
    return "\n".join(lines)


def render_fallback_template(template_text: str, *, summary: str, changes: str, test_commands: str, risk_lines: str, refs_lines: list[str]) -> str:
    refs_text = "\n".join(refs_lines)
    rendered = template_text.replace("<!-- SUMMARY_PLACEHOLDER -->", summary)
    rendered = rendered.replace("<!-- CHANGES_PLACEHOLDER -->", changes)
    rendered = rendered.replace("<!-- TEST_COMMANDS_PLACEHOLDER -->", test_commands)
    rendered = rendered.replace("<!-- RISK_PLACEHOLDER -->", risk_lines)
    rendered = rendered.replace("<!-- REFS_PLACEHOLDER -->", refs_text)
    return rendered.rstrip() + "\n"


def has_fallback_placeholders(template_text: str) -> bool:
    return any(
        marker in template_text
        for marker in (
            "<!-- SUMMARY_PLACEHOLDER -->",
            "<!-- CHANGES_PLACEHOLDER -->",
            "<!-- TEST_COMMANDS_PLACEHOLDER -->",
            "<!-- RISK_PLACEHOLDER -->",
            "<!-- REFS_PLACEHOLDER -->",
        )
    )


def render_review_focus(review_lines: list[str]) -> str:
    return "\n".join(review_lines)


TRAILING_TRIGGER_LINE_RE = re.compile(r"^\s*(?:@|/)\S")


def split_trailing_trigger_block(template_text: str) -> tuple[str, str]:
    lines = template_text.rstrip().splitlines()
    if not lines:
        return "", ""

    end = len(lines)
    while end > 0 and not lines[end - 1].strip():
        end -= 1

    start = end
    while start > 0 and TRAILING_TRIGGER_LINE_RE.match(lines[start - 1]):
        start -= 1

    if start == end:
        return "\n".join(lines[:end]), ""

    prefix = "\n".join(lines[:start]).rstrip()
    suffix = "\n".join(lines[start:end]).rstrip()
    return prefix, suffix


def render_augmented_template(
    template_text: str,
    *,
    summary: str,
    changes: str,
    review_lines: list[str],
    test_commands: str,
    risk_lines: str,
    refs_lines: list[str],
) -> str:
    if has_fallback_placeholders(template_text):
        return render_fallback_template(
            template_text,
            summary=summary,
            changes=changes,
            test_commands=test_commands,
            risk_lines=risk_lines,
            refs_lines=refs_lines,
        )

    template_prefix, trailing_triggers = split_trailing_trigger_block(template_text)
    sections = [
        template_prefix,
        "",
        "---",
        "",
        "## Generated Review Context",
        "",
        "### Summary",
        "",
        summary,
        "",
        "### Changes",
        "",
        changes,
        "",
        "### Review Focus",
        "",
        render_review_focus(review_lines),
        "",
        "### Testing",
        "",
        "```bash",
        test_commands,
        "```",
        "",
        "### Risks / rollout",
        "",
        risk_lines,
        "",
        "### Refs",
        "",
        "\n".join(refs_lines),
    ]
    if trailing_triggers:
        sections.extend(["", trailing_triggers])
    return "\n".join(sections).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices={"augment", "fallback"}, required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--commits-file", required=True)
    parser.add_argument("--changes-file", required=True)
    parser.add_argument("--template-file", required=True)
    args = parser.parse_args()

    commit_lines = read_lines(args.commits_file)
    changed_files = [line.strip() for line in read_lines(args.changes_file) if line.strip()]
    template_text = Path(args.template_file).read_text(encoding="utf-8")
    features, fixes, changes, breaking = categorize_commits(commit_lines)

    refs_lines = build_refs(commit_lines)
    summary = build_summary(
        title=args.title,
        base=args.base,
        head=args.head,
        changed_files=changed_files,
        features=features,
        fixes=fixes,
        changes=changes,
    )
    review_lines = build_review_guide(changed_files)
    test_commands = "\n".join(build_verification(args.base, args.head, changed_files))
    risk_lines = build_risk_lines(breaking)
    changes_text = build_changes(features, fixes, changes, changed_files)
    if args.mode == "augment":
        print(
            render_augmented_template(
                template_text,
                summary=summary,
                changes=changes_text,
                review_lines=review_lines,
                test_commands=test_commands,
                risk_lines=risk_lines,
                refs_lines=refs_lines,
            ),
            end="",
        )
        return 0

    print(
        render_fallback_template(
            template_text,
            summary=summary,
            changes=changes_text,
            test_commands=test_commands,
            risk_lines=risk_lines,
            refs_lines=refs_lines,
        ),
        end="",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
