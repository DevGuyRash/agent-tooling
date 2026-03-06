from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "credential_check.sh"


class CredentialCheckTests(unittest.TestCase):
    def test_fails_for_unignored_secret_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            (skill_dir / ".env").write_text("SECRET=value\n", encoding="utf-8")

            completed = subprocess.run(
                ["sh", str(SCRIPT), str(skill_dir)],
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 1)
        self.assertIn("potential secret file not in .gitignore", completed.stdout)
        self.assertNotIn("No committed secret files detected", completed.stdout)
        self.assertIn("Issues found: 1", completed.stdout)

    def test_passes_for_gitignored_secret_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp)
            (skill_dir / ".env").write_text("SECRET=value\n", encoding="utf-8")
            (skill_dir / ".gitignore").write_text(".env\n", encoding="utf-8")

            completed = subprocess.run(
                ["sh", str(SCRIPT), str(skill_dir)],
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 0)
        self.assertIn(".env — in .gitignore", completed.stdout)
        self.assertIn("Issues found: 0", completed.stdout)


if __name__ == "__main__":
    unittest.main()
