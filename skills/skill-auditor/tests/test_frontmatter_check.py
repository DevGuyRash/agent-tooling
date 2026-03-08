from __future__ import annotations

import json
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "frontmatter_check.sh"


def run_frontmatter_check(skill_dir: Path) -> tuple[subprocess.CompletedProcess[str], dict]:
    completed = subprocess.run(
        ["sh", str(SCRIPT), str(skill_dir), "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed, json.loads(completed.stdout)


class FrontmatterCheckTests(unittest.TestCase):
    def test_valid_skill_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "demo-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                textwrap.dedent(
                    """\
                    ---
                    name: demo-skill
                    description: >-
                      Check a demo skill and explain what it does. Use when
                      reviewing demo skills.
                    ---

                    # Demo Skill
                    """
                ),
                encoding="utf-8",
            )

            completed, data = run_frontmatter_check(skill_dir)

        self.assertEqual(completed.returncode, 0)
        self.assertTrue(data["ok"])
        self.assertEqual(data["issue_count"], 0)

    def test_missing_use_when_trigger_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "demo-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                textwrap.dedent(
                    """\
                    ---
                    name: demo-skill
                    description: Helps with demo skills.
                    ---
                    """
                ),
                encoding="utf-8",
            )

            completed, data = run_frontmatter_check(skill_dir)

        self.assertNotEqual(completed.returncode, 0)
        self.assertFalse(data["ok"])
        self.assertIn("description_trigger", {issue["code"] for issue in data["issues"]})

    def test_active_skill_passes(self) -> None:
        completed, data = run_frontmatter_check(ROOT)

        self.assertEqual(completed.returncode, 0)
        self.assertTrue(data["ok"])


if __name__ == "__main__":
    unittest.main()
