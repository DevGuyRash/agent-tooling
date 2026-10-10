#!/usr/bin/env python3
"""Fast smoke test for the GoalSpec V4 decision-funnel package."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "authoring-goals"
REFERENCES = SKILL / "references"

EXPECTED_SKILL_FILES = {
    "SKILL.md",
    "references/decision-funnel.md",
    "references/option-map.md",
    "references/probe-pack.md",
    "references/examples.md",
    "references/anti-patterns.md",
    "references/evaluation.md",
}

REMOVED_PATHS = [
    "hooks",
    "agents",
    "skills/authoring-goals/scripts",
    "skills/authoring-goals/assets",
    "skills/authoring-goals/agents",
    "skills/authoring-goals/templates",
    "tests/fixtures",
]

FORBIDDEN_PUBLIC_TERMS = [
    "goalmap",
    "goal map",
    "goal brief",
    "/goal",
    "context/goals",
    "contract compiler",
    "verifier gate",
    "auto-advance",
    "current/focus/rendered",
    ".goals/current.md",
]


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def rel_files(root: Path) -> set[str]:
    return {
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file()
    }


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def frontmatter(text: str) -> dict[str, str]:
    assert_true(text.startswith("---\n"), "SKILL.md starts with frontmatter")
    body = text.split("---\n", 2)[1]
    result: dict[str, str] = {}
    current_key = ""
    for line in body.splitlines():
        if not line.strip():
            continue
        if re.match(r"^[A-Za-z][A-Za-z0-9_-]*:", line):
            key, value = line.split(":", 1)
            current_key = key.strip()
            result[current_key] = value.strip()
        elif current_key:
            result[current_key] += " " + line.strip()
    return result


def assert_contains_all(text: str, needles: list[str], label: str) -> None:
    for needle in needles:
        assert_true(needle in text, f"{label} contains {needle!r}")


def assert_avoids(text: str, forbidden: list[str], label: str) -> None:
    lowered = text.lower()
    for term in forbidden:
        assert_true(term not in lowered, f"{label} avoids legacy term {term!r}")


def main() -> int:
    codex_manifest = json.loads(read(ROOT / ".codex-plugin" / "plugin.json"))
    claude_manifest = json.loads(read(ROOT / ".claude-plugin" / "plugin.json"))

    assert_true(codex_manifest["name"] == "goalspec", "Codex manifest name")
    assert_true(codex_manifest["version"] == "4.0.3", "Codex manifest version")
    assert_true(codex_manifest["skills"] == "./skills/", "Codex skills path")
    assert_true(claude_manifest["version"] == "4.0.3", "Claude manifest version")
    assert_true("hooks" not in codex_manifest, "Codex manifest does not wire hooks")

    manifest_text = json.dumps(codex_manifest).lower() + json.dumps(claude_manifest).lower()
    assert_contains_all(
        manifest_text,
        ["option maps", "probe packs", "context/docs", "after convergence"],
        "manifest",
    )
    assert_avoids(manifest_text, FORBIDDEN_PUBLIC_TERMS + ["hooks"], "manifest")

    for path in REMOVED_PATHS:
        assert_true(not (ROOT / path).exists(), f"removed path absent: {path}")

    skill_files = rel_files(SKILL)
    assert_true(
        skill_files == EXPECTED_SKILL_FILES,
        f"V4 skill file set is exact: {sorted(skill_files)}",
    )

    skill_text = read(SKILL / "SKILL.md")
    meta = frontmatter(skill_text)
    assert_true(meta.get("name") == "authoring-goals", "portable skill name")
    description = meta.get("description", "")
    assert_true(0 < len(description) <= 1024, "skill description length")
    assert_true("Use when the task involves: (1)" in description, "description has numbered triggers")
    assert_contains_all(
        skill_text,
        [
            "decision-funnel skill",
            "Design-shaped",
            "Chosen direction",
            "Ready to build",
            "Known change",
            "Option Map",
            "Probe Pack",
            "Probe Note",
            "context/docs/",
            "only after the direction is chosen or accepted",
            "<skills-file-root>/references/decision-funnel.md",
            "<skills-file-root>/references/option-map.md",
            "<skills-file-root>/references/probe-pack.md",
        ],
        "SKILL.md",
    )
    assert_avoids(skill_text, FORBIDDEN_PUBLIC_TERMS, "SKILL.md")
    assert_true("templates/" not in skill_text.lower(), "SKILL.md does not reference templates")

    funnel = read(REFERENCES / "decision-funnel.md")
    assert_contains_all(
        funnel,
        [
            "Design-shaped",
            "Chosen direction",
            "Ready-to-build",
            "Known-change",
            "True blockers",
            "Safe defaults",
            "Generate a Probe Note only",
        ],
        "decision funnel",
    )

    option_map = read(REFERENCES / "option-map.md")
    assert_contains_all(
        option_map,
        [
            "An Option Map is the design-phase output.",
            "Plausible directions",
            "Recommended direction",
            "Avoid option theater",
            "Do not write this to `context/docs/` until the user accepts or chooses a direction.",
        ],
        "option map",
    )

    probe_pack = read(REFERENCES / "probe-pack.md")
    assert_contains_all(
        probe_pack,
        [
            "A Probe Pack is the execution-pressure output.",
            "Acceptance probes",
            "Adversarial probes",
            "Compatibility probes",
            "Probe Note",
            "A planned execution handoff is ready only when it includes probes.",
            "Final Source-Review Checklist",
        ],
        "probe pack",
    )

    examples = read(REFERENCES / "examples.md")
    assert_contains_all(
        examples,
        [
            "## Example: Vague Design Prompt",
            "## Example: Known Bugfix Probe Note",
            "## Example: PRD Option Map",
            "## Example: Post-Convergence Decision Capture",
            "## Example: Ready-To-Build Probe Pack",
            "context/docs/recipe-search-decision.md",
            "metadata-bearing list",
            "Any implementation is acceptable if it passes the probes",
        ],
        "examples",
    )
    assert_true("Do not write `context/docs/` before the user chooses" in examples, "examples demonstrate delayed files")
    assert_avoids(examples, ["goalmap", "/goal", "context/goals"], "examples")

    anti = read(REFERENCES / "anti-patterns.md")
    assert_contains_all(
        anti,
        [
            "Premature Docs",
            "False Blockers",
            "Option Theater",
            "Probe-Free Handoff",
            "HOW Leakage",
            "Lost Rejected Alternatives",
            "Runtime Overreach",
        ],
        "anti-patterns",
    )
    assert_true("lock files" in anti and "hooks" in anti, "anti-patterns contains legacy terms only as failures")

    evaluation = read(REFERENCES / "evaluation.md")
    assert_contains_all(
        evaluation,
        [
            "design clarity",
            "Option Map",
            "Probe Pack",
            "Probe Note",
            "Convergence quality",
            "Default handling",
            "Premature docs",
            "False blocker",
        ],
        "evaluation guide",
    )
    assert_true("final product lift second" in evaluation, "evaluation sets design-first north star")

    public_docs = "\n".join(
        read(path)
        for path in [
            SKILL / "SKILL.md",
            REFERENCES / "decision-funnel.md",
            REFERENCES / "option-map.md",
            REFERENCES / "probe-pack.md",
            REFERENCES / "examples.md",
            REFERENCES / "evaluation.md",
        ]
    )
    assert_avoids(public_docs, FORBIDDEN_PUBLIC_TERMS, "public docs")

    print("GoalSpec V4 smoke tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
