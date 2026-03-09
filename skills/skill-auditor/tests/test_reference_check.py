from __future__ import annotations

import json
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "reference_check.sh"


def run_reference_check(skill_dir: Path) -> tuple[subprocess.CompletedProcess[str], dict]:
    completed = subprocess.run(
        ["sh", str(SCRIPT), str(skill_dir), "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed, json.loads(completed.stdout)


class ReferenceCheckTests(unittest.TestCase):
    def test_valid_relative_references_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "demo-skill"
            refs_dir = skill_dir / "references"
            skill_dir.mkdir()
            refs_dir.mkdir()
            (refs_dir / "packaging-fit.md").write_text("# Packaging\n", encoding="utf-8")
            (skill_dir / "SKILL.md").write_text(
                textwrap.dedent(
                    """\
                    ---
                    name: demo-skill
                    description: >-
                      Check a demo skill and explain what it does. Use when
                      reviewing demo skills.
                    ---

                    - Packaging fit → `references/packaging-fit.md`
                    """
                ),
                encoding="utf-8",
            )

            completed, data = run_reference_check(skill_dir)

        self.assertEqual(completed.returncode, 0)
        self.assertTrue(data["ok"])

    def test_tokenized_reference_paths_also_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "demo-skill"
            refs_dir = skill_dir / "references"
            skill_dir.mkdir()
            refs_dir.mkdir()
            (refs_dir / "packaging-fit.md").write_text("# Packaging\n", encoding="utf-8")
            (skill_dir / "SKILL.md").write_text(
                textwrap.dedent(
                    """\
                    ---
                    name: demo-skill
                    description: >-
                      Check a demo skill and explain what it does. Use when
                      reviewing demo skills.
                    ---

                    - Packaging fit → `<skills-file-root>/references/packaging-fit.md`
                    """
                ),
                encoding="utf-8",
            )

            completed, data = run_reference_check(skill_dir)

        self.assertEqual(completed.returncode, 0)
        self.assertTrue(data["ok"])

    def test_flags_unlinked_active_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "demo-skill"
            refs_dir = skill_dir / "references"
            skill_dir.mkdir()
            refs_dir.mkdir()
            (refs_dir / "packaging-fit.md").write_text("# Packaging\n", encoding="utf-8")
            (refs_dir / "trigger-evals.md").write_text("# Trigger\n", encoding="utf-8")
            (skill_dir / "SKILL.md").write_text(
                textwrap.dedent(
                    """\
                    ---
                    name: demo-skill
                    description: >-
                      Check a demo skill and explain what it does. Use when
                      reviewing demo skills.
                    ---

                    - Packaging fit → `references/packaging-fit.md`
                    """
                ),
                encoding="utf-8",
            )

            completed, data = run_reference_check(skill_dir)

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("unlinked_reference", {issue["code"] for issue in data["issues"]})

    def test_flags_nested_reference_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "demo-skill"
            refs_dir = skill_dir / "references"
            skill_dir.mkdir()
            refs_dir.mkdir()
            (refs_dir / "packaging-fit.md").write_text(
                "See references/trigger-evals.md for more.\n",
                encoding="utf-8",
            )
            (refs_dir / "trigger-evals.md").write_text("# Trigger\n", encoding="utf-8")
            (skill_dir / "SKILL.md").write_text(
                textwrap.dedent(
                    """\
                    ---
                    name: demo-skill
                    description: >-
                      Check a demo skill and explain what it does. Use when
                      reviewing demo skills.
                    ---

                    - Packaging fit → `references/packaging-fit.md`
                    - Trigger fit → `references/trigger-evals.md`
                    """
                ),
                encoding="utf-8",
            )

            completed, data = run_reference_check(skill_dir)

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("nested_reference_link", {issue["code"] for issue in data["issues"]})

    def test_active_skill_passes(self) -> None:
        completed, data = run_reference_check(ROOT)

        self.assertEqual(completed.returncode, 0)
        self.assertTrue(data["ok"])


if __name__ == "__main__":
    unittest.main()
