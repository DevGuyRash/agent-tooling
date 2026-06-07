from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "commit-message.py"


class CommitMessageScriptTests(unittest.TestCase):
    def run_script(self, *args: str, check: bool = False):
        return subprocess.run(
            ["python3", str(SCRIPT), *args],
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            check=check,
        )

    def test_generates_message_with_required_bullets(self):
        proc = self.run_script(
            "--type",
            "chore",
            "--scope",
            "submodules",
            "--subject",
            "update gitlinks",
            "--bullet",
            "update deps/child to abc12345",
            "--bullet",
            "keep unrelated staged files out of the commit",
            check=True,
        )
        self.assertEqual(
            proc.stdout,
            "chore(submodules): update gitlinks\n\n"
            "- update deps/child to abc12345\n"
            "- keep unrelated staged files out of the commit\n",
        )

    def test_rejects_missing_body_bullets(self):
        proc = self.run_script(
            "--type",
            "feat",
            "--subject",
            "add raw sync",
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("at least one --bullet is required", proc.stderr)

    def test_writes_output_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out = Path(temp_dir) / "message.txt"
            proc = self.run_script(
                "--type",
                "fix",
                "--scope",
                "sync",
                "--subject",
                "preserve current branch",
                "--bullet",
                "keep raw sync in-place",
                "--out",
                str(out),
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(out.exists())
            self.assertIn("fix(sync): preserve current branch", out.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
