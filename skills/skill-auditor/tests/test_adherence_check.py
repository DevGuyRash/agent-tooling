from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "adherence_check.sh"


def write_skill_fixture(skill_dir: Path) -> None:
    (skill_dir / "scripts").mkdir(parents=True, exist_ok=True)
    (skill_dir / "references").mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "# Skill\n\naudit-skill next-steps\naudit-skill step <N>\nIF the CLI is unavailable, use fallback docs.\n",
        encoding="utf-8",
    )
    (skill_dir / "scripts" / "audit-skill.toml").write_text(
        '[domains.D20]\nscript = "scripts/adherence_check.sh"\n',
        encoding="utf-8",
    )
    (skill_dir / "references" / "domains-analysis.md").write_text(
        "next-step guidance\nCLI with no args prints usage\n",
        encoding="utf-8",
    )


class AdherenceCheckTests(unittest.TestCase):
    def test_uses_nearest_ancestor_agents_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_dir = Path(tmp) / "repo-root"
            skill_dir = repo_dir / "nested" / "test-skill"
            skill_dir.mkdir(parents=True)
            (repo_dir / "AGENTS.md").write_text(
                "CLI-served self-documentation\n",
                encoding="utf-8",
            )
            write_skill_fixture(skill_dir)

            completed = subprocess.run(
                ["sh", str(SCRIPT), str(skill_dir)],
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 0)
        self.assertIn(
            "AGENTS.md documents CLI-served self-documentation",
            completed.stdout,
        )
        self.assertIn("Issues found: 0", completed.stdout)

    def test_skips_agents_absorption_when_no_governing_agents_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "standalone-skill"
            skill_dir.mkdir(parents=True)
            write_skill_fixture(skill_dir)

            completed = subprocess.run(
                ["sh", str(SCRIPT), str(skill_dir)],
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("No governing AGENTS.md found", completed.stdout)
        self.assertIn("Issues found: 0", completed.stdout)


if __name__ == "__main__":
    unittest.main()
