from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit-skill"


def run_cli(*args: str) -> str:
    return subprocess.check_output(["sh", str(SCRIPT), *args], text=True)


class AuditSkillCliTests(unittest.TestCase):
    def test_usage_mentions_step_command(self):
        output = run_cli()
        self.assertIn("step <N>", output)
        self.assertIn("next-steps", output)

    def test_next_steps_json_includes_titles_and_next_commands(self):
        output = run_cli("next-steps", "--format", "json")
        data = json.loads(output)

        self.assertEqual(data["steps"][0]["step"], "1")
        self.assertIn("title", data["steps"][0])
        self.assertIn("next_command", data["steps"][0])

    def test_step_json_returns_guidance(self):
        output = run_cli("step", "6", "--format", "json")
        data = json.loads(output)

        self.assertEqual(data["step"], "6")
        self.assertIn("check-all", data["command"])
        self.assertIn("domains", data)

    def test_check_preserves_quoted_skill_directory_argument(self):
        with tempfile.TemporaryDirectory(prefix="skill path ") as tmp:
            skill_dir = Path(tmp)
            (skill_dir / "SKILL.md").write_text("# Skill\n", encoding="utf-8")

            completed = subprocess.run(
                ["sh", str(SCRIPT), "check", "surface", str(skill_dir)],
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("Surface Check", completed.stdout)
        self.assertNotIn("error: not a directory", completed.stdout)


if __name__ == "__main__":
    unittest.main()
