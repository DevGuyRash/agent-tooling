from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ears_check.sh"


def run_ears_check(skill_dir: Path) -> str:
    return subprocess.check_output(["sh", str(SCRIPT), str(skill_dir)], text=True)


class EarsCheckTests(unittest.TestCase):
    def test_excludes_tests_markdown_from_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            (skill_dir / "SKILL.md").write_text(
                "# Skill\n\nWHEN validating output, the agent SHALL record the result.\n",
                encoding="utf-8",
            )
            tests_dir = skill_dir / "tests"
            tests_dir.mkdir(parents=True)
            (tests_dir / "fixture.md").write_text(
                "Run the sample command.\n",
                encoding="utf-8",
            )

            output = run_ears_check(skill_dir)

        self.assertIn("SKILL.md", output)
        self.assertNotIn("tests/fixture.md", output)
        self.assertIn("EARS coverage: 100%", output)
        self.assertNotIn("Top Bare Imperatives", output)


if __name__ == "__main__":
    unittest.main()
