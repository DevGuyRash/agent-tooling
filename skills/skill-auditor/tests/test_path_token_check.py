from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "path_token_check.sh"


def run_path_token_check(skill_dir: Path) -> str:
    return subprocess.check_output(["sh", str(SCRIPT), str(skill_dir)], text=True)


class PathTokenCheckTests(unittest.TestCase):
    def test_flags_bare_scripts_path_without_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            scripts_dir = skill_dir / "scripts"
            scripts_dir.mkdir(parents=True)
            (scripts_dir / "run.sh").write_text("#!/usr/bin/env sh\n", encoding="utf-8")
            (skill_dir / "SKILL.md").write_text(
                "# Skill\n\nUse scripts/run.sh to do the thing.\n",
                encoding="utf-8",
            )

            output = run_path_token_check(skill_dir)

        self.assertIn('bare path "scripts/run.sh"', output)
        self.assertIn("Issues found: 1", output)

    def test_ignores_scripts_path_with_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            scripts_dir = skill_dir / "scripts"
            scripts_dir.mkdir(parents=True)
            (scripts_dir / "run.sh").write_text("#!/usr/bin/env sh\n", encoding="utf-8")
            (skill_dir / "SKILL.md").write_text(
                "# Skill\n\nUse <skills-file-root>/scripts/run.sh to do the thing.\n",
                encoding="utf-8",
            )

            output = run_path_token_check(skill_dir)

        self.assertIn("All path references use <skills-file-root> correctly", output)
        self.assertNotIn('bare path "scripts/run.sh"', output)

    def test_ignores_non_path_prose_with_scripts_slash(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            scripts_dir = skill_dir / "scripts" / "binaries"
            scripts_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "| Note |\n|------|\n| CLI-heavy (scripts/binaries) |\n",
                encoding="utf-8",
            )

            output = run_path_token_check(skill_dir)

        self.assertIn("All path references use <skills-file-root> correctly", output)
        self.assertNotIn('bare path "scripts/binaries"', output)

    def test_flags_bare_scripts_path_inside_fenced_code_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            scripts_dir = skill_dir / "scripts"
            scripts_dir.mkdir(parents=True)
            (scripts_dir / "run.sh").write_text("#!/usr/bin/env sh\n", encoding="utf-8")
            (skill_dir / "SKILL.md").write_text(
                "# Skill\n\n```bash\ncat scripts/run.sh\n```\n",
                encoding="utf-8",
            )

            output = run_path_token_check(skill_dir)

        self.assertIn('bare path "scripts/run.sh"', output)
        self.assertIn("Issues found: 1", output)

    def test_flags_bare_path_in_markdown_link_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            references_dir = skill_dir / "references"
            references_dir.mkdir(parents=True)
            (references_dir / "guide.md").write_text("# Guide\n", encoding="utf-8")
            (skill_dir / "SKILL.md").write_text(
                "# Skill\n\nSee [guide](references/guide.md).\n",
                encoding="utf-8",
            )

            output = run_path_token_check(skill_dir)

        self.assertIn('bare path "references/guide.md"', output)
        self.assertIn("Issues found: 1", output)

    def test_ignores_markdown_under_tests_subtree(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            tests_fixture_dir = skill_dir / "tests" / "fixtures"
            tests_fixture_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text("# Skill\n\nNo issues here.\n", encoding="utf-8")
            (tests_fixture_dir / "example.md").write_text(
                "# Fixture\n\nSee ../linked-guidance.md for context.\n",
                encoding="utf-8",
            )

            output = run_path_token_check(skill_dir)

        self.assertIn("All path references use <skills-file-root> correctly", output)
        self.assertNotIn("parent traversal", output)

    def test_only_counts_production_markdown_when_tests_also_contain_issues(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            scripts_dir = skill_dir / "scripts"
            tests_fixture_dir = skill_dir / "tests" / "fixtures"
            scripts_dir.mkdir(parents=True)
            tests_fixture_dir.mkdir(parents=True)
            (scripts_dir / "run.sh").write_text("#!/usr/bin/env sh\n", encoding="utf-8")
            (skill_dir / "SKILL.md").write_text(
                "# Skill\n\nRun scripts/run.sh now\n",
                encoding="utf-8",
            )
            (tests_fixture_dir / "example.md").write_text(
                "# Fixture\n\nSee ../linked-guidance.md for context.\n",
                encoding="utf-8",
            )

            output = run_path_token_check(skill_dir)

        self.assertIn('bare path "scripts/run.sh"', output)
        self.assertNotIn("parent traversal", output)
        self.assertIn("Issues found: 1", output)


if __name__ == "__main__":
    unittest.main()
